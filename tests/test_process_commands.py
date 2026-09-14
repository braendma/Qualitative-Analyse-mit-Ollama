import builtins
from contextlib import ExitStack, redirect_stderr
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import process_commands as commands
import project_paths
import runtime_entry


class ProcessCommandsTests(unittest.TestCase):
    def test_source_preserves_custom_script_and_argument_layout(self):
        with tempfile.TemporaryDirectory(prefix='source ä ') as temp:
            custom = Path(temp) / 'own module.py'
            custom.write_text('pass\n', encoding='utf-8')
            args = ['--config', 'Study ä/config.yaml', '--command', 'x', '--internal-script', 'y']
            with patch.object(sys, 'frozen', False, create=True):
                self.assertEqual(commands.python_command(custom, args), [sys.executable, str(custom), *args])
                self.assertEqual(commands.python_command('./relative.py'), [sys.executable, './relative.py'])
                self.assertEqual(commands.validate_script(custom), custom)

    def test_fixed_allowlist_matches_standard_scripts_plus_explicit_tools(self):
        # This test reads the shipped config, but production never trusts a YAML
        # to extend the internal command list.
        import yaml
        config = yaml.safe_load((project_paths.PROJECT_DIR / 'config/config_v2.yaml').read_text(encoding='utf-8'))
        modules = config['pipeline']['modules']
        standard = {m['script'] for m in modules}
        self.assertEqual(len(standard), 20)
        self.assertEqual(commands.APPROVED_SCRIPTS, standard | {
            '00_WORKFLOW_RUNNER.py', 'codebook_refinement.py', 'managed_ollama.py', 'local_app.py'})

    def test_frozen_approved_targets_and_nested_args(self):
        with tempfile.TemporaryDirectory(prefix='bundle ä ') as temp:
            source = Path(temp).resolve() / 'src'; source.mkdir()
            with patch.object(commands, 'SOURCE_DIR', source), patch.object(sys, 'frozen', True, create=True):
                for name in sorted(commands.APPROVED_SCRIPTS):
                    script = source / name; script.write_text('pass\n', encoding='utf-8')
                    args = ['--command', 'binary with spaces', '--internal-script', 'clusterer.py', 'ä']
                    self.assertEqual(commands.python_command(script, args),
                                     [sys.executable, '--internal-script', name, *args])

    def test_frozen_rejects_foreign_basename_missing_relative_traversal_and_helper(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); source = root / 'src'; source.mkdir()
            (source / 'clusterer.py').write_text('pass\n', encoding='utf-8')
            (source / 'helper.py').write_text('pass\n', encoding='utf-8')
            foreign = root / 'clusterer.py'; foreign.write_text('pass\n', encoding='utf-8')
            (source / 'sub').mkdir()
            forbidden = [foreign, 'clusterer.py', source / 'unknown.py', source / 'helper.py',
                         source / 'sub' / '..' / 'clusterer.py', source / 'local_app.py', source]
            with patch.object(commands, 'SOURCE_DIR', source), patch.object(sys, 'frozen', True, create=True):
                for script in forbidden:
                    with self.subTest(script=script), self.assertRaisesRegex(ValueError, 'nicht als Einstieg'):
                        commands.python_command(script)

    def test_frozen_rejects_link_to_other_approved_file(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp).resolve(); target = source / 'clusterer.py'
            target.write_text('pass\n', encoding='utf-8')
            alias = source / 'summarizer.py'; alias.write_text('pass\n', encoding='utf-8')
            original = Path.resolve
            def redirected(path, *args, **kwargs):
                return target if path == alias else original(path, *args, **kwargs)
            with patch.object(commands, 'SOURCE_DIR', source), patch.object(sys, 'frozen', True, create=True), patch.object(Path, 'resolve', redirected):
                with self.assertRaisesRegex(ValueError, 'nicht als Einstieg'):
                    commands.validate_script(alias)


class RuntimeEntryTests(unittest.TestCase):
    def test_invalid_dispatch_never_runs_or_imports_ui(self):
        real_import = builtins.__import__
        def guarded(name, *args, **kwargs):
            if name == 'local_app':
                raise AssertionError('UI imported by internal dispatch')
            return real_import(name, *args, **kwargs)
        cases = [['--internal-script'], ['--internal-script', '../clusterer.py'],
                 ['--internal-script', str(project_paths.SOURCE_DIR / 'clusterer.py')],
                 ['--internal-script', 'helper.py'], ['--internal-script', 'src/clusterer.py'],
                 ['--internal-script', 'src\\clusterer.py'], ['--port', '8000', '--internal-script', 'local_app.py']]
        with patch('builtins.__import__', guarded), patch.object(runtime_entry.runpy, 'run_path') as run, redirect_stderr(io.StringIO()):
            for args in cases:
                with self.subTest(args=args):
                    self.assertEqual(runtime_entry.main(args), 2)
            run.assert_not_called()

    def test_internal_actual_script_preserves_argv_cwd_and_systemexit(self):
        with tempfile.TemporaryDirectory(prefix='runtime ä ') as temp:
            source = Path(temp).resolve(); script = source / '00_WORKFLOW_RUNNER.py'
            output = source / 'observation.json'
            args = ['--config', 'relative config ä.yaml', '--output-dir', str(output)]
            original_argv, original_path, original_cwd = sys.argv, sys.path[:], os.getcwd()
            for frozen in (False, True):
                for code in (0, 7, 75):
                    script.write_text('import json, os, sys\n'
                        f'with open({str(output)!r}, "w", encoding="utf-8") as out:\n'
                        '    json.dump({"argv": sys.argv, "cwd": os.getcwd()}, out)\n'
                        f'raise SystemExit({code})\n', encoding='utf-8')
                    with self.subTest(frozen=frozen, code=code), ExitStack() as stack:
                        stack.enter_context(patch.object(project_paths, 'SOURCE_DIR', source))
                        stack.enter_context(patch.object(commands, 'SOURCE_DIR', source))
                        stack.enter_context(patch.object(sys, 'frozen', frozen, create=True))
                        with self.assertRaises(SystemExit) as caught:
                            runtime_entry.main(['--internal-script', script.name, *args])
                        self.assertEqual(caught.exception.code, code)
                        data = json.loads(output.read_text(encoding='utf-8'))
                        self.assertEqual(data, {'argv': [str(script), *args], 'cwd': original_cwd})
                        self.assertIs(sys.argv, original_argv)
                        self.assertEqual(sys.path, original_path)

    def test_default_dispatch_forwards_app_arguments_without_preimport(self):
        with patch.object(runtime_entry.runpy, 'run_path') as run:
            observed = []
            run.side_effect = lambda path, **kwargs: observed.append((path, sys.argv[:], kwargs))
            self.assertEqual(runtime_entry.main(['--port', '12345']), 0)
            script = str(project_paths.SOURCE_DIR / 'local_app.py')
            self.assertEqual(observed, [(script, [script, '--port', '12345'], {'run_name': '__main__'})])

    def test_missing_resource_fails_without_default_ui_fallback(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(project_paths, 'SOURCE_DIR', Path(temp)), patch.object(runtime_entry.runpy, 'run_path') as run, redirect_stderr(io.StringIO()):
            self.assertEqual(runtime_entry.main(['--internal-script', 'clusterer.py']), 2)
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
