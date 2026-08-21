# swot_core.py

import json
import logging
from collections import OrderedDict
from datetime import datetime

from utils_prompt import build_prompt_for_module
from clusterer_core import ollama_chat

logger = logging.getLogger("swot")

DIMENSIONS = ("Stärken", "Schwächen", "Chancen", "Risiken")


def extract_json_from_text(text):
    if not text or not isinstance(text, str):
        return None

    idx_bracket = text.find("[")
    idx_brace = text.find("{")
    starts = [i for i in (idx_bracket, idx_brace) if i != -1]
    if not starts:
        return None

    start = min(starts)
    candidates = [
        i for i, ch in enumerate(text)
        if ch in ("]", "}") and i >= start
    ]

    for end in reversed(candidates):
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            continue
    return None


def safe_json_loads(text, fallback=None):
    if not text or not isinstance(text, str):
        return fallback
    try:
        return json.loads(text)
    except Exception:
        extracted = extract_json_from_text(text)
        return extracted if extracted is not None else fallback


def llm_swot(system_prompt: str, user_prompt: str, ollama_params: dict) -> str:
    for attempt in range(3):
        logger.info("[SWOT-Retry] Versuch %s/3", attempt + 1)
        logger.debug("\n===== SWOT SYSTEM PROMPT =====\n%s\n", system_prompt)
        logger.debug("\n===== SWOT USER PROMPT =====\n%s\n", user_prompt)

        content = ollama_chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=ollama_params["model"],
            temperature=ollama_params["temperature"],
            max_tokens=ollama_params["max_tokens"],
        )

        logger.info(
            "\n===== RAW SWOT OUTPUT =====\n%s\n==============================\n",
            content,
        )

        if content:
            return content.strip()

        logger.warning("[SWOT-Fehler] Leere LLM-Antwort.")

    logger.error("[SWOT-Fehler] Nach 3 Versuchen keine gültige Antwort.")
    return ""


def llm_swot_repair(broken_output: str, ollama_params: dict) -> str:
    """Repariert ausschließlich die Syntax/Struktur einer SWOT-Antwort."""
    system_prompt = """
Du reparierst ausschließlich JSON.

Gib ausschließlich ein gültiges JSON-Objekt zurück.
Das Objekt muss exakt diese vier Schlüssel enthalten:
- Stärken
- Schwächen
- Chancen
- Risiken

Jeder Schlüssel enthält eine Liste.
Jeder Listeneintrag muss exakt diese drei Schlüssel enthalten:
- thema
- analyse
- segment_ids

segment_ids muss eine Liste von Strings sein.
Verändere die inhaltliche Bedeutung nicht und füge keine neuen Befunde hinzu.
Kein Markdown. Kein Text außerhalb des JSON.
""".strip()

    user_prompt = "Repariere folgende SWOT-Antwort:\n\n" + str(broken_output)

    for attempt in range(3):
        logger.info("[SWOT-Repair] Versuch %s/3", attempt + 1)
        content = ollama_chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=ollama_params["model"],
            temperature=0.0,
            max_tokens=ollama_params["max_tokens"],
        )
        if content:
            return content.strip()
    return ""


def build_summary_index(summary_data):
    exact_index = {}
    name_index = {}

    for summary in summary_data.get("cluster_summaries", []):
        if not isinstance(summary, dict):
            continue

        cluster_name = summary.get("cluster_name", "Unbenannt")
        exact_key = (
            summary.get("hauptkategorie"),
            summary.get("subkategorie"),
            summary.get("facette"),
            cluster_name,
        )
        exact_index[exact_key] = summary
        name_index.setdefault(cluster_name, summary)

    return exact_index, name_index


def find_cluster_summary(cluster, exact_index, name_index):
    cluster_name = cluster.get("cluster_name", "Unbenannt")
    exact_key = (
        cluster.get("hauptkategorie"),
        cluster.get("subkategorie"),
        cluster.get("facette"),
        cluster_name,
    )

    summary = exact_index.get(exact_key)
    if summary is None:
        summary = name_index.get(cluster_name)
    if summary is None:
        return ""
    return summary.get("summary", "")


