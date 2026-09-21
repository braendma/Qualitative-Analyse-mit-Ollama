"""Bounded NumPy/ORT Sortformer v2 cache adapter.

Algorithm reference: NVIDIA Sortformer AOSC, and altunenes/parakeet-rs
src/sortformer.rs (MIT, copyright Enes Altun). Source and license in research/.
This is a local implementation, not execution of downloaded repository scripts.
"""
import numpy as np
from sortformer_features import streaming_features

FILENAME = 'diar_streaming_sortformer_4spk-v2.onnx'
SHA256 = 'cc520901a8cc25a8d7f7c2c8561a465709b67dd4f1df0572a97530087f3fbc73'


def compress_cache(embeddings, probabilities, silence_mean, limit=188):
    """Retain high-quality speaker frames and silence placeholders in stable order."""
    p = np.maximum(probabilities, .25)
    log_other = np.log(np.maximum(1 - p, .25))
    scores = np.log(p) - log_other + log_other.sum(axis=1, keepdims=True) - np.log(.5)
    positive = (scores > 0).sum(axis=0)
    minimum = int((limit // 4 - 3) * .5)
    scores[(probabilities <= .5) | ((scores <= 0) & (positive >= minimum)[None, :])] = -np.inf
    for count, boost in [(int((limit // 4 - 3) * .75), 2.), (int((limit // 4 - 3) * 1.5), 1.)]:
        for speaker in range(4):
            indices = np.argsort(-scores[:, speaker], kind='stable')[:count]
            scores[indices, speaker] -= boost * np.log(.5)
    n = len(scores)
    scores = np.concatenate((scores, np.full((3, 4), np.inf)))
    flattened = scores.T.reshape(-1)
    selected = np.argsort(-flattened, kind='stable')[:limit]
    selected = np.sort(np.where(np.isneginf(flattened[selected]), 99999, selected))
    indices = selected % len(scores)
    disabled = (selected == 99999) | (indices >= n)
    new_embeddings = np.repeat(silence_mean[None], len(selected), axis=0)
    new_probabilities = np.zeros((len(selected), 4), dtype=np.float32)
    new_embeddings[~disabled] = embeddings[indices[~disabled]]
    new_probabilities[~disabled] = probabilities[indices[~disabled]]
    return new_embeddings.astype(np.float32), new_probabilities


def predict(session, audio, progress=None, context="full"):
    frame_count = len(audio) // 160 + 1
    metadata = session.get_modelmeta().custom_metadata_map
    chunk_len = int(metadata.get('chunk_len', 124))
    fifo_limit = int(metadata.get('fifo_len', 124))
    cache_limit = int(metadata.get('spkcache_len', 188))
    right = int(metadata.get('right_context', 1))
    if (chunk_len, fifo_limit, cache_limit, right) != (124, 124, 188, 1):
        raise ValueError('Unexpected ONNX streaming configuration; validate this model separately.')
    if context == 'full':
        # NVIDIA's published 30.4-second profile suits a saved-file workflow.
        chunk_len, fifo_limit, cache_limit, right = 340, 40, 188, 40
    elif context != 'high':
        raise ValueError('Unknown context profile.')
    cache = np.zeros((0, 512), dtype=np.float32)
    cache_probs = np.zeros((0, 4), dtype=np.float32)
    fifo = cache.copy()
    silence_sum = np.zeros(512, dtype=np.float64)
    silence_frames = 0
    collected = []
    feed = (chunk_len + right) * 8
    for start in range(0, frame_count, chunk_len * 8):
        chunk = streaming_features(audio, start, feed)
        valid = len(chunk)
        if valid < feed:
            chunk = np.pad(chunk, ((0, feed-valid), (0, 0)))
        cache_size, fifo_size = len(cache), len(fifo)
        outputs = session.run(None, {'chunk': chunk[None], 'chunk_lengths': np.array([valid], np.int64),
            'spkcache': cache[None], 'spkcache_lengths': np.array([cache_size], np.int64),
            'fifo': fifo[None], 'fifo_lengths': np.array([fifo_size], np.int64)})
        values = dict(zip([x.name for x in session.get_outputs()], outputs))
        all_probs = values['spkcache_fifo_chunk_preds'][0]
        embeddings = values['chunk_pre_encode_embs'][0]
        keep = min(chunk_len, (valid + 7) // 8)
        new_probs = all_probs[cache_size + fifo_size:cache_size + fifo_size + keep]
        if len(new_probs) != keep:
            raise ValueError('Unexpected streaming output length.')
        collected.append(new_probs)
        fifo = np.concatenate((fifo, embeddings[:keep]))
        fifo_probs = np.concatenate((all_probs[cache_size:cache_size + fifo_size], new_probs))
        if len(fifo) > fifo_limit:
            pop = len(fifo) - fifo_limit
            old_embeddings, old_probs = fifo[:pop], fifo_probs[:pop]
            silent = old_probs.sum(axis=1) < .2
            silence_sum += old_embeddings[silent].sum(axis=0)
            silence_frames += int(silent.sum())
            fifo = fifo[pop:]
            cache = np.concatenate((cache, old_embeddings))
            cache_probs = np.concatenate((all_probs[:cache_size], old_probs))
            if len(cache) > cache_limit:
                mean = (silence_sum / max(silence_frames, 1)).astype(np.float32)
                cache, cache_probs = compress_cache(cache, cache_probs, mean, cache_limit)
        if len(cache) > cache_limit or len(fifo) > fifo_limit:
            raise ValueError('Streaming memory bounds exceeded.')
        if progress:
            progress(min((start + chunk_len * 8) * .01, len(audio) / 16000))
    return np.concatenate(collected, axis=0)
