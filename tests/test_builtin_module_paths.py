"""Path adapter contract tests; parse source AST without importing any CLI."""
import argparse
import ast
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import builtin_module_paths as adapter
from filesystem_paths import canonical_path, io_path
from process_commands import APPROVED_SCRIPTS
from project_paths import DEFAULT_CONFIG, SOURCE_DIR
from synthesis_inputs import resolve_sources


DIAGNOSTICS = {
    'coverage_analysis.py': 'coverage',
    'information_loss_analysis.py': 'information_loss',
    'codebook_diagnostics.py': 'codebook_diagnostics',
    'stability_analysis.py': 'stability',
    'sensitivity_analysis.py': 'sensitivity',
}


def parser_from_source(script):
    """Rebuild only literal argument declarations, no exec or module imports."""
    path = SOURCE_DIR / ('diagnostic_cli.py' if script in DIAGNOSTICS else script)
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    parser = argparse.ArgumentParser(allow_abbrev=False)
    declarations = sorted((node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == 'add_argument'), key=lambda node: node.lineno)
    for node in declarations:
        kwargs = {}
        for keyword in node.keywords:
            if keyword.arg == 'help':
                continue
            value = keyword.value
            if ast.unparse(value) == 'str(DEFAULT_CONFIG)':
                kwargs[keyword.arg] = str(DEFAULT_CONFIG)
            elif isinstance(value, ast.BinOp) and isinstance(value.left, ast.Name) and value.left.id == 'stem':
                kwargs[keyword.arg] = DIAGNOSTICS[script] + ast.literal_eval(value.right)
            else:
                kwargs[keyword.arg] = ast.literal_eval(value)
        parser.add_argument(*(ast.literal_eval(arg) for arg in node.args), **kwargs)
    return parser


class BuiltinModulePathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='builtin Pfade ä ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.run = self.root / 'Ergebnisse mit Leerzeichen'
        self.run.mkdir()

    def prepare(self, script, args=()):
        return adapter.prepare_builtin_arguments(SOURCE_DIR / script, args, self.run)

    def expected(self, path, base=None):
        return str(io_path((base or self.run) / path))

    def test_registry_covers_exactly_twenty_analysis_clis(self):
        self.assertEqual(set(adapter.BUILTIN_PATH_OPTIONS), APPROVED_SCRIPTS - {
            '00_WORKFLOW_RUNNER.py', 'local_app.py', 'managed_ollama.py',
            'codebook_refinement.py'})

    def test_registered_flags_aliases_and_defaults_match_actual_parsers(self):
        # Detect omitted future path arguments/default drift without importing
        # CLIs (whose top-level logging used to write files during import).
        for script, options in adapter.BUILTIN_PATH_OPTIONS.items():
            with self.subTest(script=script):
                parser = parser_from_source(script)
                actions = {a.option_strings[0]: a for a in parser._actions
                           if a.option_strings[0] != '-h'
                           and not isinstance(a, argparse._StoreTrueAction)}
                self.assertEqual(set(actions), {option.names[0] for option in options})
                for option in options:
                    action = actions[option.names[0]]
                    self.assertEqual(tuple(action.option_strings), option.names)
                    if option.names[0] != '--source-json':
                        self.assertEqual(action.default, option.default)

    def test_defaults_are_absolute_in_original_run_not_current_directory(self):
        for script in adapter.BUILTIN_PATH_OPTIONS:
            with self.subTest(script=script):
                args = ['--config', 'input config.yaml', '--input-csv', 'input.csv'] if script in DIAGNOSTICS else []
                parsed = parser_from_source(script).parse_args(self.prepare(script, args))
                for option in adapter.BUILTIN_PATH_OPTIONS[script]:
                    if option.default is None:
                        continue
                    dest = option.names[0][2:].replace('-', '_')
                    self.assertEqual(getattr(parsed, dest), self.expected(option.default))

    def test_config_relative_inputs_use_last_config_even_when_following_input(self):
        args = ['--input-csv', 'Segmente ä.csv', '--mock-responses-json=mock.json',
                '-c', 'earlier.yaml', '--config=study/config.yaml', '--codebook-csv', '../codes.csv']
        result = self.prepare('code_verification.py', args)
        parsed = parser_from_source('code_verification.py').parse_args(result)
        self.assertEqual(parsed.input_csv, self.expected('study/Segmente ä.csv'))
        self.assertEqual(parsed.mock_responses_json, self.expected('study/mock.json'))
        self.assertEqual(parsed.codebook_csv, self.expected('codes.csv'))
        self.assertEqual(result[3:5], ['-c', self.expected('earlier.yaml')])
        self.assertIn('--config=' + self.expected('study/config.yaml'), result)
        self.assertEqual(args[0:2], ['--input-csv', 'Segmente ä.csv'])

    def test_same_csv_flag_has_different_explicit_base_in_clusterer_and_thematic(self):
        args = ['--config', 'study/config.yaml', '--csv=segments.csv']
        cluster = parser_from_source('clusterer.py').parse_args(self.prepare('clusterer.py', args))
        thematic = parser_from_source('swot.py').parse_args(self.prepare('swot.py', args))
        self.assertEqual(cluster.csv, self.expected('segments.csv'))
        self.assertEqual(thematic.csv, self.expected('study/segments.csv'))

    def test_optional_checkpoint_and_missing_inputs_stay_absent_without_reading_config(self):
        for script in ('code_verification.py', 'blind_coding.py'):
            for checkpoint_setting in (False, True):
                with self.subTest(script=script, checkpoint=checkpoint_setting):
                    config = self.run / 'config.yaml'
                    config.write_text('coding_validation:\n  checkpoint: ' + str(checkpoint_setting).lower(), encoding='utf-8')
                    with patch.object(Path, 'read_text', side_effect=AssertionError('No study config read')):
                        result = self.prepare(script, ['--config', str(config)])
                    parsed = parser_from_source(script).parse_args(result)
                    self.assertIsNone(parsed.checkpoint)
                    self.assertIsNone(parsed.input_csv)
                    self.assertIsNone(parsed.codebook_csv)
                    self.assertIsNone(parsed.idmap_json)
                    self.assertIsNone(parsed.mock_responses_json)
        explicit = parser_from_source('blind_coding.py').parse_args(
            self.prepare('blind_coding.py', ['--checkpoint=manual.json']))
        self.assertEqual(explicit.checkpoint, self.expected('manual.json'))

    def test_diagnostics_keep_required_inputs_and_fill_run_output_defaults(self):
        for script, stem in DIAGNOSTICS.items():
            with self.subTest(script=script):
                result = self.prepare(script)
                self.assertNotIn('--config', result)
                self.assertNotIn('--input-csv', result)
                result = self.prepare(script, ['--config', 'study/config.yaml', '--input-csv', 'input.csv'])
                parsed = parser_from_source(script).parse_args(result)
                self.assertEqual(parsed.run_dir, self.expected('.'))
                self.assertEqual(parsed.input_csv, self.expected('input.csv'))
                self.assertEqual(parsed.out_json, self.expected(stem + '.json'))
                self.assertEqual(parsed.out_md, self.expected(stem + '.md'))
                custom = parser_from_source(script).parse_args(self.prepare(script, [
                    '--config', 'c.yaml', '--input-csv', 'i.csv', '--run-dir=other',
                    '--out-json=outputs/x.json', '--out-md', 'outputs/x.md']))
                self.assertEqual(custom.run_dir, self.expected('other'))
                self.assertEqual(custom.out_json, self.expected('outputs/x.json'))

    def test_alias_equals_and_attached_short_value_keep_layout_and_last_value(self):
        result = self.prepare('clusterer.py', ['-cstudy/c.yaml', '-o', 'first.md',
                                             '--out-md=second.md', '-x=chosen.json'])
        self.assertEqual(result[:5], ['-c' + self.expected('study/c.yaml'),
                                     '-o', self.expected('first.md'),
                                     '--out-md=' + self.expected('second.md'),
                                     '-x=' + self.expected('chosen.json')])
        parsed = parser_from_source('clusterer.py').parse_args(result)
        self.assertEqual(parsed.out_md, self.expected('second.md'))
        self.assertEqual(sum(t == '--out-md' for t in result), 0)

    def test_sources_keep_labels_repetition_equals_and_no_missing_subset_fallback(self):
        result = self.prepare('overall_synthesis.py', [
            '--source-json', ' Aussagen =sources/a=b.json ',
            '--source-json=Zählung=sources/count.json'])
        parsed = parser_from_source('overall_synthesis.py').parse_args(result)
        self.assertEqual(parsed.source_json, [
            'Aussagen=' + self.expected('sources/a=b.json'),
            'Zählung=' + self.expected('sources/count.json')])
        self.assertIsNone(parsed.meta_swot_json)
        self.assertIsNone(parsed.comparison_json)
        self.assertIsNone(parsed.contrast_json)
        legacy = parser_from_source('overall_synthesis.py').parse_args(
            self.prepare('overall_synthesis.py', ['--comparison-json=one.json']))
        self.assertEqual(legacy.comparison_json, self.expected('one.json'))
        self.assertIsNone(legacy.meta_swot_json)

    def test_synthesis_default_and_duplicate_label_validation_stay_equivalent(self):
        parsed = parser_from_source('overall_synthesis.py').parse_args(self.prepare('overall_synthesis.py'))
        sources = resolve_sources(parsed.source_json, meta_swot_json=parsed.meta_swot_json,
            comparison_json=parsed.comparison_json, contrast_json=parsed.contrast_json)
        self.assertEqual(sources, {label: self.expected(path) for label, path in resolve_sources().items()})
        duplicate = parser_from_source('overall_synthesis.py').parse_args(self.prepare(
            'overall_synthesis.py', ['--source-json', 'X=a.json', '--source-json', 'X=b.json']))
        with self.assertRaisesRegex(ValueError, 'mehrfach'):
            resolve_sources(duplicate.source_json)
        for value in ('missing separator', '=empty-label', 'label='):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.prepare('overall_synthesis.py', ['--source-json', value])

    def test_unknown_arguments_and_double_dash_tail_are_untouched(self):
        args = ['--unknown-path=foo.csv', '--unknown', 'bar.json', '--log-raw',
                '--', '--out-md', 'not-an-option.md']
        result = self.prepare('clusterer.py', args)
        self.assertEqual(result[:4], args[:4])
        self.assertEqual(result[result.index('--'):], args[4:])
        self.assertIn(self.expected('clusterer_output.md'), result[:result.index('--')])

    def test_missing_known_values_fail_without_becoming_accidental_paths(self):
        for args in (['--out-md'], ['--config', '--out-md', 'report.md'], ['-o', '--']):
            with self.subTest(args=args), self.assertRaisesRegex(ValueError, 'Dateipfad fehlt'):
                self.prepare('clusterer.py', args)

    def test_abbreviated_path_flags_fail_clearly_instead_of_overriding_user_path(self):
        for args in (['--out-j', 'chosen.json'], ['--out-j=chosen.json'],
                     ['--out', 'chosen.json'], ['--conf=study.yaml']):
            with self.subTest(args=args), self.assertRaisesRegex(ValueError, 'Vollständige Option verwenden: --'):
                self.prepare('clusterer.py', args)
        with self.assertRaisesRegex(ValueError, '--out-json'):
            self.prepare('clusterer.py', ['--out-j', 'chosen.json'])
        # An unrelated unknown argument, a non-path abbreviation and tokens
        # after '--' remain untouched for the original parser to judge.
        args = ['--new-setting=value', '--log-r', '--', '--out-j=literal']
        result = self.prepare('clusterer.py', args)
        self.assertEqual(result[:2], args[:2])
        self.assertEqual(result[result.index('--'):], args[2:])

    def test_foreign_same_named_and_infrastructure_scripts_keep_original_contract(self):
        foreign = self.root / 'clusterer.py'
        foreign.write_text('pass\n', encoding='utf-8')
        cases = [foreign, 'clusterer.py', SOURCE_DIR / 'unknown.py',
                 SOURCE_DIR / 'local_app.py', SOURCE_DIR / '00_WORKFLOW_RUNNER.py',
                 SOURCE_DIR / 'managed_ollama.py', SOURCE_DIR / 'codebook_refinement.py']
        for script in cases:
            with self.subTest(script=script):
                self.assertIsNone(adapter.prepare_builtin_arguments(script, ['--own', 'relative.csv'], self.run))

    def test_redirected_installed_script_does_not_inherit_builtin_contract(self):
        real_canonical = adapter.canonical_path
        script = SOURCE_DIR / 'clusterer.py'
        def redirected(path):
            return self.root / 'outside.py' if Path(path) == script else real_canonical(path)
        with patch.object(adapter, 'canonical_path', side_effect=redirected):
            self.assertIsNone(adapter.prepare_builtin_arguments(script, [], self.run))

    def test_absolute_unicode_paths_preserve_identity(self):
        target = self.root / 'ä anderer Ordner' / 'datei=1.md'
        result = self.prepare('swot.py', ['--out-md', str(target)])
        parsed = parser_from_source('swot.py').parse_args(result)
        self.assertEqual(canonical_path(parsed.out_md), canonical_path(target))
        self.assertEqual(parsed.out_md, str(io_path(target)))

    def test_standard_pipeline_argv_remains_parseable_and_artifacts_keep_run_identity(self):
        import yaml
        config = yaml.safe_load(DEFAULT_CONFIG.read_text(encoding='utf-8'))
        replacements = {'config': str(self.run / 'config_snapshot.yaml'),
                        'input_csv': str(self.root / 'Segmentdaten.csv'),
                        'log_raw_flag': ''}
        for module in config['pipeline']['modules']:
            with self.subTest(module=module['id']):
                original = [token.format(**replacements) for token in module['args']]
                original = [token for token in original if token]
                parser = parser_from_source(module['script'])
                before = parser.parse_args(original)
                after = parser.parse_args(self.prepare(module['script'], original))
                self.assertEqual(canonical_path(after.config), canonical_path(before.config))
                for option in adapter.BUILTIN_PATH_OPTIONS[module['script']]:
                    if option.names[0] == '--source-json':
                        continue
                    dest = option.names[0][2:].replace('-', '_')
                    previous, normalized = getattr(before, dest), getattr(after, dest)
                    if previous is None:
                        # Only overall_synthesis can conditionally materialize
                        # fallback sources. The shipped pipeline is explicit.
                        self.assertIsNone(normalized)
                    else:
                        base = Path(before.config).parent if option.base == 'config' else self.run
                        self.assertEqual(canonical_path(normalized), canonical_path(base / previous))

    def test_deep_run_with_parent_relative_output_uses_io_form_without_creating_files(self):
        deep = self.run.joinpath(*(['very long synthetic folder name'] * 8))
        result = adapter.prepare_builtin_arguments(SOURCE_DIR / 'clusterer.py',
            ['--out-json', '../sibling/result.json'], deep)
        parsed = parser_from_source('clusterer.py').parse_args(result)
        expected = deep.parent / 'sibling/result.json'
        self.assertEqual(canonical_path(parsed.out_json), canonical_path(expected))
        self.assertFalse(deep.exists())
        if os.name == 'nt':
            self.assertGreater(len(parsed.out_json), 260)
            self.assertTrue(parsed.out_json.startswith('\\\\?\\'))
            self.assertNotIn('..', Path(parsed.out_json).parts)


if __name__ == '__main__':
    unittest.main()
