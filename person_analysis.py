#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import logging
import yaml

from person_analysis_core import build_person_analysis

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("person_analysis_debug.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("person_analysis")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Qualitative Personenanalyse")
    parser.add_argument("--config", "-c", default="config_v2.yaml")
    parser.add_argument("--clusters-json", "-j", default="clusters_output.json")
    parser.add_argument("--idmap-json", "-m", default="id_to_text.json")
    parser.add_argument("--summary-json", "-s", default="summary_v1.json")
    parser.add_argument("--out-md", "-o", default="person_analysis_v1.md")
    parser.add_argument("--out-json", "-x", default="person_analysis_v1.json")
    args = parser.parse_args(argv)

    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    llm_cfg = config.get("llm", {})
    ollama_params = {
        "model": llm_cfg.get("model", "granite4.2:8b"),
        "temperature": float(llm_cfg.get("temperature", 0.05)),
        "max_tokens": int(llm_cfg.get("max_tokens", 10000)),
        "think": llm_cfg.get("think"),
        "log_thinking": bool(llm_cfg.get("log_thinking", False)),
    }

    md, json_output = build_person_analysis(
        clusters_json_path=args.clusters_json,
        id_to_text_path=args.idmap_json,
        summary_json_path=args.summary_json,
        ollama_params=ollama_params,
        prompts=config.get("prompts", {}),
        context=config.get("context", {}),
    )

    with open(args.out_md, "w", encoding="utf-8") as f:
        f.write(md)
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(json_output, f, ensure_ascii=False, indent=2)

    logger.info(f"[Personenanalyse] Markdown geschrieben: {args.out_md}")
    logger.info(f"[Personenanalyse] JSON geschrieben: {args.out_json}")


if __name__ == "__main__":
    main()
