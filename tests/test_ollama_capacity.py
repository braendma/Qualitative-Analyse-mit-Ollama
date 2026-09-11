import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import ollama_capacity as c


class CapacityTests(unittest.TestCase):
    def setUp(self):
        self.tag={'name':'test:latest','size':4*c.GIB,'digest':'abc'}
        self.show={'model_info':{'general.architecture':'llama','llama.block_count':32,
            'llama.embedding_length':4096,'llama.attention.head_count':32,
            'llama.attention.head_count_kv':8,'llama.context_length':32768}}
        self.machine={'gpus':[{'name':'Test GPU','total_bytes':16*c.GIB,'free_bytes':14*c.GIB}],
            'ram_available_bytes':32*c.GIB}

    def estimate(self, context=16384, running=None):
        return c.estimate('test:latest',context,self.tag,self.show,running or {'models':[]},self.machine)

    def test_formula_and_context_reduce_parallelism(self):
        self.assertEqual(c.kv_bytes_per_token(self.show['model_info']),131072)
        self.assertEqual(self.estimate()['estimated_parallel'],3)
        self.assertEqual(self.estimate(32768)['estimated_parallel'],1)

    def test_other_gpu_load_is_not_reclaimed(self):
        self.machine['gpus'][0]['free_bytes']=3*c.GIB
        self.assertEqual(self.estimate()['estimated_parallel'],0)

    def test_loaded_model_is_not_double_counted_or_unloaded(self):
        result=self.estimate(running={'models':[{'digest':'abc','size_vram':7*c.GIB}]})
        self.assertIsNone(result['estimated_parallel']);self.assertTrue(result['loaded'])

    def test_unknown_and_hybrid_architectures_do_not_guess(self):
        self.show['model_info']['general.architecture']='granitehybrid'
        self.assertIsNone(self.estimate()['estimated_parallel'])

    def test_missing_metadata_no_gpu_and_oversized_context(self):
        self.assertIsNone(self.estimate(65536)['estimated_parallel'])
        del self.show['model_info']['llama.attention.head_count_kv']
        self.assertIsNone(self.estimate()['estimated_parallel'])
        self.machine['gpus']=[]
        self.assertIsNone(self.estimate()['estimated_parallel'])

    def test_queries_are_read_only_and_latest_alias_resolves(self):
        calls=[]
        def metadata(endpoint, body=None):
            calls.append((endpoint,body))
            return {'tags':{'models':[self.tag]},'ps':{'models':[]},'show':self.show}[endpoint]
        with patch.object(c,'metadata',side_effect=metadata),patch.object(c,'hardware',return_value=self.machine):
            result=c.check({'provider':'ollama_local','model':'test','num_ctx':16384})
        self.assertEqual([v[0] for v in calls],['tags','show','ps'])
        self.assertEqual(result['model_calls'],0)
        self.assertEqual(result['estimated_parallel'],3)

    def test_cloud_invalid_context_and_remote_model_rejected_before_show(self):
        for values in ({'provider':'openai','gdpr_relevant':False,'model':'test','num_ctx':4096},
                       {'model':'test','num_ctx':True}, {'model':'test','num_ctx':0}):
            with patch.object(c,'metadata') as read:
                with self.assertRaises(ValueError):c.check(values)
                read.assert_not_called()
        with patch.object(c,'metadata',return_value={'models':[{**self.tag,'remote_host':'cloud'}]}) as read:
            with self.assertRaises(ValueError):c.check({'model':'test','num_ctx':4096})
            self.assertEqual(read.call_count,1)

    def test_metadata_rejects_inference_endpoints(self):
        with self.assertRaises(ValueError):c.metadata('chat',{})

if __name__=='__main__':unittest.main()
