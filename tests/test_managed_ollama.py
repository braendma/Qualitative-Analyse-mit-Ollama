import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import managed_ollama as runtime
import progress_events as progress
import clusterer_core as cluster
import pandas as pd


class ManagedTests(unittest.TestCase):
    def test_workers_validation_and_cloud_guard(self):
        for invalid in (True, 0, 9, 1.5, '2'):
            with self.assertRaises(ValueError): runtime.workers({'parallel_workers': invalid})
        self.assertEqual(runtime.workers({}), 1)
        with self.assertRaises(ValueError):
            runtime.workers({'model': 'demo', 'parallel_workers': 2, 'provider': 'openai', 'gdpr_relevant': False})

    def test_preflight_requires_fresh_sufficient_capacity(self):
        settings = {'provider': 'ollama_local', 'model': 'demo', 'parallel_workers': 2}
        with patch.object(runtime, 'executable', return_value='ollama'), patch('ollama_capacity.check') as check:
            for maximum in (None, 0, 1):
                check.return_value = {'estimated_parallel': maximum, 'reason': 'Test'}
                with self.assertRaisesRegex(ValueError, 'Parallelstart'): runtime.preflight(settings)
            check.return_value = {'estimated_parallel': 2}
            self.assertEqual(runtime.preflight(settings), 2)
            self.assertEqual(check.call_count, 4)

    def test_single_request_does_not_start_server_and_clears_old_host(self):
        with patch.dict(os.environ, {runtime.HOST_ENV: 'http://127.0.0.1:1234'}), patch.object(runtime.subprocess, 'Popen') as start:
            session = runtime.ManagedOllama({}, '.')
            self.assertFalse(session.start()['managed'])
            self.assertNotIn(runtime.HOST_ENV, os.environ)
            session.close()
            start.assert_not_called()

    def test_failed_start_closes_lease_and_log(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(runtime, 'preflight', return_value=2), patch.object(runtime, 'executable', return_value='ollama'), patch.object(runtime.subprocess, 'Popen') as start:
            process = start.return_value
            process.poll.return_value = 1
            session = runtime.ManagedOllama({'model': 'demo', 'num_ctx': 2048}, tmp)
            with self.assertRaises(RuntimeError): session.start()
            process.stdin.close.assert_called_once()
            process.wait.assert_called()
            env = start.call_args.kwargs['env']
            self.assertEqual(env['OLLAMA_NUM_PARALLEL'], '2')
            self.assertEqual(env['OLLAMA_NO_CLOUD'], '1')
            self.assertTrue(env['OLLAMA_HOST'].startswith('http://127.0.0.1:'))
            self.assertIsNone(session.log)

    def test_parallel_progress_keeps_remaining_request_active(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'WORKFLOW_PROGRESS_FILE': str(Path(tmp)/'progress.json')}):
            progress.ACTIVE_REQUESTS = 0
            progress.request_event(start=True); progress.request_event(start=True)
            progress.request_event(success=False)
            data = json.loads((Path(tmp)/'progress.json').read_text())
            self.assertTrue(data['request_active']); self.assertEqual(data['active_requests'], 1)
            self.assertNotIn('requests', data)
            progress.request_event()
            data = json.loads((Path(tmp)/'progress.json').read_text())
            self.assertFalse(data['request_active']); self.assertEqual(data['requests'], 1)

    def test_clusters_overlap_but_plots_are_ordered_on_main_thread_and_resume(self):
        frame = pd.DataFrame([{'Dokumentname': 'P', 'Code': code, 'Segment': code, 'ID': code} for code in ('B', 'A')])
        barrier = threading.Barrier(2)
        main = threading.get_ident()
        plotted = []
        def fake(system, user, params):
            barrier.wait(timeout=5)
            return json.dumps({'clusters': [{'cluster_name': 'Demo', 'definition': 'Test', 'segments': [json.loads(user)[0]['id']]}]})
        def plot(haupt, *args, **kwargs):
            self.assertEqual(threading.get_ident(), main)
            plotted.append(haupt)
        with tempfile.TemporaryDirectory() as tmp, patch.object(cluster, 'llm_cluster', side_effect=fake) as llm, patch.object(cluster, 'plot_clusters', side_effect=plot):
            params = {'model': 'mock', 'temperature': 0, 'max_tokens': 100, 'parallel_workers': 2, 'partial_checkpoint_dir': tmp+'/parts'}
            prompts = {'cluster_analysis': {'system': 'test', 'user': '{segments}'}, 'json_schema': '{}'}
            args = (frame, params, prompts, {})
            _, result = cluster.run_clustering(*args, plots_dir=tmp, id_to_text_path=tmp+'/map.json')
            self.assertEqual(plotted, ['A', 'B'])
            self.assertEqual([c['code_path'] for c in result['clusters']], ['A', 'B'])
            llm.side_effect = AssertionError('Repeated completed request')
            _, resumed = cluster.run_clustering(*args, plots_dir=tmp, id_to_text_path=tmp+'/map.json')
            self.assertEqual(result['clusters'], resumed['clusters'])


if __name__ == '__main__': unittest.main()
