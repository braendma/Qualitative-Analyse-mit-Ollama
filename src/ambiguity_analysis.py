#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from project_paths import DEFAULT_CONFIG
import argparse
import json
from runtime_support import atomic_json, atomic_text, run_artifact_path
import logging

import yaml

from ambiguity_analysis_core import build_ambiguity_analysis
from thematic_pipeline import prepare, finish

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(run_artifact_path("ambiguity_analysis_debug.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("ambiguity_analysis")


from progress_events import track_module

@track_module
def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Qualitative Analyse intrapersoneller Ambivalenzen und Spannungen"
    )
    parser.add_argument('--csv', help='Normalisierter Segmentexport für die optionale Analyseperspektive')
    parser.add_argument("--config", "-c", default=str(DEFAULT_CONFIG))
    parser.add_argument("--person-json", "-p", default="person_analysis_v1.json")
    parser.add_argument("--idmap-json", "-m", default="id_to_text.json")
    parser.add_argument("--out-md", "-o", default="ambiguity_analysis_v1.md")
    parser.add_argument("--out-json", "-x", default="ambiguity_analysis_v1.json")
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

    prepared = prepare('ambiguity_analysis', args.config, input_path=args.csv,
                       person_path=args.person_json, idmap_path=args.idmap_json)
    md, json_output = build_ambiguity_analysis(
        person_analysis_json_path=args.person_json,
        id_to_text_path=args.idmap_json,
        ollama_params=ollama_params,
        prompts=config.get("prompts", {}),
        context=config.get("context", {}),
    )

    md, json_output = finish(prepared, json_output, md, ollama_params)
    atomic_text(args.out_md, md)
    atomic_json(args.out_json, json_output)

    logger.info("[Ambivalenzanalyse] Markdown geschrieben: %s", args.out_md)
    logger.info("[Ambivalenzanalyse] JSON geschrieben: %s", args.out_json)


if __name__ == "__main__":
    main()
