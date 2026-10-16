"""Independent selected raw caller entry review for994f00; no callee/PE execution."""
from pathlib import Path
import ast
import hashlib
import json
import struct

ROOT = Path(__file__).resolve().parents[1]
OLD = 'work/reports/war-peace-api-20261016-r62-gold-recipient-generator/'
NEW = 'work/reports/war-peace-api-20261016-r66-generated-record-postprocess/'
AUDIT = 'work/reports/war-peace-api-20261016-r62-independent-review/'
OUT = ROOT / 'work/reports/war-peace-api-20261016-r66-entry-root-review'
FIXED = {
    OLD + 'manifest.json': (14300, 'd3516fdbc60b2c66115b9a0aa907daace7e5a8adac0c5dbd4c53f0840eba6db4'),
    OLD + 'capture.json': (198722, '53d565996a8b79da7cce445a7ae8576856966eb11bfb3362b924159ada7c27fc'),
    OLD + 'owned-code.json': (1868, 'b0ef4b734752e052ff5e86456f68d5e52a6eded74ab808bbc3a722c46ac84c06'),
    OLD + 'contract.json': (9485, 'b72b70f5f78c5e95f5e7984dc415dd4b4fab3ecbbaa72034e6081f0ae0e2295b'),
    AUDIT + 'findings.json': (6819, '8efc64a9385ca1472f6d4cf3c913f755ed8cdfffcd5082b1c55e87821aac15ad'),
    AUDIT + 'manifest.json': (12593, '660065e49bac4d637b609fa218058a79034fd9d5f5f7fe24c1f902f57695d42c'),
    NEW + 'entry-seed.json': (4721, '3f59299fe0acbef1c1827d48e93445a76c049a2eceb805cb18d8cff42255ef03'),
    NEW + 'source-manifest.json': (20632, 'fd9b6080f2c82133abab4db8b3e96538acec545a5db27b7b9aebc6cd001d1e91'),
    NEW + 'produce.py': (23053, 'b8b132b4ce3244c4570efdb888dc24db423a626c598d6216a135a3a9d48890ca'),
    NEW + 'budget.json': (1599, '4fcd860901dc205e9f53288edff827c04987232ee9399753ff16c8335f689c49'),
}


def pin(b):
    return dict(bytes=len(b), sha256=hashlib.sha256(b).hexdigest())


