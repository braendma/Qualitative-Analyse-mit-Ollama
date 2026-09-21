import unittest,tempfile,wave,json,sys,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"src"))
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from sortformer_features import extract_features,streaming_features,decoded_audio_file
from sortformer_streaming import predict

class LongSpeakerTests(unittest.TestCase):
 def test_features_match_previous_frontend_at_recording_and_chunk_edges(self):
  rng=np.random.default_rng(61)
  for length in (320,321,16000,16003,320003):
   audio=(rng.normal(size=length)*.12).astype(np.float32);expected=extract_features(audio,streaming=True)[0]
   actual=np.concatenate([streaming_features(audio,start,1000) for start in range(0,len(expected),1000)])
   np.testing.assert_allclose(actual,expected,rtol=2e-6,atol=2e-5)
  invalid=np.zeros(16000,np.float32);invalid[400]=np.nan
  with self.assertRaises(ValueError):streaming_features(invalid,0,100)
 def test_decoder_duration_cap_and_cleanup(self):
  with tempfile.TemporaryDirectory() as temp:
   source=Path(temp)/'a.wav';values=np.arange(16000,dtype=np.int16)
   with wave.open(str(source),'wb') as out:out.setnchannels(1);out.setsampwidth(2);out.setframerate(16000);out.writeframes(values.tobytes())
   with decoded_audio_file(source,1) as audio:
    target=Path(audio.filename);self.assertEqual(len(audio),16000);np.testing.assert_allclose(audio,values.astype(np.float32)/32768,atol=1e-7)
   self.assertFalse(target.exists())
   with self.assertRaisesRegex(ValueError,'duration limit'):
    with decoded_audio_file(source,.5):pass
 def test_full_120_minute_timeline_preserves_one_cache_and_bounds(self):
  class Session:
   calls=0;last_cache=0
   def get_modelmeta(self):return SimpleNamespace(custom_metadata_map={})
   def get_outputs(self):return [SimpleNamespace(name=n) for n in ('spkcache_fifo_chunk_preds','chunk_pre_encode_embs')]
   def run(self,names,inputs):
    self.calls+=1;cache=int(inputs['spkcache_lengths'][0]);fifo=int(inputs['fifo_lengths'][0]);self.assertions(cache,fifo)
    p=np.zeros((1,cache+fifo+125,4),np.float32);p[:,:,0]=.9
    return [p,np.ones((1,125,512),np.float32)]
   def assertions(self,cache,fifo):
    assert cache<=188 and fifo<=124
    if self.calls>2:assert cache>0 and fifo>0
  audio=SimpleNamespace(__len__=lambda:115200000)
  class Audio:
   def __len__(self):return 7200*16000
  visited=[]
  def features(audio,start,count):
   visited.append(start);return np.zeros((min(count,len(audio)//160+1-start),128),np.float32)
  progress=[];session=Session()
  with patch('sortformer_streaming.streaming_features',side_effect=features):result=predict(session,Audio(),progress.append,context='high')
  self.assertEqual(result.shape,(90001,4));self.assertEqual(progress[-1],7200);self.assertTrue(all(a<=b for a,b in zip(progress,progress[1:])));self.assertEqual(visited,list(range(0,720001,992)));self.assertGreater(session.calls,700)
 def test_pipeline_allows_long_audio_and_preserves_asr_on_speaker_failure(self):
  import transcription_pipeline as pipeline
  for duration,failed in ((181,False),(7200,False),(7200,True)):
   with tempfile.TemporaryDirectory() as temp:
    d=Path(temp);out=d/'asr';out.mkdir();(out/'run.json').write_text(json.dumps({'duration_seconds':duration,'segments':1}));model=d/'model';model.mkdir();(model/'diar_streaming_sortformer_4spk-v2.onnx').write_bytes(b'fixture')
    commands=[]
    def child(command,**kwargs):commands.append(command);return SimpleNamespace(poll=lambda:0,returncode=1 if failed and len(commands)==2 else 0)
    argv=['pipeline','--audio',str(d/'fixture.wav'),'--output',str(out),'--model-dir',str(model),'--speaker-model-dir',str(model)]
    with patch.object(sys,'argv',argv),patch.object(pipeline,'os',SimpleNamespace(name='posix',getpid=os.getpid)),patch.object(pipeline.subprocess,'Popen',side_effect=child):pipeline.main()
    self.assertEqual(len(commands),2);self.assertIn('diarize_sortformer.py',' '.join(commands[1]));self.assertEqual(json.loads((d/'asr_UI_Job.json').read_text())['phase'],'completed')
    if failed:self.assertIn('fehlgeschlagen',json.loads((d/'asr_UI_Job.json').read_text())['speaker_warning'])

 def test_central_speaker_install_reuse_failure_and_family_separation(self):
  import audio_models as library
  from sortformer_streaming import FILENAME,SHA256
  import time
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);model=root/'sortformer-v2-onnx';model.mkdir();(model/FILENAME).write_bytes(b'test-model')
   (model/'diarization_model_manifest.json').write_text(json.dumps({'filename':FILENAME,'sha256':SHA256,'backend':'sortformer_v2_onnx','repository':'altunenes/parakeet-rs'}))
   manager=library.AudioModels(root)
   with patch('download_diarization_model.digest',return_value=SHA256),patch('audio_models.subprocess.Popen',side_effect=AssertionError('No repeated download')):
    manager.start('sortformer-v2-onnx',True)
    for _ in range(200):
     if not manager.busy:break
     import time;time.sleep(.01)
    self.assertEqual(manager.state()['job']['status'],'completed')
   with self.assertRaises(ValueError):library.library_model('sortformer-v2-onnx',model,True)
   (model/'diarization_model_manifest.json').write_text(json.dumps({'filename':'../outside','sha256':SHA256,'backend':'sortformer_v2_onnx','repository':'altunenes/parakeet-rs'}))
   with self.assertRaises(ValueError):library.library_model('sortformer-v2-onnx',model)
  with tempfile.TemporaryDirectory() as temp:
   manager=library.AudioModels(Path(temp)/'library')
   class Child:
    returncode=1
    def poll(self):return 1
   with patch('audio_models.subprocess.Popen',return_value=Child()) as child:
    manager.start('sortformer-v2-onnx',True)
    for _ in range(200):
     if not manager.busy:break
     time.sleep(.01)
    self.assertEqual(manager.state()['job']['status'],'failed');self.assertFalse((manager.root/'sortformer-v2-onnx').exists())
    self.assertIn('download_diarization_model.py',' '.join(child.call_args.args[0]));self.assertIn('v2',child.call_args.args[0])

if __name__=='__main__':unittest.main()
