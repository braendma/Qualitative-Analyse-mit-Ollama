import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import clusterer_core as cluster
from llm_client import LLMResponseError, LLMTransportError


class ClusterCoverageRepairTests(unittest.TestCase):
    segments = [{'id': 's1', 'text': 'Es klappt.'}, {'id': 's2', 'text': 'Es klappt nicht.'}]
    partial = [{'cluster_name': 'positiv', 'definition': 'Erfolg', 'segments': ['s1']}]

    def test_run_repairs_omission_with_original_inputs_and_preserves_quotes(self):
        frame = pd.DataFrame([
            {'Dokumentname': 'P1', 'Code': 'A', 'Segment': item['text'], 'ID': item['id']}
            for item in self.segments])
        repaired = {'clusters': [self.partial[0], {'cluster_name': 'negativ', 'definition': 'Misserfolg', 'segments': ['s2', 'foreign']}]}
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(cluster, 'llm_cluster', return_value=json.dumps({'clusters': self.partial})), \
                patch.object(cluster, 'llm_self_repair', return_value=json.dumps(repaired)) as repair, \
                patch.object(cluster, 'plot_clusters', return_value=None):
            _, result = cluster.run_clustering(frame, {'model': 'mock', 'temperature': 0, 'max_tokens': 100},
                {'cluster_analysis': {'system': 'test', 'user': '{segments}'}, 'json_schema': '{}'}, {},
                plots_dir=tmp, id_to_text_path=str(Path(tmp) / 'map.json'))
            repair.assert_called_once()
            prompt = repair.call_args.args[1]
            self.assertIn('Es klappt nicht.', prompt)
            self.assertIn('Es klappt.', prompt)
            self.assertIn('"s2"', prompt)
            self.assertEqual({s for c in result['clusters'] for s in c['segments']}, {'s1', 's2'})
            self.assertEqual(json.loads((Path(tmp) / 'map.json').read_text(encoding='utf-8')), {'s1': 'Es klappt.', 's2': 'Es klappt nicht.'})

    def test_exhausted_repairs_fail_instead_of_inventing_assignments(self):
        with patch.object(cluster, 'llm_self_repair', return_value=json.dumps({'clusters': self.partial})) as repair:
            with self.assertRaisesRegex(LLMResponseError, '1 Segmente fehlen'):
                cluster.repair_cluster_coverage(self.partial, self.segments, 'system', 'original', {})
            self.assertEqual(repair.call_count, 2)

    def test_malformed_and_foreign_only_repairs_never_count_as_complete(self):
        with patch.object(cluster, 'llm_self_repair', side_effect=['bad', json.dumps({'clusters': [{'segments': ['foreign']}]})]) as repair:
            with self.assertRaisesRegex(LLMResponseError, '2 Segmente fehlen'):
                cluster.repair_cluster_coverage(self.partial, self.segments, 'system', 'original', {})
            self.assertEqual(repair.call_count, 2)

    def test_complete_answer_needs_no_additional_request(self):
        complete = [{'segments': ['s1', 's2']}]
        with patch.object(cluster, 'llm_self_repair') as repair:
            self.assertEqual(cluster.repair_cluster_coverage(complete, self.segments, 'system', 'original', {}), complete)
            repair.assert_not_called()

    def test_transport_error_propagates_without_coverage_retries(self):
        with patch.object(cluster, 'llm_self_repair', side_effect=LLMTransportError('offline')) as repair:
            with self.assertRaises(LLMTransportError):
                cluster.repair_cluster_coverage(self.partial, self.segments, 'system', 'original', {})
            repair.assert_called_once()


if __name__ == '__main__':
    unittest.main()
