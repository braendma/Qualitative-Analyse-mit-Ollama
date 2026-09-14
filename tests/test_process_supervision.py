import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from diagnostic_series import _execute
from local_app import pid_alive


class SupervisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def wait_json(self,name,condition=lambda x:True):
        path=self.root/name;deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            if path.is_file():
                data=json.loads(path.read_text(encoding='utf-8'))
                if condition(data):return data
            time.sleep(.03)
        self.fail('Synthetic process did not reach expected state: '+name)

    def assert_stopped(self,*pids):
        deadline=time.monotonic()+10
        while any(pid_alive(pid) for pid in pids) and time.monotonic()<deadline:time.sleep(.03)
        self.assertTrue(all(not pid_alive(pid) for pid in pids),str(pids))

    def test_normal_and_failed_exit_have_confirmed_receipts(self):
        for code in (0,7):
            result=_execute([sys.executable,'-c',f'raise SystemExit({code})'],self.root,self.root/'test.log',dict(os.environ))
            self.assertEqual(result,code)
            record=self.wait_json('test.supervision.json')
            self.assertTrue(record['cleanup_confirmed'])
            self.assertEqual(record['exit_code'],code)

    def test_missing_child_executable_has_confirmed_failed_receipt(self):
        from supervision_receipts import validate_receipt
        from runtime_support import fingerprint
        command=[str(self.root/'missing-synthetic-executable')]
        result=_execute(command,self.root,self.root/'missing.log',dict(os.environ))
        self.assertNotEqual(result,0)
        record=self.wait_json('missing.supervision.json')
        request=self.wait_json('missing.supervision.request.json')
        validate_receipt(record,ticket=request['ticket'],command_sha256=fingerprint(command))
        self.assertEqual(record['child_start'],'not_started')
        self.assertNotIn('child_pid',record)
        self.assertNotEqual(record['exit_code'],0)

    def test_parent_death_reaps_owned_tree_without_killing_unrelated_process(self):
        outsider=subprocess.Popen([sys._base_executable,'-c','import time;time.sleep(120)'],creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        controller=subprocess.Popen([sys.executable,str(ROOT/'tests/supervisor_probe.py'),'controller',str(self.root)],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            owner=self.wait_json('controller.json')['pid']
            leaf=self.wait_json('leaf.json')['pid'];tree=self.wait_json('tree.json')['pid']
            os.kill(owner,signal.SIGTERM)
            receipt=self.wait_json('probe.supervision.json',lambda r:r['status']=='finished')
            self.assertTrue(receipt['cleanup_confirmed']);self.assertTrue(receipt['parent_released'])
            self.assert_stopped(leaf,tree)
            self.assertIsNone(outsider.poll())
            controller.wait(timeout=10)
        finally:
            if controller.poll() is None:controller.kill()
            controller.wait(timeout=10)
            outsider.terminate();outsider.wait(timeout=10)

    @unittest.skipUnless(os.name=='nt','Kernel job containment is Windows-specific')
    def test_job_cleans_orphan_after_runner_exits(self):
        result=_execute([sys.executable,str(ROOT/'tests/supervisor_probe.py'),'orphan',str(self.root)],self.root,self.root/'orphan.log',dict(os.environ))
        self.assertEqual(result,0)
        self.assert_stopped(self.wait_json('leaf.json')['pid'])

    @unittest.skipUnless(os.name=='nt','Kernel job containment is Windows-specific')
    def test_killing_supervisor_also_kills_its_descendants(self):
        supervisor=subprocess.Popen([sys.executable,str(ROOT/'src/managed_ollama.py'),'--command',str(self.root/'receipt.json'),'synthetic-ticket',
            sys.executable,str(ROOT/'tests/supervisor_probe.py'),'tree',str(self.root)],stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            leaf=self.wait_json('leaf.json')['pid'];tree=self.wait_json('tree.json')['pid']
            pid=self.wait_json('receipt.json')['supervisor_pid']
            os.kill(pid,signal.SIGTERM)
            self.assert_stopped(leaf,tree)
            supervisor.wait(timeout=10)
        finally:
            supervisor.stdin.close()
            if supervisor.poll() is None:supervisor.kill()
            supervisor.wait(timeout=10)


if __name__=='__main__':unittest.main()
