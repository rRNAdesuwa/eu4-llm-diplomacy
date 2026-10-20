from pathlib import Path
import ctypes, hashlib, json

ROOT = Path(__file__).resolve().parents[1]
BASE = 'work/reports/war-peace-api-20261016-r87-dual-frontier-source/'
OUT = ROOT / (BASE + 'actual-sealed-r1')
events = []

def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def read(path, expected=None):
    assert path.stat().st_size <= 4194304
    raw = path.read_bytes(); value = pin(raw)
    events.append({'path': path.relative_to(ROOT).as_posix(), **value})
    if expected is not None:
        assert value == expected, path
    return raw

def save(name, value):
    raw = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    with (OUT / name).open('xb') as stream:
        stream.write(raw)
    return {'path': (OUT / name).relative_to(ROOT).as_posix(), **pin(raw)}

def memory():
    class C(ctypes.Structure):
        _fields_ = [('cb', ctypes.c_ulong), ('faults', ctypes.c_ulong)] + [(n, ctypes.c_size_t) for n in ['peakRSS', 'RSS', 'peakPaged', 'paged', 'peakNP', 'NP', 'committed', 'peakCommitted']]
    value = C(); value.cb = ctypes.sizeof(value)
    get = ctypes.windll.kernel32.GetCurrentProcess; get.restype = ctypes.c_void_p
    assert ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(get()), ctypes.byref(value), value.cb)
    assert max(value.RSS, value.committed) <= 805306368
    return {'RSS': value.RSS, 'commit': value.committed, 'peakRSS': value.peakRSS, 'peakCommit': value.peakCommitted}

mr = read(OUT / 'actual-manifest.json', {'bytes': 34662, 'sha256': '71e766158fdaf6f80a2dc55bf5c4fb8177bfcfcdaee35f1f7860c1fec0828b0d'})
manifest = json.loads(mr); cached = {}
assert manifest['sealed'] is True and manifest['author_preview_only'] is True and manifest['independent_actual_review_pending'] is True
for relative, expected in manifest['local_pins'].items():
    cached[relative] = read(ROOT / relative, expected)
flags = ['native_ready', 'callable', 'reader_adoption_allowed', 'selected_effect_verified', 'world_lease', 'atomic_snapshot',
         'authorizes_retry', 'ownership_transfer_verified', 'whole_function_closed', 'further_actual_authorized']
assert all(manifest[k] is False for k in flags)
contract = json.loads(cached[manifest['subject_contract_pin']['path']]); accounting = json.loads(cached[manifest['accounting_pin']['path']])
assert all(contract[k] is False for k in flags)
assert contract['scope']['local_normal_CFG_closed_source_flag'] is False
assert contract['scope']['instructions'] == 61 and contract['scope']['unique_decoded_bytes'] == 210
assert contract['normal_return_and_stack']['borrows_alive_proved'] is False
before = {v['path']: {k: v[k] for k in ('bytes', 'sha256')} for v in accounting['source_before']}
after = {v['path']: {k: v[k] for k in ('bytes', 'sha256')} for v in accounting['source_after']}
assert before == after == manifest['source_pins'] and len(before) == 52
assert len(manifest['engine_metadata_witness_pins']) == 38 and manifest['engine_bodies_opened_in_this_seal'] == 0
delivery_raw = read(OUT / 'delivery.json', {'bytes': 2648, 'sha256': '164d006777c54eb5489ef585483adc349d1f43403cc982321c544e21b6c59f0a'})
delivery = json.loads(delivery_raw)
assert delivery['actual_manifest_pin'] == {'path': (OUT / 'actual-manifest.json').relative_to(ROOT).as_posix(), **pin(mr)}
assert delivery['contract_pin'] == manifest['subject_contract_pin']
assert all(delivery[k] is False for k in flags)
run_raw = read(OUT / 'seal-r2-receipt.json'); run = json.loads(run_raw)
assert run['exit_code'] == 0 and run['direct_child_collected'] is True and run['actual_acquisition_reexecuted'] is False
read(OUT / 'seal-r2.stdout', run['stdout']); read(OUT / 'seal-r2.stderr', run['stderr'])
for name in ['work/seal_r87_actual_20261016.py', 'work/continue_r87_actual_seal_20261016.py']:
    read(ROOT / name)
read(Path(__file__).resolve())
total = sum(v['bytes'] for v in events)
assert total < 1572864
filecheck = save('filecheck.json', {
    'schema': 'EU4-R87-AUTHOR-RETAINED-FILECHECK/1', 'sealed': True, 'passed': True,
    'method': 'First own sealed-file check; original52 source before/after equality retained in accounting, no third original-source pass and no author producer/decoder execution.',
    'subject_actual_manifest': delivery['actual_manifest_pin'], 'subject_contract_pin': manifest['subject_contract_pin'],
    'subject_capture_pin': manifest['subject_capture_pin'], 'subject_owned_pin': manifest['subject_owned_pin'],
    'checked_local_pins': len(manifest['local_pins']), 'original_source_before_after_count': 52,
    'engine_metadata_only_count': 38, 'read_events': events, 'read_bytes': total,
    'firstcheck_charge_within_existing_2MiB_manual_finalcheck_allowance': True,
    'seal_failure_and_R2_repair': 'Retained exact R1 sealer source/exec stderr text; field mapping/accounting-only continuation; actual source/capture unchanged and acquisition never repeated.',
    'own_seal_run_collected': True, 'actual_independent_review_pending': True,
    'native_ready': False, 'ownership_transfer_verified': False, 'further_actual_authorized': False,
    'PE_engine_decoder_game_access': 0, 'all_shells_collected': True, 'memory': memory(),
})
extras = {v['path']: {k: v[k] for k in ('bytes', 'sha256')} for v in events if v['path'] not in manifest['local_pins']}
extras[filecheck['path']] = {k: filecheck[k] for k in ('bytes', 'sha256')}
publication = save('publication.json', {
    'schema': 'EU4-R87-AUTHOR-ACTUAL-PUBLICATION/1', 'sealed': True,
    'actual_manifest_pin': delivery['actual_manifest_pin'], 'delivery_pin': {'path': (OUT / 'delivery.json').relative_to(ROOT).as_posix(), **pin(delivery_raw)},
    'filecheck_pin': filecheck, 'extra_sealer_sources_logs_receipt_pins': extras,
    'author_delivery_only': True, 'independent_actual_review_pending': True,
    'source_upper_bytes': manifest['source_upper_bytes'], 'retained_upper_bytes': manifest['retained_upper_bytes'],
    'all_shells_collected': True, 'native_ready': False, 'further_actual_authorized': False,
})
print(json.dumps({'filecheck': filecheck, 'publication': publication, 'read_bytes': total,
                  'source_upper': manifest['source_upper_bytes'], 'retained_upper': manifest['retained_upper_bytes'],
                  'memory': memory(), 'all_shells_collected': True}))
