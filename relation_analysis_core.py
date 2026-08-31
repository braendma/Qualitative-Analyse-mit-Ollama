# relation_analysis_core.py

import itertools
import json
import logging
from datetime import datetime

from clusterer_core import ollama_chat, safe_json_loads
from utils_prompt import build_prompt_for_module

logger = logging.getLogger("relation_analysis")

ALLOWED_RELATION_TYPES = {
    "tritt_gemeinsam_auf",
    "steht_in_spannung_zu",
    "wird_miteinander_verknuepft",
    "scheint_voraussetzung_zu_sein",
    "wird_als_folge_beschrieben",
    "sonstige_beziehung",
}


def _person_from_sid(sid: str) -> str:
    sid = str(sid)
    return sid.split("#SEG", 1)[0].strip() if "#SEG" in sid else sid.strip()


def _path_for_cluster(cluster: dict) -> str:
    parts = [
        cluster.get("hauptkategorie"),
        cluster.get("subkategorie"),
        cluster.get("facette"),
    ]
    return " > ".join(str(x).strip() for x in parts if x is not None and str(x).strip())


def _summary_index(summary_data: dict) -> dict:
    index = {}
    for item in summary_data.get("cluster_summaries", []):
        if not isinstance(item, dict):
            continue
        key = (
            item.get("hauptkategorie"),
            item.get("subkategorie"),
            item.get("facette"),
            item.get("cluster_name"),
        )
        index[key] = str(item.get("summary", "")).strip()
    return index


def build_units(clusters: list, id_to_text: dict, summary_data: dict) -> dict:
    summaries = _summary_index(summary_data)
    units = {}

    for cluster in clusters:
        if not isinstance(cluster, dict):
            continue
        path = _path_for_cluster(cluster)
        if not path:
            continue

        unit = units.setdefault(
            path,
            {
                "pfad": path,
                "hauptkategorie": cluster.get("hauptkategorie"),
                "subkategorie": cluster.get("subkategorie"),
                "facette": cluster.get("facette"),
                "cluster": [],
                "segment_ids": [],
                "personen": [],
            },
        )

        seg_ids = [str(x).strip() for x in cluster.get("segments", []) if str(x).strip()]
        key = (
            cluster.get("hauptkategorie"),
            cluster.get("subkategorie"),
            cluster.get("facette"),
            cluster.get("cluster_name"),
        )
        unit["cluster"].append(
            {
                "cluster_name": str(cluster.get("cluster_name", "Unbenannt")).strip(),
                "definition": str(cluster.get("definition", "")).strip(),
                "summary": summaries.get(key, ""),
                "segment_ids": seg_ids,
            }
        )
        unit["segment_ids"].extend(seg_ids)

    for unit in units.values():
        unit["segment_ids"] = list(dict.fromkeys(unit["segment_ids"]))
        unit["personen"] = list(
            dict.fromkeys(_person_from_sid(sid) for sid in unit["segment_ids"])
        )
        unit["segmente"] = [
            {"id": sid, "text": str(id_to_text.get(sid, ""))}
            for sid in unit["segment_ids"]
            if sid in id_to_text
        ]

    return units


def build_candidate_pairs(units: dict, max_pairs: int, max_segments_per_path: int) -> tuple[list, int]:
    candidates = []
    paths = sorted(units)

    for path_a, path_b in itertools.combinations(paths, 2):
        a = units[path_a]
        b = units[path_b]
        shared = sorted(set(a["personen"]) & set(b["personen"]))
        if not shared:
            continue

        candidates.append((len(shared), path_a, path_b, shared))

    candidates.sort(key=lambda x: (-x[0], x[1], x[2]))
    total = len(candidates)
    selected = candidates[:max(0, max_pairs)] if max_pairs > 0 else candidates

    payload = []
    for idx, (_, path_a, path_b, shared) in enumerate(selected, start=1):
        a = units[path_a]
        b = units[path_b]
        shared_set = set(shared)
        sample_a = [
            s for s in a["segmente"]
            if _person_from_sid(s["id"]) in shared_set
        ][:max_segments_per_path]
        sample_b = [
            s for s in b["segmente"]
            if _person_from_sid(s["id"]) in shared_set
        ][:max_segments_per_path]

        payload.append(
            {
                "pair_id": f"PAIR{idx:04d}",
                "pfad_a": path_a,
                "pfad_b": path_b,
                "gemeinsame_personen": shared,
                "anzahl_gemeinsame_personen": len(shared),
                "cluster_a": a["cluster"],
                "cluster_b": b["cluster"],
                "segmente_a": sample_a,
                "segmente_b": sample_b,
            }
        )

    return payload, total


