"""NumPy inference frontend matching the published NeMo v1 feature settings.

References: NVIDIA-NeMo/Speech nemo/collections/asr/parts/preprocessing/features.py
and librosa Slaney mel scale. No upstream repository code is executed.
"""
import numpy as np
from functools import lru_cache
from contextlib import contextmanager
import tempfile
from pathlib import Path


@lru_cache(maxsize=2)
def mel_filterbank(n_mels=80):
    # Slaney: linear below 1 kHz, logarithmic above it; area-normalized triangles.
    min_log_mel = 15.0
    logstep = np.log(6.4) / 27.0
    max_mel = min_log_mel + np.log(8000.0 / 1000.0) / logstep
    mel = np.linspace(0, max_mel, n_mels + 2)
    hz = np.where(mel >= min_log_mel, 1000 * np.exp(logstep * (mel - min_log_mel)), mel * (200.0 / 3))
    frequencies = np.fft.rfftfreq(512, 1 / 16000)
    lower = (frequencies[None, :] - hz[:-2, None]) / (hz[1:-1] - hz[:-2])[:, None]
    upper = (hz[2:, None] - frequencies[None, :]) / (hz[2:] - hz[1:-1])[:, None]
    return (np.maximum(0, np.minimum(lower, upper)) * (2 / (hz[2:] - hz[:-2]))[:, None]).astype(np.float32)


def streaming_features(audio, start_frame, count):
    """Global 10 ms frame positions, bounded FFT buffer, unchanged pre-emphasis.

    Include the original sample before the window; never reset the filter or
    speaker cache at chunk boundaries. Padding occurs only at recording edges.
    """
    if audio.ndim != 1 or len(audio) < 320 or start_frame < 0 or count < 1:
        raise ValueError('Invalid streaming audio/frame range.')
    count = min(count, len(audio) // 160 + 1 - start_frame)
    if count <= 0:
        return np.empty((0, 128), dtype=np.float32)
    left = start_frame * 160 - 256
    right = (start_frame + count - 1) * 160 + 256
    begin, end = max(0, left), min(len(audio), right)
    samples = np.asarray(audio[max(0, begin - 1):end], dtype=np.float32)
    if not np.isfinite(samples).all():
        raise ValueError('Non-finite audio samples.')
    if begin:
        emphasized = samples[1:] - np.float32(.97) * samples[:-1]
    else:
        emphasized = np.concatenate((samples[:1], samples[1:] - np.float32(.97) * samples[:-1]))
    padded = np.pad(emphasized, (begin - left, right - end))
    frames = np.lib.stride_tricks.sliding_window_view(padded, 512)[::160]
    window = np.pad(np.hanning(400), (56, 56)).astype(np.float32)
    spectra = np.fft.rfft(frames * window, axis=1)
    power = (spectra.real ** 2 + spectra.imag ** 2).astype(np.float32)
    return np.log(mel_filterbank(128) @ power.T + np.float32(2 ** -24)).T.astype(np.float32)


def extract_features(audio, streaming=False):
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim != 1 or len(audio) < 320 or not np.isfinite(audio).all():
        raise ValueError('At least 20 ms of finite mono audio is required.')
    if not streaming:
        audio = audio / (np.max(np.abs(audio)) + 0.001)
    emphasized = np.concatenate((audio[:1], audio[1:] - np.float32(.97) * audio[:-1]))
    window = np.pad(np.hanning(400), (56, 56)).astype(np.float32)
    padded = np.pad(emphasized, (256, 256))
    frames = np.lib.stride_tricks.sliding_window_view(padded, 512)[::160]
    spectra = np.fft.rfft(frames * window, axis=1)
    power = (spectra.real ** 2 + spectra.imag ** 2).astype(np.float32)
    features = np.log(mel_filterbank(128 if streaming else 80) @ power.T + np.float32(2 ** -24))
    if streaming:
        return features.T[None].astype(np.float32)
    valid = len(audio) // 160
    mean = features[:, :valid].mean(axis=1, keepdims=True)
    std = features[:, :valid].std(axis=1, ddof=1, keepdims=True) + 1e-5
    features = (features - mean) / std
    features[:, valid:] = 0
    features = np.pad(features, ((0, 0), (0, (-features.shape[1]) % 16)))
    if not np.isfinite(features).all():
        raise ValueError('Non-finite audio features.')
    return features[None].astype(np.float32), np.array([valid], dtype=np.int64)


@contextmanager
def decoded_audio_file(path, max_seconds=7200):
    """Decode sequentially into temporary disk storage, avoiding full-audio RAM copies."""
    import av
    with tempfile.TemporaryDirectory(prefix='qa-speaker-audio-') as temporary:
        target = Path(temporary) / 'mono.f32'
        count = 0
        with target.open('wb') as output, av.open(str(path)) as container:
            resampler = av.AudioResampler(format='flt', layout='mono', rate=16000)
            def append(frame):
                nonlocal count
                values = frame.to_ndarray().reshape(-1).astype(np.float32, copy=False)
                count += len(values)
                if count > int(max_seconds * 16000):
                    raise ValueError('Decoded audio exceeds the configured duration limit.')
                if not np.isfinite(values).all():
                    raise ValueError('Non-finite decoded audio.')
                output.write(values.tobytes())
            for frame in container.decode(audio=0):
                for converted in resampler.resample(frame):
                    append(converted)
            for converted in resampler.resample(None):
                append(converted)
        if count < 320:
            raise ValueError('At least 20 ms of audio is required.')
        audio = np.memmap(target, dtype=np.float32, mode='r', shape=(count,))
        try:
            yield audio
        finally:
            audio._mmap.close()
