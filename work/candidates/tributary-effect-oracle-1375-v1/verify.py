"""Fixed file-only artifact check; no candidate import, tests or process access."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def raw(path):
    with path.open('rb') as stream:
        data = stream.read(2*1024*1024+1)
    if len(data) > 2*1024*1024:
        raise ValueError('Selected file bound')
    return data


def main():
    if sys.argv[1:] != ['--check']:
        raise SystemExit('Only --check is supported')
    manifest = json.loads(raw(HERE/'manifest.json'))
    assert manifest['sealed'] is True and manifest['native_ready'] is False
    for name, expected in manifest['file_pins'].items():
        path = (ROOT/name).resolve(strict=True)
        assert path.is_relative_to(ROOT)
        data = raw(path)
        assert expected == {'bytes':len(data), 'sha256':hashlib.sha256(data).hexdigest()}, name
    print(json.dumps({'status':'passed', 'pins':len(manifest['file_pins']),
                      'tests_run':0, 'candidate_imports':0, 'target_PE_accesses':0,
                      'game_process_accesses':0, 'native_game_calls':0}))


if __name__ == '__main__':
    main()
