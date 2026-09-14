"""Windows identity aliases must never bypass diagnostic write protection."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from test_codebook_diagnostic_loader import Workspace
import codebook_diagnostics
from diagnostic_cli import run_diagnostic
from filesystem_paths import canonical_path, io_path


@unittest.skipUnless(os.name == 'nt', 'Normal/extended Windows path aliases')
class DiagnosticPathAliasTests(unittest.TestCase):
    def environment(self, module):
        env = {key: value for key, value in os.environ.items() if not key.startswith('WORKFLOW_')}
        env.update(WORKFLOW_RUN_ID='synthetic-codebook', WORKFLOW_MODULE=module)
        return patch.dict(os.environ, env, clear=True)

    def before(self, root):
        return {path: path.read_bytes() for path in root.rglob('*') if path.is_file()}

    def unchanged(self, saved):
        for path, data in saved.items():
            self.assertEqual(path.read_bytes(), data, 'Protected synthetic file changed: ' + path.name)

    def test_own_retry_protects_all_originals_in_both_alias_directions(self):
        for protected_extended in (True, False):
            for target_name in ('config.yaml', 'input.csv', 'book.csv', 'workflow_manifest.json',
                                'config_snapshot.yaml', 'verify-custom.json'):
                with self.subTest(protected_extended=protected_extended, target=target_name), tempfile.TemporaryDirectory() as tmp:
                    w = Workspace(Path(tmp).resolve())
                    w.manifest['module_status']['codebook_diagnostics'] = 'running'; w.save_manifest()
                    (w.root / 'config_snapshot.yaml').write_text('immutable synthetic snapshot', encoding='utf-8')
                    protected_form = io_path if protected_extended else canonical_path
                    output_form = canonical_path if protected_extended else io_path
                    args = ['--config', str(protected_form(w.config)), '--input-csv', str(protected_form(w.source)),
                            '--run-dir', str(protected_form(w.root)), '--out-json', str(output_form(w.root / target_name)),
                            '--out-md', str(output_form(w.root / 'fresh.md'))]
                    saved = self.before(w.root)
                    loader = Mock(side_effect=AssertionError('Unsafe output reached the diagnostic loader'))
                    analyze = Mock(side_effect=AssertionError('Unsafe output reached analysis'))
                    # The category resolver now returns IO paths. Exercise its
                    # opposite valid representation too, independently of guards.
                    with self.environment('codebook_diagnostics'), patch('diagnostic_cli.resolve_config_path', return_value=protected_form(w.book)), \
                         patch.object(codebook_diagnostics, 'load_codebook_snapshot', loader), \
                         patch.object(codebook_diagnostics, 'analyze_snapshot', analyze):
                        try:
                            with self.assertRaisesRegex(ValueError, 'überschreiben'):
                                codebook_diagnostics.main(args)
                        finally:
                            self.unchanged(saved)
                            self.assertFalse((w.root / 'fresh.md').exists())
                    loader.assert_not_called(); analyze.assert_not_called()

    def test_reserved_series_paths_are_protected_in_both_alias_directions(self):
        for kind in ('stability', 'sensitivity'):
            for protected_extended in (True, False):
                with self.subTest(kind=kind, protected_extended=protected_extended), tempfile.TemporaryDirectory() as tmp:
                    w = Workspace(Path(tmp).resolve())
                    w.manifest['module_status'][kind] = 'running'; w.save_manifest()
                    name = '_' + kind + '_repetitions'
                    folder = w.root / name; folder.mkdir()
                    target = folder / 'keep.json'; target.write_text('{"synthetic":"preserve"}', encoding='utf-8')
                    protected_form = io_path if protected_extended else canonical_path
                    output_form = canonical_path if protected_extended else io_path
                    args = ['--config', str(protected_form(w.config)), '--input-csv', str(protected_form(w.source)),
                            '--run-dir', str(protected_form(w.root)), '--out-json', str(output_form(target)),
                            '--out-md', str(output_form(w.root / 'fresh.md'))]
                    saved = self.before(w.root)
                    loader = Mock(side_effect=AssertionError('Reserved directory reached loader'))
                    analyze = Mock(side_effect=AssertionError('Reserved directory reached analysis'))
                    with self.environment(kind):
                        try:
                            with self.assertRaisesRegex(ValueError, 'Serienverzeichnisse'):
                                run_diagnostic(kind, kind, 'Synthetic guard test', analyze, str, args,
                                               loader=loader, reserved_subdirectories=(name,))
                        finally:
                            self.unchanged(saved)
                            self.assertFalse((w.root / 'fresh.md').exists())
                    loader.assert_not_called(); analyze.assert_not_called()

    def test_output_aliases_of_each_other_are_not_two_independent_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = Workspace(Path(tmp).resolve())
            w.manifest['module_status']['codebook_diagnostics'] = 'running'; w.save_manifest()
            target = w.root / 'same-output.json'; target.write_text('synthetic previous output', encoding='utf-8')
            args = ['--config', str(w.config), '--input-csv', str(w.source), '--run-dir', str(w.root),
                    '--out-json', str(canonical_path(target)), '--out-md', str(io_path(target))]
            saved = self.before(w.root)
            loader = Mock(side_effect=AssertionError('Duplicate output identity reached loader'))
            with self.environment('codebook_diagnostics'), patch.object(codebook_diagnostics, 'load_codebook_snapshot', loader):
                try:
                    with self.assertRaisesRegex(ValueError, 'überschreiben'):
                        codebook_diagnostics.main(args)
                finally:
                    self.unchanged(saved)
            loader.assert_not_called()

    def test_original_inputs_cannot_be_inside_either_internal_series_via_alias(self):
        import stability_analysis
        for kind in ('stability', 'sensitivity'):
            for source_name in ('config', 'input', 'codebook'):
                for extended_input in (True, False):
                    with self.subTest(kind=kind, source=source_name, extended=extended_input), tempfile.TemporaryDirectory() as tmp:
                        w = Workspace(Path(tmp).resolve())
                        folder = w.root / ('_' + kind + '_repetitions'); folder.mkdir()
                        original = folder / 'original.csv'; original.write_text('synthetic protected input', encoding='utf-8')
                        incoming = io_path(original) if extended_input else canonical_path(original)
                        directory = canonical_path(w.root) if extended_input else io_path(w.root)
                        config = incoming if source_name == 'config' else w.config
                        source = incoming if source_name == 'input' else w.source
                        book = incoming if source_name == 'codebook' else w.book
                        manifest = {**w.manifest, 'fingerprint': 'synthetic-fingerprint',
                                    'module_status': {kind: 'running'}}
                        saved = self.before(w.root)
                        with self.environment(kind), patch.dict(os.environ, {'WORKFLOW_FINGERPRINT': 'synthetic-fingerprint'}), \
                             patch.object(stability_analysis, 'load_input_context', return_value=(w.cfg, manifest, book)), \
                             patch.object(stability_analysis, 'configured_plan', return_value={'synthetic': True}):
                            try:
                                with self.assertRaisesRegex(ValueError, 'Originaleingaben'):
                                    stability_analysis._load_context(directory, config, source, kind=kind)
                            finally:
                                self.unchanged(saved)


if __name__ == '__main__': unittest.main()
