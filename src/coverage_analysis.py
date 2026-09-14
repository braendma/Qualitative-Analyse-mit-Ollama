"""Coverage CLI using the existing pipeline's config, manifest and report contracts."""
import argparse
import json
import os
from pathlib import Path

from coverage_core import analyze_coverage, render_coverage
from diagnostic_sources import load_snapshot
from progress_events import track_module
from runtime_support import atomic_json, atomic_text


@track_module
def main(argv=None):
    parser = argparse.ArgumentParser(description='Coverage aus vorhandenen verifizierten Analyseergebnissen')
    parser.add_argument('--config', required=True)
    parser.add_argument('--input-csv', required=True)
    parser.add_argument('--run-dir', default='.')
    parser.add_argument('--out-json', default='coverage.json')
    parser.add_argument('--out-md', default='coverage.md')
    args = parser.parse_args(argv)
    directory = Path(args.run_dir).resolve()
    manifest = json.loads((directory / 'workflow_manifest.json').read_text(encoding='utf-8'))
    outputs = [Path(args.out_json).resolve(), Path(args.out_md).resolve()]
    protected = {Path(args.config).resolve(), Path(args.input_csv).resolve(),
                 directory / 'workflow_manifest.json', directory / 'config_snapshot.yaml'}
    protected.update((directory / name).resolve() for name in manifest.get('output_hashes', {}))
    if len(set(outputs)) != 2 or any(path in protected for path in outputs):
        raise ValueError('Diagnoseausgaben dürfen keine Eingaben oder gespeicherten Ergebnisse überschreiben.')
    # A runner may retry an unfinished module; standalone exports need fresh names.
    resuming = (os.environ.get('WORKFLOW_RUN_ID') == manifest.get('run_id') and
                os.environ.get('WORKFLOW_MODULE') == 'coverage' and
                manifest.get('module_status', {}).get('coverage') == 'running')
    if any(path.exists() for path in outputs) and not resuming:
        raise ValueError('Diagnoseausgabe existiert bereits. Neue Dateinamen verwenden.')
    snapshot = load_snapshot(args.run_dir, args.config, args.input_csv)
    result = analyze_coverage(snapshot)
    result['source_artifacts'] = {mid: {k: stage[k] for k in ('status', 'artifact', 'sha256', 'reason') if k in stage}
                                for mid, stage in snapshot['stages'].items()}
    atomic_json(args.out_json, result)
    atomic_text(args.out_md, render_coverage(result))


if __name__ == '__main__':
    main()
