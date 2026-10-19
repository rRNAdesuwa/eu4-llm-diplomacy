import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUBJECT = 'work/reports/war-peace-api-20261016-r62-gold-recipient-generator/'
OUT = ROOT / 'work/reports/war-peace-api-20261016-r62-independent-review'
MANIFEST_SHA = 'd3516fdbc60b2c66115b9a0aa907daace7e5a8adac0c5dbd4c53f0840eba6db4'
MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 24 * 1024 * 1024
MEMORY = 768 * 1024 * 1024

class PMC(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
        'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
        'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage')]

kernel = ctypes.WinDLL('kernel32', use_last_error=True)
psapi = ctypes.WinDLL('psapi', use_last_error=True)
kernel.GetCurrentProcess.restype = wintypes.HANDLE
psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
peak = 0

def guard():
    global peak
    p = PMC()
    p.cb = ctypes.sizeof(p)
    assert psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(p), p.cb)
    peak = max(peak, p.PrivateUsage, p.WorkingSetSize, p.PeakWorkingSetSize, p.PeakPagefileUsage)
    assert peak <= MEMORY, ('memory_limit', peak)

ledger = [
    {'path': SUBJECT + 'manifest.json', 'bytes': 14300, 'phase': 'initial_human_inspection', 'sha256': None},
    {'path': SUBJECT + 'contract.json', 'bytes': 9485, 'phase': 'initial_human_inspection', 'sha256': None},
]
total = sum(x['bytes'] for x in ledger)
snapshot = {}

def read(path, expected=None, size=None):
    global total
    guard()
    p = ROOT / path
    before = p.stat()
    assert before.st_size <= MAX_FILE, (path, before.st_size)
    assert total + before.st_size <= MAX_TOTAL
    raw = p.read_bytes()
    after = p.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    assert len(raw) == before.st_size
    digest = hashlib.sha256(raw).hexdigest()
    if expected is not None:
        assert digest == expected, (path, digest, expected)
    if size is not None:
        assert len(raw) == size, (path, len(raw), size)
    total += len(raw)
    pin = {'path': path, 'bytes': len(raw), 'sha256': digest}
    ledger.append({**pin, 'phase': 'independent_stat_stable_hash'})
    snapshot[path] = {**pin, 'raw_hex': raw.hex()}
    guard()
    return raw

def obj(path):
    return json.loads(bytes.fromhex(snapshot[path]['raw_hex']))

def main():
    OUT.mkdir(exist_ok=False)
    (OUT / 'claim.json').write_text(json.dumps({'schema': 'EU4-R62-INDEPENDENT-CLAIM/1',
        'subject_manifest_sha256': MANIFEST_SHA, 'scope': 'file_only',
        'author_producer_runs': 0, 'PE_reads': 0, 'decoder_imports': 0,
        'game_process_accesses': 0, 'native_calls': 0, 'old_tests': 0}, indent=2) + '\n', encoding='utf-8')
    try:
        manifest = json.loads(read(SUBJECT + 'manifest.json', MANIFEST_SHA, 14300))
        assert manifest['actual_file_pin_count'] == 35
        for pin in manifest['actual_file_pins']:
            read(pin['path'], pin['sha256'], pin['bytes'])
        for name in ('actual-delivery.json', 'actual-delivery-accounting-delta.json',
                     'actual-filecheck.json', 'actual-prerequisite-reads.json',
                     'retained-seal-accounting.json'):
            read(SUBJECT + name)
        witness = manifest['decoder_producer_authenticated_witness_pins']
        print('WITNESS_TYPE', type(witness).__name__, len(witness))
        owned = obj(SUBJECT + 'owned-code.json')
        capture = obj(SUBJECT + 'capture.json')
        selected = obj(SUBJECT + 'selected-evidence.json')
        print('KEYS', json.dumps({'owned': list(owned), 'capture': list(capture), 'selected': list(selected)}))
        print(bytes.fromhex(snapshot[SUBJECT + 'disassembly.txt']['raw_hex']).decode('utf-8'))
        print('DELIVERY', json.dumps(obj(SUBJECT + 'actual-delivery.json'), ensure_ascii=True))
        print('DELTA', json.dumps(obj(SUBJECT + 'actual-delivery-accounting-delta.json'), ensure_ascii=True))
        guard()
        payload = {'schema': 'EU4-R62-INDEPENDENT-RETAINED-SOURCES/1',
                   'subject_manifest_sha256': MANIFEST_SHA, 'files': snapshot,
                   'source_reads': ledger, 'source_physical_bytes': total,
                   'self_peak_bytes': peak, 'engine_witness_opened': False,
                   'PE_reads': 0, 'decoder_imports': 0, 'game_process_accesses': 0}
        raw = (json.dumps(payload, ensure_ascii=True, indent=2) + '\n').encode()
        assert len(raw) <= MAX_FILE
        (OUT / 'retained-sources.json').write_bytes(raw)
        guard()
        print('AUDIT_RETAINED', len(snapshot), total, len(raw), peak)
    except Exception as exc:
        (OUT / 'failure.json').write_text(json.dumps({'type': type(exc).__name__,
            'detail': str(exc), 'source_reads': ledger, 'source_physical_bytes': total,
            'self_peak_bytes': peak}, indent=2) + '\n', encoding='utf-8')
        raise

if __name__ == '__main__':
    main()
