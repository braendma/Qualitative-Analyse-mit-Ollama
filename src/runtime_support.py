"""Shared durable artifacts, provenance and validated coding checkpoints."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import copy
import logging
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from pathlib import Path
from filesystem_paths import absolute_path, canonical_path, io_path


def run_artifact_path(path):
    """Preserve standalone cwd semantics; managed modules have an explicit root."""
    root = os.environ.get('WORKFLOW_RUN_DIR')
    if not root:
        return Path(path)
    return io_path(absolute_path(root) / path)


def artifact_reference(path):
    """Keep report links portable when execution uses absolute IO arguments."""
    root = os.environ.get('WORKFLOW_RUN_DIR')
    if root:
        actual, base = canonical_path(run_artifact_path(path)), canonical_path(root)
        if actual.is_relative_to(base):
            return actual.relative_to(base).as_posix()
    return str(path)


def fingerprint(value):
    def default(item):
        return asdict(item) if is_dataclass(item) else str(item)
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     default=default).encode('utf-8')).hexdigest()


def file_hash(path):
    return hashlib.sha256(io_path(path).read_bytes()).hexdigest()


def atomic_text(path, text):
    path = io_path(path)
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


@contextmanager
def exclusive_file_lock(path):
    """Nonblocking process lock; keep the inode/file after releasing the OS lock."""
    with open(io_path(path), 'a+b') as handle:
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b'\0')
            handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('Dieser Auftrag wird bereits von einem anderen Prozess bearbeitet.') from exc
        try:
            yield
        finally:
            if os.name == 'nt':
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class Checkpoint:
    """Only completed, validated results are reusable; mismatches fail closed."""
    def __init__(self, path, identity):
        self.path = io_path(run_artifact_path(path)) if path else None
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
    from package_identity import current_package_identity
    root = Path(__file__).parent
    identity = {'segments': segments, 'codebook': codebook, 'prompts': prompts,
            'context': context, 'params': params,
            'code': {p.name: file_hash(p) for p in sorted(root.glob('*.py'))}}
    package = current_package_identity()
    if package is not None:identity['package'] = package
    return identity


def person_for_segment(sid, metadata=None):
    if metadata and sid in metadata:
        return metadata[sid]['person']
    if '#SEG' in sid:
        return sid.split('#SEG', 1)[0].strip()
    raise ValueError(f'Personenmetadaten fehlen für Segment-ID {sid!r}.')


class PartCheckpoint:
    """Persist a logical work item only after its compute/validation callback succeeds."""
    def __init__(self, module, params):
        from package_identity import current_package_identity
        package = current_package_identity()
        directory = params.get('partial_checkpoint_dir') or os.environ.get('WORKFLOW_CHECKPOINT_DIR')
        self.directory = io_path(run_artifact_path(directory)) / module if directory and params.get('partial_checkpoints', True) else None
        self.hits = 0
        self.saved = 0
        self.identity = None
        if self.directory:
            root = Path(__file__).parent
            identity = {'module':module, 'params':params,
                'workflow':os.environ.get('WORKFLOW_FINGERPRINT'),
                'code':{p.name:file_hash(p) for p in sorted(root.glob('*.py'))}}
            if package is not None:identity['package'] = package
            self.identity = fingerprint(identity)

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
