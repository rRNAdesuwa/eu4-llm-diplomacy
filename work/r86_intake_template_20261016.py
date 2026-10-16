"""R86 source-only intake. No old program import/execute or engine/PE access."""
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import traceback

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'work/reports/war-peace-api-20261016-r86-cc220-actual-source/'
OUT = ROOT / PREFIX
R79 = 'work/reports/war-peace-api-20261016-r79-null-selector-callee/'
R85 = 'work/reports/war-peace-api-20261016-r85-cc220-cache-source-plan/'
events = []
used = 25062
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


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def read(path, expected=None):
    global used
    guard()
    if path.startswith('work/deps/') or path.lower().endswith(('.exe', '.dll', '.pyd')):
        raise RuntimeError('engine/PE body access forbidden in source preparation')
    fp = ROOT / path
    n = fp.stat().st_size
    if n > 4194304 or used + n > 2097152:
        raise RuntimeError('intake sub-budget')
    raw = fp.read_bytes()
    used += len(raw)
    p = pin(raw)
    events.append({'path': path, **p})
    if len(raw) != n or (expected is not None and p != expected):
        raise RuntimeError('source pin differs: ' + path)
    return raw


def main():
    with (OUT / 'template-intake-claim.json').open('xb') as f:
        f.write(b'{"schema":"EU4-R86-TEMPLATE-INTAKE-CLAIM/1","source_build_only":true,"actual_authorized":false}\n')
    auth_raw = read(PREFIX + 'owned-source-build-authorization.json', {'bytes': 3232, 'sha256': 'e46d8394585796331bde23ff22f95d78c0c45458b28893ff3016c7a70ceada90'})
    auth = json.loads(auth_raw)
    old_raw = read(PREFIX + 'owned-r79-source-manifest.json', {'bytes': 21830, 'sha256': 'a6d3c5282e46c9ede2da9c6cfaee29edb584636941411714a081331bcd584ab8'})
    old = json.loads(old_raw)
    paths = [R79 + name for name in ['produce.py', 'entry-seed.json', 'main-template.py.inc', 'budget.json', 'source-delta.json', 'PROTOCOL.md']]
    paths.append('work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json')
    expected = {p: old['actual_source_pins'][p] for p in paths}
    for name in ['root_independent_plan_review', 'source_plan', 'second_fixed_cache_probe']:
        p = auth[name]['path']
        paths.append(p)
        expected[p] = {k: auth[name][k] for k in ['bytes', 'sha256']}
    p = auth['entry_basis']['source']
    paths.append(p)
    expected[p] = auth['entry_basis']['source_pin']
    paths.append(R85 + 'manifest.json')
    expected[R85 + 'manifest.json'] = {'bytes': 4519, 'sha256': '96c00855db91be222e5b8d6b2e2daea93f61570ceacab6062d256edace18f365'}
    owned = {}
    mapping = {}
    for p in paths:
        raw = read(p, expected[p])
        name = 'template-' + str(len(mapping)).zfill(2) + '-' + Path(p).name
        with (OUT / name).open('xb') as f:
            f.write(raw)
        mapping[p] = PREFIX + name
        owned[p] = raw
    source = owned[R79 + 'produce.py'].decode()
    review = json.loads(owned[auth['root_independent_plan_review']['path']])
    result = {'schema': 'EU4-R86-SOURCE-TEMPLATE-INTAKE/1', 'source_build_only': True,
        'prior_original_auth_manifest_reads': 25062, 'read_events': events,
        'selected_original_source_pins': expected, 'owned_source_mapping': mapping,
        'template_manifest_pin': {'path': R79 + 'source-manifest.json', **pin(old_raw)},
        'source_build_authorization_pin': {'path': 'work/reports/war-peace-api-20261016-r85-root-source-plan-review/source-build-authorization.json', **pin(auth_raw)},
        'decoder_metadata_witness_only': old['decoder_expected_witness_pins'],
        'engine_files_opened': 0, 'PE_stat_open_hash': False, 'decoder_imported': False,
        'charged_read_bytes_including_initial_intake': used, 'self_peak': peak}
    with (OUT / 'template-intake.json').open('xb') as f:
        f.write((json.dumps(result, indent=2) + '\n').encode())
    print(json.dumps({'ok': True, 'source_pins': expected, 'read_bytes': used,
         'template_producer': source, 'upstream_review': review, 'budget': json.loads(owned[R79 + 'budget.json']),
         'old_seed': json.loads(owned[R79 + 'entry-seed.json'])}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        with (OUT / 'template-intake-failure.json').open('xb') as f:
            f.write((json.dumps({'error': str(exc), 'traceback': traceback.format_exc(), 'events': events,
                 'used': used}, indent=2) + '\n').encode())
        raise
