"""Shared durable artifacts, provenance and validated coding checkpoints."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import copy
import logging
from dataclasses import asdict, is_dataclass
from pathlib import Path


def fingerprint(value):
    def default(item):
        return asdict(item) if is_dataclass(item) else str(item)
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     default=default).encode('utf-8')).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path, value):
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


class Checkpoint:
    """Only completed, validated results are reusable; mismatches fail closed."""
    def __init__(self, path, identity):
        self.path = Path(path) if path else None
        self.identity = fingerprint(identity)
        self.results = {}
        if self.path and self.path.exists():
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if data.get('fingerprint') != self.identity:
                raise ValueError('Checkpoint passt nicht zu Input, Codebuch, Prompt, Code oder Modellparametern.')
            self.results = data['results']
            if data.get('results_sha256') != fingerprint(self.results):
                raise ValueError('Checkpoint-Ergebnisse wurden verändert oder sind beschädigt.')

    def get(self, sid):
        return self.results.get(sid)

    def save(self, sid, result):
        if result.get('processing_status') != 'completed':
            return
        self.results[sid] = result
        if self.path:
            atomic_json(self.path, {'fingerprint': self.identity, 'results': self.results,
                                    'results_sha256': fingerprint(self.results)})


def checkpoint_identity(segments, codebook, prompts, context, params):
    root = Path(__file__).parent
    return {'segments': segments, 'codebook': codebook, 'prompts': prompts,
            'context': context, 'params': params,
            'code': {p.name: file_hash(p) for p in sorted(root.glob('*.py'))}}


def person_for_segment(sid, metadata=None):
    if metadata and sid in metadata:
        return metadata[sid]['person']
    if '#SEG' in sid:
        return sid.split('#SEG', 1)[0].strip()
    raise ValueError(f'Personenmetadaten fehlen für Segment-ID {sid!r}.')


class PartCheckpoint:
    """Persist a logical work item only after its compute/validation callback succeeds."""
    def __init__(self, module, params):
        directory = params.get('partial_checkpoint_dir') or os.environ.get('WORKFLOW_CHECKPOINT_DIR')
        self.directory = Path(directory) / module if directory and params.get('partial_checkpoints', True) else None
        self.hits = 0
        self.saved = 0
        self.identity = None
        if self.directory:
            root = Path(__file__).parent
            self.identity = fingerprint({'module':module, 'params':params,
                'workflow':os.environ.get('WORKFLOW_FINGERPRINT'),
                'code':{p.name:file_hash(p) for p in sorted(root.glob('*.py'))}})

    def run(self, key, inputs, compute):
        if self.directory is None:
            return compute()
        path = self.directory / (fingerprint(key) + '.json')
        expected = fingerprint({'identity':self.identity,'key':key,'inputs':inputs})
        if path.exists():
            data = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data,dict) or data.get('schema_version') != 1 or data.get('fingerprint') != expected:
                raise ValueError('Teil-Checkpoint passt nicht zu Eingaben, Prompt, Code, Lauf oder Modellparametern.')
            if data.get('processing_status') != 'completed' or 'result' not in data or data.get('result_sha256') != fingerprint(data['result']):
                raise ValueError('Teil-Checkpoint ist unvollständig oder wurde verändert.')
            self.hits += 1
            logging.getLogger('checkpoints').info('Validierten Teil-Checkpoint wiederverwendet: %s', self.directory.name)
            return copy.deepcopy(data['result'])
        result = compute()
        if isinstance(result,dict) and result.get('processing_status','completed') != 'completed':
            raise ValueError('Unvollständige Teilanalyse darf nicht als Checkpoint gespeichert werden.')
        atomic_json(path, {'schema_version':1,'fingerprint':expected,'processing_status':'completed',
                           'result_sha256':fingerprint(result),'result':result})
        self.saved += 1
        return copy.deepcopy(result)
