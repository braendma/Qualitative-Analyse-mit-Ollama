"""Synthetic fixtures use the shipped core normalizers without any model calls."""
import copy
import unittest
from unittest.mock import patch

from coding_validation_common import Segment
from person_analysis_core import normalize_person_analysis
from ambiguity_analysis_core import normalize_person_ambiguities
from thematic_material import build_material
from thematic_counts import count_topics
from thematic_person_adapters import build_person_topics, build_ambiguity_topics


def fixture(person_count=2, passages_per_person=2):
    """Return material, real-normalized person payload, real-normalized ambiguity payload.

    Each person has multiple document parts, explicit passage IDs, and one
    multiply coded passage. Documentary segment IDs deliberately aren't person IDs.
    """
    rows = []
    for number in range(1, person_count + 1):
        person = f'P{number:02d}'
        for part in range(1, passages_per_person + 1):
            sid = f'Document_{number}_{part}'
            text = 'Planbare Zeiten helfen.' if part == 1 else 'In anderen Situationen ist spontane Flexibilität wichtig.'
            rows.append(Segment(sid, text, 'A' if part == 1 else 'B', person, f'passage_{number}_{part}'))
            if part == 1:
                rows.append(Segment(sid + '_second_code', text, 'B', person, f'passage_{number}_{part}'))
    material = build_material(rows, person_basis='confirmed')
    texts = {row.segment_id: row.text for row in rows}
    people = {}; ambiguities = {}
    for number, person in enumerate(material['persons'], 1):
        ids = sorted(row.segment_id for row in rows if row.person == person)
        a = f'Document_{number}_1'; b = f'Document_{number}_2'
        normalized = normalize_person_analysis({'zentrale_themen': [{'thema': 'Zeitgestaltung', 'verdichtung': 'Planbarkeit ist relevant.', 'segment_ids': [a]}],
            'perspektiven': [{'aussage': 'Eigene Zeiten gestalten.', 'segment_ids': [a]}],
            'spannungsfelder': [{'beschreibung': 'Planung und Flexibilität.', 'segment_ids': [a]}],
            'kontrastierende_aspekte': [{'beschreibung': 'Situationsabhängige Bedürfnisse.', 'segment_ids': [a]}]}, set(ids), texts)
        people[person] = {'person': person, 'segment_ids': ids, 'abgedeckte_hauptkategorien': ['A', 'B'], 'abgedeckte_facetten': [], **normalized}
        normalized_amb = normalize_person_ambiguities({'ambivalenzen': [{'thema': 'Zeitgestaltung', 'beschreibung': 'Unterschiedliche Situationen.',
            'position_a': 'Planbare Zeiten helfen.', 'position_b': 'Spontane Flexibilität hilft.', 'segment_ids_a': [a], 'segment_ids_b': [b]}],
            'gesamteinordnung': 'Beide Bedürfnisse können nebeneinander bestehen.'}, set(ids), texts)
        normalized_amb['ambivalenzen'][0]['ambiguity_id'] = f'AMB{number:04d}'
        ambiguities[person] = {'person': person, 'segment_count': len(ids), **normalized_amb,
            'input_reduction': {'segment_ids': ids, 'parts': 2, 'context': {'used': True}, 'note': 'Blockübergreifende Kandidaten können fehlen.'}}
    person_payload = {'created_at': 'synthetic-person-source', 'source_cluster_created_at': 'synthetic-cluster-source', 'persons': people}
    ambiguity_payload = {'created_at': 'synthetic-ambiguity-output', 'source_person_analysis_created_at': person_payload['created_at'],
        'person_count': person_count, 'persons_with_ambiguities': person_count, 'ambiguity_count': person_count, 'persons': ambiguities}
    return material, person_payload, ambiguity_payload


