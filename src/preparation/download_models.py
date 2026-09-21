"""Explicit public model download. Never reads an HF token or starts inference."""
import argparse
import hashlib
import json
import os
import ssl
from pathlib import Path

os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN'] = '1'
os.environ['HF_HUB_DISABLE_XET'] = '1'

MODELS = {'small': 'Systran/faster-whisper-small',
          'large-v3': 'Systran/faster-whisper-large-v3'}
FILES = {'config.json', 'model.bin', 'tokenizer.json', 'vocabulary.json',
         'vocabulary.txt', 'preprocessor_config.json', 'README.md', 'LICENSE'}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory', type=Path, required=True)
    p.add_argument('--model', choices=[*MODELS, 'all'], default='large-v3')
    a = p.parse_args()
    from huggingface_hub import HfApi, snapshot_download
    from huggingface_hub import set_client_factory
    import httpx
    # Use Windows/system trust roots, retaining certificate and hostname checks.
    set_client_factory(lambda: httpx.Client(verify=ssl.create_default_context(), follow_redirects=True))
    for name in MODELS if a.model == 'all' else [a.model]:
        target = a.directory / name
        target.mkdir(parents=True, exist_ok=True)
        existing = target / 'model_manifest.json'
        if existing.exists():
            old = json.loads(existing.read_text(encoding='utf-8'))
            assert all(digest(target / k) == v['sha256'] for k, v in old['files'].items()), 'Existing model changed'
            print(json.dumps({'model': name, 'status': 'verified_existing'}), flush=True)
            continue
        info = HfApi(token=False).model_info(MODELS[name], files_metadata=True)
        snapshot_download(MODELS[name], revision=info.sha, local_dir=target,
                          allow_patterns=sorted(FILES), token=False, max_workers=2)
        files = {}
        for entry in info.siblings:
            if entry.rfilename not in FILES:
                continue
            path = target / entry.rfilename
            value = digest(path)
            if entry.lfs:
                assert value == entry.lfs.sha256, 'Downloaded model differs from upstream LFS SHA256'
            files[entry.rfilename] = {'sha256': value, 'bytes': path.stat().st_size}
        assert {'config.json', 'model.bin', 'tokenizer.json'} <= files.keys()
        existing.write_text(json.dumps({'schema': 1, 'repository': MODELS[name],
            'revision': info.sha, 'files': files}, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'model': name, 'revision': info.sha,
                          'bytes': sum(v['bytes'] for v in files.values()), 'status': 'downloaded_verified'}), flush=True)


if __name__ == '__main__':
    main()
