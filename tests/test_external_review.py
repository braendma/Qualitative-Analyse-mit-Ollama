"""Synthetic review storage tests; no runner subprocess or model transport."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from job_storage import create_binding, research_root, ROOT_MARKER
from local_app import App
from runtime_support import atomic_json, file_hash, fingerprint
from test_review_workspace import fixture, decision
from test_job_storage import write_run


def external_fixture(directory):
    app,pid,jid,queue,cfg=fixture(directory)
    folder=app.project_dir(pid)/'jobs'/jid
    job=json.loads((folder/'job.json').read_text(encoding='utf-8'))
    parent=Path(directory)/'Forschung Ä mit Leerzeichen';parent.mkdir()
    job['storage']=create_binding(folder,cfg,parent)
    atomic_json(folder/'job.json',job)
    run=write_run(folder,job)
    atomic_json(run/'review_queue.json',queue)
    manifest=json.loads((run/'workflow_manifest.json').read_text(encoding='utf-8'))
    manifest.update(status='success',completed_steps=['review_queue'],current_module=None)
    atomic_json(run/'workflow_manifest.json',manifest)
    return app,pid,jid,queue,cfg,research_root(folder,job)


def pointers(app,pid):
    folder=app.project_dir(pid)
    return {name:(folder/name).read_bytes() for name in ('project.json','settings.json','uploads.json')}


class ExternalReviewTests(unittest.TestCase):
    def test_drafts_versions_and_restart_use_bound_research_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,pid,jid,queue,cfg,root=external_fixture(tmp)
            app.save_review(pid,jid,decision(note='',reviewer=''),0)
            reopened=App(tmp)
            self.assertEqual(reopened.review(pid,jid)['draft']['revision'],1)
            with self.assertRaisesRegex(ValueError,'anderen Fenster'):
                reopened.save_review(pid,jid,decision(),0)
            reopened.save_review(pid,jid,decision(),1)
            self.assertEqual(len(list((root/'review/versions').glob('*.json'))),2)
            self.assertEqual(json.loads((root/'review/current.json').read_text(encoding='utf-8'))['revision'],2)
            self.assertFalse((app.project_dir(pid)/'jobs'/jid/'review').exists())
            self.assertEqual(reopened.review(pid,jid)['queue'],queue)

    def test_followup_exports_exact_validated_inputs_before_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,pid,jid,queue,cfg,root=external_fixture(tmp)
            old_settings=json.loads((cfg.parent/'settings.json').read_text(encoding='utf-8'))
            old_settings['output_dir']='historical target must not return'
            atomic_json(cfg.parent/'settings.json',old_settings)
            current=app.project(pid)['settings'];current['output_dir']=str(Path(tmp)/'New target')
            atomic_json(app.project_dir(pid)/'settings.json',current)
            original=cfg.read_bytes()
            app.save_review(pid,jid,decision(),0)
            prepared=app.prepare_followup(pid,jid,1)
            revision=app.project_dir(pid)/'revisions'/prepared['project']['revision']
            export=root/'review/followups'/revision.name
            receipt=json.loads((export/'followup_manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(set(p.name for p in export.iterdir()),
                {'segments.csv','codebook.csv','review_snapshot.json','followup_manifest.json'})
            for name in ('segments.csv','codebook.csv','review_snapshot.json'):
                self.assertEqual((revision/name).read_bytes(),(export/name).read_bytes())
                self.assertEqual(receipt['files'][name],{'sha256':file_hash(export/name),'bytes':(export/name).stat().st_size})
            normalized=yaml.safe_load((revision/'config.yaml').read_text(encoding='utf-8'))
            self.assertEqual(receipt['columns'],normalized['columns'])
            self.assertEqual(receipt['person_identity'],normalized['person_identity'])
            self.assertEqual(receipt['review_fingerprint'],fingerprint(app.review(pid,jid)['draft']))
            self.assertEqual(receipt['queue_source_fingerprint'],queue['source_fingerprint'])
            self.assertEqual(prepared['project']['settings']['output_dir'],current['output_dir'])
            self.assertEqual(cfg.read_bytes(),original)

    def test_missing_current_target_does_not_restore_old_source_setting(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,pid,jid,_,cfg,_=external_fixture(tmp)
            old=json.loads((cfg.parent/'settings.json').read_text(encoding='utf-8'))
            old['output_dir']='old target';atomic_json(cfg.parent/'settings.json',old)
            current=app.project(pid)['settings'];current.pop('output_dir',None)
            atomic_json(app.project_dir(pid)/'settings.json',current)
            app.save_review(pid,jid,decision(),0)
            result=app.prepare_followup(pid,jid,1)
            self.assertNotIn('output_dir',result['project']['settings'])

    def test_external_write_failure_leaves_all_project_pointers_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,pid,jid,_,cfg,root=external_fixture(tmp)
            app.save_review(pid,jid,decision(),0);before=pointers(app,pid)
            real_open=Path.open
            def fail_external(path,*args,**kwargs):
                if args and args[0]=='xb' and path.is_relative_to(root):
                    raise OSError('Synthetic disconnected drive')
                return real_open(path,*args,**kwargs)
            with patch.object(Path,'open',fail_external):
                with self.assertRaisesRegex(OSError,'disconnected'):
                    app.prepare_followup(pid,jid,1)
            self.assertEqual(pointers(app,pid),before)
            self.assertFalse(list((root/'review/followups').glob('*/followup_manifest.json')))

    def test_external_loss_after_export_still_does_not_publish_pointers(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,pid,jid,_,_,root=external_fixture(tmp)
            app.save_review(pid,jid,decision(),0);before=pointers(app,pid)
            export=app._export_followup
            def disconnect(*args):
                export(*args)
                (root/ROOT_MARKER).rename(root/(ROOT_MARKER+'.offline'))
            with patch.object(app,'_export_followup',side_effect=disconnect):
                with self.assertRaises(ValueError):app.prepare_followup(pid,jid,1)
            self.assertEqual(pointers(app,pid),before)
            self.assertFalse((app.project_dir(pid)/'jobs'/jid/'review').exists())

    def test_config_tampering_rejects_review_followup_and_refinement(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,pid,jid,_,cfg,root=external_fixture(tmp)
            app.save_review(pid,jid,decision(),0);before=pointers(app,pid)
            cfg.write_text(cfg.read_text(encoding='utf-8')+'\n# changed\n',encoding='utf-8')
            with patch.object(app,'start') as start:
                for operation in (lambda:app.review(pid,jid),lambda:app.prepare_followup(pid,jid,1),
                                  lambda:app.start_refinement(pid,jid,1)):
                    with self.assertRaises(ValueError):operation()
                start.assert_not_called()
            self.assertEqual(pointers(app,pid),before)
            self.assertFalse((root/'review/followups').exists())

    def test_review_descendant_symlink_cannot_escape_bound_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,pid,jid,_,_,root=external_fixture(tmp)
            (root/'review').mkdir();outside=Path(tmp)/'unrelated';outside.mkdir()
            try:(root/'review/versions').symlink_to(outside,target_is_directory=True)
            except OSError:self.skipTest('Creating symlinks is unavailable on this platform.')
            with self.assertRaises(ValueError):app.save_review(pid,jid,decision(),0)
            self.assertFalse(list(outside.iterdir()))
            self.assertFalse((root/'review/current.json').exists())

    def test_resolved_descendant_escape_rejected_without_symlink_privilege(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,pid,jid,_,_,root=external_fixture(tmp)
            outside=Path(tmp)/'unrelated';outside.mkdir()
            redirected=root/'review/versions'
            real_resolve=Path.resolve
            def resolve(path,*args,**kwargs):
                if path.is_relative_to(redirected):
                    return real_resolve(outside/path.relative_to(redirected),*args,**kwargs)
                return real_resolve(path,*args,**kwargs)
            # Simulate the path resolver's result for a junction without
            # requiring platform-specific symlink creation permissions.
            with patch.object(Path,'resolve',resolve):
                with self.assertRaisesRegex(ValueError,'Dateipfad'):
                    app.save_review(pid,jid,decision(),0)
            self.assertFalse(list(outside.iterdir()))
            self.assertFalse((root/'review/current.json').exists())

    def test_refinement_uses_bound_source_without_replacing_current_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,pid,jid,queue,_,_=external_fixture(tmp)
            app.save_review(pid,jid,decision(),0)
            current=app.project(pid)['settings'];current['output_dir']='new current target'
            atomic_json(app.project_dir(pid)/'settings.json',current)
            before=pointers(app,pid)
            with patch.object(app,'start',return_value={'synthetic':True}) as start:
                self.assertEqual(app.start_refinement(pid,jid,1),{'synthetic':True})
            config=start.call_args.kwargs['prepared_config']
            result=yaml.safe_load(config.read_text(encoding='utf-8'))
            self.assertEqual(json.loads(Path(result['refinement']['queue']).read_text(encoding='utf-8')),queue)
            self.assertEqual(result['review_provenance']['parent_job'],jid)
            self.assertEqual(pointers(app,pid),before)

    def test_legacy_followup_keeps_original_local_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,pid,jid,_,_=fixture(tmp)
            app.save_review(pid,jid,decision(),0)
            result=app.prepare_followup(pid,jid,1)
            self.assertTrue((app.project_dir(pid)/'jobs'/jid/'review/current.json').is_file())
            self.assertFalse(list(Path(tmp).rglob('followup_manifest.json')))
            self.assertTrue((app.project_dir(pid)/'revisions'/result['project']['revision']/'review_snapshot.json').is_file())


if __name__=='__main__':unittest.main()
