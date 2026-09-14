"""Owned lifecycle with synthetic runners; no model or cloud calls."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch

from app_lifecycle import ActiveRun,confirmed_cleanup,supervision_paths
from local_app import App,Handler,pid_alive,read_json
from runtime_support import atomic_json,file_hash,fingerprint
from test_review_workspace import fixture
from test_local_app import settings


class FakeLease:
    def __init__(self):self.closed=False
    def close(self):self.closed=True


class FakeProcess:
    def __init__(self):self.pid=987654;self.stdin=FakeLease();self.returncode=None
    def poll(self):return self.returncode
    def wait(self,timeout=None):
        if self.returncode is None:raise subprocess.TimeoutExpired('synthetic',timeout)
        return self.returncode


def session_fixture(tmp):
    app,pid,jid,_,config=fixture(tmp)
    folder=app.project_dir(pid)/'jobs'/jid
    process=FakeProcess()
    binding={'attempt':'b'*32,'ticket':'synthetic-ticket','command_sha256':fingerprint(['synthetic']),
             'config_sha256':file_hash(config),'run_parent':str(folder/'runs'),
             'job_folder':str(folder.resolve()),'supervisor_pid':process.pid}
    request,_=supervision_paths(folder,binding);atomic_json(request,binding)
    job=read_json(folder/'job.json');job.update(status='running',supervision=binding,pid=process.pid)
    atomic_json(folder/'job.json',job)
    session=ActiveRun(pid,jid,folder,process,binding);app._session=session;app.active=jid
    return app,session


def complete(session,status='paused',receipt=True):
    manifest=session.folder/'runs/synthetic/workflow_manifest.json'
    value=read_json(manifest);value['status']=status;atomic_json(manifest,value)
    session.process.returncode=0
    if receipt:
        _,path=supervision_paths(session.folder,session.binding)
        atomic_json(path,{'schema_version':1,'ticket':session.binding['ticket'],
            'command_sha256':session.binding['command_sha256'],'supervisor_pid':session.process.pid,
            'status':'finished','cleanup_confirmed':True,'cleanup_scope':'windows_job' if os.name=='nt' else 'process_group',
            'exit_code':0,'parent_released':session.stop_requested})


def wait_for(predicate,timeout=12):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if predicate():return
        time.sleep(.05)
    raise AssertionError('Synthetic lifecycle did not reach its expected state')


class LifecycleStateTests(unittest.TestCase):
    def test_idle_shutdown_waits_for_response_and_prevents_racing_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp);sent=threading.Event();closed=threading.Event();app._shutdown_callback=closed.set
            result=app.shutdown(response_sent=sent)
            self.assertEqual(result['state'],'stopping');self.assertFalse(closed.is_set())
            with self.assertRaises(ValueError):app.start('a'*20)
            sent.set();wait_for(lambda:app.runtime_status()['state']=='closed')
            self.assertFalse(closed.is_set())
            app.runtime_delivered(result);self.assertFalse(closed.is_set())
            app.runtime_delivered(app.runtime_status());self.assertTrue(closed.wait(2))

    def test_final_http_response_is_delivered_before_server_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp);sent=threading.Event();closed=threading.Event();app._shutdown_callback=closed.set
            app.shutdown(response_sent=sent);sent.set()
            wait_for(lambda:app.runtime_status()['state']=='closed')
            handler=object.__new__(Handler);handler.path='/api/runtime'
            handler.server=SimpleNamespace(app=app);handler.allowed=lambda **kwargs:True
            handler.wfile=Mock()
            def received(status):
                self.assertEqual(status['state'],'closed');self.assertFalse(closed.is_set())
                self.assertFalse(app._shutdown_delivery.is_set())
            handler.json=received
            handler.wfile.flush.side_effect=lambda:self.assertFalse(app._shutdown_delivery.is_set())
            handler.do_GET();self.assertTrue(closed.wait(2));handler.wfile.flush.assert_called_once()

    def test_failed_final_delivery_is_not_acknowledged_and_has_bounded_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp);sent=threading.Event();closed=threading.Event();app._shutdown_callback=closed.set
            # An event spy makes the timeout branch deterministic without sleeping.
            fallback=Mock();fallback.wait.return_value=False;app._shutdown_delivery=fallback
            app.shutdown(response_sent=sent);sent.set();self.assertTrue(closed.wait(2))
            fallback.wait.assert_called_once_with(20);fallback.set.assert_not_called()
            handler=object.__new__(Handler);handler.path='/api/runtime'
            handler.server=SimpleNamespace(app=app);handler.allowed=lambda **kwargs:True
            handler.wfile=Mock();handler.json=Mock(side_effect=BrokenPipeError('synthetic lost connection'))
            with self.assertRaises(BrokenPipeError):handler.do_GET()
            fallback.set.assert_not_called();handler.wfile.flush.assert_not_called()

    def test_direct_idle_shutdown_needs_no_browser_delivery(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp);closed=threading.Event();app._shutdown_callback=closed.set
            app.shutdown();self.assertTrue(closed.wait(2));self.assertFalse(app._shutdown_delivery.is_set())

    def test_stale_or_unconfirmed_abort_does_not_release_owned_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,session=session_fixture(tmp)
            for args in ({'mode':'idle'}, {'mode':'abort','job':session.job,'attempt':'c'*32,'confirmed':True},
                         {'mode':'abort','job':session.job,'attempt':session.binding['attempt'],'confirmed':False}):
                with self.assertRaises(ValueError):app.shutdown(**args)
            self.assertFalse(session.process.stdin.closed)
            self.assertEqual(app.runtime_status()['state'],'open')

    def test_pause_then_abort_retains_attempt_and_waits_for_latest_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,session=session_fixture(tmp);closed=threading.Event();app._shutdown_callback=closed.set
            result=app.shutdown('pause',session.job,session.binding['attempt'])
            self.assertEqual(result['state'],'waiting_for_pause')
            self.assertTrue((session.folder/'pause.request').is_file());self.assertFalse(session.process.stdin.closed)
            worker=app._shutdown_worker;sent=threading.Event()
            app.shutdown('abort',session.job,session.binding['attempt'],True,response_sent=sent)
            self.assertIs(app._shutdown_worker,worker);self.assertTrue(session.process.stdin.closed)
            complete(session);app._finish_session(session)
            self.assertFalse(closed.wait(.1))
            sent.set();wait_for(lambda:app.runtime_status()['state']=='closed')
            self.assertFalse(closed.is_set());app.runtime_delivered(app.runtime_status())
            self.assertTrue(closed.wait(2))
            self.assertEqual(read_json(session.folder/'job.json')['status'],'interrupted')

    def test_missing_receipt_blocks_new_start_and_later_status_recovers(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,session=session_fixture(tmp);complete(session,receipt=False)
            self.assertFalse(app._finish_session(session));self.assertEqual(app.runtime_status()['state'],'blocked')
            self.assertEqual(app.active,session.job)
            restarted=App(tmp)
            with self.assertRaisesRegex(ValueError,'bestätigt'):restarted.start(session.project)
            complete(session)
            self.assertEqual(app.runtime_status()['state'],'open');self.assertIsNone(app.active)
            self.assertTrue(session.finished.is_set())

    def test_wrong_attempt_or_job_receipt_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,session=session_fixture(tmp);complete(session)
            _,path=supervision_paths(session.folder,session.binding)
            value=read_json(path);value['ticket']='another-attempt';atomic_json(path,value)
            with self.assertRaises(ValueError):confirmed_cleanup(session.folder,session.binding)
            with self.assertRaises(ValueError):confirmed_cleanup(session.folder.parent/'another-job',session.binding)

    def test_launcher_and_validated_supervisor_pids_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,session=session_fixture(tmp)
            session.binding.pop('supervisor_pid')
            session.binding['launcher_pid']=session.process.pid
            complete(session)
            _,path=supervision_paths(session.folder,session.binding)
            value=read_json(path);value['supervisor_pid']=session.process.pid+1
            value['command_sha256']='0'*64;atomic_json(path,value)
            with self.assertRaises(ValueError):session.finish()
            self.assertNotIn('supervisor_pid',session.binding)
            value['command_sha256']=session.binding['command_sha256'];value['ticket']='wrong';atomic_json(path,value)
            with self.assertRaises(ValueError):session.finish()
            self.assertNotIn('supervisor_pid',session.binding)
            value['ticket']=session.binding['ticket'];atomic_json(path,value)
            self.assertTrue(app._finish_session(session))
            saved=read_json(session.folder/'job.json')['supervision']
            self.assertEqual(saved['launcher_pid'],session.process.pid)
            self.assertEqual(saved['supervisor_pid'],session.process.pid+1)

    def test_unexpected_monitor_error_keeps_lease_and_finished_run_can_recover(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,session=session_fixture(tmp)
            with patch.object(app,'_notify',side_effect=RuntimeError('synthetic monitor failure')):
                app.monitor(session.folder,session.process,1)
            self.assertEqual(app.runtime_status()['state'],'blocked')
            self.assertFalse(session.process.stdin.closed)
            complete(session,'success')
            self.assertEqual(app.runtime_status()['state'],'open')
            self.assertEqual(read_json(session.folder/'job.json')['status'],'success')

    def test_competing_start_does_not_cancel_an_existing_owned_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,session=session_fixture(tmp)
            with self.assertRaises(ValueError):app.start(session.project)
            self.assertIs(app._session,session);self.assertFalse(session.process.stdin.closed)


RUNNER=r'''
import argparse,hashlib,json,subprocess,sys,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--config');p.add_argument('--output-dir');p.add_argument('--pause-file');p.add_argument('--resume')
a=p.parse_args();folder=Path(a.resume) if a.resume else Path(a.output_dir)/'synthetic-run';folder.mkdir(parents=True,exist_ok=True)
m={'run_id':folder.name,'status':'running','current_module':'coverage','completed_steps':[],
   'output_dir':str(folder.resolve()),'provenance':{'config_sha256':hashlib.sha256(Path(a.config).read_bytes()).hexdigest()}}
def save():
 tmp=folder/'manifest.tmp';tmp.write_text(json.dumps(m));tmp.replace(folder/'workflow_manifest.json')
save()
child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)'])
(folder/'synthetic-child.pid').write_text(str(child.pid))
if a.resume:m.update(status='success',current_module=None,completed_steps=['coverage']);save();sys.exit(0)
for i in range(1200):
 if Path(a.pause_file).exists():m.update(status='paused',current_module=None);save();sys.exit(0)
 time.sleep(.05)
'''


class LifecycleProcessTests(unittest.TestCase):
    def project(self,tmp):
        app=App(Path(tmp)/'state');pid=app.create('Synthetic lifecycle',True)['id']
        app.save(pid,{**settings(app),'modules':['coverage']})
        def command(config,output_dir,pause_file,resume=None):
            result=[sys.executable,'-u','-c',RUNNER,'--config',str(config),'--output-dir',str(output_dir),'--pause-file',str(pause_file)]
            if resume:result.extend(['--resume',str(resume)])
            return result
        app.runner_command=command
        return app,pid

    def child(self,app,session):
        import job_storage
        def path():
            try:run=job_storage.run_path(session.folder,read_json(session.folder/'job.json'))
            except (BlockingIOError,PermissionError):return None
            except RuntimeError as exc:
                if isinstance(exc.__cause__,(BlockingIOError,PermissionError)):return None
                raise
            candidate=run/'synthetic-child.pid' if run else None
            return candidate if candidate and candidate.is_file() and candidate.read_text().strip().isdigit() else None
        wait_for(lambda:path() is not None)
        return int(path().read_text())

    def cleanup(self,app):
        session=app._session
        if session:
            session.stop_requested=True;session.release();app._finish_session(session)
            if session.thread:session.thread.join(3)

    def test_real_pause_resume_new_attempt_and_confirmed_child_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,pid=self.project(tmp)
            try:
                first=app.start(pid);session=app._session;child=self.child(app,session)
                app.pause(pid,first['id'])
                wait_for(lambda:app.active is None)
                self.assertFalse(pid_alive(child));self.assertEqual(app.jobs(pid)[0]['status'],'paused')
                old_attempt=session.binding['attempt'];app.start(pid,resume=first['id']);second=app._session
                self.assertNotEqual(second.binding['attempt'],old_attempt)
                wait_for(lambda:app.active is None)
                self.assertEqual(app.jobs(pid)[0]['status'],'success')
                self.assertTrue(confirmed_cleanup(second.folder,second.binding)['cleanup_confirmed'])
            finally:self.cleanup(app)

    def test_real_abort_shutdown_cleans_owned_tree_and_preserves_foreign_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,pid=self.project(tmp);foreign=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)'],
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            try:
                app.start(pid);session=app._session;child=self.child(app,session)
                closed=threading.Event();app._shutdown_callback=closed.set
                app.shutdown('abort',session.job,session.binding['attempt'],True)
                self.assertTrue(closed.wait(15));self.assertFalse(pid_alive(child))
                self.assertIsNone(foreign.poll());self.assertEqual(app.jobs(pid)[0]['status'],'interrupted')
            finally:
                self.cleanup(app);foreign.terminate();foreign.wait(10)


if __name__=='__main__':unittest.main()
