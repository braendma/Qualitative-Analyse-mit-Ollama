"""Shared read-only diagnostic CLI guard, using the existing runner output contract."""
import argparse
import json
import os
import yaml

from diagnostic_sources import load_snapshot
from coding_validation_common import resolve_config_path
from runtime_support import atomic_json, atomic_text
from filesystem_paths import canonical_path, io_path


def run_diagnostic(module_id, stem, description, analyze, render, argv=None, *, loader=load_snapshot, reserved_subdirectories=()):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--config', required=True)
    parser.add_argument('--input-csv', required=True)
    parser.add_argument('--run-dir', default='.')
    parser.add_argument('--out-json', default=stem + '.json')
    parser.add_argument('--out-md', default=stem + '.md')
    args = parser.parse_args(argv)
    directory = canonical_path(args.run_dir)
    manifest = json.loads(io_path(directory / 'workflow_manifest.json').read_text(encoding='utf-8'))
    outputs = [canonical_path(args.out_json), canonical_path(args.out_md)]
    reserved = [canonical_path(directory / name) for name in reserved_subdirectories]
    if any(path.is_relative_to(folder) for path in outputs for folder in reserved):
        raise ValueError('Diagnoseausgaben dürfen keine internen Serienverzeichnisse überschreiben.')
    config_path, input_path = canonical_path(args.config), canonical_path(args.input_csv)
    protected = {config_path, input_path, canonical_path(directory / 'workflow_manifest.json'),
                 canonical_path(directory / 'config_snapshot.yaml')}
    protected.update(canonical_path(directory / name) for name in manifest.get('output_hashes', {}))
    config = yaml.safe_load(io_path(config_path).read_text(encoding='utf-8'))
    if isinstance(config, dict) and config.get('paths', {}).get('category_system_csv'):
        protected.add(canonical_path(resolve_config_path(args.config, None, config['paths']['category_system_csv'])))
    if len(set(outputs)) != 2 or any(path in protected for path in outputs):
        raise ValueError('Diagnoseausgaben dürfen keine Eingaben oder gespeicherten Ergebnisse überschreiben.')
    resuming = (os.environ.get('WORKFLOW_RUN_ID') == manifest.get('run_id') and
                os.environ.get('WORKFLOW_MODULE') == module_id and
                manifest.get('module_status', {}).get(module_id) == 'running')
    if any(io_path(path).exists() for path in outputs) and not resuming:
        raise ValueError('Diagnoseausgabe existiert bereits. Neue Dateinamen verwenden.')
    snapshot = loader(io_path(directory), io_path(config_path), io_path(input_path))
    result = analyze(snapshot)
    result['source_artifacts'] = {mid: {k: stage[k] for k in ('status', 'artifact', 'sha256', 'reason', 'warnings') if k in stage}
                                for mid, stage in snapshot['stages'].items()}
    atomic_json(io_path(outputs[0]), result)
    atomic_text(io_path(outputs[1]), render(result))
    return result