def group_clusters_by_path(clusters):
    """Gruppiert strikt nach Hauptkategorie + Subkategorie + Facette."""
    groups = OrderedDict()

    for cluster in clusters:
        if not isinstance(cluster, dict):
            continue

        key = (
            cluster.get("hauptkategorie") or "Unbekannt",
            cluster.get("subkategorie") or "Unbekannt",
            cluster.get("facette") or "Unbekannt",
        )
        groups.setdefault(key, []).append(cluster)

    return groups


def make_source_id(haupt, sub, facette):
    return f"{haupt} > {sub} > {facette}"


def _clean_string(value, fallback=""):
    if value is None:
        return fallback
    value = str(value).strip()
    return value or fallback


def normalize_swot(swot, allowed_segment_ids, id_to_text):
    """
    Normalisiert SWOT-Befunde und validiert empirische Evidenz.

    Das LLM darf nur Segment-IDs nennen. Originalzitate werden anschließend
    deterministisch aus id_to_text ergänzt. Ein Befund ohne mindestens eine
    gültige Segment-ID wird verworfen.
    """
    if not isinstance(swot, dict):
        return None

    allowed = set(allowed_segment_ids)
    normalized = {}

    for dimension in DIMENSIONS:
        entries = swot.get(dimension, [])
        if entries is None:
            entries = []
        if not isinstance(entries, list):
            entries = [entries]

        cleaned_entries = []

        for entry in entries:
            if isinstance(entry, str):
                # Alte/abweichende Form ist nicht auditierbar genug.
                logger.warning(
                    "[SWOT] String-Eintrag ohne Segment-IDs in %s verworfen: %s",
                    dimension,
                    entry[:120],
                )
                continue

            if not isinstance(entry, dict):
                continue

            thema = _clean_string(
                entry.get("thema") or entry.get("Thema"),
                "Unbenannter Befund",
            )
            analyse = _clean_string(
                entry.get("analyse")
                or entry.get("Analyse")
                or entry.get("verdichtung")
                or entry.get("Verdichtung")
            )

            raw_ids = (
                entry.get("segment_ids")
                or entry.get("SegmentIDs")
                or entry.get("segments")
                or []
            )
            if isinstance(raw_ids, str):
                raw_ids = [raw_ids]
            if not isinstance(raw_ids, list):
                raw_ids = []

            valid_ids = []
            for sid in raw_ids:
                sid = str(sid).strip()
                if sid in allowed and sid not in valid_ids:
                    valid_ids.append(sid)
                elif sid:
                    logger.warning(
                        "[SWOT] Nicht erlaubte Segment-ID verworfen: %s", sid
                    )

            if not analyse or not valid_ids:
                logger.warning(
                    "[SWOT] Befund '%s' in %s ohne ausreichende validierte Evidenz verworfen.",
                    thema,
                    dimension,
                )
                continue

            zitate = [
                {"segment_id": sid, "text": id_to_text.get(sid, "")}
                for sid in valid_ids
                if id_to_text.get(sid, "")
            ]

            cleaned_entries.append(
                {
                    "thema": thema,
                    "analyse": analyse,
                    "segment_ids": valid_ids,
                    "zitate": zitate,
                }
            )

        normalized[dimension] = cleaned_entries

    return normalized


