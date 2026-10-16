"""R85 first local-only source-plan pin check, no historical source reopening."""
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'work/reports/war-peace-api-20261016-r85-cc220-cache-source-plan/'
OUT = ROOT / PREFIX
SELF = 'work/r85_check_local_20261016.py'
events = []
used = 0
peak = 0


class PMC(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]


def guard():
    global peak
    p = PMC()
    p.cb = ctypes.sizeof(p)
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.GetCurrentProcess.restype = wintypes.HANDLE
    fn = ctypes.WinDLL('psapi', use_last_error=True).GetProcessMemoryInfo
    fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    fn.restype = wintypes.BOOL
    if not fn(k.GetCurrentProcess(), ctypes.byref(p), p.cb):
        raise RuntimeError('self memory counter')
    peak = max(peak, p.PeakWorkingSetSize)
    if p.WorkingSetSize > 768 * 1024 * 1024 or p.PeakWorkingSetSize > 1024 * 1024 * 1024:
        raise RuntimeError('memory guard')


def read(path, expected=None):
    global used
    guard()
    if not (path.startswith(PREFIX) or path.startswith('work/r85_')):
        raise RuntimeError('upstream original read prohibited in local check')
    fp = ROOT / path
    n = fp.stat().st_size
    if n > 4194304 or used + n > 200000:
        raise RuntimeError('local verification reserve')
    raw = fp.read_bytes()
    used += len(raw)
    p = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    events.append({'path': path, **p})
    if len(raw) != n or (expected is not None and expected != p):
        raise RuntimeError('local pin differs: ' + path)
    return raw


def main():
    read(SELF)
    manifest = json.loads(read(PREFIX + 'manifest.json', {'bytes': 4519, 'sha256': '96c00855db91be222e5b8d6b2e2daea93f61570ceacab6062d256edace18f365'}))
    cached = {}
    for path, expected in manifest['inputs'].items():
        cached[path] = read(path, expected)
    for item in manifest['outputs']:
        cached[item['path']] = read(item['path'], {k: item[k] for k in ['bytes', 'sha256']})
    plan = json.loads(cached[PREFIX + 'source-plan.json'])
    finding = json.loads(cached[PREFIX + 'findings.json'])
    assert plan['sealed'] is True and plan['stage'] == 'author_source_plan_pending_non_author_review'
    assert plan['current_cache_result']['present'] is False and plan['current_cache_result']['row_count'] is None
    assert plan['conditional_native_static_scope_if_no_usable_cache']['actual_authorized'] is False
    assert plan['conditional_native_static_scope_if_no_usable_cache']['entry_rva'] == '0xcc220'
    assert finding['sealed'] and finding['passed'] and finding['blocking_findings'] == []
    assert all(type(x) is bool and x is False for x in finding['authority'].values())
    assert finding['accounting']['whole_stage_upper'] == 3551715 < 8388608
    assert len(finding['source_pins']) == 7
    for name in ['seal.stdout.txt', 'seal.stderr.txt', 'seal-command.json']:
        read(PREFIX + name)
    receipt = {'schema': 'EU4-R85-LOCAL-FILECHECK/1', 'sealed': True, 'passed': True,
      'scope': 'owned_source_plan_and_final_pin_integrity_only', 'events': events,
      'checked_file_count': len(events), 'read_bytes': used, 'reserve': 200000,
      'whole_stage_upper_with_reserve': 3551715, 'peak_working_set': peak,
      'upstream_original_reads': 0, 'body_semantics_analyzed': False,
      'PE_reads': 0, 'decoder_calls': 0, 'game_access': False, 'native_calls': 0,
      'actual_authorized': False, 'non_author_review_claimed': False,
      'all_shells_collected_on_return': True}
    raw = (json.dumps(receipt, indent=2) + '\n').encode()
    with (OUT / 'verification.json').open('xb') as f:
        f.write(raw)
    print(json.dumps({'ok': True, 'checked_files': len(events), 'read_bytes': used,
      'receipt_bytes': len(raw), 'receipt_sha256': hashlib.sha256(raw).hexdigest(),
      'whole_stage_upper': 3551715, 'peak': peak}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        with (OUT / 'local-check-failure.json').open('xb') as f:
            f.write((json.dumps({'error': str(exc), 'traceback': traceback.format_exc(), 'events': events,
                                'used': used, 'no_automatic_retry': True}, indent=2) + '\n').encode())
        print(json.dumps({'ok': False, 'error': str(exc), 'used': used}))
        sys.exit(1)
