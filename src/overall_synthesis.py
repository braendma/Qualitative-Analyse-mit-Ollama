#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from project_paths import DEFAULT_CONFIG
import argparse
import json
from runtime_support import atomic_json, atomic_text
import logging

import yaml

from overall_synthesis_core import build_overall_synthesis

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("overall_synthesis_debug.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("overall_synthesis")


def _parse_source_arg(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError(
            "--source-json erwartet LABEL=DATEI, z. B. Meta-SWOT=meta_swot_v1.json"
        )
    label, path = value.split("=", 1)
    label = label.strip()
    path = path.strip()
    if not label or not path:
        raise argparse.ArgumentTypeError("LABEL und DATEI dürfen nicht leer sein.")
    return label, path


from progress_events import track_module

@track_module
def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Gesamtsynthese aus frei deklarierbaren analytischen JSON-Quellen"
    )
    parser.add_argument("--config", "-c", default=str(DEFAULT_CONFIG))
    parser.add_argument(
        "--source-json",
        action="append",
        default=[],
        metavar="LABEL=DATEI",
        help="Analytische Quelle; mehrfach angebbar.",
    )

    # Legacy-Argumente bleiben kompatibel.
    parser.add_argument("--meta-swot-json", default=None)
    parser.add_argument("--comparison-json", default=None)
    parser.add_argument("--contrast-json", default=None)

    parser.add_argument("--out-md", "-o", default="overall_synthesis_v1.md")
    parser.add_argument("--out-json", "-x", default="overall_synthesis_v1.json")
    args = parser.parse_args(argv)

    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    llm_cfg = config.get("llm", {})
    ollama_params = {
        **llm_cfg,
        "model": llm_cfg.get("model", "granite4.2:8b"),
        "temperature": float(llm_cfg.get("temperature", 0.05)),
        "max_tokens": int(llm_cfg.get("max_tokens", 10000)),
        "think": llm_cfg.get("think"),
        "log_thinking": bool(llm_cfg.get("log_thinking", False)),
    }

    sources = {}
    for raw in args.source_json:
        label, path = _parse_source_arg(raw)
        sources[label] = path

    if args.meta_swot_json:
        sources.setdefault("Meta-SWOT", args.meta_swot_json)
    if args.comparison_json:
        sources.setdefault("Personenvergleich", args.comparison_json)
    if args.contrast_json:
        sources.setdefault("Kontrastanalyse", args.contrast_json)

    if not sources:
        # Rückwärtskompatible Defaults.
        sources = {
            "Meta-SWOT": "meta_swot_v1.json",
            "Personenvergleich": "person_comparison_v1.json",
            "Kontrastanalyse": "contrast_analysis_v1.json",
        }

    md, json_output = build_overall_synthesis(
        source_json_paths=sources,
        ollama_params=ollama_params,
        prompts=config.get("prompts", {}),
        context=config.get("context", {}),
    )

    atomic_text(args.out_md, md)
    atomic_json(args.out_json, json_output)

    logger.info("[Gesamtsynthese] Markdown geschrieben: %s", args.out_md)
    logger.info("[Gesamtsynthese] JSON geschrieben: %s", args.out_json)


if __name__ == "__main__":
    main()

