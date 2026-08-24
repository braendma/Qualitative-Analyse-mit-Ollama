#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import logging
from pathlib import Path

import yaml

from blind_coding_core import blind_code_segments
from coding_validation_common import MockLLM, load_codebook, load_segments, resolve_config_path


LOGGER = logging.getLogger("blind_coding")


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
    parser = argparse.ArgumentParser(description="Segmente blind mit einem externen Kategoriesystem codieren")
    parser.add_argument("--config", "-c", default="config_v2.yaml")
    parser.add_argument("--input-csv", "-i", default=None)
    parser.add_argument("--codebook-csv", default=None)
    parser.add_argument("--idmap-json", default="id_to_text.json")
    parser.add_argument("--out-md", default="blind_coding_v1.md")
    parser.add_argument("--out-json", default="blind_coding_v1.json")
    parser.add_argument("--log-file", default="blind_coding.log")
    parser.add_argument("--mock-responses-json", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    configure_logging(args.log_file)
    LOGGER.info("Blind-Coding gestartet")

    config_path = Path(args.config).resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    raw_enabled = bool(
        config.get("coding_validation", {}).get("log_raw_llm_output", False)
    )
    raw_log_path = "blind_coding_raw.jsonl" if raw_enabled else None
    LOGGER.info(
        "LLM-Raw-Audit: %s%s",
        "aktiv" if raw_enabled else "deaktiviert",
        f" ({raw_log_path})" if raw_log_path else "",
    )
    input_path = Path(args.input_csv or config.get("paths", {}).get("input_csv", ""))
    if not input_path.is_absolute():
        input_path = config_path.parent / input_path
    codebook_path = resolve_config_path(
        config_path, args.codebook_csv, config.get("paths", {}).get("category_system_csv")
    )
    codebook, _ = load_codebook(codebook_path)
    segments = load_segments(input_path, config.get("columns", {}), args.idmap_json)
    llm_cfg = config.get("llm", {})
    params = {
        "model": llm_cfg.get("model", "granite4.1:8b"),
        "temperature": float(llm_cfg.get("temperature", 0.0)),
        "max_tokens": int(llm_cfg.get("max_tokens", 4000)),
    }
    mock_path = None
    if args.mock_responses_json:
        mock_path = Path(args.mock_responses_json)
        if not mock_path.is_absolute():
            mock_path = config_path.parent / mock_path
    llm = MockLLM.from_path(mock_path) if mock_path else None
    markdown, output = blind_code_segments(
        segments, codebook, config.get("prompts", {}), config.get("context", {}), params,
        raw_log_path=raw_log_path,
        **({"llm": llm} if llm else {})
    )
    Path(args.out_md).write_text(markdown, encoding="utf-8")
    Path(args.out_json).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    LOGGER.info(
        "Blind-Coding abgeschlossen: %s Segmente, %s Codepfade",
        len(segments),
        len(codebook),
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        LOGGER.exception("Blind-Coding fehlgeschlagen")
        raise

