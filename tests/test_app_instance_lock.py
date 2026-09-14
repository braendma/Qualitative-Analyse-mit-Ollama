"""Real idle application processes, with isolated synthetic technical stores."""
import http.client
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.parse import urlsplit


ROOT=Path(__file__).resolve().parents[1]


class AppInstanceLockTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.children=[]

    def tearDown(self):
        for process,_ in self.children:
            if process.poll() is None:process.terminate()
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill();process.wait(timeout=10)
        self.temp.cleanup()

    def command(self,data):
        return [sys.executable,'-u',str(ROOT/'src/local_app.py'),'--data-dir',str(data),'--no-browser','--port','0']

    def environment(self):
        # Explicit source import boundary; do not depend on test discovery order
        # or the parent process exporting its own PYTHONPATH.
        return {**os.environ,'PYTHONPATH':str(ROOT/'src'),
                'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8'}

    def start(self,data):
        trace=self.root/f'app-{len(self.children)}.txt'
        with trace.open('wb') as log:
            process=subprocess.Popen(self.command(data),stdout=log,stderr=subprocess.STDOUT,
                env=self.environment(),cwd=ROOT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        self.children.append((process,trace))
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            text=trace.read_text(encoding='utf-8',errors='replace')
            match=re.search(r'Lokale Oberfläche: (http://127\.0\.0\.1:\d+/#[^\s]+)',text)
            if match:return process,urlsplit(match.group(1))
            if process.poll() is not None:self.fail('Idle application exited before becoming ready: '+text)
            time.sleep(.05)
        self.fail('Idle application failed to start within the test deadline: '+
                  trace.read_text(encoding='utf-8',errors='replace')[-4000:])

    def close_idle(self,process,address):
        connection=http.client.HTTPConnection(address.hostname,address.port,timeout=10)
        try:
            connection.request('POST','/api/shutdown',json.dumps({'mode':'idle'}),
                {'Content-Type':'application/json','X-App-Token':address.fragment})
            response=connection.getresponse();response.read()
            self.assertEqual(response.status,200)
        finally:connection.close()
        # The browser must receive the verified terminal state before the HTTP
        # server goes away. A disconnected socket is not a cleanup receipt.
        self.assertIsNone(process.poll())
        deadline=time.monotonic()+8
        state=None
        while time.monotonic()<deadline:
            connection=http.client.HTTPConnection(address.hostname,address.port,timeout=5)
            try:
                connection.request('GET','/api/runtime',headers={'X-App-Token':address.fragment})
                response=connection.getresponse()
                self.assertEqual(response.status,200)
                state=json.loads(response.read())['state']
            finally:connection.close()
            if state=='closed':break
            time.sleep(.02)
        self.assertEqual(state,'closed')
        self.assertEqual(process.wait(timeout=20),0)

    def test_same_store_refuses_second_instance_other_store_remains_independent(self):
        first,url=self.start(self.root/'technical-one')
        duplicate=subprocess.run(self.command(self.root/'technical-one'),stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,timeout=20,encoding='utf-8',errors='replace',
            env=self.environment(),cwd=ROOT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        self.assertNotEqual(duplicate.returncode,0)
        self.assertNotIn('Lokale Oberfläche:',duplicate.stdout)
        self.assertRegex(duplicate.stdout.lower(),r'bereits|geöffnet')
        self.assertIsNone(first.poll())
        second,second_url=self.start(self.root/'technical-two')
        self.assertNotEqual(url.port,second_url.port)
        self.close_idle(second,second_url)
        self.assertIsNone(first.poll())
        self.close_idle(first,url)

    def test_process_death_releases_os_lock_without_deleting_technical_data(self):
        data=self.root/'technical'
        first,_=self.start(data)
        marker=data/'synthetic-retained.txt';marker.write_text('retained',encoding='utf-8')
        first.kill();first.wait(timeout=10)
        restarted,address=self.start(data)
        self.assertEqual(marker.read_text(encoding='utf-8'),'retained')
        self.close_idle(restarted,address)


if __name__=='__main__':unittest.main()
