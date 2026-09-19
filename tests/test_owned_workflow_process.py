import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from owned_workflow_process import run_owned


class OwnedWorkflowProcessTests(unittest.TestCase):
    def test_output_and_exit_code_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_owned([sys.executable, '-c', 'print("fixture"); raise SystemExit(7)'],
                               env=os.environ.copy(), directory=tmp, timeout=15)
            self.assertEqual(result.returncode, 7)
            self.assertIn('fixture', result.stdout)

    def test_timeout_releases_lease_and_child_file_handle_before_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'held.txt'
            child = "import sys,time; f=open(sys.argv[1], 'w'); f.write('ready'); f.flush(); time.sleep(90)"
            script = ('import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",'
                      + repr(child) + ',sys.argv[1]]); time.sleep(90)')
            with self.assertRaises(subprocess.TimeoutExpired):
                run_owned([sys.executable, '-c', script, str(path)], env=os.environ.copy(),
                          directory=tmp, timeout=10)
            self.assertTrue(path.exists(), 'Child must have reached the open file before timeout')
            path.unlink()  # Windows would reject this while a descendant holds the file.
