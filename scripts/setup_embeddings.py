"""Explicit one-time, checksum-verified download. Worker never downloads models."""
import hashlib
import json
from pathlib import Path
import sys
import time
import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.modules.semantics.embedding_config import MODEL_ID, REVISION, MODEL_SHA256, SMALL_FILES
from app.modules.foundation.config import Settings
from app.modules.foundation.storage import reject_links


def main():
    target = Settings().embedding_model_dir
    reject_links(target)
    target.mkdir(parents=True, exist_ok=True)
    files = {'onnx/model.onnx': ('sha256', MODEL_SHA256), **{name: ('git', digest) for name, digest in SMALL_FILES.items()}}
    report = {}
    with httpx.Client(timeout=60, trust_env=False, follow_redirects=True) as client:
        for name, (kind, expected) in files.items():
            path = target / name
            reject_links(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + '.download')
            reject_links(temporary)
            def verified(content):
                return hashlib.sha256(content).hexdigest() if kind == 'sha256' else hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()
            if path.is_file() and verified(path.read_bytes()) == expected:
                print('Already verified: ' + name, flush=True)
            else:
                print('Downloading: ' + name, flush=True)
                deadline = time.monotonic() + 1800
                limit = 100_000_000 if kind == 'sha256' else 1_000_000
                size = 0
                try:
                    with client.stream('GET', f'https://huggingface.co/{MODEL_ID}/resolve/{REVISION}/{name}') as response:
                        response.raise_for_status()
                        with temporary.open('wb') as output:
                            for chunk in response.iter_bytes():
                                size += len(chunk)
                                if size > limit or time.monotonic() > deadline:
                                    raise ValueError('Download exceeded its bound.')
                                output.write(chunk)
                    if verified(temporary.read_bytes()) != expected:
                        raise ValueError('Downloaded artifact checksum does not match the pinned revision.')
                    temporary.replace(path)
                finally:
                    temporary.unlink(missing_ok=True)
            content = path.read_bytes()
            report[name] = {'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
    if 'license: apache-2.0' not in (target / 'README.md').read_text(encoding='utf-8'):
        raise ValueError('Pinned model card license could not be verified.')
    (target / 'download-manifest.json').write_text(json.dumps({'model': MODEL_ID, 'revision': REVISION, 'files': report}, indent=2))
    print('Local embedding model ready; no cloud inference is used.', flush=True)


if __name__ == '__main__': main()
