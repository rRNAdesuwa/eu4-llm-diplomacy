"""Build an allowlisted ZIP locally. Does not launch or access the game process."""
import hashlib
import json
from pathlib import Path
import re
import zipfile


def assert_no_machine_paths(payload):
    """Reject accidental Windows/POSIX absolute paths in text release files."""

    absolute_path = re.compile(rb"(?i)(?:[A-Z]:[\\/]|/(?:users|home)/)")
    text_suffixes = {'.md', '.py', '.json', '.txt', '.yml', '.yaml', '.ps1'}
    for name, data in payload.items():
        if name == 'local.env.example' or Path(name).suffix.lower() not in text_suffixes:
            continue
        if absolute_path.search(data):
            raise RuntimeError(f'Absolute machine path found in release file: {name}')


def main():
    root = Path(__file__).resolve().parents[1]
    meta = json.loads((root / 'release/release.json').read_text(encoding='utf-8'))
    if not re.fullmatch(r'[A-Za-z0-9.-]+', meta['version']):
        raise RuntimeError('Invalid release version')
    dll = root / 'work/native' / meta['dll']
    if hashlib.sha256(dll.read_bytes()).hexdigest() != meta['dll_sha256']:
        raise RuntimeError('DLL differs from the reviewed release; validate before updating metadata')
    paths = ['release/release.json', 'tools/load_release.py', 'tools/request_treaty.py',
             'local.env.example', 'work/local_config.py',
             'work/native/inject_probe.py', 'work/probe_native_state.py',
             'docs/DLL安装与更新.md', 'docs/开发与发布.md',
             'work/native/' + meta['dll']]
    payload = {name: (root / name).read_bytes() for name in paths}
    assert_no_machine_paths(payload)
    payload['SHA256SUMS.txt'] = ''.join(
        f'{hashlib.sha256(data).hexdigest()}  {name}\n'
        for name, data in sorted(payload.items())).encode('utf-8')
    out = root / 'dist'
    out.mkdir(exist_ok=True)
    archive = out / f'eu4-authorized-peace-{meta["version"]}.zip'
    if archive.exists():
        raise RuntimeError('Release ZIP already exists; use a new version or move the old ZIP first')
    prefix = archive.stem
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as zipped:
        for name, data in payload.items():
            zipped.writestr(f'{prefix}/{name}', data)
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(
        f'{checksum}  {archive.name}\n', encoding='utf-8')
    print(archive)
    print(f'SHA256: {checksum}')


if __name__ == '__main__':
    main()
