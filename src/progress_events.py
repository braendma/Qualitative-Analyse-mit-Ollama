"""Best-effort numeric progress; never put research content in status files."""
import json
import os
import time
import threading
from pathlib import Path
from runtime_support import atomic_json

LOCK = threading.RLock()
ACTIVE_REQUESTS = 0


def update_progress(**changes):
    with LOCK:
        _update_progress(**changes)


def _update_progress(**changes):
    path=os.environ.get('WORKFLOW_PROGRESS_FILE')
    if not path:return
    try:
        data=json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).exists() else {}
        allowed={'completed','total','unit','requests','active_requests','request_active','last_response_at','request_started_at',
                 'reused','failed','failure_kind','context_required','context_limit','context_blocked','phase',
                 'phase_level','detail_completed','detail_total'}
        if data.get('module') != os.environ.get('WORKFLOW_MODULE',''):
            data = {}
        data.update({k:v for k,v in changes.items() if k in allowed})
        data.update(module=os.environ.get('WORKFLOW_MODULE',''),updated_at=time.time())
        atomic_json(path,data)
    except (OSError,ValueError):
        pass  # Status display must not turn a successful analysis into a failure.


def request_event(start=False, success=True):
    with LOCK:
        _request_event(start, success)


def _request_event(start, success):
    global ACTIVE_REQUESTS
    ACTIVE_REQUESTS = ACTIVE_REQUESTS + 1 if start else max(0, ACTIVE_REQUESTS - 1)
    path=os.environ.get('WORKFLOW_PROGRESS_FILE')
    if not path:return
    try:
        data=json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).exists() else {}
        changes = {'request_active': ACTIVE_REQUESTS > 0, 'active_requests': ACTIVE_REQUESTS}
        if start: changes['request_started_at'] = time.time()
        elif success: changes.update(last_response_at=time.time(), requests=int(data.get('requests',0))+1)
        update_progress(**changes)
    except (OSError,ValueError):pass


def begin_phase(phase, total=None, unit='steps', level=None):
    """Reset a phase's counts without discarding module-wide response counters."""
    update_progress(phase=phase, completed=0, total=total, unit=unit,
                    phase_level=level, detail_completed=None, detail_total=None)


def track_module(function):
    """Every CLI has visible preparation and a success boundary, even CPU-only ones."""
    from functools import wraps
    @wraps(function)
    def tracked(*args, **kwargs):
        begin_phase('preparation')
        result = function(*args, **kwargs)
        update_progress(phase='finished', completed=1, total=1, unit='steps',
                        detail_completed=None, detail_total=None)
        return result
    return tracked
