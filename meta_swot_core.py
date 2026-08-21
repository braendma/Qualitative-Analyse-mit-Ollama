# meta_swot_core.py

import json
import logging
from datetime import datetime

from utils_prompt import build_prompt_for_module
from clusterer_core import ollama_chat

logger = logging.getLogger("meta_swot")

DIMENSIONS = ("Stärken", "Schwächen", "Chancen", "Risiken")
PREFIXES = {
    "Stärken": "STR",
    "Schwächen": "SCH",
    "Chancen": "CHA",
    "Risiken": "RIS",
}


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


def llm_meta_swot(system_prompt: str, user_prompt: str, ollama_params: dict) -> str:
    for attempt in range(3):
        logger.info("[Meta-SWOT-Retry] Versuch %s/3", attempt + 1)
        logger.debug("\n===== META SWOT SYSTEM PROMPT =====\n%s\n", system_prompt)
        logger.debug("\n===== META SWOT USER PROMPT =====\n%s\n", user_prompt)

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
            "\n===== RAW META SWOT OUTPUT =====\n%s\n"
            "================================\n",
            content,
        )

        if content:
            return content.strip()
        logger.warning("[Meta-SWOT] Leere LLM-Antwort.")

    logger.error("[Meta-SWOT] Nach 3 Versuchen keine gültige Antwort.")
    return ""


def llm_meta_swot_repair(broken_output: str, ollama_params: dict) -> str:
    system_prompt = """
Du reparierst ausschließlich JSON.

Gib ausschließlich ein gültiges JSON-Objekt mit genau dem Schlüssel "cluster" zurück.
"cluster" ist eine Liste. Jeder Eintrag muss exakt diese drei Schlüssel enthalten:
- thema
- verdichtung
- finding_ids

finding_ids ist eine Liste von Strings.
Füge keine neuen Befunde oder IDs hinzu.
Kein Markdown. Kein Text außerhalb des JSON.
""".strip()

    user_prompt = "Repariere folgende Meta-SWOT-Clusterantwort:\n\n" + str(broken_output)

    for attempt in range(3):
        logger.info("[Meta-SWOT-Repair] Versuch %s/3", attempt + 1)
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


def flatten_findings(swot_data):
    """Vergibt deterministische finding_ids für alle SWOT-Befunde."""
    raw_swots = swot_data.get("swot", {})
    if not isinstance(raw_swots, dict):
        raise ValueError("Das Feld 'swot' im SWOT-JSON muss ein Objekt sein.")

    by_dimension = {dimension: [] for dimension in DIMENSIONS}
    counters = {dimension: 0 for dimension in DIMENSIONS}

    for source_id, unit in raw_swots.items():
        if not isinstance(unit, dict):
            continue

        metadata = {
            "source_id": str(source_id),
            "hauptkategorie": unit.get("hauptkategorie"),
            "subkategorie": unit.get("subkategorie"),
            "facette": unit.get("facette"),
        }

        for dimension in DIMENSIONS:
            entries = unit.get(dimension, [])
            if not isinstance(entries, list):
                continue

            for entry in entries:
                if not isinstance(entry, dict):
                    continue

                counters[dimension] += 1
                finding_id = f"{PREFIXES[dimension]}{counters[dimension]:04d}"

                by_dimension[dimension].append(
                    {
                        "finding_id": finding_id,
                        **metadata,
                        "thema": str(entry.get("thema", "")).strip(),
                        "analyse": str(entry.get("analyse", "")).strip(),
                        "segment_ids": [
                            str(x)
                            for x in entry.get("segment_ids", [])
                            if str(x).strip()
                        ],
                    }
                )

    return by_dimension


