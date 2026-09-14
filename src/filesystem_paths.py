"""Separate Windows IO syntax from canonical identity and visible paths.

No drive mapping, filesystem alias, registry change or alternate output folder.
Only ordinary absolute drive/UNC paths are accepted by the Windows adapter.
"""
import ntpath
import os
from pathlib import Path


def _ordinary_windows(value):
    raw = str(value).replace('/', '\\')
    folded = raw.casefold()
    if any(ord(char) < 32 for char in raw):
        raise ValueError('Steuerzeichen sind in Windows-Dateipfaden nicht zulässig.')
    if folded.startswith('\\\\?\\') and any(part in ('.', '..') for part in raw.split('\\')):
        raise ValueError('Erweiterte Windows-Pfade dürfen keine relativen Punkt-Komponenten enthalten.')
    if folded.startswith('\\\\?\\unc\\'):
        raw = '\\\\' + raw[8:]
    elif folded.startswith('\\\\?\\'):
        raw = raw[4:]
        if len(raw) < 3 or raw[1:3] != ':\\' or not raw[0].isalpha():
            raise ValueError('Nur normale Laufwerks- oder Netzwerkpfade verwenden; Gerätepfade sind nicht zulässig.')
    elif folded.startswith(('\\\\.\\', '\\??\\')):
        raise ValueError('Gerätepfade sind kein zulässiger Datei- oder Ergebnisordner.')
    drive, tail = ntpath.splitdrive(raw)
    if drive.startswith('\\\\') and len([part for part in drive[2:].split('\\') if part]) != 2:
        raise ValueError('Ein Netzwerkpfad benötigt Server und Freigabe.')
    if (drive and not drive.startswith('\\\\') and not tail.startswith('\\')) or (not drive and raw.startswith('\\')):
        raise ValueError('Laufwerksrelative Pfade sind mehrdeutig. Einen vollständigen Pfad auswählen.')
    return raw


def absolute_path(value):
    """Lexical absolute form without following symlinks or hiding redirection."""
    raw = os.fspath(value)
    if os.name == 'nt':
        raw = _ordinary_windows(raw)
        _, tail = ntpath.splitdrive(raw)
        for part in tail.split('\\'):
            if not part or part in ('.', '..'):
                continue
            stem = part.split('.')[0].upper()
            if (':' in part or part.endswith((' ', '.'))
                    or stem in {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'}
                    or stem in {base + digit for base in ('COM', 'LPT') for digit in '123456789¹²³'}):
                raise ValueError('Mehrdeutiger Windows-Dateiname. Gerätebezeichnungen, Datenströme sowie '
                                 'abschließende Punkte oder Leerzeichen sind nicht zulässig.')
    return Path(os.path.abspath(os.path.expanduser(raw)))


def io_path(value):
    """Absolute filesystem path; Windows extended syntax survives descendants."""
    path = absolute_path(value)
    if os.name != 'nt':
        return path
    raw = str(path)
    drive, tail = ntpath.splitdrive(raw)
    if not drive or (tail and not tail.startswith('\\')):
        raise ValueError('Ein vollständiger Laufwerks- oder Netzwerkpfad wird benötigt.')
    if raw.startswith('\\\\'):
        return Path('\\\\?\\UNC\\' + raw[2:])
    return Path('\\\\?\\' + raw)


def canonical_path(value):
    """One comparable identity for ordinary/extended syntax and reparsepoints."""
    resolved = io_path(value).resolve()
    return absolute_path(resolved)


def process_directory(value):
    """Process cwd has a separate Windows limit; fail with a repair instruction."""
    directory = canonical_path(value)
    if not io_path(directory).is_dir():
        raise ValueError('Arbeitsordner des Programms fehlt. Installation erneut entpacken.')
    if os.name == 'nt' and len(str(directory).encode('utf-16-le')) // 2 >= 248:
        raise ValueError('Der Programmordner ist für Windows-Unterprozesse zu tief verschachtelt. '
                         'Das vollständige Programmpaket in einen kürzeren Ordner entpacken und erneut starten.')
    return directory
