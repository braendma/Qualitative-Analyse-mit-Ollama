"""Explicit public ONNX download. v2: CC-BY-4.0; v1: CC-BY-NC; v2.1: NVIDIA license."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import ssl

os.environ.update(HF_HUB_DISABLE_IMPLICIT_TOKEN='1', HF_HUB_DISABLE_TELEMETRY='1', HF_HUB_DISABLE_XET='1')
REPOSITORY = 'altunenes/parakeet-rs'
REVISION = 'a61d2818df4659c956b9661a9447f46e98c15126'
FILENAME = 'diar_sortformer_4spk-v1.onnx'
SHA256 = 'bfa06abe734c6813cc691473b3dcdbc6a2411ba58dceef82b0613a7aacfacff0'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--model', choices=['v1','v2','v2.1'], default='v2')
    args = parser.parse_args()
    global FILENAME, SHA256
    if args.model == 'v2':
        FILENAME='diar_streaming_sortformer_4spk-v2.onnx'
        SHA256='cc520901a8cc25a8d7f7c2c8561a465709b67dd4f1df0572a97530087f3fbc73'
    if args.model == 'v2.1':
        FILENAME='diar_streaming_sortformer_4spk-v2.1.onnx'
        SHA256='f010a62654fd6d2adb70166265df2e53f5a766e354d2cce152b4c7966a04d02d'
    path = args.directory / FILENAME
    existing = path.exists()
    if existing and digest(path) != SHA256:
        parser.error('Existing model hash differs; choose a new model directory.')
    if not existing:
        from huggingface_hub import hf_hub_download, set_client_factory
        import httpx
        set_client_factory(lambda: httpx.Client(verify=ssl.create_default_context(), follow_redirects=True))
        args.directory.mkdir(parents=True, exist_ok=True)
        hf_hub_download(REPOSITORY, FILENAME, revision=REVISION, token=False, local_dir=args.directory)
    if digest(path) != SHA256:
        raise ValueError('Downloaded model SHA256 differs from the published LFS checksum.')
    manifest = {'schema': 1, 'backend': 'sortformer_'+args.model+'_onnx', 'repository': REPOSITORY,
        'revision': REVISION, 'filename': FILENAME, 'sha256': SHA256, 'bytes': path.stat().st_size,
        'original_model': 'nvidia/diar_sortformer_4spk-v1' if args.model=='v1' else 'nvidia/diar_streaming_sortformer_4spk-v2', 'license': 'CC-BY-NC-4.0' if args.model=='v1' else 'CC-BY-4.0',
        'license_url': 'https://creativecommons.org/licenses/by-nc/4.0/' if args.model=='v1' else 'https://creativecommons.org/licenses/by/4.0/',
        'original_model_url': 'https://huggingface.co/nvidia/diar_sortformer_4spk-v1' if args.model=='v1' else 'https://huggingface.co/nvidia/diar_streaming_sortformer_4spk-v2',
        'conversion_author': 'altunenes', 'max_speakers': 4, 'token_used': False,
        'note': 'Third-party ONNX conversion; original NVIDIA model license applies. v1 is noncommercial only.'}
    if args.model == 'v2.1':
        manifest.update(original_model='nvidia/diar_streaming_sortformer_4spk-v2.1', original_model_url='https://huggingface.co/nvidia/diar_streaming_sortformer_4spk-v2.1', license='nvidia-open-model-license', license_url='https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/')
    (args.directory / 'diarization_model_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({'status': 'existing_verified' if existing else 'downloaded_verified', 'bytes': manifest['bytes'], 'sha256': SHA256}))


if __name__ == '__main__':
    main()
