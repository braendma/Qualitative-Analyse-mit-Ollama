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
