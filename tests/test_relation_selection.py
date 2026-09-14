"""Synthetic exact selection/replay tests; no model or subprocess access."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from coding_validation_common import Segment
from thematic_material import build_material
from runtime_support import fingerprint
from relation_analysis_core import build_units, build_candidate_pairs, normalize_relations, build_relation_analysis
from relation_selection import build_relation_selection, validate_relation_selection


def relation_fixture():
    """Return (confirmed material, complete clusters, complete summaries)."""
    rows = [Segment('A1','Shared passage','A','P1','u1'), Segment('B1','Shared passage','B','P1','u1'),
        Segment('A2','A second person','A','P2','u2'), Segment('B2','B second person','B','P2','u3'),
        Segment('C2','C second person','C','P2','u4'), Segment('C3','C third person','C','P3','u5')]
    material = build_material(rows, person_basis='confirmed')
    clusters = {'created_at': 'synthetic-clusters', 'processing_status': 'completed',
        'segment_metadata': {s.segment_id: {'person': s.person, 'unit_id': s.unit_id} for s in rows},
        'clusters': [{'hauptkategorie': code, 'code_path': code, 'cluster_name': code, 'definition': 'Definition ' + code,
            'segments': [s.segment_id for s in rows if s.human_code == code]} for code in ('A','B','C')]}
    summaries = {'created_at': 'synthetic-summary', 'cluster_summaries': [
        {**copy.deepcopy(row), 'summary': 'Zusammenfassung ' + row['code_path']} for row in clusters['clusters']],
        'final_summary': 'Originale qualitative Zusammenfassung.'}
    return material, clusters, summaries


def _inputs(material, clusters, summary, max_pairs=1, max_segments=2):
    texts = {sid: material['units'][row['unit_id']]['text'] for sid,row in material['segment_index'].items()}
    units = build_units(clusters['clusters'], texts, summary, clusters['segment_metadata'])
    pairs, total = build_candidate_pairs(units,max_pairs,max_segments)
    return texts, units, pairs, total


def _payload(material, clusters, summary, *, across=False, max_pairs=1, max_segments=2):
    texts, units, pairs, total = _inputs(material,clusters,summary,max_pairs,max_segments)
    raw = []
    if pairs:
        p = pairs[0]
        raw = [{'pair_id': p['pair_id'], 'thema': 'Verbindung', 'beschreibung': 'Eine qualitative Beziehung.',
            'beziehungstyp': 'wird_miteinander_verknuepft', 'segment_ids_a': [p['segmente_a'][0]['id']],
            'segment_ids_b': [p['segmente_b'][-1 if across else 0]['id']]}]
    normalized = normalize_relations({'beziehungen':raw, 'gesamteinordnung':'Originaler Kontext.'},
                                    {p['pair_id']:p for p in pairs},texts)
    return {'created_at':'synthetic-relation', 'source_cluster_created_at':clusters['created_at'],
        'source_summary_created_at':summary['created_at'], 'context_reduction':{}, 'codepfad_count':len(units),
        'candidate_pair_count_total':total, 'omitted_pair_count':total-len(pairs), 'candidate_pair_count_submitted':len(pairs),
        'candidate_pair_count_with_relation':len(raw), 'candidate_pair_count_without_validated_relation':len(pairs)-len(raw),
        'selection_provenance':build_relation_selection(material,clusters,summary,max_pairs=max_pairs,max_segments_per_path=max_segments),
        **normalized}


class RelationSelectionTests(unittest.TestCase):
    def test_complete_ranked_registry_records_only_actual_selected_examples(self):
        material,clusters,summary = relation_fixture()
        receipt = build_relation_selection(material,clusters,summary,max_pairs=1,max_segments_per_path=1)
        self.assertEqual(len(receipt['candidate_pairs']),3)
        self.assertEqual(sum(row['selected'] for row in receipt['candidate_pairs']),1)
        submitted = next(iter(receipt['submitted_pairs'].values()))
        self.assertEqual(submitted['segment_ids_a'],['A1']); self.assertEqual(submitted['segment_ids_b'],['B1'])
        self.assertEqual(submitted['sampled_person_ids'],['P1']); self.assertEqual(submitted['shared_person_ids'],['P1','P2'])
        self.assertEqual(receipt['path_registry']['A']['segment_ids'],['A1','A2'])
        self.assertEqual(receipt['verification_level'],'confirmed_original_material')
        self.assertNotIn('Shared passage',json.dumps(receipt))

    def test_full_registry_does_not_construct_unselected_quote_payloads(self):
        material,clusters,summary=relation_fixture()
        with patch('relation_analysis_core.build_candidate_pairs',wraps=build_candidate_pairs) as mock:
            build_relation_selection(material,clusters,summary,max_pairs=1,max_segments_per_path=1)
        self.assertEqual(mock.call_count,1)
        self.assertEqual(mock.call_args.args[1:],(1,1))

    def test_all_pairs_zero_and_strict_parameters(self):
        material,clusters,summary=relation_fixture()
        self.assertEqual(len(build_relation_selection(material,clusters,summary,max_pairs=0,max_segments_per_path=2)['submitted_pairs']),3)
        for a,b in ((True,2),('1',2),(-1,2),(1,0),(1,-1),(1,True),(1,'2')):
            with self.subTest(a=a,b=b), self.assertRaises(ValueError):
                build_relation_selection(material,clusters,summary,max_pairs=a,max_segments_per_path=b)

    def test_no_candidate_pairs_still_validate_limits_and_complete_empty_result(self):
        row=Segment('only','Original','A','P1','single')
        material=build_material([row],person_basis='confirmed')
        cluster={'code_path':'A','hauptkategorie':'A','cluster_name':'A','definition':'A definition','segments':['only']}
        clusters={'created_at':'one-source','processing_status':'completed','clusters':[cluster],'segment_metadata':{'only':{'person':'P1','unit_id':'single'}}}
        summary={'created_at':'one-summary','cluster_summaries':[{**cluster,'summary':'Summary'}],'final_summary':'Final'}
        payload=_payload(material,clusters,summary)
        self.assertEqual(payload['selection_provenance']['candidate_pairs'],[])
        self.assertEqual(validate_relation_selection(material,payload,clusters,summary),payload['selection_provenance'])
        with self.assertRaises(ValueError):build_relation_selection(material,clusters,summary,max_pairs=1,max_segments_per_path=0)

    def test_asymmetric_many_a_one_b_does_not_claim_exhaustive_examples(self):
        material,clusters,summary=relation_fixture()
        rows=[Segment(sid,material['units'][entry['unit_id']]['text'],entry['code_path'],
            material['units'][entry['unit_id']]['person'],clusters['segment_metadata'][sid]['unit_id'])
            for sid,entry in material['segment_index'].items()]
        extra=[Segment('extra'+str(i),'Additional A '+str(i),'A','P1','extra_u'+str(i)) for i in range(99)]
        material=build_material(rows+extra,person_basis='confirmed')
        clusters['clusters'][0]['segments'].extend(r.segment_id for r in extra)
        clusters['segment_metadata'].update({r.segment_id:{'person':r.person,'unit_id':r.unit_id} for r in extra})
        summary['cluster_summaries'][0]['segments']=list(clusters['clusters'][0]['segments'])
        receipt=build_relation_selection(material,clusters,summary,max_pairs=1,max_segments_per_path=100)
        submitted=next(iter(receipt['submitted_pairs'].values()))
        self.assertEqual(len(receipt['path_registry']['A']['segment_ids']),101)
        self.assertEqual(submitted['segment_ids_a'],['A1','A2'])
        self.assertEqual(submitted['segment_ids_b'],['B1','B2'])

    def test_replay_normalized_same_and_different_person_evidence(self):
        material,clusters,summary=relation_fixture()
        for across in (False,True):
            payload=_payload(material,clusters,summary,across=across)
            self.assertEqual(validate_relation_selection(material,payload,clusters,summary),payload['selection_provenance'])
            row=payload['beziehungen'][0]
            self.assertEqual(row['bezugsebene'],'personenuebergreifend' if across else 'innerhalb_person')
            self.assertEqual(row['beidseitig_belegte_personen'],[] if across else ['P1'])

    def test_foreign_or_modified_output_references_fail(self):
        material,clusters,summary=relation_fixture()
        for change in ('pair','path','text','person','scope','relationid','stat','side','duplicate','receipt','boolrank'):
            payload=_payload(material,clusters,summary); row=payload['beziehungen'][0]
            if change=='pair': row['pair_id']='PAIR0002'
            if change=='path': row['pfad_a']='B'
            if change=='text': row['belege_a'][0]['text']='modified'
            if change=='person': row['gemeinsame_personen']=['P3']
            if change=='scope': row['bezugsebene']='personenuebergreifend'
            if change=='relationid': row['relation_id']='REL9999'
            if change=='stat': payload['omitted_pair_count']=0
            if change=='side': row['segment_ids_a']=['B1']
            if change=='duplicate': payload['beziehungen'].append(copy.deepcopy(row))
            if change=='receipt': payload['selection_provenance']['candidate_pairs'][0]['shared_person_ids'].append('P3')
            if change=='boolrank': payload['selection_provenance']['candidate_pairs'][0]['rank']=True
            with self.subTest(change=change),self.assertRaises(ValueError):validate_relation_selection(material,payload,clusters,summary)

    def test_source_and_confirmed_material_must_be_complete(self):
        for change in ('unconfirmed','metadata','missing','crosscode','summary'):
            material,clusters,summary=relation_fixture()
            if change=='unconfirmed': material['person_basis']='unconfirmed'
            if change=='metadata': clusters['segment_metadata']['A1']['person']='P3'
            if change=='missing': clusters['clusters'].pop()
            if change=='crosscode': clusters['clusters'][0]['segments']=['B1','A2']
            if change=='summary': summary['cluster_summaries'].pop()
            with self.subTest(change=change),self.assertRaises(ValueError):
                build_relation_selection(material,clusters,summary,max_pairs=1,max_segments_per_path=2)

    def test_actual_source_order_changes_receipt_not_pair_identity(self):
        material,clusters,summary=relation_fixture()
        before=build_relation_selection(material,clusters,summary,max_pairs=1,max_segments_per_path=1)
        for row in clusters['clusters']:row['segments'].reverse()
        # Summary membership order is not an identity field; both remain valid.
        after=build_relation_selection(material,clusters,summary,max_pairs=1,max_segments_per_path=1)
        self.assertEqual(set(before['submitted_pairs']),set(after['submitted_pairs']))
        self.assertNotEqual(before['selection_fingerprint'],after['selection_fingerprint'])

    def test_legacy_output_does_not_gain_confirmed_selection(self):
        material,clusters,summary=relation_fixture();payload=_payload(material,clusters,summary)
        del payload['selection_provenance']
        with self.assertRaisesRegex(ValueError,'nicht vollständig nachweisbar'):
            validate_relation_selection(material,payload,clusters,summary)

    def test_context_receipts_bind_actual_original_side_context(self):
        material,clusters,summary=relation_fixture();payload=_payload(material,clusters,summary)
        _,_,pairs,_=_inputs(material,clusters,summary)
        payload['context_reduction']={'PAIR0001':{
            'a':{'used':False,'source_sha256':fingerprint(pairs[0]['cluster_a'])},
            'b':{'used':True,'source_sha256':fingerprint(pairs[0]['cluster_b']),'summary':'Kurze Verdichtung.','note':'Synthetic.'}}}
        validate_relation_selection(material,payload,clusters,summary)
        payload['context_reduction']['PAIR0001']['b']['source_sha256']='wrong'
        with self.assertRaises(ValueError):validate_relation_selection(material,payload,clusters,summary)

    def test_weighted_extensions_ignored_without_mutation(self):
        values=relation_fixture();material,clusters,summary=values
        before=build_relation_selection(*values,max_pairs=1,max_segments_per_path=2)
        clusters['analysis_perspective']={'text':'additional'};summary['analysis_perspective']={'text':'additional'}
        originals=copy.deepcopy(values)
        after=build_relation_selection(*values,max_pairs=1,max_segments_per_path=2)
        self.assertEqual(before,after);self.assertEqual(values,originals)
        after['path_registry']['A']['segment_ids'].clear();self.assertEqual(values,originals)

    def test_actual_core_selection_and_compacted_originals_replay(self):
        for compact in (False,True):
            material,clusters,summary=relation_fixture()
            if compact:
                for row in clusters['clusters']:row['definition']='Long synthetic definition '*1200
                for row in summary['cluster_summaries']:row['definition']='Long synthetic definition '*1200
            texts,_,_,_=_inputs(material,clusters,summary)
            seen=[]
            def model(system,user,params):
                data=json.loads(user);seen.extend(data['kandidaten']);pair=data['kandidaten'][0]
                return json.dumps({'beziehungen':[{'pair_id':pair['pair_id'],'thema':'Bezug','beschreibung':'Qualitative Beziehung.',
                    'beziehungstyp':'tritt_gemeinsam_auf','segment_ids_a':[pair['segmente_a'][0]['id']],
                    'segment_ids_b':[pair['segmente_b'][0]['id']]}],'gesamteinordnung':'Synthetic.'})
            with tempfile.TemporaryDirectory() as temp,patch('relation_analysis_core._llm',side_effect=model),\
                 patch('analysis_context.reduce_prompt',return_value='Kurzer vollständiger Hintergrund.'):
                root=Path(temp);paths=[]
                for name,value in (('clusters',clusters),('texts',texts),('summary',summary)):
                    path=root/(name+'.json');path.write_text(json.dumps(value),encoding='utf-8');paths.append(path)
                _,payload=build_relation_analysis(*paths,{'model':'synthetic','num_ctx':8000,'max_tokens':512,'partial_checkpoints':False},
                    {'relation_analysis':{'system':'Synthetic','user':'{data}'}},{},max_pairs=1,max_segments_per_path=2,material=material)
                validate_relation_selection(material,payload,clusters,summary)
                self.assertEqual(bool(payload['context_reduction']),compact)
                submitted=next(iter(payload['selection_provenance']['submitted_pairs'].values()))
                self.assertEqual(submitted['segment_ids_a'],[r['id'] for r in seen[0]['segmente_a']])
                self.assertEqual(seen[0]['segmente_a'][0]['text'],texts[submitted['segment_ids_a'][0]])


if __name__=='__main__':unittest.main()
