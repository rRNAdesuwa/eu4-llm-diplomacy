"""Independent selected raw-call review; upstream full body review is a separate gate."""
from pathlib import Path
import ast
import hashlib
import json
import struct

ROOT = Path(__file__).resolve().parents[1]
OLD = 'work/reports/war-peace-api-20261016-r64-gold-element-selection/'
NEW = 'work/reports/war-peace-api-20261016-r65-element-slot-helper/'
OUT = ROOT / 'work/reports/war-peace-api-20261016-r65-entry-root-review'
FIXED = {
    OLD + 'manifest.json': (14450, 'ac219aa1b6adc947acf64d61dcd56126b370860b02ab7dcff22a1a8000d1fc81'),
    OLD + 'capture.json': (276303, '723c6a94b549d08f9f24b710b81426ba32d9eecee5cb9e17e4ddc43e8ef26d1c'),
    OLD + 'owned-code.json': (2508, 'd922eb0f548e7722258eafe1f99db3f44171846e46af02df5b2a5ae481f31c52'),
    OLD + 'contract.json': (9119, '737775651b93f23b69fe70059e8c424fa22ca0a48cbadc8bea7573da390d50ef'),
    NEW + 'entry-seed.json': (7240, 'b192107c225a96336eabf1137cecc9ad01a54df7ad27aa29930492dbad2ee600'),
    NEW + 'source-manifest.json': (19693, 'c8b9d0b0037a280c038c46a65ab2f8b9792492be5d358b4eb493d7063cf1d303'),
    NEW + 'produce.py': (23015, '6884ef7aa98a47bf487915134d357a7deda292a9196106c817e809d76aad13ea'),
    NEW + 'budget.json': (1599, 'c50466e7b59b508f40a3a712f35440b329646fc92013250110a8c330c121dce5'),
    'work/reports/element-slot-helper-retained-inventory-20261016-r1/inventory.json':
        (7259, '7e29944ad278fe171a0784d71080af39567848b9a80d874885f3f1fe2c3d0012'),
}


def pin(b):
    return dict(bytes=len(b), sha256=hashlib.sha256(b).hexdigest())


