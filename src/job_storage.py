"""Bind external research storage to existing local jobs, never adopt other runs."""
from contextlib import contextmanager, ExitStack
import json
from pathlib import Path
import re
import secrets

from project_paths import resolve_output_parent
from filesystem_paths import absolute_path, canonical_path, io_path
from runtime_support import atomic_json, exclusive_file_lock, file_hash, fingerprint

ROOT_MARKER = '.qualitativeanalyse-job.json'
LOCAL_MARKER = '.research_binding.json'
RUN_MARKER = '.research_run.json'
LOCK = '.research_binding.lock'


def _require(value, message='Forschungsordner passt nicht zur gespeicherten Jobbindung.'):
    if not value:
        raise ValueError(message)


def _folder(folder, *, strict=False):
    folder = Path(folder).resolve()
    _require(folder.is_dir(), 'Lokaler Jobordner fehlt.')
    _require(not strict or (folder.parent.name == 'jobs'
             and folder.parent.parent.parent.name == 'projects'
             and re.fullmatch(r'[a-f0-9]{20}|[a-f0-9]{32}', folder.name)
             and re.fullmatch(r'[a-f0-9]{20}|[a-f0-9]{32}', folder.parent.parent.name)),
             'Lokaler Projekt-/Jobordner fehlt oder ist ungültig.')
    return folder


def _child(root, name):
    expected = io_path(root / name)
    _require(canonical_path(expected) == absolute_path(expected), 'Gebundener Pfad wurde umgeleitet. Ursprünglichen Forschungsordner wiederherstellen.')
    return expected


def _read(path):
    _require(path.is_file(), 'Forschungsbindung oder Laufmanifest fehlt. Ursprünglichen Ordner wieder verfügbar machen.')
    value = json.loads(path.read_text(encoding='utf-8'))
    _require(isinstance(value, dict))
    return value


def _identity(path):
    stat = path.stat()
    return {'device': stat.st_dev, 'inode': stat.st_ino}


@contextmanager
def _binding_lock(path):
    """Only lock acquisition conflicts are transient; body failures propagate."""
    with ExitStack() as stack:
        try:
            stack.enter_context(exclusive_file_lock(path))
        except RuntimeError as exc:
            # The shared helper wraps only the OS lock-acquisition OSError.
            if not isinstance(exc.__cause__, OSError):
                raise
            raise BlockingIOError('Jobbindung wird gerade geprüft. Bitte kurz warten und erneut versuchen.') from exc
        yield


def _config(folder, value):
    _folder(folder, strict=True)
    _require(isinstance(value, (str, Path)) and bool(str(value)))
    path = Path(value).resolve()
    _require(path.is_file() and path.is_relative_to(folder.parent.parent),
             'Jobkonfiguration muss eine vorhandene Datei innerhalb des eigenen Projekts sein.')
    return path


def create_binding(folder, config, parent):
    """Create one exclusive research directory and its local/external identity."""
    folder = _folder(folder, strict=True)
    config = _config(folder, config)
    parent = resolve_output_parent(output_dir=parent, check_write=True)
    lock = _child(folder, LOCK)
    with _binding_lock(lock):
        _require(not (folder / LOCAL_MARKER).exists(), 'Dieser Job besitzt bereits einen Forschungsordner.')
        # Creation time is already stored on the job; avoid repeating it in
        # every nested output/checkpoint path. Keep the complete unique job ID.
        root = io_path(parent / ('QualitativeAnalyse_' + folder.name))
        root.mkdir(exist_ok=False)
        storage = {'schema_version': 1, 'kind': 'external', 'project_id': folder.parent.parent.name,
                   'job_id': folder.name, 'job_folder': str(folder), 'research_root': str(canonical_path(root)),
                   'root_identity': _identity(root), 'config_path': str(config), 'config_sha256': file_hash(config),
                   'nonce': secrets.token_hex(32)}
        (root / 'runs').mkdir()
        atomic_json(root / ROOT_MARKER, storage)
        atomic_json(folder / LOCAL_MARKER, storage)
        return storage


