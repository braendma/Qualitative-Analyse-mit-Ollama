"""Local-only bounded transcription prototype. CPU is the explicit default."""
import argparse
import datetime
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import socket
import sys
import time
import unicodedata
import re

os.environ.update(HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
                  HF_HUB_DISABLE_IMPLICIT_TOKEN='1', OMP_NUM_THREADS='2')
ROOT = Path(__file__).resolve().parent


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, data):
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


def timestamp(seconds, separator=','):
    value = round(seconds * 1000)
    hours, value = divmod(value, 3600000)
    minutes, value = divmod(value, 60000)
    secs, millis = divmod(value, 1000)
    return f'{hours:02}:{minutes:02}:{secs:02}{separator}{millis:03}'


def words(text):
    return re.findall(r'\w+', unicodedata.normalize('NFKC', text).casefold())


def error_rate(reference, hypothesis):
    a, b = words(reference), words(hypothesis)
    previous = list(range(len(b) + 1))
    for i, left in enumerate(a, 1):
        current = [i]
        for j, right in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[-1] + 1, previous[j-1] + (left != right)))
        previous = current
    distance = previous[-1]
    return {'reference_words': len(a), 'hypothesis_words': len(b), 'edit_distance': distance,
            'normalized_word_error_rate': distance / len(a) if a else None,
            'normalization': 'NFKC, casefold, unicode word tokens; punctuation ignored; numbers not expanded'}