class PersonTopicAdapterTests(unittest.TestCase):
    def test_all_sections_use_complete_single_person_scope_not_chosen_quotes(self):
        material, payload, _ = fixture(); before = copy.deepcopy((material, payload))
        result = build_person_topics(material, payload)
        self.assertEqual(len(result['topics']), 8); self.assertIsNone(result['assignments']); self.assertEqual(result['model_calls'], 0)
        self.assertEqual({t['kind'] for t in result['topics']}, {'derived'})
        for topic in result['topics']:
            link = result['source_links'][topic['topic_id']]
            self.assertEqual(len(topic['scope_unit_ids']), 2)
            self.assertEqual({material['units'][uid]['person'] for uid in topic['scope_unit_ids']}, {link['person']})
            self.assertEqual(len(link['selected_evidence_segment_ids']), 1)
        self.assertEqual((material, payload), before)
        result['qualitative_source']['persons'].clear(); self.assertEqual((material, payload), before)
        self.assertIn('gesamtverdichtung', result['unassigned_context']['persons']['P01'])
        self.assertTrue(all('gesamtverdichtung' != result['source_links'][t['topic_id']]['section'] for t in result['topics']))

    def test_twelve_confirmed_people_from_twentyfour_parts_and_multicodes_not_twentyfour_people(self):
        material, payload, _ = fixture(12)
        result = build_person_topics(material, payload)
        self.assertEqual(len(material['persons']), 12); self.assertEqual(len(material['units']), 24)
        self.assertEqual(len(material['segment_index']), 36)
        self.assertEqual(len({t['topic_id'] for t in result['topics']}), 48)
        counted = count_topics(material, result['topics'], [])
        self.assertTrue(all(row['scope']['person_count'] == 1 for row in counted['topics']))
        self.assertTrue(all(row['scope']['unit_count'] == 2 for row in counted['topics']))

    def test_ten_identically_worded_separate_passages_do_not_become_ten_people_or_one_passage(self):
        material, payload, _ = fixture(1, 10); result = build_person_topics(material, payload)
        assignments = [{'topic_id': t['topic_id'], 'unit_id': uid, 'status': 'supported'} for t in result['topics'] for uid in t['scope_unit_ids']]
        counted = count_topics(material, result['topics'], assignments)
        for row in counted['topics']:
            self.assertEqual(row['counts']['supporting']['exact_person_count'], 1)
            self.assertEqual(row['counts']['supporting']['exact_unit_count'], 10)

    def test_person_identity_stable_under_reordering_and_evidence_changes_but_not_changed_definition(self):
        material, payload, _ = fixture(); result = build_person_topics(material, payload)
        changed = copy.deepcopy(payload); changed['persons'] = dict(reversed(list(changed['persons'].items())))
        for row in changed['persons'].values():row['segment_ids'].reverse()
        self.assertEqual(result['topics'], build_person_topics(material, changed)['topics'])
        row = changed['persons']['P01']; row['zentrale_themen'][0]['segment_ids'] = ['Document_1_2']
        row['belege'].append({'segment_id': 'Document_1_2', 'zitat': material['units']['passage:passage_1_2']['text']})
        sampled = build_person_topics(material, changed)
        self.assertEqual(result['topics'], sampled['topics']); self.assertNotEqual(result['source_fingerprint'], sampled['source_fingerprint'])
        row['zentrale_themen'][0]['verdichtung'] += ' Neue Interpretation.'
        self.assertNotEqual(result['topics'], build_person_topics(material, changed)['topics'])

    def test_person_rejects_missing_foreign_duplicate_and_corrupted_original_sources(self):
        material, payload, _ = fixture()
        for case in ('missing_person', 'wrong_person', 'foreign_input', 'missing_input', 'duplicate_input', 'foreign_evidence', 'unknown_evidence', 'duplicate_evidence',
                     'quote', 'missing_quote', 'duplicate_quote', 'missing_section', 'bad_section', 'duplicate_topic', 'empty_statement', 'failed'):
            broken = copy.deepcopy(payload); row = broken['persons']['P01']
            if case == 'missing_person': broken['persons'].pop('P02')
            if case == 'wrong_person': row['person'] = 'P02'
            if case == 'foreign_input': row['segment_ids'][-1] = 'Document_2_2'
            if case == 'missing_input': row['segment_ids'].pop()
            if case == 'duplicate_input': row['segment_ids'].append(row['segment_ids'][0])
            if case == 'foreign_evidence': row['perspektiven'][0]['segment_ids'] = ['Document_2_1']
            if case == 'unknown_evidence': row['perspektiven'][0]['segment_ids'] = ['missing']
            if case == 'duplicate_evidence': row['perspektiven'][0]['segment_ids'] *= 2
            if case == 'quote': row['belege'][0]['zitat'] = 'Nicht original.'
            if case == 'missing_quote': row['belege'] = []
            if case == 'duplicate_quote': row['belege'].append(copy.deepcopy(row['belege'][0]))
            if case == 'missing_section': row.pop('perspektiven')
            if case == 'bad_section': row['spannungsfelder'] = None
            if case == 'duplicate_topic': row['zentrale_themen'].append(copy.deepcopy(row['zentrale_themen'][0]))
            if case == 'empty_statement': row['perspektiven'][0]['aussage'] = ' '
            if case == 'failed': broken['processing_status'] = 'failed'
            with self.subTest(case=case), self.assertRaises(ValueError): build_person_topics(material, broken)

    def test_confirmed_material_and_consistent_index_required(self):
        material, payload, amb = fixture()
        for change in ('unconfirmed', 'index_missing', 'index_wrong_unit'):
            bad = copy.deepcopy(material)
            if change == 'unconfirmed': bad['person_basis'] = 'unconfirmed'
            if change == 'index_missing': bad['segment_index'].pop('Document_1_1')
            if change == 'index_wrong_unit': bad['segment_index']['Document_1_1']['unit_id'] = 'passage:passage_2_1'
            for fn, args in [(build_person_topics,(bad,payload)),(build_ambiguity_topics,(bad,amb,payload))]:
                with self.subTest(change=change, fn=fn.__name__), self.assertRaises(ValueError): fn(*args)

    def test_empty_normalized_person_sections_and_label_only_central_theme_remain_valid(self):
        material, payload, _ = fixture(1)
        row = payload['persons']['P01']; row['zentrale_themen'][0]['verdichtung'] = ''
        self.assertEqual(len(build_person_topics(material,payload)['topics']),4)
        row.update(normalize_person_analysis({}, set(row['segment_ids']), {}))
        result = build_person_topics(material,payload); self.assertEqual(result['topics'],[]); self.assertIsNone(result['assignments'])

    def test_weighted_extension_is_not_a_candidate_or_fingerprint_source(self):
        material, person, payload = fixture()
        base_person = build_person_topics(material, person)
        base_amb = build_ambiguity_topics(material, payload, person)
        person['analysis_perspective'] = {'interpretation': 'Andere Gewichtung', 'counts': {'invented': 999}}
        payload['analysis_perspective'] = {'interpretation': 'Andere Ambivalenzgewichtung', 'counts': {'invented': 888}}
        before = copy.deepcopy((person, payload))
        self.assertEqual(base_person, build_person_topics(material, person))
        self.assertEqual(base_amb, build_ambiguity_topics(material, payload, person))
        self.assertEqual((person, payload), before)


