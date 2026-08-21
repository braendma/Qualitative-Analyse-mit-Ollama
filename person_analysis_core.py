# person_analysis_core.py

import json
import logging
from datetime import datetime

from utils_prompt import build_prompt_for_module
from clusterer_core import ollama_chat, safe_json_loads

logger = logging.getLogger("person_analysis")


def llm_person_analysis(system_prompt: str, user_prompt: str, ollama_params: dict) -> str:
    for attempt in range(3):
        logger.info(f"[Personenanalyse-Retry] Versuch {attempt + 1}/3")
        content = ollama_chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=ollama_params["model"],
            temperature=ollama_params["temperature"],
            max_tokens=ollama_params["max_tokens"],
        )
        logger.info("\n===== RAW PERSONENANALYSE OUTPUT =====\n%s\n======================================\n", content)
        if content:
            return content.strip()
    logger.error("[Personenanalyse] Nach 3 Versuchen keine gültige Antwort.")
    return ""


def llm_repair_person_analysis(broken_output: str, ollama_params: dict) -> str:
    system_prompt = """
Du reparierst ausschließlich JSON.
Gib ausschließlich ein gültiges JSON-Objekt zurück.
Die obersten Schlüssel müssen exakt sein:
- zentrale_themen
- perspektiven
- spannungsfelder
- kontrastierende_aspekte
- gesamtverdichtung

zentrale_themen ist eine Liste aus Objekten mit:
- thema
- verdichtung
- segment_ids

perspektiven ist eine Liste aus Objekten mit:
- aussage
- segment_ids

spannungsfelder ist eine Liste aus Objekten mit:
- beschreibung
- segment_ids

kontrastierende_aspekte ist eine Liste aus Objekten mit:
- beschreibung
- segment_ids

segment_ids ist immer eine Liste von Strings.
gesamtverdichtung ist ein String.
Keine neuen Inhalte hinzufügen. Kein Markdown. Keine Erklärung.
""".strip()

    for attempt in range(3):
        logger.info(f"[Personenanalyse-Repair] Versuch {attempt + 1}/3")
        content = ollama_chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Repariere folgende Antwort:\n\n{broken_output}"},
            ],
            model=ollama_params["model"],
            temperature=0.0,
            max_tokens=ollama_params["max_tokens"],
        )
        if content:
            return content.strip()
    return ""


def person_from_segment_id(segment_id: str) -> str:
    sid = str(segment_id).strip()
    if "#SEG" in sid:
        return sid.split("#SEG", 1)[0].strip()
    return sid


def build_summary_index(summary_data: dict):
    exact = {}
    by_name = {}
    for item in summary_data.get("cluster_summaries", []):
        if not isinstance(item, dict):
            continue
        key = (
            item.get("hauptkategorie"),
            item.get("subkategorie"),
            item.get("facette"),
            item.get("cluster_name"),
        )
        exact[key] = item.get("summary", "")
        by_name.setdefault(item.get("cluster_name"), item.get("summary", ""))
    return exact, by_name


def get_cluster_summary(cluster: dict, exact_index: dict, name_index: dict) -> str:
    key = (
        cluster.get("hauptkategorie"),
        cluster.get("subkategorie"),
        cluster.get("facette"),
        cluster.get("cluster_name"),
    )
    return exact_index.get(key) or name_index.get(cluster.get("cluster_name"), "")


def build_person_payloads(clusters: list, id_to_text: dict, summary_data: dict) -> dict:
    exact_index, name_index = build_summary_index(summary_data)
    persons = {}

    for cluster in clusters:
        if not isinstance(cluster, dict):
            continue

        cluster_context = {
            "hauptkategorie": cluster.get("hauptkategorie"),
            "subkategorie": cluster.get("subkategorie"),
            "facette": cluster.get("facette"),
            "cluster_name": cluster.get("cluster_name", "Unbenannt"),
            "definition": cluster.get("definition", ""),
            "summary": get_cluster_summary(cluster, exact_index, name_index),
        }

        for raw_sid in cluster.get("segments", []):
            sid = str(raw_sid).strip()
            if not sid:
                continue

            person = person_from_segment_id(sid)
            pdata = persons.setdefault(
                person,
                {
                    "person": person,
                    "segments": {},
                },
            )

            segment = pdata["segments"].setdefault(
                sid,
                {
                    "id": sid,
                    "text": id_to_text.get(sid, ""),
                    "cluster_contexts": [],
                },
            )

            if cluster_context not in segment["cluster_contexts"]:
                segment["cluster_contexts"].append(cluster_context)

    result = {}
    for person, pdata in persons.items():
        result[person] = {
            "person": person,
            "segments": list(pdata["segments"].values()),
        }
    return result


def _clean_ids(value, allowed_ids):
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []

    cleaned = []
    for sid in value:
        sid = str(sid).strip()
        if sid in allowed_ids and sid not in cleaned:
            cleaned.append(sid)
    return cleaned


def _normalize_list(parsed, key, text_key, allowed_ids):
    value = parsed.get(key, []) if isinstance(parsed, dict) else []
    if value is None:
        value = []
    if not isinstance(value, list):
        value = [value]

    out = []
    for entry in value:
        if isinstance(entry, dict):
            text = str(entry.get(text_key, "")).strip()
            segment_ids = _clean_ids(entry.get("segment_ids", []), allowed_ids)
        else:
            text = str(entry).strip()
            segment_ids = []
        if text:
            out.append({text_key: text, "segment_ids": segment_ids})
    return out


