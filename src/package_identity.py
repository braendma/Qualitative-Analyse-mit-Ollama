"""Reproducible frozen-package identity, not a publisher signature.

Validate the recorded build inputs against the files shipped with this running
executable. Source execution deliberately has no additional package identity.
"""
import hashlib
import importlib.metadata
import json
from pathlib import Path, PurePosixPath
import re
import sys


RUNTIME_DEPENDENCIES = ('pandas', 'numpy', 'matplotlib', 'PyYAML', 'ollama', 'openpyxl', 'faster-whisper','ctranslate2','av','onnxruntime','huggingface-hub','tokenizers','striprtf')
BUILD_DEPENDENCIES = ('pyinstaller', 'pyinstaller-hooks-contrib')
BUILD_FILES = ('bootstrap.py', 'windows.spec', 'resources.json', 'resource_contract.py',
               'build_manifest.py', 'requirements-build.txt')
ERROR = ('Programmpaket ist unvollständig, verändert oder passt nicht zur Laufzeit. '
         'Bitte das vollständige Programmpaket erneut entpacken; vorhandene Ergebnisse behalten.')


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('utf-8')


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise ValueError(ERROR)
        value[key] = item
    return value


def _json(path):
    with path.open('rb') as stream:
        raw = stream.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError(ERROR)
    return json.loads(raw, object_pairs_hook=_pairs), raw


def _file(root, relative):
    if not isinstance(relative, str) or '\\' in relative or ':' in relative:
        raise ValueError(ERROR)
    parsed = PurePosixPath(relative)
    if (parsed.is_absolute() or not parsed.parts or '..' in parsed.parts
            or parsed.as_posix() != relative):
        raise ValueError(ERROR)
    current = root
    for part in parsed.parts:
        current = current / part
        if current.is_symlink() or (hasattr(current, 'is_junction') and current.is_junction()):
            raise ValueError(ERROR)
    if not current.is_file() or not current.resolve(strict=True).is_relative_to(root):
        raise ValueError(ERROR)
    return current


def _digest(path):
    digest = hashlib.sha256()
    size = 0
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
            size += len(block)
    return {'sha256': digest.hexdigest(), 'bytes': size}


def validate_frozen_package(root, executable):
    """Validate actual bundle files and installed runtime dependency metadata.

    No Git discovery, source-tree fallback, or executable path is published.
    Hashes are recomputed at each identity boundary so changed files cannot reuse
    a previously validated checkpoint identity merely through a cache hit.
    """
    try:
        root = Path(root).resolve(strict=True)
        executable = Path(executable).resolve(strict=True)
        if not root.is_dir() or not executable.is_file():
            raise ValueError(ERROR)
        manifest, raw = _json(_file(root, 'packaging/build-manifest.json'))
        if not isinstance(manifest, dict) or set(manifest) != {
                'schema', 'kind', 'version', 'source_commit', 'python', 'platform',
                'build_type', 'dependencies', 'resources', 'build_input_id'}:
            raise ValueError(ERROR)
        claimed = manifest['build_input_id']
        payload = {key: value for key, value in manifest.items() if key != 'build_input_id'}
        if (type(manifest['schema']) is not int or manifest['schema'] != 1
                or manifest['kind'] not in ('build-input-manifest','private-build-input-manifest')
                or not isinstance(claimed, str)
                or claimed != hashlib.sha256(_canonical(payload)).hexdigest()
                or not ((manifest['kind']=='private-build-input-manifest' and manifest['source_commit'] is None and 'private' in str(manifest['version'])) or (manifest['kind']=='build-input-manifest' and isinstance(manifest['source_commit'],str) and re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})',manifest['source_commit'])))
                or not isinstance(manifest['version'], str)
                or not re.fullmatch(r'[0-9][0-9A-Za-z.+-]{0,63}', manifest['version'])
                or manifest['python'] != '.'.join(map(str, sys.version_info[:3]))
                or manifest['platform'] != 'windows-x64'
                or manifest['build_type'] != 'pyinstaller-onedir-console'):
            raise ValueError(ERROR)
        dependencies = manifest['dependencies']
        if (not isinstance(dependencies, dict)
                or set(dependencies) != set(RUNTIME_DEPENDENCIES + BUILD_DEPENDENCIES)
                or any(not isinstance(value, str) or not value.strip() for value in dependencies.values())):
            raise ValueError(ERROR)
        for name in RUNTIME_DEPENDENCIES:
            if dependencies[name] != importlib.metadata.version(name):
                raise ValueError(ERROR)
        resources = manifest['resources']
        if not isinstance(resources, dict) or not resources:
            raise ValueError(ERROR)
        for relative, expected in resources.items():
            if (not isinstance(expected, dict) or set(expected) != {'sha256', 'bytes'}
                    or type(expected['bytes']) is not int or expected['bytes'] < 0
                    or not isinstance(expected['sha256'], str)
                    or not re.fullmatch('[a-f0-9]{64}', expected['sha256'])
                    or _digest(_file(root, relative)) != expected):
                raise ValueError(ERROR)
        allowlist, _ = _json(_file(root, 'packaging/resources.json'))
        entries = allowlist.get('resources') if isinstance(allowlist, dict) else None
        if (not isinstance(allowlist, dict) or type(allowlist.get('schema')) is not int
                or allowlist['schema'] != 1 or not isinstance(entries, list)
                or not all(isinstance(item, str) for item in entries)
                or len(entries) != len(set(entries))):
            raise ValueError(ERROR)
        required = {'VERSION', 'LICENSE', 'README.md', 'requirements.txt',
                    'src/package_identity.py', 'src/runtime_entry.py',
                    'src/runtime_support.py', 'src/00_WORKFLOW_RUNNER.py'}
        if (not required <= set(entries)
                or set(resources) != set(entries) | {'packaging/' + name for name in BUILD_FILES}
                or (_file(root, 'VERSION').read_text(encoding='utf-8').strip() != manifest['version'])):
            raise ValueError(ERROR)
        # Every shipped Python module can be imported by the dispatcher; no
        # unrecorded source file may silently extend this execution identity.
        actual_sources = {path.relative_to(root).as_posix() for path in (root / 'src').rglob('*.py')}
        if actual_sources != {name for name in resources if name.startswith('src/') and name.endswith('.py')}:
            raise ValueError(ERROR)
        return {'schema': 1, 'kind': 'frozen-package',
                'executable_sha256': _digest(executable)['sha256'],
                'build_input_id': claimed, 'manifest_sha256': hashlib.sha256(raw).hexdigest(),
                'resources_sha256': hashlib.sha256(_canonical(resources)).hexdigest(),
                'bootstrap_sha256': resources['packaging/bootstrap.py']['sha256'],
                **{key: manifest[key] for key in ('source_commit', 'version', 'python', 'platform',
                                                 'build_type', 'dependencies')}}
    except (OSError, ValueError, TypeError, KeyError, importlib.metadata.PackageNotFoundError) as exc:
        raise ValueError(ERROR) from exc


def current_package_identity():
    if not getattr(sys, 'frozen', False):
        return None
    root = getattr(sys, '_MEIPASS', None)
    if not isinstance(root, str) or not root:
        raise ValueError(ERROR)
    return validate_frozen_package(root, sys.executable)
