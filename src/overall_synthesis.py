#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from project_paths import DEFAULT_CONFIG
import argparse
import json
from runtime_support import atomic_json, atomic_text, run_artifact_path
import logging

import yaml

from overall_synthesis_core import build_overall_synthesis
from synthesis_inputs import parse_source, resolve_sources
from thematic_pipeline import prepare, finish

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(run_artifact_path("overall_synthesis_debug.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("overall_synthesis")


def _parse_source_arg(value: str) -> tuple[str, str]:
    try:
        return parse_source(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


from progress_events import track_module

@track_module
def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Gesamtsynthese aus frei deklarierbaren analytischen JSON-Quellen", allow_abbrev=False
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
    parser.add_argument("--csv", default=None, help="Originalmaterial für die optionale Häufigkeitsperspektive")

    parser.add_argument("--out-md", "-o", default="overall_synthesis_v1.md")
    parser.add_argument("--out-json", "-x", default="overall_synthesis_v1.json")
    args = parser.parse_args(argv)

    sources = resolve_sources(args.source_json, meta_swot_json=args.meta_swot_json,
                              comparison_json=args.comparison_json, contrast_json=args.contrast_json)

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

    prepared = prepare('overall_synthesis', args.config, input_path=args.csv, source_paths=sources)
    md, json_output = build_overall_synthesis(
        source_json_paths=sources,
        ollama_params=ollama_params,
        prompts=config.get("prompts", {}),
        context=config.get("context", {}),
    )

    md, json_output = finish(prepared, json_output, md, ollama_params)
    atomic_text(args.out_md, md)
    atomic_json(args.out_json, json_output)

    logger.info("[Gesamtsynthese] Markdown geschrieben: %s", args.out_md)
    logger.info("[Gesamtsynthese] JSON geschrieben: %s", args.out_json)


if __name__ == "__main__":
    main()
