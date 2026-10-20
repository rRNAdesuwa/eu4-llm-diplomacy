"""Root-only fixed startup source materialization and one formal v16 DLL build, no injection."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / 'work/candidates/v16-acceptance-initialization-review'
OUT = ROOT / 'work/runtime/native1375-v16'
PINS = {'work/candidates/v16-acceptance-initialization-review/review.json': 'bfc1654624ad7ed054bf640f9445f566c73ce9e53f32041d8fbc687c4c680929', 'work/candidates/v16-acceptance-initialization-review/candidate-index.json': '710cd5ba13e501ab23cd8587a24cfae868813e6aefd0ad82b430c91941339c60', 'work/review-results/v16-candidate-root-20261008a/validation.json': '29b2d5353dc1f46ec5b75dea25eb76750285102b15b44a26dd87ef32763e73ad', 'work/review-results/v16-acceptance-initialization-action-catalog-20261008a/review.json': '34b01891d7759b8648045f3eb6c5fb340ac9e424f6278d7c5a8049ef0ac7c545', 'work/review-results/v16-native-object-compile-native-inventory-20261008a/review-r2.json': 'b57e14850c402e263981875e397b00717b20aee7b9d8c51bb9e09a579a20b5ad', 'work/review-results/v16-native-object-compile-native-inventory-20261008a/validation.json': 'b137fb63846a101456ec1e8e0dbe0b9aefe21fbb9f9d4c2e577f214825d4b5f0', 'work/candidates/v16-acceptance-initialization-review/native-source-review.json': '1ac15f2466a2feffcc48d7c14fe247176bfce22d685d6cc28690c281fedd92c5'}
SUPPORT = frozenset(('bridge/diplomacy_api.py', 'bridge/diplomacy_lab_http.py',
    'bridge/native_build.py', 'bridge/native_pair_backend.py', 'work/local_config.py',
    'work/native/inject_probe.py', 'work/native/lab_protocol_v9_1375.py',
    'work/probe_diplomacy_current.py'))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def bounded(path):
    require(not path.is_symlink() and not path.is_junction(), 'Artifact must be an ordinary file')
    with path.open('rb') as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    require(len(raw) <= 2 * 1024 * 1024, 'Artifact read budget exceeded')
    return raw


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_new(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    require(path.resolve().is_relative_to(ROOT.resolve()), 'Output escapes repository')
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def save(path, value):
    write_new(path, (json.dumps(value, indent=2) + '\n').encode())


def audited_files():
    data = {}
    for name, digest in PINS.items():
        raw = bounded(ROOT / name)
        require(sha(raw) == digest, 'Fixed review input changed: ' + name)
        data[name] = json.loads(raw)
    independent = data['work/review-results/v16-acceptance-initialization-action-catalog-20261008a/review.json']
    validation = data['work/review-results/v16-candidate-root-20261008a/validation.json']
    require(independent['findings'] == [] and independent['status'] == 'passed_with_no_blocking_findings_in_reviewed_scope'
        and independent['candidate_review']['sha256'] == PINS['work/candidates/v16-acceptance-initialization-review/review.json']
        and independent['source_scope']['before_after_equal'] is True
        and independent['independent_validation']['python_tests'] == 56
        and independent['independent_validation']['python_test_exit_code'] == 0, 'Independent review differs')
    require(validation['all_stages_exit_zero'] is True and validation['inputs_unchanged'] is True
        and all(r['exit_code'] == 0 for r in validation['runs']), 'Root validation differs')
    check = subprocess.run([sys.executable, '-B', str(CANDIDATE / 'prepare.py'), '--check'],
        cwd=ROOT, capture_output=True, timeout=30)
    require(check.returncode == 0, 'Fixed candidate check failed: ' + check.stderr.decode(errors='replace')[:2000])
    index = data['work/candidates/v16-acceptance-initialization-review/candidate-index.json']
    native = data['work/candidates/v16-acceptance-initialization-review/native-source-review.json']['native_source_sha256']
    require(index['counts'] == {'native': 22, 'host': 12, 'support': 8, 'fixture': 5, 'total': 47}
        and len(index['files']) == 47 and len(native) == 22 and SUPPORT <= index['files'].keys(), 'Inventory differs')
    compiled = data['work/review-results/v16-native-object-compile-native-inventory-20261008a/validation.json']
    native_review = data['work/review-results/v16-native-object-compile-native-inventory-20261008a/review-r2.json']
    require(compiled['all_compile_steps_passed'] is True and compiled['sources_unchanged'] is True
        and compiled['all_candidate_inputs_unchanged'] is True and compiled['sources_before'] == compiled['sources_after']
        and compiled['object_cpp_count'] == 9 and compiled['assembly_count'] == 1
        and len(compiled['commands']) == 12 and all(c['exit_code'] == 0 for c in compiled['commands']), 'Compile evidence differs')
    require(native_review['mock_observation']['checks_summary'] == 'checks=69 failures=0'
        and native_review['mock_observation']['event']['acceptance_action'] == 'none'
        and native_review['mock_observation']['event']['acceptance_target'] == 'none'
        and native_review['candidate_review']['sha256'] == PINS['work/candidates/v16-acceptance-initialization-review/review.json'], 'Mock evidence differs')
    for name, digest in native.items():
        key = ('work/candidates/v16-acceptance-initialization-review/files/' + name).replace('/', chr(92))
        require(compiled['sources_before'][key]['sha256'] == digest.lower()
            and native_review['native_sources_after'][name]['sha256'] == digest.lower(), 'Compiled source differs: ' + name)
    files = []
    for name, item in index['files'].items():
        dest = ROOT / name
        require(not Path(name).is_absolute() and '..' not in Path(name).parts
            and dest.resolve().is_relative_to(ROOT.resolve()), 'Target escapes repository')
        raw = bounded(CANDIDATE / 'files' / name)
        require(len(raw) == item['bytes'] and sha(raw) == item['sha256'], 'Source changed: ' + name)
        if name in SUPPORT:
            require(sha(bounded(dest)) == item['sha256'], 'Frozen shared support changed: ' + name)
        else:
            require('v16' in name, 'Nonversioned mutation rejected: ' + name)
            files.append((dest, raw, item['sha256']))
    require(len(files) == 39 and len({str(p) for p, _, _ in files}) == 39, 'New destination count differs')
    return files


def materialize():
    files = audited_files()
    require(all(not p.exists() for p, _, _ in files), 'Versioned source exists; never overwrite')
    OUT.mkdir(parents=True, exist_ok=True)
    require(not any(OUT.iterdir()), 'v16 runtime is not empty')
    save(OUT / 'root-candidate-review-20261008a.json', {
        'schema_version': 1, 'purpose': 'root_v16_r3_materialization_review',
        'reviewed_at_utc': datetime.now(timezone.utc).isoformat(), 'review_pins': PINS,
        'files': {p.relative_to(ROOT).as_posix(): digest for p, _, digest in files},
        'native_count': 22, 'host_count': 12, 'fixture_count': 5, 'unchanged_support_count': 8,
        'game_accessed': False, 'injected': False, 'production_ready': False,
    })
    for dest, raw, _ in files:
        write_new(dest, raw)
    require(all(sha(bounded(p)) == digest for p, _, digest in audited_files()), 'Materialized source differs')
    print(json.dumps({'materialized': True, 'new_files': 39, 'unchanged_support_files': 8, 'game_accessed': False}))


def build():
    files = audited_files()
    require(all(p.is_file() and sha(bounded(p)) == digest for p, _, digest in files), 'Source changed before build')
    source_review = OUT / 'root-candidate-review-20261008a.json'
    review = json.loads(bounded(source_review))
    require(review['review_pins'] == PINS and review['files'] == {p.relative_to(ROOT).as_posix(): d for p, _, d in files},
            'Root source set differs')
    require(not (OUT / 'build.json').exists() and not any(OUT.glob('session-*'))
            and not (OUT / 'eu4_pair_lab_v16_1375.dll').exists(), 'Used runtime; never rebuild')
    intent = {'schema_version': 1, 'purpose': 'root_v16_single_formal_build',
        'started_at_utc': datetime.now(timezone.utc).isoformat(), 'source_review_sha256': sha(bounded(source_review)),
        'game_accessed': False, 'injection_performed': False}
    save(OUT / 'root-single-build-intent-20261008a.json', intent)
    env = os.environ.copy()
    env['EU4_V16_ROOT_REVIEW_APPROVED'] = '1'
    env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + env.get('PATH', '')
    stdout_path = OUT / 'root-single-build-20261008a.stdout.txt'
    with stdout_path.open('xb') as stdout:
        run = subprocess.run(['cmd.exe', '/d', '/c', str(ROOT / 'work/native/v16/build-lab-1375.cmd')],
            cwd=ROOT, env=env, stdout=stdout, stderr=subprocess.STDOUT, timeout=120)
        stdout.flush()
        os.fsync(stdout.fileno())
    unchanged = all(sha(bounded(p)) == digest for p, _, digest in audited_files())
    report = {'schema_version': 1, 'purpose': intent['purpose'], 'exit_code': run.returncode,
        'source_unchanged_after_build': unchanged, 'stdout_sha256': sha(bounded(stdout_path)),
        'completed_at_utc': datetime.now(timezone.utc).isoformat(), 'game_accessed': False,
        'injected': False, 'production_ready': False}
    if (OUT / 'build.json').is_file():
        sys.path.insert(0, str(ROOT))
        from work.native import lab_protocol_v16_1375 as lab
        manifest, digest = lab.verify_build()
        report.update(manifest_sha256=digest, dll_sha256=manifest['dll_sha256'],
            native_sources=len(manifest['source_sha256']), host_sources=len(manifest['host_source_sha256']),
            support_sources=len(manifest['support_source_sha256']))
    save(OUT / 'root-single-build-verification-20261008a.json', report)
    print(json.dumps(report))
    require(run.returncode == 0 and unchanged and 'dll_sha256' in report, 'Formal build failed; do not retry/rebuild')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('check', 'materialize', 'build'))
    mode = parser.parse_args().mode
    if mode == 'check':
        print(json.dumps({'checked': True, 'new_files': len(audited_files()), 'game_accessed': False}))
    else:
        (materialize if mode == 'materialize' else build)()
