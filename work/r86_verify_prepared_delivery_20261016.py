"""First R86 late delivery/local-file verification, no upstream re-open."""
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
SELF = 'work/r86_verify_prepared_delivery_20261016.py'
LIMIT = 524288
events = []
cache = {}
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


def read(path, expected=None):
    global used
    if path in cache:
        raw = cache[path]
        if expected is not None and pin(raw) != expected:
            raise RuntimeError('Cached local pin differs')
        return raw
    guard()
    if not (path.startswith(PREFIX) or path.startswith('work/r86_')):
        raise RuntimeError('Upstream/engine/PE read prohibited by local verifier')
    fp = ROOT / path
    n = fp.stat().st_size
    if n > 4194304 or used + n > LIMIT:
        raise RuntimeError('Late verification reserve')
    raw = fp.read_bytes()
    used += len(raw)
    p = pin(raw)
    events.append({'path': path, **p})
    if len(raw) != n or (expected is not None and p != expected):
        raise RuntimeError('Local prepared pin differs: ' + path)
    cache[path] = raw
    return raw


def main():
    read(SELF)
    publication = json.loads(read(PREFIX + 'delivery-manifest.json', {'bytes': 1107, 'sha256': 'ede2ebc320c808af94cd610f41ded2db232056d8cd503087b9694c7477db5d49'}))
    for path, expected in publication['files'].items():
        read(path, expected)
    final = json.loads(cache[PREFIX + 'prepared-final-manifest.json'])
    base_raw = read(PREFIX + 'source-manifest.json', {'bytes': 22473, 'sha256': '74f6c8f8eeeadea9e4216c7b37e2a8034e9fb7967d8dfe7167c7ee1ffd143472'})
    base = json.loads(base_raw)
    # Explicit extraction of triple fields avoids treating a path as pin content.
    check_ref = final['actual_source_prepost_witness']
    check = json.loads(read(check_ref['path'], {k: check_ref[k] for k in ['bytes', 'sha256']}))
    external_witnesses = []
    for path, expected in final['files'].items():
        if path.startswith(PREFIX) or path.startswith('work/r86_'):
            read(path, expected)
        else:
            if base['actual_source_pins'].get(path) != expected:
                raise RuntimeError('External text not in the exact actual-source graph')
            records = [x for x in check['read_events'] if x['path'] == path]
            if len(records) != 2 or any({k: x[k] for k in ['bytes', 'sha256']} != expected for x in records):
                raise RuntimeError('Prior source pre/post witness differs')
            external_witnesses.append({'path': path, **expected})
    for name in ['prepared-seal.stdout.txt', 'prepared-seal.stderr.txt', 'prepared-seal-command.json']:
        read(PREFIX + name)
    if not (final['sealed'] and final['file_count'] == len(final['files']) == 59
            and final['actual_authorized'] is False and publication['actual_authorized'] is False
            and len(base['actual_source_pins']) == 22 and len(base['decoder_expected_witness_pins']) == 38):
        raise RuntimeError('Prepared source-only graph/count')
    if any((HERE / n).exists() for n in ('run-authorization.json', 'claim.json', 'capture.json', 'owned-code.json', 'failure.json')):
        raise RuntimeError('Unexpected actual artifacts')
    result = {'schema': 'EU4-R86-PREPARED-DELIVERY-VERIFY/1', 'sealed': True, 'passed': True,
        'scope': 'new_owned_delivery_pins_plus_prior_exact_upstream_source_witnesses',
        'read_events': events, 'read_bytes': used, 'limit': LIMIT,
        'upstream_sources_not_reopened': external_witnesses, 'upstream_witness_count': len(external_witnesses),
        'text_pins_in_prepared_final_manifest': 59, 'actual_source_pins': 22, 'engine_metadata_only': 38,
        'source_build_upper': 4700351, 'retained_upper_including_this_reserve': 2817412,
        'peak_committed_bytes': peak, 'producer_imported_or_executed': False,
        'PE_stat_open_hash': False, 'engine_body_stat_open': False, 'decoder_imported': False,
        'old_programs_or_tests_executed': False, 'actual_authorized': False, 'native_ready': False,
        'non_author_source_review_claimed': False, 'game_access': False,
        'all_shells_collected_on_return': True}
    raw = (json.dumps(result, indent=2) + '\n').encode()
    with (HERE / 'prepared-delivery-verification.json').open('xb') as f:
        f.write(raw)
    print(json.dumps({'passed': True, 'local_checked_files': len(events), 'read_bytes': used,
        'receipt_bytes': len(raw), 'receipt_sha256': hashlib.sha256(raw).hexdigest(),
        'upstream_witnesses_not_reopened': len(external_witnesses), 'actual_authorized': False}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        with (HERE / 'prepared-delivery-verify-failure.json').open('x', encoding='utf-8') as f:
            json.dump({'error': str(exc), 'traceback': traceback.format_exc(), 'events': events,
                       'read_bytes': used, 'actual_authorized': False}, f, indent=2)
        raise
