# overall_synthesis_core.py

import json
import logging
from datetime import datetime

from clusterer_core import ollama_chat, safe_json_loads
from utils_prompt import build_prompt_for_module

logger = logging.getLogger("overall_synthesis")


def llm_overall_synthesis(system_prompt: str, user_prompt: str, ollama_params: dict) -> str:
    for attempt in range(3):
        logger.info("[Gesamtsynthese-Retry] Versuch %s/3", attempt + 1)
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
            "\n===== RAW GESAMTSYNTHESE OUTPUT =====\n%s\n=====================================\n",
            content,
        )
        if content:
            return content.strip()
    return ""


def llm_repair_overall_synthesis(broken_output: str, ollama_params: dict) -> str:
    system_prompt = """
Du reparierst ausschließlich JSON.
Gib ausschließlich ein gültiges JSON-Objekt zurück.

Erlaubte oberste Schlüssel:
- kernergebnisse
- uebergreifende_muster
- spannungen_und_relativierungen
- methodische_einordnung
- gesamtsynthese

kernergebnisse und uebergreifende_muster sind Listen aus Objekten mit:
- thema
- verdichtung
- quellen

spannungen_und_relativierungen ist eine Liste aus Objekten mit:
- aussage
- einordnung
- quellen

methodische_einordnung ist eine Liste von Strings.
gesamtsynthese ist ein String.
quellen ist immer eine Liste von Strings und darf ausschließlich bereits gelieferte Quellenbezeichnungen verwenden.

Keine neuen empirischen Inhalte. Kein Markdown. Keine Erklärung.
""".strip()

    for attempt in range(3):
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


def _clean_sources(value, allowed_sources: set):
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    cleaned = []
    for source in value:
        source = str(source).strip()
        if source in allowed_sources and source not in cleaned:
            cleaned.append(source)
    return cleaned


def _normalize_theme_entries(parsed: dict, key: str, allowed_sources: set) -> list:
    raw = parsed.get(key, [])
    if not isinstance(raw, list):
        raw = [raw] if raw else []
    result = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        thema = str(entry.get("thema", "")).strip()
        verdichtung = str(entry.get("verdichtung", "")).strip()
        if not thema and not verdichtung:
            continue
        result.append({
            "thema": thema or "Unbenanntes Thema",
            "verdichtung": verdichtung,
            "quellen": _clean_sources(entry.get("quellen", []), allowed_sources),
        })
    return result


def normalize_overall_synthesis(parsed: dict, source_labels: list) -> dict:
    if not isinstance(parsed, dict):
        return None
    allowed_sources = set(source_labels)

    tensions = []
    raw = parsed.get("spannungen_und_relativierungen", [])
    if not isinstance(raw, list):
        raw = [raw] if raw else []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        tensions.append({
            "aussage": str(entry.get("aussage", "")).strip(),
            "einordnung": str(entry.get("einordnung", "")).strip(),
            "quellen": _clean_sources(entry.get("quellen", []), allowed_sources),
        })

    methodological = parsed.get("methodische_einordnung", [])
    if not isinstance(methodological, list):
        methodological = [methodological] if methodological else []
    methodological = [str(x).strip() for x in methodological if str(x).strip()]

    return {
        "kernergebnisse": _normalize_theme_entries(parsed, "kernergebnisse", allowed_sources),
        "uebergreifende_muster": _normalize_theme_entries(parsed, "uebergreifende_muster", allowed_sources),
        "spannungen_und_relativierungen": tensions,
        "methodische_einordnung": methodological,
        "gesamtsynthese": str(parsed.get("gesamtsynthese", "")).strip(),
    }


def build_overall_synthesis(
    source_json_paths: dict,
    ollama_params: dict,
    prompts: dict,
    context: dict,
):
    if not isinstance(source_json_paths, dict) or not source_json_paths:
        raise ValueError("Mindestens eine analytische JSON-Quelle ist erforderlich.")

    sources = {}
    source_created_at = {}
    for label, path in source_json_paths.items():
        label = str(label).strip()
        if not label:
            continue
        logger.info("[Gesamtsynthese] Lade %s: %s", label, path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        sources[label] = data
        source_created_at[label] = data.get("created_at") if isinstance(data, dict) else None

    if not sources:
        raise ValueError("Keine verwertbaren analytischen Quellen geladen.")

    source_labels = list(sources.keys())
    payload = {
        "verfuegbare_analytische_quellen": source_labels,
        "analysen": sources,
    }

    system_prompt, user_prompt = build_prompt_for_module(
        "overall_synthesis",
        prompts=prompts,
        context=context,
        data=json.dumps(payload, ensure_ascii=False, indent=2),
    )

    raw = llm_overall_synthesis(system_prompt, user_prompt, ollama_params)
    parsed = safe_json_loads(raw)
    if parsed is None:
        logger.warning("[Gesamtsynthese] Ungültiges JSON; starte Repair.")
        parsed = safe_json_loads(llm_repair_overall_synthesis(raw, ollama_params))
    if parsed is None:
        raise ValueError("Gesamtsynthese konnte nicht als JSON gelesen werden.")

    normalized = normalize_overall_synthesis(parsed, source_labels)
    if normalized is None:
        raise ValueError("Gesamtsynthese besitzt kein verwertbares Format.")

    json_output = {
        "created_at": datetime.now().isoformat(),
        "source_labels": source_labels,
        "source_created_at": source_created_at,
        **normalized,
    }

    md = [
        "# Gesamtsynthese\n",
        f"Erstellt am: {json_output['created_at']}\n\n",
        f"Einbezogene analytische Ebenen: **{', '.join(source_labels)}**\n\n",
    ]

    if normalized["gesamtsynthese"]:
        md.append(f"## Gesamtverdichtung\n\n{normalized['gesamtsynthese']}\n\n")

    for title, key in [
        ("Kernergebnisse", "kernergebnisse"),
        ("Übergreifende Muster", "uebergreifende_muster"),
    ]:
        md.append(f"## {title}\n\n")
        entries = normalized[key]
        if not entries:
            md.append("_Keine belastbaren Einträge identifiziert._\n\n")
        for entry in entries:
            md.append(f"### {entry['thema']}\n\n{entry['verdichtung']}\n\n")
            if entry["quellen"]:
                md.append(f"**Analytische Quellen:** {', '.join(entry['quellen'])}\n\n")

    md.append("## Spannungen und Relativierungen\n\n")
    if not normalized["spannungen_und_relativierungen"]:
        md.append("_Keine zusätzlichen Spannungen oder Relativierungen._\n\n")
    for entry in normalized["spannungen_und_relativierungen"]:
        md.append(f"### {entry['aussage'] or 'Relativierung'}\n\n{entry['einordnung']}\n\n")
        if entry["quellen"]:
            md.append(f"**Analytische Quellen:** {', '.join(entry['quellen'])}\n\n")

    md.append("## Methodische Einordnung\n\n")
    if normalized["methodische_einordnung"]:
        for item in normalized["methodische_einordnung"]:
            md.append(f"- {item}\n")
    else:
        md.append("_Keine zusätzliche methodische Einordnung._\n")

    return "".join(md), json_output
