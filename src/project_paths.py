"""Separate bundled read-only resources, technical app data and research outputs.

These helpers do not create or migrate directories. Existing source constants
remain compatible until their callers explicitly adopt the new path contracts.
"""
import os
from pathlib import Path
import sys
import tempfile


def resource_root():
    """Source project root or the single bundled resource root (src/config/demo)."""
    if getattr(sys, 'frozen', False):
        bundled = getattr(sys, '_MEIPASS', None)
        if (not isinstance(bundled, (str, Path)) or not str(bundled).strip()
                or not Path(bundled).is_absolute() or not Path(bundled).is_dir()):
            raise ValueError('Die gebündelten Programmressourcen fehlen. Installation erneut entpacken.')
        return Path(bundled).resolve()
    return Path(__file__).resolve().parent.parent


PROJECT_DIR = resource_root()
SOURCE_DIR = PROJECT_DIR / 'src'
DEFAULT_CONFIG = PROJECT_DIR / 'config' / 'config_v2.yaml'
DEFAULT_OUTPUT = PROJECT_DIR / 'workflow_output'
DEMO_DIR = PROJECT_DIR / 'demo'


def default_data_dir():
    """Find one existing technical workspace, otherwise return the platform default.

    Old App versions used LOCALAPPDATA when set, otherwise ~/.local/share,
    including on macOS. Search that historical location without moving data.
    Multiple existing workspaces require an explicit --data-dir selection.
    """
    local = os.environ.get('LOCALAPPDATA')
    if local and not Path(local).is_absolute():
        raise ValueError('LOCALAPPDATA enthält keinen absoluten Pfad. Mit --data-dir einen App-Datenordner auswählen.')
    home = Path.home() if sys.platform != 'win32' or not local else None
    old_parent = Path(local) if local else home / '.local' / 'share'
    if sys.platform == 'win32':
        parent = Path(local) if local else home / 'AppData' / 'Local'
    elif sys.platform == 'darwin':
        parent = home / 'Library' / 'Application Support'
    else:
        xdg = os.environ.get('XDG_DATA_HOME')
        parent = Path(xdg) if xdg and Path(xdg).is_absolute() else home / '.local' / 'share'
    preferred = parent / 'QualitativeAnalyse'
    candidates = {path.resolve() for path in
                  (preferred, parent / 'QualitativeOllama', old_parent / 'QualitativeOllama')}
    existing = []
    for path in sorted(candidates):
        if path.exists():
            if not path.is_dir():
                raise ValueError('App-Datenpfad ist kein Ordner: ' + str(path) + '. Mit --data-dir einen Ordner auswählen.')
            existing.append(path)
    if len(existing) > 1:
        raise ValueError('Mehrere bestehende App-Datenordner gefunden: ' + '; '.join(map(str, existing))
                         + '. Mit --data-dir den gewünschten Ordner ausdrücklich auswählen; es wurde nichts verschoben.')
    return existing[0] if existing else preferred.resolve()


def _path(value, label):
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise ValueError(label + ' fehlt. Bitte einen tatsächlichen lokalen Pfad auswählen.')
    # Browsers intentionally hide the original path. A displayed fake path is
    # never an authority for deriving where research results belong.
    parts = str(value).replace('\\', '/').casefold().split('/')
    if 'fakepath' in parts:
        raise ValueError('Der Browser übermittelt keinen tatsächlichen Eingabepfad. Speicherort für Analyseergebnisse auswählen.')
    return Path(value).expanduser().resolve()


def validate_output_location(output_dir):
    """Canonicalize and protect bundled resources before any directory creation."""
    parent = _path(output_dir, 'Speicherort für Analyseergebnisse')
    if getattr(sys, 'frozen', False) and parent.is_relative_to(resource_root()):
        raise ValueError('Gebündelte Programmressourcen sind kein Speicherort für Analyseergebnisse. '
                         'Bitte einen vorhandenen Ordner außerhalb der Programmressourcen auswählen.')
    return parent


def resolve_output_parent(input_path=None, output_dir=None, check_write=False):
    """Return an existing explicit output folder or the actual input's folder.

    No implicit AppData/temporary fallback and no directory creation. The runner
    remains responsible for making a unique run directory below this parent.
    """
    if type(check_write) is not bool:
        raise ValueError('Schreibprüfung muss ein Wahrheitswert sein.')
    if output_dir is not None:
        parent = validate_output_location(output_dir)
    else:
        source = _path(input_path, 'Tatsächlicher Eingabepfad')
        if not source.is_file():
            raise ValueError('Eingabedatei nicht gefunden. Datei erneut auswählen oder Speicherort für Analyseergebnisse festlegen.')
        parent = validate_output_location(source.parent)
    if not parent.is_dir():
        raise ValueError('Speicherort für Analyseergebnisse ist nicht als Ordner verfügbar: '
                         + str(parent) + '. Bitte einen vorhandenen Ordner auswählen.')
    if check_write:
        try:
            with tempfile.NamedTemporaryFile(prefix='.qualitativeanalyse-write-', suffix='.tmp', dir=parent) as probe:
                probe.write(b'write-check')
                probe.flush()
        except OSError as exc:
            raise ValueError('Speicherort für Analyseergebnisse ist nicht beschreibbar oder die Schreibprüfung konnte nicht bereinigt werden: '
                             + str(parent) + '. Bitte ein anderes vorhandenes Ziel auswählen.') from exc
    return parent