def build_swot(
    clusters_json_path: str,
    id_to_text_path: str,
    summary_json_path: str,
    ollama_params: dict,
    prompts: dict,
    context: dict,
):
    logger.info("[SWOT] Lade Cluster-JSON…")
    with open(clusters_json_path, "r", encoding="utf-8") as f:
        cluster_data = json.load(f)
    clusters = cluster_data.get("clusters", [])

    logger.info("[SWOT] Lade Segmenttexte…")
    with open(id_to_text_path, "r", encoding="utf-8") as f:
        id_to_text = json.load(f)

    logger.info("[SWOT] Lade Cluster-Summaries…")
    with open(summary_json_path, "r", encoding="utf-8") as f:
        summary_data = json.load(f)

    exact_summary_index, name_summary_index = build_summary_index(summary_data)
    path_groups = group_clusters_by_path(clusters)

    logger.info(
        "[SWOT] Erstelle %s SWOT-Einheiten auf Ebene Haupt > Sub > Facette.",
        len(path_groups),
    )

    swot_results = OrderedDict()

    for (haupt, sub, facette), path_clusters in path_groups.items():
        source_id = make_source_id(haupt, sub, facette)
        logger.info("[SWOT] Erstelle SWOT für: %s", source_id)

        cluster_payload = []
        allowed_segment_ids = []

        for cluster in path_clusters:
            segment_ids = []
            segments = []

            for sid in cluster.get("segments", []):
                sid = str(sid).strip()
                if not sid:
                    continue
                if sid not in segment_ids:
                    segment_ids.append(sid)
                if sid not in allowed_segment_ids:
                    allowed_segment_ids.append(sid)

                segments.append(
                    {
                        "id": sid,
                        "text": id_to_text.get(sid, ""),
                    }
                )

            cluster_payload.append(
                {
                    "cluster_name": cluster.get("cluster_name", "Unbenannt"),
                    "definition": cluster.get("definition", ""),
                    "summary": find_cluster_summary(
                        cluster,
                        exact_summary_index,
                        name_summary_index,
                    ),
                    "segments": segments,
                }
            )

        payload_text = json.dumps(
            {
                "source_id": source_id,
                "hauptkategorie": haupt,
                "subkategorie": sub,
                "facette": facette,
                "clusters": cluster_payload,
            },
            ensure_ascii=False,
            indent=2,
        )

        system_prompt, user_prompt = build_prompt_for_module(
            "swot_analysis",
            prompts=prompts,
            context=context,
            category=source_id,
            clusters=payload_text,
        )

        raw_swot = llm_swot(system_prompt, user_prompt, ollama_params)
        parsed = safe_json_loads(raw_swot)

        if parsed is None:
            logger.warning(
                "[SWOT] JSON-Parsing für '%s' fehlgeschlagen. Starte Repair.",
                source_id,
            )
            repaired = llm_swot_repair(raw_swot, ollama_params)
            parsed = safe_json_loads(repaired)

        if parsed is None:
            logger.error("[SWOT] Keine gültige SWOT für '%s'.", source_id)
            parsed = {dimension: [] for dimension in DIMENSIONS}

        normalized = normalize_swot(
            parsed,
            allowed_segment_ids=allowed_segment_ids,
            id_to_text=id_to_text,
        )
        if normalized is None:
            normalized = {dimension: [] for dimension in DIMENSIONS}

        unique_segment_ids = list(dict.fromkeys(allowed_segment_ids))
        swot_results[source_id] = {
            "hauptkategorie": haupt,
            "subkategorie": sub,
            "facette": facette,
            "cluster_count": len(path_clusters),
            "segment_count": len(unique_segment_ids),
            **normalized,
        }

    json_output = {
        "created_at": datetime.now().isoformat(),
        "source_cluster_created_at": cluster_data.get("created_at"),
        "analysis_level": "hauptkategorie > subkategorie > facette",
        "swot_unit_count": len(swot_results),
        "swot": swot_results,
    }

    md = [
        "# SWOT-Analysen\n",
        f"Erstellt am: {json_output['created_at']}\n\n",
        "Analyseebene: **Hauptkategorie → Subkategorie → Facette**\n\n",
        f"Anzahl SWOT-Einheiten: **{len(swot_results)}**\n\n",
    ]

    for source_id, unit in swot_results.items():
        md.append(f"## {source_id}\n\n")
        md.append(
            f"Cluster: **{unit['cluster_count']}** · "
            f"Segmente: **{unit['segment_count']}**\n\n"
        )

        for dimension in DIMENSIONS:
            md.append(f"### {dimension}\n\n")
            entries = unit.get(dimension, [])

            if not entries:
                md.append("_Keine ausreichend belegten Befunde._\n\n")
                continue

            for entry in entries:
                md.append(f"#### {entry['thema']}\n\n")
                md.append(f"{entry['analyse']}\n\n")
                md.append("**Empirische Belege:**\n\n")

                for quote in entry.get("zitate", []):
                    md.append(f"- `{quote['segment_id']}`: {quote['text']}\n")

                md.append("\n")

    return "".join(md), json_output
