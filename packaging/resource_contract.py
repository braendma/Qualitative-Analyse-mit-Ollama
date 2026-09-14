"""Build-only validation helpers; standard library and no application imports."""
import hashlib
import json
from pathlib import Path, PurePosixPath


BUILD_FILES = (
    'bootstrap.py', 'windows.spec', 'resources.json', 'resource_contract.py',
    'build_manifest.py', 'requirements-build.txt',
)


def checked_file(root, relative):
    if not isinstance(relative, str) or '\\' in relative or ':' in relative:
        raise ValueError('Resource path must be a portable relative path')
    parsed = PurePosixPath(relative)
    if (parsed.is_absolute() or '..' in parsed.parts or '.' in parsed.parts
            or not parsed.parts or parsed.as_posix() != relative):
        raise ValueError('Resource path must be a canonical relative path')
    root = Path(root).resolve(strict=True)
    path = root.joinpath(*parsed.parts)
    current = root
    for part in parsed.parts:
        current = current / part
        if current.is_symlink() or (hasattr(current, 'is_junction') and current.is_junction()):
            raise ValueError('Redirected resources are not permitted: ' + relative)
    if not path.is_file() or not path.resolve(strict=True).is_relative_to(root):
        raise ValueError('Missing or escaped resource: ' + relative)
    return path


def resource_paths(repository, packaging):
    data = json.loads((Path(packaging) / 'resources.json').read_text(encoding='utf-8'))
    entries = data.get('resources')
    if data.get('schema') != 1 or not isinstance(entries, list) or not entries:
        raise ValueError('Invalid resource allowlist')
    if len(set(entries)) != len(entries):
        raise ValueError('Duplicate resource allowlist entries')
    result = []
    for relative in sorted(entries):
        # The reviewed list is authoritative; these guards additionally reject
        # obvious accidental private/build roots, even if added to the JSON.
        parts = PurePosixPath(relative).parts
        if not (parts[0] in {'src', 'config', 'demo', 'docs'} or relative in
                {'VERSION', 'LICENSE', 'README.md', 'requirements.txt'}):
            raise ValueError('Resource outside public roots: ' + relative)
        if any(part.lower() in {'__pycache__', '.git', '.venv', 'app_data', 'runs',
                               'uploads', 'workflow_output', 'secrets'} for part in parts):
            raise ValueError('Private/generated resource root: ' + relative)
        result.append((relative, checked_file(repository, relative)))
    return result


def fingerprint(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return {'sha256': digest.hexdigest(), 'bytes': Path(path).stat().st_size}


def inventory(repository, packaging):
    entries = {relative: fingerprint(path)
               for relative, path in resource_paths(repository, packaging)}
    for name in BUILD_FILES:
        entries['packaging/' + name] = fingerprint(checked_file(packaging, name))
    return entries
