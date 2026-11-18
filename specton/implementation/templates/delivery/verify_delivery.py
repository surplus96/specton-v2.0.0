"""Run before installation; compare the archive SHA256 with Specton's source hash separately."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
manifest = json.loads((ROOT / 'build-manifest.json').read_text())
for name, expected in manifest['files'].items():
    path = ROOT / name
    if path.is_symlink() or not path.resolve().is_relative_to(ROOT) or not path.is_file():
        raise SystemExit('Invalid package path')
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit('Package file mismatch: ' + name)
print('Package files match manifest; independently verify the downloaded archive hash.')
