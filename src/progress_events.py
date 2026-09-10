"""Best-effort numeric progress; never put research content in status files."""
import json
import os
import time
from pathlib import Path
from runtime_support import atomic_json


def update_progress(**changes):
    path=os.environ.get('WORKFLOW_PROGRESS_FILE')
    if not path:return
    try:
        data=json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).exists() else {}
        allowed={'completed','total','unit','requests','request_active','last_response_at','request_started_at'}
        data.update({k:v for k,v in changes.items() if k in allowed})
        data.update(module=os.environ.get('WORKFLOW_MODULE',''),updated_at=time.time())
        atomic_json(path,data)
    except (OSError,ValueError):
        pass  # Status display must not turn a successful analysis into a failure.


def request_event(start=False):
    path=os.environ.get('WORKFLOW_PROGRESS_FILE')
    if not path:return
    try:
        data=json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).exists() else {}
        if start:update_progress(request_active=True,request_started_at=time.time())
        else:update_progress(request_active=False,last_response_at=time.time(),requests=int(data.get('requests',0))+1)
    except (OSError,ValueError):pass