def normalize_cluster_response(parsed, findings_by_id):
    """Validiert ausschließlich bekannte finding_ids und verhindert Doppelnutzung."""
    if not isinstance(parsed, dict):
        return []

    raw_clusters = parsed.get("cluster", [])
    if raw_clusters is None:
        raw_clusters = []
    if not isinstance(raw_clusters, list):
        raw_clusters = [raw_clusters]

    used_ids = set()
    normalized = []

    for raw_cluster in raw_clusters:
        if not isinstance(raw_cluster, dict):
            continue

        raw_ids = raw_cluster.get("finding_ids", [])
        if isinstance(raw_ids, str):
            raw_ids = [raw_ids]
        if not isinstance(raw_ids, list):
            raw_ids = []

        valid_ids = []
        for finding_id in raw_ids:
            finding_id = str(finding_id).strip()
            if (
                finding_id in findings_by_id
                and finding_id not in used_ids
                and finding_id not in valid_ids
            ):
                valid_ids.append(finding_id)

        if not valid_ids:
            continue

        used_ids.update(valid_ids)

        thema = str(raw_cluster.get("thema", "")).strip() or "Unbenanntes Muster"
        verdichtung = str(raw_cluster.get("verdichtung", "")).strip()

        if not verdichtung:
            verdichtung = " / ".join(
                findings_by_id[fid].get("analyse", "") for fid in valid_ids
            )

        normalized.append(
            {
                "thema": thema,
                "verdichtung": verdichtung,
                "finding_ids": valid_ids,
            }
        )

    return normalized


def _source_ids_for_finding_ids(finding_ids, findings_by_id):
    return list(
        dict.fromkeys(
            findings_by_id[fid]["source_id"]
            for fid in finding_ids
            if fid in findings_by_id
        )
    )


def build_dimension_meta(
    dimension,
    findings,
    ollama_params,
    prompts,
    context,
):
    if not findings:
        return {
            "uebergreifende_muster": [],
            "einzelbefunde": [],
            "statistik": {
                "befunde": 0,
                "quellbereiche": 0,
                "in_mehrquellenmustern": 0,
            },
        }

    findings_by_id = {f["finding_id"]: f for f in findings}
    source_ids = list(dict.fromkeys(f["source_id"] for f in findings))

    system_prompt, user_prompt = build_prompt_for_module(
        "meta_swot",
        prompts=prompts,
        context=context,
        category=dimension,
        clusters=json.dumps(findings, ensure_ascii=False, indent=2),
    )

    raw = llm_meta_swot(system_prompt, user_prompt, ollama_params)
    parsed = safe_json_loads(raw)

    if parsed is None:
        logger.warning(
            "[Meta-SWOT] JSON-Parsing für %s fehlgeschlagen. Starte Repair.",
            dimension,
        )
        repaired = llm_meta_swot_repair(raw, ollama_params)
        parsed = safe_json_loads(repaired)

    if parsed is None:
        logger.error(
            "[Meta-SWOT] Keine gültige Clusterantwort für %s. Alle Befunde bleiben Einzelbefunde.",
            dimension,
        )
        parsed = {"cluster": []}

    clusters = normalize_cluster_response(parsed, findings_by_id)

    cross_patterns = []
    assigned_to_cross = set()
    assigned_any = set()
    single_source_clusters = []

    for cluster in clusters:
        finding_ids = cluster["finding_ids"]
        sources = _source_ids_for_finding_ids(finding_ids, findings_by_id)
        assigned_any.update(finding_ids)

        enriched = {
            "thema": cluster["thema"],
            "verdichtung": cluster["verdichtung"],
            "finding_ids": finding_ids,
            "quellen": sources,
            "anzahl_quellen": len(sources),
        }

        if len(sources) >= 2 and len(finding_ids) >= 2:
            cross_patterns.append(enriched)
            assigned_to_cross.update(finding_ids)
        else:
            single_source_clusters.append(enriched)

    # Alles, was nicht in einem echten Mehrquellenmuster steckt, bleibt sichtbar.
    single_findings = []
    already_added_single_ids = set()

    for cluster in single_source_clusters:
        for finding_id in cluster["finding_ids"]:
            if finding_id in already_added_single_ids:
                continue
            finding = findings_by_id[finding_id]
            single_findings.append(
                {
                    "finding_id": finding_id,
                    "thema": finding["thema"],
                    "verdichtung": finding["analyse"],
                    "quelle": finding["source_id"],
                    "segment_ids": finding.get("segment_ids", []),
                }
            )
            already_added_single_ids.add(finding_id)

    for finding in findings:
        finding_id = finding["finding_id"]
        if finding_id in assigned_to_cross or finding_id in already_added_single_ids:
            continue
        single_findings.append(
            {
                "finding_id": finding_id,
                "thema": finding["thema"],
                "verdichtung": finding["analyse"],
                "quelle": finding["source_id"],
                "segment_ids": finding.get("segment_ids", []),
            }
        )
        already_added_single_ids.add(finding_id)

    return {
        "uebergreifende_muster": cross_patterns,
        "einzelbefunde": single_findings,
        "statistik": {
            "befunde": len(findings),
            "quellbereiche": len(source_ids),
            "in_mehrquellenmustern": len(assigned_to_cross),
        },
    }


