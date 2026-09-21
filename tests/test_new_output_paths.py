import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from output_path_advice import _path_limits, require_new_output_paths


class NewOutputPathTests(unittest.TestCase):
    def test_real_onedrive_boundaries_not_explorer_threshold(self):
        with tempfile.TemporaryDirectory() as temp:
            cloud = Path(temp)
            with patch.dict(os.environ, {'OneDrive': str(cloud), 'OneDriveConsumer': '', 'OneDriveCommercial': ''}):
                exact = cloud / ('a' * 190) / ('b' * 209)
                self.assertEqual(_path_limits(exact), [])
                self.assertTrue(any('401' in reason for reason in _path_limits(exact.with_name('b' * 210))))
                self.assertEqual(_path_limits(cloud.with_name(cloud.name + '-sibling') / ('a' * 190) / ('b' * 210)), [])
                self.assertEqual(list(cloud.iterdir()), [])

    def test_component_and_unicode_limits(self):
        root = Path(tempfile.gettempdir())
        self.assertEqual(_path_limits(root / ('a' * 255)), [])
        self.assertTrue(any('255' in reason for reason in _path_limits(root / ('a' * 256))))
        self.assertTrue(any('255' in reason for reason in _path_limits(root / ('😀' * 128))))

    def test_local_sync_total_bound_is_independent_of_relative_bound(self):
        cloud = Path(tempfile.gettempdir()) / ('root' * 35)
        with patch.dict(os.environ, {'OneDrive': str(cloud), 'OneDriveConsumer': '', 'OneDriveCommercial': ''}):
            reasons = _path_limits(cloud / ('a' * 190) / ('b' * 200))
            self.assertTrue(any('520' in reason for reason in reasons))
            self.assertFalse(any('400' in reason for reason in reasons))

    def test_declared_outputs_and_actual_selected_series_names_are_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            cloud = Path(temp)
            root = cloud / ('a' * 130) / ('b' * 100)
            modules = [{'id': 'clusterer', 'outputs': ['clusters.json'], 'requires_model': True}]
            config = {'pipeline': {'modules': modules}}
            with patch.dict(os.environ, {'OneDrive': str(cloud), 'OneDriveConsumer': '', 'OneDriveCommercial': ''}):
                require_new_output_paths(root, modules)
                short = {'kind': 'sensitivity', 'configurations': [{'configuration_id': 'x', 'config': config}],
                         'samples': [{'sample_id': 'x-repeat-001', 'configuration_id': 'x'}]}
                require_new_output_paths(root, modules, plans=(short,))
                long = {**short, 'samples': [{'sample_id': 'v' * 40 + '-repeat-001', 'configuration_id': 'x'}]}
                with self.assertRaisesRegex(ValueError, 'OneDrive-relativer.*Reserve'):
                    require_new_output_paths(root, modules, plans=(long,))
                with self.assertRaisesRegex(ValueError, 'deklarierte Modulausgabe'):
                    require_new_output_paths(root, [{'id': 'custom', 'outputs': ['x' * 175 + '.json']}])
                self.assertEqual(list(cloud.iterdir()), [])

    def test_app_rechecks_new_destination_before_binding_or_model_preflight(self):
        from test_local_app import settings
        from local_app import App
        with tempfile.TemporaryDirectory() as temp:
            app = App(temp)
            pid = app.create('Synthetic path rejection', True)['id']
            opts = settings(app)
            app.save(pid, opts)
            with patch('output_path_advice.require_new_output_paths', side_effect=ValueError('OneDrive-Pfad zu lang')), \
                    patch('job_storage.create_binding') as bind, patch('managed_ollama.preflight') as model, \
                    patch('local_app.subprocess.Popen') as spawn:
                with self.assertRaisesRegex(ValueError, 'OneDrive-Pfad'):
                    app.start(pid)
                bind.assert_not_called(); model.assert_not_called(); spawn.assert_not_called()
            self.assertTrue(app.jobs(pid)[0]['start_rejected'])
            self.assertEqual(list(Path(opts['output_dir']).iterdir()), [])

    def test_real_cli_rejects_before_run_manifest_and_model_start(self):
        import importlib
        from test_entrypoint_paths import EntryPointPathsTests
        runner = importlib.import_module('00_WORKFLOW_RUNNER')
        with tempfile.TemporaryDirectory() as temp:
            cloud = Path(temp)
            workspace = EntryPointPathsTests().workspace(cloud)
            destination = cloud / ('a' * 190) / ('b' * 180)
            with patch.dict(os.environ, {'OneDrive': str(cloud), 'OneDriveConsumer': '', 'OneDriveCommercial': ''}), \
                    patch('managed_ollama.ManagedOllama.start') as model:
                with self.assertRaisesRegex(ValueError, 'OneDrive-relativer'):
                    runner.main(['--config', str(workspace.path), '--output-dir', str(destination)])
                model.assert_not_called()
            from filesystem_paths import io_path
            self.assertEqual(list(io_path(destination).iterdir()), [])
            # Remove our two known empty directories using the same long-path
            # IO syntax; TemporaryDirectory's ordinary path can hit MAX_PATH.
            io_path(destination).rmdir()
            io_path(destination.parent).rmdir()


if __name__ == '__main__':
    unittest.main()
