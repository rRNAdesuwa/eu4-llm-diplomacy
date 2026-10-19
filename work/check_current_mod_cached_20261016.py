"""First local-only final pin replay; excludes the four historical source bodies."""
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'work/reports/current-mod-field-cached-source-20261016-r1/'
OUT = ROOT / PREFIX
CAP = 100000
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
        raise RuntimeError('self memory measurement unavailable')
    peak = max(peak, p.PeakWorkingSetSize)
    if p.WorkingSetSize > 768 * 1024 * 1024 or p.PeakWorkingSetSize > 1024 * 1024 * 1024:
        raise RuntimeError('self memory guard')


def read(path, expected=None):
    global used
    guard()
    if path in {'work/reports/native-action-fields-1375.json',
                'work/reports/diplomacy-effect-profiles-20261015/ask-march-replies/static.json',
                'work/reports/diplomacy-effect-profiles-20261015/ask-march-replies/disassembly.txt',
                'work/reports/diplomacy-effect-profiles-20261015/ask-march-replies/trace.py'}:
        raise RuntimeError('fixed source third pass forbidden')
    fp = ROOT / path
    n = fp.stat().st_size
    if used + n > CAP:
        raise RuntimeError('local verify budget')
    raw = fp.read_bytes()
    used += len(raw)
    actual = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    events.append({'path': path, **actual})
    if expected is not None and actual != expected:
        raise RuntimeError('pin differs: ' + path)
    return raw


def main():
    own = 'work/check_current_mod_cached_20261016.py'
    read(own)
    raw = read(PREFIX + 'manifest.json', {'bytes': 4715, 'sha256': '9004f4db1e24f286c2c7f65856c13f60091529ca5b77a9bcbd2705045e5d620c'})
    manifest = json.loads(raw)
    cached = {}
    for p, expected in manifest['inputs'].items():
        cached[p] = read(p, expected)
    for p in manifest['outputs']:
        cached[p['path']] = read(p['path'], {'bytes': p['bytes'], 'sha256': p['sha256']})
    finding = json.loads(cached[PREFIX + 'findings.json'])
    assert finding['sealed'] and finding['passed'] and finding['blocking_findings'] == []
    assert finding['selected_result']['status'] == 'unknown_native_field_meaning'
    assert all(v is False for v in finding['authority'].values())
    assert finding['process_reads'] == finding['PE_reads'] == finding['decoder_calls'] == finding['native_game_calls'] == 0
    assert finding['accounting']['whole_stage_charged_upper'] == 3435500
    assert finding['accounting']['whole_stage_charged_upper'] < 4194304
    assert finding['all_shells_collected'] is True
    assert finding['address']['preferred_va_decimal'] == 5405663332
    for name in ['seal.stdout.txt', 'seal.stderr.txt', 'seal-command-receipt.json']:
        read(PREFIX + name)
    receipt = {'schema': 'EU4-CACHED-FIELD-LOCAL-VERIFY/1', 'sealed': True, 'passed': True,
       'scope': 'local_final_pins_only_no_four_source_third_pass',
       'events': events, 'verification_charged_read_bytes': used,
       'verification_reserve': CAP, 'whole_stage_upper_with_reserve': 3435500,
       'self_peak_working_set': peak,
       'four_fixed_source_reads': 0, 'target_process_reads': 0, 'decoder_calls': 0,
       'old_program_execution': False, 'native_game_calls': 0, 'all_authority': False,
       'all_shells_collected_on_return': True}
    data = (json.dumps(receipt, indent=2) + '\n').encode()
    with (OUT / 'verification.json').open('xb') as f:
        f.write(data)
    print(json.dumps({'ok': True, 'checked_files': len(events), 'verify_reads': used,
                     'receipt_bytes': len(data), 'receipt_sha256': hashlib.sha256(data).hexdigest(),
                     'whole_stage_upper': 3435500}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        with (OUT / 'verification-failure.json').open('xb') as f:
            f.write((json.dumps({'error': str(exc), 'traceback': traceback.format_exc(),
                'events': events, 'used': used, 'no_automatic_retry': True}, indent=2) + '\n').encode())
        print(json.dumps({'ok': False, 'error': str(exc), 'used': used}))
        sys.exit(1)
