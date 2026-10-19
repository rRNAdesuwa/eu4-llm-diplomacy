"""Continue R84 after an intake-schema failure; first small-body reads only."""
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import traceback

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/reports/war-peace-api-20261016-r84-selector-call-rcx-crosswalk'
BASE = 'work/reports/war-peace-api-20261016-r82-selector-cached-use-crosswalk/'
PINS = {
    BASE + 'crosswalk.json': {'bytes': 21151, 'sha256': '4a7c8b64ed150a97449abaca1fe868b1c03a3afb5baae27699c4e50e59530ffe'},
    BASE + 'selected-context.json': {'bytes': 52837, 'sha256': '56dbc60ce183ac215bb9dffc066db14cfe2de3e0a8b5549f343f2fdb6072a3c7'},
}
events = []
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
        raise RuntimeError('self measurement')
    peak = max(peak, p.PeakWorkingSetSize)
    if p.WorkingSetSize > 768 * 1024 * 1024 or p.PeakWorkingSetSize > 1024 * 1024 * 1024:
        raise RuntimeError('memory guard')


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def read(path, phase):
    guard()
    p = ROOT / path
    n = p.stat().st_size
    if n > 4 * 1024 * 1024 or sum(e['bytes'] for e in events) + n > 250000:
        raise RuntimeError('small-source budget')
    raw = p.read_bytes()
    got = pin(raw)
    events.append({'path': path, 'phase': phase, **got})
    if got != PINS[path]:
        raise RuntimeError('exact small pin differs')
    return raw


def walk(value, path=''):
    yield path, value
    if isinstance(value, dict):
        for k, v in value.items():
            yield from walk(v, path + '/' + str(k).replace('~', '~0').replace('/', '~1'))
    elif isinstance(value, list):
        for k, v in enumerate(value):
            yield from walk(v, path + '/' + str(k))


def main():
    with (OUT / 'small-context-claim.json').open('xb') as f:
        f.write(b'{"scope":"First reads of the two fixed R82 bodies; schema-only continuation","game_access":false}\n')
    raw = {p: read(p, 'small_before') for p in PINS}
    docs = {p: json.loads(data) for p, data in raw.items()}
    matches = []
    for source, doc in docs.items():
        parents = {}
        for pointer, value in walk(doc):
            if isinstance(value, (dict, list)):
                parents[pointer] = value
            elif isinstance(value, str) and '97bd30' in value.lower():
                parent = pointer.rsplit('/', 1)[0]
                nearest = parents[parent]
                text = json.dumps(nearest)
                matches.append({'source': source, 'pointer': pointer, 'value': value,
                    'nearest_context_pointer': parent, 'nearest_context': nearest if len(text) <= 16000 else text[:16000]})
    for source, data in raw.items():
        with (OUT / ('owned-' + Path(source).name)).open('xb') as f:
            f.write(data)
    for source in PINS:
        read(source, 'small_after')
    record = {'schema': 'EU4-R84-FIXED-SMALL-CONTEXT/1', 'source_pins': PINS,
        'source_shape': {p: list(doc) if isinstance(doc, dict) else type(doc).__name__ for p, doc in docs.items()},
        'matches': matches, 'read_events': events, 'charged_bytes': sum(e['bytes'] for e in events),
        'peak': peak, 'original_body_opened': False, 'game_access': False}
    with (OUT / 'small-context.json').open('xb') as f:
        f.write((json.dumps(record, indent=2) + '\n').encode())
    print(json.dumps({'source_shape': record['source_shape'], 'matches': matches,
                      'crosswalk': docs[BASE + 'crosswalk.json'], 'read_bytes': record['charged_bytes']}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        with (OUT / 'small-context-failure.json').open('xb') as f:
            f.write((json.dumps({'error': str(exc), 'traceback': traceback.format_exc(), 'events': events}, indent=2) + '\n').encode())
        raise
