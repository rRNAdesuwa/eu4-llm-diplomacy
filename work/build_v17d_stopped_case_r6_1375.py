"""Create an explicit R6 stopped case; preserve the failed R5 case unchanged."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'work/runtime/native1375-v17'
SOURCE = BASE / 'batch-stopped-case-r5-9656.json'
OUTPUT = BASE / 'batch-stopped-case-r6-9656.json'
SOURCE_SHA = '79f14ea64bd1c4c2d6b64490ff1034f37f61dfb8f38cefc802d381e8a6378a4c'


def read(path, limit=8 * 1024 * 1024):
    if not path.is_file() or path.is_symlink() or path.is_junction():
        raise ValueError('Nonregular case input')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Case artifact bound')
    return raw


def desc(raw):
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def main():
    original = read(SOURCE, 512 * 1024)
    if desc(original)['sha256'] != SOURCE_SHA:
        raise ValueError('Original explicit R5 case changed')
    case = json.loads(original)
    if case['purpose'] != 'v17_batch_stopped_case_r5' or case['finalized'] is not True:
        raise ValueError('Unexpected predecessor case')
    inputs = dict(case['inputs'])
    for key, expected in inputs.items():
        if '\\' in key or ':' in key or not key.startswith('work/'):
            raise ValueError('Noncanonical case input')
        path = ROOT / key
        if not path.resolve().is_relative_to(ROOT.resolve()) or desc(read(path)) != expected:
            raise ValueError('Stopped input changed or escaped')
    for path in (SOURCE, Path(__file__)):
        inputs[path.relative_to(ROOT).as_posix()] = desc(read(path))
    if len(inputs) > 1400 or sum(row['bytes'] for row in inputs.values()) > 160 * 1024 * 1024:
        raise ValueError('Final case inventory budget')
    case['purpose'] = 'v17_batch_stopped_case_r6'
    case['inputs'] = inputs
    encoded = (json.dumps(case, sort_keys=True, indent=2) + '\n').encode()
    if len(encoded) > 512 * 1024:
        raise ValueError('Case size bound')
    if read(SOURCE, 512 * 1024) != original:
        raise ValueError('Predecessor changed during materialization')
    with OUTPUT.open('xb') as stream:
        stream.write(encoded)
    print(json.dumps(dict(output=OUTPUT.relative_to(ROOT).as_posix(), case_sha256=desc(encoded)['sha256'],
                          case_bytes=len(encoded), inputs=len(inputs), review_run=False, production=False)))


if __name__ == '__main__':
    main()
