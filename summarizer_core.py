# summarizer_core.py

import json
import logging
from datetime import datetime

from utils_prompt import build_prompt_for_module
from clusterer_core import ollama_chat

logger = logging.getLogger("summarizer")


def llm_summary(system_prompt: str, user_prompt: str, ollama_params: dict) -> str:
    """LLM-Zusammenfassung mit Debug-Logging und bis zu 3 Versuchen."""

    for attempt in range(3):
        logger.info(f"[Summary-Retry] Versuch {attempt+1}/3")

        logger.debug("\n===== SUMMARY SYSTEM PROMPT =====\n%s\n", system_prompt)
        logger.debug("\n===== SUMMARY USER PROMPT =====\n%s\n", user_prompt)

        content = ollama_chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model=ollama_params["model"],
            temperature=ollama_params["temperature"],
            max_tokens=ollama_params["max_tokens"],
            think=ollama_params.get("think"),
            log_thinking=ollama_params.get("log_thinking", False),
        )

        logger.info("\n===== RAW SUMMARY OUTPUT =====\n%s\n==============================\n", content)

        if not content:
            logger.warning("[Summary-Fehler] Leere LLM-Antwort.")
            continue

        return content.strip()

    logger.error("[Summary-Fehler] Nach 3 Versuchen keine gültige Antwort.")
    return ""


def summarize_clusters(
    cluster_json_path: str,
    id_to_text_path: str,
    ollama_params: dict,
    prompts: dict,
    context: dict
):
    """
    Erzeugt:

      - Markdown als Liste von Zeilen
      - JSON mit Cluster-Summaries
      - Gesamtzusammenfassung

    Erwartete Eingaben:

      clusters_output.json
      id_to_text.json

    Das id_to_text.json enthält:

      {
        "Segment-ID": "Originaler Segmenttext"
      }
    """

    logger.info(
        "[Summarizer] Lade Cluster-JSON…"
    )

    # -------------------------------------------------
    # Cluster-JSON laden
    # -------------------------------------------------
    with open(
        cluster_json_path,
        "r",
        encoding="utf-8"
    ) as f:
        data = json.load(f)

    clusters = data.get(
        "clusters",
        []
    )

    logger.info(
        f"[Summarizer] {len(clusters)} Cluster geladen."
    )

    # -------------------------------------------------
    # Segmenttexte laden
    # -------------------------------------------------
    logger.info(
        "[Summarizer] Lade Segmenttexte…"
    )

    with open(
        id_to_text_path,
        "r",
        encoding="utf-8"
    ) as f:
        id_to_text = json.load(f)

    logger.info(
        f"[Summarizer] "
        f"{len(id_to_text)} Segmenttexte geladen."
    )

    # -------------------------------------------------
    # Cluster-Summaries
    # -------------------------------------------------
    cluster_summaries = []

    # -------------------------------------------------
    # Einzelsummaries
    # -------------------------------------------------
    for index, c in enumerate(clusters, start=1):

        cname = c.get(
            "cluster_name",
            "Unbenannt"
        )

        definition = c.get(
            "definition",
            ""
        )

        seg_ids = c.get(
            "segments",
            []
        )

        # -------------------------------------------------
        # Segmenttexte anhand der IDs auflösen
        # -------------------------------------------------
        quote_lines = []

        for sid in seg_ids:

            text = id_to_text.get(
                sid
            )

            if text is None:

                logger.warning(
                    "[Summarizer] "
                    f"Kein Segmenttext für ID "
                    f"{sid} gefunden."
                )

                text = ""

            quote_lines.append(
                f"- {text}"
            )

        quotes = "\n".join(
            quote_lines
        )

        # -------------------------------------------------
        # Prompt bauen
        # -------------------------------------------------
        system_prompt, user_prompt = (
            build_prompt_for_module(
                "cluster_summary",
                prompts=prompts,
                context=context,
                clusters=json.dumps(
                    c,
                    ensure_ascii=False
                ),
                cluster_name=cname,
                definition=definition,
                quotes=quotes
            )
        )

        logger.info(
            "[Summarizer] "
            f"Erstelle Zusammenfassung "
            f"für Cluster {index}/"
            f"{len(clusters)}: {cname}"
        )

        # -------------------------------------------------
        # LLM
        # -------------------------------------------------
        summary = llm_summary(
            system_prompt,
            user_prompt,
            ollama_params
        )

        # -------------------------------------------------
        # Ergebnis speichern
        # -------------------------------------------------
        cluster_summaries.append({
            "hauptkategorie": c.get(
                "hauptkategorie"
            ),
            "subkategorie": c.get(
                "subkategorie"
            ),
            "facette": c.get(
                "facette"
            ),
            "cluster_name": cname,
            "definition": definition,
            "segments": seg_ids,
            "summary": summary
        })

    # -------------------------------------------------
    # Gesamtsummary vorbereiten
    # -------------------------------------------------
    logger.info(
        "[Summarizer] "
        "Erstelle Gesamtzusammenfassung…"
    )

    cluster_summaries_text = "\n\n".join(
        (
            f"Cluster: {c['cluster_name']}\n"
            f"Definition: {c['definition']}\n"
            f"Zusammenfassung:\n"
            f"{c['summary']}"
        )
        for c in cluster_summaries
    )

    # -------------------------------------------------
    # Gesamt-Prompt
    # -------------------------------------------------
    system_prompt, user_prompt = (
        build_prompt_for_module(
            "category_summary",
            prompts=prompts,
            context=context,
            category="Gesamtanalyse",
            subcats=cluster_summaries_text
        )
    )

    # -------------------------------------------------
    # Gesamtzusammenfassung erzeugen
    # -------------------------------------------------
    final_summary = llm_summary(
        system_prompt,
        user_prompt,
        ollama_params
    )

    # -------------------------------------------------
    # JSON-Output
    # -------------------------------------------------
    json_output = {
        "created_at": datetime.now().isoformat(),
        "cluster_summaries": cluster_summaries,
        "final_summary": final_summary
    }

    # -------------------------------------------------
    # Markdown
    # -------------------------------------------------
    md = []

    md.append(
        "# Zusammenfassung aller Cluster\n"
    )

    md.append(
        f"Erstellt am: "
        f"{json_output['created_at']}\n\n"
    )

    for c in cluster_summaries:

        md.append(
            f"## {c['cluster_name']}\n\n"
        )

        if c["definition"]:

            md.append(
                f"**Definition:** "
                f"{c['definition']}\n\n"
            )

        md.append(
            c["summary"]
            + "\n\n"
        )

    md.append(
        "# Gesamtzusammenfassung\n\n"
    )

    md.append(
        final_summary
        + "\n"
    )

    return md, json_output
