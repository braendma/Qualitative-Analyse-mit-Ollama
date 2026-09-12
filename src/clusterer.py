#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import yaml
import logging
from project_paths import DEFAULT_CONFIG
import argparse
import json
from runtime_support import atomic_json, atomic_text
import pandas as pd

from clusterer_core import run_clustering
from coding_validation_common import load_codebook, resolve_config_path

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


from progress_events import track_module

@track_module
def main(argv=None):
    parser = argparse.ArgumentParser(description="LLM-Clusterer")

    parser.add_argument("--config", "-c", default=str(DEFAULT_CONFIG))
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
    input_csv = args.csv or str(resolve_config_path(args.config, None, config["paths"]["input_csv"]))

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
        sep=";", dtype=str, keep_default_na=False
    )

    # -------------------------------------------------
    # LLM-Konfiguration
    # -------------------------------------------------
    llm_cfg = config["llm"]

    ollama_params = {
        **llm_cfg,
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
        id_to_text_path=args.idmap_json,
        codebook=load_codebook(resolve_config_path(args.config, None, config["paths"]["category_system_csv"]))[1],
        columns_config=config.get("columns", {})
    )

    # -------------------------------------------------
    # Markdown schreiben
    # -------------------------------------------------
    atomic_text(output_md, md)

    # -------------------------------------------------
    # Cluster-JSON schreiben
    # -------------------------------------------------
    atomic_json(args.out_json, json_output)

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

