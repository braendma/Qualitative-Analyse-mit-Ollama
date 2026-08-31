#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import logging

import yaml

from evidence_audit_core import build_evidence_audit

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("evidence_audit_debug.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("evidence_audit")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Audit der empirischen Breite zentraler Meta-SWOT-Befunde"
    )
    parser.add_argument("--config", "-c", default="config_v2.yaml")
    parser.add_argument("--swot-json", default="swot_v1.json")
    parser.add_argument("--meta-swot-json", default="meta_swot_v1.json")
    parser.add_argument("--contrast-json", default="contrast_analysis_v1.json")
    parser.add_argument("--ambiguity-json", default="ambiguity_analysis_v1.json")
    parser.add_argument("--idmap-json", "-m", default="id_to_text.json")
    parser.add_argument("--out-md", "-o", default="evidence_audit_v1.md")
    parser.add_argument("--out-json", "-x", default="evidence_audit_v1.json")
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

    md, json_output = build_evidence_audit(
        swot_json_path=args.swot_json,
        meta_swot_json_path=args.meta_swot_json,
        contrast_analysis_json_path=args.contrast_json,
        ambiguity_analysis_json_path=args.ambiguity_json,
        id_to_text_path=args.idmap_json,
        ollama_params=ollama_params,
        prompts=config.get("prompts", {}),
        context=config.get("context", {}),
    )

    with open(args.out_md, "w", encoding="utf-8") as f:
        f.write(md)
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(json_output, f, ensure_ascii=False, indent=2)

    logger.info("[Evidence-Audit] Markdown geschrieben: %s", args.out_md)
    logger.info("[Evidence-Audit] JSON geschrieben: %s", args.out_json)


if __name__ == "__main__":
    main()
