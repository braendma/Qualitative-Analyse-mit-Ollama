"""Ownership of the existing supervisor; no alternate runner or process tree."""
import json
from pathlib import Path
import re
import threading

from supervision_receipts import validate_receipt


def supervision_paths(folder, binding):
    if not isinstance(binding, dict) or not re.fullmatch('[a-f0-9]{32}',str(binding.get('attempt',''))):
        raise ValueError('Die gespeicherte Prozesszuordnung ist ungültig.')
    root=Path(folder).resolve()
    if (binding.get('job_folder')!=str(root)
            or not re.fullmatch('[a-f0-9]{64}',str(binding.get('config_sha256','')))
            or not isinstance(binding.get('run_parent'),str) or not Path(binding['run_parent']).is_absolute()):
        raise ValueError('Die Prozesszuordnung passt nicht zum lokalen Jobordner.')
    base=root/'supervision'/binding['attempt']
    paths=[base.with_suffix('.request.json'),base.with_suffix('.json')]
    if any(p.resolve()!=p or not p.is_relative_to(root) for p in paths):
        raise ValueError('Der Pfad der Prozessbestätigung wurde umgeleitet.')
    return paths


def confirmed_cleanup(folder, binding):
    request_path,receipt_path=supervision_paths(folder,binding)
    request=json.loads(request_path.read_text(encoding='utf-8'))
    keys=('attempt','ticket','command_sha256','config_sha256','run_parent','job_folder')
    if not isinstance(request,dict) or any(request.get(k)!=binding.get(k) for k in keys):
        raise ValueError('Die Prozessbestätigung gehört nicht zu diesem Startversuch.')
    receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
    return validate_receipt(receipt,ticket=binding.get('ticket'),
        command_sha256=binding.get('command_sha256'),supervisor_pid=binding.get('supervisor_pid'))


class ActiveRun:
    def __init__(self,project,job,folder,process,binding):
        self.project,self.job,self.folder=project,job,Path(folder)
        self.process,self.binding=process,binding
        self.finished=threading.Event()
        self.finish_lock=threading.Lock()
        self.lease_lock=threading.Lock()
        self.receipt=None
        self.stop_requested=False
        self.thread=None

    def public(self):
        return {'project':self.project,'job':self.job,'attempt':self.binding['attempt']}

    def release(self):
        with self.lease_lock:
            if self.process.stdin and not self.process.stdin.closed:
                self.process.stdin.close()

    def finish(self,timeout=35):
        with self.finish_lock:
            if self.receipt is not None:return self.receipt
            self.process.wait(timeout=timeout)
            self.release()
            self.receipt=confirmed_cleanup(self.folder,self.binding)
            # A Windows venv redirector can own the Popen handle while a child
            # interpreter runs the supervisor. Adopt its PID only after the
            # owned launcher exited and the attempt/slot receipt was verified.
            self.binding['supervisor_pid']=self.receipt['supervisor_pid']
            return self.receipt
