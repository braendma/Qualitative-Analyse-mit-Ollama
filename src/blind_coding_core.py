#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Blindes LLM-Coding ausschließlich mit vorhandenen Codepfaden."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Callable

from coding_validation_common import (
    UNKNOWN_CODES,
    CodebookEntry,
    RawJsonlWriter,
    Segment,
    call_json_with_repair,
    default_llm,
    markdown_escape,
)
from utils_prompt import build_prompt_for_module
from runtime_support import Checkpoint, checkpoint_identity
from coding_validation_common import CODEBOOK_RULE_GUIDANCE
from llm_client import LLMResponseError

CONFIDENCES = {"hoch", "mittel", "niedrig"}
LOGGER = logging.getLogger("blind_coding")


def _duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "--:--:--"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _show_progress(current: int, total: int, started: float) -> None:
    from progress_events import update_progress
    update_progress(completed=current,total=total,unit='rows')
    width = 28
    ratio = (current / total) if total else 1.0
    filled = min(width, int(width * ratio))
    bar = "#" * filled + "-" * (width - filled)
    elapsed = time.monotonic() - started
    eta = ((elapsed / current) * (total - current)) if current else None
    LOGGER.info(
        "[Blind-Coding] [%s] %s/%s (%6.2f%%) | Laufzeit %s | Restzeit ca. %s",
        bar,
        current,
        total,
        ratio * 100,
        _duration(elapsed),
        _duration(eta),
    )


def _validate_response(value: dict, segment_id: str, allowed_codes: set[str]) -> dict:
    returned_id = str(value.get("segment_id", "")).strip()
    predicted = str(value.get("predicted_code", "")).strip()
    confidence = str(value.get("confidence", "")).strip().casefold()
    reason = str(value.get("begruendung") or value.get("begründung") or "").strip()
    alternatives = value.get("alternative_codes", [])
    if returned_id != segment_id:
        raise ValueError(f"segment_id muss exakt {segment_id!r} sein.")
    if predicted not in allowed_codes and predicted.casefold() not in UNKNOWN_CODES:
        raise ValueError(f"predicted_code ist kein existierender Codepfad: {predicted!r}")
    if predicted.casefold() in UNKNOWN_CODES:
        predicted = predicted.casefold()
    if confidence not in CONFIDENCES:
        raise ValueError(f"confidence muss einer dieser Werte sein: {sorted(CONFIDENCES)}")
    if not reason:
        raise ValueError("begruendung darf nicht leer sein.")
    if isinstance(alternatives, str):
        alternatives = [alternatives]
    if not isinstance(alternatives, list):
        raise ValueError("alternative_codes muss eine Liste sein.")
    cleaned = []
    for code in alternatives:
        code = str(code).strip()
        if code not in allowed_codes:
            LOGGER.warning(
                "[Blind-Coding] Nicht existierender Alternativcode für %s verworfen: %r",
                segment_id,
                code,
            )
            continue
        if code != predicted and code not in cleaned:
            cleaned.append(code)
    return {
        "segment_id": segment_id,
        "predicted_code": predicted,
        "confidence": confidence,
        "begruendung": reason,
        "alternative_codes": cleaned,
    }


def blind_code_segments(
    segments: list[Segment],
    codebook: list[CodebookEntry],
    prompts: dict,
    context: dict,
    llm_params: dict,
    raw_log_path: str | None = None,
    llm: Callable = default_llm,
    checkpoint_path: str | None = None,
) -> tuple[str, dict]:
    if llm_params.get('label_mode') == 'multi_label':
        from multi_label_core import blind_code_units
        return blind_code_units(segments, codebook, prompts, context, llm_params, raw_log_path, llm, checkpoint_path)
    allowed_codes = {entry.code for entry in codebook}
    codebook_payload = json.dumps(
        [entry.as_prompt_dict() for entry in codebook], ensure_ascii=False
    )
    results = []
    checkpoint = Checkpoint(checkpoint_path, checkpoint_identity(segments, codebook, prompts, context, llm_params))
    raw_writer = RawJsonlWriter(raw_log_path, "blind_coding") if raw_log_path else None
    total = len(segments)
    started = time.monotonic()
    _show_progress(0, total, started)
    for position, segment in enumerate(segments, start=1):
        cached = checkpoint.get(segment.segment_id)
        if cached:
            results.append(cached)
            _show_progress(position, total, started)
            continue
        # Absichtlich wird hier weder human_code noch ein daraus abgeleiteter Zielcode übergeben.
        system_prompt, user_prompt = build_prompt_for_module(
            "blind_coding",
            prompts=prompts,
            context=context,
            segment_id=segment.segment_id,
            segment=segment.text,
            codebook=codebook_payload,
        )
        try:
            result = call_json_with_repair(
                [{"role": "system", "content": system_prompt + CODEBOOK_RULE_GUIDANCE}, {"role": "user", "content": user_prompt}],
                llm_params,
                lambda value, sid=segment.segment_id: _validate_response(value, sid, allowed_codes),
                llm=llm,
                raw_callback=(raw_writer.callback_for(segment.segment_id) if raw_writer else None),
            )
        except (ValueError, LLMResponseError) as exc:
            LOGGER.warning(
                "[Blind-Coding] Strukturell ungültige LLM-Antwort für %s; Fall erhält processing_status=failed: %s",
                segment.segment_id,
                exc,
            )
            result = {
                "segment_id": segment.segment_id,
                "predicted_code": "unklar",
                "confidence": "niedrig",
                "processing_status": "failed",
                "error_type": "invalid_response",
                "begruendung": "Die LLM-Antwort blieb nach Self-Repair strukturell ungültig; es wurde kein nicht validierter Code übernommen.",
                "alternative_codes": [],
            }
        result.setdefault("processing_status", "completed")
        checkpoint.save(segment.segment_id, result)
        results.append(result)
        _show_progress(position, total, started)
    output = {
        "analysis_type": "Blind Coding mit externem Kategoriesystem",
        "created_at": datetime.now().isoformat(),
        "codebook_size": len(codebook),
        "segment_count": len(segments),
        "processing_status": "completed" if all(r["processing_status"] == "completed" for r in results) else "incomplete",
        "processing_counts": {key: sum(r["processing_status"] == key for r in results) for key in ("completed", "failed", "invalid_input")},
        "confidence_note": "Konfidenz ist eine unkalibrierte Selbsteinschätzung des Modells.",
        "results": results,
    }
    return render_markdown(output), output


def render_markdown(output: dict) -> str:
    lines = [
        "# Blind-Coding\n\n",
        "Das LLM erhielt Segmenttext und Kategoriesystem, jedoch nicht den menschlich vergebenen Code. "
        "Zulässig waren nur vollständige bestehende Codepfade, `unklar` oder `keine_zuordnung`.\n\n",
        "| Segment-ID | Vorhergesagter Code | Konfidenz | Begründung | Alternativen |\n",
        "|---|---|---|---|---|\n",
    ]
    lines.insert(1, f"Verarbeitungsstatus: **{output['processing_status']}**. {output['processing_counts']}\n\nKonfidenz = unkalibrierte Modellselbsteinschätzung.\n\n")
    for row in output["results"]:
        alternatives = ", ".join(row["alternative_codes"]) or "–"
        lines.append(
            f"| {markdown_escape(row['segment_id'])} | {row.get('processing_status', 'completed')}: {markdown_escape(row['predicted_code'])} | "
            f"{row['confidence']} | {markdown_escape(row['begruendung'])} | {markdown_escape(alternatives)} |\n"
        )
    return "".join(lines)
