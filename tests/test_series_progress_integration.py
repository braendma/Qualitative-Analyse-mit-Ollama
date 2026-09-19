"""Real supervisor/runner integration with slow, entirely synthetic transport."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_diagnostic_repetitions import Workspace, ROOT
import diagnostic_series as series
from diagnostic_repetitions import prepare_repetitions


class SeriesProgressIntegrationTests(unittest.TestCase):
    def test_inner_work_is_visible_before_repetition_finishes_and_resume_stays_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = Workspace(root)
            plan = prepare_repetitions(workspace.path, ['blind_coding'], repetitions=2)
            harness = root / 'slow_synthetic_pipeline.py'
            source = (ROOT / 'tests/mock_pipeline.py').read_text(encoding='utf-8')
            source = source.replace('ROOT=Path(__file__).resolve().parents[1]', 'ROOT=Path(' + repr(str(ROOT)) + ')')
            # A 0.6s request can fall entirely between the production 2s polls.
            # Hold the first request until the real parent observer sees it;
            # missing progress still fails, but machine speed cannot hide it.
            acknowledgement = root / 'progress-observed'
            source = source.replace('def fake_chat(messages, **kwargs):',
                'def fake_chat(messages, **kwargs):\n'
                '    import time\n'
                f'    acknowledgement = Path({str(acknowledgement)!r})\n'
                '    deadline = time.monotonic() + 30\n'
                '    while not acknowledgement.exists():\n'
                '        if time.monotonic() >= deadline:\n'
                '            raise RuntimeError("Parent did not observe active request")\n'
                '        time.sleep(0.05)')
            harness.write_text(source, encoding='utf-8')
            env = {k: v for k, v in os.environ.items() if not k.startswith(('MOCK_', 'WORKFLOW_'))
                   and k != 'QUALITATIVE_MANAGED_OLLAMA_HOST'}
            env.update(MOCK_RUNTIME_EVIDENCE='1', MPLBACKEND='Agg', PYTHONUTF8='1')
            outer = []
            inner = []
            def capture(detail):
                inner.append({'series_completed': outer[-1][0], **detail})
                if (detail.get('sample_number') == 1 and
                        detail.get('detail', {}).get('active_requests', 0) > 0):
                    acknowledgement.touch()
            with patch.dict(os.environ, env, clear=True), patch.object(series, '_runner_command',
                    return_value=[sys.executable, str(harness)]):
                result = series.execute_repetitions(plan, root / 'series', progress=lambda *args: outer.append(args),
                                                   inner_progress=capture)
                self.assertEqual(result['status'], 'success')
                observed = [item for item in inner if item.get('detail', {}).get('active_requests', 0) > 0]
                self.assertTrue(observed, inner)
                self.assertTrue(any(item['series_completed'] == 0 and item['sample_number'] == 1 for item in observed))
                self.assertTrue(all(item['sample_total'] == 2 and item['configuration_number'] == 1 for item in inner))
                self.assertTrue(all(item['module'] in ('clusterer', 'blind_coding') for item in observed))
                self.assertNotIn('prompt', json.dumps(inner))
                self.assertIsNone(series._PROGRESS_POLL.get())
                with patch.object(series, '_execute', side_effect=AssertionError('Completed repetition dispatched')):
                    resumed = series.execute_repetitions(plan, root / 'series', resume=True,
                        inner_progress=lambda _: self.fail('No live child exists during complete resume'))
                self.assertEqual(resumed['completed_samples'], 2)


if __name__ == '__main__':
    unittest.main()