def _storage(folder, job):
    _require(isinstance(job, dict))
    if 'storage' not in job:
        # A newly bound job cannot become legacy merely by deleting one JSON key.
        _require(not (folder / LOCAL_MARKER).exists(), 'Forschungsbindung fehlt im Jobindex; kein lokaler Ersatzordner wird verwendet.')
        return None
    storage = job['storage']
    _folder(folder, strict=True)
    _require(isinstance(storage, dict) and type(storage.get('schema_version')) is int
             and storage['schema_version'] == 1 and storage.get('kind') == 'external')
    _require(storage.get('job_folder') == str(folder) and storage.get('job_id') == folder.name
             and storage.get('project_id') == folder.parent.parent.name)
    _require(fingerprint(_read(_child(folder, LOCAL_MARKER))) == fingerprint(storage))
    _require(isinstance(storage.get('research_root'), str))
    declared = Path(storage['research_root'])
    root = io_path(declared)
    _require(declared.is_absolute() and canonical_path(root) == absolute_path(declared) and root.is_dir(),
             'Gebundener Forschungsordner ist nicht verfügbar oder wurde umgeleitet.')
    _require(fingerprint(_identity(root)) == fingerprint(storage.get('root_identity')),
             'Forschungsordner wurde ausgetauscht; ursprünglichen Ordner wiederherstellen.')
    _require(fingerprint(_read(_child(root, ROOT_MARKER))) == fingerprint(storage))
    config = _config(folder, job.get('config'))
    _require(str(config) == storage.get('config_path') and file_hash(config) == storage.get('config_sha256'),
             'Jobkonfiguration wurde verändert oder ausgetauscht; neuen Lauf mit geprüften Eingaben erstellen.')
    return storage


def config_path(folder, job):
    folder = _folder(folder)
    _storage(folder, job)
    return _config(folder, job.get('config'))


def research_root(folder, job):
    folder = _folder(folder)
    storage = _storage(folder, job)
    return io_path(storage['research_root']) if storage is not None else None


def runs_root(folder, job):
    folder = _folder(folder)
    root = research_root(folder, job)
    result = _child(root if root is not None else folder, 'runs')
    if root is not None:
        _require(result.is_dir(), 'Gebundener Laufordner fehlt; kein Ersatzordner wird angelegt.')
    return result


def review_root(folder, job):
    folder = _folder(folder)
    root = research_root(folder, job)
    return _child(root if root is not None else folder, 'review')


def _manifest_run(root, path, storage):
    _require(path.parent == root and canonical_path(path) == absolute_path(path) and path.is_dir(), 'Laufpfad wurde umgeleitet.')
    manifest = _read(_child(path, 'workflow_manifest.json'))
    if storage is not None:
        _require(manifest.get('run_id') == path.name
                 and isinstance(manifest.get('provenance'), dict)
                 and manifest['provenance'].get('config_sha256') == storage['config_sha256'],
                 'Laufherkunft passt nicht zur gebundenen Jobkonfiguration.')
        if 'output_dir' in manifest:
            _require(isinstance(manifest['output_dir'], str) and canonical_path(manifest['output_dir']) == canonical_path(path),
                     'Laufmanifest verweist auf einen anderen Ergebnisordner.')
    return manifest


def run_path(folder, job):
    """Find exactly one run; external jobs pin its identity at first discovery."""
    folder = _folder(folder)
    storage = _storage(folder, job)
    root = _child(Path(storage['research_root']) if storage else folder, 'runs')
    if storage:
        _require(root.is_dir(), 'Gebundener Laufordner fehlt; kein Ersatzordner wird angelegt.')
        lock = _child(folder, LOCK)
        _require(lock.is_file(), 'Lokale Jobbindung ist unvollständig.')
        with _binding_lock(lock):
            # Recheck after obtaining the cross-process lock.
            _storage(folder, job)
            marker = _child(folder, RUN_MARKER)
            if marker.exists():
                pinned = _read(marker)
                _require(type(pinned.get('schema_version')) is int and pinned['schema_version'] == 1
                         and pinned.get('storage_fingerprint') == fingerprint(storage))
                name = pinned.get('run_id')
                _require(isinstance(name, str) and name not in ('', '.', '..') and Path(name).name == name)
                path = _child(root, name)
                _manifest_run(root, path, storage)
                _require(fingerprint(_identity(path)) == fingerprint(pinned.get('run_identity')), 'Gebundener Laufordner wurde ausgetauscht.')
                _require(sorted(root.glob('*/workflow_manifest.json')) == [path / 'workflow_manifest.json'],
                         'Mehrere Laufmanifeste im Jobordner; keine eindeutige Zuordnung.')
                return path
            candidates = sorted(root.glob('*/workflow_manifest.json'))
            _require(len(candidates) <= 1, 'Mehrere Laufmanifeste im Jobordner; keine eindeutige Zuordnung.')
            if not candidates:
                return None
            path = candidates[0].parent
            _manifest_run(root, path, storage)
            atomic_json(marker, {'schema_version': 1, 'storage_fingerprint': fingerprint(storage),
                                 'run_id': path.name, 'run_identity': _identity(path)})
            return path
    candidates = sorted(root.glob('*/workflow_manifest.json'))
    _require(len(candidates) <= 1, 'Mehrere alte Laufmanifeste im Jobordner; keine eindeutige Zuordnung.')
    if not candidates:
        return None
    path = candidates[0].parent
    _manifest_run(root, path, None)
    return path
