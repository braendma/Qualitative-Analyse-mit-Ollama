"""Explicit source-document to analysis-person assignments, without guessing identities."""
import csv
import hashlib
import io
import json
import re
from collections import Counter


def _hash(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest()


def preview(raw, columns):
    columns={k:str(columns.get(k) or '').strip() or None for k in ('segment','person','code','segment_id','unit_id')}
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')),delimiter=';')
    rows=list(reader);headers=reader.fieldnames or []
    column=columns.get('person')
    if column not in headers:raise ValueError('Zuerst die Dokument-/Personenspalte zuordnen.')
    if not rows:raise ValueError('Keine Interviewzeilen vorhanden.')
    counts=Counter(str(row[column]).strip() for row in rows)
    if '' in counts:raise ValueError('Leere Dokument-/Personenkennung vorhanden.')
    fingerprint=_hash({'input_sha256':hashlib.sha256(raw).hexdigest(),'columns':columns})
    return {'fingerprint':fingerprint,'document_count':len(counts),'row_count':len(rows),
        'documents':[{'document':name,'rows':count} for name,count in counts.items()]}


def apply(raw, columns, assignment):
    info=preview(raw,columns)
    if not isinstance(assignment,dict) or assignment.get('confirmed') is not True:
        raise ValueError('Personenzuordnung prüfen und ausdrücklich bestätigen, bevor ein Lauf startet.')
    if assignment.get('fingerprint')!=info['fingerprint']:
        raise ValueError('Datei oder Spalten geändert. Personenzuordnung erneut prüfen und bestätigen.')
    mapping=assignment.get('mapping')
    if not isinstance(mapping,dict) or set(mapping)!={d['document'] for d in info['documents']}:
        raise ValueError('Jedem Dokument muss genau eine Personenkennung zugeordnet sein.')
    if any(not isinstance(v,str) or not v.strip() or len(v)>200 or any(ord(c)<32 for c in v) for v in mapping.values()):
        raise ValueError('Personenkennungen müssen nichtleere Texte mit höchstens 200 Zeichen sein.')
    mapping={k:v.strip() for k,v in mapping.items()}
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')),delimiter=';');rows=list(reader)
    headers=list(reader.fieldnames)
    def fresh(base):
        value=base
        while value in headers:value+='_'
        headers.append(value)
        return value
    person_column=fresh('Analyse_PersonID')
    # Preserve supplied IDs or exactly reproduce the pre-assignment ID algorithm.
    from coding_validation_common import segments_from_frame
    import pandas as pd
    original=segments_from_frame(pd.DataFrame(rows),columns)
    id_column=fresh('Analyse_SegmentID')
    for row,segment in zip(rows,original):
        row[person_column]=mapping[str(row[columns['person']]).strip()]
        row[id_column]=segment.segment_id
    out=io.StringIO(newline='');writer=csv.DictWriter(out,fieldnames=headers,delimiter=';',lineterminator='\n')
    writer.writeheader();writer.writerows(rows);normalized=out.getvalue().encode('utf-8')
    configured={**columns,'person':person_column,'segment_id':id_column}
    receipt={'version':1,'confirmed':True,'source_fingerprint':info['fingerprint'],
        'source_sha256':hashlib.sha256(raw).hexdigest(),'normalized_sha256':hashlib.sha256(normalized).hexdigest(),
        'source_column':columns['person'],'person_column':person_column,'mapping':mapping,
        'document_count':info['document_count'],'person_count':len(set(mapping.values())),'row_count':len(rows)}
    return normalized,configured,receipt


def verify(raw,columns,receipt):
    if not isinstance(receipt,dict) or receipt.get('confirmed') is not True:
        raise ValueError('Personenzuordnung fehlt. Unter Eingaben prüfen die Dokumente Personen zuordnen und bestätigen.')
    if hashlib.sha256(raw).hexdigest()!=receipt.get('normalized_sha256') or columns.get('person')!=receipt.get('person_column'):
        raise ValueError('Bestätigte Personenzuordnung passt nicht mehr zur Eingabe. Erneut prüfen.')
    rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig')),delimiter=';'))
    mapping=receipt.get('mapping',{});source=receipt.get('source_column');person=receipt.get('person_column')
    if not rows or any(mapping.get(str(r.get(source,'')).strip())!=r.get(person) for r in rows):
        raise ValueError('Personenkennungen weichen von der bestätigten Dokumentzuordnung ab.')
    if len(rows)!=receipt.get('row_count') or len({r[person] for r in rows})!=receipt.get('person_count'):
        raise ValueError('Personenzahl oder Zeilenzahl stimmt nicht mit der Bestätigung überein.')
    return receipt['person_count']


def possible_split_documents(values):
    """Warning only: never apply inferred grouping to any study."""
    groups={}
    for value in set(values):
        match=re.match(r'^(.+?)[_-](\d+)(?:\s|$)',value)
        if match:groups.setdefault(match[1],set()).add(value)
    return any(len(group)>1 for group in groups.values())
