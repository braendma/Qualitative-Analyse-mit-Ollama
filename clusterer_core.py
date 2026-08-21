# clusterer_core.py

import json
import logging
import os
from datetime import datetime

import pandas as pd
import ollama

from utils_prompt import build_prompt_for_module
from plot_core import plot_clusters


logger = logging.getLogger("clusterer")


# -----------------------------------------------------
# JSON-Extraktion aus Text
# -----------------------------------------------------
def extract_json_from_text(text):
    """
    Versucht, das erste gültige JSON-Array oder -Objekt
    aus einem Textblock zu extrahieren.

    Vorgehen:
      1. Erste öffnende '[' oder '{' suchen.
      2. Mögliche schließende ']' oder '}' von hinten testen.
      3. Erfolgreiches json.loads zurückgeben.

    Dadurch können auch LLM-Antworten verarbeitet werden,
    die nach dem JSON noch zusätzlichen Text enthalten.
    """

    if not text or not isinstance(text, str):
        return None

    idx_bracket = text.find("[")
    idx_brace = text.find("{")

    starts = [
        i
        for i in (idx_bracket, idx_brace)
        if i != -1
    ]

    if not starts:
        return None

    start = min(starts)

    candidates = [
        i
        for i, ch in enumerate(text)
        if ch in ("]", "}")
        and i >= start
    ]

    for end in reversed(candidates):

        substr = text[
            start:end + 1
        ]

        try:
            return json.loads(substr)
        except Exception:
            continue

    return None


# -----------------------------------------------------
# Robuster JSON Loader
# -----------------------------------------------------
def safe_json_loads(text, fallback=None):
    """
    Versucht zuerst direktes JSON-Parsing.

    Falls das fehlschlägt, wird JSON aus einem
    umgebenden LLM-Text extrahiert.
    """

    if not text or not isinstance(text, str):
        return fallback

    try:
        return json.loads(text)

    except Exception:

        extracted = extract_json_from_text(
            text
        )

        if extracted is not None:
            return extracted

        return fallback


# -----------------------------------------------------
# Ollama Chat Wrapper
# -----------------------------------------------------
def ollama_chat(
    messages,
    model,
    temperature,
    max_tokens
):
    """
    Zentraler Ollama-Wrapper.
    """

    try:

        response = ollama.chat(
            model=model,
            messages=messages,
            options={
                "temperature": temperature,
                "num_predict": max_tokens
            }
        )

        return response[
            "message"
        ][
            "content"
        ]

    except Exception as e:

        logger.error(
            f"[Ollama] Fehler beim Chat-Request: {e}"
        )

        return ""


