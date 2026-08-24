#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import logging
from pathlib import Path

import yaml

from coding_agreement_core import calculate_agreement
from coding_validation_common import load_codebook, load_segments, resolve_config_path


LOGGER = logging.getLogger("coding_agreement")


def configure_logging(log_file: str) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Deterministisches Human–LLM Coding Agreement")
    parser.add_argument("--config", "-c", default="config_v2.yaml")
    parser.add_argument("--input-csv", "-i", default=None)
    parser.add_argument("--codebook-csv", default=None)
    parser.add_argument("--verify-json", default="code_verification_v1.json")
    parser.add_argument("--blind-json", default="blind_coding_v1.json")
    parser.add_argument("--out-md", default="coding_agreement_v1.md")
    parser.add_argument("--out-json", default="coding_agreement_v1.json")
    parser.add_argument("--out-confusion-png", default="coding_agreement_confusion.png")
    parser.add_argument("--log-file", default="coding_agreement.log")
    args = parser.parse_args(argv)
    configure_logging(args.log_file)
    LOGGER.info("Human–LLM Coding Agreement gestartet")

    config_path = Path(args.config).resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    input_path = Path(args.input_csv or config.get("paths", {}).get("input_csv", ""))
    if not input_path.is_absolute():
        input_path = config_path.parent / input_path
    codebook_path = resolve_config_path(
        config_path, args.codebook_csv, config.get("paths", {}).get("category_system_csv")
    )
    codebook, _ = load_codebook(codebook_path)
    segments = load_segments(input_path, config.get("columns", {}))
    verification = json.loads(Path(args.verify_json).read_text(encoding="utf-8"))
    blind = json.loads(Path(args.blind_json).read_text(encoding="utf-8"))
    markdown, output = calculate_agreement(
        segments, codebook, verification, blind, confusion_png=args.out_confusion_png
    )
    Path(args.out_md).write_text(markdown, encoding="utf-8")
    Path(args.out_json).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    exact = output["exact_agreement"]
    LOGGER.info(
        "Agreement abgeschlossen: %s Segmente, %s vergleichbar, exact=%s/%s, bestätigt=%s, strittig=%s, unklar=%s",
        output["n_segments"],
        output["n_comparable_exact_codes"],
        exact["agreements"],
        exact["n_comparable"],
        output["case_counts"]["bestätigt"],
        output["case_counts"]["strittig"],
        output["case_counts"]["unklar"],
    )
    if output.get("confusion_png"):
        LOGGER.info("Konfusionsmatrix geschrieben: %s", output["confusion_png"])
    else:
        LOGGER.info("Keine PNG-Konfusionsmatrix erzeugt (nicht sinnvoll oder Matplotlib nicht verfügbar)")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        LOGGER.exception("Human–LLM Coding Agreement fehlgeschlagen")
        raise

