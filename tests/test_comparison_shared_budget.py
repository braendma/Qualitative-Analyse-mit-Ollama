import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from summary_reduction import reduce_prompt
from comparison_reduction import prepare_people


class SharedBudgetTests(unittest.TestCase):
    def test_soft_target_retains_complete_smallest_input_after_bounded_retries(self):
        original = 'Vollständiger Befund. ' * 60
        seen = []
        def model(s, u, p):
            seen.append(u)
            return 'x' * 3000
        result = reduce_prompt('sys', original, {'num_ctx':8192, 'max_tokens':2048},
                               model, target_bytes=256, allow_target_overflow=True)
        self.assertEqual(result, original)
        self.assertEqual(len(seen), 4)
        self.assertEqual(seen[-1], original)

    def test_uneven_person_sizes_fit_shared_budget_without_omissions(self):
        persons = {f'P{i}': {'person':f'P{i}', 'analysis':'Befund ' * 1000} for i in range(10)}
        prompt = lambda p: ('Vergleiche vollständig', json.dumps(p, ensure_ascii=False))
        seen = []
        def reduce(s, u, p, summarize, **kwargs):
            source = json.loads(u)
            seen.append(source)
            self.assertTrue(kwargs['allow_target_overflow'])
            return 'ä' * (600 if source['person']=='P0' else 25)
        params = {'num_ctx':8192, 'max_tokens':2048, 'partial_checkpoints':False}
        with patch('comparison_reduction.reduce_prompt', side_effect=reduce):
            payload, ledger = prepare_people(persons, prompt, params, None)
        self.assertCountEqual([x['person'] for x in payload['personen']], persons)
        self.assertEqual(len(seen), len(persons))
        self.assertEqual(seen[0], persons['P0'])
        self.assertGreater(ledger['actual_bytes_per_person']['P0'], ledger['target_bytes_per_person'])
        self.assertLessEqual(sum(len(s.encode('utf-8')) for s in prompt(payload))+2048+1024,8192)

    def test_shared_budget_still_rejects_oversized_combined_payload(self):
        persons = {f'P{i}': {'person':f'P{i}', 'analysis':'x'*5000} for i in range(10)}
        with patch('comparison_reduction.reduce_prompt', return_value='x'*1500):
            with self.assertRaisesRegex(ValueError, 'Kontextfenster'):
                prepare_people(persons, lambda p: ('sys', json.dumps(p)),
                               {'num_ctx':8192, 'max_tokens':2048, 'partial_checkpoints':False}, None)


if __name__ == '__main__': unittest.main()
