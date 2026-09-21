import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, MagicMock
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from local_app import App, make_server
from preparation_host import Preparation, exports, review
from workspace_store import empty_project, atomic_write


def fixture():
    p=empty_project()
    p['documents']=[{'id':'d1','title':'Synthetisches Interview','transcript_sha256':'synthetic-fixture','transcript_confirmed':True,'segments':[{'id':'s1','text':'Die Bedienung ist einfach.','person':'P01','exclude':False,'start':None,'end':None}]}]
    p['categories']=[{'id':'c1','code':'Bedienbarkeit','definition':'Aussagen zur Bedienung','inclusion':'Bedienkomfort','exclusion':'Kosten','anchors':''}]
    p['annotations']=[{'id':'a1','document_id':'d1','segment_id':'s1','start':0,'end':len('Die Bedienung ist einfach.'),'quote':'Die Bedienung ist einfach.','category_id':'c1','origin':'manual','memo':''}]
    return p


class Integration(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        (Path(self.tmp.name)/'outputs').mkdir()
        self.app=App(self.tmp.name)
        self.pid=self.app.create('Integration')['id']
        self.service=Preparation(self.app,self.pid)
        self.service.store.save(fixture(),0,'initial')
        atomic_write(self.app.project_dir(self.pid)/'settings.json',{'modules':['coverage'],'num_ctx':32768,'max_tokens':4096,'output_dir':str(Path(self.tmp.name)/'outputs')})
    def tearDown(self):self.tmp.cleanup()
    def handoff(self,**updates):
        s=self.service.state();return self.service.handoff({'revision':s['revision'],'project_sha256':s['project_sha256'],'confirmed':True,'reviewer':'Testperson',**updates})
    def test_snapshot_and_real_importer(self):
        first=self.handoff();self.assertEqual(first['handoff']['validation']['persons'],1)
        original=(self.service.root/'handoffs'/first['handoff']['snapshot']/'project.json').read_bytes()
        state=self.service.store.get();p=state['project'];p['annotations'][0]['memo']='Kontext geprüft'
        self.service.store.save(p,state['revision'],'edit')
        second=self.handoff();self.assertNotEqual(first['handoff']['analysis_revision'],second['handoff']['analysis_revision'])
        self.assertEqual(original,(self.service.root/'handoffs'/first['handoff']['snapshot']/'project.json').read_bytes())
        restored=Preparation(App(self.tmp.name),self.pid);self.assertEqual(restored.state()['revision'],2)
    def test_reject_stale_unconfirmed_and_modified_quote(self):
        with self.assertRaises(ValueError):self.handoff(revision=0)
        with self.assertRaises(ValueError):self.handoff(confirmed=False)
        p=fixture();p['annotations'][0]['quote']='Erfundener Beleg'
        with self.assertRaises(ValueError):exports(p)
        p=fixture();p['documents'][0]['segments'][0]['person']=''
        with self.assertRaises(ValueError):exports(p)
    def test_cloud_guard_before_request(self):
        with self.assertRaises(ValueError):self.service.action('/host-provider',{'provider':'ollama_cloud','model':'gemma4:31b','gdpr_relevant':True},self.service.session)
        self.service.action('/host-provider',{'provider':'ollama_cloud','model':'gemma4:31b','gdpr_relevant':False},self.service.session)
        with self.assertRaises(ValueError):self.service.suggest({'revision':1,'document_id':'d1','mode':'coding','reviewer':'Test','categories_confirmed':True})
        self.assertFalse(self.service.running)
    def test_cloud_mock_validated_and_human_review_required(self):
        self.service.action('/host-provider',{'provider':'ollama_cloud','model':'gemma4:31b','gdpr_relevant':False},self.service.session)
        self.app.provider_keys.keys['ollama_cloud']='synthetic-mock-key'
        reply={'done':True,'done_reason':'stop','message':{'content':json.dumps({'suggestions':[{'id':'new','code':'Klarheit','definition':'Verständlichkeit','inclusion':'Klare Bedienung','exclusion':'Preis','reason':'Explizite Aussage','evidence':[{'segment_id':'s1','quote':'Bedienung ist einfach'}]}]})}}
        with patch('llm_client.request_chat',return_value=reply) as call:
            self.service.suggest({'revision':1,'document_id':'d1','mode':'categories','reviewer':'Test','cloud_confirmed':True})
            for _ in range(100):
                if not self.service.running:break
                time.sleep(.02)
        self.assertEqual(self.service.job['status'],'awaiting_human_review');self.assertEqual(call.call_count,1)
        restored=Preparation(App(self.tmp.name),self.pid)
        self.assertEqual(restored.job['status'],'awaiting_human_review')
        with self.assertRaises(ValueError):self.service.approve({'revision':1,'decisions_revision':0,'reviewer':'Test'})
        d=self.service.session.review_store.get();d['project']['decisions'][0]['decision']='accept'
        self.service.session.review_store.save(d['project'],0,'review')
        self.service.approve({'revision':1,'decisions_revision':1,'reviewer':'Test'})
        self.assertEqual(len(self.service.store.get()['project']['categories']),2)
        self.assertEqual(Preparation(App(self.tmp.name),self.pid).job['status'],'applied')
    def test_http_namespace_and_token(self):
        server=make_server(self.app);worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            base=f'http://127.0.0.1:{server.server_port}/preparation/{self.pid}'
            with urllib.request.urlopen(base+'/coding') as response:html=response.read().decode()
            self.assertIn(base.split(':'+str(server.server_port))[1]+'/project',html)
            self.assertIn('host_ui.js',html)
            with urllib.request.urlopen(base+'/host_ui.js') as response:js=response.read().decode()
            self.assertIn('/preparation/'+self.pid+'/host-handoff',js)
            for attempt in range(10):
                with self.subTest(rejected_request=attempt):
                    req=urllib.request.Request(base+'/host-handoff',data=b'{}',headers={'Content-Type':'application/json'})
                    with self.assertRaises(urllib.error.HTTPError) as raised:urllib.request.urlopen(req,timeout=2)
                    self.assertEqual(raised.exception.code,403)
        finally:server.shutdown();server.server_close();worker.join()

    def test_local_model_is_default_and_remote_alias_is_rejected(self):
        self.assertEqual(self.service.state()['provider'],'ollama_local')
        client=MagicMock();client.list.return_value={'models':[{'model':'granite4.2:8b','remote_host':'https://ollama.com'}]}
        client.show.return_value={}
        with patch('ollama.Client',return_value=client),patch('llm_client.request_chat') as request:
            self.service.suggest({'revision':1,'document_id':'d1','mode':'categories','reviewer':'Test'})
            for _ in range(100):
                if not self.service.running:break
                time.sleep(.02)
        self.assertEqual(self.service.job['status'],'failed')
        self.assertIn('Remote-Modell',self.service.job['error']);request.assert_not_called()

    def test_reviewed_audio_adds_document_and_survives_restart(self):
        p=fixture();p['documents'][0].update(id='audio1',transcript_sha256='other-approved-audio')
        p['documents'][0]['segments'][0]['text']='Geprüfter Audiotext.'
        p['annotations']=[];p['categories']=[]
        before=self.service.store.get()['project']['annotations']
        self.service.adopt_finished({'project':p})
        self.service.adopt_finished({'project':p})
        restored=Preparation(App(self.tmp.name),self.pid)
        self.assertEqual(len(restored.store.get()['project']['documents']),2)
        self.assertEqual(restored.store.get()['project']['annotations'],before)

    def test_shutdown_blocks_owned_running_work(self):
        from preparation_host import require_idle
        self.app.preparations={self.pid:self.service};self.service.running=True
        with self.assertRaisesRegex(ValueError,'Vorschlagsauftrag'):require_idle(self.app)
        self.service.running=False
        require_idle(self.app)

    def test_interrupted_request_restores_without_dispatch(self):
        jid='a'*20;folder=self.service.root/'suggestions'/jid;folder.mkdir(parents=True)
        atomic_write(folder/'status.json',{'id':jid,'status':'running','provider':'ollama_cloud'})
        atomic_write(self.service.root/'last_job.json',{'id':jid})
        with patch('llm_client.request_chat') as call:
            restored=Preparation(App(self.tmp.name),self.pid)
        self.assertEqual(restored.job['status'],'interrupted');call.assert_not_called()
        atomic_write(self.service.root/'last_job.json',{'id':'../outside'})
        with self.assertRaises(ValueError):Preparation(App(self.tmp.name),self.pid)

if __name__=='__main__':unittest.main()
