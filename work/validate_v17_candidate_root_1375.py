"""Root check and regression of a sealed v17 source candidate; no native build/game."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / 'work/candidates/v17-acceptance-pin-review'
OUT = ROOT / 'work/review-results/v17-candidate-root-20261008a'
EXPECTED_REVIEW = 'ad9d5d2c368e8358cf5e3e6b156f5ccb2b399a7c1c33f989a9e79db0e6d7fd7a'


def pin(path):
    with path.open('rb') as f:
        raw = f.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024 or path.is_symlink() or path.is_junction():
        raise ValueError('Review input bound')
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def sources():
    result = {}
    for p in CANDIDATE.rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts and not any(s.startswith('validation-results') for s in p.parts):
            result[p.relative_to(CANDIDATE).as_posix()] = pin(p)
    if len(result) > 256:
        raise ValueError('Source inventory bound')
    return result


def main():
    assert pin(CANDIDATE / 'review.json')['sha256'] == EXPECTED_REVIEW
    before = sources()
    OUT.mkdir(parents=True, exist_ok=False)
    commands = [
        [sys.executable, '-B', str(CANDIDATE / 'prepare.py'), '--check'],
        [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(CANDIDATE), '-p', 'test_*.py', '-v'],
    ]
    runs = []
    for number, command in enumerate(commands):
        output = OUT / f'{number}-output.txt'
        started = time.monotonic()
        with output.open('xb') as stream:
            done = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=180)
        runs.append({'command': command, 'exit_code': done.returncode,
                     'elapsed_seconds': time.monotonic() - started, 'output': pin(output)})
    after = sources()
    result = {'purpose': 'root_v17_sealed_candidate_validation', 'candidate_review_sha256': EXPECTED_REVIEW,
              'runs': runs, 'source_files': before, 'inputs_unchanged': before == after,
              'all_stages_exit_zero': all(r['exit_code'] == 0 for r in runs),
              'cpp_compiled': False, 'native_built': False, 'materialized': False,
              'game_accessed': False, 'requests_published': False, 'production_ready': False}
    path = OUT / 'validation.json'
    with path.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(result, f, indent=2);f.write('\n')
    print(json.dumps({'output': str(path.relative_to(ROOT)), **pin(path),
                     'passed': result['all_stages_exit_zero'] and result['inputs_unchanged']}))
    return 0 if result['all_stages_exit_zero'] and result['inputs_unchanged'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
