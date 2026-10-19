"""Independent retained caller-byte review for97b8a0; no callee/PE execution."""
import ast
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = 'work/reports/war-peace-api-20261016-r63-gold-scalar-source/'
NEW = 'work/reports/war-peace-api-20261016-r64-gold-element-selection/'
AUDIT = 'work/reports/war-peace-api-20261016-r63-independent-review/'
OUT = ROOT / 'work/reports/war-peace-api-20261016-r64-entry-root-review'
FIXED = {
    OLD + 'manifest.json': (14796, '965c8f654428410f47ff327a7de28252c9650d8ae02f2f8876560881a6ffdca5'),
    OLD + 'capture.json': (107151, '43b43f911772730b84a4750f3f4c1ada68c44fc3239afd0b4b752a247171bcab'),
    OLD + 'owned-code.json': (898, 'b161c3bfe65f5749131c5c5e2bfa90a574e686a220966cef764055cd34f8428d'),
    OLD + 'contract.json': (7894, 'e515d681b968f8f30f5aad8df900a97b38f0ee44aa8286e1e5c22d399fbc48f0'),
    AUDIT + 'findings.json': (4385, '80418ecca9b71e5d98dc26ac102b9304fd8d3732deb7754f618473f33db2b8ac'),
    AUDIT + 'manifest.json': (13129, '439846e7b3ba478585f90aa02c891fe3055619284fe43cd4caf97987a81e7149'),
    NEW + 'entry-seed.json': (22912, '3af9dd9439bcfdc7d464de130686816f6fb4150712bedf82e592b805a83312da'),
    NEW + 'source-manifest.json': (19275, '043e7f261df881931801a67308e012723f0f62c87313f54d3be8b62687bd52f0'),
    NEW + 'produce.py': (23022, '8dba7831bcbb0dce24139100a3d719c084e1fec7e4f1dcf5ebcd6d58188ba792'),
    NEW + 'budget.json': (1599, '23a1a75a1d66e3b046faa999901f6e834befcb6c67e19d1fb4fa15ea91963c7a'),
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
    files, events, total = {}, [], 0
    for rel, (size, sha) in FIXED.items():
        assert (ROOT / rel).stat().st_size == size <= 4 * 1024 * 1024
        raw = (ROOT / rel).read_bytes()
        assert pin(raw) == {'bytes': size, 'sha256': sha}
        files[rel] = raw
        events.append({'path': rel, 'phase': 'before', **pin(raw)})
        total += len(raw)
    capture = json.loads(files[OLD + 'capture.json'])
    owned = json.loads(files[OLD + 'owned-code.json'])
    seed = json.loads(files[NEW + 'entry-seed.json'])
    review = json.loads(files[AUDIT + 'findings.json'])
    assert review['sealed'] is review['passed'] is True and review['blocking_findings'] == []
    assert review['subject_manifest'] == pin(files[OLD + 'manifest.json'])
    for key, filename in [('manifest', 'manifest.json'), ('capture', 'capture.json'), ('owned', 'owned-code.json'), ('contract', 'contract.json')]:
        assert seed['upstream_R63_' + key] == pin(files[OLD + filename])
    rows = capture['analysis']['instructions']
    prefix = seed['R63_entry_to_CALL_raw_rows']
    post = seed['R63_postCALL_selection_rows']
    assert prefix == rows[:21] and post == rows[21:27]
    expected_prefix = ['48895c2408', '4889742410', '57', '4881ec50040000', '488bda',
        '0f57c0', '0f11442430', '33ff', '48c744244080000000', '488d35012c2c01',
        '4889742430', '488d442448', '4889442438', '897c2420', '48897c2428',
        '0f28442420', '660f7f442420', '41b101', '4c8d442420', '488d542430', 'e87c050000']
    assert [r['bytes'] for r in prefix] == expected_prefix
    assert [r['bytes'] for r in post] == ['837c244401', '7520', '488b4c2438', '488b01', '8b5030', '8913']
    code = bytes.fromhex(owned['raw_hex'])
    assert len(code) == 199 and hashlib.sha256(code).hexdigest() == owned['sha256']
    cursor = 0x97b2c0
    for row in prefix + post:
        assert int(row['rva'], 16) == cursor
        raw = bytes.fromhex(row['bytes'])
        assert code[cursor - 0x97b2c0:cursor - 0x97b2c0 + len(raw)] == raw
        cursor += len(raw)
    assert sum(len(bytes.fromhex(r['bytes'])) for r in prefix) == 100
    assert sum(len(bytes.fromhex(r['bytes'])) for r in post) == 20
    rel = struct.unpack('<i', bytes.fromhex('7c050000'))[0]
    assert rel == seed['signed_rel32'] == 1404 and 0x97b31f + 5 + rel == 0x97b8a0
    assert seed['source_pointer'] == '/analysis/instructions/20'
    assert all(r['mnemonic'] != 'call' for r in prefix[:-1])
    assert all(not set(r['registers_written']).intersection({'rcx', 'ecx', 'cx', 'cl', 'ch'}) for r in prefix[:-1])
    assert 8 + 0x450 == 0x458
    assert 0x97b2e8 + 7 + struct.unpack('<i', bytes.fromhex('012c2c01'))[0] == 0x1c3def0
    # Symbolic byte provenance, restricted to the exact raw writes above. This is not native execution.
    stack = {a: 'unknown' for a in range(0x20, 0x48)}
    xmm0 = [0] * 16
    for a, b in zip(range(0x30, 0x40), xmm0):
        stack[a] = b
    for a, b in zip(range(0x40, 0x48), (0x80).to_bytes(8, 'little')):
        stack[a] = b
    for a in range(0x30, 0x38):
        stack[a] = 'module_pointer_1c3def0'
    for a in range(0x38, 0x40):
        stack[a] = 'steady_rsp_plus48'
    for a in range(0x20, 0x24):
        stack[a] = 0
    for a in range(0x28, 0x30):
        stack[a] = 0
    xmm0 = [stack[a] for a in range(0x20, 0x30)]
    for a, b in zip(range(0x20, 0x30), xmm0):
        stack[a] = b
    assert xmm0 == [0] * 4 + ['unknown'] * 4 + [0] * 8
    assert [stack[a] for a in range(0x44, 0x48)] == [0] * 4
    assert seed['descriptor_raw']['Cpp_class_vtable_identity_proved'] is False
    assert seed['descriptor_raw']['low_DWORD40'] == 128 and seed['descriptor_raw']['high_DWORD44_initial'] == 0
    assert seed['XMM0_at_call'] == 'copied_stack20_16B_DWORD0_paddingDWORD_unknown_QWORD0'
    assert seed['callee_XMM_consumption_proved'] is False
    assert seed['R9'] == 'OnlyR9B=1; upper56inheritedunknown, nofullregisterzero.'
    assert 'NOToriginalR63outputpointer' in seed['RDX']
    budget = json.loads(files[NEW + 'budget.json'])
    assert budget['new_unique_code_bytes_max'] == 8192 and budget['pdata_requests_max'] == 32
    assert budget['new_callee_data_header_unwind_literal_vtable_reads'] == 0
    source = files[NEW + 'produce.py'].decode()
    ast.parse(source)
    assert "for label in ('upstream_body_review','source_peer_review')" in source
    assert source.index("values.get('subject_entry_seed')==seed_pin") < source.index('base,pins=source_guard()')
    for rel, (size, sha) in FIXED.items():
        raw = (ROOT / rel).read_bytes()
        assert pin(raw) == {'bytes': size, 'sha256': sha}
        events.append({'path': rel, 'phase': 'after', **pin(raw)})
        total += len(raw)
    assert total + 512 * 1024 <= 4 * 1024 * 1024
    findings = save('findings.json', {
        'schema': 'EU4-R64-INDEPENDENT-RAW-CALL-ENTRY-REVIEW/1',
        'sealed': True, 'passed': True, 'blocking_findings': [],
        'scope': 'raw_call_entry_seed_only', 'entry_seed_pin': pin(files[NEW + 'entry-seed.json']),
        'entry_rva': '0x97b8a0', 'call_site_rva': '0x97b31f', 'raw_call': 'e87c050000',
        'source_pins': events, 'physical_source_bytes': total, 'prior_console_allowance': 524288,
        'bounded_source_upper': total + 524288,
        'checks': ['Exact21rows100B tofirstCALL and6postrows20B match frozenR63 ownedbytes/capture.',
                   'SignedE8 resolves97b8a0; no priorCALL or RCXwrite, opaqueW forwarded.',
                   'PUSH8+SUB450 yieldssteadyRSP=Q-458; originaloutRDX savedRBX separately.',
                   'RDX=&descriptor30; pointer1c3def0/data=&steady48/capacity128/count0 are raw shape, not a C++ type.',
                   'R8=&selector20: bytes20..23=0,24..27unknown,28..2f=0. MOVAPS/MOVDQA preserve unknown padding.',
                   'R9B=1 initializes eight bits only; XMM0 contains the same unknown padding.',
                   'PostCALL count1 gate reads freshdata, firstQWORDelement and DWORD30 into oldout.',
                   'R63 fullbodyreview passes; new sourcepeer and explicitrootactual still distinct gates before engine/target.'],
        'limits': ['Rawcaller only; no97b8a0body/formalconsumption/writes/selection/return is established.',
                   'No enumeration0/gold units/recipient direction/type/lifetime/world or final output claim.',
                   'No automatic actual authorization, callee expansion or reader adoption.'],
        'PE_decoder_tests_game_native_requests': 0,
        'authority': {'callable': False, 'native_ready': False, 'effect_verified': False,
                      'money_unit': False, 'lease': False, 'retry': False}})
    manifest = save('manifest.json', {'sealed': True, 'findings': findings, 'sources': events,
                                     'script': pin(Path(__file__).read_bytes())})
    print(json.dumps({'passed': True, 'findings': findings, 'manifest': manifest, 'source_bytes': total}))


if __name__ == '__main__':
    main()
