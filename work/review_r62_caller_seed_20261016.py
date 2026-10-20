"""Authenticate the retained caller of9844d0 without opening an executable."""
import ast
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = 'work/reports/positive-gold-transfer-seeds-20261015-r1/'
AUDIT = 'work/reports/positive-gold-transfer-seeds-independent-review-20261015-r1/'
NEW = 'work/reports/war-peace-api-20261016-r62-gold-recipient-generator/'
OUT = ROOT / 'work/reports/war-peace-api-20261016-r62-entry-root-review'
FIXED = {
    OLD + 'selected-native.json': (8829, '26bce46e90bf1674e96868ade14967a508de8cc3000c5c184f3666725c67abaa'),
    OLD + 'manifest.json': (5744, '0c4ca3a81aef9ff21796ac44306fa97d55f5f73a2ccbaa7129d779cd167113a9'),
    AUDIT + 'findings.json': (4752, '19d77d639d649ae3210d80cb635b4be6ef25aa082caf71cc52c9ee66f1e2d722'),
    AUDIT + 'manifest.json': (6979, 'cea3c386c05dc0e5296e784591809bb8a3633aa6cf66e6bfa74225f569180b59'),
    NEW + 'entry-seed.json': (5796, '8fbdd4c501490f33bc4d6c470145536f3f9288ac274df7ea477e62f8432a7523'),
    NEW + 'source-manifest.json': (18687, '21b38c7e227fda23b371dfc5def50c69a7d7d80a099e2b1023505f3095a31b96'),
    NEW + 'produce.py': (21388, '20a764de7b695640f2d1f7ce506c27ada6206ceee9ed7752743ef52555251840'),
    NEW + 'budget.json': (1617, '056a9a867a4f166a98c2bd0a5fa18d813dc4300866972fe09b10e6847ee9f8b9'),
}

def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def save(name, data):
    raw = (json.dumps(data, ensure_ascii=True, indent=2) + '\n').encode()
    with (OUT / name).open('xb') as stream:
        stream.write(raw)
    return pin(raw)

def main():
    OUT.mkdir(parents=True, exist_ok=False)
    save('claim.json', {'scope': 'raw_call_entry_seed_only', 'PE_decoder_game': 0})
    files = {}
    events = []
    total = 0
    for rel, (size, digest) in FIXED.items():
        assert (ROOT / rel).stat().st_size == size <= 4 * 1024 * 1024
        raw = (ROOT / rel).read_bytes()
        assert pin(raw) == {'bytes': size, 'sha256': digest}
        files[rel] = raw
        events.append({'path': rel, 'phase': 'before', **pin(raw)})
        total += len(raw)
    original = json.loads(files[OLD + 'selected-native.json'])
    seed = json.loads(files[NEW + 'entry-seed.json'])
    independent = json.loads(files[AUDIT + 'findings.json'])
    assert independent['sealed'] and independent['passed'] and independent['blocking_findings'] == []
    assert independent['subject_manifest'] == pin(files[OLD + 'manifest.json'])
    assert seed['selected_native_pin'] == pin(files[OLD + 'selected-native.json'])
    assert seed['full_inventory_review_pin'] == pin(files[AUDIT + 'findings.json'])
    rows = original['rows']
    assert len(rows) == 62
    cursor = 0x9b4040
    joined = bytearray()
    for row in rows:
        assert int(row['rva'], 16) == cursor
        raw = bytes.fromhex(row['bytes'])
        cursor += len(raw)
        joined.extend(raw)
    assert bytes(joined).hex() == original['owned_raw_hex'] and len(joined) == 246
    assert hashlib.sha256(joined).hexdigest() == original['owned_raw_sha256']
    assert seed['minimal_caller_context'] == rows[:16] and seed['record_consumer_context'] == rows[16:32]
    call = bytes(joined[0x9b407c - 0x9b4040:0x9b407c - 0x9b4040 + 5])
    assert call.hex() == 'e84f04fdff' and 0x9b407c + 5 + struct.unpack('<i', call[1:])[0] == 0x9844d0
    critical = {r['rva']: r['bytes'] for r in rows}
    expected = {'0x9b4050': '4883ec40', '0x9b4054': '488bc2', '0x9b405a': '83793000',
                '0x9b4064': '0f57c0', '0x9b4067': 'f30f7f442420', '0x9b406d': '33db',
                '0x9b406f': '48895c2430', '0x9b4074': '488d542420', '0x9b4079': '488bc8',
                '0x9b40b0': '8b040b', '0x9b40b7': '4c8b440b04', '0x9b40c9': '488d5b0c'}
    assert all(critical[k] == value for k, value in expected.items())
    assert seed['XMM0_at_call'] == 'all128bits_zero_by_XORPS_at9b4064'
    assert seed['callee_XMM_consumption_proved'] is False
    assert seed['path_precondition'].startswith('component+30 DWORD !=0, not>0')
    assert 8 + 0x40 - 0x20 == 0x28
    budget = json.loads(files[NEW + 'budget.json'])
    assert budget['pdata_requests_max'] == 32 and budget['new_unique_code_bytes_max'] == 8192
    assert budget['code_reads_max'] == 1 and budget['exact_pdata_begin_required'] is True
    source = files[NEW + 'produce.py'].decode()
    ast.parse(source)
    assert source.index("review.get('scope')=='raw_call_entry_seed_only'") < source.index('base,pins=source_guard()')
    assert source.index('base,pins=source_guard()') < source.index("stream=(ROOT.parent/'eu4.exe').open('rb')")
    for rel, (size, digest) in FIXED.items():
        raw = (ROOT / rel).read_bytes()
        assert pin(raw) == {'bytes': size, 'sha256': digest}
        events.append({'path': rel, 'phase': 'after', **pin(raw)})
        total += len(raw)
    assert total <= 4 * 1024 * 1024
    findings = save('findings.json', {
        'schema': 'EU4-R62-INDEPENDENT-RAW-CALL-ENTRY-REVIEW/1',
        'sealed': True, 'passed': True, 'blocking_findings': [],
        'scope': 'raw_call_entry_seed_only', 'entry_seed_pin': pin(files[NEW + 'entry-seed.json']),
        'entry_rva': '0x9844d0', 'call_site_rva': '0x9b407c', 'raw_call': 'e84f04fdff',
        'source_pins': events, 'physical_source_bytes': total,
        'checks': ['Frozen62rows/246B and source-review subjects agree; E8rel32 resolves9844d0.',
                   'RCX=originalW; RDX addresses24Bzeroheader at originalQ-28hex.',
                   'XORPS zeroes128bitsXMM0 and MOVDQU+MOVQ initialize allthreeQwords.',
                   'Nonzero component30 path is not a positiveamount contract; R8/R9 remain unknown.',
                   'Consumer stride12/DWORD0/unalignedQWORD4 checked, no business types inferred.'],
        'limits': ['Only retained caller seed authenticated; originalR3largeJSON not reopened.',
                   'New callee body, actualXMMuse, recipients, amountunits and effects remain unknown.',
                   'Separate full producer source review and root explicit actual start remain required.'],
        'PE_decoder_tests_game_native_requests': 0,
        'authority': {'callable': False, 'native_ready': False, 'effect_verified': False,
                      'recipient_mapping': False, 'lease': False, 'retry': False}})
    manifest = save('manifest.json', {'sealed': True, 'findings': findings, 'source_pins': events,
                                     'script': pin(Path(__file__).read_bytes())})
    print(json.dumps({'passed': True, 'findings': findings, 'manifest': manifest, 'source_bytes': total}))

if __name__ == '__main__':
    main()
