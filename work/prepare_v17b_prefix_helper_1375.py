"""Create a new identity-only variant of the already reviewed RO prefix helper."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'work/snapshot_v17_directional_preflight_prefix_1375.py'
TARGET = ROOT / 'work/snapshot_v17b_directional_preflight_prefix_1375.py'
BASELINE = ROOT / 'work/runtime/native1375-v17/baseline-before-injection-63500.json'
PID, CREATION = 63500, '01dd56c21f9b7c9d'


def main():
    raw = SOURCE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == '02eafbe31a9f067c3a214db11d4d7de073e6714814660bd33d27db8ba0d89428'
    baseline = json.loads(BASELINE.read_bytes())
    assert baseline['read_only'] is True
    assert baseline['source']['pid'] == PID
    assert baseline['source']['process_creation_filetime'] == int(CREATION, 16)
    first, second = baseline['identity_before_and_after']
    assert first == second and first['raw_date'] == 56456976 and first['acceptance_flag'] == 0
    world = first['world_cookie']
    assert isinstance(world, str) and world.startswith('0x') and int(world, 16) > 0
    text = raw.decode('utf-8')
    tree = ast.parse(text)
    matches = [n for n in tree.body if isinstance(n, ast.Assign)
               and isinstance(n.targets[0], ast.Tuple)
               and [x.id for x in n.targets[0].elts] == ['PID', 'CREATION', 'WORLD']]
    assert len(matches) == 1 and matches[0].lineno == matches[0].end_lineno
    lines = text.splitlines(keepends=True)
    lines[matches[0].lineno - 1] = f'PID, CREATION, WORLD = {PID}, {CREATION!r}, {world!r}\n'
    new = ''.join(lines)
    compile(new, str(TARGET), 'exec')
    normalized = new.replace(lines[matches[0].lineno - 1], text.splitlines(keepends=True)[matches[0].lineno - 1], 1)
    assert normalized == text
    delta = ''.join(difflib.unified_diff(text.splitlines(True), new.splitlines(True), fromfile=str(SOURCE), tofile=str(TARGET)))
    with TARGET.open('xb') as dst:
        dst.write(new.encode())
    diffpath = ROOT / 'work/runtime/native1375-v17/prefix-helper-adaptation-63500.diff'
    with diffpath.open('x', encoding='utf-8', newline='\n') as dst:
        dst.write(delta)
    print(json.dumps({'output': str(TARGET), 'sha256': hashlib.sha256(new.encode()).hexdigest(),
                      'delta': delta, 'identity_only': True}))


if __name__ == '__main__':
    main()
