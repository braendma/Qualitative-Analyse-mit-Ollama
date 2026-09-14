"""Optional runner module: controlled repetitions followed by a verified diagnosis."""
import os
from pathlib import Path
import sys

import yaml

from diagnostic_cli import run_diagnostic
from diagnostic_repetitions import prepare_repetitions
from diagnostic_series import _inside, execute_repetitions
from diagnostic_sources import load_input_context
from progress_events import begin_phase, update_progress
from stability_report import render_stability
from stability_series import load_stability_series

SERIES_DIRECTORY = '_stability_repetitions'
PAUSED_EXIT_CODE = 75


def planning_summary(plan):
    if plan is None:
        return None
    return {key: plan[key] for key in ('repetitions', 'requested_modules', 'effective_modules',
            'added_prerequisites', 'module_executions', 'model_calls')}


def configured_plan(config_path):
    """Preflight uses the same planner as execution, before any model is started."""
    config = yaml.safe_load(Path(config_path).read_text(encoding='utf-8'))
    enabled = [m for m in config.get('pipeline', {}).get('modules', [])
               if m.get('id') == 'stability' and m.get('enabled', True)]
    if not enabled:
        return None
    if len(enabled) != 1 or enabled[0].get('starts_child_runs') is not True or enabled[0].get('requires_model') is not True:
        raise ValueError('Stabilität benötigt genau ein Modellmodul mit starts_child_runs: true.')
    if enabled[0].get('script') != 'stability_analysis.py':
        raise ValueError('Stabilitätsmodul benötigt das mitgelieferte Modulskript.')
    diagnostics = config.get('diagnostics', {})
    settings = diagnostics.get('stability') if isinstance(diagnostics, dict) else None
    if not isinstance(settings, dict) or set(settings) - {'modules', 'repetitions'}:
        raise ValueError('diagnostics.stability benötigt modules und optional repetitions (2–20).')
    return prepare_repetitions(config_path, settings.get('modules'), repetitions=settings.get('repetitions', 3))


def _load_context(directory, config_path, input_path):
    root = Path(directory).resolve()
    config, manifest, book_path = load_input_context(root, config_path, input_path, require_codebook=True)
    if (os.environ.get('WORKFLOW_RUN_ID') != manifest.get('run_id') or
            os.environ.get('WORKFLOW_FINGERPRINT') != manifest.get('fingerprint') or
            os.environ.get('WORKFLOW_MODULE') != 'stability' or
            manifest.get('module_status', {}).get('stability') != 'running'):
        raise ValueError('Stabilitätsmodul über den zugehörigen Workflow-Runner starten oder fortsetzen.')
    plan = configured_plan(config_path)
    if plan is None:
        raise ValueError('Stabilitätsmodul ist nicht aktiviert.')
    series = root / SERIES_DIRECTORY
    _inside(series, root)
    if any(Path(path).resolve().is_relative_to(series) for path in (config_path, input_path, book_path)):
        raise ValueError('Originaleingaben dürfen nicht im internen Wiederholungsverzeichnis liegen.')
    return {'plan': plan, 'directory': series, 'stages': {}}


def _analyze(context):
    def progress(completed, total):
        update_progress(phase='repetitions', completed=completed, total=total, unit='repetitions')
    series = execute_repetitions(context['plan'], context['directory'],
        resume=context['directory'].exists(), pause_file=os.environ.get('WORKFLOW_PAUSE_FILE'), progress=progress)
    begin_phase('comparison')
    result = load_stability_series(context['directory'])
    result['series_status'] = series['status']
    if series['status'] != 'success':
        result['processing_status'] = 'incomplete'
    return result


def main(argv=None):
    begin_phase('preparation')
    result = run_diagnostic('stability', 'stability', 'Stabilität kontrollierter Wiederholungen',
        _analyze, render_stability, argv, loader=_load_context, reserved_subdirectories=(SERIES_DIRECTORY,))
    if result['series_status'] == 'paused':
        update_progress(phase='paused')
        return PAUSED_EXIT_CODE
    if result['processing_status'] != 'completed':
        raise RuntimeError('Stabilitätsanalyse unvollständig. Ausschlussgründe im Teilbericht und Serienlog prüfen; dann denselben Lauf fortsetzen.')
    update_progress(phase='finished', completed=1, total=1, unit='steps')
    return 0


if __name__ == '__main__':
    sys.exit(main())
