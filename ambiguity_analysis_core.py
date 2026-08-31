# ambiguity_analysis_core.py

import json
import logging
from datetime import datetime

from clusterer_core import ollama_chat, safe_json_loads
from utils_prompt import build_prompt_for_module

logger = logging.getLogger("ambiguity_analysis")


def _llm(system_prompt, user_prompt, ollama_params):
    for attempt in range(3):
        logger.info("[Ambivalenzanalyse-Retry] Versuch %s/3", attempt + 1)
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
        logger.info("\n===== RAW AMBIGUITY OUTPUT =====\n%s\n================================\n", content)
        if content:
            return content.strip()
    return ""


def _repair(broken_output, ollama_params):
    system = """
Du reparierst ausschließlich JSON für eine intrapersonelle Ambivalenzanalyse.
Gib genau ein Objekt zurück mit:
- ambivalenzen: Liste
- gesamteinordnung: String
Jeder Ambivalenzeintrag besitzt exakt:
thema, beschreibung, position_a, position_b, segment_ids_a, segment_ids_b.
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


def normalize_person_ambiguities(parsed: dict, allowed_ids: set, id_to_text: dict) -> dict:
    if not isinstance(parsed, dict):
        return None

    raw = parsed.get("ambivalenzen", [])
    if not isinstance(raw, list):
        raw = [raw] if raw else []

    out = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        ids_a = [str(x).strip() for x in entry.get("segment_ids_a", []) if str(x).strip() in allowed_ids]
        ids_b = [str(x).strip() for x in entry.get("segment_ids_b", []) if str(x).strip() in allowed_ids]
        ids_a = list(dict.fromkeys(ids_a))
        ids_b = list(dict.fromkeys(ids_b))

        # Eine Ambivalenz braucht empirische Belege für beide Pole.
        if not ids_a or not ids_b:
            continue
        if set(ids_a) == set(ids_b):
            continue

        out.append(
            {
                "ambiguity_id": f"AMB{len(out) + 1:04d}",
                "thema": str(entry.get("thema", "")).strip() or "Unbenanntes Spannungsfeld",
                "beschreibung": str(entry.get("beschreibung", "")).strip(),
                "position_a": str(entry.get("position_a", "")).strip(),
                "position_b": str(entry.get("position_b", "")).strip(),
                "segment_ids_a": ids_a,
                "segment_ids_b": ids_b,
                "belege_a": [{"segment_id": sid, "text": id_to_text.get(sid, "")} for sid in ids_a],
                "belege_b": [{"segment_id": sid, "text": id_to_text.get(sid, "")} for sid in ids_b],
            }
        )

    return {
        "ambivalenzen": out,
        "gesamteinordnung": str(parsed.get("gesamteinordnung", "")).strip(),
    }


def build_ambiguity_analysis(
    person_analysis_json_path: str,
    id_to_text_path: str,
    ollama_params: dict,
    prompts: dict,
    context: dict,
):
    with open(person_analysis_json_path, "r", encoding="utf-8") as f:
        person_data = json.load(f)
    with open(id_to_text_path, "r", encoding="utf-8") as f:
        id_to_text = json.load(f)

    persons = person_data.get("persons", {})
    if not isinstance(persons, dict):
        raise ValueError("Das Feld 'persons' der Personenanalyse muss ein Objekt sein.")

    results = {}
    global_counter = 0

    for person in sorted(persons):
        analysis = persons[person]
        allowed_ids = {
            str(sid).strip()
            for sid in analysis.get("segment_ids", [])
            if str(sid).strip() in id_to_text
        }
        segments = [
            {"id": sid, "text": id_to_text[sid]}
            for sid in sorted(allowed_ids)
        ]

        payload = {
            "person": person,
            "personenanalyse": analysis,
            "originalsegmente": segments,
        }

        system_prompt, user_prompt = build_prompt_for_module(
            "ambiguity_analysis",
            prompts=prompts,
            context=context,
            data=json.dumps(payload, ensure_ascii=False, indent=2),
        )
        raw = _llm(system_prompt, user_prompt, ollama_params)
        parsed = safe_json_loads(raw)
        if parsed is None:
            logger.warning("[Ambivalenzanalyse] Ungültiges JSON für %s; starte Repair.", person)
            parsed = safe_json_loads(_repair(raw, ollama_params))
        if parsed is None:
            logger.error("[Ambivalenzanalyse] Keine verwertbare Antwort für %s.", person)
            continue

        normalized = normalize_person_ambiguities(parsed, allowed_ids, id_to_text)
        if normalized is None:
            continue

        # IDs workflowweit innerhalb dieses Outputs eindeutig machen.
        for item in normalized["ambivalenzen"]:
            global_counter += 1
            item["ambiguity_id"] = f"AMB{global_counter:04d}"

        results[person] = {
            "person": person,
            "segment_count": len(allowed_ids),
            **normalized,
        }

    json_output = {
        "created_at": datetime.now().isoformat(),
        "source_person_analysis_created_at": person_data.get("created_at"),
        "person_count": len(persons),
        "persons_with_ambiguities": sum(1 for x in results.values() if x.get("ambivalenzen")),
        "ambiguity_count": sum(len(x.get("ambivalenzen", [])) for x in results.values()),
        "persons": results,
    }

    md = [
        "# Ambivalenz- und Widerspruchsanalyse\n",
        f"Erstellt am: {json_output['created_at']}\n\n",
        "Analysiert werden ausschließlich **intrapersonelle** Spannungen: unterschiedliche, empirisch belegte Positionen innerhalb desselben Falls.\n\n",
    ]

    for person, result in results.items():
        md.append(f"## {person}\n\n")
        if result.get("gesamteinordnung"):
            md.append(f"{result['gesamteinordnung']}\n\n")
        if not result["ambivalenzen"]:
            md.append("_Keine belastbare intrapersonelle Ambivalenz identifiziert._\n\n")
            continue
        for amb in result["ambivalenzen"]:
            md.append(f"### {amb['thema']}\n\n")
            if amb["beschreibung"]:
                md.append(f"{amb['beschreibung']}\n\n")
            md.append(f"**Position A:** {amb['position_a']}\n\n")
            for b in amb["belege_a"]:
                md.append(f"> `{b['segment_id']}` {b['text']}\n\n")
            md.append(f"**Position B:** {amb['position_b']}\n\n")
            for b in amb["belege_b"]:
                md.append(f"> `{b['segment_id']}` {b['text']}\n\n")

    return "".join(md), json_output