def deny_network(*args, **kwargs):
    raise RuntimeError('Network access is disabled during local transcription')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('audio', type=Path)
    p.add_argument('--model-dir', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    p.add_argument('--compute-type', choices=['int8', 'float16', 'int8_float16'], default='int8')
    p.add_argument('--threads', type=int, default=2)
    p.add_argument('--beam-size', type=int, default=3)
    p.add_argument('--language', default='de')
    p.add_argument('--reference', type=Path)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--max-seconds', type=float, default=7200)
    a = p.parse_args()
    if not 1 <= a.threads <= 8 or not 1 <= a.beam_size <= 10 or not 0 < a.max_seconds <= 7200:
        p.error('Threads 1..8, beam size 1..10, duration at most 7200 seconds')
    model_dir = a.model_dir.resolve(strict=True)
    model_manifest = model_dir / 'model_manifest.json'
    inventory = json.loads(model_manifest.read_text(encoding='utf-8'))
    for name, entry in inventory['files'].items():
        path = model_dir / name
        if Path(name).name != name or digest(path) != entry['sha256']:
            p.error('Local model files changed; run download_models.py again to check')
    audio = a.audio.resolve(strict=True)
    if audio.stat().st_size > 2 * 1024 * 1024 * 1024:
        p.error('Audio exceeds the 2 GiB prototype limit')
    versions = {n: importlib.metadata.version(n) for n in ('faster-whisper', 'ctranslate2', 'av', 'onnxruntime')}
    identity = {'audio_sha256': digest(audio), 'model_manifest_sha256': digest(model_manifest),
                'source_sha256': digest(Path(__file__)), 'versions': versions,
                'reference_sha256': digest(a.reference) if a.reference else None,
                'parameters': {'device': a.device, 'compute_type': a.compute_type,
                    'threads': a.threads, 'beam_size': a.beam_size, 'language': a.language,
                    'vad_filter': True, 'word_timestamps': True, 'temperature': 0.0,
                    'condition_on_previous_text': False, 'max_seconds': a.max_seconds}}
    output = a.output.resolve()
    if output.exists():
        previous_file = output / 'run.json'
        if not a.resume or not previous_file.is_file():
            p.error('Output exists; choose a new directory or --resume for an identical run')
        previous = json.loads(previous_file.read_text(encoding='utf-8'))
        if previous.get('identity') != identity:
            p.error('Audio, model, settings or code changed; use a new output directory')
        if previous.get('status') == 'completed':
            if not all((output / n).is_file() and digest(output / n) == h
                       for n, h in previous.get('outputs', {}).items()) or not previous.get('outputs'):
                p.error('Completed output changed; use a new output directory')
            print(json.dumps({'status': 'verified_reuse', 'output': str(output)}))
            return 0
        history = previous.get('attempt_history', []) + [{'status': previous.get('status'), 'started_at': previous.get('started_at')}]
    else:
        output.mkdir(parents=True)
        history = []
    run = {'schema': 1, 'status': 'running', 'identity': identity,
           'attempt_history': history, 'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'network_guard': 'Python socket connections blocked; local model path and offline flags',
           'limitations': ['No speaker diarization', 'No human-verified transcription',
                           'Interrupted runs restart entire file, partials never concatenated',
                           'Audio capped at 120 minutes; decoded audio held in memory']}
    write_json(output / 'run.json', run)
    started = time.monotonic()
    try:
        socket.socket.connect = deny_network
        socket.socket.connect_ex = deny_network
        socket.create_connection = deny_network
        from faster_whisper import WhisperModel
        from faster_whisper.audio import decode_audio
        import av
        with av.open(str(audio)) as container:
            if not container.streams.audio:
                raise ValueError('File has no audio stream')
            if container.duration is None or container.duration / av.time_base > a.max_seconds:
                raise ValueError('Duration is unknown or exceeds the prototype limit')
        waveform = decode_audio(str(audio), sampling_rate=16000)
        duration = len(waveform) / 16000
        if duration <= 0 or duration > a.max_seconds:
            raise ValueError('Empty audio or duration exceeds the prototype limit')
        run['duration_seconds'] = duration
        write_json(output / 'progress.json', {'phase': 'model_loading', 'audio_seconds': duration})
        model = WhisperModel(str(model_dir), device=a.device, compute_type=a.compute_type,
                             cpu_threads=a.threads, num_workers=1, local_files_only=True)
        segments, info = model.transcribe(waveform, language=a.language, task='transcribe',
            beam_size=a.beam_size, vad_filter=True, word_timestamps=True, temperature=0.0,
            condition_on_previous_text=False)
        collected = []
        with (output / 'segments.partial.jsonl').open('w', encoding='utf-8') as partial:
            for seg in segments:
                if not (math.isfinite(seg.start) and math.isfinite(seg.end)
                        and 0 <= seg.start <= seg.end <= duration + .5):
                    raise ValueError('Invalid timestamp returned')
                value = {'id': len(collected) + 1, 'start': seg.start, 'end': seg.end,
                         'text': seg.text.strip(), 'speaker': None,
                         'avg_logprob': seg.avg_logprob, 'no_speech_prob': seg.no_speech_prob,
                         'words': [{'start': w.start, 'end': w.end, 'word': w.word,
                                    'probability': w.probability} for w in seg.words or []]}
                collected.append(value)
                partial.write(json.dumps(value, ensure_ascii=False) + '\n'); partial.flush()
                write_json(output / 'progress.json', {'phase': 'transcription',
                    'processed_seconds': min(seg.end, duration), 'audio_seconds': duration,
                    'segments': len(collected)})
        text = ' '.join(s['text'] for s in collected).strip()
        write_json(output / 'transcript.json', {'language': info.language, 'duration': duration, 'segments': collected})
        (output / 'transcript.txt').write_text(text + '\n', encoding='utf-8')
        for suffix, sep, header in [('srt', ',', ''), ('vtt', '.', 'WEBVTT\n\n')]:
            body = ''.join(f"{s['id']}\n{timestamp(s['start'], sep)} --> {timestamp(s['end'], sep)}\n{s['text']}\n\n" for s in collected)
            (output / ('transcript.' + suffix)).write_text(header + body, encoding='utf-8')
        names = ['transcript.json', 'transcript.txt', 'transcript.srt', 'transcript.vtt']
        if a.reference:
            write_json(output / 'evaluation.json', error_rate(a.reference.read_text(encoding='utf-8-sig'), text))
            names.append('evaluation.json')
        run.update(status='completed', elapsed_seconds=time.monotonic() - started,
                   outputs={n: digest(output / n) for n in names}, segments=len(collected))
        write_json(output / 'run.json', run)
        write_json(output / 'progress.json', {'phase': 'completed', 'processed_seconds': duration, 'audio_seconds': duration})
        print(json.dumps({'status': run['status'], 'segments': len(collected), 'elapsed_seconds': run['elapsed_seconds']}))
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        run.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed',
                   error_type=type(exc).__name__, elapsed_seconds=time.monotonic() - started,
                   error=str(exc)[:500])
        write_json(output / 'run.json', run)
        write_json(output / 'progress.json', {'phase': run['status'], 'error_type': run['error_type']})
        print(json.dumps({'status': run['status'], 'error_type': run['error_type'], 'error': run['error']}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
