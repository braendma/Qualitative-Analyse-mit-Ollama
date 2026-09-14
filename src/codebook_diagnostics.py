"""Codebook diagnosis from declared, verified coding artifacts; no model calls."""
from coding_validation_common import load_codebook, load_segments
from codebook_diagnostics_core import analyze_codebook, render_codebook_diagnostics
from diagnostic_cli import run_diagnostic
from diagnostic_sources import load_input_context, load_declared_artifact
from progress_events import track_module
from codebook_repetition_links import project_repetition_source

SOURCES = {'code_verification': 'verification', 'blind_coding': 'blind',
           'coding_agreement': 'agreement', 'review_queue': 'review'}


def load_codebook_snapshot(directory, config_path, input_path):
    config, manifest, book_path = load_input_context(directory, config_path, input_path, require_codebook=True)
    codebook, _ = load_codebook(book_path)
    stages, payloads, repetitions = {}, {}, {}
    segments = load_segments(input_path, config['columns'])
    for module in config.get('pipeline', {}).get('modules', []):
        mid = module['id']
        if mid not in SOURCES and mid not in ('stability', 'sensitivity'):
            continue
        if mid in stages:
            raise ValueError('Codebook-Diagnose abgelehnt: doppelte Quellmodul-ID.')
        stage = stages[mid] = load_declared_artifact(directory, module, manifest)
        if stage['status'] == 'available':
            payload = stage.pop('payload')
            if mid in SOURCES:
                payloads[SOURCES[mid]] = payload
            else:
                try:
                    provenance = payload.get('source_provenance', {})
                    if any(provenance.get(key) != manifest['provenance'].get(key)
                           for key in ('input_sha256', 'codebook_sha256')):
                        raise ValueError('Wiederholungsbericht gehört zu anderen Eingaben.')
                    projected = project_repetition_source(payload, mid, segments, codebook,
                        config.get('coding_agreement', {}).get('label_mode', 'single_label'))
                    repetitions[mid] = {**projected, 'artifact': stage['artifact']}
                except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
                    stage.update(status='invalid', reason='Wiederholungsquelle passt nicht zu Material, Kategoriensystem oder Vergleichsschema.')
        if mid in ('stability', 'sensitivity') and mid not in repetitions:
            repetitions[mid] = {'kind': mid, 'status': stage['status']}
    for mid in ('stability', 'sensitivity'):
        repetitions.setdefault(mid, {'kind': mid, 'status': 'unavailable'})
    for mid, parameter in (('coding_agreement', 'agreement'), ('review_queue', 'review')):
        if parameter in payloads and any(name not in payloads for name in ('verification', 'blind')):
            stages[mid].update(status='invalid', reason='Zugehörige Verifikation oder Blindcodierung fehlt; kein unabhängiger Quellabgleich möglich.')
            del payloads[parameter]
    return {'segments': segments, 'codebook': codebook, 'repetition_diagnostics': repetitions,
            'settings': config.get('coding_agreement', {}), 'stages': stages, 'payloads': payloads,
            'codebook_source': {'sha256': manifest['provenance']['codebook_sha256'], 'file': book_path.name}}


def analyze_snapshot(snapshot):
    try:
        result = analyze_codebook(snapshot['segments'], snapshot['codebook'], settings=snapshot['settings'], **snapshot['payloads'])
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError('Codebook-Diagnose abgelehnt: ' + str(exc)) from exc
    if any(stage['status'] == 'invalid' or (stage['status'] == 'unavailable' and stage.get('reason') != 'disabled')
           for stage in snapshot['stages'].values()):
        result['processing_status'] = 'incomplete'
    result['codebook_source'] = snapshot['codebook_source']
    result['repetition_diagnostics'] = snapshot.get('repetition_diagnostics', {})
    return result


@track_module
def main(argv=None):
    run_diagnostic('codebook_diagnostics', 'codebook_diagnostics', 'Hinweise zum gespeicherten Kategoriensystem',
                   analyze_snapshot, render_codebook_diagnostics, argv, loader=load_codebook_snapshot)


if __name__ == '__main__':
    main()
