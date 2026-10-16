from pathlib import Path
import ctypes, hashlib, json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/reports/support-heir-current-controller-source-independent-review-20261016-r1'
events = []

def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def read(path, expected=None):
    assert path.stat().st_size <= 4194304
    raw = path.read_bytes()
    value = pin(raw)
    events.append({'path': path.relative_to(ROOT).as_posix(), **value})
    if expected is not None:
        assert value == expected, path
    return raw

def save(name, data):
    raw = (json.dumps(data, indent=2, sort_keys=True) + '\n').encode()
    with (OUT / name).open('xb') as stream:
        stream.write(raw)
    return {'path': (OUT / name).relative_to(ROOT).as_posix(), **pin(raw)}

def memory():
    class C(ctypes.Structure):
        _fields_ = [('cb', ctypes.c_ulong), ('faults', ctypes.c_ulong)] + [(n, ctypes.c_size_t) for n in ['peakRSS', 'RSS', 'peakPaged', 'paged', 'peakNP', 'NP', 'committed', 'peakCommitted']]
    c = C(); c.cb = ctypes.sizeof(c)
    get = ctypes.windll.kernel32.GetCurrentProcess; get.restype = ctypes.c_void_p
    assert ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(get()), ctypes.byref(c), c.cb)
    assert max(c.RSS, c.committed) <= 805306368
    return {'RSS': c.RSS, 'commit': c.committed, 'peakRSS': c.peakRSS, 'peakCommit': c.peakCommitted}

manifest_raw = read(OUT / 'manifest.json', {'bytes': 33412, 'sha256': 'a39124ca367c79ee2a068641da9bb68e2d446917b45af9bb0a879a056a5e3367'})
manifest = json.loads(manifest_raw)
assert manifest['sealed'] is True and manifest['runtime_authorized'] is False
cached = {}
for relative, expected in manifest['local_pins'].items():
    cached[relative] = read(ROOT / relative, expected)
findings_path = (OUT / 'findings.json').relative_to(ROOT).as_posix()
findings_raw = cached[findings_path]
findings = json.loads(findings_raw)
assert manifest['findings_pin'] == {'path': findings_path, **pin(findings_raw)}
assert findings['sealed'] is True and findings['passed'] is True and findings['blocking_findings'] == []
assert findings['source_ready'] is True and findings['runtime_authorized'] is False
assert findings['source_pins'] == manifest['source_pins']
assert len(findings['source_pins']) == 69 and len(findings['source_after']) == 69
after = {v['path']: {'bytes': v['bytes'], 'sha256': v['sha256']} for v in findings['source_after']}
assert after == findings['source_pins']
subjects = {key: findings[key] for key in ['subject_source_manifest', 'subject_controller_pin', 'subject_child_pin', 'subject_adapter_pin']}
for key, value in subjects.items():
    assert set(value) == {'path', 'bytes', 'sha256'}
    assert findings['source_pins'][value['path']] == {k: value[k] for k in ('bytes', 'sha256')}
assert all(findings[k] == 0 for k in ['author_modules_or_helpers_executed', 'author_tests_executed', 'candidate_CLI_executed', 'PE_engine_decoder_access', 'PID_UI_process_access', 'native_game_calls', 'requests'])
assert all(findings[k] is False for k in ['real_env_access', 'native_ready', 'selected_effect_verified', 'world_lease', 'atomic_snapshot', 'authorizes_retry'])
run_raw = read(OUT / 'reviewer-r2-receipt.json'); run = json.loads(run_raw)
assert run['exit_code'] == 0 and run['direct_child_collected'] is True
read(OUT / 'reviewer-r2.stdout', run['stdout'])
read(OUT / 'reviewer-r2.stderr', run['stderr'])
for name in ['work/review_support_controller_20261016.py', 'work/repair_support_controller_review_20261016.py', 'work/continue_support_controller_review_20261016.py']:
    read(ROOT / name)
read(Path(__file__).resolve())
charged = sum(e['bytes'] for e in events)
assert charged < findings['source_accounting']['manual_own_scripts_and_finalcheck_allowance']
verification = save('verification.json', {
    'schema': 'EU4-SUPPORT-CONTROLLER-INDEPENDENT-VERIFICATION/1', 'sealed': True, 'passed': True,
    'method': 'Check own sealed pins and prior original-source before/after equality; no author execution and no third original-source pass.',
    'checked_local_pins': len(manifest['local_pins']), 'original_source_before_after_count': 69,
    'four_full_subjects': subjects, 'manifest_pin': {'path': (OUT / 'manifest.json').relative_to(ROOT).as_posix(), **pin(manifest_raw)},
    'findings_pin': manifest['findings_pin'], 'read_events': events, 'read_bytes': charged,
    'charged_within_existing_2MiB_manual_finalcheck_allowance': True,
    'reviewer_failure_precision': 'The first seal failure source is exact preserved bytes. Its saved stderr text was transcribed from the failed exec tool result, not retained raw process tee. The corrected source alone was run once; no author or fake case was executed.',
    'R2_reviewer_receipt_pin': {'path': (OUT / 'reviewer-r2-receipt.json').relative_to(ROOT).as_posix(), **pin(run_raw)},
    'all_shells_collected': True, 'runtime_authorized': False, 'native_ready': False, 'memory': memory(),
})
extra = {e['path']: {'bytes': e['bytes'], 'sha256': e['sha256']} for e in events if e['path'] not in manifest['local_pins']}
extra[verification['path']] = {k: verification[k] for k in ('bytes', 'sha256')}
publication = save('publication-manifest.json', {
    'schema': 'EU4-SUPPORT-CONTROLLER-INDEPENDENT-PUBLICATION/1', 'sealed': True,
    'canonical_manifest_pin': {'path': (OUT / 'manifest.json').relative_to(ROOT).as_posix(), **pin(manifest_raw)},
    'findings_pin': manifest['findings_pin'], 'verification_pin': verification,
    'extra_source_and_review_receipt_pins': extra, 'runtime_authorized': False, 'native_ready': False,
    'all_shells_collected': True,
})
print(json.dumps({'findings': manifest['findings_pin'], 'manifest': {'path': (OUT / 'manifest.json').relative_to(ROOT).as_posix(), **pin(manifest_raw)},
                  'verification': verification, 'publication': publication, 'subjects': subjects,
                  'verification_read_bytes': charged, 'memory': memory(), 'all_shells_collected': True}))
