"""Lossless comparison-register encoding; no model calls."""
import copy
import json
import unittest
from thematic_interpretation import _register_table, _compact_register_table, _interpretation_prompt, CORRECTION
from runtime_context import message_bound, require_messages, ContextBudgetError


def decode_compact(table):
    decoded = []
    for encoded in table['rows']:
        row = [table['strings'][v['string']] if isinstance(v, dict) and set(v) == {'string'} else v
               for v in encoded]
        row = [row[v['prefix']] + v['suffix'] if isinstance(v, dict) and set(v) == {'prefix', 'suffix'} else v
               for v in row]
        result = {}
        def put(path, value):
            target = result
            for key in path[:-1]:
                target = target.setdefault(key, {})
            target[path[-1]] = copy.deepcopy(value)
        for field in table['shared_fields']:
            put(field['path'], field['value'])
        for paths, value in zip(table['column_groups'], row):
            for path in paths:
                put(path, value)
        decoded.append(result)
    return decoded


class CompactRegisterTests(unittest.TestCase):
    def test_roundtrip_preserves_types_nested_values_unicode_order_and_input(self):
        register = [{'label': 'Long shared label ' * 8, 'definition': 'Long shared label ' * 8 + '\nFinding ' + str(i),
                     'topic_id': str(i), 'scope': 'a' * 64, 'other_scope': 'a' * 64,
                     'nested': {'zero': 0, 'false': False, 'missing': None, 'list': [i, 'ae'], 'empty': {}},
                     'var': [0, False, None][i % 3]} for i in range(9)]
        before = copy.deepcopy(register)
        compact = _compact_register_table(_register_table(register))
        self.assertEqual(json.dumps(decode_compact(compact), sort_keys=True), json.dumps(register, sort_keys=True))
        self.assertEqual(register, before)
        # Shared label remains in shared_fields, without creating unresolved prefix references.
        self.assertFalse(any(isinstance(v, dict) and 'prefix' in v for r in compact['rows'] for v in r))

    def test_prefix_and_dictionary_references_expand_exactly(self):
        register = [{'label': ('Distinct label ' + str(i) + ' ') * 8,
                     'definition': ('Distinct label ' + str(i) + ' ') * 8 + '\nUnchanged finding',
                     'scope': str(i % 2) * 64, 'metric': i, 'same_metric': i}
                    for i in range(20)]
        compact = _compact_register_table(_register_table(register))
        self.assertEqual(decode_compact(compact), register)
        self.assertTrue(any(isinstance(v, dict) and 'prefix' in v for r in compact['rows'] for v in r))
        self.assertTrue(any(isinstance(v, dict) and 'string' in v for r in compact['rows'] for v in r))
        self.assertTrue(any(len(paths) > 1 for paths in compact['column_groups']))

    def test_small_prompt_unchanged_and_unique_oversize_text_still_rejected(self):
        payload = {'comparison_register': [{'topic_id': 'one', 'definition': 'short'}], 'qualitative_finding': 'short'}
        params = {'num_ctx': 57344, 'max_tokens': 8192}
        system, user = _interpretation_prompt(payload, params)
        self.assertEqual(json.loads(user), payload)
        payload['qualitative_finding'] = 'Unshortened ' * 10000
        system, user = _interpretation_prompt(payload, params)
        self.assertEqual(json.loads(user)['qualitative_finding'], payload['qualitative_finding'])
        with self.assertRaises(ContextBudgetError):
            require_messages([{'content': system}, {'content': user}, {'content': CORRECTION}], params)

if __name__ == '__main__':
    unittest.main()