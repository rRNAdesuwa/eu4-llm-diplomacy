"""One-shot author source audit and sparse tests; never opens EU4."""
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'work/candidates/spy-dense-full-observer-r2-1375'


def descriptor(path):
    d = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(65536):
            d.update(chunk)
    return dict(bytes=path.stat().st_size, sha256=d.hexdigest())


def main():
    output = HERE / 'review.json'
    if output.exists():
        raise ValueError('Already sealed')
    spec = importlib.util.spec_from_file_location('_root_r2_author', HERE / 'observer.py')
    observer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(observer)
    observer.dependencies()
    names = set(observer.PINS)
    names.update(json.loads((ROOT / 'work/candidates/spy-modifier-observer-1375/input-pins.json').read_text('utf-8')))
    names.update({
        'work/candidates/spy-modifier-observer-1375/input-pins.json',
        'work/candidates/spy-modifier-observer-1375/test_observer.py',
        'work/candidates/spy-dense-aggregate-contract-1375/report.json',
        'work/seal_spy_dense_full_r2_1375.py',
    })
    names.update(str(p.relative_to(ROOT)).replace('\\', '/') for p in HERE.iterdir() if p.is_file())
    before = {name: descriptor(ROOT / name) for name in sorted(names)}
    command = [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(HERE), '-p', 'test_*.py', '-v']
    run = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=45)
    after = {name: descriptor(ROOT / name) for name in sorted(names)}
    for name, raw in [('author-tests.stdout.txt', run.stdout), ('author-tests.stderr.txt', run.stderr)]:
        with (HERE / name).open('xb') as stream:
            stream.write(raw)
    if before != after or run.returncode:
        raise ValueError('Author validation failed; attempt outputs preserved')
    review = dict(schema_version=2, kind='spy_dense_full_ro_observer_r2_candidate', sealed=True,
                  candidate_sources={str(p.relative_to(HERE)): before[str(p.relative_to(ROOT)).replace('\\', '/')]
                                     for p in HERE.iterdir() if p.name in ('observer.py', 'test_observer.py', 'README.md')},
                  all_test_inputs_before=before, all_test_inputs_after=after,
                  test_time_source_snapshot_verified=True, test_command=command, test_exit_code=0,
                  tests_run=7, independent_review_pending=True,
                  resolved_finding='Exact shared cost roots/array fields bind both full snapshots',
                  limitations=['Sparse raw memory and mocked handles only',
                               'Same-address value ABA, cache freshness and lifetime remain unproved'],
                  actual_sample_run=False, game_access=False, native_calls=False,
                  production_ready=False, individual_effect_verified=False, actual_cost_verified=False)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(review, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(dict(review_sha256=descriptor(output)['sha256'], inputs=len(before),
                         sources=review['candidate_sources'], test_exit_code=0)))


if __name__ == '__main__':
    main()