def normalize_person_analysis(parsed: dict, allowed_ids: set, id_to_text: dict) -> dict:
    if not isinstance(parsed, dict):
        return None

    zentrale_themen_raw = parsed.get("zentrale_themen", [])
    if zentrale_themen_raw is None:
        zentrale_themen_raw = []
    if not isinstance(zentrale_themen_raw, list):
        zentrale_themen_raw = [zentrale_themen_raw]

    zentrale_themen = []
    for entry in zentrale_themen_raw:
        if isinstance(entry, dict):
            thema = str(entry.get("thema", "")).strip()
            verdichtung = str(entry.get("verdichtung", "")).strip()
            ids = _clean_ids(entry.get("segment_ids", []), allowed_ids)
        else:
            thema = str(entry).strip()
            verdichtung = ""
            ids = []
        if thema or verdichtung:
            zentrale_themen.append({
                "thema": thema or "Unbenanntes Thema",
                "verdichtung": verdichtung,
                "segment_ids": ids,
            })

    result = {
        "zentrale_themen": zentrale_themen,
        "perspektiven": _normalize_list(parsed, "perspektiven", "aussage", allowed_ids),
        "spannungsfelder": _normalize_list(parsed, "spannungsfelder", "beschreibung", allowed_ids),
        "kontrastierende_aspekte": _normalize_list(parsed, "kontrastierende_aspekte", "beschreibung", allowed_ids),
        "gesamtverdichtung": str(parsed.get("gesamtverdichtung", "")).strip(),
    }

    used_ids = []
    for section in ["zentrale_themen", "perspektiven", "spannungsfelder", "kontrastierende_aspekte"]:
        for entry in result[section]:
            for sid in entry.get("segment_ids", []):
                if sid not in used_ids:
                    used_ids.append(sid)

    result["belege"] = [
        {"segment_id": sid, "zitat": id_to_text.get(sid, "")}
        for sid in used_ids
        if id_to_text.get(sid, "")
    ]
    return result


def build_person_analysis(
    clusters_json_path: str,
    id_to_text_path: str,
    summary_json_path: str,
    ollama_params: dict,
    prompts: dict,
    context: dict,
):
    logger.info("[Personenanalyse] Lade Inputs…")

    with open(clusters_json_path, "r", encoding="utf-8") as f:
        cluster_data = json.load(f)
    with open(id_to_text_path, "r", encoding="utf-8") as f:
        id_to_text = json.load(f)
    with open(summary_json_path, "r", encoding="utf-8") as f:
        summary_data = json.load(f)

    person_payloads = build_person_payloads(
        cluster_data.get("clusters", []),
        id_to_text,
        summary_data,
    )

    results = {}

    for person in sorted(person_payloads):
        payload = person_payloads[person]
        allowed_ids = {s["id"] for s in payload["segments"]}

        logger.info(
            f"[Personenanalyse] Analysiere {person} mit {len(allowed_ids)} Segmenten."
        )

        system_prompt, user_prompt = build_prompt_for_module(
            "person_analysis",
            prompts=prompts,
            context=context,
            persons=json.dumps(payload, ensure_ascii=False, indent=2),
        )

        raw = llm_person_analysis(system_prompt, user_prompt, ollama_params)
        parsed = safe_json_loads(raw)

        if parsed is None:
            logger.warning(f"[Personenanalyse] JSON für {person} ungültig; starte Repair.")
            repaired = llm_repair_person_analysis(raw, ollama_params)
            parsed = safe_json_loads(repaired)

        if parsed is None:
            logger.error(f"[Personenanalyse] Keine verwertbare Antwort für {person}.")
            continue

        normalized = normalize_person_analysis(parsed, allowed_ids, id_to_text)
        if normalized is None:
            continue

        categories = sorted({
            ctx.get("hauptkategorie")
            for seg in payload["segments"]
            for ctx in seg.get("cluster_contexts", [])
            if ctx.get("hauptkategorie")
        })
        facets = sorted({
            ctx.get("facette")
            for seg in payload["segments"]
            for ctx in seg.get("cluster_contexts", [])
            if ctx.get("facette")
        })

        results[person] = {
            "person": person,
            "segment_ids": sorted(allowed_ids),
            "abgedeckte_hauptkategorien": categories,
            "abgedeckte_facetten": facets,
            **normalized,
        }

    json_output = {
        "created_at": datetime.now().isoformat(),
        "source_cluster_created_at": cluster_data.get("created_at"),
        "persons": results,
    }

    md = ["# Personenanalysen\n", f"Erstellt am: {json_output['created_at']}\n\n"]

    for person, analysis in results.items():
        md.append(f"## {person}\n\n")
        if analysis.get("gesamtverdichtung"):
            md.append(f"**Gesamtverdichtung:** {analysis['gesamtverdichtung']}\n\n")

        md.append("### Zentrale Themen\n\n")
        for entry in analysis.get("zentrale_themen", []):
            md.append(f"- **{entry['thema']}**: {entry['verdichtung']}\n")
        if not analysis.get("zentrale_themen"):
            md.append("_Keine belastbaren zentralen Themen identifiziert._\n")
        md.append("\n")

        for title, key, field in [
            ("Perspektiven", "perspektiven", "aussage"),
            ("Spannungsfelder", "spannungsfelder", "beschreibung"),
            ("Kontrastierende Aspekte", "kontrastierende_aspekte", "beschreibung"),
        ]:
            md.append(f"### {title}\n\n")
            entries = analysis.get(key, [])
            if entries:
                for entry in entries:
                    md.append(f"- {entry[field]}\n")
            else:
                md.append("_Keine Einträge._\n")
            md.append("\n")

        md.append("### Empirische Belege\n\n")
        for beleg in analysis.get("belege", []):
            md.append(f"#### {beleg['segment_id']}\n\n> {beleg['zitat']}\n\n")
        if not analysis.get("belege"):
            md.append("_Keine ausgewählten Belege._\n\n")

    return "\n".join(md), json_output
