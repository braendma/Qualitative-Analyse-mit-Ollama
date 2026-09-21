"""Generate a public, path-free build-input manifest; never scan user data.

This records build inputs, not the final binary inventory or proof
that frozen imports actually load the recorded sources.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import subprocess
import sys

from resource_contract import inventory


DISTRIBUTIONS = (
    'pandas', 'numpy', 'matplotlib', 'PyYAML', 'ollama', 'openpyxl',
    'faster-whisper','ctranslate2','av','onnxruntime','huggingface-hub','tokenizers','striprtf',
    'pyinstaller', 'pyinstaller-hooks-contrib',
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True, type=Path)
    parser.add_argument('--private-snapshot',action='store_true',help='Private uncommitted source snapshot; never claim a Git commit')
    parser.add_argument('--source-commit',
                        help='Exact reviewed public Git commit (40 or 64 hexadecimal characters)')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    if args.private_snapshot and args.source_commit:parser.error('Private snapshots do not claim a source commit')
    if not args.private_snapshot and not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', args.source_commit or ''):
        parser.error('source-commit must be an exact lowercase Git object identifier')
    repository = args.repository.resolve(strict=True)
    packaging = Path(__file__).resolve().parent
    output = args.output.resolve()
    if output != packaging / 'build-manifest.json':
        parser.error('output must be packaging/build-manifest.json next to this generator')
    resources = inventory(repository, packaging)
    # Bind the advertised revision to a clean, tracked set of actual inputs.
    def git(*arguments):
        return subprocess.check_output(['git', '-C', str(repository), *arguments],
                                       encoding='utf-8', stderr=subprocess.PIPE).strip()
    if not args.private_snapshot:
        if git('rev-parse', 'HEAD') != args.source_commit:
            parser.error('source-commit must equal the checked-out HEAD')
        if git('status', '--porcelain', '--untracked-files=no'):
            parser.error('Commit tracked source changes before creating the build manifest')
        for relative in resources:
            git('ls-files', '--error-unmatch', '--', relative)
    version = (repository / 'VERSION').read_text(encoding='utf-8').strip()
    if not re.fullmatch(r'[0-9][0-9A-Za-z.+-]{0,63}', version):
        parser.error('VERSION is not a portable version identifier')
    if args.private_snapshot and 'private' not in version:parser.error('Private snapshot needs a clearly private VERSION')
    dependencies = {name: importlib.metadata.version(name) for name in DISTRIBUTIONS}
    if dependencies['pyinstaller'] != '6.22.3':
        parser.error('Build requires the reviewed PyInstaller 6.22.3 pin')
    if sys.platform != 'win32' or platform.machine().lower() not in {'amd64', 'x86_64'}:
        parser.error('This build targets native Windows x64 only')
    manifest = {
        'schema': 1,
        'kind': 'private-build-input-manifest' if args.private_snapshot else 'build-input-manifest',
        'version': version,
        'source_commit': args.source_commit,
        'python': '.'.join(map(str, sys.version_info[:3])),
        'platform': 'windows-x64',
        'build_type': 'pyinstaller-onedir-console',
        'dependencies': dependencies,
        'resources': resources,
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    manifest['build_input_id'] = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print('Build-input manifest created; no binary or release validation performed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
