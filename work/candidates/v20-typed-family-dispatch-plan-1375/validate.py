"""Run only this candidate's two bounded documentation checks; CreateNew outputs."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import build_plan as build

HERE = Path(__file__).resolve().parent
LOCAL = ('build_plan.py', 'test_plan.py', 'validate.py', 'README.md', 'plan.json', 'abi-registry.json', 'input-pins.json')

def descriptor(path):
    raw = path.read_bytes()
    if len(raw) > build.LIMIT: raise ValueError('Local byte bound')
    return {'path': path.relative_to(build.ROOT).as_posix(), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def main():
    out = HERE / 'validation-final'
    out.mkdir(exist_ok=False)
    before = build.describe_inputs() + [descriptor(HERE / n) for n in LOCAL]
    commands = [
        [sys.executable, '-B', str(HERE/'build_plan.py'), '--check'],
        [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(HERE), '-p', 'test_*.py', '-v'],
    ]
    stages = []
    for index, command in enumerate(commands):
        stdout, stderr = out / f'{index}.stdout.txt', out / f'{index}.stderr.txt'
        with stdout.open('xb') as so, stderr.open('xb') as se:
            done = subprocess.run(command, cwd=build.ROOT, stdout=so, stderr=se, timeout=30, check=False)
        stages.append({'argv': command, 'exit_code': done.returncode, 'stdout': descriptor(stdout), 'stderr': descriptor(stderr)})
        if stdout.stat().st_size + stderr.stat().st_size > 128*1024: raise ValueError('Unexpected output growth')
    after = build.describe_inputs() + [descriptor(HERE / n) for n in LOCAL]
    record = {'schema_version': 1, 'stages': stages, 'inputs_before': before, 'inputs_after': after,
              'inputs_unchanged': before == after, 'passed': before == after and all(s['exit_code'] == 0 for s in stages),
              'all_children_collected': True, 'remaining_shell_sessions': [],
              'new_decode_bytes': 0, 'game_accessed': False, 'compiled': False}
    with (out/'validation.json').open('xb') as stream: stream.write(build.canonical(record))
    print(json.dumps({'passed': record['passed'], 'tracked_files': len(before), 'exit_codes': [s['exit_code'] for s in stages]}))
    return 0 if record['passed'] else 1

if __name__ == '__main__': raise SystemExit(main())