def _llm(system_prompt, user_prompt, ollama_params):
    for attempt in range(3):
        logger.info("[Zusammenhangsanalyse-Retry] Versuch %s/3", attempt + 1)
        content = ollama_chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=ollama_params["model"],
            temperature=ollama_params["temperature"],
            max_tokens=ollama_params["max_tokens"],
            think=ollama_params.get("think"),
            log_thinking=ollama_params.get("log_thinking", False),
        )
        logger.info("\n===== RAW RELATION OUTPUT =====\n%s\n===============================\n", content)
        if content:
            return content.strip()
    return ""


def _repair(broken_output, ollama_params):
    system = """
Du reparierst ausschließlich JSON für eine qualitative Zusammenhangsanalyse.
Gib genau ein Objekt mit den Schlüsseln \"beziehungen\" und \"gesamteinordnung\" zurück.
\"beziehungen\" ist eine Liste. Jeder Eintrag enthält exakt:
pair_id, thema, beziehungstyp, beschreibung, segment_ids_a, segment_ids_b.
segment_ids_a und segment_ids_b sind Listen von Strings.
Keine neuen Inhalte. Kein Markdown. Kein Text außerhalb des JSON.
""".strip()
    return ollama_chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Repariere folgende Antwort:\n\n{broken_output}"},
        ],
        model=ollama_params["model"],
        temperature=0.0,
        max_tokens=ollama_params["max_tokens"],
        think=ollama_params.get("think"),
        log_thinking=ollama_params.get("log_thinking", False),
    ) or ""


def normalize_relations(parsed: dict, pair_lookup: dict, id_to_text: dict) -> dict:
    if not isinstance(parsed, dict):
        return None

    raw = parsed.get("beziehungen", [])
    if not isinstance(raw, list):
        raw = [raw] if raw else []

    out = []
    used_pairs = set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        pair_id = str(entry.get("pair_id", "")).strip()
        pair = pair_lookup.get(pair_id)
        if pair is None or pair_id in used_pairs:
            continue

        rel_type = str(entry.get("beziehungstyp", "sonstige_beziehung")).strip()
        if rel_type not in ALLOWED_RELATION_TYPES:
            rel_type = "sonstige_beziehung"

        allowed_a = {x["id"] for x in pair.get("segmente_a", [])}
        allowed_b = {x["id"] for x in pair.get("segmente_b", [])}
        ids_a = [str(x).strip() for x in entry.get("segment_ids_a", []) if str(x).strip() in allowed_a]
        ids_b = [str(x).strip() for x in entry.get("segment_ids_b", []) if str(x).strip() in allowed_b]
        ids_a = list(dict.fromkeys(ids_a))
        ids_b = list(dict.fromkeys(ids_b))

        # Eine Relation muss auf beiden Seiten empirisch rückverfolgbar sein.
        if not ids_a or not ids_b:
            logger.warning("[Zusammenhangsanalyse] Relation %s ohne beidseitige Belege verworfen.", pair_id)
            continue

        out.append(
            {
                "relation_id": f"REL{len(out) + 1:04d}",
                "pair_id": pair_id,
                "thema": str(entry.get("thema", "")).strip() or "Unbenannte Beziehung",
                "beziehungstyp": rel_type,
                "beschreibung": str(entry.get("beschreibung", "")).strip(),
                "pfad_a": pair["pfad_a"],
                "pfad_b": pair["pfad_b"],
                "gemeinsame_personen": pair["gemeinsame_personen"],
                "segment_ids_a": ids_a,
                "segment_ids_b": ids_b,
                "belege_a": [{"segment_id": sid, "text": id_to_text.get(sid, "")} for sid in ids_a],
                "belege_b": [{"segment_id": sid, "text": id_to_text.get(sid, "")} for sid in ids_b],
            }
        )
        used_pairs.add(pair_id)

    return {
        "beziehungen": out,
        "gesamteinordnung": str(parsed.get("gesamteinordnung", "")).strip(),
    }


