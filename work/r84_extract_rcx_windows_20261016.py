"""R84: exactly two fixed cached windows, no function/callee inventory search."""
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import traceback

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/reports/war-peace-api-20261016-r84-selector-call-rcx-crosswalk'
SOURCE = 'work/reports/native-owned-peace-1375.json'
EXPECTED = {'bytes': 1302642, 'sha256': 'f78ca33e46e8a7ea153055ffb77f940710b263a7a366acfc7dfee40c35e7488d'}
SELECT = [(14, 0x97ed33, 'e8f8cfffff'), (257, 0x97f1a1, 'e88acbffff')]
reads = []
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


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def read_source(phase):
    guard()
    path = ROOT / SOURCE
    if path.stat().st_size != EXPECTED['bytes'] or EXPECTED['bytes'] > 4 * 1024 * 1024:
        raise RuntimeError('fixed source size')
    raw = path.read_bytes()
    got = pin(raw)
    reads.append({'path': SOURCE, 'phase': phase, **got})
    if got != EXPECTED:
        raise RuntimeError('fixed source bytes differ')
    return raw


def write(name, value):
    raw = (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode()
    with (OUT / name).open('xb') as f:
        f.write(raw)
    return pin(raw)


def main():
    write('native-window-claim.json', {'schema': 'EU4-R84-WINDOW-CLAIM/1',
          'source': SOURCE, 'pin': EXPECTED, 'selected_function': '0x97ed00',
          'windows': [{'call_index': i, 'call_site': hex(site), 'before_max': 16, 'after_max': 16} for i, site, _ in SELECT],
          'no_other_body_selected': True, 'game_access': False})
    raw = read_source('native_before')
    # Exact cached bytes are pinned before parse. Only this one key is accessed.
    document = json.loads(raw)
    rows = document['functions']['0x97ed00']['instructions']
    windows = []
    for index, site, expected_call in SELECT:
        row = rows[index]
        assert int(row['rva'], 16) == site and row['bytes'] == expected_call
        call_raw = bytes.fromhex(row['bytes'])
        assert len(call_raw) == 5 and call_raw[0] == 0xe8
        displacement = int.from_bytes(call_raw[1:], 'little', signed=True)
        assert site + 5 + displacement == 0x97bd30
        lo, hi = max(0, index - 16), min(len(rows), index + 17)
        selected = []
        gaps = []
        for j in range(lo, hi):
            item = rows[j]
            addr = int(item['rva'], 16)
            code = bytes.fromhex(item['bytes'])
            selected.append({'json_pointer': '/functions/0x97ed00/instructions/' + str(j),
                'array_index': j, 'byte_count': len(code), 'row': item})
            if j > lo:
                prev = rows[j - 1]
                expected_next = int(prev['rva'], 16) + len(bytes.fromhex(prev['bytes']))
                if expected_next != addr:
                    gaps.append({'after_index': j - 1, 'expected_next': hex(expected_next), 'next_rva': item['rva']})
        windows.append({'call_site': hex(site), 'call_index': index, 'raw_call': expected_call,
            'signed_rel32': displacement, 'next_rva': hex(site + 5), 'target': '0x97bd30',
            'source': SOURCE, 'source_pin': EXPECTED, 'start_index': lo, 'end_index_exclusive': hi,
            'rows_before': index - lo, 'rows_after': hi - index - 1,
            'selected_rows': selected, 'linear_address_gaps': gaps,
            'selected_raw_bytes': sum(x['byte_count'] for x in selected)})
    read_source('native_after')
    guard()
    evidence = {'schema': 'EU4-R84-FIXED-RCX-WINDOWS/1', 'source': SOURCE, 'source_pin': EXPECTED,
       'windows': windows, 'read_events': reads, 'charged_read_bytes': sum(x['bytes'] for x in reads),
       'selected_row_total': sum(len(w['selected_rows']) for w in windows),
       'peak_working_set': peak, 'all_other_function_bodies_examined': False,
       'new_decoder_calls': 0, 'game_access': False, 'native_calls': 0,
       'row_interpretation': 'Frozen producer instruction text and exact raw bytes only; no new instruction decoding or callee analysis.'}
    output_pin = write('rcx-window-evidence.json', evidence)
    print(json.dumps({'ok': True, 'evidence_pin': output_pin, 'source_reads': evidence['charged_read_bytes'],
                     'peak': peak, 'windows': windows}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        write('native-window-failure.json', {'error': str(exc), 'traceback': traceback.format_exc(),
              'reads': reads, 'no_automatic_retry': True})
        raise
