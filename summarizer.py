#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import yaml
import logging
import argparse
import json

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
        default="config_v2.yaml"
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
    with open(
        args.out_md,
        "w",
        encoding="utf-8"
    ) as f:
        f.write(md)

    # -------------------------------------------------
    # JSON schreiben
    # -------------------------------------------------
    with open(
        args.out_json,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            json_output,
            f,
            ensure_ascii=False,
            indent=2
        )

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
