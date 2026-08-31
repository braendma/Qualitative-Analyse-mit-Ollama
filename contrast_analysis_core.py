# contrast_analysis_core.py

import json
import logging
from datetime import datetime

from utils_prompt import build_prompt_for_module
from clusterer_core import ollama_chat, safe_json_loads

logger = logging.getLogger("contrast_analysis")


def llm_contrast_analysis(system_prompt: str, user_prompt: str, ollama_params: dict) -> str:
    for attempt in range(3):
        logger.info(f"[Kontrastanalyse-Retry] Versuch {attempt + 1}/3")
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
        logger.info("\n===== RAW KONTRASTANALYSE OUTPUT =====\n%s\n======================================\n", content)
        if content:
            return content.strip()
    return ""


def llm_repair_contrast(broken_output: str, ollama_params: dict) -> str:
    system_prompt = """
Du reparierst ausschließlich JSON.
Erlaubte oberste Schlüssel:
- dominante_muster
- negativfaelle
- spannungen_zwischen_typen
- relativierungen
- gesamteinordnung

Dominante Muster: muster, beschreibung, getragen_von.
Negativfälle: person, bezugs_muster, abweichung, begruendung.
Spannungen zwischen Typen: typen, beschreibung.
Relativierungen: aussage, bedeutung.
Kein Markdown. Keine neuen Inhalte.
""".strip()
    for attempt in range(3):
        content = ollama_chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Repariere:\n\n{broken_output}"},
            ],
            model=ollama_params["model"],
            temperature=0.0,
            max_tokens=ollama_params["max_tokens"],
            think=ollama_params.get("think"),
            log_thinking=ollama_params.get("log_thinking", False),
        )
        if content:
            return content.strip()
    return ""


def _clean_people(values, allowed):
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    return [p for p in dict.fromkeys(str(v).strip() for v in values) if p in allowed]


def normalize_contrast(parsed: dict, source_people: list, type_names: list) -> dict:
    if not isinstance(parsed, dict):
        return None
    allowed_people = set(source_people)
    allowed_types = set(type_names)

    dominant = []
    raw = parsed.get("dominante_muster", [])
    if not isinstance(raw, list):
        raw = [raw] if raw else []
    for e in raw:
        if isinstance(e, dict):
            dominant.append({
                "muster": str(e.get("muster", "")).strip(),
                "beschreibung": str(e.get("beschreibung", "")).strip(),
                "getragen_von": _clean_people(e.get("getragen_von", []), allowed_people),
            })

    negatives = []
    raw = parsed.get("negativfaelle", [])
    if not isinstance(raw, list):
        raw = [raw] if raw else []
    for e in raw:
        if not isinstance(e, dict):
            continue
        person = str(e.get("person", "")).strip()
        if person in allowed_people:
            negatives.append({
                "person": person,
                "bezugs_muster": str(e.get("bezugs_muster", "")).strip(),
                "abweichung": str(e.get("abweichung", "")).strip(),
                "begruendung": str(e.get("begruendung", "")).strip(),
            })

    tensions = []
    raw = parsed.get("spannungen_zwischen_typen", [])
    if not isinstance(raw, list):
        raw = [raw] if raw else []
    for e in raw:
        if not isinstance(e, dict):
            continue
        typen = e.get("typen", [])
        if isinstance(typen, str):
            typen = [typen]
        typen = [str(t).strip() for t in typen if str(t).strip() in allowed_types] if isinstance(typen, list) else []
        tensions.append({
            "typen": list(dict.fromkeys(typen)),
            "beschreibung": str(e.get("beschreibung", "")).strip(),
        })

    relativierungen = []
    raw = parsed.get("relativierungen", [])
    if not isinstance(raw, list):
        raw = [raw] if raw else []
    for e in raw:
        if isinstance(e, dict):
            relativierungen.append({
                "aussage": str(e.get("aussage", "")).strip(),
                "bedeutung": str(e.get("bedeutung", "")).strip(),
            })

    return {
        "dominante_muster": dominant,
        "negativfaelle": negatives,
        "spannungen_zwischen_typen": tensions,
        "relativierungen": relativierungen,
        "gesamteinordnung": str(parsed.get("gesamteinordnung", "")).strip(),
    }


