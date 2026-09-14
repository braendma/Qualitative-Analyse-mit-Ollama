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
from failure_help import repetition_failure_marker
from stability_report import render_stability
from stability_series import load_stability_series

SERIES_DIRECTORY = '_stability_repetitions'
PAUSED_EXIT_CODE = 75


def planning_summary(plan):
    if plan is None:
        return None
    summary = {key: plan[key] for key in ('repetitions', 'requested_modules', 'effective_modules',
            'added_prerequisites', 'module_executions', 'model_calls')}
    if plan['kind'] == 'sensitivity':
        summary.update(configuration_count=plan['configuration_count'], total_repetitions=len(plan['samples']),
            configurations=[{'id': c['configuration_id'], 'changes': c['changes'], 'joint_changes': c['joint_changes']}
                            for c in plan['configurations']])
    return summary


def configured_plan(config_path, *, kind='stability'):
    """Preflight uses the same planner as execution, before any model is started."""
    if kind not in ('stability', 'sensitivity'):
        raise ValueError('Unbekannte Wiederholungsdiagnose.')
    name = 'Stabilität' if kind == 'stability' else 'Sensitivität'
    config = yaml.safe_load(Path(config_path).read_text(encoding='utf-8'))
    enabled = [m for m in config.get('pipeline', {}).get('modules', [])
               if m.get('id') == kind and m.get('enabled', True)]
    if not enabled:
        return None
    if len(enabled) != 1 or enabled[0].get('starts_child_runs') is not True or enabled[0].get('requires_model') is not True:
        raise ValueError(name + ' benötigt genau ein Modellmodul mit starts_child_runs: true.')
    if enabled[0].get('script') != kind + '_analysis.py':
        raise ValueError(name + ' benötigt das mitgelieferte Modulskript.')
    diagnostics = config.get('diagnostics', {})
    settings = diagnostics.get(kind) if isinstance(diagnostics, dict) else None
    allowed = {'modules', 'repetitions', 'variants'} if kind == 'sensitivity' else {'modules', 'repetitions'}
    if not isinstance(settings, dict) or set(settings) - allowed:
        raise ValueError('diagnostics.' + kind + ' benötigt modules, repetitions (2–20)' +
                         (' und variants (1–9).' if kind == 'sensitivity' else '.'))
    if kind == 'sensitivity':
        from diagnostic_sensitivity import prepare_sensitivity
        return prepare_sensitivity(config_path, settings.get('modules'), settings.get('variants'),
                                   repetitions=settings.get('repetitions', 2))
    return prepare_repetitions(config_path, settings.get('modules'), repetitions=settings.get('repetitions', 3))


def _load_context(directory, config_path, input_path, *, kind='stability'):
    root = Path(directory).resolve()
    config, manifest, book_path = load_input_context(root, config_path, input_path, require_codebook=True)
    if (os.environ.get('WORKFLOW_RUN_ID') != manifest.get('run_id') or
            os.environ.get('WORKFLOW_FINGERPRINT') != manifest.get('fingerprint') or
            os.environ.get('WORKFLOW_MODULE') != kind or
            manifest.get('module_status', {}).get(kind) != 'running'):
        raise ValueError('Wiederholungsdiagnose über den zugehörigen Workflow-Runner starten oder fortsetzen.')
    plan = configured_plan(config_path, kind=kind)
    if plan is None:
        raise ValueError('Wiederholungsdiagnose ist nicht aktiviert.')
    series = root / ('_' + kind + '_repetitions')
    _inside(series, root)
    if any(Path(path).resolve().is_relative_to(series) for path in (config_path, input_path, book_path)):
        raise ValueError('Originaleingaben dürfen nicht im internen Wiederholungsverzeichnis liegen.')
    return {'plan': plan, 'directory': series, 'stages': {}}


def _analyze(context):
    def progress(completed, total):
        update_progress(phase='repetitions', completed=completed, total=total, unit='repetitions', series_current=None)
    series = execute_repetitions(context['plan'], context['directory'],
        resume=context['directory'].exists(), pause_file=os.environ.get('WORKFLOW_PAUSE_FILE'), progress=progress,
        inner_progress=lambda current: update_progress(series_current=current))
    begin_phase('comparison')
    if context['plan']['kind'] == 'sensitivity':
        from stability_series import load_sensitivity_series
        result = load_sensitivity_series(context['directory'])
    else:
        result = load_stability_series(context['directory'])
    result['series_status'] = series['status']
    if series['status'] != 'success':
        result['processing_status'] = 'incomplete'
    return result


def main(argv=None, *, kind='stability'):
    if kind not in ('stability', 'sensitivity'):
        raise ValueError('Unbekannte Wiederholungsdiagnose.')
    if kind == 'sensitivity':
        from sensitivity_report import render_sensitivity
        renderer, title = render_sensitivity, 'Sensitivität gegenüber geänderten Einstellungen'
    else:
        renderer, title = render_stability, 'Stabilität kontrollierter Wiederholungen'
    begin_phase('preparation')
    result = run_diagnostic(kind, kind, title, _analyze, renderer, argv,
        loader=lambda *args: _load_context(*args, kind=kind), reserved_subdirectories=('_' + kind + '_repetitions',))
    if result['series_status'] == 'paused':
        update_progress(phase='paused')
        return PAUSED_EXIT_CODE
    if result['processing_status'] != 'completed':
        name = 'Stabilitätsanalyse' if kind == 'stability' else 'Sensitivitätsanalyse'
        raise RuntimeError(repetition_failure_marker(result) + name + ' unvollständig. Ausschlussgründe im Teilbericht und Serienlog prüfen; dann denselben Lauf fortsetzen.')
    update_progress(phase='finished', completed=1, total=1, unit='steps')
    return 0


if __name__ == '__main__':
    sys.exit(main())