class AmbiguityTopicAdapterTests(unittest.TestCase):
    def test_two_independent_sides_share_pair_and_single_person_scope(self):
        material, person, payload = fixture(); before = copy.deepcopy((material,person,payload))
        result = build_ambiguity_topics(material,payload,person)
        self.assertEqual(len(result['topics']),4);self.assertIsNone(result['assignments']); self.assertEqual(result['model_calls'],0)
        for who in material['persons']:
            links = [row for row in result['source_links'].values() if row['person']==who]
            self.assertEqual({row['side'] for row in links},{'A','B'});self.assertEqual(len({row['pair_id'] for row in links}),1)
            self.assertTrue(all('Position A:' in row['qualitative_text'] and 'Position B:' in row['qualitative_text'] for row in links))
        self.assertTrue(all(len(t['scope_unit_ids'])==2 for t in result['topics']))
        self.assertTrue(all(t['kind']=='derived' for t in result['topics']))
        self.assertEqual((material,person,payload),before)
        self.assertTrue(result['unassigned_context']['persons']['P01']['input_reduction']['context']['used'])
        self.assertIn('blockübergreifende',result['methodological_note'])

    def test_same_passage_can_support_both_sides_without_automatic_negation(self):
        material, person, payload = fixture(1); result = build_ambiguity_topics(material,payload,person)
        rows = [{'topic_id':t['topic_id'],'unit_id':uid,'status':'supported' if uid.endswith('_1') else 'no_evidence'} for t in result['topics'] for uid in t['scope_unit_ids']]
        counted=count_topics(material,result['topics'],rows)
        a,b=counted['topics'];self.assertEqual(a['counts']['supporting']['unit_ids'],b['counts']['supporting']['unit_ids'])
        self.assertTrue(all(t['counts']['supporting']['exact_person_count']==1 for t in counted['topics']))
        self.assertTrue(all(t['counts']['opposing']['exact_unit_count']==0 for t in counted['topics']))
        rows[0]['status']='unclear'; counted=count_topics(material,result['topics'],rows)
        self.assertIsNone(counted['topics'][0]['counts']['supporting']['exact_unit_count'])

    def test_pair_identity_ignores_amb_counter_but_binds_side_roles_and_source_fingerprint(self):
        material, person, payload = fixture(); result=build_ambiguity_topics(material,payload,person)
        changed=copy.deepcopy(payload); row=changed['persons']['P01']['ambivalenzen'][0];row['ambiguity_id']='AMB0099'
        renumbered=build_ambiguity_topics(material,changed,person)
        self.assertEqual(result['topics'],renumbered['topics']);self.assertNotEqual(result['source_fingerprint'],renumbered['source_fingerprint'])
        for prefix in ('position_','segment_ids_','belege_'):row[prefix+'a'],row[prefix+'b']=row[prefix+'b'],row[prefix+'a']
        self.assertNotEqual(result['topics'],build_ambiguity_topics(material,changed,person)['topics'])

    def test_ambiguity_rejects_wrong_sources_incomplete_sides_quotes_and_statistics(self):
        material, person, payload=fixture()
        cases=('missing_person','wrong_person','wrong_source','count','bool_count','scope','missing_reduction','empty_position','foreign_side','unknown_side','missing_side','same_sides','bad_quote','missing_quote','duplicate_id','duplicate_pair','wrong_total','wrong_person_total','failed')
        for case in cases:
            bad=copy.deepcopy(payload);row=bad['persons']['P01'];finding=row['ambivalenzen'][0]
            if case=='missing_person':bad['persons'].pop('P02')
            if case=='wrong_person':row['person']='P02'
            if case=='wrong_source':bad['source_person_analysis_created_at']='foreign'
            if case=='count':row['segment_count']=2
            if case=='bool_count':row['segment_count']=True
            if case=='scope':row['input_reduction']['segment_ids']=['Document_1_1','Document_2_2']
            if case=='missing_reduction':row.pop('input_reduction')
            if case=='empty_position':finding['position_b']=''
            if case=='foreign_side':finding['segment_ids_b']=['Document_2_2']
            if case=='unknown_side':finding['segment_ids_b']=['unknown']
            if case=='missing_side':finding['segment_ids_a']=[]
            if case=='same_sides':finding['segment_ids_b']=finding['segment_ids_a'];finding['belege_b']=finding['belege_a']
            if case=='bad_quote':finding['belege_b'][0]['text']='not original'
            if case=='missing_quote':finding['belege_a']=[]
            if case=='duplicate_id':bad['persons']['P02']['ambivalenzen'][0]['ambiguity_id']=finding['ambiguity_id']
            if case=='duplicate_pair':row['ambivalenzen'].append({**copy.deepcopy(finding),'ambiguity_id':'AMB0999'})
            if case=='wrong_total':bad['ambiguity_count']=999
            if case=='wrong_person_total':bad['persons_with_ambiguities']=0
            if case=='failed':bad['processing_status']='failed'
            with self.subTest(case=case),self.assertRaises(ValueError):build_ambiguity_topics(material,bad,person)
        broken_person=copy.deepcopy(person);broken_person['persons']['P02']['belege'][0]['zitat']='corrupt unused source person'
        with self.assertRaises(ValueError):build_ambiguity_topics(material,payload,broken_person)

    def test_empty_ambiguity_output_does_not_invent_themes_and_preserves_unassigned_context(self):
        material,person,payload=fixture(1);row=payload['persons']['P01'];row['ambivalenzen']=[]
        payload.update(ambiguity_count=0,persons_with_ambiguities=0)
        result=build_ambiguity_topics(material,payload,person)
        self.assertEqual(result['topics'],[]);self.assertIsNone(result['assignments']);self.assertIn('Gesamteinordnung',result['unassigned_context']['counting_note'])

    def test_large_complete_context_is_retained_and_adapter_never_allocates_count_matrix(self):
        material,person,payload=fixture(1);full='Sehr langer Kontext. '*10000
        payload['persons']['P01']['ambivalenzen'][0]['beschreibung']=full
        with patch('thematic_counts.count_topics',side_effect=AssertionError('No matrix allocation in adapter')):
            result=build_ambiguity_topics(material,payload,person)
        self.assertTrue(all(full in topic['definition'] for topic in result['topics']))
        self.assertTrue(all(full in link['qualitative_text'] for link in result['source_links'].values()))


if __name__=='__main__':unittest.main()
