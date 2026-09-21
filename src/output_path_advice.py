"""Path advice and sync-bound preflight for NEW runs; never relocate old runs.

Lengths use a representative generated checkpoint path, not a promise covering
every configured output name, filesystem, cloud library or synchronisation app.
"""
import os
from pathlib import Path
import sys

from filesystem_paths import canonical_path


RUN_NAME_RESERVE = '20000101T000000-00000000'


def _path_limits(path):
    """Known local sync bounds, not a remote library or Explorer guarantee."""
    path = canonical_path(path)
    units = lambda value: len(str(value).encode('utf-16-le')) // 2
    reasons = []
    if any(units(part) > 255 for part in path.parts if part != path.anchor):
        reasons.append('eine Datei-/Ordnerkomponente überschreitet 255 UTF-16-Zeichen')
    relatives = []
    for key in ('OneDrive', 'OneDriveConsumer', 'OneDriveCommercial'):
        value = os.environ.get(key)
        if not value or not Path(value).is_absolute():
            continue
        try:
            relative = path.relative_to(canonical_path(value))
        except ValueError:
            continue
        relatives.append(units(relative.as_posix()))
    if relatives:
        cloud = max(relatives)
        if cloud > 400:
            reasons.append(f'OneDrive-relativer Pfad {cloud} überschreitet 400 UTF-16-Zeichen')
        if units(path) > 520:
            reasons.append(f'lokaler OneDrive-Pfad {units(path)} überschreitet 520 UTF-16-Zeichen')
    return reasons


def require_new_output_paths(run_root, modules, *, plans=()):
    """Reject overlong NEW layouts before inference; never relocate/resume data.

    Uses configured output names and actual planned diagnostic sample names.
    Checkpoint names reserve all SHA256 bits and the longer internal namespaces;
    this conservative reservation is identified explicitly in the error. Custom
    module side outputs and remote library prefixes cannot be predicted here.
    """
    run_root = canonical_path(run_root)

    def check(path, kind):
        reasons = _path_limits(path)
        if reasons:
            raise ValueError('Neuer Ergebnislauf abgewiesen: ' + '; '.join(reasons)
                             + f' ({kind}). Einen kürzeren Ergebnisordner wählen. '
                               'Bestehende Läufe bleiben unverändert. Die Prüfung bestätigt keine Cloud-Synchronisation.')

    def outputs(root, selected):
        check(root / 'workflow_manifest.json', 'Laufmanifest')
        for module in selected:
            for name in module.get('outputs', []):
                check(root / name, 'deklarierte Modulausgabe')
            check(root / ('execution_' + module['id'] + '.log'), 'Modulprotokoll')
            if module.get('requires_model', True):
                # Current internal helpers may use a namespace longer than the
                # module ID; the thematic namespace is the longest suffix.
                namespace = max((module['id'] + '_thematic_assignments',
                                 'comparison_person_reduction'), key=len)
                check(root / '_checkpoints' / namespace / ('a' * 52 + '.json'),
                      'konservative Reserve für Teil-Checkpoints')

    outputs(run_root, modules)
    for plan in plans:
        if not plan:
            continue
        series = run_root / ('_' + plan['kind'] + '_repetitions')
        if plan['kind'] == 'sensitivity':
            configs = {item['configuration_id']: item['config'] for item in plan['configurations']}
        else:
            configs = {'baseline': plan['config']}
        for sample in plan['samples']:
            config = configs[sample.get('configuration_id', 'baseline')]
            selected = [module for module in config['pipeline']['modules'] if module.get('enabled', True)]
            outputs(series / sample['sample_id'] / RUN_NAME_RESERVE, selected)
            check(series / (sample['sample_id'] + '.supervision.request.json'), 'Serienaufsicht')


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
    if cloud_units is not None and (cloud_units > 400 or units > 520):
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
