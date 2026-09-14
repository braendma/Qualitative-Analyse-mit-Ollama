"""Frozen synthetic fifteen-module YAML and existing projects remain readable."""
import contextlib
import copy
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from test_local_app import App, ROOT
from local_app import RUNNER, csv_info
from person_identity import apply, preview
from runtime_support import atomic_json

FIXTURE = ROOT / 'tests' / 'fixtures' / 'legacy_v5'
DIAGNOSTICS = {'coverage', 'information_loss', 'codebook_diagnostics', 'stability', 'sensitivity'}


def legacy(directory):
    for source in FIXTURE.iterdir():
        shutil.copyfile(source, directory/source.name)
    return directory/'config_15_modules.yaml'


def files(directory):
    return {str(p.relative_to(directory)): p.read_bytes() for p in directory.rglob('*') if p.is_file()}


class LegacyCompatibilityTests(unittest.TestCase):
    def test_frozen_yaml_normalization_never_adds_diagnostics_or_mutates_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp); path = legacy(directory)
            before = files(directory)
            config = yaml.safe_load(path.read_text(encoding='utf-8'))
            original = copy.deepcopy(config)
            self.assertNotIn('diagnostics', config)
            self.assertEqual(len(config['pipeline']['modules']), 15)
            self.assertTrue(all(not ({'cost_profile', 'starts_child_runs'} & set(m))
                                for m in config['pipeline']['modules']))
            modules = RUNNER.normalize_modules(config)
            self.assertEqual(len(modules), 15)
            self.assertFalse(DIAGNOSTICS & {m['id'] for m in modules})
            self.assertTrue(all(not m['starts_child_runs'] for m in modules))
            self.assertEqual([m['id'] for m in RUNNER.topological_order(modules)], ['clusterer', 'summarizer'])
            self.assertEqual(config, original)
            self.assertEqual(files(directory), before)

    def test_legacy_cli_validate_only_keeps_files_and_reports_only_selected_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp); path = legacy(directory); before = files(directory)
            output = io.StringIO()
            with patch.object(RUNNER, 'run_step', side_effect=AssertionError('No model execution')) as step, \
                    contextlib.redirect_stdout(output):
                RUNNER.main(['--config', str(path), '--output-dir', str(directory/'new-runs'), '--validate-only'])
            step.assert_not_called()
            result = json.loads(output.getvalue())
            self.assertEqual(result['status'], 'valid')
            self.assertEqual(result['modules'], 2)
            self.assertEqual(result['model_calls'], 0)
            self.assertNotIn('stability_plan', result)
            self.assertNotIn('sensitivity_plan', result)
            self.assertEqual(files(directory), before)
            self.assertFalse((directory/'new-runs').exists())

    def existing_project(self, directory):
        app = App(directory)
        pid, jid, rid = 'a'*20, 'b'*20, 'c'*20
        project = app.projects_dir/pid; revision = project/'revisions'/rid
        inputs = project/'inputs'; run = project/'jobs'/jid/'runs'/'old-run'
        for folder in (revision, inputs, run):
            folder.mkdir(parents=True)
        config = yaml.safe_load((FIXTURE/'config_15_modules.yaml').read_text(encoding='utf-8'))
        raw = (FIXTURE/'segments.csv').read_bytes(); book = (FIXTURE/'codebook.csv').read_bytes()
        info = preview(raw, config['columns'])
        assignment = {'confirmed': True, 'fingerprint': info['fingerprint'],
            'mapping': {'Interview_A_Teil1': 'Person_01', 'Interview_A_Teil2': 'Person_01', 'Interview_B': 'Person_02'}}
        settings = {'columns': copy.deepcopy(config['columns']), 'person_identity': assignment,
            'book_columns': {'code': 'Code', 'definition': 'Definition', 'ankerbeispiel': 'Ankerbeispiel'},
            'modules': ['summarizer'], 'model': 'mock', 'label_mode': 'multi_label', 'context': {}}
        normalized, columns, receipt = apply(raw, config['columns'], assignment)
        (inputs/('1'*20+'.csv')).write_bytes(raw); (inputs/('2'*20+'.csv')).write_bytes(book)
        (revision/'segments.csv').write_bytes(normalized); (revision/'codebook.csv').write_bytes(book)
        config.update(columns=columns, person_identity=receipt)
        config['paths'].update(input_csv=str(revision/'segments.csv'), category_system_csv=str(revision/'codebook.csv'))
        (revision/'config.yaml').write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding='utf-8')
        atomic_json(project/'project.json', {'id': pid, 'name': 'Altes künstliches Projekt', 'created': 1, 'revision': rid, 'demo': False})
        atomic_json(project/'settings.json', settings)
        atomic_json(project/'uploads.json', {
            'segments': {'id': '1'*20, 'name': 'segments.csv', **csv_info(raw)},
            'codebook': {'id': '2'*20, 'name': 'codebook.csv', **csv_info(book)}})
        atomic_json(project/'jobs'/jid/'job.json', {'id': jid, 'created': 2, 'status': 'success', 'config': str(revision/'config.yaml')})
        atomic_json(run/'workflow_manifest.json', {'status': 'success', 'completed_steps': ['clusterer', 'summarizer'],
            'current_module': None, 'fingerprint': 'historical-fingerprint'})
        shutil.copyfile(FIXTURE/'gesamtbericht.html', run/'gesamtbericht.html')
        (run/'gesamtbericht.md').write_text('# Historischer Bericht\n\nZwei künstliche Personen.\n', encoding='utf-8')
        return app, pid, jid, revision, run, settings

    def test_existing_project_reads_selection_mapping_prompts_and_reports_without_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, pid, jid, revision, run, settings = self.existing_project(Path(tmp))
            root = app.project_dir(pid); before = files(root)
            # A fresh app with today's template opens an already existing directory.
            app = App(tmp)
            loaded = app.project(pid)
            self.assertEqual(loaded['settings'], settings)
            self.assertFalse(DIAGNOSTICS & set(loaded['settings']['modules']))
            self.assertNotIn('stability', loaded['settings'])
            self.assertNotIn('sensitivity', loaded['settings'])
            self.assertEqual(loaded['settings']['person_identity']['mapping']['Interview_A_Teil2'], 'Person_01')
            self.assertEqual(app.person_preview(pid, settings['columns'])['document_count'], 3)
            checked = app.validate_config(revision/'config.yaml')
            self.assertEqual(checked['persons'], 2)
            for result in (app.prompt_templates(pid), app.prompt_templates(pid, jid)):
                self.assertEqual(len(result['modules']), 15)
                self.assertIn('Historische Clustervorlage', str(result))
            job = app.jobs(pid)[0]
            self.assertEqual(job['status'], 'success')
            self.assertEqual(job['completed'], ['clusterer', 'summarizer'])
            for name in ('gesamtbericht.html', 'gesamtbericht.md'):
                self.assertIn(name, job['files'])
                self.assertEqual(app.artifact(pid, jid, name).read_bytes(), (run/name).read_bytes())
            self.assertEqual(files(root), before)

    def test_explicit_resave_creates_new_revision_and_keeps_legacy_reports_and_person_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, pid, jid, old_revision, run, settings = self.existing_project(Path(tmp))
            original_revision, original_run = files(old_revision), files(run)
            with patch.object(app, 'authorize_llm', side_effect=AssertionError('Saving must not call model')):
                checked = app.save(pid, settings)
            new_revision = app.project_dir(pid)/'revisions'/app.project(pid)['revision']
            self.assertNotEqual(new_revision, old_revision)
            self.assertEqual(files(old_revision), original_revision)
            self.assertEqual(files(run), original_run)
            self.assertEqual(checked['persons'], 2)
            current = yaml.safe_load((new_revision/'config.yaml').read_text(encoding='utf-8'))
            self.assertEqual(len(current['pipeline']['modules']), 20)
            self.assertTrue(all(not m['enabled'] for m in current['pipeline']['modules'] if m['id'] in DIAGNOSTICS))
            self.assertEqual({m['id'] for m in current['pipeline']['modules'] if m['enabled']}, {'clusterer', 'summarizer'})
            self.assertEqual(current['person_identity']['mapping'], settings['person_identity']['mapping'])
            self.assertIn('gesamtbericht.html', app.jobs(pid)[0]['files'])
            self.assertEqual(len(app.prompt_templates(pid, jid)['modules']), 15)

    def test_readable_legacy_report_does_not_bypass_changed_resume_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, pid, jid, revision, run, settings = self.existing_project(Path(tmp))
            before = files(app.project_dir(pid))
            # A fixed changed source identity avoids scanning concurrently edited source
            # or dispatching git/subprocesses; the existing runner guard itself is real.
            with patch.object(RUNNER, 'execution_provenance', return_value={'code_sha256': 'new-code-identity'}), \
                    patch.object(RUNNER, 'run_step', side_effect=AssertionError('Rejected resume must not execute')) as step:
                with self.assertRaisesRegex(ValueError, 'Wiederaufnahme abgelehnt'):
                    RUNNER.main(['--config', str(revision/'config.yaml'), '--resume', str(run)])
            step.assert_not_called()
            self.assertEqual(files(app.project_dir(pid)), before)
            self.assertTrue(app.artifact(pid, jid, 'gesamtbericht.html').is_file())


if __name__ == '__main__':
    unittest.main()
