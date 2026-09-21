import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from report_annotations import editable_fields, load_fields
from html_report import local_file


class ReportAnnotationTests(unittest.TestCase):
    def test_exact_swot_meta_finding_chain_not_just_reused_counter_or_quote(self):
        source={'swot':{'Code':{'strengths':[{'thema':'Gerät','analyse':'SWOT Deutung','segment_ids':['S1']}]}}}
        swot=editable_fields('SWOT Deutung',source,{'S1':'Original'})['0']
        registry={'S0001':{'source_id':'Code','thema':'Gerät','analyse':'SWOT Deutung','segment_ids':['S1']}}
        meta={'finding_registry':registry,'meta_swot':{'strengths':{'uebergreifende_muster':[{'thema':'Meta Gerät','verdichtung':'Meta Deutung','finding_ids':['S0001']}]}}}
        field=editable_fields('Meta Deutung',meta,{'S1':'Original'})['0']
        self.assertEqual(field['parent_items'][0]['id'],swot['item_id'])
        self.assertEqual(field['parent_items'][0]['reference'],'S0001')
        self.assertEqual(field['evidence'][0]['text'],'Original')
        registry['S0001']['analyse']='Anderer Befund unter gleicher Kennung'
        different=editable_fields('Meta Deutung',meta,{'S1':'Original'})['0']
        self.assertNotEqual(different['parent_items'][0]['id'],swot['item_id'])

    def test_frequency_interpretation_links_back_to_its_exact_swot_finding(self):
        payload={'swot':{'C':{'strengths':[{'thema':'T','analyse':'Originalbefund','segment_ids':['S']}]}}}
        payload['analysis_perspective']={'source_links':{'T1':{'module_id':'swot','code_path':'C','dimension':'strengths','thema':'T','qualitative_text':'Originalbefund','selected_evidence_segment_ids':['S']}},'interpretations':[{'topic_id':'T1','interpretation':'Häufigkeitsdeutung'}]}
        fields=editable_fields('Originalbefund\nHäufigkeitsdeutung',payload,{'S':'Zitat'})
        self.assertEqual(fields['0']['item_id'],fields['1']['item_id'])

    def test_negation_can_be_corrected_but_original_quote_is_not_an_editable_field(self):
        quote = 'Simulation startet nicht auf Leihgeräten.'
        prose = 'Die Simulation startet auf Leihgeräten.'
        payload = {'segment_metadata': {'S1': {'person': 'P1'}}, 'swot': [{'analyse': prose,
                   'segment_ids': ['S1'], 'zitate': [{'segment_id': 'S1', 'text': quote}]}]}
        markdown = f'### Befund\n\n{prose}\n\n**Empirische Belege:**\n\n- `S1`: {quote}\n'
        original = json.dumps(payload, sort_keys=True)
        fields = editable_fields(markdown, payload, {'S1': quote})
        self.assertEqual(list(fields), ['2'])
        self.assertEqual(fields['2']['evidence'], [{'id': 'S1', 'text': quote, 'person': 'P1'}])
        self.assertEqual(json.dumps(payload, sort_keys=True), original)
        self.assertEqual(fields['2']['original'], prose)

    def test_quote_fields_embedded_quotes_tables_and_ambiguous_matches_stay_locked(self):
        quote = 'Das Gerät startet nicht.'
        payload = {'analyse': 'Deutung', 'zitate': [{'summary': 'Gesperrt', 'text': quote}],
                   'other': {'summary': 'Deutung'}, 'interpretation': f'Er sagt: {quote}'}
        self.assertEqual(editable_fields('Deutung\nGesperrt\n'+payload['interpretation'], payload), {})
        self.assertEqual(editable_fields('Deutung\nDeutung', {'analyse': 'Deutung'}), {})
        self.assertEqual(editable_fields('| Deutung |\n> Deutung\n```\nDeutung\n```', {'analyse': 'Deutung'}), {})

    def test_thematic_source_links_and_fingerprint_bind_exact_source(self):
        p={'analysis_perspective': {'source_links': {'T': {'selected_evidence_segment_ids': ['S']}},
           'interpretations': {'frequency': [{'topic_id': 'T', 'interpretation': 'Deutung'}]}}}
        field=editable_fields('Deutung', p, {'S':'Zitat'})['0']
        self.assertEqual(field['topic_id'], 'T')
        self.assertEqual(field['evidence'][0]['text'], 'Zitat')
        self.assertNotEqual(field['source_sha256'], editable_fields('Deutung', p, {'S':'Anderes Zitat'})['0']['source_sha256'])

    def test_conflicting_original_quote_register_is_not_silently_relabelled(self):
        with self.assertRaises(ValueError):
            editable_fields('Deutung', {'analyse':'Deutung','segment_ids':['S'],
                            'zitate':[{'segment_id':'S','text':'Original'}]}, {'S':'Widerspruch'})

    def test_custom_output_path_and_missing_map_keep_quote_from_saved_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'custom.json').write_text(json.dumps({'analyse':'Deutung','segment_ids':['S'],
                'zitate':[{'segment_id':'S','text':'Original'}]}),encoding='utf-8')
            field=load_fields(root,{'args':['--out-json','custom.json']},'Deutung',local_file)['0']
            self.assertEqual(field['evidence'][0]['text'],'Original')
            with self.assertRaises(ValueError):
                load_fields(root,{'args':['--out-json','../secret.json']},'Deutung',local_file)

    def test_review_note_binds_exact_topic_field_and_original_and_rejects_stale_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            data={'analysis_perspective':{'interpretations':{'frequency':[{'topic_id':'T','interpretation':'Deutung'}]}}}
            (root/'result.json').write_text(json.dumps(data),encoding='utf-8')
            flag={'module_id':'swot','topic_id':'T','field':'interpretation','original':'Deutung','note':'Original hat eine Verneinung.'}
            path=root/'report_review_flags.json'
            path.write_text(json.dumps({'schema_version':1,'flags':[flag]}),encoding='utf-8')
            module={'id':'swot','args':['--out-json','result.json']}
            field=load_fields(root,module,'Deutung',local_file)['0']
            self.assertEqual(field['review_note'],flag['note'])
            self.assertEqual(field['original'],'Deutung')
            other=load_fields(root,{**module,'id':'other'},'Deutung',local_file)['0']
            self.assertNotIn('review_note',other)
            flag['original']='Anderer Vorschlag'
            path.write_text(json.dumps({'schema_version':1,'flags':[flag]}),encoding='utf-8')
            with self.assertRaises(ValueError):load_fields(root,module,'Deutung',local_file)

    def test_cluster_membership_quotes_are_visible_with_limited_claim_and_custom_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            payload={'analysis_perspective':{'source_links':{'T':{'member_segment_ids':['S']}},
                'interpretations':{'frequency':[{'topic_id':'T','interpretation':'Deutung'}]}}}
            (root/'result.json').write_text(json.dumps(payload),encoding='utf-8')
            (root/'custom_map.json').write_text(json.dumps({'S':'Unveränderbares Original.'}),encoding='utf-8')
            module={'id':'clusterer','args':['--out-json','result.json','--idmap-json','custom_map.json']}
            field=load_fields(root,module,'Deutung',local_file)['0']
            self.assertEqual(field['evidence'][0]['text'],'Unveränderbares Original.')
            self.assertIn('nicht automatisch jede Aussage',field['evidence_note'])
            self.assertEqual(field['evidence'][0]['id'],'S')
            self.assertEqual(json.loads((root/'custom_map.json').read_text()),{'S':'Unveränderbares Original.'})
