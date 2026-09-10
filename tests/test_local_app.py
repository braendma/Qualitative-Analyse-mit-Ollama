import base64
import copy
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from local_app import App, make_server, safe_child, csv_info
from telegram_notifications import Telegram


def settings(app):
    return {'columns':copy.deepcopy(app.template['columns']),
            'book_columns':dict(zip(('kategorie','unterkategorie','auspraegung','facette','definition','ankerbeispiel'),
                                   ('Kategorie','Unterkategorie','Ausprägung','Facette','Definition','Ankerbeispiel'))),
            'modules':['summarizer'],'model':'mock','label_mode':'multi_label','context':{}}


class DesktopTests(unittest.TestCase):
    def test_invalid_save_keeps_last_valid_revision_and_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp);pid=app.create('Demo',True)['id'];opts=settings(app)
            app.save(pid,opts)
            previous=app.project(pid)
            # Every row gets a different "person" but repeated passage IDs remain.
            invalid=copy.deepcopy(opts);invalid['columns']['person']='segment_id'
            with self.assertRaises(ValueError):app.save(pid,invalid)
            self.assertEqual(app.project(pid)['revision'],previous['revision'])
            self.assertEqual(app.project(pid)['settings'],previous['settings'])

    def test_upload_invalidates_revision_and_only_its_column_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp);pid=app.create('Demo',True)['id'];opts=settings(app)
            app.save(pid,opts)
            app.upload(pid,'segments','new.csv',base64.b64encode((ROOT/'demo/maxqda_export.csv').read_bytes()).decode())
            current=app.project(pid)
            self.assertIsNone(current['revision'])
            self.assertNotIn('columns',current['settings'])
            self.assertEqual(current['settings']['book_columns'],opts['book_columns'])
            with self.assertRaisesRegex(ValueError,'zuerst speichern'):app.start(pid)

    def test_failed_resume_is_not_reported_as_old_pause(self):
        from runtime_support import atomic_json
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp);pid=app.create('Demo',True)['id'];app.save(pid,settings(app))
            directory=app.project_dir(pid);cfg=directory/'revisions'/app.project(pid)['revision']/'config.yaml'
            folder=directory/'jobs'/('a'*20);run=folder/'runs'/'old';run.mkdir(parents=True)
            atomic_json(run/'workflow_manifest.json',{'status':'paused','completed_steps':['clusterer']})
            job={'id':'a'*20,'created':1,'config':str(cfg),'status':'failed','error':'Resume rejected','pid':123,'modules':[]}
            atomic_json(folder/'job.json',job)
            self.assertEqual(app.jobs(pid)[0]['status'],'failed')
            self.assertEqual(app.jobs(pid)[0]['error'],'Resume rejected')
            atomic_json(folder/'job.json',{**job,'status':'running','error':''})
            with patch('local_app.pid_alive',return_value=True):self.assertEqual(app.jobs(pid)[0]['status'],'running')

    def test_demo_mapping_validation_and_immutable_revisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp);project=app.create('Demo',True);pid=project['id'];opts=settings(app)
            result=app.save(pid,opts)
            self.assertEqual((result['segments'],result['passages'],result['codes']),(50,43,12))
            self.assertEqual([m['id'] for m in result['modules']],['clusterer','summarizer'])
            revision=app.project_dir(pid)/'revisions'/app.project(pid)['revision']/'config.yaml'
            saved=revision.read_bytes();old=yaml.safe_load(saved)
            app.upload(pid,'segments','replacement.csv',base64.b64encode((ROOT/'demo/maxqda_export.csv').read_bytes()).decode())
            app.save(pid,{**opts,'temperature':0.2})
            self.assertEqual(revision.read_bytes(),saved)
            self.assertTrue(Path(old['paths']['input_csv']).is_file())
            self.assertNotEqual(app.project(pid)['revision'],revision.parent.name)
            self.assertNotIn('telegram',saved.decode().lower())
            with self.assertRaisesRegex(ValueError,'Passage-ID'):
                app.save(pid,{**opts,'columns':{**opts['columns'],'unit_id':''}})
            with self.assertRaisesRegex(ValueError,'Cloud'):
                app.save(pid,{**opts,'model':'remote-cloud'})

    def test_invalid_csv_mapping_and_path_escape(self):
        with self.assertRaises(ValueError):csv_info(b'a;a\n1;2\n')
        with self.assertRaises(ValueError):csv_info(b'a;b\n1;2;3\n')
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):safe_child(tmp,'../private.txt')
            app=App(tmp)
            with self.assertRaises(ValueError):app.project('../x')
            pid=app.create('Example',True)['id'];opts=settings(app)
            opts['columns']['person']='missing'
            with self.assertRaisesRegex(ValueError,'Spalte fehlt'):app.save(pid,opts)

    def test_http_auth_origin_host_and_secret_redaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp);server=make_server(app)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def request(method,path,data=None,headers=None):
                conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                payload=json.dumps(data) if data is not None else None
                conn.request(method,path,payload,headers=headers or {})
                result=conn.getresponse();body=result.read();status=result.status;conn.close();return status,body
            try:
                self.assertEqual(request('GET','/')[0],200)
                self.assertEqual(request('GET','/api/state')[0],403)
                headers={'X-App-Token':server.token,'Content-Type':'application/json'}
                self.assertEqual(request('GET','/api/state',headers={**headers,'Origin':'https://attacker.invalid'})[0],403)
                self.assertEqual(request('GET','/',headers={'Host':'attacker.invalid'})[0],403)
                self.assertEqual(request('POST','/api/create',[],headers)[0],400)
                token='123456:'+('A'*30)
                status,body=request('POST','/api/telegram',{'token':token,'chat_id':'123','enabled':True,'persist':False,'events':['success']},headers)
                self.assertEqual(status,200);self.assertNotIn(token.encode(),body)
                status,body=request('GET','/api/state',headers=headers)
                self.assertEqual(status,200);self.assertNotIn(token.encode(),body)
            finally:
                server.shutdown();server.server_close();thread.join()

    def test_desktop_launch_pause_and_resume_real_runner_with_mock_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(tmp);pid=app.create('Synthetic workflow',True)['id'];opts=settings(app)
            app.template['prompts']['cluster_analysis']={'system':'cluster_analysis','user':'{segments}'}
            app.template['prompts']['cluster_summary']={'system':'cluster_summary','user':'{clusters}'}
            app.template['prompts']['category_summary']={'system':'category_summary','user':'{subcats}'}
            app.save(pid,opts)
            real_popen=subprocess.Popen
            first=True
            def launch(command,**kwargs):
                nonlocal first
                command=list(command);command[1]=str(ROOT/'tests/mock_pipeline.py')
                if first:
                    Path(command[command.index('--pause-file')+1]).write_text('pause')
                    first=False
                return real_popen(command,**kwargs)
            def settle():
                deadline=time.monotonic()+40
                while app.active is not None and time.monotonic()<deadline:time.sleep(.1)
                self.assertIsNone(app.active,'Workflow monitor failed to finish')
            with patch.object(app,'models',return_value={'models':['mock']}),patch('local_app.subprocess.Popen',side_effect=launch):
                started=app.start(pid);settle()
                job=app.jobs(pid)[0];self.assertEqual(job['status'],'paused')
                app.start(pid,started['id']);settle()
                job=app.jobs(pid)[0]
                if job['status']!='success':
                    self.fail(app.artifact(pid,started['id'],'console.log').read_text(encoding='utf-8')[-5000:])
                self.assertEqual(job['completed'],['clusterer','summarizer'])
                self.assertIn('gesamtbericht.md',job['files'])
                with self.assertRaises(ValueError):app.artifact(pid,started['id'],'../../telegram.private.json')
                with self.assertRaisesRegex(ValueError,'bereits abgeschlossen'):app.start(pid,started['id'])


