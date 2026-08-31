# evidence_audit_core.py

import json
import logging
from datetime import datetime

from clusterer_core import ollama_chat, safe_json_loads
from meta_swot_core import DIMENSIONS, flatten_findings
from utils_prompt import build_prompt_for_module

logger = logging.getLogger("evidence_audit")


def _person_from_sid(sid: str) -> str:
    sid = str(sid)
    return sid.split("#SEG", 1)[0].strip() if "#SEG" in sid else sid.strip()


def _flatten_lookup(swot_data: dict) -> dict:
    by_dimension = flatten_findings(swot_data)
    return {
        item["finding_id"]: item
        for dimension in DIMENSIONS
        for item in by_dimension.get(dimension, [])
    }


def build_audit_items(meta_swot_data: dict, finding_lookup: dict) -> list:
    items = []
    meta = meta_swot_data.get("meta_swot", {})

    for dimension in DIMENSIONS:
        section = meta.get(dimension, {})
        if not isinstance(section, dict):
            continue

        for pattern in section.get("uebergreifende_muster", []) or []:
            if not isinstance(pattern, dict):
                continue
            finding_ids = [
                str(x).strip() for x in pattern.get("finding_ids", [])
                if str(x).strip() in finding_lookup
            ]
            findings = [finding_lookup[fid] for fid in finding_ids]
            segment_ids = list(dict.fromkeys(
                sid for finding in findings for sid in finding.get("segment_ids", [])
            ))
            sources = list(dict.fromkeys(f["source_id"] for f in findings))
            persons = list(dict.fromkeys(_person_from_sid(sid) for sid in segment_ids))
            items.append({
                "audit_id": f"EVA{len(items) + 1:04d}",
                "dimension": dimension,
                "befundtyp": "uebergreifendes_muster",
                "thema": str(pattern.get("thema", "")).strip(),
                "verdichtung": str(pattern.get("verdichtung", "")).strip(),
                "finding_ids": finding_ids,
                "quellbereiche": sources,
                "segment_ids": segment_ids,
                "personen": persons,
            })

        for single in section.get("einzelbefunde", []) or []:
            if not isinstance(single, dict):
                continue
            fid = str(single.get("finding_id", "")).strip()
            finding = finding_lookup.get(fid)
            if finding is None:
                continue
            segment_ids = list(dict.fromkeys(finding.get("segment_ids", [])))
            persons = list(dict.fromkeys(_person_from_sid(sid) for sid in segment_ids))
            items.append({
                "audit_id": f"EVA{len(items) + 1:04d}",
                "dimension": dimension,
                "befundtyp": "einzelbefund",
                "thema": str(single.get("thema", finding.get("thema", ""))).strip(),
                "verdichtung": str(single.get("verdichtung", finding.get("analyse", ""))).strip(),
                "finding_ids": [fid],
                "quellbereiche": [finding["source_id"]],
                "segment_ids": segment_ids,
                "personen": persons,
            })

    return items


def build_counter_candidates(contrast_data: dict, ambiguity_data: dict) -> list:
    candidates = []

    for idx, item in enumerate(contrast_data.get("negativfaelle", []) or [], start=1):
        if not isinstance(item, dict):
            continue
        candidates.append({
            "counter_id": f"NEG{idx:04d}",
            "typ": "negativfall",
            "person": str(item.get("person", "")).strip(),
            "bezugs_muster": str(item.get("bezugs_muster", "")).strip(),
            "abweichung": str(item.get("abweichung", "")).strip(),
            "begruendung": str(item.get("begruendung", "")).strip(),
        })

    amb_index = 0
    for person, pdata in (ambiguity_data.get("persons", {}) or {}).items():
        if not isinstance(pdata, dict):
            continue
        for amb in pdata.get("ambivalenzen", []) or []:
            if not isinstance(amb, dict):
                continue
            amb_index += 1
            candidates.append({
                "counter_id": f"AMB{amb_index:04d}",
                "typ": "intrapersonelle_ambivalenz",
                "person": str(person),
                "thema": str(amb.get("thema", "")).strip(),
                "beschreibung": str(amb.get("beschreibung", "")).strip(),
                "position_a": str(amb.get("position_a", "")).strip(),
                "position_b": str(amb.get("position_b", "")).strip(),
                "segment_ids_a": amb.get("segment_ids_a", []),
                "segment_ids_b": amb.get("segment_ids_b", []),
            })

    return candidates


