import copy
import unittest
from coding_validation_common import Segment
from thematic_material import build_material
from thematic_memberships import cluster_memberships


def fixture():
    rows=[Segment('s1','x','A','P1','u1'),Segment('s2','x','B','P1','u1'),
          Segment('s3','y','A','P2','u2'),Segment('s4','z','B','P2','u3')]
    material=build_material(rows,person_basis='confirmed')
    payload={'processing_status':'completed',
        'segment_metadata':{s.segment_id:{'person':s.person,'unit_id':s.unit_id} for s in rows},
        'clusters':[{'cluster_name':'Identischer Titel','definition':'Erste Bedeutung','code_path':'A','segments':['s1']},
                    {'cluster_name':'Anderes','definition':'Zweite Bedeutung','code_path':'A','segments':['s3']},
                    {'cluster_name':'Identischer Titel','definition':'Andere Bedeutung','code_path':'B','segments':['s2','s4']}]}
    return material,payload


class MembershipTests(unittest.TestCase):
    def test_shortened_index_and_sources_cannot_hide_an_original_row(self):
        material, payload = fixture()
        del material['segment_index']['s3']
        del payload['segment_metadata']['s3']
        payload['clusters'].pop(1)
        with self.assertRaisesRegex(ValueError, 'vollständige Originalzuordnung'):
            cluster_memberships(material, payload)

    def test_wrong_unit_or_code_index_rejected_against_original_units(self):
        for change in ('unit', 'code', 'missing_index'):
            with self.subTest(change=change):
                material, payload = fixture()
                if change == 'unit':
                    material['segment_index']['s1']['unit_id'] = 'passage:u2'
                elif change == 'code':
                    material['segment_index']['s2']['code_path'] = 'A'
                else:
                    del material['segment_index']
                with self.assertRaises(ValueError):
                    cluster_memberships(material, payload)

    def test_complete_clusters_project_to_scoped_cells_without_new_model_work(self):
        material,payload=fixture();before=copy.deepcopy(payload);result=cluster_memberships(material,payload)
        self.assertEqual(result['model_calls'],0);self.assertEqual(payload,before)
        self.assertEqual(len(result['topics']),3);self.assertEqual(len(result['assignments']),6)
        self.assertEqual(len({t['topic_id'] for t in result['topics']}),3)
        self.assertEqual({t['kind'] for t in result['topics']},{'membership'})
        b=next(t for t in result['topics'] if t['definition']=='Andere Bedeutung')
        self.assertEqual(b['scope_unit_ids'],['passage:u1','passage:u3'])
        self.assertEqual({c['status'] for c in result['assignments'] if c['topic_id']==b['topic_id']},{'supported'})
        payload['clusters'].reverse()
        reordered=cluster_memberships(material,payload)
        self.assertEqual(result['topics'],reordered['topics']);self.assertEqual(result['assignments'],reordered['assignments'])

    def test_partial_foreign_crosscode_or_duplicate_membership_cannot_claim_completeness(self):
        material,payload=fixture()
        for change in ('missing','foreign','crosscode','duplicate','person','metadata','failed','definition'):
            value=copy.deepcopy(payload)
            if change=='missing':value['clusters'].pop(1)
            if change=='foreign':value['clusters'][0]['segments']=['foreign']
            if change=='crosscode':value['clusters'][0]['segments']=['s2']
            if change=='duplicate':value['clusters'].append(copy.deepcopy(value['clusters'][0]))
            if change=='person':value['segment_metadata']['s1']['person']='Other'
            if change=='metadata':value.pop('segment_metadata')
            if change=='failed':value['processing_status']='failed'
            if change=='definition':value['clusters'][0]['definition']=''
            with self.subTest(change=change),self.assertRaises(ValueError):cluster_memberships(material,value)

    def test_overlapping_cluster_members_remain_separate_not_summed(self):
        material,payload=fixture();payload['clusters'][1]['segments']=['s1','s3']
        result=cluster_memberships(material,payload)
        self.assertEqual(len(result['topics']),3)
        self.assertEqual(sum(c['status']=='supported' for c in result['assignments']),5)
        self.assertEqual(len(material['persons']),2)


if __name__=='__main__':unittest.main()