class TelegramTests(unittest.TestCase):
    TOKEN='123456:'+('A'*30)
    def test_session_token_replace_remove_and_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot=Telegram(tmp)
            opts={'token':self.TOKEN,'chat_id':'123','enabled':True,'persist':False,'events':['success']}
            bot.save(opts)
            self.assertNotIn(self.TOKEN,bot.path.read_text())
            self.assertFalse(Telegram(tmp).public()['enabled'])
            replacement='123456:'+('B'*30)
            bot.save({**opts,'token':replacement})
            self.assertEqual(bot.token,replacement)
            bot.save({**opts,'token':'','remove_token':True})
            self.assertFalse(bot.public()['has_token']);self.assertFalse(bot.public()['enabled'])

    @unittest.skipUnless(os.name=='nt','Windows DPAPI only')
    def test_windows_encrypted_persistence_and_rotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot=Telegram(tmp);opts={'token':self.TOKEN,'chat_id':'123','enabled':True,'persist':True,'events':['success']}
            bot.save(opts);self.assertNotIn(self.TOKEN,bot.path.read_text())
            self.assertEqual(Telegram(tmp).token,self.TOKEN)
            bot.save({**opts,'token':'123456:'+('C'*30)})
            self.assertNotEqual(Telegram(tmp).token,self.TOKEN)
            bot.save({**opts,'token':'','remove_token':True})
            self.assertFalse(Telegram(tmp).public()['has_token'])

    def test_only_generic_notifications_and_sanitized_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot=Telegram(tmp);bot.save({'token':self.TOKEN,'chat_id':'123','enabled':True,'events':['success'],'persist':False})
            with patch('telegram_notifications.urllib.request.build_opener') as factory:
                opener=factory.return_value
                opener.open.return_value.__enter__.return_value.read.return_value=b'{"ok":true}'
                self.assertFalse(bot.send('progress',1,15));opener.open.assert_not_called()
                self.assertTrue(bot.send('success'))
                request=opener.open.call_args.args[0]
                payload=json.loads(request.data)
                self.assertEqual(set(payload),{'chat_id','text'})
                self.assertEqual(payload['text'],'Qualitative Analyse: Lauf abgeschlossen. Ergebnisse lokal öffnen.')
                opener.open.side_effect=RuntimeError('https://api.telegram.org/bot'+self.TOKEN+'/sendMessage')
                self.assertFalse(bot.send('success'))
                with self.assertRaises(ValueError) as error:bot.send('start',test=True)
                self.assertNotIn(self.TOKEN,str(error.exception))
                self.assertNotIn(self.TOKEN,json.dumps(bot.public()))


if __name__=='__main__':unittest.main()
