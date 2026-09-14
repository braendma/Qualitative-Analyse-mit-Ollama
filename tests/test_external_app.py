"""Actual model-free App runs in explicit research folders and failure isolation."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from local_app import App, read_json
from test_local_app import settings,attach_supervision
from runtime_support import file_hash
from filesystem_paths import canonical_path


class ExternalAppTests(unittest.TestCase):
    def setup_project(self, root):
        app=App(root/'appdata');pid=app.create('Synthetic external study',True)['id']
        target=root/'Forschung mit Umlaut ä';target.mkdir()
        opts={**settings(app),'modules':['coverage','information_loss','codebook_diagnostics'],'output_dir':str(target)}
        app.save(pid,opts)
        return app,pid,target,opts

    def wait(self, app):
        deadline=time.monotonic()+25
        while app.active is not None and time.monotonic()<deadline:time.sleep(.05)
        self.assertIsNone(app.active,'Own synthetic diagnostic did not finish')

    def test_external_report_survives_restart_and_later_target_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);app,pid,target,opts=self.setup_project(root)
            inputs={p:file_hash(p) for p in (app.project_dir(pid)/'inputs').glob('*')}
            job=app.start(pid);self.wait(app)
            listed=app.jobs(pid)[0]
            self.assertEqual(listed['status'],'success',listed)
            research=Path(listed['research_path'])
            self.assertEqual(research.parent,target.resolve())
            report=app.artifact(pid,job['id'],'gesamtbericht.html')
            self.assertTrue(canonical_path(report).is_relative_to(canonical_path(research)))
            self.assertIn('Codebook-Diagnostik',report.read_text(encoding='utf-8'))
            restarted=App(root/'appdata')
            self.assertEqual(restarted.artifact(pid,job['id'],'gesamtbericht.html'),report)
            target2=root/'Neues Ziel';target2.mkdir()
            restarted.save(pid,{**opts,'output_dir':str(target2)})
            second=restarted.start(pid);self.wait(restarted)
            self.assertEqual(restarted.artifact(pid,job['id'],'gesamtbericht.html'),report)
            self.assertTrue(canonical_path(restarted.artifact(pid,second['id'],'gesamtbericht.html')).is_relative_to(canonical_path(target2)))
            self.assertEqual({p:file_hash(p) for p in inputs},inputs)
            self.assertFalse((app.project_dir(pid)/'jobs'/job['id']/'runs').exists())
            with self.assertRaises(ValueError):restarted.artifact(pid,job['id'],'../../outside.txt')

    def test_missing_choice_and_disconnected_target_create_no_job_or_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);app,pid,target,opts=self.setup_project(root)
            app.save(pid,{**opts,'output_dir':''})
            with patch('subprocess.Popen',side_effect=AssertionError('No process allowed')):
                with self.assertRaisesRegex(ValueError,'Speicherort'):app.start(pid)
            self.assertEqual(list((app.project_dir(pid)/'jobs').glob('*')),[])
            app.save(pid,opts);target.rename(root/'disconnected')
            with patch('subprocess.Popen',side_effect=AssertionError('No process allowed')):
                with self.assertRaises(ValueError):app.start(pid)
            self.assertEqual(list((app.project_dir(pid)/'jobs').glob('*')),[])
            self.assertFalse(target.exists())

    def test_offline_finished_job_is_isolated_and_recovers_without_reassignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);app,pid,target,opts=self.setup_project(root)
            job=app.start(pid);self.wait(app)
            research=Path(app.jobs(pid)[0]['research_path']);offline=target/'offline'
            research.rename(offline)
            listed=app.jobs(pid)[0]
            self.assertIn('output_error',listed)
            self.assertEqual(listed['files'],[])
            self.assertEqual(app.projects()[0]['id'],pid)
            with self.assertRaises(ValueError):app.artifact(pid,job['id'],'gesamtbericht.html')
            offline.rename(research)
            restored=app.jobs(pid)[0]
            self.assertNotIn('output_error',restored)
            self.assertEqual(restored['research_path'],str(research))
            self.assertTrue(app.artifact(pid,job['id'],'gesamtbericht.html').is_file())

    def test_monitor_storage_failure_keeps_active_guard_until_process_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);app,pid,target,opts=self.setup_project(root)
            folder=app.project_dir(pid)/'jobs'/('d'*20);folder.mkdir(parents=True)
            config=app.project_dir(pid)/'revisions'/app.project(pid)['revision']/'config.yaml'
            (folder/'job.json').write_text(json.dumps({'id':folder.name,'config':str(config),'status':'running'}),encoding='utf-8')
            alive={'value':True}
            process=MagicMock();process.poll.side_effect=lambda:None if alive['value'] else 0;process.returncode=0
            app.active=folder.name
            attach_supervision(app,folder,process)
            def sleep(_):
                self.assertEqual(app.active,folder.name);alive['value']=False
            with patch('local_app.job_storage.run_path',side_effect=ValueError('synthetic offline')), \
                 patch('local_app.time.sleep',side_effect=sleep),patch.object(app.telegram,'send'):
                app.monitor(folder,process,1)
            self.assertIsNone(app.active)
            self.assertEqual(read_json(folder/'job.json')['status'],'interrupted')
            self.assertTrue(read_json(folder/'job.json')['cleanup_confirmed'])
            self.assertTrue(process.stdin.closed)

    def test_process_start_failure_retains_displayable_bound_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);app,pid,target,opts=self.setup_project(root)
            with patch('local_app.subprocess.Popen',side_effect=OSError('synthetic startup failure')):
                with self.assertRaises(OSError):app.start(pid)
            jobs=app.jobs(pid)
            self.assertEqual(len(jobs),1)
            failed=jobs[0]
            self.assertEqual(failed['status'],'failed')
            self.assertEqual({m['id'] for m in failed['modules']},set(opts['modules']))
            self.assertEqual(Path(failed['research_path']).parent,target.resolve())
            self.assertEqual(failed['files'],[])
            self.assertIsNone(app.active)


if __name__=='__main__':unittest.main()
