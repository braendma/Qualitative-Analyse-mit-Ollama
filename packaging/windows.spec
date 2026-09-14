# Native Windows onedir build from explicitly reviewed public resources.
import ast
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import sys

from PyInstaller.utils.hooks import copy_metadata

PACKAGING = Path(SPECPATH).resolve()
REPOSITORY = PACKAGING.parent
sys.path.insert(0, str(PACKAGING))
from resource_contract import BUILD_FILES, inventory, resource_paths

if sys.platform != 'win32':
    raise SystemExit('This spec requires a native Windows build environment.')
if importlib.metadata.version('pyinstaller') != '6.22.3':
    raise SystemExit('The reviewed PyInstaller 6.22.3 pin is required.')

resources = resource_paths(REPOSITORY, PACKAGING)
manifest_path = PACKAGING / 'build-manifest.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
if manifest.get('resources') != inventory(REPOSITORY, PACKAGING):
    raise SystemExit('Build inputs changed after manifest creation; review and regenerate.')
identity = {key: value for key, value in manifest.items() if key != 'build_input_id'}
canonical = json.dumps(identity, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
if manifest.get('build_input_id') != hashlib.sha256(canonical.encode('utf-8')).hexdigest():
    raise SystemExit('Build-input identity is invalid.')
for distribution, version in manifest.get('dependencies', {}).items():
    if importlib.metadata.version(distribution) != version:
        raise SystemExit('Build dependency changed after manifest creation: ' + distribution)

project_sources = [(relative, path) for relative, path in resources
                   if relative.startswith('src/') and relative.endswith('.py')]
project_modules = {path.stem for _, path in project_sources}
# Fail closed if a new Python helper was added but not publicly reviewed/listed.
actual_sources = {path.name for path in (REPOSITORY / 'src').glob('*.py')}
if actual_sources != {path.name for _, path in project_sources}:
    raise SystemExit('Source inventory differs from the reviewed resource allowlist.')

# runpy-loaded project sources are intentionally invisible to static application
# analysis. Include their stdlib imports as well, not only third-party packages.
stdlib_imports = {'ctypes.wintypes'}
unknown_imports = set()
for _, path in project_sources:
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    for node in ast.walk(tree):
        names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                 else [node.module] if isinstance(node, ast.ImportFrom) and not node.level
                 and node.module else [])
        for name in names:
            if name.split('.')[0] in sys.stdlib_module_names:
                stdlib_imports.add(name)
            elif name.split('.')[0] not in project_modules | {
                    'pandas', 'numpy', 'matplotlib', 'yaml', 'ollama', 'openpyxl'}:
                unknown_imports.add(name)
if unknown_imports:
    raise SystemExit('Review new third-party imports before build: ' + ', '.join(sorted(unknown_imports)))

THIRD_PARTY_IMPORTS = [
    'pandas', 'numpy', 'matplotlib', 'matplotlib.pyplot',
    'matplotlib.backends.backend_agg', 'matplotlib.backends.backend_svg',
    'matplotlib.backends.backend_pdf', 'yaml', 'ollama', 'openpyxl',
    'openpyxl.cell._writer', 'openpyxl.reader.excel', 'openpyxl.writer.excel',
]
METADATA_DISTRIBUTIONS = ['pandas', 'numpy', 'matplotlib', 'PyYAML', 'ollama', 'openpyxl']
datas = [(str(path), str(Path(relative).parent)) for relative, path in resources]
datas += [(str(PACKAGING / name), 'packaging') for name in BUILD_FILES]
datas.append((str(manifest_path), 'packaging'))
for distribution in METADATA_DISTRIBUTIONS:
    datas += copy_metadata(distribution, recursive=True)
# Preserve copyright/license files supplied in dependency metadata, including
# the PyInstaller bootloader exception and Python's own license.
datas += copy_metadata('pyinstaller')
datas += copy_metadata('setuptools')
datas.append((str(Path(sys.base_prefix) / 'LICENSE.txt'), 'third_party_licenses/python'))

a = Analysis(
    [str(PACKAGING / 'bootstrap.py')],
    pathex=[], binaries=[], datas=datas,
    hiddenimports=sorted(stdlib_imports | set(THIRD_PARTY_IMPORTS)),
    hookspath=[], runtime_hooks=[],
    excludes=sorted(project_modules),
    hooksconfig={'matplotlib': {'backends': ['Agg', 'svg', 'pdf']}},
    noarchive=False,
)
# Defense against accidental duplicate implementations; do not merely delete
# suspect entries silently, because that would conceal a changed import graph.
duplicates = [name for name, *_ in a.pure if name.split('.')[0] in project_modules]
if duplicates:
    raise SystemExit('Project module entered PYZ despite exclusions: ' + ', '.join(duplicates))
pyz = PYZ(a.pure)
exe = EXE(
    # Embedded Python ignores PYTHONUTF8/PYTHONIOENCODING from child env.
    # Keep redirected German logs and supervisor/runner text consistently UTF-8.
    pyz, a.scripts, [('X utf8=1', None, 'OPTION')], exclude_binaries=True,
    name='QualitativeAnalyse', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=True, disable_windowed_traceback=False,
    contents_directory='_internal',
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='QualitativeAnalyse')
shutil.copyfile(REPOSITORY / 'docs' / 'WINDOWS_STANDALONE.txt',
                Path(DISTPATH) / 'QualitativeAnalyse' / 'README.txt')
