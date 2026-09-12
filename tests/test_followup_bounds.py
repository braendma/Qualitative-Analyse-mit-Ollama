import json
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from contrast_analysis_core import build_contrast_analysis
from ambiguity_analysis_core import build_ambiguity_analysis
from relation_analysis_core import build_relation_analysis
from analysis_context import compact_context


class FollowupBoundsTests(unittest.TestCase):
    params={'num_ctx':16384,'max_tokens':6000,'parallel_workers':2,'partial_checkpoints':False}
    def write(self,root,name,value):
        p=Path(root)/name;p.write_text(json.dumps(value),encoding='utf-8');return str(p)
    def compact(self,value,*args):return {'verdichteter_kontext':'kurzer Kontext'},{'used':True}
    def check(self,system,user,params):
        self.assertLessEqual(len((system+user).encode('utf-8'))+params['max_tokens']+320,params['num_ctx'])
        return json.loads(user)
    def test_complete_source_enters_context_reduction(self):
        value={'analysis':'Original '*4000};seen=[]
        def summary(s,u,p):seen.append(u);return 'kurze Analyse'
        out,receipt=compact_context(value,self.params,summary,800)
        self.assertTrue(receipt['used']);self.assertIn('kurze Analyse',out['verdichteter_kontext'])
        self.assertGreater(len(seen),1)
        self.assertEqual(''.join(u.split('\n\n',1)[1] for u in seen),json.dumps(value,ensure_ascii=False,indent=2))
    def test_contrast_covers_all_people_and_filters_invented_people(self):
        persons={f'P{i}':{'person':f'P{i}','analysis':'x'*40000} for i in range(21)};seen=[]
        def model(s,u,p):
            payload=self.check(s,u,p);names=[x['person'] for x in payload['personen']];seen.extend(names)
            return json.dumps({'dominante_muster':[],'negativfaelle':[{'person':'invented'}],
                'spannungen_zwischen_typen':[],'relativierungen':[],'gesamteinordnung':'Einordnung'})
        with tempfile.TemporaryDirectory() as tmp,patch('analysis_context.compact_context',side_effect=self.compact),patch('contrast_analysis_core.llm_contrast_analysis',side_effect=model):
            md,out=build_contrast_analysis(self.write(tmp,'people.json',{'persons':persons}),self.write(tmp,'comparison.json',{'typen':[]}),self.params,{'contrast_analysis':{'system':'sys','user':'{data}'}},{})
        self.assertCountEqual(seen,persons);self.assertEqual(out['negativfaelle'],[])
        self.assertIn('keine zusätzliche globale Synthese',md)
    def test_ambiguity_keeps_every_original_segment_and_only_block_evidence(self):
        texts={f'S{i}':f'Original{i} '+'x'*4500 for i in range(10)};seen={}
        def model(s,u,p):
            data=self.check(s,u,p)
            for x in data['originalsegmente']:seen[x['id']]=x['text']
            return json.dumps({'ambivalenzen':[{'thema':'T','segment_ids_a':[data['originalsegmente'][0]['id']],
                'segment_ids_b':['invented']}],'gesamteinordnung':'Test'})
        with tempfile.TemporaryDirectory() as tmp,patch('analysis_context.compact_context',side_effect=self.compact),patch('ambiguity_analysis_core._llm',side_effect=model):
            md,out=build_ambiguity_analysis(self.write(tmp,'people.json',{'persons':{'P1':{'analysis':'x'*90000,'segment_ids':list(texts)}}}),
                self.write(tmp,'texts.json',texts),self.params,{'ambiguity_analysis':{'system':'sys','user':'{data}'}},{})
        self.assertEqual(seen,texts);self.assertEqual(out['ambiguity_count'],0)
        self.assertIn('blockübergreifende',md)
    def test_relation_preserves_selected_originals_when_context_is_compacted(self):
        texts={'P1#SEG1':'Original A','P1#SEG2':'Original B'}
        clusters=[{'code_path':path,'hauptkategorie':path,'cluster_name':path,'definition':'x'*25000,'segments':[sid]} for path,sid in [('A','P1#SEG1'),('B','P1#SEG2')]]
        seen=[]
        def model(s,u,p):
            data=self.check(s,u,p);seen.extend(data['kandidaten'])
            pair=data['kandidaten'][0]
            return json.dumps({'beziehungen':[{'pair_id':pair['pair_id'],'segment_ids_a':['P1#SEG1'],'segment_ids_b':['P1#SEG2']}],'gesamteinordnung':'Test'})
        with tempfile.TemporaryDirectory() as tmp,patch('analysis_context.compact_context',side_effect=self.compact),patch('relation_analysis_core._llm',side_effect=model):
            md,out=build_relation_analysis(self.write(tmp,'clusters.json',{'clusters':clusters}),self.write(tmp,'texts.json',texts),
                self.write(tmp,'summary.json',{}),self.params,{'relation_analysis':{'system':'sys','user':'{data}'}},{})
        self.assertEqual(seen[0]['segmente_a'][0]['text'],'Original A')
        self.assertEqual(out['beziehungen'][0]['belege_b'][0]['text'],'Original B')
        self.assertTrue(out['context_reduction'])


if __name__=='__main__':unittest.main()
