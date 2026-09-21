"""Offline CPU Sortformer. v2: CC-BY-4.0; v1: noncommercial research only."""
import argparse
import json
import os
from pathlib import Path
import socket
import time

os.environ.update(HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audio', type=Path)
    parser.add_argument('--model-dir', type=Path, required=True)
    parser.add_argument('--backend', choices=['v1','v2','v2.1'], default='v2')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--transcript', type=Path)
    parser.add_argument('--reference-turns', type=Path)
    parser.add_argument('--context', choices=['high','full'], default='high')
    parser.add_argument('--threads', type=int, choices=[1, 2], default=2)
    parser.add_argument('--max-seconds', type=float)
    args = parser.parse_args()
    if args.max_seconds is None: args.max_seconds = 180 if args.backend == 'v1' else 7200
    if args.output.exists(): parser.error('Choose a new output directory; previous evidence is protected.')
    if not 0 < args.max_seconds <= 7200: parser.error('Maximum audio duration is 120 minutes.')
    if args.backend == 'v1' and args.max_seconds > 180: parser.error('The offline v1 backend is limited to 180 seconds; use streaming v2 for long recordings.')
    from download_diarization_model import digest, FILENAME, SHA256
    if args.backend != 'v1':
        from sortformer_streaming import FILENAME, SHA256
        if args.backend == 'v2.1':
            FILENAME='diar_streaming_sortformer_4spk-v2.1.onnx'
            SHA256='f010a62654fd6d2adb70166265df2e53f5a766e354d2cce152b4c7966a04d02d'
    from transcribe_local import deny_network, write_json
    from diarization_core import probability_turns, align_word, placement_metrics
    model = args.model_dir / FILENAME
    if digest(model) != SHA256: parser.error('Model checksum mismatch.')
    if args.audio.stat().st_size > 2 * 1024 * 1024 * 1024: parser.error('Audio exceeds 2 GiB.')
    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    socket.create_connection = deny_network
    import av
    import numpy as np
    import onnxruntime as ort
    from sortformer_features import extract_features, decoded_audio_file
    with av.open(str(args.audio)) as container:
        if not container.streams.audio or container.duration is None or container.duration / av.time_base > args.max_seconds:
            parser.error('Audio duration unknown or exceeds the configured duration limit.')
    with decoded_audio_file(args.audio, args.max_seconds) as audio:
        duration = len(audio) / 16000
        if not 0 < duration <= args.max_seconds: parser.error('Invalid decoded audio duration.')
        args.output.mkdir(parents=True)
        started = time.monotonic()
        run = {'status': 'running', 'backend': 'sortformer_'+args.backend+'_onnx', 'device': 'cpu', 'threads': args.threads,
            'audio_sha256': digest(args.audio), 'model_sha256': SHA256, 'source_sha256': digest(Path(__file__)),
            'features_source_sha256': digest(Path(__file__).with_name('sortformer_features.py')),
            'core_source_sha256': digest(Path(__file__).with_name('diarization_core.py')),
            'streaming_context': args.context, 'duration_seconds': duration, 'license': {'v1':'CC-BY-NC-4.0','v2':'CC-BY-4.0','v2.1':'nvidia-open-model-license'}[args.backend], 'max_speakers': 4,
            'person_mapping_confirmed': False, 'onnxruntime': ort.__version__, 'numpy': np.__version__}
        if args.backend != 'v1':
            run['streaming_source_sha256']=digest(Path(__file__).with_name('sortformer_streaming.py'))
        write_json(args.output / 'run.json', run)
        try:
            options = ort.SessionOptions()
            options.intra_op_num_threads = args.threads
            options.inter_op_num_threads = 1
            options.log_severity_level = 3
            session = ort.InferenceSession(str(model), options, providers=['CPUExecutionProvider'])
            if session.get_providers() != ['CPUExecutionProvider']:
                raise ValueError('CPU provider required.')
            if args.backend != 'v1':
                from sortformer_streaming import predict
                predictions = predict(session, audio, lambda seconds: write_json(args.output/'progress.json', {'processed_seconds': seconds, 'streaming_context': args.context, 'duration_seconds': duration}), context=args.context)
            else:
                features, lengths = extract_features(audio)
                predictions = session.run(['speaker_predictions'], {'mel_features': features, 'mel_lengths': lengths})[0][0]
            if predictions.ndim != 2 or predictions.shape[1] != 4 or not np.isfinite(predictions).all() or ((predictions < 0) | (predictions > 1)).any():
                raise ValueError('Invalid model predictions.')
            predictions = predictions[:int(np.ceil(duration / .08))]
            turns = probability_turns(predictions, duration)
            np.save(args.output / 'activity_scores.npy', predictions, allow_pickle=False)
            result = {'schema': 1, 'kind': 'speaker_suggestions', 'audio_sha256': run['audio_sha256'],
                'duration': duration, 'turns': turns, 'person_mapping_confirmed': False,
                'note': 'Speaker labels are recording-local suggestions, not identified people. Short, boundary and overlap words remain unknown.'}
            if args.transcript:
                transcript = json.loads(args.transcript.read_text(encoding='utf-8-sig'))
                # ASR source must be tied to this same audio by its completed run manifest.
                asr_run = json.loads(args.transcript.with_name('run.json').read_text(encoding='utf-8-sig'))
                if asr_run.get('status') != 'completed' or asr_run.get('identity', {}).get('audio_sha256') != run['audio_sha256'] or asr_run.get('outputs', {}).get(args.transcript.name) != digest(args.transcript):
                    raise ValueError('Transcript is not a verified completed ASR result for this audio.')
                result['transcript_sha256'] = digest(args.transcript)
                result['segments'] = []
                for segment in transcript['segments']:
                    words = [{**w, **align_word(w['start'], w['end'], turns)} for w in segment.get('words', [])]
                    result['segments'].append({**segment, 'speaker': None, 'words': words})
            write_json(args.output / 'speaker_suggestions.json', result)
            if args.reference_turns:
                reference = json.loads(args.reference_turns.read_text(encoding='utf-8-sig'))
                if isinstance(reference, dict): reference = reference.get('turns', reference.get('segments'))
                write_json(args.output / 'placement_evaluation.json', placement_metrics(reference, turns, duration))
            run.update(status='completed', elapsed_seconds=time.monotonic() - started, turns=len(turns),
                speakers=len({t['speaker'] for t in turns}), outputs={f.name: digest(f) for f in args.output.iterdir() if f.name != 'run.json'})
            write_json(args.output / 'run.json', run)
            print(json.dumps({k: run[k] for k in ['status', 'turns', 'speakers', 'elapsed_seconds']}, ensure_ascii=False))
        except BaseException as exc:
            run.update(status='failed', error_type=type(exc).__name__, error=str(exc)[:400], elapsed_seconds=time.monotonic()-started)
            write_json(args.output / 'run.json', run)
            raise


if __name__ == '__main__':
    main()
