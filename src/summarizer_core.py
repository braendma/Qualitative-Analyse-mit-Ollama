from runtime_support import PartCheckpoint
from progress_events import update_progress
# summarizer_core.py

import json
import logging
from datetime import datetime

from utils_prompt import build_prompt_for_module
from clusterer_core import ollama_chat
from llm_client import LLMResponseError

logger = logging.getLogger("summarizer")


def llm_summary(system_prompt: str, user_prompt: str, ollama_params: dict) -> str:
    """LLM-Zusammenfassung mit Debug-Logging und bis zu 3 Versuchen."""

    from summary_reduction import reduce_prompt
    user_prompt = reduce_prompt(system_prompt, user_prompt, ollama_params, llm_summary)

    for attempt in range(3):
        logger.info(f"[Summary-Retry] Versuch {attempt+1}/3")

        logger.debug("\n===== SUMMARY SYSTEM PROMPT =====\n%s\n", system_prompt)
        logger.debug("\n===== SUMMARY USER PROMPT =====\n%s\n", user_prompt)

        base_limit = int(ollama_params["max_tokens"])
        safe_limit = int(ollama_params.get("num_ctx", 32768)) - len((system_prompt + user_prompt).encode("utf-8")) - 1024
        answer_limit = min(safe_limit, base_limit * (2 ** attempt)) if base_limit <= 600 else base_limit
        try:
            content = ollama_chat(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                model=ollama_params["model"],
                temperature=ollama_params["temperature"],
                max_tokens=answer_limit,
                think=ollama_params.get("think"),
                log_thinking=ollama_params.get("log_thinking", False),
                settings={**ollama_params, "max_tokens": answer_limit},
            )
        except LLMResponseError:
            if attempt == 2:
                raise
            logger.warning("Unvollständige Zusammenfassung; erneuter Versuch mit geprüftem Antwortbudget.")
            continue

        logger.info("\n===== RAW SUMMARY OUTPUT =====\n%s\n==============================\n", content)

        if not content:
            logger.warning("[Summary-Fehler] Leere LLM-Antwort.")
            continue

        return content.strip()

    logger.error("[Summary-Fehler] Nach 3 Versuchen keine gültige Antwort.")
    raise LLMResponseError("Nach drei Versuchen keine vollständige Zusammenfassung.")


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
    total_steps = len(clusters) + 1  # Include the final synthesis, which can take longer.
    update_progress(completed=0, total=total_steps, unit='summaries', phase='cluster_summaries')
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
        summary = PartCheckpoint("summarizer", ollama_params).run(
            [index, c.get("code_path"), cname], {"system":system_prompt,"user":user_prompt},
            lambda: llm_summary(
                system_prompt, user_prompt, ollama_params
            ))

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
            "auspraegung": c.get("auspraegung"),
            "code_path": c.get("code_path"),
            "facette": c.get(
                "facette"
            ),
            "cluster_name": cname,
            "definition": definition,
            "segments": seg_ids,
            "summary": summary
        })
        update_progress(completed=index)

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
    update_progress(phase='overall_summary')
    final_summary = PartCheckpoint("summarizer", ollama_params).run(
        'overall', {"system":system_prompt,"user":user_prompt},
        lambda: llm_summary(
            system_prompt, user_prompt, ollama_params
        ))

    # -------------------------------------------------
    # JSON-Output
    # -------------------------------------------------
    update_progress(completed=total_steps)
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