# -----------------------------------------------------
# LLM-Clustering
# -----------------------------------------------------
def llm_cluster(
    system_prompt: str,
    user_prompt: str,
    ollama_params: dict
) -> str:
    """
    Führt das Clustering-LLM mit bis zu drei
    Versuchen aus.
    """

    for attempt in range(3):

        logger.info(
            f"[Cluster-Retry] Versuch "
            f"{attempt + 1}/3"
        )

        content = ollama_chat(
            [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
            model=ollama_params["model"],
            temperature=ollama_params["temperature"],
            max_tokens=ollama_params["max_tokens"]
        )

        if content:
            return content.strip()

    logger.error(
        "[Cluster-Fehler] Keine gültige Antwort "
        "nach 3 Versuchen."
    )

    return ""


# -----------------------------------------------------
# Self-Repair
# -----------------------------------------------------
def llm_self_repair(
    system_prompt: str,
    user_prompt: str,
    ollama_params: dict
) -> str:
    """
    Versucht eine fehlerhafte LLM-Antwort
    bis zu drei Mal reparieren zu lassen.
    """

    for attempt in range(3):

        logger.info(
            f"[Repair-Retry] Versuch "
            f"{attempt + 1}/3"
        )

        content = ollama_chat(
            [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
            model=ollama_params["model"],
            temperature=ollama_params["temperature"],
            max_tokens=ollama_params["max_tokens"]
        )

        if content:
            return content.strip()

    logger.error(
        "[Repair-Fehler] Keine gültige Antwort "
        "nach 3 Versuchen."
    )

    return ""


# -----------------------------------------------------
# Code-Hierarchie robust zerlegen
# -----------------------------------------------------
def split_code_path(code_string):
    """
    Zerlegt beispielsweise:

        A > B > C

    in:

        Hauptkategorie = A
        Subkategorie   = B
        Facette         = C
    """

    if not isinstance(
        code_string,
        str
    ):
        return (
            "Unkategorisiert",
            None,
            None
        )

    code_string = code_string.strip()

    if code_string == "":
        return (
            "Unkategorisiert",
            None,
            None
        )

    parts = [
        p.strip()
        for p in code_string.split(">")
    ]

    if len(parts) == 1:

        return (
            parts[0],
            None,
            None
        )

    elif len(parts) == 2:

        return (
            parts[0],
            parts[1],
            None
        )

    else:

        return (
            parts[0],
            parts[1],
            parts[2]
        )


# -----------------------------------------------------
# Segment-ID normalisieren
# -----------------------------------------------------
def normalize_segment_id(segment):
    """
    Normalisiert eine Segmentangabe.

    Erwartete Varianten:

        "Person#SEG00001"

    oder:

        {
            "id": "Person#SEG00001",
            "text": "..."
        }

    oder:

        {
            "segment_id": "Person#SEG00001"
        }

    oder:

        {
            "ID": "Person#SEG00001"
        }

    Rückgabe:
        String oder None
    """

    if isinstance(
        segment,
        dict
    ):

        segment_id = (
            segment.get("id")
            or segment.get("segment_id")
            or segment.get("ID")
        )

        if segment_id is None:
            return None

        return str(
            segment_id
        ).strip()

    if segment is None:
        return None

    return str(
        segment
    ).strip()


# -----------------------------------------------------
# Cluster-Segmente normalisieren
# -----------------------------------------------------
def normalize_clusters(clusters):
    """
    Normalisiert die Segmentangaben aller Cluster.

    Nach dieser Funktion gilt garantiert:

        cluster["segments"]

    ist immer eine Liste von Strings.

    Dadurch bleibt der Cluster-Output kompatibel
    mit Summarizer und SWOT.
    """

    normalized_clusters = []

    if not isinstance(
        clusters,
        list
    ):
        return normalized_clusters

    for cluster in clusters:

        if not isinstance(
            cluster,
            dict
        ):

            logger.warning(
                "[Clusterer] Überspringe "
                f"ungültiges Cluster: {cluster!r}"
            )

            continue

        raw_segments = cluster.get(
            "segments",
            []
        )

        if not isinstance(
            raw_segments,
            list
        ):

            logger.warning(
                "[Clusterer] 'segments' ist "
                "keine Liste im Cluster "
                f"{cluster.get('cluster_name', 'Unbenannt')}"
            )

            raw_segments = []

        normalized_segments = []

        for segment in raw_segments:

            segment_id = normalize_segment_id(
                segment
            )

            if segment_id:

                normalized_segments.append(
                    segment_id
                )

            else:

                logger.warning(
                    "[Clusterer] "
                    "Segment ohne gültige ID "
                    f"übersprungen: {segment!r}"
                )

        cluster["segments"] = (
            normalized_segments
        )

        normalized_clusters.append(
            cluster
        )

    return normalized_clusters


# -----------------------------------------------------
# Hauptfunktion: Clustering pro Facette
# -----------------------------------------------------

# -----------------------------------------------------
# Segment-IDs gegen aktuellen LLM-Input validieren
# -----------------------------------------------------
def validate_cluster_segment_ids(clusters, allowed_ids):
    """Entfernt erfundene/fremde Segment-IDs aus LLM-Clustern.

    Nur IDs, die für den aktuell analysierten Codepfad tatsächlich an das
    LLM übergeben wurden, dürfen in den Cluster-Output gelangen. Leere
    Cluster werden anschließend verworfen.
    """
    allowed = {str(x).strip() for x in allowed_ids if str(x).strip()}
    validated = []

    for cluster in clusters if isinstance(clusters, list) else []:
        if not isinstance(cluster, dict):
            continue
        valid_segments = []
        for sid in cluster.get("segments", []) or []:
            sid = str(sid).strip()
            if sid in allowed:
                if sid not in valid_segments:
                    valid_segments.append(sid)
            else:
                logger.warning(
                    "[Clusterer] Nicht gelieferte Segment-ID verworfen: %s",
                    sid,
                )
        if not valid_segments:
            logger.warning(
                "[Clusterer] Cluster ohne gültige Segmente verworfen: %s",
                cluster.get("cluster_name", "Unbenannt"),
            )
            continue
        cluster["segments"] = valid_segments
        validated.append(cluster)

    return validated

def run_clustering(
    df: pd.DataFrame,
    ollama_params: dict,
    prompts: dict,
    context: dict,
    COL_CODE="Code",
    COL_SEG="Segment",
    COL_PERSON="Dokumentname",
    plots_dir="plots",
    log_raw: bool = False,
    id_to_text_path: str = "id_to_text.json"
):
    """
    Führt die komplette Clustering-Pipeline aus.

    Erzeugt:

      1. Markdown-Report
      2. Cluster-JSON-Objekt
      3. id_to_text.json

    Das Segment-Mapping hat die Form:

        {
            "Person#SEG00001": "Originaltext ..."
        }

    Die clusters_output-Struktur enthält bei
    'segments' ausschließlich Segment-IDs als Strings.
    """

    logger.info(
        "[Clusterer] Starte Clustering-Pipeline…"
    )

    # -------------------------------------------------
    # Plot-Verzeichnis sicherstellen
    # -------------------------------------------------
    os.makedirs(
        plots_dir,
        exist_ok=True
    )

    # -------------------------------------------------
    # Arbeitskopie + stabiler globaler Zeilenindex
    # -------------------------------------------------
    # Die Segment-ID darf NICHT pro Facette neu bei SEG00000 beginnen.
    # Deshalb wird der DataFrame einmal global neu indiziert und jede
    # Zeile erhält genau eine feste Segment-ID für den gesamten Lauf.
    df = df.copy().reset_index(drop=True)

    # -------------------------------------------------
    # Code-Spalte als String
    # -------------------------------------------------
    df[COL_CODE] = (
        df[COL_CODE]
        .astype(str)
    )

    # -------------------------------------------------
    # Globale Segment-IDs erzeugen
    # -------------------------------------------------
    df["_SegmentID"] = [
        f"{str(person).strip()}#SEG{idx:05d}"
        for idx, person in enumerate(df[COL_PERSON])
    ]

    # -------------------------------------------------
    # Code-Hierarchie
    # -------------------------------------------------
    df[
        "Hauptkategorie"
    ], df[
        "Subkategorie"
    ], df[
        "Facette"
    ] = zip(
        *df[
            COL_CODE
        ].apply(
            split_code_path
        )
    )

    # -------------------------------------------------
    # Nur vollständige 3-stufige Pfade werden geclustert.
    # Gruppiert wird nach dem KOMPLETTEN Hierarchiepfad, nicht nur
    # nach dem Facettennamen. So bleiben gleichnamige Facetten unter
    # verschiedenen Haupt-/Subkategorien strikt getrennt.
    # -------------------------------------------------
    df_clusterable = df[df["Facette"].notna()].copy()

    grouped_facets = df_clusterable.groupby(
        ["Hauptkategorie", "Subkategorie", "Facette"],
        sort=True,
        dropna=False
    )

    # -------------------------------------------------
    # Output
    # -------------------------------------------------
    output = {
        "created_at": datetime.now().isoformat(),
        "clusters": [],
        "plots": {}
    }

    # -------------------------------------------------
    # Globales Segment-Mapping
    # -------------------------------------------------
    # Das Mapping wird EINMAL für den gesamten DataFrame aufgebaut.
    # Damit sind alle IDs eindeutig und können nicht zwischen Facetten
    # gegenseitig überschrieben werden.
    id_to_text = {
        str(row["_SegmentID"]): str(row[COL_SEG])
        for _, row in df.iterrows()
    }

    # -------------------------------------------------
    # Markdown
    # -------------------------------------------------
    md_lines = [
        "# Clusteranalyse\n"
    ]

    md_lines.append(
        f"Erstellt am: "
        f"{output['created_at']}\n\n"
    )

    md_lines.append(
        "## LLM-Konfiguration\n"
    )

    md_lines.append(
        f"- Modell: "
        f"**{ollama_params['model']}**\n"
    )

    md_lines.append(
        f"- Temperatur: "
        f"**{ollama_params['temperature']}**\n"
    )

    md_lines.append(
        f"- Max Tokens: "
        f"**{ollama_params['max_tokens']}**\n\n"
    )

    # -------------------------------------------------
    # Jede eindeutige Kombination aus Hauptkategorie,
    # Subkategorie und Facette clustern
    # -------------------------------------------------
    for (haupt, sub, facette), df_facet in grouped_facets:

        # Lokalen Index darf man für Iteration zurücksetzen; die globale
        # Segment-ID bleibt als eigene Spalte erhalten.
        df_facet = df_facet.reset_index(drop=True)

        if df_facet.empty:
            continue

        # -------------------------------------------------
        # Markdown-Kontext
        # -------------------------------------------------
        md_lines.append(
            f"# {haupt} → "
            f"{sub} → "
            f"{facette}\n\n"
        )

        md_lines.append(
            "### Kontext der Analyse\n"
        )

        md_lines.append(
            f"- Hauptkategorie: "
            f"**{haupt}**\n"
        )

        md_lines.append(
            f"- Subkategorie: "
            f"**{sub}**\n"
        )

        md_lines.append(
            f"- Facette: "
            f"**{facette}**\n\n"
        )

        # -------------------------------------------------
        # Segmente für LLM erzeugen
        # -------------------------------------------------
        segments_payload = []

        for _, row in df_facet.iterrows():

            # Bereits global erzeugte, stabile Segment-ID übernehmen.
            seg_id = str(
                row["_SegmentID"]
            )

            text = str(
                row[COL_SEG]
            )

            person = str(
                row[COL_PERSON]
            )

            segments_payload.append({
                "id": seg_id,
                "text": text,
                "person": person
            })

        # -------------------------------------------------
        # Prompt
        # -------------------------------------------------
        system_prompt, user_prompt = (
            build_prompt_for_module(
                "cluster_analysis",
                prompts=prompts,
                context=context,
                subcat=facette,
                facets=(
                    f"{haupt} > "
                    f"{sub} > "
                    f"{facette}"
                ),
                segments=json.dumps(
                    segments_payload,
                    ensure_ascii=False
                ),
                json_schema=prompts[
                    "json_schema"
                ]
            )
        )

        # -------------------------------------------------
        # LLM
        # -------------------------------------------------
        raw_clusters = llm_cluster(
            system_prompt,
            user_prompt,
            ollama_params
        )

        # -------------------------------------------------
        # RAW Logging
        # -------------------------------------------------
        try:

            preview = (
                raw_clusters
                if raw_clusters is not None
                else ""
            )

            if len(preview) > 2000:

                preview_short = (
                    preview[:2000]
                    + "...(truncated)"
                )

            else:

                preview_short = preview

            logger.debug(
                "[LLM RAW PREVIEW] "
                f"Haupt: {haupt} | "
                f"Sub: {sub} | "
                f"Facette: {facette} | "
                f"Preview: {preview_short}"
            )

            if log_raw:

                logger.debug(
                    "[LLM RAW FULL] "
                    f"Haupt: {haupt} | "
                    f"Sub: {sub} | "
                    f"Facette: {facette} | "
                    "FullOutputStart\n"
                    f"{raw_clusters}\n"
                    "FullOutputEnd"
                )

        except Exception as e:

            logger.exception(
                "[LLM RAW] Fehler beim "
                f"Loggen der Rohantwort: {e}"
            )

        # -------------------------------------------------
        # JSON parsen
        # -------------------------------------------------
        clusters_json = safe_json_loads(
            raw_clusters
        )

        # -------------------------------------------------
        # Self-Repair
        # -------------------------------------------------
        if clusters_json is None:

            logger.error(
                "[Clusterer] "
                "JSON-Parsing fehlgeschlagen "
                f"für Facette {facette}, "
                "starte Self-Repair."
            )

            repair_system, repair_user = (
                build_prompt_for_module(
                    "self_repair",
                    prompts=prompts,
                    context=context,
                    segments=json.dumps(
                        segments_payload,
                        ensure_ascii=False
                    ),
                    clusters=raw_clusters
                )
            )

            repaired = llm_self_repair(
                repair_system,
                repair_user,
                ollama_params
            )

            clusters_json = safe_json_loads(
                repaired
            )

        # -------------------------------------------------
        # Kein gültiges JSON
        # -------------------------------------------------
        if clusters_json is None:

            logger.error(
                "[Clusterer] "
                "Self-Repair lieferte "
                "ebenfalls kein gültiges "
                f"JSON für Facette {facette}."
            )

            clusters_json = []

        # -------------------------------------------------
        # JSON-Struktur erkennen
        # -------------------------------------------------
        if (
            isinstance(
                clusters_json,
                dict
            )
            and "clusters" in clusters_json
        ):

            clusters = (
                clusters_json[
                    "clusters"
                ]
            )

        elif isinstance(
            clusters_json,
            list
        ):

            clusters = clusters_json

        else:

            logger.error(
                "[Clusterer] "
                "Unerwartetes JSON-Format "
                f"für Facette {facette}."
            )

            clusters = []

        # -------------------------------------------------
        # WICHTIG:
        # Segmentangaben normalisieren
        # -------------------------------------------------
        clusters = normalize_clusters(
            clusters
        )

        # -------------------------------------------------
        # Nur tatsächlich gelieferte Segment-IDs zulassen
        # -------------------------------------------------
        clusters = validate_cluster_segment_ids(
            clusters,
            [segment["id"] for segment in segments_payload]
        )

        # -------------------------------------------------
        # Plot
        # -------------------------------------------------
        plot_path = plot_clusters(
            haupt,
            sub,
            clusters,
            df_facet,
            COL_SEG=COL_SEG,
            COL_PERSON=COL_PERSON,
            out_dir=plots_dir,
            facet=facette
        )

        if plot_path:

            plot_key = (
                f"{haupt} > {sub} > {facette}"
            )

            output[
                "plots"
            ][plot_key] = plot_path

        # -------------------------------------------------
        # Markdown Cluster
        # -------------------------------------------------
        md_lines.append(
            f"## Cluster für Facette: "
            f"{facette}\n\n"
        )

        if plot_path:

            md_lines.append(
                f"![Clusterdiagramm]"
                f"({plot_path})\n\n"
            )

        md_lines.append(
            "---\n\n"
        )

        # -------------------------------------------------
        # Cluster ausgeben
        # -------------------------------------------------
        for cluster in clusters:

            cname = cluster.get(
                "cluster_name",
                "Unbenannt"
            )

            definition = cluster.get(
                "definition",
                ""
            )

            seg_ids = cluster.get(
                "segments",
                []
            )

            # -------------------------------------------------
            # Cluster-Überschrift
            # -------------------------------------------------
            md_lines.append(
                f"### Cluster: "
                f"{cname}\n\n"
            )

            md_lines.append(
                f"**Definition:** "
                f"{definition}\n\n"
            )

            md_lines.append(
                "**Segmente:**\n\n"
            )

            # -------------------------------------------------
            # Segmenttexte
            # -------------------------------------------------
            for segment_id in seg_ids:

                # Durch normalize_clusters()
                # ist segment_id hier garantiert
                # ein String.
                segment_text = (
                    id_to_text.get(
                        segment_id,
                        ""
                    )
                )

                md_lines.append(
                    f"#### {segment_id}\n\n"
                )

                if segment_text:

                    md_lines.append(
                        f"> {segment_text}\n\n"
                    )

                else:

                    md_lines.append(
                        "> **Segmenttext "
                        "nicht gefunden.**\n\n"
                    )

            # -------------------------------------------------
            # Cluster-JSON
            # -------------------------------------------------
            output[
                "clusters"
            ].append({
                "hauptkategorie": haupt,
                "subkategorie": sub,
                "facette": facette,
                "cluster_name": cname,
                "definition": definition,
                "segments": seg_ids,
                "plot": plot_path
            })

    # -------------------------------------------------
    # id_to_text.json schreiben
    # -------------------------------------------------
    try:

        absolute_idmap_path = os.path.abspath(
            id_to_text_path
        )

        idmap_dir = os.path.dirname(
            absolute_idmap_path
        )

        if idmap_dir:

            os.makedirs(
                idmap_dir,
                exist_ok=True
            )

        with open(
            absolute_idmap_path,
            "w",
            encoding="utf-8"
        ) as fh:

            json.dump(
                id_to_text,
                fh,
                ensure_ascii=False,
                indent=2
            )

        logger.info(
            "[Clusterer] "
            "Segment-ID/Text-Mapping "
            f"geschrieben: "
            f"{absolute_idmap_path}"
        )

    except Exception as e:

        logger.exception(
            "[Clusterer] Fehler beim "
            f"Schreiben von id_to_text: {e}"
        )

    # -------------------------------------------------
    # Markdown zusammensetzen
    # -------------------------------------------------
    md = "\n".join(
        md_lines
    )

    return md, output