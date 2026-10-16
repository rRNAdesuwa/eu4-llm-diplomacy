"""R86 retained metadata-only R2. Preserve R1 and never rerun successful phases."""
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'work/reports/war-peace-api-20261016-r86-cc220-actual-source/'
HERE = ROOT / PREFIX
SELF = 'work/r86_repair_prepared_metadata_r2_20261016.py'
OLD_VERIFY = 'work/r86_verify_prepared_delivery_20261016.py'
FILES = [SELF, OLD_VERIFY] + [PREFIX + n for n in [
    'prepared-metadata-repair-claim-r2.json',
    'prepared-final-manifest.json', 'prepared-delivery.json', 'delivery-manifest.json',
    'prepared-read-accounting.json', 'prepared-filecheck.json', 'source-manifest.json',
    'prepared-seal.stdout.txt', 'prepared-seal.stderr.txt', 'prepared-seal-command.json',
    'prepared-delivery-verify-failure.json', 'delivery-verification.stdout.txt',
    'delivery-verification.stderr.txt', 'delivery-verification-command.json']]
events = []
used = 0
peak = 0


class PMC(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in ('peak_working', 'working', 'peak_paged', 'paged',
        'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile', 'private')]


def guard():
    global peak
    c = PMC()
    c.cb = ctypes.sizeof(c)
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.GetCurrentProcess.restype = wintypes.HANDLE
    f = ctypes.WinDLL('psapi', use_last_error=True).GetProcessMemoryInfo
    f.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    f.restype = wintypes.BOOL
    if not f(k.GetCurrentProcess(), ctypes.byref(c), c.cb):
        raise RuntimeError('Own memory counter')
    peak = max(peak, int(c.private), int(c.peak_pagefile))
    if not (0 < peak <= 805306368 and peak < 1073741824):
        raise RuntimeError('Own memory guard')


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def read(path, phase, expected=None):
    global used
    guard()
    if path not in FILES:
        raise RuntimeError('Only explicit closed owned metadata files')
    fp = ROOT / path
    n = fp.stat().st_size
    if n > 4194304 or used + n > 2097152:
        raise RuntimeError('R2 metadata read subbudget')
    raw = fp.read_bytes()
    used += len(raw)
    p = pin(raw)
    events.append({'path': path, 'phase': phase, **p})
    if len(raw) != n or (expected is not None and p != expected):
        raise RuntimeError('Closed metadata pin differs')
    return raw


