"""R85 source-plan extraction: cached key/row metadata, never callee semantics."""
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import re
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/reports/war-peace-api-20261016-r85-cc220-cache-source-plan'
PREFIX = str(OUT.relative_to(ROOT)).replace('\\', '/') + '/'
R6 = 'work/reports/war-peace-api-20261015-r6-registry-lifetime/war/'
R84 = 'work/reports/war-peace-api-20261016-r84-selector-call-rcx-crosswalk/'
SELF = 'work/r85_cc220_cache_metadata_20261016.py'
PINS = {
 R6 + 'manifest.json': {'bytes': 3033, 'sha256': '2b07deb736d9607915c5065fd075f438af3627314a4471bf5d6e55fa5b3b5ca9'},
 R6 + 'corrigendum-manifest-r2.json': {'bytes': 991, 'sha256': '4a534593e6bbc0cb74d401dfe387e5213520a2d288a5b18731c444895cfdbc29'},
 R6 + 'report.md': {'bytes': 6502, 'sha256': '7be0fd9119e36c3bb9d11a5464bd2b02ee6510c1df26a4cd10694d163db81d89'},
 R6 + 'corrigendum-r2.md': {'bytes': 1868, 'sha256': 'e284b5cfae5ed6808ec4eb8582a123d513ea76fd3a5925b71e76f0b24e70917f'},
 R84 + 'manifest.json': {'bytes': 5593, 'sha256': 'dd02b62f4e12933dc91028192e18ee0a5870a096a96b390d3c0d5dbb9b57a927'},
 R84 + 'rcx-window-evidence.json': {'bytes': 20778, 'sha256': 'df3fe934afd5cfc590a2efa84af7baf68b6c35aaf49094835d036081f81a3e42'},
 'work/reports/native-owned-peace-1375.json': {'bytes': 1302642, 'sha256': 'f78ca33e46e8a7ea153055ffb77f940710b263a7a366acfc7dfee40c35e7488d'},
}
MANUAL_UPPER = 524288
SEAL_VERIFY_RESERVE = 800000
CAP = 8 * 1024 * 1024
events = []
used = 4024  # The two original small manifest reads already performed in intake.
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
        raise RuntimeError('self memory guard')


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def read(path, phase, expected=None):
    global used
    guard()
    if path not in PINS and not path.startswith(PREFIX) and path != SELF:
        raise RuntimeError('non-selected source')
    fp = ROOT / path
    n = fp.stat().st_size
    if n > 4 * 1024 * 1024 or used + n + MANUAL_UPPER + SEAL_VERIFY_RESERVE > CAP:
        raise RuntimeError('source budget')
    raw = fp.read_bytes()
    used += len(raw)
    got = pin(raw)
    events.append({'path': path, 'phase': phase, **got})
    if len(raw) != n or (expected is not None and got != expected):
        raise RuntimeError('source pin differs: ' + path)
    return raw


