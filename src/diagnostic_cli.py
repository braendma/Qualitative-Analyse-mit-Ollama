"""Shared read-only diagnostic CLI guard, using the existing runner output contract."""
import argparse
import json
import os
from pathlib import Path
import yaml

from diagnostic_sources import load_snapshot
from coding_validation_common import resolve_config_path
from runtime_support import atomic_json, atomic_text


def run_diagnostic(module_id, stem, description, analyze, render, argv=None, *, loader=load_snapshot, reserved_subdirectories=()):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--config', required=True)
    parser.add_argument('--input-csv', required=True)
    parser.add_argument('--run-dir', default='.')
    parser.add_argument('--out-json', default=stem + '.json')
    parser.add_argument('--out-md', default=stem + '.md')
    args = parser.parse_args(argv)
    directory = Path(args.run_dir).resolve()
    manifest = json.loads((directory / 'workflow_manifest.json').read_text(encoding='utf-8'))
    outputs = [Path(args.out_json).resolve(), Path(args.out_md).resolve()]
    reserved = [(directory / name).resolve() for name in reserved_subdirectories]
    if any(path.is_relative_to(folder) for path in outputs for folder in reserved):
        raise ValueError('Diagnoseausgaben dürfen keine internen Serienverzeichnisse überschreiben.')
    protected = {Path(args.config).resolve(), Path(args.input_csv).resolve(),
                 directory / 'workflow_manifest.json', directory / 'config_snapshot.yaml'}
    protected.update((directory / name).resolve() for name in manifest.get('output_hashes', {}))
    config = yaml.safe_load(Path(args.config).read_text(encoding='utf-8'))
    if isinstance(config, dict) and config.get('paths', {}).get('category_system_csv'):
        protected.add(resolve_config_path(args.config, None, config['paths']['category_system_csv']))
    if len(set(outputs)) != 2 or any(path in protected for path in outputs):
        raise ValueError('Diagnoseausgaben dürfen keine Eingaben oder gespeicherten Ergebnisse überschreiben.')
    resuming = (os.environ.get('WORKFLOW_RUN_ID') == manifest.get('run_id') and
                os.environ.get('WORKFLOW_MODULE') == module_id and
                manifest.get('module_status', {}).get(module_id) == 'running')
    if any(path.exists() for path in outputs) and not resuming:
        raise ValueError('Diagnoseausgabe existiert bereits. Neue Dateinamen verwenden.')
    snapshot = loader(args.run_dir, args.config, args.input_csv)
    result = analyze(snapshot)
    result['source_artifacts'] = {mid: {k: stage[k] for k in ('status', 'artifact', 'sha256', 'reason', 'warnings') if k in stage}
                                for mid, stage in snapshot['stages'].items()}
    atomic_json(args.out_json, result)
    atomic_text(args.out_md, render(result))
    return result
