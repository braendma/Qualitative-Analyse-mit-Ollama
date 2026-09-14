import copy
from pathlib import Path
import tempfile
import unittest

from test_diagnostic_repetitions import Workspace
from diagnostic_sensitivity import prepare_sensitivity


class SensitivityPlanTests(unittest.TestCase):
    def test_isolated_variants_repeat_the_same_material_and_include_baseline_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp));before={p:p.read_bytes() for p in w.root.iterdir()}
            variants=[{'id':'warmer','llm':{'temperature':0.3}},
                      {'id':'other-model','llm':{'model':'synthetic-other'}}]
            plan=prepare_sensitivity(w.path,['blind_coding'],variants)
            self.assertEqual(plan['configuration_count'],3)
            self.assertEqual(plan['effective_modules'],['clusterer','blind_coding'])
            self.assertEqual(plan['module_executions'],12)
            self.assertIsNone(plan['model_calls'])
            self.assertEqual(len({s['sample_id'] for s in plan['samples']}),6)
            baseline,warm,other=plan['configurations']
            self.assertEqual(other['config']['llm']['temperature'],baseline['config']['llm']['temperature'])
            self.assertEqual(warm['config']['llm']['temperature'],0.3)
            for item in plan['configurations']:
                self.assertEqual(item['config']['paths'],baseline['config']['paths'])
                self.assertEqual(item['config']['columns'],baseline['config']['columns'])
                self.assertTrue(item['config']['_diagnostic_child'])
                self.assertFalse(item['context_preflight']['blocked'])
            self.assertEqual(prepare_sensitivity(w.path,['blind_coding'],variants),plan)
            self.assertEqual({p:p.read_bytes() for p in w.root.iterdir()},before)
            warm['config']['columns']['person']='changed-in-memory'
            self.assertNotEqual(warm['config']['columns'],baseline['config']['columns'])

    def test_rejects_unknown_private_recursive_and_noop_variants_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp));before={p:p.read_bytes() for p in w.root.iterdir()}
            bad=[{}, {'id':'../escape','llm':{'temperature':0.3}}, {'id':'baseline','llm':{'temperature':0.3}},
                 {'id':'empty'}, {'id':'noop','llm':{'temperature':0.05}},
                 {'id':'alias','llm':{'model':'mock:latest'}},
                 {'id':'sampling','llm':{'top_p':0.9}},
                 {'id':'secret','llm':{'api_key':'synthetic-not-a-key'}},
                 {'id':'cloud','llm':{'provider':'ollama_cloud'}},
                 {'id':'input','paths':{'input_csv':'elsewhere'}},
                 {'id':'cloud-model','llm':{'model':'synthetic:cloud'}},
                 {'id':'unknown','prompts':{'unused':{'system':'test'}}}]
            for variant in bad:
                with self.subTest(variant=variant),self.assertRaises(ValueError):
                    prepare_sensitivity(w.path,['blind_coding'],[variant])
            self.assertEqual({p:p.read_bytes() for p in w.root.iterdir()},before)

    def test_invalid_numbers_types_counts_and_duplicate_conditions(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp))
            for field,values in {'temperature':[True,-0.1,2.1,float('nan'),float('inf'),'0.2'],
                                 'num_ctx':[0,-1,True,4096.0], 'max_tokens':[0,True,65536],
                                 'think':['true',[],{},1], 'model':[None,True,' mock']}.items():
                for value in values:
                    with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                        prepare_sensitivity(w.path,['blind_coding'],[{'id':'bad','llm':{field:value}}])
            variant={'id':'warm','llm':{'temperature':0.2}}
            for variants in (None,[],[variant]*10,[variant,variant],
                             [variant,{'id':'same','llm':{'temperature':0.2}}]):
                with self.subTest(variants=variants),self.assertRaises(ValueError):
                    prepare_sensitivity(w.path,['blind_coding'],variants)
            for repetitions in (1,True,21,'2'):
                with self.subTest(repetitions=repetitions),self.assertRaises(ValueError):
                    prepare_sensitivity(w.path,['blind_coding'],[variant],repetitions=repetitions)

    def test_cloud_adapters_reject_ignored_parameters_and_keep_provider_fixed(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp))
            for provider in ('openai','anthropic','huggingface','ollama_cloud'):
                w.config['llm'].update(provider=provider,gdpr_relevant=False);w.save()
                keys=['num_ctx']+(['temperature','think'] if provider!='ollama_cloud' else [])
                for key in keys:
                    with self.subTest(provider=provider,key=key),self.assertRaises(ValueError):
                        prepare_sensitivity(w.path,['blind_coding'],[{'id':'ignored','llm':{key: {'num_ctx':32768,'temperature':0.2,'think':True}[key]}}])
                plan=prepare_sensitivity(w.path,['blind_coding'],[{'id':'other','llm':{'model':'synthetic-other'}}])
                self.assertEqual(plan['provider'],provider)
                self.assertFalse(plan['configurations'][1]['config']['llm']['gdpr_relevant'])

    def test_prompt_variant_retains_placeholders_and_rejects_ignored_multilabel_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp))
            original=w.config['prompts']['blind_coding']['user']
            variant={'id':'instruction','prompts':{'blind_coding':{'user':'Prüfe Gegenbelege.\n'+original}}}
            plan=prepare_sensitivity(w.path,['blind_coding'],[variant])
            change=plan['configurations'][1]['changes'][0]
            self.assertIn('after_sha256',change)
            self.assertNotIn('after',change)
            for text in (original+' ', '{segment}',original+' {unknown}',original+' {segment_id}'):
                invalid=copy.deepcopy(variant);invalid['prompts']['blind_coding']['user']=text
                with self.subTest(text=text),self.assertRaises(ValueError):
                    prepare_sensitivity(w.path,['blind_coding'],[invalid])
            w.config['coding_agreement']['label_mode']='multi_label';w.save()
            with self.assertRaisesRegex(ValueError,'nicht konfigurierbar'):
                prepare_sensitivity(w.path,['blind_coding'],[variant])

    def test_long_material_and_long_prompt_fail_preflight_without_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp))
            variant={'id':'large','prompts':{'blind_coding':{'system':'Zusätzliche Anleitung. '*9000}}}
            with self.assertRaisesRegex(ValueError,'large: Start gesperrt'):
                prepare_sensitivity(w.path,['blind_coding'],[variant])
            p=w.root/'input.csv';p.write_text('ID;Person;Code;Text\ns1;P1;A > B > C > positiv;'+('ü'*80000)+'\n',encoding='utf-8')
            original=p.read_bytes()
            with self.assertRaisesRegex(ValueError,'baseline: Start gesperrt'):
                prepare_sensitivity(w.path,['blind_coding'],[{'id':'warm','llm':{'temperature':0.2}}])
            self.assertEqual(p.read_bytes(),original)

    def test_multiple_changes_are_explicit_and_prompt_whitespace_duplicates_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Workspace(Path(tmp))
            plan=prepare_sensitivity(w.path,['blind_coding'],[{'id':'joint','llm':{'temperature':0.2,'think':True}}])
            self.assertTrue(plan['configurations'][1]['joint_changes'])
            variants=[{'id':'one','prompts':{'blind_coding':{'system':'Bitte genau prüfen.'}}},
                      {'id':'two','prompts':{'blind_coding':{'system':'Bitte  genau prüfen. '}}}]
            with self.assertRaisesRegex(ValueError,'Doppelte wirksame'):
                prepare_sensitivity(w.path,['blind_coding'],variants)


if __name__=='__main__':unittest.main()
