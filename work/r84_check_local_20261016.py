"""First R84 final local pin check. No upstream original-body re-read."""
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'work/reports/war-peace-api-20261016-r84-selector-call-rcx-crosswalk/'
OUT = ROOT / PREFIX
SELF = 'work/r84_check_local_20261016.py'
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
        raise RuntimeError('self measurement unavailable')
    peak = max(peak, p.PeakWorkingSetSize)
    if p.WorkingSetSize > 768 * 1024 * 1024 or p.PeakWorkingSetSize > 1024 * 1024 * 1024:
        raise RuntimeError('memory guard')


def read(path, expected=None):
    global used
    guard()
    if not (path.startswith(PREFIX) or path.startswith('work/r84_')):
        raise RuntimeError('upstream original/body read forbidden in local check')
    fp = ROOT / path
    n = fp.stat().st_size
    if n > 4 * 1024 * 1024 or used + n > 500000:
        raise RuntimeError('local check reserve')
    raw = fp.read_bytes()
    p = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    events.append({'path': path, **p})
    used += len(raw)
    if len(raw) != n or (expected is not None and p != expected):
        raise RuntimeError('local pin differs: ' + path)
    return raw


def main():
    read(SELF)
    manifest = json.loads(read(PREFIX + 'manifest.json', {'bytes': 5593, 'sha256': 'dd02b62f4e12933dc91028192e18ee0a5870a096a96b390d3c0d5dbb9b57a927'}))
    cached = {}
    for p, expected in manifest['inputs'].items():
        cached[p] = read(p, expected)
    for p in manifest['outputs']:
        cached[p['path']] = read(p['path'], {k: p[k] for k in ['bytes', 'sha256']})
    findings = json.loads(cached[PREFIX + 'findings.json'])
    assert findings['sealed'] and findings['passed'] and findings['blocking_findings'] == []
    assert findings['stage'] == 'author_retained_analysis_pending_non_author_review'
    assert all(type(v) is bool and v is False for v in findings['authority'].values())
    assert [x['call_site'] for x in findings['results']] == ['0x97beaa', '0x97ed33', '0x97f1a1']
    assert findings['results'][0]['evidence_mode'] == 'reuse_already_complete_R82_answer_no_original_window_reextraction'
    assert findings['new_selected_rows'] == 64 and findings['new_selected_raw_bytes'] == 279
    assert findings['accounting']['original_source_read_bytes_including_failed_manifest_intake'] == 2795606
    assert findings['accounting']['whole_stage_upper'] == 4242494 < 8 * 1024 * 1024
    for name in ['analysis-seal.stdout.txt', 'analysis-seal.stderr.txt', 'analysis-seal-command.json']:
        read(PREFIX + name)
    result = {'schema': 'EU4-R84-LOCAL-FILECHECK/1', 'sealed': True, 'passed': True,
       'scope': 'final_local_file_pins_and_false_authority_only', 'events': events,
       'checked_file_count': len(events), 'read_bytes': used, 'reserve': 500000,
       'whole_stage_upper_with_reserve': 4242494, 'peak_working_set': peak,
       'upstream_original_source_reads': 0, 'old_programs_executed': False,
       'PE_reads': 0, 'decoder_calls': 0, 'game_access': False, 'native_calls': 0,
       'all_shells_collected_on_return': True, 'non_author_review_claimed': False}
    raw = (json.dumps(result, indent=2) + '\n').encode()
    with (OUT / 'verification.json').open('xb') as f:
        f.write(raw)
    print(json.dumps({'ok': True, 'checked_files': len(events), 'verify_read_bytes': used,
       'receipt_bytes': len(raw), 'receipt_sha256': hashlib.sha256(raw).hexdigest(),
       'whole_stage_upper': 4242494, 'peak': peak}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        with (OUT / 'local-check-failure.json').open('xb') as f:
            f.write((json.dumps({'error': str(exc), 'traceback': traceback.format_exc(), 'events': events,
                 'read_bytes': used, 'no_automatic_retry': True}, indent=2) + '\n').encode())
        print(json.dumps({'ok': False, 'error': str(exc), 'read_bytes': used}))
        sys.exit(1)
