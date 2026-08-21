# utils_csv.py
# Robustes Einlesen von MAXQDA-CSV

import os
import io
import pandas as pd


def read_segments_from_csv(csv_path: str) -> tuple[list[dict], dict]:
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(csv_path)

    try:
        raw = open(csv_path, "r", encoding="utf-8").read()
    except UnicodeDecodeError:
        raw = open(csv_path, "r", encoding="latin1").read()

    raw = raw.replace('""', '"').replace("\r\n", "\n")

    try:
        df = pd.read_csv(io.StringIO(raw), sep=";", engine="python", dtype=str, on_bad_lines="skip").fillna("")
    except Exception:
        df = pd.read_csv(io.StringIO(raw), sep=",", engine="python", dtype=str, on_bad_lines="skip").fillna("")

    # Wichtige Spalten
    if "Dokumentname" not in df.columns:
        raise ValueError(f"Spalte 'Dokumentname' fehlt im CSV! Gefunden: {df.columns.tolist()}")

    if "Segment" not in df.columns:
        raise ValueError(f"Spalte 'Segment' fehlt im CSV! Gefunden: {df.columns.tolist()}")

    segments = []
    id_to_text = {}

    for idx, row in df.iterrows():
        docname = str(row.get("Dokumentname", "")).strip()
        text = str(row.get("Segment", "")).strip()
        person = str(row.get("Bearbeitet von", "")).strip() if "Bearbeitet von" in df.columns else ""

        # KORREKTE SegmentID
        sid = f"{docname}#SEG{idx:05d}"

        segments.append({
            "SegmentID": sid,
            "text": text,
            "person": person
        })
        id_to_text[sid] = text

    return segments, id_to_text
