"""Shared counting material; explicit passages and confirmed people, never guesses."""
import csv
import io
import hashlib
from pathlib import Path
import re

import yaml

from coding_validation_common import load_codebook, load_segments, resolve_config_path
from coverage_core import material_units
from diagnostic_sources import make_snapshot, load_input_context
from person_identity import verify
from runtime_support import file_hash, fingerprint

HASH_FIELDS = {'input_sha256', 'config_sha256', 'codebook_sha256', 'person_identity_sha256'}


def build_material(segments, *, person_basis='unconfirmed', provenance=None):
    """Pure adapter for already loaded segments. Confirmation is an upstream contract.

    Use load_counting_material for files: only it verifies the saved confirmation.
    Missing explicit passage IDs remain coding rows; identical texts stay separate.
    """
    if person_basis not in ('confirmed', 'unconfirmed'):
        raise ValueError('Unbekannte Grundlage der Personenzählung.')
    segments = list(segments)
    for row in segments:
        for field in ('segment_id', 'person', 'human_code', 'text'):
            value = getattr(row, field, None)
            if not isinstance(value, str) or not value.strip():
                raise ValueError('Zählgrundlage benötigt eindeutige Kennungen, Personen, Codes und Originaltexte.')
        if row.unit_id is not None and (not isinstance(row.unit_id, str) or not row.unit_id.strip()):
            raise ValueError('Eine vorhandene Passage-ID darf nicht leer sein.')
    source = dict(provenance or {})
    if set(source) - HASH_FIELDS or any(not isinstance(v, str) or not re.fullmatch(r'[a-f0-9]{64}', v) for v in source.values()):
        raise ValueError('Ungültige Herkunftsnachweise der Zählgrundlage.')
    snapshot = make_snapshot(segments, {})
    grouped = material_units(snapshot['inputs'])
    by_id = {s.segment_id:s for s in segments}
    units = {}
    for (kind, identifier), members in sorted(grouped.items()):
        kind = 'passage' if kind == 'passage' else 'coding_row'
        uid = kind + ':' + identifier
        row = by_id[members[0]]
        units[uid] = {'kind':kind, 'person':row.person, 'text':row.text,
            'segment_ids':sorted(members), 'code_paths':sorted({by_id[s].human_code for s in members})}
    people = sorted({s.person for s in segments})
    material = {'schema_version':1, 'person_basis':person_basis, 'persons':people,
        'units':units, 'provenance':source,
        'segment_index':{sid:{'unit_id':uid,'code_path':by_id[sid].human_code}
            for uid,row in units.items() for sid in row['segment_ids']},
        'unit_basis':'explicit_passages' if all(u['kind']=='passage' for u in units.values()) else 'coding_rows_or_mixed',
        'scope':'exported_coded_material',
        'counts':{'coding_rows':len(segments), 'material_units':len(units),
            'passages':len(units) if all(u['kind']=='passage' for u in units.values()) else None,
            'persons':len(people) if person_basis=='confirmed' else None},
        'methodological_note':'Die Bezugsmenge ist das übergebene codierte Material. '
            'Nicht exportierte Interviewteile sind nicht erfasst. Gleicher Wortlaut begründet keine gemeinsame Passage.'}
    material['basis_fingerprint'] = fingerprint(material)
    return material


def unit_ids_for_segments(material, segment_ids):
    """Project explicit coding-row references onto their material units, once each."""
    if not isinstance(segment_ids, (list, tuple, set)) or any(not isinstance(s,str) for s in segment_ids):
        raise ValueError('Zählumfang benötigt eine Liste von Segment-IDs.')
    index = {sid:uid for uid,row in material['units'].items() for sid in row['segment_ids']}
    if set(segment_ids) - index.keys():
        raise ValueError('Zählumfang enthält unbekannte Segment-IDs.')
    return sorted({index[s] for s in segment_ids})


def load_counting_material(config_path, input_path=None, *, run_dir=None, require_confirmed=True):
    """Read current material; bind it to person confirmation and optional run hashes."""
    config_path = Path(config_path).resolve()
    config_raw = config_path.read_bytes()
    config = yaml.safe_load(config_raw.decode('utf-8-sig'))
    if not isinstance(config, dict):
        raise ValueError('Zählung benötigt eine gültige Konfiguration.')
    columns = config.get('columns', {})
    if not isinstance(columns, dict):
        raise ValueError('Zählung benötigt gültige Spaltenzuordnungen.')
    input_path = resolve_config_path(config_path, input_path, config.get('paths', {}).get('input_csv'))
    book_path = resolve_config_path(config_path, None, config.get('paths', {}).get('category_system_csv'))
    before = {key:file_hash(path) for key,path in
        (('input_sha256',input_path),('config_sha256',config_path),('codebook_sha256',book_path))}
    before['config_sha256'] = hashlib.sha256(config_raw).hexdigest()
    if run_dir is not None:
        load_input_context(run_dir, config_path, input_path, require_codebook=True)
    raw = input_path.read_bytes()
    receipt = config.get('person_identity')
    person_basis = 'unconfirmed'
    if receipt is not None or require_confirmed:
        if not isinstance(receipt,dict) or receipt.get('version') != 1:
            raise ValueError('Personenzuordnung zuerst prüfen und bestätigen; ein gültiger Nachweis fehlt.')
        expected_count = verify(raw, columns, receipt)
        person_basis = 'confirmed'
    segments = load_segments(input_path, columns)
    _, codebook = load_codebook(book_path)
    if any(s.human_code not in codebook for s in segments):
        raise ValueError('Zählgrundlage enthält Codes außerhalb des aktuellen Kategoriensystems.')
    if person_basis == 'confirmed':
        rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig')), delimiter=';'))
        expected_people = {r[columns['person']] for r in rows}
        if len({s.person for s in segments}) != expected_count or {s.person for s in segments} != expected_people:
            raise ValueError('Personenkennungen werden beim Einlesen verändert. Eindeutige Kennungen vergeben und erneut bestätigen.')
        before['person_identity_sha256'] = fingerprint(receipt)
    after = {key:file_hash(path) for key,path in
        (('input_sha256',input_path),('config_sha256',config_path),('codebook_sha256',book_path))}
    if any(before[key] != value for key,value in after.items()):
        raise ValueError('Eingaben wurden während der Zählvorbereitung verändert; erneut prüfen.')
    return build_material(segments, person_basis=person_basis, provenance=before)