def save(n, value):
    b = (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode()
    with (OUT / n).open('xb') as f:
        f.write(b)
    return pin(b)


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    save('claim.json', dict(scope='raw_call_entry_seed_only', PE_decoder_game=0))
    files, events, total = {}, [], 0
    for p, (n, sha) in FIXED.items():
        assert (ROOT / p).stat().st_size == n <= 4194304
        raw = (ROOT / p).read_bytes()
        assert pin(raw) == dict(bytes=n, sha256=sha)
        files[p] = raw
        events.append(dict(path=p, phase='before', **pin(raw)))
        total += len(raw)
    cap = json.loads(files[OLD + 'capture.json'])
    owned = json.loads(files[OLD + 'owned-code.json'])
    seed = json.loads(files[NEW + 'entry-seed.json'])
    review = json.loads(files[AUDIT + 'findings.json'])
    assert review['sealed'] is review['passed'] is True and review['blocking_findings'] == []
    assert review['subject_manifest'] == pin(files[OLD + 'manifest.json'])
    for key, name in [('manifest', 'manifest.json'), ('capture', 'capture.json'), ('owned', 'owned-code.json'), ('contract', 'contract.json')]:
        assert seed['upstream_R62_' + key] == pin(files[OLD + name])
    rows = cap['analysis']['instructions']
    selected = seed['minimal_CALL_prefix_raw_rows']
    assert selected == rows[125:128]
    assert [r['bytes'] for r in selected] == ['488d9424a0000000', '498bce', 'e826080100']
    rawcode = bytes.fromhex(owned['raw_hex'])
    assert len(rawcode) == 684 and hashlib.sha256(rawcode).hexdigest() == owned['sha256']
    cursor = 0x9846ca
    for row in selected:
        raw = bytes.fromhex(row['bytes'])
        assert int(row['rva'], 16) == cursor and rawcode[cursor - 0x9844d0:cursor - 0x9844d0 + len(raw)] == raw
        cursor += len(raw)
    assert cursor == 0x9846da and seed['minimal_prefix_bytes'] == 16
    assert 0x9846d5 + 5 + struct.unpack('<i', bytes.fromhex('26080100'))[0] == 0x994f00
    assert seed['signed_rel32'] == 67622
    assert [r['bytes'] for r in rows[2:10]] == ['55', '56', '57', '4154', '4155', '4156', '4157', '4883ec50']
    assert rows[10]['rva'] == '0x9844e9' and rows[10]['bytes'] == '4c8bf2'
    assert 7 * 8 + 0x50 == 0x88 and 0xa0 - 0x88 == 0x18
    for row in rows[:14]:
        off = int(row['rva'], 16) - 0x9844d0
        raw = bytes.fromhex(row['bytes'])
        assert rawcode[off:off + len(raw)] == raw
    assert all(not set(row['registers_written']).intersection({'r8', 'r8d', 'r9', 'r9d', 'xmm0'}) for row in selected[:-1])
    assert seed['R8_R9'].startswith('Unknownafterunfollowed')
    assert seed['XMM0_at_call'] == 'unknown_after_unfollowed_complex_branch_calls'
    # A complex-path exit can bypass this call too. Check the raw conditional displacement.
    gate = next(r for r in rows if r['rva'] == '0x98455b')
    assert gate['bytes'] == '0f8e83010000'
    assert 0x98455b + 6 + struct.unpack('<i', bytes.fromhex('83010000'))[0] == 0x9846e4 > 0x9846d5
    test = next(r for r in rows if r['rva'] == '0x984559')
    assert test['bytes'] == '85f6'
    for row in (test, gate):
        off = int(row['rva'], 16) - 0x9844d0
        assert rawcode[off:off + len(bytes.fromhex(row['bytes']))] == bytes.fromhex(row['bytes'])
    assert seed['callee_XMM_consumption_proved'] is False and seed['upstream_full_R62_actual_review_required'] is True
    source = files[NEW + 'produce.py'].decode()
    ast.parse(source)
    assert "for label in ('upstream_body_review','source_peer_review')" in source
    assert source.index("values.get('subject_entry_seed')==seed_pin") < source.index('base,pins=source_guard()')
    budget = json.loads(files[NEW + 'budget.json'])
    assert budget['new_unique_code_bytes_max'] == 8192 and budget['pdata_requests_max'] == 32
    assert budget['new_callee_data_header_unwind_literal_vtable_reads'] == 0
    for p, (n, sha) in FIXED.items():
        raw = (ROOT / p).read_bytes()
        assert pin(raw) == dict(bytes=n, sha256=sha)
        events.append(dict(path=p, phase='after', **pin(raw)))
        total += len(raw)
    assert total + 524288 < 4194304
    findings = save('findings.json', dict(schema='EU4-R66-INDEPENDENT-RAW-CALL-ENTRY-REVIEW/1',
        sealed=True, passed=True, blocking_findings=[], scope='raw_call_entry_seed_only',
        entry_seed_pin=pin(files[NEW + 'entry-seed.json']), entry_rva='0x994f00',
        call_site_rva='0x9846d5', raw_call='e826080100', source_pins=events,
        physical_source_bytes=total, prior_manual_allowance=524288, bounded_source_upper=total + 524288,
        checks=['Exact3rows16B match retained R62 code/capture and signedCALL994f00.',
                'RDX=&steady+a0=originalentryQ+18; borrowed currentDWORD, no retainedTvalue assertion.',
                'RCX=currentR14, originallyH by9844e9; opaquecontents may change under aliases/callees.',
                'R8/R9/XMM are unknown after earlier complexcalls, not inheritedfirst-call constants.',
                'FullR62 independent review binds exact acceptedmanifest; newsourcepeer androotstart remain separate prerequisites.'],
        precision_notes=['Simplebranch bypasses thiscall. Complexbranch TESTESI/JLE9846e4 at984559/98455b can also bypass; this is only a selected reachable complexpath.',
                         'Initial T/D positivity gates are historical samples, not postcallee T/D/H invariants.',
                         'No formalcallee consumption, H/record writes, borrowretention, returntype or normaltermination is proved by callerbytes.'],
        limits=['No sort/normalization/goldconservation/units/recipient or finalworldeffect claim.',
                'NewR66 sourcepeer and explicitrootactual required; no outsidecallee/data/header/unwind/reader adoption.'],
        PE_decoder_tests_game_native_requests=0,
        authority=dict(callable=False, native_ready=False, effect_verified=False, lease=False, retry=False)))
    manifest = save('manifest.json', dict(sealed=True, findings=findings, sources=events,
        script=pin(Path(__file__).read_bytes())))
    print(json.dumps(dict(passed=True, findings=findings, manifest=manifest, source_bytes=total), ensure_ascii=True))


if __name__ == '__main__':
    main()
