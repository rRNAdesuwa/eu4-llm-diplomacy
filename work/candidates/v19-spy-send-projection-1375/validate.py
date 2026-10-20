"""CreateNew offline validation; collect every exact owned Python child."""
from pathlib import Path
import argparse
import json
import subprocess
import sys
import time
import prepare


def snapshot():
    paths = {prepare.ROOT/n for n in json.loads(prepare.read(prepare.HERE/'input-pins.json'))}
    paths.update(prepare.HERE/n for n in json.loads(prepare.read(prepare.HERE/'source-index.json'))['sources'])
    paths.update(prepare.HERE/n for n in json.loads(prepare.read(prepare.HERE/'capture-index.json'))['files'])
    paths.add(prepare.HERE/'source-index.json')
    return {p.relative_to(prepare.ROOT).as_posix(): prepare.desc(prepare.read(p)) for p in sorted(paths)}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); out = args.output.resolve(); out.mkdir(exist_ok=False)
    before = snapshot(); commands = [
        [sys.executable, '-B', str(prepare.HERE/'prepare.py'), '--check'],
        [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(prepare.HERE), '-p', 'test_projection.py', '-v'],
        [sys.executable, '-B', str(prepare.HERE/'summarize_mock.py')]]
    results = []
    for n, argv in enumerate(commands):
        start = time.monotonic(); timeout = False
        with (out/f'{n}.stdout.txt').open('xb') as stdout, (out/f'{n}.stderr.txt').open('xb') as stderr:
            child = subprocess.Popen(argv, cwd=prepare.ROOT, stdout=stdout, stderr=stderr)
            try: code = child.wait(timeout=55)
            except subprocess.TimeoutExpired:
                timeout = True; child.kill(); code = child.wait(timeout=10)
        results.append({'argv': argv, 'exit_code': code, 'timed_out': timeout, 'seconds': time.monotonic()-start})
        if code: break
    after = snapshot()
    passed = len(results) == 3 and all(r['exit_code'] == 0 and not r['timed_out'] for r in results) and before == after
    files = {p.name: prepare.desc(prepare.read(p)) for p in out.iterdir() if p.is_file()}
    value = {'passed': passed, 'commands': results, 'before': before, 'after': after,
             'inputs_unchanged': before == after, 'artifacts': files, 'all_shell_sessions_collected': True,
             'game_accessed': False, 'native_calls_performed': False, 'dll_built': False, 'production_ready': False}
    with (out/'validation.json').open('x', encoding='utf8', newline='\n') as f:
        json.dump(value, f, sort_keys=True, indent=2); f.write('\n')
    print(json.dumps({'passed': passed, 'commands': len(results), 'inputs': len(before)}))
    return 0 if passed else 1


if __name__ == '__main__': raise SystemExit(main())
