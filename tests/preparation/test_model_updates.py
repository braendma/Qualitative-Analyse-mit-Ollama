import json
from pathlib import Path
import tempfile
import unittest
from model_updates import ModelUpdates


class ModelUpdateTests(unittest.TestCase):
    def test_offline_default_daily_cache_and_no_model_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);directory=root/'models/large-v3';directory.mkdir(parents=True)
            manifest=directory/'model_manifest.json'
            manifest.write_text(json.dumps({'repository':'Systran/faster-whisper-large-v3','revision':'a'*40}))
            original=manifest.read_bytes();calls=[];clock=[100000]
            def fetch():
                calls.append(1)
                return [{'id':'Systran/faster-whisper-large-v3','sha':'b'*40}, {'id':'Systran/faster-whisper-large-v99','sha':'c'*40}, {'id':'evil/faster-whisper-test','sha':'a'*40}]
            checker=ModelUpdates(root/'models',root/'settings.json',fetch,lambda:clock[0])
            checker.check();self.assertEqual(calls,[])
            checker.preference(True);result=checker.check()
            self.assertEqual(len(calls),1);self.assertEqual(len(result['models']),2)
            self.assertEqual(result['models'][0]['status'],'revision_available')
            self.assertFalse(result['models'][1]['tested_family'])
            checker.check();self.assertEqual(len(calls),1)
            clock[0]+=86401;checker.check();self.assertEqual(len(calls),2)
            self.assertEqual(manifest.read_bytes(),original)
            self.assertTrue(ModelUpdates(root/'models',root/'settings.json').state()['automatic'])

    def test_network_failure_retains_last_known_results(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);clock=[100000]
            def fetch():return [{'id':'Systran/faster-whisper-small','sha':'a'*40}]
            checker=ModelUpdates(root,root/'settings.json',fetch,lambda:clock[0]);first=checker.check(manual=True)
            def offline():raise OSError('synthetic failure; no network')
            checker.fetch=offline;clock[0]+=61
            second=checker.check(manual=True)
            self.assertTrue(second['error']);self.assertEqual(second['models'],first['models'])
            self.assertEqual(second['checked_at'],first['checked_at'])


if __name__=='__main__':unittest.main()
