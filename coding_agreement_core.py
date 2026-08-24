#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Deterministisches Human–LLM Coding Agreement (keine klassische IRR)."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from coding_validation_common import CodebookEntry, Segment, UNKNOWN_CODES, markdown_escape


def _rows(payload: dict, label: str) -> list[dict]:
    rows = payload.get("results")
    if not isinstance(rows, list):
        raise ValueError(f"{label}: Schlüssel 'results' muss eine Liste sein.")
    return rows


def _index_exact(rows: list[dict], expected_ids: set[str], label: str) -> dict[str, dict]:
    indexed = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"{label}: jeder Ergebnis-Eintrag muss ein Objekt sein.")
        sid = str(row.get("segment_id", "")).strip()
        if sid not in expected_ids:
            raise ValueError(f"{label}: unbekannte Segment-ID {sid!r}.")
        if sid in indexed:
            raise ValueError(f"{label}: doppelte Segment-ID {sid!r}.")
        indexed[sid] = row
    missing = expected_ids - set(indexed)
    if missing:
        raise ValueError(f"{label}: Ergebnisse fehlen für Segment-IDs: {sorted(missing)}")
    return indexed


def _agreement(correct: int, denominator: int) -> dict:
    return {
        "agreements": correct,
        "n_comparable": denominator,
        "rate": (correct / denominator) if denominator else None,
    }


def _cohen_kappa(human: list[str], predicted: list[str]) -> dict:
    n = len(human)
    labels = sorted(set(human) | set(predicted))
    if n < 2 or len(labels) < 2:
        return {
            "calculated": False,
            "value": None,
            "reason": "Nicht sinnvoll: weniger als zwei vergleichbare Fälle oder nur eine nominale Kategorie.",
        }
    observed = sum(a == b for a, b in zip(human, predicted)) / n
    human_counts = Counter(human)
    predicted_counts = Counter(predicted)
    expected = sum((human_counts[x] / n) * (predicted_counts[x] / n) for x in labels)
    if expected >= 1.0:
        return {"calculated": False, "value": None, "reason": "Nicht definiert: erwartete Übereinstimmung ist 1."}
    return {
        "calculated": True,
        "value": (observed - expected) / (1 - expected),
        "reason": (
            "Exploratives Cohen's Kappa für single-label nominale exakte Codepfade; "
            "Human–LLM Coding Agreement, keine klassische Interrater-Reliabilität."
        ),
    }


def _make_confusion(human: list[str], predicted: list[str]) -> tuple[list[str], list[list[int]]]:
    labels = sorted(set(human) | set(predicted))
    positions = {label: index for index, label in enumerate(labels)}
    matrix = [[0 for _ in labels] for _ in labels]
    for left, right in zip(human, predicted):
        matrix[positions[left]][positions[right]] += 1
    return labels, matrix


def save_confusion_png(labels: list[str], matrix: list[list[int]], path: str | Path) -> bool:
    if len(labels) < 2 or len(labels) > 40:
        return False
    try:
        import matplotlib
        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    size = max(7, min(20, 0.55 * len(labels) + 4))
    fig, ax = plt.subplots(figsize=(size, size))
    image = ax.imshow(matrix, cmap="Blues")
    short = [label if len(label) <= 45 else label[:42] + "…" for label in labels]
    ax.set_xticks(range(len(labels)), labels=short, rotation=90, fontsize=7)
    ax.set_yticks(range(len(labels)), labels=short, fontsize=7)
    ax.set_xlabel("LLM-Code")
    ax.set_ylabel("Human-Code")
    ax.set_title("Human–LLM Coding Agreement: Konfusionsmatrix")
    for row_index, row in enumerate(matrix):
        for col_index, value in enumerate(row):
            if value:
                ax.text(col_index, row_index, str(value), ha="center", va="center", fontsize=7)
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return True


