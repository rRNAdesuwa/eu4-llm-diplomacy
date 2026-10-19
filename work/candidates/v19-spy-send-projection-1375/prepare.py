"""Read-only exact source and isolated capture checks. No compiler/process API."""
from pathlib import Path
import argparse
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def read(path, limit=4*1024*1024):
    path = path.resolve()
    if not path.is_relative_to(ROOT) or path.is_symlink() or not path.is_file():
        raise ValueError('regular repository input required')
    with path.open('rb') as f: raw = f.read(limit+1)
    if len(raw) > limit: raise ValueError('input byte budget')
    return raw


def desc(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def check():
    inputs = json.loads(read(HERE/'input-pins.json', 65536))
    if not 1 <= len(inputs) <= 64: raise ValueError('input count')
    total = 0
    for name, pin in inputs.items():
        if name == 'bridge/diplomacy_api.py': raise ValueError('mutable formal API dependency forbidden')
        raw = read(ROOT/name, 2097152); total += len(raw)
        if desc(raw) != pin or total > 16777216: raise ValueError('frozen source changed '+name)
    index = json.loads(read(HERE/'source-index.json', 65536))
    if index['input_pins_sha256'] != desc(read(HERE/'input-pins.json'))['sha256']: raise ValueError('input index changed')
    for name, pin in index['sources'].items():
        if Path(name).name != name or desc(read(HERE/name)) != pin: raise ValueError('local source changed '+name)
    captures = json.loads(read(HERE/'capture-index.json', 65536))
    for name, pin in captures['files'].items():
        if not name.startswith('compile-final/'): raise ValueError('only explicit isolated artifacts')
        if desc(read(HERE/name)) != pin: raise ValueError('capture artifact changed '+name)
    if json.loads(read(HERE/'compile-final/command.json'))['exit_code'] != 0: raise ValueError('mock compilation failed')
    if b'../v19-spy-send-core-1375/mock_support.inc' not in read(HERE/'capture_mock.cpp'): raise ValueError('sealed mock include')
    return {'checked': True, 'source_inputs': len(inputs), 'input_bytes': total,
            'capture_files': len(captures['files']), 'game_accessed': False, 'production_ready': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', required=True)
    parser.parse_args(); print(json.dumps(check(), sort_keys=True))
