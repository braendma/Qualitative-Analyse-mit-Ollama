"""Real synthesis DAG fixtures with synthetic model text and strict replay tests."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from overall_synthesis_core import build_overall_synthesis, project_synthesis_source, normalize_overall_synthesis
from hierarchical_synthesis import reduce_sources
from runtime_support import fingerprint
from synthesis_provenance import validate_synthesis_provenance


def synthesis_fixture(*, reduced=False, multilevel=False):
    """Return (actual core payload, original source_payloads_by_label)."""
    size = 40 if multilevel else 4
    sources = {'Analytische Quelle': {'created_at': 'synthetic-source',
        'findings': [{'thema': 'Thema ' + str(i), 'verdichtung': 'Vollständiger synthetischer Befund. ' * (40 if multilevel else 3),
            'segment_ids': ['S' + str(i)]} for i in range(size)],
        'empty_list': [], 'empty_dict': {}, 'scalar': False},
        'Leere Quelle': {'created_at': 'empty-source'}}
    def response(system,user,params):
        refs=json.loads(user)['verfuegbare_analytische_quellen']
        return json.dumps({'kernergebnisse':[{'thema':'Gemeinsames Thema','verdichtung':'Eine synthetische Gesamtaussage.', 'quellen':refs[:1]}],
            'uebergreifende_muster':[], 'spannungen_und_relativierungen':[], 'methodische_einordnung':['Keine Repräsentativität.'],
            'gesamtsynthese':'Wird vom Normalizer neu zusammengesetzt.'})
    with tempfile.TemporaryDirectory() as temp,patch('overall_synthesis_core.llm_overall_synthesis',side_effect=response),\
         patch('coding_validation_common.default_llm',return_value=json.dumps({'summary':'Analytische Verdichtung mit Gegenposition. '*4})):
        paths={}
        for index,(label,value) in enumerate(sources.items()):
            path=Path(temp)/(str(index)+'.json');path.write_text(json.dumps(value),encoding='utf-8');paths[label]=path
        _,payload=build_overall_synthesis(paths,{'model':'synthetic','num_ctx':4000 if multilevel else 32768,
            'max_tokens':256,'partial_checkpoints':False,'hierarchical_synthesis':{'force':reduced,'batch_items':2,
                'summary_chars':300,'max_calls':128}}, {'overall_synthesis':{'system':'Synthetic','user':'{data}'}},{})
    return payload,sources


def _leaf_id(source,path,content):
    return 'L'+fingerprint([source,path,content])[:20]


class SynthesisProvenanceTests(unittest.TestCase):
    def test_actual_core_unreduced_and_multilevel_dag(self):
        for reduced,multilevel in ((False,False),(True,False),(True,True)):
            payload,sources=synthesis_fixture(reduced=reduced,multilevel=multilevel)
            result=validate_synthesis_provenance(payload,sources)
            self.assertEqual(result['reduction_used'],reduced)
            self.assertEqual(result['source_labels'],sorted(sources))
            self.assertNotIn('Vollständiger synthetischer Befund',str(result))
            if multilevel:self.assertGreaterEqual(payload['hierarchical_reduction']['levels'],2)
            if reduced:
                expected=set(payload['hierarchical_reduction']['leaves'])
                actual={lid for value in result['references'].values() for lid in value['leaf_ids']}
                self.assertEqual(actual,expected)
                # Not every final source needs to be cited by an individual finding.
                self.assertGreater(len(result['references']),1)

    def test_actual_reduce_sources_scalar_root_list_and_empty_containers(self):
        sources={'List': [[],{},None,False,0,'text'], 'Scalar': 'scalar', 'Dict': {}}
        original={label:project_synthesis_source(value) for label,value in sources.items()}
        final,ledger=reduce_sources(original,lambda value:('Synthetic',json.dumps(value)),
            {'num_ctx':32768,'max_tokens':256,'partial_checkpoints':False,'hierarchical_synthesis':{'force':True,'batch_items':2}},
            lambda *args:json.dumps({'summary':'Short.'}))
        refs=final['verfuegbare_analytische_quellen']
        payload={'source_labels':list(sources),'source_created_at':{label:None for label in sources},'hierarchical_reduction':ledger,
            **normalize_overall_synthesis({'kernergebnisse':[{'thema':'Theme','verdichtung':'Material statement.','quellen':refs}]},refs)}
        self.assertTrue(validate_synthesis_provenance(payload,sources)['reduction_used'])

    def test_source_label_timestamp_and_actual_changed_content_are_rejected(self):
        for change in ('labels','date','content','failed'):
            payload,sources=synthesis_fixture(reduced=True)
            if change=='labels':payload['source_labels'].append('foreign')
            if change=='date':sources['Analytische Quelle']['created_at']='changed'
            if change=='content':sources['Analytische Quelle']['findings'][0]['verdichtung']='changed'
            if change=='failed':sources['Analytische Quelle']['processing_status']='failed'
            with self.subTest(change=change),self.assertRaises(ValueError):validate_synthesis_provenance(payload,sources)

    def test_leaf_hash_path_content_and_foreign_source_checks(self):
        for change in ('hash','content','path','bool','float','foreign'):
            payload,sources=synthesis_fixture(reduced=True);leaves=payload['hierarchical_reduction']['leaves']
            lid=next(lid for lid,row in leaves.items() if len(row['path'])==2);leaf=leaves[lid]
            if change=='hash':leaves['L'+'0'*20]=leaves.pop(lid)
            if change=='content':leaf['content']['verdichtung']='changed'
            if change=='path':leaf['path']=['missing']
            if change=='bool':leaf['path'][-1]=False
            if change=='float':leaf['path'][-1]=0.0
            if change=='foreign':leaf['source']='foreign'
            with self.subTest(change=change),self.assertRaises(ValueError):validate_synthesis_provenance(payload,sources)

    def test_leaf_coverage_missing_overlapping_and_illegal_top_level_are_rejected(self):
        for change in ('missing','overlap','top'):
            payload,sources=synthesis_fixture(reduced=True);leaves=payload['hierarchical_reduction']['leaves']
            if change=='missing':del leaves[next(iter(leaves))]
            else:
                label='Analytische Quelle';path=['findings'] if change=='overlap' else []
                content=project_synthesis_source(sources[label]);content=content['findings'] if path else content
                leaves[_leaf_id(label,path,content)]={'source':label,'path':path,'content':content}
            with self.subTest(change=change),self.assertRaises(ValueError):validate_synthesis_provenance(payload,sources)

    def test_valid_rehashed_overlapping_leaf_still_fails_structural_coverage(self):
        payload,sources=synthesis_fixture(reduced=True);leaves=payload['hierarchical_reduction']['leaves']
        lid=next(lid for lid,row in leaves.items() if len(row['path'])==2)
        leaf=leaves[lid];path=leaf['path']+['thema'];content=leaf['content']['thema']
        leaves[_leaf_id(leaf['source'],path,content)]={'source':leaf['source'],'path':path,'content':content}
        with self.assertRaisesRegex(ValueError,'überlappen'):validate_synthesis_provenance(payload,sources)

    def test_node_hash_levels_edges_union_and_final_refs_are_rejected(self):
        for change in ('hash','level','boollevel','cycle','missing','duplicate','union','final','used'):
            payload,sources=synthesis_fixture(reduced=True);ledger=payload['hierarchical_reduction'];nodes=ledger['nodes']
            nid=next(iter(nodes));node=nodes[nid]
            if change=='hash':node['text']+='changed'
            if change=='level':node['level']+=1
            if change=='boollevel':node['level']=True
            if change=='cycle':node['input_ids']=[nid]
            if change=='missing':node['input_ids']=['Nmissing']
            if change=='duplicate':node['input_ids'].append(node['input_ids'][0])
            if change=='union':node['source_labels']=['Leere Quelle']
            if change=='final':ledger['final_node_ids'].pop()
            if change=='used':ledger['used']=1
            with self.subTest(change=change),self.assertRaises(ValueError):validate_synthesis_provenance(payload,sources)

    def test_rehashed_extra_node_is_not_a_valid_disconnected_graph(self):
        payload,sources=synthesis_fixture(reduced=True);ledger=payload['hierarchical_reduction']
        node=copy.deepcopy(next(iter(ledger['nodes'].values())));node['text']='Additional unconnected summary.'
        nid='N'+fingerprint([node['level']-1,{'text':node['text'],'input_ids':node['input_ids']}])[:20]
        ledger['nodes'][nid]=node;ledger['model_calls']=len(ledger['nodes'])
        with self.assertRaises(ValueError):validate_synthesis_provenance(payload,sources)
        # Even appending the orphan to final roots cannot legitimize duplicate parents.
        ledger['final_node_ids'].append(nid)
        with self.assertRaisesRegex(ValueError,'Elternschaft'):validate_synthesis_provenance(payload,sources)

    def test_findings_reference_only_actual_final_sources(self):
        for reduced in (False,True):
            payload,sources=synthesis_fixture(reduced=reduced)
            payload['kernergebnisse'][0]['quellen']=['foreign']
            with self.assertRaises(ValueError):validate_synthesis_provenance(payload,sources)
        payload,sources=synthesis_fixture(reduced=True,multilevel=True)
        payload['kernergebnisse'][0]['quellen']=[next(iter(payload['hierarchical_reduction']['leaves']))]
        with self.assertRaises(ValueError):validate_synthesis_provenance(payload,sources)

    def test_normalized_empty_description_is_not_falsely_treated_as_invalid_provenance(self):
        payload,sources=synthesis_fixture(reduced=True)
        payload['kernergebnisse'][0]['verdichtung']='';payload['gesamtsynthese']=''
        self.assertTrue(validate_synthesis_provenance(payload,sources)['reduction_used'])

    def test_unreduced_old_ledger_does_not_need_invented_hashes(self):
        payload,sources=synthesis_fixture()
        del payload['source_projection_fingerprints']
        self.assertEqual(set(payload['hierarchical_reduction']),{'used','model_calls','levels','nodes','leaves'})
        validate_synthesis_provenance(payload,sources)
        payload['hierarchical_reduction']['model_calls']=False
        with self.assertRaises(ValueError):validate_synthesis_provenance(payload,sources)

    def test_new_unreduced_core_hash_detects_changed_source_with_unchanged_dates(self):
        payload,sources=synthesis_fixture()
        expected={label:fingerprint(project_synthesis_source(value)) for label,value in sources.items()}
        self.assertEqual(payload['source_projection_fingerprints'],expected)
        self.assertNotIn('Vollständiger synthetischer Befund',str(payload['source_projection_fingerprints']))
        sources['Analytische Quelle']['findings'][0]['verdichtung']='Changed original, unchanged timestamp.'
        with self.assertRaisesRegex(ValueError,'Projektionsnachweis'):validate_synthesis_provenance(payload,sources)

    def test_present_projection_hashes_require_exact_real_labels_and_hash_values(self):
        for change in ('missing','foreign','wrong','none','nonstring'):
            payload,sources=synthesis_fixture()
            hashes=payload['source_projection_fingerprints']
            if change=='missing':hashes.pop('Leere Quelle')
            if change=='foreign':hashes['foreign']='0'*64
            if change=='wrong':hashes['Leere Quelle']='0'*64
            if change=='none':payload['source_projection_fingerprints']=None
            if change=='nonstring':hashes['Leere Quelle']=True
            with self.subTest(change=change),self.assertRaises(ValueError):validate_synthesis_provenance(payload,sources)

    def test_reserved_extensions_ignored_and_inputs_unchanged(self):
        for reduced in (False,True):
            payload,sources=synthesis_fixture(reduced=reduced);expected=validate_synthesis_provenance(payload,sources)
            payload['analysis_perspective']={'interpretations':'Additional result'}
            for source in sources.values():
                source['analysis_perspective']={'text':'extra '*1000}
                source['selection_provenance']={'registry':'extra'}
                source['code_cooccurrence']={'counts':'extra'}
            before=copy.deepcopy((payload,sources))
            actual=validate_synthesis_provenance(payload,sources)
            self.assertEqual(actual,expected);self.assertEqual((payload,sources),before)
            actual['references'].clear();self.assertEqual((payload,sources),before)


if __name__=='__main__':unittest.main()
