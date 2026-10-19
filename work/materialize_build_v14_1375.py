"""Root-exclusive reviewed v14 materialization and one formal build; no injection."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / 'work/candidates/v14-intent-review'
OUT = ROOT / 'work/runtime/native1375-v14'
REVIEW_SHA = '473857491a91c56cb664c4a8c5e19463355fd1e4158aa4ff46a558072d8aa143'
NEW_FILES_SHA = 'e4c04cdd1ed9e6ce1fe22fffafaad0f9c52d727d626c977b0b358a6540e6c6ae'
INDEPENDENT = ROOT / 'work/review-results/v14-native-candidate-native-inventory-20261008a.json'
INDEPENDENT_SHA = '4d4bffc4463f0f19247eca2c013456c3e5cc4dfc88c6417665ce004ca47bc6a8'
HOST_VALIDATION = CANDIDATE / 'validation-results/20261007T220131Z-84cb631fd9274196aa8933949623c72f/validation.json'
HOST_VALIDATION_SHA = '700f9a572e29bdae2ee509061b7845ebc4146aecb5efe0ced29129e6824e857d'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def bounded(path):
    with path.open('rb') as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    require(len(raw) <= 2 * 1024 * 1024, 'Artifact read budget exceeded')
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
    write_new(path, (json.dumps(value, indent=2) + '\n').encode())


def audited_files():
    for path, expected in ((CANDIDATE / 'review.json', REVIEW_SHA),
                           (CANDIDATE / 'new-files.json', NEW_FILES_SHA),
                           (INDEPENDENT, INDEPENDENT_SHA), (HOST_VALIDATION, HOST_VALIDATION_SHA)):
        require(sha(bounded(path)) == expected, 'Review or validation input changed: ' + str(path))
    independent = json.loads(bounded(INDEPENDENT))
    validation = json.loads(bounded(HOST_VALIDATION))
    require(independent['finding_count'] == 0 and independent['candidate_review_sha256'] == REVIEW_SHA
            and validation['passed'] is True and validation['review_sha256'] == REVIEW_SHA,
            'Review no longer approves the fixed candidate')
    check = subprocess.run([sys.executable, '-B', str(CANDIDATE / 'prepare.py'), '--check'],
                           cwd=ROOT, capture_output=True, timeout=30)
    require(check.returncode == 0, 'Candidate check failed: ' + check.stderr.decode(errors='replace')[:2000])
    listing = json.loads(bounded(CANDIDATE / 'new-files.json'))
    require(listing['counts'] == {'frozen_native': 20, 'frozen_host': 11, 'frozen_fixture': 5}
            and len(listing['files']) == 36, 'Reviewed source counts differ')
    files = []
    for item in listing['files']:
        name = item['path']
        dest = ROOT / name
        require(not Path(name).is_absolute() and '..' not in Path(name).parts
                and dest.resolve().is_relative_to(ROOT.resolve()), 'Target escapes repository')
        raw = bounded(CANDIDATE / 'generated' / name)
        require(len(raw) == item['bytes'] and sha(raw) == item['sha256'], 'Generated source changed: ' + name)
        files.append((dest, raw, item['sha256']))
    require(len({str(p) for p, _, _ in files}) == 36, 'Duplicate source destination')
    return files


def materialize():
    files = audited_files()
    require(all(not p.exists() for p, _, _ in files), 'A v14 source already exists; never overwrite')
    OUT.mkdir(parents=True, exist_ok=True)
    require(not any(OUT.iterdir()), 'v14 runtime is not empty')
    review = {
        'schema_version': 1, 'purpose': 'root_v14_materialization_review',
        'candidate_review_sha256': REVIEW_SHA, 'new_files_sha256': NEW_FILES_SHA,
        'native_independent_review_sha256': INDEPENDENT_SHA,
        'root_host_validation_sha256': HOST_VALIDATION_SHA,
        'reviewed_at_utc': datetime.now(timezone.utc).isoformat(),
        'files': {p.relative_to(ROOT).as_posix(): digest for p, _, digest in files},
        'native_count': 20, 'host_count': 11, 'fixture_count': 5,
        'game_accessed': False, 'injected': False, 'production_ready': False,
    }
    save(OUT / 'root-candidate-review-20261008a.json', review)
    for dest, raw, _ in files:
        write_new(dest, raw)
    require(all(sha(bounded(p)) == digest for p, _, digest in audited_files()), 'Materialized source differs')
    print(json.dumps({'materialized': True, 'files': len(files), 'game_accessed': False}))


def build():
    files = audited_files()
    require(all(p.is_file() and sha(bounded(p)) == digest for p, _, digest in files), 'Source changed before build')
    review = json.loads(bounded(OUT / 'root-candidate-review-20261008a.json'))
    require(review['files'] == {p.relative_to(ROOT).as_posix(): digest for p, _, digest in files}, 'Root source set differs')
    require(not (OUT / 'build.json').exists() and not any(OUT.glob('session-*'))
            and not (OUT / 'eu4_pair_lab_v14_1375.dll').exists(), 'Used/built v14 runtime; never rebuild')
    intent = {'schema_version': 1, 'purpose': 'root_v14_single_formal_build',
              'started_at_utc': datetime.now(timezone.utc).isoformat(),
              'source_review_sha256': sha(bounded(OUT / 'root-candidate-review-20261008a.json')),
              'game_accessed': False, 'injection_performed': False}
    save(OUT / 'root-single-build-intent-20261008a.json', intent)
    env = os.environ.copy()
    env['EU4_V14_ROOT_REVIEW_APPROVED'] = '1'
    env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + env.get('PATH', '')
    command = ['cmd.exe', '/d', '/c', str(ROOT / 'work/native/v14/build-lab-1375.cmd')]
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
        from work.native import lab_protocol_v14_1375 as lab
        manifest, digest = lab.verify_build()
        report.update(manifest_sha256=digest, dll_sha256=manifest['dll_sha256'],
                      native_sources=len(manifest['source_sha256']), host_sources=len(manifest['host_source_sha256']),
                      support_sources=len(manifest['support_source_sha256']))
    save(OUT / 'root-single-build-verification-20261008a.json', report)
    print(json.dumps(report))
    require(run.returncode == 0 and unchanged and 'dll_sha256' in report, 'Formal build failed; no retry/rebuild')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('materialize', 'build'))
    args = parser.parse_args()
    (materialize if args.mode == 'materialize' else build)()