def build_contrast_analysis(
    person_analysis_json_path: str,
    person_comparison_json_path: str,
    ollama_params: dict,
    prompts: dict,
    context: dict,
):
    with open(person_analysis_json_path, "r", encoding="utf-8") as f:
        person_data = json.load(f)
    with open(person_comparison_json_path, "r", encoding="utf-8") as f:
        comparison_data = json.load(f)

    persons = person_data.get("persons", {})
    source_people = sorted(persons.keys()) if isinstance(persons, dict) else []
    type_names = [
        str(t.get("typ_name", "")).strip()
        for t in comparison_data.get("typen", [])
        if isinstance(t, dict) and str(t.get("typ_name", "")).strip()
    ]

    payload = {
        "personenanalyse": person_data,
        "personenvergleich_und_typenbildung": comparison_data,
    }

    system_prompt, user_prompt = build_prompt_for_module(
        "contrast_analysis",
        prompts=prompts,
        context=context,
        data=json.dumps(payload, ensure_ascii=False, indent=2),
    )

    raw = llm_contrast_analysis(system_prompt, user_prompt, ollama_params)
    parsed = safe_json_loads(raw)
    if parsed is None:
        logger.warning("[Kontrastanalyse] Ungültiges JSON; starte Repair.")
        parsed = safe_json_loads(llm_repair_contrast(raw, ollama_params))
    if parsed is None:
        raise ValueError("Kontrastanalyse konnte nicht als JSON gelesen werden.")

    result = normalize_contrast(parsed, source_people, type_names)
    if result is None:
        raise ValueError("Kontrastanalyse besitzt kein verwertbares Format.")

    json_output = {
        "created_at": datetime.now().isoformat(),
        "source_person_analysis_created_at": person_data.get("created_at"),
        "source_person_comparison_created_at": comparison_data.get("created_at"),
        **result,
    }

    md = ["# Kontrast- und Negativfallanalyse\n", f"Erstellt am: {json_output['created_at']}\n\n"]
    if result["gesamteinordnung"]:
        md.append(f"## Gesamteinordnung\n\n{result['gesamteinordnung']}\n\n")

    md.append("## Dominante Muster\n\n")
    for e in result["dominante_muster"]:
        md.append(f"### {e['muster']}\n\n{e['beschreibung']}\n\n**Getragen von:** {', '.join(e['getragen_von'])}\n\n")
    if not result["dominante_muster"]:
        md.append("_Keine dominanten Muster identifiziert._\n\n")

    md.append("## Negativ- und Kontrastfälle\n\n")
    for e in result["negativfaelle"]:
        md.append(f"### {e['person']}\n\n**Bezugsmuster:** {e['bezugs_muster']}\n\n**Abweichung:** {e['abweichung']}\n\n**Begründung:** {e['begruendung']}\n\n")
    if not result["negativfaelle"]:
        md.append("_Keine belastbaren Negativfälle identifiziert._\n\n")

    md.append("## Spannungen zwischen Typen\n\n")
    for e in result["spannungen_zwischen_typen"]:
        md.append(f"- **{' ↔ '.join(e['typen'])}**: {e['beschreibung']}\n")
    if not result["spannungen_zwischen_typen"]:
        md.append("_Keine belastbaren Spannungen zwischen Typen._\n")
    md.append("\n")

    md.append("## Relativierungen der Gesamtergebnisse\n\n")
    for e in result["relativierungen"]:
        md.append(f"- **{e['aussage']}** — {e['bedeutung']}\n")
    if not result["relativierungen"]:
        md.append("_Keine zusätzlichen Relativierungen._\n")

    return "\n".join(md), json_output
