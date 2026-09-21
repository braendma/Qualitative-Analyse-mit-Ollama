"""Synthetic bundle identity contracts; no executable build or model calls."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import package_identity as package
from runtime_support import Checkpoint, PartCheckpoint, checkpoint_identity, fingerprint


def manifest_write(root, manifest):
    value = copy.deepcopy(manifest)
    value.pop('build_input_id', None)
    value['build_input_id'] = hashlib.sha256(package._canonical(value)).hexdigest()
    (root / 'packaging/build-manifest.json').write_text(json.dumps(value), encoding='utf-8')
    return value


def bundle_fixture(directory):
    root = Path(directory) / 'bundle'; root.mkdir()
    names = ['VERSION', 'LICENSE', 'README.md', 'requirements.txt', 'src/package_identity.py',
             'src/runtime_entry.py', 'src/runtime_support.py', 'src/00_WORKFLOW_RUNNER.py']
    for name in names + ['packaging/' + name for name in package.BUILD_FILES]:
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('0.0.0-test' if name == 'VERSION' else 'synthetic public build input\n', encoding='utf-8')
    (root / 'packaging/resources.json').write_text(json.dumps({'schema': 1, 'resources': names}), encoding='utf-8')
    executable = Path(directory) / 'synthetic.exe'; executable.write_bytes(b'synthetic executable identity')
    resources = {name: package._digest(root / name)
                 for name in names + ['packaging/' + name for name in package.BUILD_FILES]}
    manifest = {'schema': 1, 'kind': 'build-input-manifest', 'version': '0.0.0-test',
                'source_commit': 'a' * 40, 'python': '.'.join(map(str, sys.version_info[:3])),
                'platform': 'windows-x64', 'build_type': 'pyinstaller-onedir-console',
                'dependencies': {name: '1.0' for name in package.RUNTIME_DEPENDENCIES + package.BUILD_DEPENDENCIES},
                'resources': resources}
    return root, executable, manifest_write(root, manifest)


class PackageIdentityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root, self.executable, self.manifest = bundle_fixture(temporary.name)
        versions = patch('package_identity.importlib.metadata.version', return_value='1.0')
        versions.start(); self.addCleanup(versions.stop)

    def identity(self):
        return package.validate_frozen_package(self.root, self.executable)

    def test_identity_binds_actual_executable_build_inputs_and_resources_without_paths(self):
        first = self.identity()
        self.assertEqual(first['executable_sha256'], package._digest(self.executable)['sha256'])
        self.assertEqual(first['build_input_id'], self.manifest['build_input_id'])
        self.assertEqual(first['bootstrap_sha256'], self.manifest['resources']['packaging/bootstrap.py']['sha256'])
        self.assertNotIn(str(self.root), json.dumps(first))
        self.executable.write_bytes(b'different executable')
        self.assertNotEqual(first, self.identity())

    def test_source_identity_has_no_added_package_field(self):
        with patch.object(sys, 'frozen', False, create=True):
            self.assertIsNone(package.current_package_identity())
            self.assertEqual(set(checkpoint_identity([], [], {}, {}, {})),
                             {'segments', 'codebook', 'prompts', 'context', 'params', 'code'})

    def test_private_snapshot_has_no_invented_commit_and_still_binds_files(self):
        changed=copy.deepcopy(self.manifest)
        changed.update(kind='private-build-input-manifest',version='8.0.0-private1',source_commit=None)
        (self.root/'VERSION').write_text(changed['version'],encoding='utf-8')
        changed['resources']['VERSION']=package._digest(self.root/'VERSION')
        manifest_write(self.root,changed)
        self.assertIsNone(self.identity()['source_commit'])
        for altered in ({'source_commit':'a'*40},{'kind':'build-input-manifest'},{'version':'8.0.0'}):
            manifest_write(self.root,{**changed,**altered})
            with self.assertRaises(ValueError):self.identity()

    def test_frozen_missing_manifest_fails_instead_of_using_source_fallback(self):
        (self.root / 'packaging/build-manifest.json').unlink()
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, '_MEIPASS', str(self.root), create=True), \
                patch.object(sys, 'executable', str(self.executable)), self.assertRaisesRegex(ValueError, 'Programmpaket'):
            package.current_package_identity()

    def test_changed_source_bootstrap_or_public_resource_fails(self):
        for relative in ('src/runtime_entry.py', 'packaging/bootstrap.py', 'README.md'):
            path = self.root / relative; original = path.read_bytes()
            with self.subTest(relative=relative):
                path.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'Programmpaket'): self.identity()
                path.write_bytes(original)
        self.identity()

    def test_manifest_hash_duplicate_fields_and_dependency_mismatch_fail(self):
        path = self.root / 'packaging/build-manifest.json'; original = path.read_text(encoding='utf-8')
        changed = copy.deepcopy(self.manifest); changed['source_commit'] = 'b' * 40
        path.write_text(json.dumps(changed), encoding='utf-8')
        with self.assertRaises(ValueError): self.identity()
        path.write_text(original[:-1] + ', "schema": 1}', encoding='utf-8')
        with self.assertRaises(ValueError): self.identity()
        changed = copy.deepcopy(self.manifest); changed['dependencies']['numpy'] = 'different'
        manifest_write(self.root, changed)
        with self.assertRaises(ValueError): self.identity()

    def test_escaped_or_untracked_sources_fail(self):
        changed = copy.deepcopy(self.manifest)
        changed['resources']['../synthetic.exe'] = package._digest(self.executable)
        manifest_write(self.root, changed)
        with self.assertRaises(ValueError): self.identity()
        manifest_write(self.root, self.manifest)
        (self.root / 'src/extra_untracked.py').write_text('pass', encoding='utf-8')
        with self.assertRaises(ValueError): self.identity()

    def test_changed_package_prevents_both_checkpoint_kinds_from_reusing_results(self):
        params = {'partial_checkpoint_dir': str(self.root / 'checkpoints')}
        with patch('package_identity.current_package_identity', side_effect=self.identity):
            old_identity = checkpoint_identity([], [], {}, {}, {})
            checkpoint = Checkpoint(self.root / 'checkpoint.json', old_identity)
            checkpoint.save('s1', {'processing_status': 'completed'})
            part = PartCheckpoint('synthetic', params)
            self.assertEqual(part.run('key', {}, lambda: {'answer': 1}), {'answer': 1})
            self.assertEqual(PartCheckpoint('synthetic', params).run('key', {}, lambda: self.fail('cache not reused')), {'answer': 1})
            self.executable.write_bytes(b'new executable identity')
            with self.assertRaises(ValueError): Checkpoint(self.root / 'checkpoint.json', checkpoint_identity([], [], {}, {}, {}))
            with self.assertRaises(ValueError): PartCheckpoint('synthetic', params).run('key', {}, lambda: self.fail('mismatch computed'))

    def test_source_partial_identity_keeps_existing_shape(self):
        import os
        import runtime_support
        params = {'partial_checkpoint_dir': str(self.root / 'parts')}
        root = Path(runtime_support.__file__).parent
        from runtime_support import file_hash
        expected = fingerprint({'module': 'synthetic', 'params': params,
                                'workflow': os.environ.get('WORKFLOW_FINGERPRINT'),
                                'code': {p.name: file_hash(p) for p in sorted(root.glob('*.py'))}})
        with patch.object(sys, 'frozen', False, create=True):
            self.assertEqual(PartCheckpoint('synthetic', params).identity, expected)

    def test_frozen_runner_uses_manifest_commit_and_never_parent_git(self):
        from local_app import RUNNER
        config_path = self.root / 'config.yaml'; config_path.write_text('{}', encoding='utf-8')
        csv_path = self.root / 'segments.csv'; csv_path.write_text('synthetic', encoding='utf-8')
        identity = self.identity()
        with patch('package_identity.current_package_identity', return_value=identity), \
                patch.object(sys, '_MEIPASS', str(self.root), create=True), \
                patch.object(RUNNER.subprocess, 'check_output', side_effect=AssertionError('No Git in frozen mode')):
            result = RUNNER.execution_provenance(config_path, csv_path, {}, self.root / 'src')
            with self.assertRaisesRegex(ValueError, 'eigenen geprüften'):
                RUNNER.execution_provenance(config_path, csv_path, {}, self.root.parent)
        self.assertEqual(result['package'], identity)
        self.assertEqual(result['commit'], self.manifest['source_commit'])

    def test_missing_package_is_rejected_even_if_partial_checkpoints_disabled(self):
        with patch('package_identity.current_package_identity', side_effect=ValueError(package.ERROR)), \
                self.assertRaisesRegex(ValueError, 'Programmpaket'):
            PartCheckpoint('synthetic', {'partial_checkpoints': False})


if __name__ == '__main__':
    unittest.main()
