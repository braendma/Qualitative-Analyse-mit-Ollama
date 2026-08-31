#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import yaml
import logging
import argparse
import json
import pandas as pd

from clusterer_core import run_clustering

# Logging konfigurieren (schreibt in clusterer_debug.log und stdout)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("clusterer_debug.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("clusterer")


def main(argv=None):
    parser = argparse.ArgumentParser(description="LLM-Clusterer")

    parser.add_argument("--config", "-c", default="config_v2.yaml")
    parser.add_argument("--csv", "-i", default=None)
    parser.add_argument("--out-md", "-o", default="clusterer_output.md")
    parser.add_argument("--out-json", "-x", default="clusters_output.json")
    parser.add_argument("--idmap-json", "-m", default="id_to_text.json")
    parser.add_argument("--plots-dir", "-p", default="plots")
    parser.add_argument(
        "--log-raw",
        action="store_true",
        help="Wenn gesetzt, wird der vollständige RAW-LLM-Output zusätzlich im Debug-Log protokolliert."
    )

    args = parser.parse_args(argv)

    # -------------------------------------------------
    # YAML laden
    # -------------------------------------------------
    with open(args.config, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)

    # -------------------------------------------------
    # Pfade aus Config / Kommandozeile
    # -------------------------------------------------
    input_csv = args.csv or config["paths"]["input_csv"]

    # args.out-md hat jetzt standardmäßig bereits
    # den korrekten Namen clusterer_output.md
    output_md = args.out_md

    logger.info(f"[Clusterer] Lade CSV: {input_csv}")

    # -------------------------------------------------
    # CSV laden
    # -------------------------------------------------
    df = pd.read_csv(
        input_csv,
        encoding="utf-8",
        sep=";"
    )

    # -------------------------------------------------
    # LLM-Konfiguration
    # -------------------------------------------------
    llm_cfg = config["llm"]

    ollama_params = {
        "model": llm_cfg["model"],
        "temperature": float(llm_cfg["temperature"]),
        "max_tokens": int(llm_cfg["max_tokens"]),
        "think": llm_cfg.get("think"),
        "log_thinking": bool(llm_cfg.get("log_thinking", False)),
    }

    prompts = config.get("prompts", {})
    context = config.get("context", {})

    # -------------------------------------------------
    # Clusterer ausführen
    # -------------------------------------------------
    md, json_output = run_clustering(
        df=df,
        ollama_params=ollama_params,
        prompts=prompts,
        context=context,
        COL_CODE=config["columns"]["code"],
        COL_SEG=config["columns"]["segment"],
        COL_PERSON=config["columns"]["person"],
        plots_dir=args.plots_dir,
        log_raw=args.log_raw,
        id_to_text_path=args.idmap_json
    )

    # -------------------------------------------------
    # Markdown schreiben
    # -------------------------------------------------
    with open(output_md, "w", encoding="utf-8") as f:
        f.write(md)

    # -------------------------------------------------
    # Cluster-JSON schreiben
    # -------------------------------------------------
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(
            json_output,
            f,
            ensure_ascii=False,
            indent=2
        )

    logger.info(
        f"[Clusterer] Markdown geschrieben nach: {output_md}"
    )

    logger.info(
        f"[Clusterer] Cluster-JSON geschrieben nach: {args.out_json}"
    )

    logger.info(
        f"[Clusterer] Segment-ID/Text-Mapping geschrieben nach: "
        f"{args.idmap_json}"
    )


if __name__ == "__main__":
    main()
