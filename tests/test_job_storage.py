import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import job_storage as storage
from filesystem_paths import canonical_path
from runtime_support import atomic_json, file_hash, exclusive_file_lock


def workspace(root):
    folder = root / 'projects' / ('a' * 20) / 'jobs' / ('b' * 20)
    folder.mkdir(parents=True)
    config = folder.parent.parent / 'revisions' / ('c' * 20) / 'config.yaml'
    config.parent.mkdir(parents=True); config.write_text('synthetic: true\n', encoding='utf-8')
    parent = root / 'Forschung Ä mit Leerzeichen'; parent.mkdir()
    job = {'config': str(config)}
    return folder, config, parent, job


def bound_workspace(root):
    folder, config, parent, job = workspace(root)
    job['storage'] = storage.create_binding(folder, config, parent)
    return folder, config, parent, job


def write_run(folder, job, name='synthetic-run'):
    path = storage.runs_root(folder, job) / name; path.mkdir(parents=True)
    atomic_json(path / 'workflow_manifest.json', {'run_id': name, 'status': 'running',
        'output_dir': str(path.resolve()), 'provenance': {'config_sha256': file_hash(job['config'])}})
    return path


class JobStorageTests(unittest.TestCase):
    def test_create_preserves_config_and_binds_external_review_and_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, config, parent, job = bound_workspace(Path(temp))
            root = storage.research_root(folder, job)
            self.assertEqual(canonical_path(root.parent), parent.resolve())
            self.assertTrue(root.name.startswith('QualitativeAnalyse_'))
            self.assertEqual(storage.config_path(folder, job), config.resolve())
            self.assertEqual(storage.runs_root(folder, job), root / 'runs')
            self.assertEqual(storage.review_root(folder, job), root / 'review')
            self.assertFalse((root / 'review').exists())
            self.assertIsNone(storage.run_path(folder, job))
            self.assertEqual(config.read_text(encoding='utf-8'), 'synthetic: true\n')
            self.assertFalse((folder / 'runs').exists())
            with self.assertRaises(ValueError): storage.create_binding(folder, config, parent)

    def test_run_is_pinned_without_racing_job_index_and_manifest_updates_are_allowed(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, _, _, job = bound_workspace(Path(temp)); path = write_run(folder, job)
            original = copy.deepcopy(job)
            self.assertEqual(storage.run_path(folder, job), path.resolve())
            self.assertEqual(job, original)
            self.assertTrue((folder / storage.RUN_MARKER).is_file())
            value = json.loads((path / 'workflow_manifest.json').read_text(encoding='utf-8'))
            value['status'] = 'success'; value['completed_steps'] = ['synthetic']
            atomic_json(path / 'workflow_manifest.json', value)
            self.assertEqual(storage.run_path(folder, job), path.resolve())

    def test_legacy_read_does_not_create_anything_and_config_cannot_escape_project(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, config, _, job = workspace(Path(temp)); before = set(Path(temp).rglob('*'))
            self.assertIsNone(storage.research_root(folder, job))
            self.assertEqual(canonical_path(storage.runs_root(folder, job)), folder / 'runs')
            self.assertEqual(canonical_path(storage.review_root(folder, job)), folder / 'review')
            self.assertIsNone(storage.run_path(folder, job))
            self.assertEqual(storage.config_path(folder, job), config.resolve())
            self.assertEqual(set(Path(temp).rglob('*')), before)
            external = Path(temp) / 'foreign.yaml'; external.write_text('foreign')
            with self.assertRaises(ValueError): storage.config_path(folder, {'config': str(external)})
            path = write_run(folder, job)
            self.assertEqual(storage.run_path(folder, job), path.resolve())
            write_run(folder, job, 'other')
            with self.assertRaisesRegex(ValueError, 'Mehrere'): storage.run_path(folder, job)

    def test_marker_config_job_and_root_changes_fail_without_fallback(self):
        for case in ('deleted_storage', 'null_storage', 'changed_config', 'foreign_config', 'foreign_job',
                     'marker', 'missing_root', 'replaced_root', 'root_path', 'missing_local_marker'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                folder, config, parent, job = bound_workspace(Path(temp)); root = storage.research_root(folder, job)
                if case == 'deleted_storage': del job['storage']
                if case == 'null_storage': job['storage'] = None
                if case == 'changed_config': config.write_text('changed', encoding='utf-8')
                if case == 'foreign_config':
                    other = config.with_name('other.yaml'); other.write_bytes(config.read_bytes()); job['config'] = str(other)
                if case == 'foreign_job': job['storage']['job_id'] = 'd' * 20
                if case == 'marker': atomic_json(root / storage.ROOT_MARKER, {})
                if case == 'missing_root': root.rename(parent / 'offline')
                if case == 'replaced_root':
                    old = parent / 'old'; root.rename(old); shutil.copytree(old, root)
                if case == 'root_path': job['storage']['research_root'] = str(parent)
                if case == 'missing_local_marker': (folder / storage.LOCAL_MARKER).unlink()
                with self.assertRaises((ValueError, OSError)): storage.research_root(folder, job)
                self.assertFalse((folder / 'runs').exists())

    def test_unknown_or_multiple_run_manifests_and_replaced_pinned_run_are_rejected(self):
        for case in ('config', 'run_id', 'output_dir', 'two', 'replaced', 'missing', 'pin'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                folder, _, _, job = bound_workspace(Path(temp)); path = write_run(folder, job)
                manifest = json.loads((path / 'workflow_manifest.json').read_text(encoding='utf-8'))
                if case == 'config': manifest['provenance']['config_sha256'] = '0' * 64
                if case == 'run_id': manifest['run_id'] = 'foreign'
                if case == 'output_dir': manifest['output_dir'] = str(Path(temp))
                if case in ('config', 'run_id', 'output_dir'): atomic_json(path / 'workflow_manifest.json', manifest)
                if case == 'two': write_run(folder, job, 'other-run')
                if case in ('replaced', 'missing', 'pin'):
                    storage.run_path(folder, job)
                    if case == 'missing': (path / 'workflow_manifest.json').unlink()
                    if case == 'pin': atomic_json(folder / storage.RUN_MARKER, {})
                    if case == 'replaced':
                        saved = path.parent.parent / 'old-run'; path.rename(saved); shutil.copytree(saved, path)
                with self.assertRaises((ValueError, OSError)): storage.run_path(folder, job)

    def test_missing_parent_is_not_created(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, config, _, _ = workspace(Path(temp)); target = Path(temp) / 'missing'
            with self.assertRaises(ValueError): storage.create_binding(folder, config, target)
            self.assertFalse(target.exists())
            self.assertFalse((folder / storage.LOCAL_MARKER).exists())

    def test_lock_contention_is_transient_for_read_and_create_then_recovers(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, config, parent, job = workspace(Path(temp))
            with exclusive_file_lock(folder / storage.LOCK):
                with self.assertRaisesRegex(BlockingIOError, 'gerade geprüft'):
                    storage.create_binding(folder, config, parent)
                self.assertFalse((folder / storage.LOCAL_MARKER).exists())
            job['storage'] = storage.create_binding(folder, config, parent)
            path = write_run(folder, job)
            with exclusive_file_lock(folder / storage.LOCK):
                with self.assertRaisesRegex(BlockingIOError, 'gerade geprüft'):
                    storage.run_path(folder, job)
                self.assertFalse((folder / storage.RUN_MARKER).exists())
            self.assertEqual(storage.run_path(folder, job), path.resolve())

    def test_lock_wrapper_does_not_translate_runtime_errors_inside_body(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError, 'body failure'):
                with storage._binding_lock(Path(temp) / 'lock'):
                    raise RuntimeError('body failure')

    def test_legacy_monitor_folder_without_config_can_read_runs_only(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'job'; folder.mkdir()
            path = folder / 'runs/synthetic-run'; path.mkdir(parents=True)
            atomic_json(path / 'workflow_manifest.json', {'status': 'running'})
            self.assertIsNone(storage.research_root(folder, {}))
            self.assertEqual(canonical_path(storage.run_path(folder, {})), path.resolve())
            with self.assertRaises(ValueError): storage.config_path(folder, {})
            with self.assertRaises(ValueError): storage.research_root(folder, {'storage': {}})
            with self.assertRaises(ValueError): storage.create_binding(folder, 'unused.yaml', Path(temp))
            for function in (storage.research_root, storage.run_path):
                with self.assertRaises(ValueError): function(Path(temp) / 'missing', {})

    def test_missing_external_runs_is_not_recreated_or_treated_as_an_empty_new_job(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, _, _, job = bound_workspace(Path(temp)); runs = storage.runs_root(folder, job)
            runs.rmdir()
            for function in (storage.runs_root, storage.run_path):
                with self.subTest(function=function.__name__), self.assertRaisesRegex(ValueError, 'Laufordner fehlt'):
                    function(folder, job)
            self.assertFalse(runs.exists())

    def test_resolved_review_or_runs_redirection_is_rejected(self):
        # Mock only resolution: Windows symlinks require privileges on some hosts.
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            folder, _, parent, job = bound_workspace(Path(temp)); root = storage.research_root(folder, job)
            original_resolve = Path.resolve
            for child, function in [('review', storage.review_root), ('runs', storage.runs_root)]:
                target = root / child
                def redirected(path, *args, **kwargs):
                    return parent.resolve() if path == target else original_resolve(path, *args, **kwargs)
                with patch.object(Path, 'resolve', redirected), self.assertRaisesRegex(ValueError, 'umgeleitet'):
                    function(folder, job)


if __name__ == '__main__': unittest.main()
