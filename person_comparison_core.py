# person_comparison_core.py

import json
import logging
from datetime import datetime

from utils_prompt import build_prompt_for_module
from clusterer_core import ollama_chat, safe_json_loads

logger = logging.getLogger("person_comparison")


def llm_person_comparison(system_prompt: str, user_prompt: str, ollama_params: dict) -> str:
    for attempt in range(3):
        logger.info(f"[Personenvergleich-Retry] Versuch {attempt + 1}/3")
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
        logger.info("\n===== RAW PERSONENVERGLEICH OUTPUT =====\n%s\n========================================\n", content)
        if content:
            return content.strip()
    return ""


def llm_repair_comparison(broken_output: str, ollama_params: dict) -> str:
    system_prompt = """
Du reparierst ausschließlich JSON. Gib ausschließlich ein gültiges JSON-Objekt zurück.
Erlaubte oberste Schlüssel:
- gemeinsame_muster
- zentrale_unterschiede
- typen
- nicht_zugeordnete_personen
- gesamtvergleich

Gemeinsame Muster: Objekte mit thema, verdichtung, personen.
Zentrale Unterschiede: Objekte mit thema, beschreibung, personenpositionen.
personenpositionen ist eine Liste aus Objekten mit person und position.
Typen: Objekte mit typ_name, beschreibung, personen, merkmale.
Nicht zugeordnete Personen: Objekte mit person und begruendung.
Keine neuen Inhalte. Kein Markdown. Keine Erklärung.
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


def _allowed_people(values, allowed):
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    out = []
    for person in values:
        person = str(person).strip()
        if person in allowed and person not in out:
            out.append(person)
    return out


def normalize_comparison(parsed: dict, source_people: list) -> dict:
    if not isinstance(parsed, dict):
        return None
    allowed = set(source_people)

    common = []
    raw = parsed.get("gemeinsame_muster", [])
    if not isinstance(raw, list):
        raw = [raw] if raw else []
    for e in raw:
        if not isinstance(e, dict):
            continue
        common.append({
            "thema": str(e.get("thema", "")).strip(),
            "verdichtung": str(e.get("verdichtung", "")).strip(),
            "personen": _allowed_people(e.get("personen", []), allowed),
        })

    diffs = []
    raw = parsed.get("zentrale_unterschiede", [])
    if not isinstance(raw, list):
        raw = [raw] if raw else []
    for e in raw:
        if not isinstance(e, dict):
            continue
        positions = []
        for p in e.get("personenpositionen", []) if isinstance(e.get("personenpositionen", []), list) else []:
            if isinstance(p, dict) and str(p.get("person", "")).strip() in allowed:
                positions.append({
                    "person": str(p.get("person")).strip(),
                    "position": str(p.get("position", "")).strip(),
                })
        diffs.append({
            "thema": str(e.get("thema", "")).strip(),
            "beschreibung": str(e.get("beschreibung", "")).strip(),
            "personenpositionen": positions,
        })

    typen = []
    raw = parsed.get("typen", [])
    if not isinstance(raw, list):
        raw = [raw] if raw else []
    for e in raw:
        if not isinstance(e, dict):
            continue
        merkmale = e.get("merkmale", [])
        if isinstance(merkmale, str):
            merkmale = [merkmale]
        if not isinstance(merkmale, list):
            merkmale = []
        typen.append({
            "typ_name": str(e.get("typ_name", "")).strip(),
            "beschreibung": str(e.get("beschreibung", "")).strip(),
            "personen": _allowed_people(e.get("personen", []), allowed),
            "merkmale": [str(m).strip() for m in merkmale if str(m).strip()],
        })

    unassigned = []
    raw = parsed.get("nicht_zugeordnete_personen", [])
    if not isinstance(raw, list):
        raw = [raw] if raw else []
    for e in raw:
        if not isinstance(e, dict):
            continue
        person = str(e.get("person", "")).strip()
        if person in allowed:
            unassigned.append({
                "person": person,
                "begruendung": str(e.get("begruendung", "")).strip(),
            })

    return {
        "gemeinsame_muster": common,
        "zentrale_unterschiede": diffs,
        "typen": typen,
        "nicht_zugeordnete_personen": unassigned,
        "gesamtvergleich": str(parsed.get("gesamtvergleich", "")).strip(),
    }


def build_person_comparison(
    person_analysis_json_path: str,
    ollama_params: dict,
    prompts: dict,
    context: dict,
):
    with open(person_analysis_json_path, "r", encoding="utf-8") as f:
        person_data = json.load(f)

    persons = person_data.get("persons", {})
    if not isinstance(persons, dict) or not persons:
        raise ValueError("Keine Personenanalysen gefunden.")

    source_people = sorted(persons.keys())
    payload = {
        "personen": [persons[name] for name in source_people]
    }

    system_prompt, user_prompt = build_prompt_for_module(
        "person_comparison",
        prompts=prompts,
        context=context,
        persons=json.dumps(payload, ensure_ascii=False, indent=2),
    )

    raw = llm_person_comparison(system_prompt, user_prompt, ollama_params)
    parsed = safe_json_loads(raw)
    if parsed is None:
        logger.warning("[Personenvergleich] Ungültiges JSON; starte Repair.")
        parsed = safe_json_loads(llm_repair_comparison(raw, ollama_params))
    if parsed is None:
        raise ValueError("Personenvergleich konnte nicht als JSON gelesen werden.")

    comparison = normalize_comparison(parsed, source_people)
    if comparison is None:
        raise ValueError("Personenvergleich besitzt kein verwertbares Format.")

    json_output = {
        "created_at": datetime.now().isoformat(),
        "source_person_analysis_created_at": person_data.get("created_at"),
        "source_persons": source_people,
        **comparison,
    }

    md = ["# Personenvergleich und Typenbildung\n", f"Erstellt am: {json_output['created_at']}\n\n"]
    if comparison["gesamtvergleich"]:
        md.append(f"## Gesamtvergleich\n\n{comparison['gesamtvergleich']}\n\n")

    md.append("## Gemeinsame Muster\n\n")
    for e in comparison["gemeinsame_muster"]:
        md.append(f"### {e['thema']}\n\n{e['verdichtung']}\n\n**Personen:** {', '.join(e['personen'])}\n\n")
    if not comparison["gemeinsame_muster"]:
        md.append("_Keine belastbaren gemeinsamen Muster._\n\n")

    md.append("## Zentrale Unterschiede\n\n")
    for e in comparison["zentrale_unterschiede"]:
        md.append(f"### {e['thema']}\n\n{e['beschreibung']}\n\n")
        for p in e["personenpositionen"]:
            md.append(f"- **{p['person']}**: {p['position']}\n")
        md.append("\n")
    if not comparison["zentrale_unterschiede"]:
        md.append("_Keine belastbaren Unterschiede._\n\n")

    md.append("## Datenbasierte Typen\n\n")
    for e in comparison["typen"]:
        md.append(f"### {e['typ_name']}\n\n{e['beschreibung']}\n\n")
        md.append(f"**Personen:** {', '.join(e['personen'])}\n\n")
        if e["merkmale"]:
            md.append("**Kennzeichnende Merkmale:**\n")
            for m in e["merkmale"]:
                md.append(f"- {m}\n")
            md.append("\n")
    if not comparison["typen"]:
        md.append("_Keine belastbare Typenbildung möglich._\n\n")

    md.append("## Nicht zugeordnete Personen\n\n")
    for e in comparison["nicht_zugeordnete_personen"]:
        md.append(f"- **{e['person']}**: {e['begruendung']}\n")
    if not comparison["nicht_zugeordnete_personen"]:
        md.append("_Keine._\n")

    return "\n".join(md), json_output
