"""R84 fixed-small-source intake. No target binary, decoder, or author execution."""
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import traceback

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/reports/war-peace-api-20261016-r84-selector-call-rcx-crosswalk'
BASE = 'work/reports/war-peace-api-20261016-r82-selector-cached-use-crosswalk/'
SELECTED = [BASE + 'manifest.json', BASE + 'crosswalk.json', BASE + 'selected-context.json']
ORIGINAL = 'work/reports/native-owned-peace-1375.json'
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


def read(path, expected=None):
    guard()
    fp = ROOT / path
    n = fp.stat().st_size
    if n > 4 * 1024 * 1024 or n + sum(x['bytes'] for x in reads) > 500000:
        raise RuntimeError('fixed small intake budget')
    raw = fp.read_bytes()
    actual = pin(raw)
    reads.append({'path': path, **actual})
    if len(raw) != n or (expected is not None and actual != expected):
        raise RuntimeError('exact pin differs: ' + path)
    return raw


def walk(v, path=''):
    todo = [(path, v)]
    while todo:
        p, x = todo.pop()
        yield p, x
        if isinstance(x, dict):
            todo.extend((p + '/' + str(k).replace('~', '~0').replace('/', '~1'), y) for k, y in reversed(list(x.items())))
        elif isinstance(x, list):
            todo.extend((p + '/' + str(k), y) for k, y in reversed(list(enumerate(x))))


def named_pins(manifest, sought):
    found = []
    for pointer, value in walk(manifest):
        if isinstance(value, dict) and sought in value and isinstance(value[sought], dict):
            candidate = value[sought]
            if 'bytes' in candidate and 'sha256' in candidate:
                found.append({'pointer': pointer + '/' + sought.replace('/', '~1'),
                              'pin': {k: candidate[k] for k in ['bytes', 'sha256']}})
        if isinstance(value, dict) and value.get('path') == sought and 'bytes' in value and 'sha256' in value:
            found.append({'pointer': pointer, 'pin': {k: value[k] for k in ['bytes', 'sha256']}})
    if not found or any(x['pin'] != found[0]['pin'] for x in found):
        raise RuntimeError('missing or conflicting manifest pin: ' + sought)
    return found


def write(name, value):
    raw = (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode()
    with (OUT / name).open('xb') as f:
        f.write(raw)
    return pin(raw)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    write('intake-claim.json', {'scope': 'R82 fixed crosswalk/selected-context metadata intake', 'game_access': False})
    manifest_raw = read(SELECTED[0])
    manifest_pin = pin(manifest_raw)
    manifest = json.loads(manifest_raw)
    refs = {p: named_pins(manifest, p) for p in SELECTED[1:] + [ORIGINAL]}
    owned = {SELECTED[0]: manifest_raw}
    for p in SELECTED[1:]:
        owned[p] = read(p, refs[p][0]['pin'])
    docs = {p: json.loads(raw) for p, raw in owned.items()}
    matches = []
    for source, doc in docs.items():
        if source.endswith('/manifest.json'):
            continue
        containers = {}
        for pointer, value in walk(doc):
            if isinstance(value, (dict, list)):
                containers[pointer] = value
            elif isinstance(value, str) and '97bd30' in value.lower():
                ancestor = pointer.rsplit('/', 1)[0]
                contexts = []
                for _ in range(3):
                    item = containers.get(ancestor)
                    text = json.dumps(item, ensure_ascii=True)
                    contexts.append({'pointer': ancestor, 'value': item if len(text) <= 10000 else None,
                                     'bounded_prefix': text[:10000] if len(text) > 10000 else None})
                    if not ancestor:
                        break
                    ancestor = ancestor.rsplit('/', 1)[0]
                matches.append({'source': source, 'pointer': pointer, 'value': value, 'contexts': contexts})
    for source, raw in owned.items():
        name = 'owned-' + Path(source).name
        with (OUT / name).open('xb') as f:
            f.write(raw)
    summary = {'schema': 'EU4-R84-FIXED-SMALL-INTAKE/1', 'manifest_pin': {'path': SELECTED[0], **manifest_pin},
         'declared_pins': refs, 'source_top_keys': {p: list(doc) if isinstance(doc, dict) else type(doc).__name__ for p, doc in docs.items()},
         'selected_97bd30_matches': matches, 'reads': reads, 'charged_read_bytes': sum(x['bytes'] for x in reads),
         'original_body_opened': False, 'source_claim': 'No original source body or engine opened; only three exact fixed small inputs.',
         'upstream_manifest_identity': 'Current raw manifest pin recorded before parse; subordinate exact pins checked before parsing. Not a new independent acceptance of R82.', 'self_peak_working_set': peak}
    summary_pin = write('intake.json', summary)
    print(json.dumps({'ok': True, 'summary_pin': summary_pin, 'read_bytes': sum(x['bytes'] for x in reads),
        'manifest_pin': manifest_pin, 'original_pin': refs[ORIGINAL], 'top_keys': summary['source_top_keys'],
        'match_count': len(matches), 'matches': [{'source': m['source'], 'pointer': m['pointer'], 'value': m['value'], 'nearest_context': m['contexts'][0]} for m in matches]}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        OUT.mkdir(parents=True, exist_ok=True)
        write('intake-failure.json', {'error': str(exc), 'traceback': traceback.format_exc(), 'reads': reads})
        raise