def calculate_agreement(
    segments: list[Segment],
    codebook: list[CodebookEntry],
    verification_payload: dict,
    blind_payload: dict,
    confusion_png: str | Path | None = None,
) -> tuple[str, dict]:
    expected_ids = {segment.segment_id for segment in segments}
    verification = _index_exact(_rows(verification_payload, "Verify-Output"), expected_ids, "Verify-Output")
    blind = _index_exact(_rows(blind_payload, "Blind-Output"), expected_ids, "Blind-Output")
    code_index = {entry.code: entry for entry in codebook}
    allowed_codes = set(code_index)

    level_names = ("hauptkategorie", "unterkategorie", "auspraegung", "facette")
    level_correct = Counter()
    level_total = Counter()
    exact_correct = 0
    comparable = 0
    human_codes, predicted_codes = [], []
    confusion_pairs = Counter()
    status_counts = Counter()
    cases = []

    for segment in segments:
        verify_row = verification[segment.segment_id]
        blind_row = blind[segment.segment_id]
        if str(verify_row.get("human_code", "")).strip() != segment.human_code:
            raise ValueError(f"Verify-Output verändert human_code für {segment.segment_id}.")
        verify_state = str(verify_row.get("verification", "")).strip().casefold()
        if verify_state not in {"bestätigt", "teilweise_passend", "nicht_passend", "unklar"}:
            raise ValueError(f"Verify-Output enthält ungültige verification für {segment.segment_id}.")
        for alternative in verify_row.get("alternative_codes", []) or []:
            if alternative not in allowed_codes:
                raise ValueError(f"Verify-Output nennt unbekannten Code {alternative!r}.")

        predicted = str(blind_row.get("predicted_code", "")).strip()
        if predicted not in allowed_codes and predicted.casefold() not in UNKNOWN_CODES:
            raise ValueError(f"Blind-Output nennt unbekannten Code {predicted!r}.")
        for alternative in blind_row.get("alternative_codes", []) or []:
            if alternative not in allowed_codes:
                raise ValueError(f"Blind-Output nennt unbekannten Alternativcode {alternative!r}.")

        is_comparable = segment.human_code in allowed_codes and predicted in allowed_codes
        exact = None
        level_matches = {name: None for name in level_names}
        if is_comparable:
            comparable += 1
            human_codes.append(segment.human_code)
            predicted_codes.append(predicted)
            exact = segment.human_code == predicted
            exact_correct += int(exact)
            if not exact:
                confusion_pairs[(segment.human_code, predicted)] += 1
            human_levels = code_index[segment.human_code].levels()
            predicted_levels = code_index[predicted].levels()
            for name in level_names:
                if human_levels[name] is not None and predicted_levels[name] is not None:
                    level_total[name] += 1
                    match = human_levels[name] == predicted_levels[name]
                    level_correct[name] += int(match)
                    level_matches[name] = match

        if not is_comparable or verify_state == "unklar":
            status = "unklar"
        elif exact and verify_state == "bestätigt":
            status = "bestätigt"
        else:
            status = "strittig"
        status_counts[status] += 1
        cases.append({
            "segment_id": segment.segment_id,
            "human_code": segment.human_code,
            "predicted_code": predicted,
            "verification": verify_state,
            "case_status": status,
            "exact_agreement": exact,
            "level_agreement": level_matches,
        })

    labels, matrix = _make_confusion(human_codes, predicted_codes)
    png_created = bool(confusion_png and save_confusion_png(labels, matrix, confusion_png))
    levels = {name: _agreement(level_correct[name], level_total[name]) for name in level_names}
    output = {
        "analysis_type": "Human–LLM Coding Agreement",
        "methodological_label": "Keine klassische Interrater-Reliabilität",
        "created_at": datetime.now().isoformat(),
        "n_segments": len(segments),
        "n_comparable_exact_codes": comparable,
        "exact_agreement": _agreement(exact_correct, comparable),
        "level_agreement": levels,
        "cohens_kappa": _cohen_kappa(human_codes, predicted_codes),
        "case_counts": {name: status_counts[name] for name in ("bestätigt", "strittig", "unklar")},
        "confusion_matrix": {"labels": labels, "matrix": matrix},
        "confusion_pairs": [
            {"human_code": pair[0], "predicted_code": pair[1], "count": count}
            for pair, count in sorted(confusion_pairs.items(), key=lambda item: (-item[1], item[0]))
        ],
        "confusion_png": Path(confusion_png).name if png_created else None,
        "cases": cases,
    }
    return render_markdown(output), output


def _rate(value):
    return "nicht berechenbar" if value is None else f"{value:.1%}"


def render_markdown(output: dict) -> str:
    exact = output["exact_agreement"]
    lines = [
        "# Human–LLM Coding Agreement\n\n",
        "**Methodischer Hinweis:** Dies ist ein automatisierter Human–LLM Coding-Agreement-Check und keine klassische Interrater-Reliabilität zwischen unabhängigen menschlichen Ratern.\n\n",
        "## Kennzahlen\n\n",
        f"- Segmente insgesamt: {output['n_segments']}\n",
        f"- Vergleichbare single-label Codepfade: {output['n_comparable_exact_codes']}\n",
        f"- Exakte Übereinstimmung: {_rate(exact['rate'])} ({exact['agreements']}/{exact['n_comparable']})\n",
    ]
    for name in ("hauptkategorie", "unterkategorie", "auspraegung", "facette"):
        metric = output["level_agreement"][name]
        lines.append(f"- {name}: {_rate(metric['rate'])} ({metric['agreements']}/{metric['n_comparable']})\n")
    kappa = output["cohens_kappa"]
    if kappa["calculated"]:
        lines.append(f"- Exploratives Cohen's Kappa (exact codes): {kappa['value']:.3f}\n")
    else:
        lines.append(f"- Cohen's Kappa: nicht berechnet — {kappa['reason']}\n")
    lines.extend(["\n## Fallstatus\n\n"])
    for name, count in output["case_counts"].items():
        lines.append(f"- {name}: {count}\n")
    if output["confusion_png"]:
        lines.append(f"\n![Konfusionsmatrix]({output['confusion_png']})\n")
    lines.extend(["\n## Häufige Verwechslungspaare\n\n", "| Human-Code | LLM-Code | Anzahl |\n", "|---|---|---:|\n"])
    for row in output["confusion_pairs"]:
        lines.append(f"| {markdown_escape(row['human_code'])} | {markdown_escape(row['predicted_code'])} | {row['count']} |\n")
    if not output["confusion_pairs"]:
        lines.append("| – | – | 0 |\n")
    lines.extend(["\n## Fälle\n\n", "| Segment-ID | Human-Code | LLM-Code | Verify | Status |\n", "|---|---|---|---|---|\n"])
    for row in output["cases"]:
        lines.append(
            f"| {markdown_escape(row['segment_id'])} | {markdown_escape(row['human_code'])} | "
            f"{markdown_escape(row['predicted_code'])} | {row['verification']} | {row['case_status']} |\n"
        )
    return "".join(lines)

