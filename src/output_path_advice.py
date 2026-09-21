"""Non-blocking path advice for NEW runs; never move or reject existing runs.

Lengths use a representative generated checkpoint path, not a promise covering
every configured output name, filesystem, cloud library or synchronisation app.
"""
import os
from pathlib import Path
import sys

from filesystem_paths import canonical_path


def output_path_check(parent, *, app_layout=True, diagnostics=True, run_prefix=''):
    parent = canonical_path(parent)
    run = '20000101T000000-00000000'
    relative = Path('QualitativeAnalyse_' + '0' * 20) / 'runs' if app_layout else Path()
    relative /= run_prefix + run
    if diagnostics:
        # Sensitivity permits variant IDs of up to 40 characters. The example
        # intentionally includes this deepest ordinary diagnostic layout.
        relative = relative / '_sensitivity_repetitions' / ('v' * 40 + '-repeat-020') / run
    relative = relative / '_checkpoints' / 'clusterer' / ('a' * 52 + '.json')
    example = parent / relative
    units = len(str(example).encode('utf-16-le')) // 2
    byte_length = len(str(example).encode('utf-8'))
    warnings = []
    if sys.platform == 'win32' and units >= 260:
        warnings.append(
            f'Langer Ergebnispfad: Ein Beispiel-Zwischenstand erreicht hier {units} UTF-16-Zeichen. '
            'Explorer und andere Programme können bei langen Pfaden Probleme haben. '
            'Für neue Läufe einen kürzeren Ergebnisordner näher am Laufwerks- oder Synchronisationsordner wählen.')
    elif sys.platform != 'win32' and byte_length >= 1024:
        warnings.append(
            f'Langer Ergebnispfad: Ein Beispiel-Zwischenstand erreicht hier {byte_length} UTF-8-Bytes. '
            'Andere Programme können damit Probleme haben. Für neue Läufe einen kürzeren Ergebnisordner wählen.')
    # Environment roots identify a locally configured OneDrive location, not
    # the remote library URL or its remaining server-side path allowance.
    cloud_units = None
    for key in ('OneDrive', 'OneDriveConsumer', 'OneDriveCommercial'):
        value = os.environ.get(key)
        if not value or not Path(value).is_absolute():
            continue
        try:
            cloud_relative = example.relative_to(canonical_path(value))
        except ValueError:
            continue
        length = len(cloud_relative.as_posix().encode('utf-16-le')) // 2
        cloud_units = max(cloud_units or 0, length)
    if cloud_units is not None and (cloud_units >= 400 or units >= 520):
        warnings.append(
            'Der Beispielpfad liegt im konfigurierten OneDrive-Ordner und kann dessen Pfadlängengrenzen erreichen. '
            'Vor einem neuen Lauf ein kürzeres Ziel wählen und den Synchronisationsstatus in OneDrive prüfen. '
            'Die entfernte Bibliotheksadresse ist hier nicht bekannt.')
    note = ('Schätzung anhand eines erzeugten Zwischenstandspfads'
            + (' einschließlich verschachtelter Wiederholungsdiagnose und langer Variantenkennung' if diagnostics else '')
            + '. Andere Ausgabedateien können abweichen. Eine erfolgreiche lokale Schreibprüfung bestätigt keine Cloud-Synchronisation. '
              'Bestehende Läufe während der Verarbeitung nicht verschieben oder umbenennen.')
    return {'example_relative_path': relative.as_posix(), 'example_utf16_length': units,
            'example_utf8_bytes': byte_length, 'onedrive_relative_utf16_length': cloud_units,
            'warnings': warnings, 'note': note}


def output_check_message(check):
    return 'Ordner ist verfügbar und beschreibbar. Beim Start wird erneut geprüft. ' + ' '.join(check['warnings']) + ' ' + check['note']
