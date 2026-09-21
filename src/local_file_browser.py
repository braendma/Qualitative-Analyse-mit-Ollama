"""Read-only local selections for the authenticated app, with bounded I/O."""
from itertools import islice
import os
from pathlib import Path
import stat

MAX_ENTRIES = 1000
KINDS = {'directory', 'segments', 'codebook', 'audio'}
EXTENSIONS = {'.csv', '.xlsx'}


def _absolute(value):
    if not isinstance(value, (str, Path)) or not str(value).strip() or '\0' in str(value):
        raise ValueError('Bitte einen vollständigen lokalen Pfad auswählen.')
    path = Path(value)
    if not path.is_absolute():
        raise ValueError('Bitte einen absoluten Pfad auf dem Rechner der Anwendung auswählen.')
    return path


def _linked(info):
    if stat.S_ISLNK(info.st_mode):
        return True
    if not getattr(info, 'st_file_attributes', 0) & 0x400:
        return False
    # OneDrive cloud placeholders are reparse points too, but are not links.
    # Name-surrogate tags (symlinks/junctions) redirect path resolution; reject
    # these and unknown metadata, while retaining ordinary cloud placeholders.
    tag = getattr(info, 'st_reparse_tag', None)
    return tag is None or bool(tag & 0x20000000)


def _windows_roots():
    # GetLogicalDrives reads the local drive mask. Do not stat/probe each drive:
    # mapped network drives and disconnected media must not stall the dialog.
    import ctypes
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    return [{'name': chr(65 + i) + ':', 'path': chr(65 + i) + ':\\'}
            for i in range(26) if mask & (1 << i)]


def _roots():
    home = Path.home().resolve()
    values = [{'name': 'Persönlicher Ordner', 'path': str(home)}]
    values.extend(_windows_roots() if os.name == 'nt' else [{'name': '/', 'path': '/'}])
    return list({row['path']: row for row in values}.values())


def browse(path='', kind='directory'):
    """List direct visible children only; a reached scan limit is conservative.

    truncated=True means the 1000-entry inspection limit was reached, not a
    count of additional visible matches. Hidden/nonmatching items use the budget.
    No folder is created, and no file content or writeability is inspected.
    """
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError('Unbekannte Art der Datei- oder Ordnerauswahl.')
    try:
        directory = (Path.home() if path == '' else _absolute(path)).resolve()
        if not directory.is_dir():
            raise ValueError('Der gewählte Ordner ist nicht verfügbar. Einen anderen vorhandenen Ordner auswählen.')
        directories, files, inspected = [], [], 0
        with os.scandir(directory) as entries:
            for entry in islice(entries, MAX_ENTRIES):
                inspected += 1
                if entry.name.startswith('.'):
                    continue
                try:
                    info = entry.stat(follow_symlinks=False)
                    if _linked(info) or getattr(info, 'st_file_attributes', 0) & 2:
                        continue
                    child = directory / entry.name
                    if child.resolve() != child:
                        continue
                    row = {'name': entry.name, 'path': str(child)}
                    if stat.S_ISDIR(info.st_mode):
                        directories.append(row)
                    elif kind != 'directory' and stat.S_ISREG(info.st_mode) and child.suffix.lower() in ({'.wav','.mp3','.m4a','.mp4','.flac','.ogg','.wma','.aac'} if kind=='audio' else EXTENSIONS):
                        files.append(row)
                except (OSError, RuntimeError):
                    # A disappearing or inaccessible child is not an alternate path.
                    continue
        order = lambda row: (row['name'].casefold(), row['name'])
        return {'path': str(directory), 'parent': str(directory.parent) if directory.parent != directory else None,
                'roots': _roots(), 'directories': sorted(directories, key=order),
                'files': sorted(files, key=order), 'truncated': inspected == MAX_ENTRIES}
    except (OSError, RuntimeError) as exc:
        raise ValueError('Ordner kann nicht gelesen werden. Zugriffsrechte und Verfügbarkeit prüfen.') from exc


def _file_identity(info):
    # On Windows lstat and fstat can expose different meanings of ctime
    # (creation versus metadata-change time). Compare ctime only within the
    # same API below, never between a path stat and an open-handle stat.
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def read_input(path, max_bytes):
    """Read one unchanged regular input file with an explicit byte limit."""
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError('Das Dateigrößenlimit muss eine positive ganze Zahl sein.')
    selected = _absolute(path)
    if selected.suffix.lower() not in EXTENSIONS:
        raise ValueError('Bitte eine CSV- oder XLSX-Datei auswählen.')
    try:
        before = selected.lstat()
        if _linked(before) or not stat.S_ISREG(before.st_mode):
            raise ValueError('Bitte eine reguläre Datei auswählen; Verknüpfungen werden nicht eingelesen.')
        canonical = selected.resolve()
        if before.st_size > max_bytes:
            raise ValueError('Die ausgewählte Datei überschreitet das erlaubte Größenlimit.')
        with canonical.open('rb') as handle:
            opened = os.fstat(handle.fileno())
            if _file_identity(opened) != _file_identity(before):
                raise ValueError('Datei wurde während der Auswahl verändert. Bitte erneut auswählen.')
            content = handle.read(max_bytes + 1)
            after_read = os.fstat(handle.fileno())
        after = selected.lstat()
        if (len(content) > max_bytes or len(content) != before.st_size
                or _linked(after) or selected.resolve() != canonical
                or _file_identity(after_read) != _file_identity(before)
                or _file_identity(after) != _file_identity(before)
                or after_read.st_ctime_ns != opened.st_ctime_ns
                or after.st_ctime_ns != before.st_ctime_ns):
            raise ValueError('Datei wurde während des Einlesens verändert oder ist zu groß. Bitte erneut auswählen.')
        return canonical, content
    except (OSError, RuntimeError) as exc:
        raise ValueError('Datei kann nicht gelesen werden. Zugriffsrechte und Verfügbarkeit prüfen.') from exc
