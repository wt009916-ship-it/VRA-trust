"""Explicit optional model installation. Never downloads during application requests."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.semantic_models import ARTIFACTS, MODEL_ID, REVISION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    manifest = {'model': MODEL_ID, 'revision': REVISION, 'files': [],
                'base_license': 'https://huggingface.co/BAAI/bge-small-zh-v1.5#license',
                'training': False}
    for name, expected in ARTIFACTS.items():
        target = root/name
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                raise ValueError('Existing model differs; choose another empty output directory')
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix + '.part')
            with urlopen(f'https://huggingface.co/{MODEL_ID}/resolve/{REVISION}/{name}', timeout=120) as response, temporary.open('xb') as stream:
                size = 0; digest = hashlib.sha256()
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > 100 * 1024**2:
                        raise ValueError('Model artifact exceeds declared limit')
                    stream.write(chunk); digest.update(chunk)
            if digest.hexdigest() != expected:
                raise ValueError('Model digest mismatch; incomplete artifact preserved, not installed')
            temporary.rename(target)
        manifest['files'].append({'path': name, 'sha256': expected, 'bytes': target.stat().st_size})
    (root/'installation.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print('Verified optional model. Set VRA_SEMANTIC_MODEL_DIR to this directory explicitly.')


if __name__ == '__main__':
    main()
