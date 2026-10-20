"""Independent retained first-call seed review for97b2c0; no target execution."""
import ast
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = 'work/reports/war-peace-api-20261016-r62-gold-recipient-generator/'
NEW = 'work/reports/war-peace-api-20261016-r63-gold-scalar-source/'
AUDIT = 'work/reports/war-peace-api-20261016-r62-independent-review/'
OUT = ROOT / 'work/reports/war-peace-api-20261016-r63-entry-root-review'
FIXED = {
    OLD + 'manifest.json': (14300, 'd3516fdbc60b2c66115b9a0aa907daace7e5a8adac0c5dbd4c53f0840eba6db4'),
    OLD + 'capture.json': (198722, '53d565996a8b79da7cce445a7ae8576856966eb11bfb3362b924159ada7c27fc'),
    OLD + 'owned-code.json': (1868, 'b0ef4b734752e052ff5e86456f68d5e52a6eded74ab808bbc3a722c46ac84c06'),
    OLD + 'entry-seed.json': (5796, '8fbdd4c501490f33bc4d6c470145536f3f9288ac274df7ea477e62f8432a7523'),
    AUDIT + 'findings.json': (6819, '8efc64a9385ca1472f6d4cf3c913f755ed8cdfffcd5082b1c55e87821aac15ad'),
    AUDIT + 'manifest.json': (12593, '660065e49bac4d637b609fa218058a79034fd9d5f5f7fe24c1f902f57695d42c'),
    NEW + 'entry-seed.json': (12360, 'cbf9d9f367e98c0822286471ccb68a84d01fa039e83650cac76d6d3503881bad'),
    NEW + 'source-manifest.json': (19311, '17fe6ea0ee577b36c36accbdc88ff25e6a2f21aebdccea8f29c3549afa211200'),
    NEW + 'produce.py': (23023, '4084a0f39990c76dcf94c3810134d993ddcedfd7314ca39455d699f5bc161e19'),
    NEW + 'budget.json': (1599, '2dcf1b06d6708671b37f3d2af688e7bfa3856edf6e5648b39bc6bcda1f946f85'),
}

def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def save(name, value):
    raw = (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode()
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
    capture = json.loads(files[OLD + 'capture.json'])
    owned = json.loads(files[OLD + 'owned-code.json'])
    upstream_seed = json.loads(files[OLD + 'entry-seed.json'])
    seed = json.loads(files[NEW + 'entry-seed.json'])
    review = json.loads(files[AUDIT + 'findings.json'])
    assert review['sealed'] and review['passed'] and review['blocking_findings'] == []
    assert review['subject_manifest'] == pin(files[OLD + 'manifest.json'])
    assert seed['upstream_R62_manifest'] == pin(files[OLD + 'manifest.json'])
    assert seed['upstream_R62_capture'] == pin(files[OLD + 'capture.json'])
    assert seed['upstream_R62_owned'] == pin(files[OLD + 'owned-code.json'])
    rows = capture['analysis']['instructions']
    prefix = seed['R62_entry_to_CALL_raw_rows']
    assert prefix == rows[:14] and seed['R62_postCALL_scalar_rows'] == rows[14:17]
    code = bytes.fromhex(owned['raw_hex'])
    assert len(code) == 684 and hashlib.sha256(code).hexdigest() == owned['sha256']
    cursor = 0x9844d0
    for row in prefix:
        assert int(row['rva'], 16) == cursor
        raw = bytes.fromhex(row['bytes'])
        assert code[cursor - 0x9844d0:cursor - 0x9844d0 + len(raw)] == raw
        cursor += len(raw)
    assert prefix[-1]['rva'] == '0x9844f7' and prefix[-1]['bytes'] == 'e8c46dffff'
    assert 0x9844f7 + 5 + struct.unpack('<i', bytes.fromhex('c46dffff'))[0] == 0x97b2c0
    assert all(row['mnemonic'] != 'call' for row in prefix[:-1])
    assert all(not set(row['registers_written']).intersection({'rcx', 'ecx', 'cx', 'cl', 'ch', 'r8', 'r8d', 'r9', 'r9d', 'xmm0'})
               for row in prefix[:-1])
    assert prefix[10]['bytes'] == '4c8bf2' and prefix[11]['bytes'] == '488bf1'
    assert prefix[12]['bytes'] == '488d9424a0000000'
    assert 7 * 8 + 0x50 == 0x88 and 0xa0 - 0x88 == 0x18
    assert [row['bytes'] for row in seed['R62_postCALL_scalar_rows']] == ['4863bc24a0000000', '85ff', '0f8e52020000']
    assert upstream_seed['XMM0_at_call'] == 'all128bits_zero_by_XORPS_at9b4064'
    assert seed['XMM0_at_call'] == 'all128bits_zero_inherited_from9b4064_no_R62_prefix_XMM_write'
    assert seed['callee_XMM_consumption_proved'] is False and seed['R8_R9'].startswith('inheritedunknown')
    budget = json.loads(files[NEW + 'budget.json'])
    assert budget['new_unique_code_bytes_max'] == 8192 and budget['pdata_requests_max'] == 32
    source = files[NEW + 'produce.py'].decode()
    ast.parse(source)
    assert "for label in ('upstream_body_review','source_peer_review')" in source
    assert source.index("values.get('subject_entry_seed')==seed_pin") < source.index('base,pins=source_guard()')
    for rel, (size, digest) in FIXED.items():
        raw = (ROOT / rel).read_bytes()
        assert pin(raw) == {'bytes': size, 'sha256': digest}
        events.append({'path': rel, 'phase': 'after', **pin(raw)})
        total += len(raw)
    assert total <= 4 * 1024 * 1024
    findings = save('findings.json', {
        'schema': 'EU4-R63-INDEPENDENT-RAW-CALL-ENTRY-REVIEW/1',
        'sealed': True, 'passed': True, 'blocking_findings': [],
        'scope': 'raw_call_entry_seed_only', 'entry_seed_pin': pin(files[NEW + 'entry-seed.json']),
        'entry_rva': '0x97b2c0', 'call_site_rva': '0x9844f7', 'raw_call': 'e8c46dffff',
        'source_pins': events, 'physical_source_bytes': total,
        'checks': ['Exact14rows tofirstCALL/threepostCALLrows match frozen R62 ownedbytes and capture.',
                   'SignedE8 resolves97b2c0; RCX remainsW, RDX=Q+18 addressableuninitializedDWORD.',
                   'SevenPUSH plusSUB50 makesframeQ-88; helperreturn precedesMOVSXD andsignedpositivegate.',
                   'No priorCALL/XMM0write; original9b4064zero128 survives tothisfirstCALL.',
                   'R62 fullbodyreview passes; distinct peer/raw/upstream gates precede engine/target.'],
        'limits': ['Rawcaller only; no97b2c0 body/formalconsumption, actualoutwrite ormoneyunit is established.',
                   'New fullsourcepeer review and explicitrootstart still required for actual.'],
        'PE_decoder_tests_game_native_requests': 0,
        'authority': {'callable': False, 'native_ready': False, 'effect_verified': False,
                      'money_unit': False, 'lease': False, 'retry': False}})
    manifest = save('manifest.json', {'sealed': True, 'findings': findings, 'sources': events,
                                     'script': pin(Path(__file__).read_bytes())})
    print(json.dumps({'passed': True, 'findings': findings, 'manifest': manifest, 'source_bytes': total}))

if __name__ == '__main__':
    main()