def _llm(system_prompt, user_prompt, ollama_params):
    for attempt in range(3):
        logger.info("[Evidence-Audit-Retry] Versuch %s/3", attempt + 1)
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
        logger.info("\n===== RAW EVIDENCE AUDIT OUTPUT =====\n%s\n=====================================\n", content)
        if content:
            return content.strip()
    return ""


def _repair(broken_output, ollama_params):
    system = """
Du reparierst ausschließlich JSON für einen Evidence-Audit.
Gib genau ein Objekt mit dem Schlüssel \"zuordnungen\" zurück.
zuordnungen ist eine Liste. Jeder Eintrag besitzt exakt:
audit_id, gegenbeleg_ids, einordnung.
gegenbeleg_ids ist eine Liste von Strings.
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


def normalize_mappings(parsed: dict, audit_ids: set, counters_by_id: dict) -> dict:
    result = {audit_id: {"gegenbeleg_ids": [], "einordnung": ""} for audit_id in audit_ids}
    if not isinstance(parsed, dict):
        return result

    raw = parsed.get("zuordnungen", [])
    if not isinstance(raw, list):
        raw = [raw] if raw else []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        audit_id = str(entry.get("audit_id", "")).strip()
        if audit_id not in audit_ids:
            continue
        ids = [
            str(x).strip()
            for x in entry.get("gegenbeleg_ids", [])
            if str(x).strip() in counters_by_id
        ]
        result[audit_id] = {
            "gegenbeleg_ids": list(dict.fromkeys(ids)),
            "einordnung": str(entry.get("einordnung", "")).strip(),
        }
    return result


def evidence_breadth(source_count: int, person_count: int) -> str:
    if source_count >= 2 and person_count >= 2:
        return "mehrere_quellbereiche_und_mehrere_personen"
    if source_count >= 2:
        return "mehrere_quellbereiche"
    if person_count >= 2:
        return "mehrere_personen"
    return "lokal_begrenzt"


def build_evidence_audit(
    swot_json_path: str,
    meta_swot_json_path: str,
    contrast_analysis_json_path: str,
    ambiguity_analysis_json_path: str,
    id_to_text_path: str,
    ollama_params: dict,
    prompts: dict,
    context: dict,
):
    with open(swot_json_path, "r", encoding="utf-8") as f:
        swot_data = json.load(f)
    with open(meta_swot_json_path, "r", encoding="utf-8") as f:
        meta_data = json.load(f)
    with open(contrast_analysis_json_path, "r", encoding="utf-8") as f:
        contrast_data = json.load(f)
    with open(ambiguity_analysis_json_path, "r", encoding="utf-8") as f:
        ambiguity_data = json.load(f)
    with open(id_to_text_path, "r", encoding="utf-8") as f:
        id_to_text = json.load(f)

    registry = meta_data.get("finding_registry", {})
    if isinstance(registry, dict) and registry:
        finding_lookup = {
            str(fid): finding
            for fid, finding in registry.items()
            if isinstance(finding, dict)
        }
    else:
        logger.warning(
            "[Evidence-Audit] Meta-SWOT enthält kein finding_registry; "
            "rekonstruiere IDs aus swot_v1.json."
        )
        finding_lookup = _flatten_lookup(swot_data)

    audit_items = build_audit_items(meta_data, finding_lookup)
    counter_candidates = build_counter_candidates(contrast_data, ambiguity_data)
    counters_by_id = {x["counter_id"]: x for x in counter_candidates}

    if audit_items and counter_candidates:
        payload = {
            "audit_befunde": [
                {
                    "audit_id": x["audit_id"],
                    "dimension": x["dimension"],
                    "thema": x["thema"],
                    "verdichtung": x["verdichtung"],
                }
                for x in audit_items
            ],
            "moegliche_gegenbelege": counter_candidates,
        }
        system_prompt, user_prompt = build_prompt_for_module(
            "evidence_audit",
            prompts=prompts,
            context=context,
            data=json.dumps(payload, ensure_ascii=False, indent=2),
        )
        raw = _llm(system_prompt, user_prompt, ollama_params)
        parsed = safe_json_loads(raw)
        if parsed is None:
            logger.warning("[Evidence-Audit] Ungültiges JSON; starte Repair.")
            parsed = safe_json_loads(_repair(raw, ollama_params))
        mappings = normalize_mappings(
            parsed or {}, {x["audit_id"] for x in audit_items}, counters_by_id
        )
    else:
        mappings = {x["audit_id"]: {"gegenbeleg_ids": [], "einordnung": ""} for x in audit_items}

    audited = []
    for item in audit_items:
        mapping = mappings[item["audit_id"]]
        counter_items = [counters_by_id[cid] for cid in mapping["gegenbeleg_ids"]]
        source_count = len(item["quellbereiche"])
        person_count = len(item["personen"])
        segment_count = len(item["segment_ids"])
        counter_count = len(counter_items)

        if item["befundtyp"] == "uebergreifendes_muster":
            status = "mehrfach_gestuetzt_mit_relativierung" if counter_count else "mehrfach_gestuetzt"
        else:
            status = "quellenspezifisch_mit_relativierung" if counter_count else "quellenspezifisch"

        audited.append({
            **item,
            "finding_count": len(item["finding_ids"]),
            "quellbereich_count": source_count,
            "personen_count": person_count,
            "segment_count": segment_count,
            "evidenzbreite": evidence_breadth(source_count, person_count),
            "status": status,
            "gegenbeleg_count": counter_count,
            "gegenbelege": counter_items,
            "relativierende_einordnung": mapping["einordnung"],
            "belegbeispiele": [
                {"segment_id": sid, "text": id_to_text.get(sid, "")}
                for sid in item["segment_ids"][:3]
            ],
        })

    json_output = {
        "created_at": datetime.now().isoformat(),
        "source_swot_created_at": swot_data.get("created_at"),
        "source_meta_swot_created_at": meta_data.get("created_at"),
        "source_contrast_created_at": contrast_data.get("created_at"),
        "source_ambiguity_created_at": ambiguity_data.get("created_at"),
        "audited_finding_count": len(audited),
        "methodischer_hinweis": (
            "Evidenzbreite beschreibt ausschließlich die Verteilung innerhalb des vorliegenden qualitativen Materials; "
            "sie ist weder statistische Signifikanz noch ein quantitatives Gütemaß."
        ),
        "befunde": audited,
    }

    md = [
        "# Evidence-Audit\n",
        f"Erstellt am: {json_output['created_at']}\n\n",
        f"> {json_output['methodischer_hinweis']}\n\n",
        f"Geprüfte Meta-SWOT-Befunde: **{len(audited)}**\n\n",
    ]

    for item in audited:
        md.append(f"## {item['dimension']}: {item['thema']}\n\n")
        md.append(f"{item['verdichtung']}\n\n")
        md.append(
            f"- Befundtyp: **{item['befundtyp']}**\n"
            f"- Quellbereiche: **{item['quellbereich_count']}**\n"
            f"- Personen: **{item['personen_count']}**\n"
            f"- Segmente: **{item['segment_count']}**\n"
            f"- Evidenzbreite: **{item['evidenzbreite']}**\n"
            f"- Status: **{item['status']}**\n"
            f"- Zugeordnete Gegenbelege/Relativierungen: **{item['gegenbeleg_count']}**\n\n"
        )
        if item["relativierende_einordnung"]:
            md.append(f"**Relativierende Einordnung:** {item['relativierende_einordnung']}\n\n")
        if item["gegenbelege"]:
            md.append("### Gegenbelege / Relativierungen\n\n")
            for c in item["gegenbelege"]:
                label = c.get("abweichung") or c.get("beschreibung") or c.get("thema") or c.get("counter_id")
                md.append(f"- **{c['counter_id']}** ({c['typ']}): {label}\n")
            md.append("\n")
        if item["belegbeispiele"]:
            md.append("### Belegbeispiele\n\n")
            for b in item["belegbeispiele"]:
                md.append(f"> `{b['segment_id']}` {b['text']}\n\n")

    return "".join(md), json_output
