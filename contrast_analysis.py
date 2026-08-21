#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import logging
import yaml

from contrast_analysis_core import build_contrast_analysis

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("contrast_analysis_debug.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("contrast_analysis")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Qualitative Kontrast- und Negativfallanalyse")
    parser.add_argument("--config", "-c", default="config_v2.yaml")
    parser.add_argument("--person-json", "-p", default="person_analysis_v1.json")
    parser.add_argument("--comparison-json", "-j", default="person_comparison_v1.json")
    parser.add_argument("--out-md", "-o", default="contrast_analysis_v1.md")
    parser.add_argument("--out-json", "-x", default="contrast_analysis_v1.json")
    args = parser.parse_args(argv)

    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    llm_cfg = config.get("llm", {})
    ollama_params = {
        "model": llm_cfg.get("model", "granite4.1:8b"),
        "temperature": float(llm_cfg.get("temperature", 0.05)),
        "max_tokens": int(llm_cfg.get("max_tokens", 10000)),
    }

    md, json_output = build_contrast_analysis(
        person_analysis_json_path=args.person_json,
        person_comparison_json_path=args.comparison_json,
        ollama_params=ollama_params,
        prompts=config.get("prompts", {}),
        context=config.get("context", {}),
    )

    with open(args.out_md, "w", encoding="utf-8") as f:
        f.write(md)
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(json_output, f, ensure_ascii=False, indent=2)

    logger.info(f"[Kontrastanalyse] Markdown geschrieben: {args.out_md}")
    logger.info(f"[Kontrastanalyse] JSON geschrieben: {args.out_json}")


if __name__ == "__main__":
    main()