def build_relation_analysis(
    clusters_json_path: str,
    id_to_text_path: str,
    summary_json_path: str,
    ollama_params: dict,
    prompts: dict,
    context: dict,
    max_pairs: int = 80,
    max_segments_per_path: int = 6,
):
    with open(clusters_json_path, "r", encoding="utf-8") as f:
        cluster_data = json.load(f)
    with open(id_to_text_path, "r", encoding="utf-8") as f:
        id_to_text = json.load(f)
    with open(summary_json_path, "r", encoding="utf-8") as f:
        summary_data = json.load(f)

    units = build_units(cluster_data.get("clusters", []), id_to_text, summary_data)
    pairs, total_candidates = build_candidate_pairs(units, max_pairs, max_segments_per_path)
    pair_lookup = {p["pair_id"]: p for p in pairs}

    if not pairs:
        normalized = {"beziehungen": [], "gesamteinordnung": "Keine Codepfad-Paare mit gemeinsamen Fällen gefunden."}
    else:
        system_prompt, user_prompt = build_prompt_for_module(
            "relation_analysis",
            prompts=prompts,
            context=context,
            data=json.dumps({"kandidaten": pairs}, ensure_ascii=False, indent=2),
        )
        raw = _llm(system_prompt, user_prompt, ollama_params)
        parsed = safe_json_loads(raw)
        if parsed is None:
            logger.warning("[Zusammenhangsanalyse] Ungültiges JSON; starte Repair.")
            parsed = safe_json_loads(_repair(raw, ollama_params))
        if parsed is None:
            raise ValueError("Zusammenhangsanalyse konnte nicht als JSON gelesen werden.")
        normalized = normalize_relations(parsed, pair_lookup, id_to_text)
        if normalized is None:
            raise ValueError("Zusammenhangsanalyse besitzt kein verwertbares Format.")

    json_output = {
        "created_at": datetime.now().isoformat(),
        "source_cluster_created_at": cluster_data.get("created_at"),
        "source_summary_created_at": summary_data.get("created_at"),
        "codepfad_count": len(units),
        "candidate_pair_count_total": total_candidates,
        "candidate_pair_count_analyzed": len(pairs),
        **normalized,
    }

    md = [
        "# Zusammenhangsanalyse\n",
        f"Erstellt am: {json_output['created_at']}\n\n",
        f"Analysierte Codepfade: **{len(units)}** · Kandidatenpaare: **{len(pairs)}** von **{total_candidates}**\n\n",
        "Die Beziehungen sind qualitative, datenbasierte Relationen. Sie sind nicht automatisch als Kausalität zu verstehen.\n\n",
    ]
    if normalized["gesamteinordnung"]:
        md.append(f"## Gesamteinordnung\n\n{normalized['gesamteinordnung']}\n\n")

    md.append("## Identifizierte Beziehungen\n\n")
    if not normalized["beziehungen"]:
        md.append("_Keine belastbaren Beziehungen identifiziert._\n")
    else:
        for rel in normalized["beziehungen"]:
            md.append(f"### {rel['thema']}\n\n")
            md.append(f"**Typ:** `{rel['beziehungstyp']}`\n\n")
            md.append(f"**Codepfade:** {rel['pfad_a']} ↔ {rel['pfad_b']}\n\n")
            md.append(f"{rel['beschreibung']}\n\n")
            if rel["gemeinsame_personen"]:
                md.append(f"**Gemeinsame Fälle:** {', '.join(rel['gemeinsame_personen'])}\n\n")
            md.append("**Belege Pfad A:**\n\n")
            for b in rel["belege_a"]:
                md.append(f"- `{b['segment_id']}`: {b['text']}\n")
            md.append("\n**Belege Pfad B:**\n\n")
            for b in rel["belege_b"]:
                md.append(f"- `{b['segment_id']}`: {b['text']}\n")
            md.append("\n")

    return "".join(md), json_output