def write(name, value):
    raw = (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode()
    with (HERE / name).open('xb') as f:
        f.write(raw)
    return {'path': PREFIX + name, **pin(raw)}


def main():
    if sys.argv[1:] or any((HERE / n).exists() for n in ('run-authorization.json', 'claim.json', 'capture.json', 'owned-code.json', 'failure.json')):
        raise RuntimeError('Source-only repair; no override or actual artifacts')
    write('prepared-metadata-repair-claim-r2.json', {'schema': 'EU4-R86-RETAINED-METADATA-REPAIR-CLAIM/1',
        'only_closed_log_pin_metadata_and_failure_provenance': True, 'successful_source_build_or_check_repeated': False,
        'actual_authorized': False})
    raw = {p: read(p, 'closed_metadata_before') for p in FILES}
    old = json.loads(raw[PREFIX + 'prepared-final-manifest.json'])
    if pin(raw[PREFIX + 'prepared-final-manifest.json']) != {'bytes': 19704, 'sha256': '6225636d723f4a51312598791e9b2ef615139affa246ff9cb11f4e0d7e17f044'}:
        raise RuntimeError('Preserved R1 manifest pin')
    base = json.loads(raw[PREFIX + 'source-manifest.json'])
    base_pin = pin(raw[PREFIX + 'source-manifest.json'])
    if base_pin != {'bytes': 22473, 'sha256': '74f6c8f8eeeadea9e4216c7b37e2a8034e9fb7967d8dfe7167c7ee1ffd143472'}:
        raise RuntimeError('Core source manifest changed')
    firstcheck = json.loads(raw[PREFIX + 'prepared-filecheck.json'])
    failed = json.loads(raw[PREFIX + 'prepared-delivery-verify-failure.json'])
    if not (firstcheck['passed'] and firstcheck['read_bytes'] == 488888
            and 'prepared-seal.stdout.txt' in failed['error']):
        raise RuntimeError('Exact previous success/failure scope')
    stdout_path = PREFIX + 'prepared-seal.stdout.txt'
    stderr_path = PREFIX + 'prepared-seal.stderr.txt'
    if old['files'][stdout_path]['bytes'] != 0 or len(raw[stdout_path]) == 0:
        raise RuntimeError('Expected live-output inventory mismatch')
    before = {p: pin(v) for p, v in raw.items()}
    for path, expected in before.items():
        read(path, 'closed_metadata_after', expected)
    guard()
    files = dict(old['files'])
    old_stdout_pin = files[stdout_path]
    old_stderr_pin = files[stderr_path]
    files[stdout_path] = before[stdout_path]
    files[stderr_path] = before[stderr_path]
    # Add preserved R1 failure/current closed logs and R2 source. The R2 running
    # stdout/stderr files are deliberately not selected, enumerated or pinned.
    for path, p in before.items():
        if path in files and path not in (stdout_path, stderr_path) and files[path] != p:
            raise RuntimeError('Unexpected non-log R1 pin change')
        files[path] = p
    changed_old_paths = [p for p in old['files'] if old['files'][p] != files[p]]
    if changed_old_paths != [stdout_path]:
        raise RuntimeError('Only the completed nonempty stdout pin may differ')
    unchanged_old_count = len(old['files']) - len(changed_old_paths)
    reserve = 1048576
    manual = 1048576
    prior_retained = 488888 + 755660
    retained_upper = prior_retained + failed['read_bytes'] + used + manual + reserve
    if retained_upper >= 16777216:
        raise RuntimeError('Cumulative retained16MiB budget')
    correction = {'schema': 'EU4-R86-PREPARED-METADATA-CORRIGENDUM/2', 'sealed': True,
        'preserved_R1_final_manifest': {'path': PREFIX + 'prepared-final-manifest.json', **before[PREFIX + 'prepared-final-manifest.json']},
        'preserved_R1_failed_verifier': {'path': PREFIX + 'prepared-delivery-verify-failure.json', **before[PREFIX + 'prepared-delivery-verify-failure.json']},
        'cause': 'R1 enumerated its still-open redirected stdout/stderr. The stdout was0B at inventory and received the final print only after its pin was sealed.',
        'R1_final_delivery_pin_check': 'failed, not accepted as a clean final receipt',
        'successful_core_source_build_and_prepared_filecheck': 'remain passed; never rerun or rewritten',
        'closed_stdout_before': old_stdout_pin, 'closed_stdout_after': before[stdout_path],
        'closed_stderr_before': old_stderr_pin, 'closed_stderr_after': before[stderr_path],
        'changed_preexisting_R1_paths': changed_old_paths, 'unchanged_preexisting_R1_pin_count': unchanged_old_count,
        'new_R2_live_stdout_stderr_excluded_from_manifest': True,
        'core_source_manifest': {'path': PREFIX + 'source-manifest.json', **base_pin},
        'producer': old['producer'], 'entry_seed': old['entry_seed'],
        'producer_or_old_programs_executed': False, 'actual_authorized': False,
        'PE_or_engine_access': False, 'native_ready': False}
    correction_pin = write('prepared-metadata-corrigendum-r2.json', correction)
    account_pin = write('prepared-read-accounting-r2.json', {'schema': 'EU4-R86-PREPARED-READ-ACCOUNT/2', 'sealed': True,
        'source_build_explicit_reads': 506047, 'source_build_upper': 4700351, 'source_build_limit': 33554432,
        'prior_successful_retained_reads': prior_retained, 'R1_failed_late_verifier_reads': failed['read_bytes'],
        'R2_metadata_seal_events': events, 'R2_metadata_seal_reads': used,
        'one_cumulative_retained_manual_upper': manual, 'R2_final_verify_reserve': reserve,
        'retained_cumulative_upper': retained_upper, 'retained_limit': 16777216,
        'source_core_changed': False, 'PE_or_engine_stat_open': False,
        'all_failure_reads_counted': True, 'not_whole_OS_loader_IO': True})
    files[correction_pin['path']] = {k: correction_pin[k] for k in ['bytes', 'sha256']}
    files[account_pin['path']] = {k: account_pin[k] for k in ['bytes', 'sha256']}
    final = dict(old)
    final.update(schema='EU4-R86-PREPARED-FINAL-MANIFEST/2',
        stage='source_only_author_complete_pending_non_author_source_review_r2', files=files,
        file_count=len(files), retained_upper=retained_upper,
        R1_final_delivery_pin_check_failed=True, metadata_corrigendum=correction_pin,
        successful_core_source_or_filecheck_rerun=False,
        new_running_output_streams_pinned=False)
    final_pin = write('prepared-final-manifest-r2.json', final)
    old_delivery = json.loads(raw[PREFIX + 'prepared-delivery.json'])
    delivery = dict(old_delivery)
    delivery.update(schema='EU4-R86-PREPARED-DELIVERY/2', prepared_final_manifest=final_pin,
        source_read_accounting=account_pin, metadata_corrigendum=correction_pin,
        R1_delivery_pin_check_failed=True, R2_final_filecheck_pending=True)
    delivery_pin = write('prepared-delivery-r2.json', delivery)
    publication_pin = write('delivery-manifest-r2.json', {'schema': 'EU4-R86-PREPARED-DELIVERY-MANIFEST/2', 'sealed': True,
        'files': {p['path']: {k: p[k] for k in ['bytes', 'sha256']} for p in [final_pin, delivery_pin, correction_pin, account_pin]},
        'R1_retained_unchanged': True, 'R1_final_delivery_pin_check_failed': True,
        'only_R2_metadata_deliverable_selected': True, 'source_core_unchanged': True,
        'actual_authorized': False, 'non_author_source_review_claimed': False, 'all_authority': False})
    print(json.dumps({'ok': True, 'prepared_final_manifest': final_pin, 'prepared_delivery': delivery_pin,
        'delivery_manifest': publication_pin, 'corrigendum': correction_pin, 'read_accounting': account_pin,
        'R1_failed_verify_reads': failed['read_bytes'], 'R2_seal_reads': used,
        'retained_cumulative_upper': retained_upper, 'text_files': len(files),
        'old_unchanged': unchanged_old_count, 'actual_authorized': False, 'peak': peak}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        write('prepared-metadata-repair-failure-r2.json', {'error': str(exc), 'traceback': traceback.format_exc(),
            'events': events, 'read_bytes': used, 'actual_authorized': False})
        print(json.dumps({'ok': False, 'error': str(exc), 'read_bytes': used}))
        sys.exit(1)
