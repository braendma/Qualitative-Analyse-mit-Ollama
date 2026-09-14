import json,sys,tempfile,unittest
import time
from pathlib import Path
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from telegram_progress import format_progress
from local_app import App
from test_local_app import attach_supervision


def monitor_clock(advance, ticks):
    """Control only the monitor clock, not other modules' atomic-write timers."""
    clock = Mock(wraps=time)
    clock.sleep.side_effect = advance
    clock.monotonic.side_effect = ticks
    return patch('local_app.time', clock)


def monitored_app(folder, iterations, update=None):
    """Real App, synthetic owned process/receipt and mocked notification transport."""
    app=App(folder);app.telegram=Mock()
    process=Mock(returncode=None)
    process.poll.side_effect=lambda:process.returncode
    attach_supervision(app,folder,process)
    remaining=iterations
    def advance(*args):
        nonlocal remaining
        if update is not None:update()
        remaining-=1
        if remaining==0:process.returncode=0
    return app,process,advance


class TelegramProgressTests(unittest.TestCase):
    def test_monitor_clock_does_not_replace_shared_runtime_clock(self):
        import local_app
        import runtime_support
        monotonic, sleep = time.monotonic, time.sleep
        with monitor_clock(lambda *_: None, [0, 121]):
            self.assertEqual(local_app.time.monotonic(), 0)
            self.assertEqual(local_app.time.monotonic(), 121)
            self.assertIs(runtime_support.time.monotonic, monotonic)
            self.assertIs(runtime_support.time.sleep, sleep)
        self.assertIs(local_app.time, time)

    def test_all_configured_modules_show_steps_or_request_activity(self):
        import yaml
        from telegram_progress import MODULES
        modules=yaml.safe_load((ROOT/'config/config_v2.yaml').read_text(encoding='utf-8'))['pipeline']['modules']
        self.assertTrue({m['id'] for m in modules} <= MODULES.keys())
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
            def update():
                (run/'progress.json').write_text(json.dumps({**detail,'detail_completed':2}))
            app,process,advance=monitored_app(folder,2,update)
            with monitor_clock(advance, itertools.count(0,121)):
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
            app,process,advance=monitored_app(folder,1)
            with monitor_clock(advance, [0,121]):
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
            app,process,advance=monitored_app(folder,3)
            with monitor_clock(advance, [0,121,240,721]):
                app.monitor(folder,process,15)
            calls=[c for c in app.telegram.send.call_args_list if c.args[0]=='progress']
            self.assertEqual(len(calls),2)
            text=format_progress(14,15,calls[-1].kwargs['detail'],now=1000)
            for value in ('▰'*14+'▱','Modellantworten: 43','3 Minuten','Verdichtungsrunden'):
                self.assertIn(value,text)
            self.assertNotIn('%',text)


    def inner_monitor(self, frames, ticks):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);run=folder/'runs/example';run.mkdir(parents=True)
            (folder/'job.json').write_text('{}')
            (run/'workflow_manifest.json').write_text(json.dumps({'status':'success','completed_steps':[],
                                                                 'current_module':'stability'}))
            base={'module':'stability','phase':'repetitions','completed':0,'total':2,'unit':'repetitions'}
            def write(frame):
                (run/'progress.json').write_text(json.dumps({**base,'series_current':frame}))
            write(frames[0])
            remaining=iter(frames[1:])
            def update():
                frame=next(remaining,None)
                if frame is not None:write(frame)
            app,process,advance=monitored_app(folder,len(frames),update)
            with monitor_clock(advance, [0]+ticks):
                app.monitor(folder,process,20)
            return app.telegram.send.call_args_list

    def test_inner_counter_changes_reach_telegram_after_throttle(self):
        current={'state':'running','sample_number':1,'module':'blind_coding',
                 'detail':{'completed':1,'total':9,'requests':2,'updated_at':100}}
        second={**current,'detail':{**current['detail'],'completed':2,'requests':3,'updated_at':101}}
        calls=self.inner_monitor([current,second,second],[121,180,242])
        sent=[c for c in calls if c.args[0]=='progress']
        self.assertEqual(len(sent),2)
        self.assertEqual(sent[-1].kwargs['detail']['series_current']['detail']['completed'],2)
        self.assertEqual(sent[-1].kwargs['detail']['completed'],0)

    def test_poll_timestamp_only_change_does_not_send_extra_status(self):
        current={'state':'running','sample_number':1,'module':'blind_coding',
                 'detail':{'requests':2,'updated_at':100}}
        second={**current,'detail':{**current['detail'],'updated_at':999}}
        calls=self.inner_monitor([current,second,second],[121,242,722])
        sent=[c for c in calls if c.args[0]=='progress']
        # First bounded update, then the existing ten-minute activity heartbeat.
        self.assertEqual(len(sent),2)
        self.assertEqual(sent[-1].kwargs['detail']['series_current']['detail']['updated_at'],999)

    def test_inner_failure_is_announced_once_without_research_data(self):
        current={'state':'running','sample_number':1,'module':'blind_coding','configuration_id':'PRIVATE',
                 'detail':{'requests':2,'failed':1,'context_blocked':True,'error':'PRIVATE'}}
        calls=self.inner_monitor([current,current],[121,242])
        failed=[c for c in calls if c.args[0]=='partial_failed']
        self.assertEqual(len(failed),1)
        sent=[c for c in calls if c.args[0]=='progress']
        self.assertEqual(len(sent),1)
        self.assertNotIn('PRIVATE',str(sent[0]))

    def test_new_repetition_with_same_inner_counts_is_a_status_change(self):
        current={'state':'running','sample_number':1,'module':'blind_coding','detail':{'completed':1,'total':9}}
        second={**current,'sample_number':2}
        calls=self.inner_monitor([current,second],[121,242])
        self.assertEqual(len([c for c in calls if c.args[0]=='progress']),2)


if __name__=='__main__':unittest.main()
