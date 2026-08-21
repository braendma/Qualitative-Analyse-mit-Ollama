# plot_core.py

import matplotlib.pyplot as plt
import numpy as np
import os
import logging
import json

logger = logging.getLogger("clusterer")


def _safe_filename(s: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in s)


def _extract_person_from_segment_id(sid: str) -> str:
    if not isinstance(sid, str) or sid == "":
        return "Unbekannt"
    if "#SEG" in sid:
        return sid.split("#SEG", 1)[0].strip()
    if " " in sid:
        return sid.split(" ", 1)[0].strip()
    return sid.strip()


def _normalize_segment_id(raw_sid):
    """
    Normalisiert einen Segment-Eintrag:
    - Wenn raw_sid ein String ist: return raw_sid
    - Wenn raw_sid ein Dict ist: versuche keys 'id','segment_id','segment'
      ansonsten: return json.dumps(raw_sid, ensure_ascii=False)
    """
    if isinstance(raw_sid, str):
        return raw_sid
    if isinstance(raw_sid, dict):
        for key in ("id", "segment_id", "segment"):
            if key in raw_sid and isinstance(raw_sid[key], str):
                return raw_sid[key]
        # Fallback: wenn dict ein Feld 'text' und 'person' hat, rekonstruiere id
        if "person" in raw_sid and "index" in raw_sid:
            try:
                return f"{raw_sid['person']}#SEG{int(raw_sid['index']):05d}"
            except Exception:
                pass
        # Letzter Fallback: serialisiere das Dict zu einem String
        try:
            return json.dumps(raw_sid, ensure_ascii=False)
        except Exception:
            return str(raw_sid)
    # Sonst: cast to str
    return str(raw_sid)


def plot_clusters(cat,
                  subcat,
                  clusters,
                  df_sub,
                  COL_SEG="Segment",
                  COL_PERSON="Dokumentname",
                  out_dir="plots",
                  sort_by_segments: bool = False,
                  facet=None):
    """
    Erstellt ein Diagramm:
    - Segmentanzahl pro Cluster
    - Einzigartige Personen pro Cluster

    Robust gegen:
    - fehlende 'cluster_name'
    - segments, die als dicts geliefert werden
    """

    if not clusters:
        logger.warning(f"[Plot] Keine Cluster für {cat}/{subcat}.")
        return None

    os.makedirs(out_dir, exist_ok=True)

    # Robust: sichere Cluster-Namen und Segmentlisten extrahieren
    processed = []
    for idx, c in enumerate(clusters):
        name = None
        segs = None
        if isinstance(c, dict):
            name = c.get("cluster_name")
            segs = c.get("segments")
        if not name:
            name = f"Cluster_{idx+1}"
            logger.debug(f"[Plot] Cluster ohne 'cluster_name' gefunden, verwende '{name}'.")
        if not isinstance(segs, list):
            segs = []
            logger.debug(f"[Plot] Cluster '{name}' hat keine gültige 'segments'-Liste; verwende leere Liste.")
        processed.append({"name": name, "segments": segs})

    # Optional sortieren
    if sort_by_segments:
        processed.sort(key=lambda x: len(x["segments"]), reverse=True)

    names = [p["name"] for p in processed]
    segment_counts = [len(p["segments"]) for p in processed]

    # 1) Mapping: SegmentID -> Person anhand von df_sub
    # Wenn der Clusterer die globale Spalte "_SegmentID" mitliefert,
    # wird exakt diese verwendet. Nur als Fallback wird lokal rekonstruiert.
    segment_to_person = {}
    for i, (_, row) in enumerate(df_sub.iterrows()):
        try:
            person = str(row[COL_PERSON])
        except Exception:
            person = "Unbekannt"

        seg_id = ""
        try:
            raw_global_id = row.get("_SegmentID", "")
            if raw_global_id is not None:
                seg_id = str(raw_global_id).strip()
        except Exception:
            seg_id = ""

        if not seg_id:
            seg_id = f"{person}#SEG{str(i).zfill(5)}"

        segment_to_person[seg_id] = person

    # 2) Für jeden Cluster: bestimme die Menge eindeutiger Personen
    person_counts = []
    for p in processed:
        segs = p["segments"]
        persons = set()
        for raw_sid in segs:
            sid = _normalize_segment_id(raw_sid)

            # Direkter Lookup
            if sid in segment_to_person:
                persons.add(segment_to_person[sid])
                continue

            # Fallback: versuche, Person aus sid zu extrahieren
            extracted = _extract_person_from_segment_id(sid)
            if extracted:
                persons.add(extracted)
            else:
                persons.add("Unbekannt")

            # Logge ungewöhnliche Fälle (einmal pro sid)
            if isinstance(raw_sid, dict):
                logger.debug(f"[Plot] Segment-Eintrag war Dict; normalisiert zu '{sid}' (Cluster: {p['name']}).")

        person_counts.append(len(persons))

    # 3) Plot erstellen (horizontal bars)
    x = np.arange(len(names))
    width = 0.4

    plt.figure(figsize=(12, 7))
    plt.barh(x - width/2, segment_counts, height=width, label="Segmente", color="steelblue")
    plt.barh(x + width/2, person_counts, height=width, label="Personen (einzigartig)", color="darkorange")

    plt.yticks(x, names)
    plt.xlabel("Anzahl")
    hierarchy_label = f"{cat} / {subcat}"
    if facet is not None:
        hierarchy_label += f" / {facet}"
    plt.title(f"Clustergrößen – {hierarchy_label}")
    plt.legend()
    plt.tight_layout()

    # 4) Dateiname sicher erzeugen
    safe_cat = _safe_filename(str(cat))
    safe_sub = _safe_filename(str(subcat))

    if facet is not None:
        safe_facet = _safe_filename(str(facet))
        filename = f"{safe_cat}_{safe_sub}_{safe_facet}_clusterdiagramm.png"
    else:
        filename = f"{safe_cat}_{safe_sub}_clusterdiagramm.png"
    filepath = os.path.join(out_dir, filename)

    try:
        plt.savefig(filepath)
        plt.close()
        logger.info(f"[Plot] Diagramm gespeichert: {filepath}")
    except Exception as e:
        logger.exception(f"[Plot] Fehler beim Speichern des Diagramms: {e}")
        try:
            plt.close()
        except Exception:
            pass
        return None

    return filepath
