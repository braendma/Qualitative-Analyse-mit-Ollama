#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import yaml
import logging
import argparse
import json

from swot_core import build_swot


# -----------------------------------------------------
# Logging
# -----------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            "swot_debug.log",
            encoding="utf-8"
        ),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("swot")


# -----------------------------------------------------
# Main
# -----------------------------------------------------
def main(argv=None):

    parser = argparse.ArgumentParser(
        description="SWOT-Pipeline"
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
        "--summary-json",
        "-s",
        default="summary_v1.json"
    )

    parser.add_argument(
        "--out-md",
        "-o",
        default="swot_v1.md"
    )

    parser.add_argument(
        "--out-json",
        "-x",
        default="swot_v1.json"
    )

    args = parser.parse_args(argv)

    # -------------------------------------------------
    # Config
    # -------------------------------------------------
    with open(
        args.config,
        "r",
        encoding="utf-8"
    ) as fh:
        config = yaml.safe_load(fh)

    # -------------------------------------------------
    # LLM
    # -------------------------------------------------
    llm_cfg = config.get(
        "llm",
        {}
    )

    ollama_params = {
        "model": llm_cfg.get(
            "model",
            "granite4.1:8b"
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
        )
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
    # SWOT
    # -------------------------------------------------
    markdown_output, json_output = build_swot(
        clusters_json_path=args.clusters_json,
        id_to_text_path=args.idmap_json,
        summary_json_path=args.summary_json,
        ollama_params=ollama_params,
        prompts=prompts,
        context=context
    )

    # -------------------------------------------------
    # Markdown
    # -------------------------------------------------
    with open(
        args.out_md,
        "w",
        encoding="utf-8"
    ) as f:
        f.write(
            markdown_output
        )

    # -------------------------------------------------
    # JSON
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
        f"[SWOT] Markdown geschrieben nach: {args.out_md}"
    )

    logger.info(
        f"[SWOT] JSON geschrieben nach: {args.out_json}"
    )


if __name__ == "__main__":
    main()