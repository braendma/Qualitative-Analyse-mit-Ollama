"""Source aliases never substitute for verified module/artifact identities."""
import tempfile
import unittest
from pathlib import Path
from synthesis_inputs import resolve_sources, sources_from_module, bind_source_modules


def module(mid, artifact):
    return {'id': mid, 'script': mid + '.py', 'enabled': True,
            'args': ['--out-json', artifact], 'outputs': [artifact]}


class SynthesisInputTests(unittest.TestCase):
    def test_explicit_sources_do_not_pull_in_default_files(self):
        self.assertEqual(resolve_sources([' Alias = folder/a=b.json ']), {'Alias': 'folder/a=b.json'})
        self.assertEqual(len(resolve_sources()), 3)
        self.assertEqual(resolve_sources(comparison_json='renamed.json'), {'Personenvergleich': 'renamed.json'})

    def test_duplicate_alias_is_rejected_including_legacy_collision(self):
        for args, kwargs in [(['A=x.json', 'A=y.json'], {}),
                             (['A=x.json', ' A =x.json'], {}),
                             (['Meta-SWOT=x.json'], {'meta_swot_json': 'y.json'})]:
            with self.subTest(args=args), self.assertRaisesRegex(ValueError, 'mehrfach'):
                resolve_sources(args, **kwargs)

    def test_saved_module_arguments_resolve_identically_to_cli(self):
        declared = {'args': ['--config', '{config}', '--source-json=A=a.json',
                             '--source-json', 'B=b.json', '--comparison-json', 'c.json',
                             '--out-json', 'result.json']}
        self.assertEqual(sources_from_module(declared),
                         resolve_sources(['A=a.json', 'B=b.json'], comparison_json='c.json'))

    def test_malformed_or_duplicate_flags_fail_early(self):
        for args in [['--source-json'], ['--source-json', '--out-json', 'x'],
                     ['--source-json='], ['--source-json', '=path'],
                     ['--comparison-json', 'a', '--comparison-json=b']]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                sources_from_module({'args': args})

    def test_alias_and_renamed_artifact_bind_to_actual_module(self):
        with tempfile.TemporaryDirectory() as temp:
            modules = [module('swot', 'custom/result.json')]
            sources = {'Unusual label': str(Path(temp, 'custom', 'result.json'))}
            self.assertEqual(bind_source_modules(sources, modules, temp),
                             {'Unusual label': {'module_id': 'swot', 'artifact': 'custom/result.json'}})

    def test_label_or_default_filename_does_not_identify_module(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                bind_source_modules({'SWOT': 'swot_v1.json'}, [module('swot', 'actual.json')], temp)

    def test_ambiguous_disabled_or_replaced_modules_are_rejected(self):
        for mutation in ('ambiguous', 'disabled', 'replaced', 'duplicate', 'undeclared'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                modules = [module('swot', 'result.json')]
                if mutation == 'ambiguous':
                    modules.append(module('summarizer', 'result.json'))
                elif mutation == 'disabled':
                    modules[0]['enabled'] = False
                elif mutation == 'replaced':
                    modules[0]['script'] = 'custom.py'
                elif mutation == 'duplicate':
                    modules.append(module('swot', 'different.json'))
                else:
                    modules[0]['outputs'] = []
                with self.assertRaises(ValueError):
                    bind_source_modules({'Source': 'result.json'}, modules, temp)


if __name__ == '__main__':
    unittest.main()
