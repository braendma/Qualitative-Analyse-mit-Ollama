#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""LLM-gestützte Prüfung menschlicher Codes gegen ein externes Codebuch."""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime
from typing import Callable

from coding_validation_common import (
    CodebookEntry,
    RawJsonlWriter,
    Segment,
    call_json_with_repair,
    default_llm,
    markdown_escape,
)
from utils_prompt import build_prompt_for_module

LOGGER = logging.getLogger("code_verification")
VERIFICATIONS = {"bestätigt", "teilweise_passend", "nicht_passend", "unklar"}
CONFIDENCES = {"hoch", "mittel", "niedrig"}


def _duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "--:--:--"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _show_progress(current: int, total: int, started: float) -> None:
    width = 28
    ratio = (current / total) if total else 1.0
    filled = min(width, int(width * ratio))
    bar = "#" * filled + "-" * (width - filled)
    elapsed = time.monotonic() - started
    eta = ((elapsed / current) * (total - current)) if current else None
    ending = "\n" if current >= total else "\r"
    print(
        f"[Code-Verifikation] [{bar}] {current}/{total} "
        f"({ratio:6.2%}) | Laufzeit {_duration(elapsed)} | Restzeit ca. {_duration(eta)}",
        end=ending,
        file=sys.stderr,
        flush=True,
    )


def _validate_response(value: dict, segment: Segment, allowed_codes: set[str]) -> dict:
    segment_id = str(value.get("segment_id", "")).strip()
    human_code = str(value.get("human_code", "")).strip()
    verification = str(value.get("verification", "")).strip().casefold()
    confidence = str(value.get("confidence", "")).strip().casefold()
    reason = str(value.get("begruendung") or value.get("begründung") or "").strip()
    alternatives = value.get("alternative_codes", [])

    if segment_id != segment.segment_id:
        raise ValueError(f"segment_id muss exakt {segment.segment_id!r} sein.")
    if human_code != segment.human_code:
        raise ValueError("human_code wurde verändert oder dem falschen Segment zugeordnet.")
    if verification not in VERIFICATIONS:
        raise ValueError(f"verification muss einer dieser Werte sein: {sorted(VERIFICATIONS)}")
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
                "[Code-Verifikation] Nicht existierender Alternativcode für %s verworfen: %r",
                segment.segment_id,
                code,
            )
            continue
        if code != segment.human_code and code not in cleaned:
            cleaned.append(code)
    return {
        "segment_id": segment.segment_id,
        "human_code": segment.human_code,
        "verification": verification,
        "confidence": confidence,
        "begruendung": reason,
        "alternative_codes": cleaned,
    }


def verify_segments(
    segments: list[Segment],
    codebook: list[CodebookEntry],
    prompts: dict,
    context: dict,
    llm_params: dict,
    idmap_reference: str = "id_to_text.json",
    raw_log_path: str | None = None,
    llm: Callable = default_llm,
) -> tuple[str, dict]:
    by_code = {entry.code: entry for entry in codebook}
    allowed_codes = set(by_code)
    codebook_payload = json.dumps(
        [entry.as_prompt_dict() for entry in codebook], ensure_ascii=False
    )
    results = []
    raw_writer = RawJsonlWriter(raw_log_path, "code_verification") if raw_log_path else None
    total = len(segments)
    started = time.monotonic()
    _show_progress(0, total, started)

    for position, segment in enumerate(segments, start=1):
        if segment.human_code not in allowed_codes:
            base = {
                "segment_id": segment.segment_id,
                "human_code": segment.human_code,
                "verification": "unklar",
                "confidence": "niedrig",
                "begruendung": "Der menschliche Code ist kein vollständiger Codepfad des geladenen Kategoriesystems.",
                "alternative_codes": [],
            }
        else:
            target = by_code[segment.human_code]
            system_prompt, user_prompt = build_prompt_for_module(
                "code_verification",
                prompts=prompts,
                context=context,
                segment_id=segment.segment_id,
                segment=segment.text,
                human_code=segment.human_code,
                target_code=json.dumps(target.as_prompt_dict(), ensure_ascii=False),
                codebook=codebook_payload,
            )
            try:
                base = call_json_with_repair(
                    [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    llm_params,
                    lambda value, current=segment: _validate_response(value, current, allowed_codes),
                    llm=llm,
                    raw_callback=(raw_writer.callback_for(segment.segment_id) if raw_writer else None),
                )
            except ValueError as exc:
                LOGGER.warning(
                    "[Code-Verifikation] Strukturell ungültige LLM-Antwort für %s; Fall wird als unklar fortgeführt: %s",
                    segment.segment_id,
                    exc,
                )
                base = {
                    "segment_id": segment.segment_id,
                    "human_code": segment.human_code,
                    "verification": "unklar",
                    "confidence": "niedrig",
                    "begruendung": "Die LLM-Antwort blieb nach Self-Repair strukturell ungültig; es wurde kein nicht validierter Befund übernommen.",
                    "alternative_codes": [],
                }

        base["validated_quote"] = segment.text
        base["original_text_ref"] = f"{idmap_reference}::{segment.segment_id}"
        results.append(base)
        _show_progress(position, total, started)

    output = {
        "analysis_type": "Code Verification gegen externes Kategoriesystem",
        "created_at": datetime.now().isoformat(),
        "codebook_size": len(codebook),
        "segment_count": len(segments),
        "results": results,
    }
    return render_markdown(output), output


def render_markdown(output: dict) -> str:
    counts = {key: 0 for key in sorted(VERIFICATIONS)}
    for row in output["results"]:
        counts[row["verification"]] += 1
    lines = [
        "# Code-Verifikation\n\n",
        "Prüfung menschlich vergebener Codes gegen Definitionen und Ankerbeispiele des externen Kategoriensystems. "
        "Es wurden keine neuen Codes zugelassen und keine psychologischen Interpretationen vorgenommen.\n\n",
        "## Übersicht\n\n",
        f"- Segmente: {output['segment_count']}\n",
    ]
    for key, value in counts.items():
        lines.append(f"- {key}: {value}\n")
    lines.extend(["\n## Einzelfälle\n\n", "| Segment-ID | Human-Code | Ergebnis | Konfidenz | Begründung | Alternativen |\n", "|---|---|---|---|---|---|\n"])
    for row in output["results"]:
        alternatives = ", ".join(row["alternative_codes"]) or "–"
        lines.append(
            f"| {markdown_escape(row['segment_id'])} | {markdown_escape(row['human_code'])} | "
            f"{row['verification']} | {row['confidence']} | {markdown_escape(row['begruendung'])} | "
            f"{markdown_escape(alternatives)} |\n"
        )
        lines.append(f"\n> **{row['segment_id']}** — {row['validated_quote']}\n\n")
    return "".join(lines)

