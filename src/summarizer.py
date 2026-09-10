#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import yaml
import logging
from project_paths import DEFAULT_CONFIG
import argparse
import json
from runtime_support import atomic_json, atomic_text

from summarizer_core import summarize_clusters

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("summarizer_debug.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("summarizer")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Cluster-Summarizer"
    )

    parser.add_argument(
        "--config",
        "-c",
        default=str(DEFAULT_CONFIG)
    )

    parser.add_argument(
        "--clusters-json",
        "-j",
        default="clusters_output.json"
    )

    parser.add_argument(
        "--idmap-json",
        "-m",
        default="id_to_text.json"
    )

    parser.add_argument(
        "--out-md",
        "-o",
        default="summary_v1.md"
    )

    parser.add_argument(
        "--out-json",
        "-x",
        default="summary_v1.json"
    )

    args = parser.parse_args(argv)

    # -------------------------------------------------
    # Config laden
    # -------------------------------------------------
    with open(
        args.config,
        "r",
        encoding="utf-8"
    ) as fh:
        config = yaml.safe_load(fh)

    # -------------------------------------------------
    # LLM-Konfiguration
    # -------------------------------------------------
    llm_cfg = config.get(
        "llm",
        {}
    )

    ollama_params = {
        **llm_cfg,
        "model": llm_cfg.get(
            "model",
            "granite4.2:8b"
        ),
        "temperature": float(
            llm_cfg.get(
                "temperature",
                0.05
            )
        ),
        "max_tokens": int(
            llm_cfg.get(
                "max_tokens",
                10000
            )
        ),
        "think": llm_cfg.get("think"),
        "log_thinking": bool(llm_cfg.get("log_thinking", False)),
    }

    prompts = config.get(
        "prompts",
        {}
    )

    context = config.get(
        "context",
        {}
    )

    # -------------------------------------------------
    # Summarizer ausführen
    # -------------------------------------------------
    md_lines, json_output = summarize_clusters(
        cluster_json_path=args.clusters_json,
        id_to_text_path=args.idmap_json,
        ollama_params=ollama_params,
        prompts=prompts,
        context=context
    )

    # -------------------------------------------------
    # Markdown-Liste -> String
    # -------------------------------------------------
    md = "\n".join(
        md_lines
    )

    # -------------------------------------------------
    # Markdown schreiben
    # -------------------------------------------------
    atomic_text(args.out_md, md)

    # -------------------------------------------------
    # JSON schreiben
    # -------------------------------------------------
    atomic_json(args.out_json, json_output)

    logger.info(
        f"Summaries geschrieben nach: "
        f"{args.out_md}"
    )

    logger.info(
        f"JSON geschrieben nach: "
        f"{args.out_json}"
    )


if __name__ == "__main__":
    main()

