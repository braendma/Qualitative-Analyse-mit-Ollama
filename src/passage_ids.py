"""Deterministic ID preparation from exact MAXQDA locations, with human grouping review."""
import csv
import hashlib
import io
import json
from collections import defaultdict


def prepare(raw, columns):
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')), delimiter=';')
    headers = reader.fieldnames or []
    rows = list(reader)
    for key in ('person', 'segment', 'code'):
        if not columns.get(key) or columns[key] not in headers:
            raise ValueError('Zuerst Person/Dokument, Text und Code einer Spalte zuordnen.')
    if columns.get('unit_id') or any(h in headers for h in ('PassageID', 'Passage-ID', 'unit_id')):
        raise ValueError('Passage-IDs sind bereits vorhanden oder zugeordnet. Bestehende IDs verwenden und prüfen; sie werden nicht ersetzt.')
    start = next((h for h in ('Anfang', 'Start') if h in headers), None)
    end = next((h for h in ('Ende', 'End') if h in headers), None)
    group = next((h for h in ('Dokumentgruppe', 'Document group', 'Document Group') if h in headers), None)
    if not start or not end:
        raise ValueError('Für Passage-Vorschläge fehlen Anfang/Start und Ende/End. MAXQDA mit Positionsspalten exportieren oder den Zeilenvergleich verwenden.')
    grouped = defaultdict(list)
    for index, row in enumerate(rows):
        if any(not row[columns[k]].strip() for k in ('person', 'segment', 'code')):
            raise ValueError(f'Datenzeile {index+2}: Person, Text oder Code fehlt.')
        if row[start].strip() and row[end].strip():
            key = (row.get(group, ''), row[columns['person']], row[start], row[end], row[columns['segment']])
            grouped[key].append(index)
    candidates = []
    for key, indices in grouped.items():
        if len(indices) < 2:
            continue
        codes = [rows[i][columns['code']] for i in indices]
        candidates.append({'id':str(indices[0]), 'rows':[i+2 for i in indices], 'group':key[0],
                           'person':key[1], 'start':key[2], 'end':key[3], 'text':key[4],
                           'codes':codes, 'duplicate_code':len(set(codes)) < len(codes)})
    fingerprint = hashlib.sha256(raw + json.dumps(columns, sort_keys=True).encode()).hexdigest()
    return {'fingerprint':fingerprint, 'count':len(rows), 'candidates':candidates}, headers, rows


def apply(raw, columns, fingerprint, confirmed):
    preview, headers, rows = prepare(raw, columns)
    if fingerprint != preview['fingerprint']:
        raise ValueError('Datei oder Spaltenzuordnung geändert. Passage-Vorschläge erneut laden.')
    available = {c['id']:c for c in preview['candidates']}
    if not isinstance(confirmed, list) or any(not isinstance(c, str) or c not in available for c in confirmed) or len(set(confirmed)) != len(confirmed):
        raise ValueError('Ungültige Auswahl von Passage-Gruppen.')
    ids = ['P'+fingerprint[:10]+'-'+str(i+1).zfill(6) for i in range(len(rows))]
    for cid in confirmed:
        indices = [n-2 for n in available[cid]['rows']]
        for index in indices:
            ids[index] = ids[indices[0]]
    # Keep existing row IDs; otherwise materialize the same kind of unique row ID
    # that the analysis loader already supplies without an explicit ID column.
    row_id = columns.get('segment_id') or next((h for h in ('segment_id','Segment-ID','SegmentID','ID') if h in headers), None)
    generated_row = row_id is None
    if generated_row:
        row_id = 'segment_id'
        headers.append(row_id)
    headers.append('PassageID')
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=headers, delimiter=';', lineterminator='\n')
    writer.writeheader()
    for index, row in enumerate(rows):
        if generated_row:
            row[row_id] = 'Z'+fingerprint[:10]+'-'+str(index+1).zfill(6)
        row['PassageID'] = ids[index]
        writer.writerow(row)
    mapped = {**columns, 'segment_id':row_id, 'unit_id':'PassageID'}
    return output.getvalue().encode('utf-8'), mapped, {'confirmed_groups':confirmed, 'fingerprint':fingerprint,
           'candidates':len(available), 'passages':len(set(ids)), 'rows':len(rows), 'generated_row_ids':generated_row}
