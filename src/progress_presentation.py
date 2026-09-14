"""Shared, content-free presentation for local and private progress messages."""
import math


def module_overview(done, total):
    if type(done) is not int or type(total) is not int or not 0 <= done <= total <= 100:
        return []
    lines = [f'Module abgeschlossen: {done}/{total}']
    if total:
        cells = min(total, 20)
        filled = done * cells // total
        lines.append('▰' * filled + '▱' * (cells - filled) + ' · Modulübersicht')
    return lines


def phase_lines(detail, labels):
    phase = detail.get('phase')
    if not isinstance(phase, str) or phase not in labels:
        return []
    title = labels[phase]
    level = detail.get('phase_level')
    if phase == 'reduction_level':
        if type(level) is int and 1 <= level <= 100:
            title += f' {level}'
        return [title, 'Teilfortschritt dieser Ebene; weitere Ebenen können folgen.']
    return [title]


def request_age_lines(detail, now):
    active = detail.get('active_requests')
    is_active = (type(active) is int and active > 0) if type(active) is int else detail.get('request_active') is True
    stamp = detail.get('request_started_at')
    if not is_active or type(stamp) not in (int, float) or not math.isfinite(stamp) or not 0 < stamp <= now:
        return []
    seconds = int(now - stamp)
    age = f'{seconds} Sekunden' if seconds < 60 else f'{seconds // 60} Minuten'
    return [f'Letzter Anfragestart vor {age}.']


def unknown_work_lines(module):
    lines = ['⏳ In Bearbeitung · Fortschritt noch nicht beziffert']
    if module == 'overall_synthesis':
        lines.append('Die Gesamtsynthese kann mehrere Verdichtungsrunden benötigen.')
    lines.append('Keine Gesamtzahl gemeldet; Antwortzahl zeigt Aktivität, keinen Prozentwert.')
    return lines


# Status projections contain only built-in states and bounded numeric counters.
# They are display hints, not evidence of completed or verified analysis outputs.
SERIES_STATES = {'starting', 'running', 'finishing', 'paused', 'failed', 'unavailable'}
PROGRESS_PHASES = {'preparation', 'analysis', 'person_reduction', 'comparison',
    'synthesis', 'reduction_level', 'finished', 'cluster_summaries', 'overall_summary',
    'repetitions', 'paused'}
PROGRESS_UNITS = {'passages', 'rows', 'batches', 'categories', 'persons', 'summaries',
    'dimensions', 'pairs', 'steps', 'repetitions'}


def safe_numeric_progress(value):
    """Drop all research content, arbitrary labels and unbounded scalar values."""
    if not isinstance(value, dict):
        return {}
    out = {}
    for key in ('completed', 'total', 'requests', 'active_requests', 'reused', 'failed',
                'phase_level', 'detail_completed', 'detail_total', 'context_required', 'context_limit'):
        item = value.get(key)
        if type(item) is int and 0 <= item <= 10000000:
            out[key] = item
    for key in ('request_active', 'context_blocked'):
        if type(value.get(key)) is bool:
            out[key] = value[key]
    for key in ('updated_at', 'last_response_at', 'request_started_at'):
        item = value.get(key)
        if type(item) in (int, float) and math.isfinite(item) and 0 < item < 100000000000:
            out[key] = item
    for key, allowed in (('phase', PROGRESS_PHASES), ('unit', PROGRESS_UNITS)):
        if isinstance(value.get(key), str) and value[key] in allowed:
            out[key] = value[key]
    return out


def safe_series_progress(value):
    """Whitelist nested series status independently of any sender or renderer."""
    if not isinstance(value, dict):
        return None
    out = {}
    for key in ('sample_number', 'sample_total', 'configuration_number', 'configuration_total',
                'repetition_number', 'repetition_total', 'modules_completed', 'modules_total'):
        item = value.get(key)
        if type(item) is int and 0 <= item <= 10000:
            out[key] = item
    if isinstance(value.get('state'), str) and value['state'] in SERIES_STATES:
        out['state'] = value['state']
    # The module identifier is resolved against a fixed catalog by the consumer.
    # Do not carry names, arbitrary variant IDs, paths or manifest contents.
    from diagnostic_repetitions import ANALYSES
    if isinstance(value.get('module'), str) and value['module'] in ANALYSES:
        out['module'] = value['module']
    if isinstance(value.get('detail'), dict):
        out['detail'] = safe_numeric_progress(value['detail'])
    return out
