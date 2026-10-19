"""Check sealed offline batch inputs; never materialize or run game code."""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MAX_FILE = 2 * 1024 * 1024


def read(path):
    with path.open('rb') as stream:
        raw = stream.read(MAX_FILE + 1)
    if len(raw) > MAX_FILE:
        raise ValueError('Bounded candidate input exceeded')
    return raw


def check():
    count = 0
    for manifest in ('source-pins.json', 'candidate-index.json'):
        entries = json.loads(read(HERE / manifest))
        if type(entries) is not dict or len(entries) > 64:
            raise ValueError('Manifest bounds')
        for name, expected in entries.items():
            path = ROOT / name
            if path.resolve() != path or not path.is_relative_to(ROOT):
                raise ValueError('Noncanonical input')
            raw = read(path)
            actual = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            if expected != actual:
                raise ValueError('Input hash differs: ' + name)
            count += 1
    return {'checked_files': count, 'game_access': False, 'production': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', required=True)
    parser.parse_args()
    print(json.dumps(check(), sort_keys=True))