def write(name, value):
    raw = (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode()
    with (OUT / name).open('xb') as f:
        f.write(raw)
    return {'path': PREFIX + name, **pin(raw)}


def main():
    write('metadata-claim.json', {'schema': 'EU4-R85-CACHE-METADATA-CLAIM/1',
       'scope': 'only_cc220_function_key_and_row_metadata_plus_fixed_small_reports',
       'native_business_analysis': False, 'PE_reads': 0, 'decoder_calls': 0, 'game_access': False})
    own = read(SELF, 'reviewer_source_before')
    intake_raw = read(PREFIX + 'manifest-intake.json', 'local_manifest_intake')
    intake = json.loads(intake_raw.decode('utf-8-sig'))
    assert intake['read_bytes'] == 4024 and len(intake['read_events']) == 2
    cached_manifests = {}
    for record in intake['read_events']:
        p = record['path']
        assert {k: record[k] for k in ['bytes', 'sha256']} == PINS[p]
        name = 'owned-r6-' + Path(p).name
        raw = read(PREFIX + name, 'local_manifest_copy', PINS[p])
        cached_manifests[p] = json.loads(raw)
    old_manifest = cached_manifests[R6 + 'manifest.json']
    correction_manifest = cached_manifests[R6 + 'corrigendum-manifest-r2.json']
    assert next(x for x in old_manifest['files'] if x['path'] == 'report.md') == {'path': 'report.md', **PINS[R6 + 'report.md']}
    assert next(x for x in correction_manifest['files'] if x['path'] == R6 + 'corrigendum-r2.md') == {'path': R6 + 'corrigendum-r2.md', **PINS[R6 + 'corrigendum-r2.md']}
    # The two original manifests have had their BEFORE pass already. All others
    # have their sole BEFORE pass now, exact raw pin before parsing/inspection.
    raw_sources = {p: read(p, 'fixed_source_before', expected) for p, expected in PINS.items() if p not in cached_manifests}
    reports = {}
    for p in [R6 + 'report.md', R6 + 'corrigendum-r2.md']:
        lines = raw_sources[p].decode('utf-8').splitlines()
        hits = []
        for i, line in enumerate(lines):
            if re.search(r'cc220|first|append|首次|未闭|失败|unknown|handler|exception|异常|allocator|1b3780|8eb80', line, re.I):
                lo, hi = max(0, i - 1), min(len(lines), i + 2)
                hits.append({'matched_line': i + 1, 'lines': [{'line': j + 1, 'text': lines[j]} for j in range(lo, hi)]})
        reports[p] = {'source_pin': PINS[p], 'selected_limitation_lines': hits, 'line_count': len(lines)}
    r84_manifest = json.loads(raw_sources[R84 + 'manifest.json'])
    assert r84_manifest['inputs'][R84 + 'rcx-window-evidence.json'] == PINS[R84 + 'rcx-window-evidence.json']
    r84 = json.loads(raw_sources[R84 + 'rcx-window-evidence.json'])
    w = next(x for x in r84['windows'] if x['call_site'] == '0x97f1a1')
    row = next(x for x in w['selected_rows'] if x['array_index'] == 255)
    assert row['row']['rva'] == '0x97f199' and row['row']['bytes'] == 'e882d074ff'
    b = bytes.fromhex(row['row']['bytes'])
    displacement = int.from_bytes(b[1:], 'little', signed=True)
    assert 0x97f199 + 5 + displacement == 0xcc220
    original = 'work/reports/native-owned-peace-1375.json'
    original_doc = json.loads(raw_sources[original])
    functions = original_doc.get('functions')
    metadata = {'source': original, 'source_pin': PINS[original], 'functions_container_type': type(functions).__name__,
                'selected_key': '0xcc220', 'present': isinstance(functions, dict) and '0xcc220' in functions,
                'no_other_function_body_examined': True}
    if metadata['present']:
        function = functions['0xcc220']
        metadata['function_container_type'] = type(function).__name__
        metadata['function_keys'] = list(function) if isinstance(function, dict) else None
        metadata['scalar_metadata'] = {k: v for k, v in function.items() if isinstance(v, (str, int, float, bool)) or v is None} if isinstance(function, dict) else {}
        rows = function.get('instructions') if isinstance(function, dict) else None
        metadata['instructions_container_type'] = type(rows).__name__
        metadata['row_count'] = len(rows) if isinstance(rows, list) else None
        row_metadata = []
        if isinstance(rows, list):
            for i, item in enumerate(rows):
                # Metadata only: no instruction text, operands, branches, callees,
                # field interpretation, or new decoding is read/interpreted.
                raw_hex = item.get('bytes') if isinstance(item, dict) else None
                raw_count = len(bytes.fromhex(raw_hex)) if isinstance(raw_hex, str) else None
                row_metadata.append({'json_pointer': '/functions/0xcc220/instructions/' + str(i),
                                     'rva': item.get('rva') if isinstance(item, dict) else None,
                                     'raw_byte_count': raw_count})
            metadata['row_metadata'] = row_metadata
            if row_metadata:
                metadata['first_row'] = row_metadata[0]
                metadata['last_row'] = row_metadata[-1]
                last = row_metadata[-1]
                metadata['recorded_span_candidate'] = {'begin': row_metadata[0]['rva'],
                     'end_exclusive': hex(int(last['rva'], 16) + last['raw_byte_count']) if isinstance(last['rva'], str) and last['raw_byte_count'] is not None else None,
                     'not_pdata_or_whole_function_proof': True}
                metadata['sum_cached_raw_byte_counts'] = sum(x['raw_byte_count'] or 0 for x in row_metadata)
    for p, expected in PINS.items():
        read(p, 'fixed_source_after', expected)
    read(SELF, 'reviewer_source_after', pin(own))
    guard()
    result = {'schema': 'EU4-R85-CC220-CACHE-METADATA/1', 'sealed': True,
       'source_pins': PINS, 'old_small_manifest_schema': {p: list(doc) for p, doc in cached_manifests.items()},
       'old_fixed_report_limitations': reports,
       'R84_seed': {'source': R84 + 'rcx-window-evidence.json', 'source_pin': PINS[R84 + 'rcx-window-evidence.json'],
          'pointer': '/windows/1/selected_rows/14', 'original_source_pointer': row['json_pointer'],
          'site': '0x97f199', 'raw': 'e882d074ff', 'signed_rel32': displacement, 'next': '0x97f19e', 'target': '0xcc220'},
       'cache_metadata': metadata, 'source_read_events': events,
       'prior_manifest_reads': [{k: record[k] for k in ['path', 'phase', 'bytes', 'sha256']} for record in intake['read_events']],
       'charged_read_bytes_including_prior_intake': used,
       'source_only_two_pass_bytes': 2 * sum(x['bytes'] for x in PINS.values()),
       'manual_upper': MANUAL_UPPER, 'seal_verify_reserve': SEAL_VERIFY_RESERVE,
       'whole_stage_upper': used + MANUAL_UPPER + SEAL_VERIFY_RESERVE, 'budget': CAP,
       'peak_working_set': peak, 'business_analysis_performed': False,
       'PE_reads': 0, 'decoder_calls': 0, 'game_access': False, 'native_calls': 0}
    result_pin = write('cache-metadata.json', result)
    print(json.dumps({'ok': True, 'result_pin': result_pin, 'metadata': metadata, 'reports': reports,
       'read_bytes': used, 'whole_stage_upper': result['whole_stage_upper'], 'peak': peak}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        write('metadata-failure.json', {'error': str(exc), 'traceback': traceback.format_exc(), 'events': events,
              'charged_read_bytes': used, 'no_automatic_retry': True})
        print(json.dumps({'ok': False, 'error': str(exc), 'read_bytes': used}))
        sys.exit(1)
