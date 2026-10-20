"""Root-only fixed exact-image source materialization and one formal v17 DLL build, no injection."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / 'work/candidates/v17-acceptance-pin-review'
OUT = ROOT / 'work/runtime/native1375-v17'
PINS = {'work/candidates/v17-acceptance-pin-review/review.json': 'ad9d5d2c368e8358cf5e3e6b156f5ccb2b399a7c1c33f989a9e79db0e6d7fd7a', 'work/candidates/v17-acceptance-pin-review/candidate-index.json': '43552adb80412ddbf21e1dfc608c3aca44f5cb178229a40a5fc0714282016a3a', 'work/candidates/v17-acceptance-pin-review/native-source-review.json': '120bdc29f85634226aefcf07e3cc4914f7201e169a6edcfefaeb296344fabc7b', 'work/review-results/v17-candidate-root-20261008a/validation.json': 'dbd8515495bd8ab37f41d026a1843fa18c9ff6f564c890c721592675303c1455', 'work/review-results/v17-python-external-api-20261008a/review.json': '36dacbd380b54f61efa8ca517f6e26438d51b02d303c3ccf95065fc3cf76eb15', 'work/review-results/v17-python-external-api-20261008a/validation-final.json': '98202d3e7fbb789a90b5072f774a088585c3db3167b4d5717b7bc7f89bdb39da', 'work/review-results/v17-native-object-compile-native-inventory-20261008a/review-r2.json': 'c041ce073991df9df0012c04dc79653ffa59b0edf0901de5e8bfbb95cd14172d', 'work/review-results/v17-native-object-compile-native-inventory-20261008a/validation.json': '16c6298bb3a46dcac39697c87182e24c89dd6f492c56903f4d7d4699aa5dedf7', 'work/review-results/v17-native-object-compile-native-inventory-20261008a/source-and-pin-review.json': '17926e5a591835ac1eecee3b115d56ab696e7bbd877c52e43cdf20c7eb0cd9fe'}
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
    independent = data['work/review-results/v17-python-external-api-20261008a/review.json']
    python_validation = data['work/review-results/v17-python-external-api-20261008a/validation-final.json']
    validation = data['work/review-results/v17-candidate-root-20261008a/validation.json']
    require(independent['findings'] == [] and independent['status'] == 'no_blocking_findings_in_reviewed_delta'
        and independent['candidate_review']['sha256'] == PINS['work/candidates/v17-acceptance-pin-review/review.json']
        and independent['inputs_unchanged'] is True and independent['all_shell_sessions_collected'] is True
        and independent['validation']['sha256'] == PINS['work/review-results/v17-python-external-api-20261008a/validation-final.json']
        and python_validation['inputs_unchanged'] is True and python_validation['outputs_compared'] == 47
        and len(python_validation['stages']) == 3 and all(s['exit_code'] == 0 for s in python_validation['stages'])
        and python_validation['stages'][2]['test_methods'] == 8, 'Independent Python review differs')
    pin_review = data['work/review-results/v17-native-object-compile-native-inventory-20261008a/source-and-pin-review.json']
    require(pin_review['code_pin_count'] == 8 and pin_review['code_bytes'] == 945
        and pin_review['pe_header_checks_passed'] == 6 and len(pin_review['data_checks']) == 13
        and all(p['source_matches'] is True for p in pin_review['code_pins'])
        and all(p['match'] is True for p in pin_review['data_checks'])
        and pin_review['game_sha256'].upper() == '9AD3EFE1AF169F40EE577F9DAE5DEBBC87AF6FB8B5450FB345EBF110DC4D771A',
        'Independent exact image review differs')
    require(validation['all_stages_exit_zero'] is True and validation['inputs_unchanged'] is True
        and all(r['exit_code'] == 0 for r in validation['runs']), 'Root validation differs')
    check = subprocess.run([sys.executable, '-B', str(CANDIDATE / 'prepare.py'), '--check'],
        cwd=ROOT, capture_output=True, timeout=30)
    require(check.returncode == 0, 'Fixed candidate check failed: ' + check.stderr.decode(errors='replace')[:2000])
    index = data['work/candidates/v17-acceptance-pin-review/candidate-index.json']
    native = data['work/candidates/v17-acceptance-pin-review/native-source-review.json']['native_source_sha256']
    require(index['counts'] == {'native': 22, 'host': 12, 'support': 8, 'fixture': 5, 'total': 47}
        and len(index['files']) == 47 and len(native) == 22 and SUPPORT <= index['files'].keys(), 'Inventory differs')
    compiled = data['work/review-results/v17-native-object-compile-native-inventory-20261008a/validation.json']
    native_review = data['work/review-results/v17-native-object-compile-native-inventory-20261008a/review-r2.json']
    require(compiled['all_compile_steps_passed'] is True and compiled['sources_unchanged'] is True
        and compiled['all_candidate_inputs_unchanged'] is True and compiled['sources_before'] == compiled['sources_after']
        and compiled['object_cpp_count'] == 9 and compiled['assembly_count'] == 1
        and len(compiled['commands']) == 12 and all(c['exit_code'] == 0 for c in compiled['commands']), 'Compile evidence differs')
    require(native_review['mock_observation']['checks_summary'] == 'checks=69 failures=0'
        and native_review['mock_observation']['event']['acceptance_action'] == 'none'
        and native_review['mock_observation']['event']['acceptance_target'] == 'none'
        and native_review['candidate_review']['sha256'] == PINS['work/candidates/v17-acceptance-pin-review/review.json'], 'Mock evidence differs')
    for name, digest in native.items():
        key = ('work/candidates/v17-acceptance-pin-review/files/' + name).replace('/', chr(92))
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
            require('v17' in name, 'Nonversioned mutation rejected: ' + name)
            files.append((dest, raw, item['sha256']))
    require(len(files) == 39 and len({str(p) for p, _, _ in files}) == 39, 'New destination count differs')
    return files



def materialize():
    files = audited_files()
    require(all(not p.exists() for p, _, _ in files), 'Versioned source exists; never overwrite')
    OUT.mkdir(parents=True, exist_ok=True)
    require(not any(OUT.iterdir()), 'v17 runtime is not empty')
    save(OUT / 'root-candidate-review-20261008a.json', {
        'schema_version': 1, 'purpose': 'root_v17_r3_materialization_review',
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
            and not (OUT / 'eu4_pair_lab_v17_1375.dll').exists(), 'Used runtime; never rebuild')
    intent = {'schema_version': 1, 'purpose': 'root_v17_single_formal_build',
        'started_at_utc': datetime.now(timezone.utc).isoformat(), 'source_review_sha256': sha(bounded(source_review)),
        'game_accessed': False, 'injection_performed': False}
    save(OUT / 'root-single-build-intent-20261008a.json', intent)
    env = os.environ.copy()
    env['EU4_V17_ROOT_REVIEW_APPROVED'] = '1'
    env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + env.get('PATH', '')
    stdout_path = OUT / 'root-single-build-20261008a.stdout.txt'
    with stdout_path.open('xb') as stdout:
        run = subprocess.run(['cmd.exe', '/d', '/c', str(ROOT / 'work/native/v17/build-lab-1375.cmd')],
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
        from work.native import lab_protocol_v17_1375 as lab
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
