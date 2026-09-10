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
        processed.append({"name": name, "segments": list(dict.fromkeys(_normalize_segment_id(s) for s in segs))})

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
        missing = False
        for raw_sid in segs:
            sid = _normalize_segment_id(raw_sid)
            person = segment_to_person.get(sid)
            if person and person not in ('Unbekannt','nan','None'):
                persons.add(person)
            else:
                missing = True
        person_counts.append(None if missing else len(persons))

    # Shared, readable style with direct integer labels and wrapped category names.
    import textwrap
    from matplotlib.patches import Patch
    from matplotlib.ticker import MaxNLocator
    labels = ['\n'.join(textwrap.wrap(str(name), 32)) for name in names]
    units = [max(1.0, .34 * (label.count('\n') + 1) + .35) for label in labels]
    height = max(4.8, 2.5 + sum(units) * .85)
    fig = plt.figure(figsize=(11.4, height), facecolor='white')
    teal, copper, ink, muted = '#197b80', '#b87540', '#203b3b', '#627572'
    hierarchy = '  ›  '.join(str(x) for x in (cat, subcat, facet) if x is not None and str(x).strip())
    heading = '\n'.join(textwrap.wrap(hierarchy, 102))
    top = 1.25 + .18 * (heading.count('\n'))
    fig.text(.045, 1-.30/height, 'Clustergrößen', fontsize=22, color=ink, weight='bold', va='top')
    fig.text(.045, 1-.78/height, heading, fontsize=11, color=muted, va='top')
    fig.legend(handles=[Patch(facecolor=teal,label='Codierzeilen'),
                        Patch(facecolor='white',edgecolor=copper,linewidth=1.7,label='Personen (eindeutig je Cluster)')],
               loc='upper left',bbox_to_anchor=(.038,1-top/height),frameon=False,ncol=2,fontsize=10)
    ax=fig.add_axes([.39,.85/height,.535,(height-top-1.45)/height])
    positions=[];position=0
    for unit in units: positions.append(position+unit/2);position+=unit
    maximum=max(segment_counts+ [n for n in person_counts if n is not None]+[1])
    for y,n,persons in zip(positions,segment_counts,person_counts):
        ax.barh(y-.13,n,height=.20,color=teal,zorder=3)
        ax.text(n+maximum*.025,y-.13,str(n),va='center',fontsize=11,weight='bold',color=teal)
        if persons is not None:
            ax.barh(y+.13,persons,height=.20,facecolor='white',edgecolor=copper,linewidth=1.7,zorder=3)
        ax.text((persons or 0)+maximum*.025,y+.13,str(persons) if persons is not None else 'nicht bestimmbar',va='center',fontsize=10,color=copper)
    ax.set_yticks(positions,labels,fontsize=11,color=ink)
    ax.tick_params(axis='y',length=0,pad=18);ax.tick_params(axis='x',length=0,pad=8,colors=muted)
    ax.set_xlim(0,maximum*1.18);ax.set_ylim(position,0)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True,nbins=5))
    ax.set_axisbelow(True);ax.grid(axis='x',color='#e2eae7',linewidth=.8)
    for spine in ax.spines.values():spine.set_visible(False)
    ax.set_xlabel('Anzahl',color=muted,labelpad=8,fontsize=10)
    note='Eine Person kann in mehreren Clustern vorkommen. Die Häufigkeit zeigt keine inhaltliche Wichtigkeit.'
    if any(n is None for n in person_counts):note+=' Fehlende Zuordnung: Personenzahl unbekannt.'
    fig.text(.045,.18/height,'\n'.join(textwrap.wrap(note,125)),fontsize=9,color=muted,va='bottom')

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
        fig.savefig(filepath, dpi=160, facecolor="white", bbox_inches="tight")
        fig.savefig(os.path.splitext(filepath)[0]+".svg", format="svg", facecolor="white", bbox_inches="tight")
        plt.close(fig)
        logger.info(f"[Plot] Diagramm gespeichert: {filepath}")
    except Exception as e:
        logger.exception(f"[Plot] Fehler beim Speichern des Diagramms: {e}")
        try:
            plt.close(fig)
        except Exception:
            pass
        return None

    return filepath

