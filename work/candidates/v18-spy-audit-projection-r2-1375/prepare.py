"""Check this offline projection's fixed source/capture bytes; no compilation or process access."""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def bounded(path, limit):
    with path.open('rb') as stream:
        raw = stream.read(limit+1)
    if len(raw) > limit:
        raise ValueError('Read budget')
    return raw


def descriptor(raw):
    return {'bytes':len(raw), 'sha256':hashlib.sha256(raw).hexdigest()}


def check():
    groups = [('source-pins.json',128),('candidate-index.json',16),('mock-artifacts.json',32)]
    total = 0
    result = {}
    for filename, limit in groups:
        mapping = json.loads(bounded(HERE/filename,128*1024))
        if not 1 <= len(mapping) <= limit:
            raise ValueError('Inventory count budget')
        for name, expected in mapping.items():
            path = ROOT/name
            if path.resolve() != path or not path.is_relative_to(ROOT):
                raise ValueError('Noncanonical source')
            raw = bounded(path,4*1024*1024)
            total += len(raw)
            if total > 24*1024*1024 or descriptor(raw) != expected:
                raise ValueError('Changed source or byte budget: '+name)
        result[filename] = len(mapping)
    result.update(checked_bytes=total, native_game_calls=False, game_access=False,
                  actual_native_log_authenticated=False, production_ready=False)
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true',required=True)
    parser.parse_args()
    print(json.dumps(check(),sort_keys=True))
