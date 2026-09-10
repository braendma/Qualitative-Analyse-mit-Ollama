import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runtime_support import PartCheckpoint,atomic_json
import relation_analysis_core as relation
import evidence_audit_core as audit


class PartialCheckpointTests(unittest.TestCase):
    def test_failed_partial_work_is_not_saved_and_integrity_is_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            params={'partial_checkpoint_dir':tmp,'model':'mock'}
            cache=PartCheckpoint('test',params)
            with self.assertRaises(RuntimeError):cache.run('one',{'input':'A'},lambda:(_ for _ in ()).throw(RuntimeError('interrupted')))
            self.assertFalse(list(Path(tmp).rglob('*.json')))
            with self.assertRaises(ValueError):cache.run('one',{},lambda:{'processing_status':'failed'})
            self.assertFalse(list(Path(tmp).rglob('*.json')))
            result=cache.run('one',{'input':'A'},lambda:{'values':[1]})
            result['values'].append(2)
            reused=PartCheckpoint('test',params).run('one',{'input':'A'},lambda:self.fail('Repeated compute'))
            self.assertEqual(reused,{'values':[1]})
            for cfg,inputs in [(params,{'input':'changed'}),({**params,'model':'other'},{'input':'A'})]:
                with self.assertRaises(ValueError):PartCheckpoint('test',cfg).run('one',inputs,lambda:self.fail('Mismatch ignored'))
            path=next(Path(tmp).rglob('*.json'));data=json.loads(path.read_text());data['result']['values']=[99];atomic_json(path,data)
            with self.assertRaises(ValueError):cache.run('one',{'input':'A'},lambda:self.fail('Corruption ignored'))

    def test_disabled_checkpoints_do_not_write_or_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache=PartCheckpoint('test',{'partial_checkpoint_dir':tmp,'partial_checkpoints':False})
            self.assertEqual(cache.run('one',{},lambda:1),1)
            self.assertEqual(cache.run('one',{},lambda:2),2)
            self.assertFalse(list(Path(tmp).iterdir()))

    def test_relation_batches_resume_after_interruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);params={'model':'mock','temperature':0,'max_tokens':1000,'batch_items':1,'partial_checkpoint_dir':str(root/'parts')}
            for name,data in [('clusters',{}),('summary',{}),('texts',{'S1':'first','S2':'second'})]:atomic_json(root/(name+'.json'),data)
            pairs=[{'pair_id':f'P{i}','pfad_a':'A','pfad_b':'B','gemeinsame_personen':['person'],
                    'segmente_a':[{'id':'S1','person':'person'}],'segmente_b':[{'id':'S2','person':'person'}]} for i in range(3)]
            calls=[];interrupt=[True]
            def fake(system,user,settings):
                pair=json.loads(user)['kandidaten'][0];calls.append(pair['pair_id'])
                if interrupt[0] and len(calls)==2:raise RuntimeError('interrupted')
                return json.dumps({'beziehungen':[{'pair_id':pair['pair_id'],'thema':'Test','beschreibung':'Beleg','segment_ids_a':['S1'],'segment_ids_b':['S2']}],'gesamteinordnung':'Test'})
            args=[str(root/(name+'.json')) for name in ('clusters','texts','summary')]+[params,{'relation_analysis':{'system':'test','user':'{data}'}},{}]
            with patch.object(relation,'build_units',return_value=[]),patch.object(relation,'build_candidate_pairs',return_value=(pairs,3)),patch.object(relation,'_llm',side_effect=fake):
                with self.assertRaises(RuntimeError):relation.build_relation_analysis(*args)
                interrupt[0]=False
                _,result=relation.build_relation_analysis(*args)
                self.assertEqual(calls,['P0','P1','P1','P2'])
                self.assertEqual([x['relation_id'] for x in result['beziehungen']],['REL0001','REL0002','REL0003'])

    def test_audit_batches_resume_and_keep_all_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);params={'model':'mock','temperature':0,'max_tokens':1000,'batch_items':1,'partial_checkpoint_dir':str(root/'parts')}
            registry={f'F{i}':{'source_id':'A','segment_ids':['P1#SEG0'],'thema':str(i),'analyse':'Test'} for i in range(3)}
            files={'swot':{},'meta':{'finding_registry':registry,'meta_swot':{'Stärken':{'einzelbefunde':[{'finding_id':fid,'thema':fid} for fid in registry]}}},
                   'contrast':{'negativfaelle':[{'person':'P1','abweichung':'Gegenbefund'}]},'ambiguity':{},'map':{'P1#SEG0':'Beleg'}}
            for name,data in files.items():atomic_json(root/(name+'.json'),data)
            calls=[];interrupt=[True]
            def fake(system,user,settings):
                item=json.loads(user)['audit_befunde'][0];calls.append(item['audit_id'])
                if interrupt[0] and len(calls)==2:raise RuntimeError('interrupted')
                return json.dumps({'zuordnungen':[{'audit_id':item['audit_id'],'gegenbeleg_ids':[],'einordnung':'Kein passender Gegenbeleg'}]})
            args=[str(root/(name+'.json')) for name in files]+[params,{'evidence_audit':{'system':'test','user':'{data}'}},{}]
            with patch.object(audit,'_llm',side_effect=fake):
                with self.assertRaises(RuntimeError):audit.build_evidence_audit(*args)
                interrupt[0]=False
                _,result=audit.build_evidence_audit(*args)
                self.assertEqual(calls.count(calls[0]),1)
                self.assertEqual(len(result['befunde']),3)
                self.assertEqual(len({f['audit_id'] for f in result['befunde']}),3)

if __name__=='__main__':unittest.main()
