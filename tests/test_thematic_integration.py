"""Use actual confirmed CSV material across membership, counting and mode contracts."""
from pathlib import Path
import tempfile
import unittest

from analysis_perspectives import perspective_metadata, perspective_effort
from thematic_material import load_counting_material
from thematic_memberships import cluster_memberships
from thematic_counts import count_topics, union_topics
from test_thematic_material import workspace


class ThematicIntegrationTests(unittest.TestCase):
    def test_twelve_people_share_one_membership_basis_across_both_perspectives(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path,_=workspace(root);material=load_counting_material(path)
            clusters=[]
            for part in (1,2):
                clusters.append({'cluster_name':f'Thema {part}','definition':f'Künstliche Gruppe {part}',
                    'code_path':'A','segments':sorted(sid for sid in material['segment_index'] if sid.endswith('_'+str(part)))})
            payload={'processing_status':'completed','clusters':clusters,
                'segment_metadata':{sid:{'person':material['units'][entry['unit_id']]['person'],
                    'unit_id':entry['unit_id'][len('passage:'):]} for sid,entry in material['segment_index'].items()}}
            projected=cluster_memberships(material,payload)
            counted=count_topics(material,projected['topics'],projected['assignments'])
            for topic in counted['topics']:
                self.assertEqual(topic['count_meaning'],'model_assigned_group_membership')
                self.assertEqual(topic['scope']['person_count'],12)
                self.assertEqual(topic['scope']['passage_count'],24)
                self.assertEqual(topic['counts']['mentioned']['exact_person_count'],12)
                self.assertEqual(topic['counts']['mentioned']['exact_passage_count'],12)
            union=union_topics(material,counted,topic_id='all_clusters',definition='Explizite Vereinigung beider Gruppen',
                member_topic_ids=[t['topic_id'] for t in counted['topics']],exact_union=True)
            self.assertEqual(union['counts']['mentioned']['exact_person_count'],12)
            self.assertEqual(union['counts']['mentioned']['exact_passage_count'],24)
            both={'analysis_perspectives':{'clusterer':'both'}}
            effort=perspective_effort(both,['clusterer'],implemented_modules=['clusterer'])
            self.assertEqual(effort['shared_assignment_bases'],1)
            self.assertEqual(effort['modules'][0]['interpretation_outputs'],['qualitative','frequency'])
            self.assertIsNone(effort['additional_model_calls'])
            self.assertNotEqual(perspective_metadata(both,implemented_modules=['clusterer'])['fingerprint'],
                perspective_metadata({})['fingerprint'])
            self.assertEqual(material['basis_fingerprint'],counted['basis_fingerprint'])

    def test_partial_matrix_uses_observed_lower_bound_not_false_absence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path,_=workspace(Path(tmp));material=load_counting_material(path);units=list(material['units'])
            topic={'topic_id':'topic_a','definition':'Künstliche Nennung','inclusion':'','exclusion':'',
                'kind':'explicit','scope_unit_ids':units}
            rows=[{'topic_id':'topic_a','unit_id':units[0],'status':'supported'},
                  {'topic_id':'topic_a','unit_id':units[1],'status':'opposed'}]
            result=count_topics(material,[topic],rows)['topics'][0]
            self.assertEqual(result['coverage']['expected_cells'],24)
            self.assertEqual(result['coverage']['status_counts']['not_checked'],22)
            self.assertEqual(result['counts']['mentioned']['observed_passage_count'],2)
            self.assertIsNone(result['counts']['mentioned']['exact_passage_count'])
            self.assertIsNone(result['counts']['mentioned']['person_share_in_scope'])
            self.assertEqual(result['counts']['both']['observed_person_count'],1)


if __name__=='__main__':unittest.main()
