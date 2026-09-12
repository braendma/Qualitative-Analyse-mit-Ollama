import json,sys,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from telegram_progress import format_progress
from local_app import App


class TelegramProgressTests(unittest.TestCase):
    def test_all_configured_modules_show_steps_or_request_activity(self):
        import yaml
        from telegram_progress import MODULES
        modules=yaml.safe_load((ROOT/'config/config_v2.yaml').read_text(encoding='utf-8'))['pipeline']['modules']
        self.assertEqual(len(modules),15)
        for module in modules:
            mid=module['id']
            for known in (True,False):
                with self.subTest(module=mid,known_total=known):
                    text=format_progress(7,15,{'module':mid,'completed':2,'total':4 if known else None,
                        'unit':'steps','phase':'analysis','requests':13,'request_active':True,'last_response_at':980,
                        'error':'PRIVATE'},now=1000)
                    for value in (MODULES[mid],'Modellantworten: 13','Modellanfrage läuft','vor 20 Sekunden'):
                        self.assertIn(value,text)
                    self.assertNotIn('PRIVATE',text)
                    if known:self.assertIn('50 %',text)
                    else:self.assertNotIn('%',text)

    def test_substep_only_change_is_sent_by_monitor(self):
        import itertools
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);run=folder/'runs/example';run.mkdir(parents=True)
            (folder/'job.json').write_text('{}')
            (run/'workflow_manifest.json').write_text(json.dumps({'status':'success','completed_steps':['swot'],'current_module':'meta_swot'}))
            detail={'module':'meta_swot','completed':1,'total':4,'requests':5,'detail_completed':1,'detail_total':8}
            (run/'progress.json').write_text(json.dumps(detail))
            def advance(*args):
                (run/'progress.json').write_text(json.dumps({**detail,'detail_completed':2}))
            app=object.__new__(App);app.telegram=Mock();app.lock=threading.RLock();app.active=True
            process=Mock(returncode=0);process.poll.side_effect=[None,None,0]
            with patch('local_app.time.sleep',side_effect=advance),patch('local_app.time.monotonic',side_effect=itertools.count(0,121)):
                app.monitor(folder,process,15)
            calls=[c for c in app.telegram.send.call_args_list if c.args[0]=='progress']
            self.assertEqual(len(calls),2)
            self.assertEqual(calls[-1].kwargs['detail']['detail_completed'],2)

    def test_phase_substeps_and_last_response_are_visible(self):
        text=format_progress(7,15,{'module':'meta_swot','completed':1,'total':4,'unit':'dimensions',
            'phase':'analysis','detail_completed':2,'detail_total':8,'requests':7,'last_response_at':980},now=1000)
        for value in ('SWOT-Dimensionen','Analyse','Teilabschnitt: 2/8','Modellantworten: 7','vor 20 Sekunden'):
            self.assertIn(value,text)
        for stamp in (float('nan'),float('inf'),True,1001,-1,'PRIVATE'):
            self.assertNotIn('Letzte Modellantwort',format_progress(1,15,{'module':'swot','last_response_at':stamp},now=1000))

    def test_readable_progress_parallelism_and_reused_units(self):
        text=format_progress(2,15,{'module':'person_analysis','unit':'persons','completed':4,'total':8,
                                  'reused':2,'requests':6,'active_requests':2},now=1000)
        for expected in ('Module abgeschlossen: 2/15','Personenanalyse','▰▰▰▰▰▱▱▱▱▱ 50 %',
                         '4 von 8 Personen','Davon 2','Modellantworten: 6','gleichzeitig aktiv: 2'):
            self.assertIn(expected,text)
        self.assertNotIn('HPC',text);self.assertLess(len(text),4096)

    def test_private_labels_and_invalid_numbers_never_render(self):
        text=format_progress(1,15,{'module':'PRIVATE','unit':'PRIVATE','completed':'PRIVATE',
             'total':float('inf'),'reused':'PRIVATE','error':'PRIVATE','project':'PRIVATE',
             'active_requests':-1,'requests':True,'failed':1},now=1000)
        self.assertNotIn('PRIVATE',text);self.assertNotIn('inf',text)
        self.assertIn('noch nicht beziffert',text);self.assertIn('Teilproblem',text)
        self.assertNotIn('Modellantworten:',text)

    def test_request_only_progress_has_no_made_up_percentage(self):
        text=format_progress(1,15,{'module':'overall_synthesis','total':None,'requests':2,'request_active':True},now=1000)
        self.assertNotIn('%',text);self.assertIn('Gesamtsynthese',text)
        self.assertIn('Modellantworten: 2',text);self.assertIn('Modellanfrage läuft',text)

    def monitor(self,old_detail=False):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);run=folder/'runs'/'example';run.mkdir(parents=True)
            (folder/'job.json').write_text('{}')
            (run/'workflow_manifest.json').write_text(json.dumps({'status':'success','completed_steps':['clusterer'],'current_module':'blind_coding'}))
            (run/'progress.json').write_text(json.dumps({'module':'clusterer' if old_detail else 'blind_coding',
                 'completed':7,'total':10,'requests':9}))
            app=object.__new__(App);app.telegram=Mock();app.lock=threading.RLock();app.active=True
            process=Mock(returncode=0);process.poll.side_effect=[None,0]
            with patch('local_app.time.sleep'),patch('local_app.time.monotonic',side_effect=[0,121]):
                app.monitor(folder,process,15)
            calls=[c for c in app.telegram.send.call_args_list if c.args[0]=='progress']
            self.assertEqual(len(calls),1);self.assertIsNone(app.active)
            return calls[0].kwargs['detail']

    def test_module_transition_sends_only_one_progress_message(self):
        detail=self.monitor();self.assertEqual(detail['module'],'blind_coding');self.assertEqual(detail['completed'],7)

    def test_module_transition_does_not_send_previous_module_counters(self):
        detail=self.monitor(old_detail=True)
        self.assertEqual(detail,{'module':'blind_coding'})



    def test_unchanged_long_request_gets_periodic_status_without_false_percentage(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);run=folder/'runs/example';run.mkdir(parents=True)
            (folder/'job.json').write_text('{}')
            (run/'workflow_manifest.json').write_text(json.dumps({'status':'success','completed_steps':['swot'],'current_module':'overall_synthesis'}))
            detail={'module':'overall_synthesis','requests':43,'request_active':True,'request_started_at':800}
            (run/'progress.json').write_text(json.dumps(detail))
            app=object.__new__(App);app.telegram=Mock();app.lock=threading.RLock();app.active=True
            process=Mock(returncode=0);process.poll.side_effect=[None,None,None,0]
            with patch('local_app.time.sleep'),patch('local_app.time.monotonic',side_effect=[0,121,240,721]):
                app.monitor(folder,process,15)
            calls=[c for c in app.telegram.send.call_args_list if c.args[0]=='progress']
            self.assertEqual(len(calls),2)
            text=format_progress(14,15,calls[-1].kwargs['detail'],now=1000)
            for value in ('▰'*14+'▱','Modellantworten: 43','3 Minuten','Verdichtungsrunden'):
                self.assertIn(value,text)
            self.assertNotIn('%',text)


if __name__=='__main__':unittest.main()