def build_meta_swot(
    swot_json_path: str,
    ollama_params: dict,
    prompts: dict,
    context: dict,
):
    logger.info("[Meta-SWOT] Lade SWOT-JSON: %s", swot_json_path)
    with open(swot_json_path, "r", encoding="utf-8") as f:
        swot_data = json.load(f)

    findings_by_dimension = flatten_findings(swot_data)

    source_units = list(swot_data.get("swot", {}).keys())
    logger.info(
        "[Meta-SWOT] %s SWOT-Quellbereiche geladen.",
        len(source_units),
    )

    meta_swot = {}
    total_findings = 0
    total_cross = 0

    for dimension in DIMENSIONS:
        findings = findings_by_dimension[dimension]
        logger.info(
            "[Meta-SWOT] Verdichte %s Befunde in Dimension %s.",
            len(findings),
            dimension,
        )
        result = build_dimension_meta(
            dimension,
            findings,
            ollama_params,
            prompts,
            context,
        )
        meta_swot[dimension] = result
        total_findings += result["statistik"]["befunde"]
        total_cross += result["statistik"]["in_mehrquellenmustern"]

    finding_registry = {
        finding["finding_id"]: finding
        for dimension in DIMENSIONS
        for finding in findings_by_dimension.get(dimension, [])
    }

    json_output = {
        "created_at": datetime.now().isoformat(),
        "source_swot_created_at": swot_data.get("created_at"),
        "source_units": source_units,
        "source_unit_count": len(source_units),
        "finding_count": total_findings,
        "findings_in_cross_source_patterns": total_cross,
        "finding_registry": finding_registry,
        "meta_swot": meta_swot,
    }

    md = [
        "# Meta-SWOT\n",
        f"Erstellt am: {json_output['created_at']}\n\n",
        f"SWOT-Quellbereiche: **{len(source_units)}** · "
        f"SWOT-Befunde: **{total_findings}**\n\n",
        "Ein **übergreifendes Muster** muss durch mindestens zwei unterschiedliche "
        "SWOT-Quellbereiche gestützt werden. Alle übrigen Befunde bleiben als "
        "Einzelbefunde sichtbar.\n\n",
    ]

    for dimension in DIMENSIONS:
        section = meta_swot[dimension]
        stats = section["statistik"]

        md.append(f"## {dimension}\n\n")
        md.append(
            f"Befunde: **{stats['befunde']}** · "
            f"Quellbereiche: **{stats['quellbereiche']}** · "
            f"Befunde in Mehrquellenmustern: **{stats['in_mehrquellenmustern']}**\n\n"
        )

        md.append("### Übergreifende Muster\n\n")
        patterns = section["uebergreifende_muster"]
        if not patterns:
            md.append("_Keine echten Mehrquellenmuster identifiziert._\n\n")
        else:
            for pattern in patterns:
                md.append(f"#### {pattern['thema']}\n\n")
                md.append(f"{pattern['verdichtung']}\n\n")
                md.append(
                    f"**Unterstützende Quellbereiche ({pattern['anzahl_quellen']}):**\n\n"
                )
                for source in pattern["quellen"]:
                    md.append(f"- {source}\n")
                md.append("\n")

        md.append("### Einzelbefunde / quellenspezifische Befunde\n\n")
        singles = section["einzelbefunde"]
        if not singles:
            md.append("_Keine verbleibenden Einzelbefunde._\n\n")
        else:
            for single in singles:
                md.append(f"#### {single['thema']}\n\n")
                md.append(f"{single['verdichtung']}\n\n")
                md.append(f"**Quelle:** {single['quelle']}\n\n")

    return "".join(md), json_output
