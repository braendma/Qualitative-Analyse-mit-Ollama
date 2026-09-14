"""Descriptive execution counts from the existing, validated repetition plans.

No I/O, model calls, scheduling or second planner. Counts describe a fresh run,
not time, tokens, price or remaining work when resuming checkpoints.
"""


def effort_summary(modules, *, stability=None, sensitivity=None):
    rows = {m['id']: {'id': m['id'], 'name': m['name'],
            'cost_profile': m.get('cost_profile'), 'main': 1,
            'stability': 0, 'sensitivity': 0, 'total': 1} for m in modules}
    series = []
    for kind, plan in (('stability', stability), ('sensitivity', sensitivity)):
        if plan is None:
            continue
        if kind not in rows:
            raise ValueError('Aufwandplan enthält eine nicht aktivierte Diagnose: ' + kind)
        repetitions = plan['repetitions']
        configurations = plan.get('configuration_count', 1)
        targets = plan['effective_modules']
        if (type(repetitions) is not int or repetitions < 2
                or type(configurations) is not int or configurations < 1
                or len(targets) != len(set(targets)) or not targets
                or not set(targets) <= set(rows)
                or any(mid in ('stability', 'sensitivity') for mid in targets)
                or plan['module_executions'] != repetitions * configurations * len(targets)):
            raise ValueError('Inkonsistenter Aufwandplan für ' + kind)
        runs = repetitions * configurations
        for mid in targets:
            rows[mid][kind] += runs
            rows[mid]['total'] += runs
        series.append({'id': kind, 'configuration_count': configurations,
            'repetitions': repetitions, 'run_count': runs,
            'effective_modules': list(targets), 'module_executions': plan['module_executions']})
    planned = {s['id'] for s in series}
    unknown = [m['id'] for m in modules if m.get('starts_child_runs') and m['id'] not in planned]
    additional = sum(s['module_executions'] for s in series)
    return {'basis': 'fresh_run', 'main_module_executions': len(modules),
        'additional_module_executions': additional,
        'known_module_executions': len(modules) + additional,
        'total_module_executions': None if unknown else len(modules) + additional,
        'model_calls_estimate': 0 if modules and all(m.get('requires_model') is False for m in modules) else None,
        'unplanned_child_modules': unknown,
        'series': series, 'modules': list(rows.values())}
