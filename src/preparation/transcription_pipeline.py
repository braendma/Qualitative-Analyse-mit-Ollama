"""Sequential CPU ASR then optional installed Sortformer; no downloads or GPU fallback."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
import llm_review as r
from workspace_store import atomic_write


def main():
    p=argparse.ArgumentParser();p.add_argument('--audio',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--model-dir',type=Path,required=True);p.add_argument('--speaker-model-dir',type=Path);a=p.parse_args()
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
    from process_commands import python_command
    supervisor=None
    if os.name=='nt':
        from windows_process_job import SupervisorJob
        supervisor=SupervisorJob()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    job=a.output.parent/(a.output.name+'_UI_Job.json')
    record={'pid':os.getpid(),'started_at':time.time(),'status':'started','phase':'asr'};atomic_write(job,record)
    base=Path(__file__).resolve().parent
    stop=a.output.parent/(a.output.name+'_stop.request')
    def run_owned(command,required=True):
        process=subprocess.Popen(command,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),start_new_session=(os.name!='nt'))
        while process.poll() is None:
            if stop.exists():
                if supervisor is not None:supervisor.stop_descendants()
                else:
                    import signal
                    os.killpg(process.pid,signal.SIGTERM)
                process.wait(timeout=15)
                raise InterruptedError('Audioverarbeitung auf Nutzerwunsch beendet; Teilresultate bleiben erhalten.')
            time.sleep(.2)
        if required and process.returncode:raise subprocess.CalledProcessError(process.returncode,command)
        return process.returncode
    try:
        run_owned(python_command(base/'transcribe_local.py',[str(a.audio),'--model-dir',str(a.model_dir),'--output',str(a.output),'--device','cpu','--threads','2']))
        run=r.read(a.output/'run.json')
        speaker_model=a.speaker_model_dir
        if speaker_model and (speaker_model/'diar_streaming_sortformer_4spk-v2.onnx').is_file() and run.get('duration_seconds',0)<=7200 and run.get('segments',0):
            record['phase']='diarization';atomic_write(job,record)
            result=run_owned(python_command(base/'diarize_sortformer.py',[str(a.audio),'--backend','v2','--context','high','--model-dir',str(speaker_model),'--output',str(a.output.parent/(a.output.name+'_Sprecher')),'--transcript',str(a.output/'transcript.json'),'--threads','2']),required=False)
            if result:record['speaker_warning']='Sprechererkennung fehlgeschlagen; ASR-Text bleibt ohne automatische Zuordnung verfügbar.'
        else:
            record['speaker_warning']='Keine lokale Sprechererkennung ausgeführt: v2-Modell fehlt, Audio länger als 120 Minuten oder kein ASR-Text. Sprecher bleiben unzugeordnet.'
        record.update(status='completed',phase='completed')
    except Exception as exc:record.update(status='failed',error=str(exc)[:500])
    if supervisor is not None:supervisor.stop_descendants()
    record['cleanup_confirmed']=True
    atomic_write(job,record)


if __name__=='__main__':main()