def save(n, v):
    b = (json.dumps(v, ensure_ascii=True, indent=2) + '\n').encode()
    with (OUT / n).open('xb') as f:
        f.write(b)
    return pin(b)


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    save('claim.json', dict(scope='raw_call_entry_seed_only', PE_decoder_game=0))
    files, reads, total = {}, [], 0
    for p, (n, sha) in FIXED.items():
        assert (ROOT / p).stat().st_size == n <= 4194304
        b = (ROOT / p).read_bytes()
        assert pin(b) == dict(bytes=n, sha256=sha)
        files[p] = b
        reads.append(dict(path=p, phase='before', **pin(b)))
        total += len(b)
    capture = json.loads(files[OLD + 'capture.json'])
    owned = json.loads(files[OLD + 'owned-code.json'])
    seed = json.loads(files[NEW + 'entry-seed.json'])
    for key, name in [('manifest', 'manifest.json'), ('capture', 'capture.json'), ('owned', 'owned-code.json'), ('contract', 'contract.json')]:
        assert seed['upstream_R64_' + key] == pin(files[OLD + name])
    rows = capture['analysis']['instructions']
    chosen = seed['minimal_CALL_prefix_raw_rows']
    start = next(i for i, row in enumerate(rows) if row['rva'] == '0x97bc55')
    assert start == 248 and chosen == rows[start:start + 6]
    assert [r['bytes'] for r in chosen] == ['488b07', '4c8d442478', '8b5314', '488bcb', '4889442478', 'e8d329e0ff']
    rawcode = bytes.fromhex(owned['raw_hex'])
    assert len(rawcode) == 1003 and hashlib.sha256(rawcode).hexdigest() == owned['sha256']
    cursor = 0x97bc55
    for row in chosen:
        b = bytes.fromhex(row['bytes'])
        assert int(row['rva'], 16) == cursor and rawcode[cursor - 0x97b8a0:cursor - 0x97b8a0 + len(b)] == b
        cursor += len(b)
    assert cursor == 0x97bc6d and seed['minimal_prefix_bytes'] == 24
    assert 0x97bc68 + 5 + struct.unpack('<i', bytes.fromhex('d329e0ff'))[0] == 0x77e640
    assert seed['signed_rel32'] == -2086445 and seed['entry_rva'] == '0x77e640'
    assert all(r['mnemonic'] != 'call' for r in chosen[:-1])
    # Exact retained prologue and post-call bytes establish only the stated conditional frame/loop facts.
    prologue = rows[:14]
    assert [r['bytes'] for r in prologue[2:10]] == ['55', '56', '57', '4154', '4155', '4156', '4157', '4883ec30']
    assert prologue[12]['bytes'] == '488bda'
    for row in prologue:
        off = int(row['rva'], 16) - 0x97b8a0
        assert rawcode[off:off + len(bytes.fromhex(row['bytes']))] == bytes.fromhex(row['bytes'])
    assert 7 * 8 + 0x30 == 0x68 and 0x78 - 0x68 == 0x10
    assert rows[start + 6]['bytes'] == '4883c708' and rows[start + 7]['bytes'] == 'ebdd'
    assert all(not set(r['registers_written']).intersection({'r9', 'r9d', 'r9w', 'r9b', 'xmm0'}) for r in chosen[:-1])
    assert seed['XMM0_at_call'] == 'unknown_after_unfollowed_1c20d0_or_prior_iteration'
    assert seed['callee_XMM_consumption_proved'] is False and seed['R9'].startswith('Unknownafterunfollowed')
    assert 'zeroextendedfreshPcount' in seed['not_old_output']
    assert seed['upstream_full_R64_actual_review_required'] is True
    assert seed['new_R65_full_source_peer_required'] is True and seed['new_root_explicit_actual_authorization_required'] is True
    budget = json.loads(files[NEW + 'budget.json'])
    assert budget['new_unique_code_bytes_max'] == 8192 and budget['pdata_requests_max'] == 32
    assert budget['new_callee_data_header_unwind_literal_vtable_reads'] == 0
    source = files[NEW + 'produce.py'].decode()
    ast.parse(source)
    assert "for label in ('upstream_body_review','source_peer_review')" in source
    assert source.index("values.get('subject_entry_seed')==seed_pin") < source.index('base,pins=source_guard()')
    for p, (n, sha) in FIXED.items():
        b = (ROOT / p).read_bytes()
        assert pin(b) == dict(bytes=n, sha256=sha)
        reads.append(dict(path=p, phase='after', **pin(b)))
        total += len(b)
    assert total + 524288 < 4194304
    findings = save('findings.json', dict(schema='EU4-R65-INDEPENDENT-RAW-CALL-ENTRY-REVIEW/1',
        sealed=True, passed=True, blocking_findings=[], scope='raw_call_entry_seed_only',
        entry_seed_pin=pin(files[NEW + 'entry-seed.json']), entry_rva='0x77e640',
        call_site_rva='0x97bc68', raw_call='e8d329e0ff', source_pins=reads,
        source_reads=total, prior_manual_allowance=524288, bounded_source_upper=total + 524288,
        checks=['Exact selected6rows24B match retained R64 owned bytes and capture; signedCALL resolves77e640.',
                'RAX=freshQWORD[RDI]; temporaryQWORDsteady78 receives it; R8=&thatcurrent8Bslot.',
                'EDX=freshDWORD[RBX+14] zeroextendsRDX; RCX=currentRBX. No amount/index or pointer meaning assigned to RDX.',
                'Retainedprologue savesoriginalincomingRDX toRBX and uses7PUSH+SUB30, so steady78=entryQ+10 under normal stack/ABI assumptions.',
                'Caller incrementsRDI8 after normalreturn. Whether callee copiesvalue or retainsborrow is not established.',
                'R9/XMM0 not written byminimalprefix; preceding unknowncallees mean unknown at thiscall, not inheritedentryconstants.',
                'Three distinct reviews plus newrootstart remain producer gates beforeengine/target.'],
        limits=['This review covers selected raw caller seed only, not entireR64 body/CFG or new77e640callee.',
                'Association ofcurrentRBX withoriginalP and selectedF8zero reachability requires the separately passed fullR64 review and ordinary nonvolatile/alias assumptions.',
                'FullR64 review and newR65 sourcepeer must both pass exact subjects before actual; this receipt authorizes neither actual nor anothercallee.',
                'No C++ append/vector type, borrowedpointer lifetime, businessenum0, units, recipient, effect, retry or lease.'],
        upstream_full_actual_review_is_separate_required_gate=True,
        PE_decoder_tests_game_native_requests=0,
        authority=dict(callable=False, native_ready=False, effect_verified=False, lease=False, retry=False)))
    manifest = save('manifest.json', dict(sealed=True, findings=findings, sources=reads,
        script=pin(Path(__file__).read_bytes())))
    print(json.dumps(dict(passed=True, findings=findings, manifest=manifest, source_bytes=total), ensure_ascii=True))


if __name__ == '__main__':
    main()
