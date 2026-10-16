"""Root's exclusive v13 materialization and single formal build, never injection."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'work/candidates/v13-owned-peace-review'
HOST = ROOT / 'work/candidates/v13-host-review'
OUT = ROOT / 'work/runtime/native1375-v13'
REVIEWS = ((NATIVE, 'ceaa1802a0230761ebaf27476c368377d59485cd275f7d8466da5052223a1ef7'),
           (HOST, '131a460f7cb75e110857ab73a8fe3e6b23a7cc604eee583152d17febe1751bfe'))

def require(ok, message):
    if not ok:
        raise ValueError(message)

def bounded(path):
    with path.open('rb') as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    require(len(raw) <= 2 * 1024 * 1024, 'Source read budget exceeded')
    return raw

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def write_new(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())

def save(path, value):
    write_new(path, (json.dumps(value, indent=2, ensure_ascii=True) + '\n').encode())

def audited_files():
    files = []
    for candidate, digest in REVIEWS:
        require(sha(bounded(candidate / 'review.json')) == digest, 'Candidate review changed')
        check = subprocess.run([sys.executable, '-B', str(candidate / 'prepare.py'), '--check'],
                               cwd=ROOT, capture_output=True, timeout=30)
        require(check.returncode == 0, 'Candidate prepare check failed: ' + check.stderr.decode(errors='replace')[:2000])
    native = json.loads(bounded(NATIVE / 'source-set.json'))['sources']
    host = json.loads(bounded(HOST / 'new-files.json'))['files']
    require(len(native) == 20 and len(host) == 16, 'Exact source counts differ')
    for candidate, source_list in ((NATIVE, native), (HOST, host)):
        for item in source_list:
            name = item['path']
            dest = ROOT / name
            require(not Path(name).is_absolute() and '..' not in Path(name).parts
                    and dest.resolve().is_relative_to(ROOT.resolve()), 'Target escapes repository')
            source = candidate / 'generated' / name
            raw = bounded(source)
            require(len(raw) == item['bytes'] and sha(raw) == item['sha256'], 'Generated source differs: ' + name)
            files.append((dest, raw, item['sha256']))
    require(len({str(p) for p, _, _ in files}) == 36, 'Duplicate source destination')
    return files

def materialize():
    files = audited_files()
    require(all(not p.exists() for p, _, _ in files), 'A v13 source already exists; never overwrite')
    OUT.mkdir(parents=True, exist_ok=True)
    require(not any(OUT.iterdir()), 'v13 runtime is not empty')
    review = {'schema_version': 1, 'purpose': 'root_v13_materialization_review',
              'native_review_sha256': REVIEWS[0][1], 'host_review_sha256': REVIEWS[1][1],
              'reviewed_at_utc': datetime.now(timezone.utc).isoformat(),
              'files': {p.relative_to(ROOT).as_posix(): digest for p, _, digest in files},
              'native_count': 20, 'host_count': 11, 'fixture_count': 5,
              'native_independent_review_sha256': '283db31b3b183bdb0a78c846229b741d36fed6a923ce224758f34e41047f5a58',
              'root_host_validation_sha256': 'b16aa414375f0162b924f5b04012c3151dc4b00e95b062afb8d6f0f980a5ad1f',
              'game_accessed': False, 'injected': False, 'production_ready': False}
    save(OUT / 'root-candidate-review-20261008a.json', review)
    for dest, raw, _ in files:
        write_new(dest, raw)
    require(all(sha(bounded(p)) == digest for p, _, digest in audited_files()), 'Materialized source hash differs')
    print(json.dumps({'materialized': True, 'files': len(files), 'game_accessed': False}))

def build():
    files = audited_files()
    require(all(p.is_file() and sha(bounded(p)) == digest for p, _, digest in files), 'Reviewed source differs before build')
    review = json.loads(bounded(OUT / 'root-candidate-review-20261008a.json'))
    require(review['files'] == {p.relative_to(ROOT).as_posix(): digest for p, _, digest in files}, 'Root review source set differs')
    require(not (OUT / 'build.json').exists() and not any(OUT.glob('session-*'))
            and not (OUT / 'eu4_pair_lab_v13_1375.dll').exists(), 'Used or built v13 runtime; never rebuild')
    intent = {'schema_version': 1, 'purpose': 'root_v13_single_formal_build',
              'started_at_utc': datetime.now(timezone.utc).isoformat(),
              'source_review_sha256': sha(bounded(OUT / 'root-candidate-review-20261008a.json')),
              'game_accessed': False, 'injection_performed': False}
    save(OUT / 'root-single-build-intent-20261008a.json', intent)
    env = os.environ.copy()
    env['EU4_V13_ROOT_REVIEW_APPROVED'] = '1'
    env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + env.get('PATH', '')
    command = ['cmd.exe', '/d', '/c', str(ROOT / 'work/native/v13/build-lab-1375.cmd')]
    with (OUT / 'root-single-build-20261008a.stdout.txt').open('xb') as stdout:
        run = subprocess.run(command, cwd=ROOT, env=env, stdout=stdout, stderr=subprocess.STDOUT, timeout=120)
        stdout.flush()
        os.fsync(stdout.fileno())
    unchanged = all(sha(bounded(p)) == digest for p, _, digest in audited_files())
    report = {'schema_version': 1, 'purpose': intent['purpose'], 'exit_code': run.returncode,
              'source_unchanged_after_build': unchanged,
              'stdout_sha256': sha(bounded(OUT / 'root-single-build-20261008a.stdout.txt')),
              'completed_at_utc': datetime.now(timezone.utc).isoformat(),
              'game_accessed': False, 'injected': False, 'production_ready': False}
    if (OUT / 'build.json').is_file():
        sys.path.insert(0, str(ROOT))
        from work.native import lab_protocol_v13_1375 as lab
        manifest, digest = lab.verify_build()
        report.update(manifest_sha256=digest, dll_sha256=manifest['dll_sha256'],
                      native_sources=len(manifest['source_sha256']), host_sources=len(manifest['host_source_sha256']),
                      support_sources=len(manifest['support_source_sha256']))
    save(OUT / 'root-single-build-verification-20261008a.json', report)
    print(json.dumps(report))
    require(run.returncode == 0 and unchanged and 'dll_sha256' in report, 'Formal build failed; no retry/rebuild')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('materialize', 'build'))
    args = parser.parse_args()
    (materialize if args.mode == 'materialize' else build)()

if __name__ == '__main__':
    main()
