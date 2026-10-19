"""Two independent, bounded retained raw-seed reviews; no target or subject execution."""
import hashlib
import json
import struct
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def pair(n, sha):
    return dict(bytes=n, sha256=sha)


def pin(raw):
    return pair(len(raw), hashlib.sha256(raw).hexdigest())


class Review:
    def __init__(self, output):
        self.out = ROOT / ('work/reports/' + output)
        assert not self.out.exists()
        self.pins = {}; self.ledger = []; self.raws = {}
        self.limit = 4 * 1024 * 1024; self.manual = 512 * 1024

    def read(self, rel, expected):
        p = (ROOT / rel).resolve()
        assert p.is_relative_to(ROOT) and not p.is_relative_to((ROOT / 'work/deps').resolve())
        assert p.suffix.lower() not in ('.exe', '.dll', '.pyd')
        a = p.stat(); assert a.st_size <= 4 * 1024 * 1024
        assert sum(r['bytes'] for r in self.ledger) + a.st_size + self.manual <= self.limit
        raw = p.read_bytes(); b = p.stat()
        self.ledger.append(dict(path=rel, **pin(raw)))
        assert (len(raw), a.st_size, a.st_mtime_ns) == (b.st_size, b.st_size, b.st_mtime_ns)
        assert pin(raw) == expected and (rel not in self.pins or self.pins[rel] == expected), rel
        self.pins[rel] = expected; self.raws[rel] = raw
        return json.loads(raw) if rel.endswith('.json') else raw

    def save(self, name, obj):
        raw = (json.dumps(obj, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode()
        with (self.out / name).open('xb') as f:
            f.write(raw)
        return pin(raw)

    def finish(self, finding):
        for rel, value in dict(self.pins).items():
            self.read(rel, value)
        finding.update(sealed=True, passed=True, blocking_findings=[],
            resources=dict(selected_read_bytes=sum(r['bytes'] for r in self.ledger), manual_inspection_allowance=self.manual, maximum=self.limit),
            PE_engine_decoder_game_operations=0, author_programs_or_tests_run=0,
            actual_authorized=False, native_ready=False, callable=False, authorizes_retry=False,
            reader_adoption_allowed=False, class_or_mode_verified=False, host_guard_change_authorized=False,
            selected_effect_verified=False, world_lease=False, atomic_snapshot=False)
        self.out.mkdir()
        fp = self.save('findings.json', finding)
        mp = self.save('manifest.json', dict(sealed=True, passed=True, pins=self.pins,
            findings=fp, before_after_equal=True, read_journal=self.ledger, scope='selected flat retained seed files only',
            actual_authorized=False))
        print(json.dumps(dict(scope=finding['scope'], findings=fp, manifest=mp,
            selected_read_bytes=sum(r['bytes'] for r in self.ledger), files=len(self.pins)), ensure_ascii=True))


def r78():
    rev = Review('server-expected-owner-sample-data-entry-review-20261016-r78')
    base = 'work/reports/server-expected-owner-sample-data-20261016-r78/'
    assert not any((ROOT / (base + n)).exists() for n in ('run-authorization.json', 'attempt-claim.json', 'capture.json', 'failure.json'))
    source = rev.read(base + 'source-manifest.json', pair(7700, 'd1bce281e91ebca3ff60ce5a5b25acb1dfd91a4178e34acd5a66e1b9d4c10b33'))
    rev.read(base + 'produce.py', pair(18803, 'eca07fe527f95f7db33094ff78f315571ca75bb238a7ebb4676e67e3d5aca2b3'))
    seed = rev.read(base + 'entry-seed.json', pair(6277, '028f47b32044c1ca47f28c885379a9a69108fd4474157b3cfc7626c11b8ad0fc'))
    for n in ('produce.py', 'entry-seed.json'):
        assert source['source_pins'][base + n] == rev.pins[base + n]
    def prior(rel):
        return rev.read(rel, source['source_pins'][rel])
    owned = prior(seed['caller_owned_source']['path'])
    selected = prior(seed['caller_selected_source']['path'])
    upstream = prior(seed['R76_full_review']['path'])
    prior('work/reports/server-expected-vtable-reference-owner-actual-independent-review-20261016-r1/manifest.json')
    cache = prior('work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json')
    assert upstream['sealed'] and upstream['passed'] and upstream['blocking_findings'] == []
    assert upstream['subject_owned_pin'] == rev.pins[seed['caller_owned_source']['path']]
    for key, value in seed['R76_upstream_subjects_from_real_full_findings'].items():
        assert upstream[key] == value
    assert seed['data_rva'] == 0x1caa8f0 and seed['requested_bytes'] == seed['root_selected_sample_budget'] == 6
    assert seed['sample_range'] == ['0x1caa8f0', '0x1caa8f6'] and seed['R8D6_is_not_proved_length'] is True
    assert owned['window'] == ['0x803270', '0x803a70']
    raw = bytes.fromhex(owned['raw_hex']); assert len(raw) == 2048
    rows = {r['rva']: r for r in selected['instructions']}
    expected = [('0x8035b4', '488d8b900a0000'), ('0x8035bb', '41b806000000'),
                ('0x8035c1', '488d1528734a01'), ('0x8035c8', 'e8431b89ff')]
    assert [(r['rva'], r['bytes']) for r in seed['caller_rows']] == expected
    for row in seed['caller_rows']:
        assert row == rows[row['rva']]
        at = int(row['rva'], 16) - 0x803270; body = bytes.fromhex(row['bytes'])
        assert raw[at:at + len(body)] == body
    lea = bytes.fromhex(expected[2][1]); target = 0x8035c1 + len(lea) + struct.unpack('<i', lea[-4:])[0]
    assert target == 0x1caa8f0
    call = bytes.fromhex(expected[3][1]); assert 0x8035c8 + len(call) + struct.unpack('<i', call[1:])[0] == 0x95110
    assert struct.unpack('<I', bytes.fromhex(expected[1][1])[2:])[0] == 6
    matches = [s for s in cache['sections'] if int(s['rva'], 16) <= target
        and target + 6 <= int(s['rva'], 16) + s['raw_size']]
    assert len(matches) == 1
    sec = matches[0]; start = int(sec['rva'], 16)
    assert sec['name'] == '.rdata' and target + 6 <= start + sec['virtual_size']
    header = bytes.fromhex(sec['section_header_raw_hex'])
    assert len(header) == 40 and header[:8].rstrip(b'\0') == b'.rdata'
    assert struct.unpack_from('<IIII', header, 8) == (sec['virtual_size'], start, sec['raw_size'], sec['raw_file_offset'])
    where = sec['raw_file_offset'] + target - start
    assert where == seed['prepared_cached_mapping_plan']['file_offset'] == 30055152
    assert 0 <= sec['raw_file_offset'] <= 38462504 - sec['raw_size'] and where + 6 <= 38462504
    assert seed['prepared_cached_mapping_plan']['section_header_raw_hex'] == sec['section_header_raw_hex']
    rev.finish(dict(schema='EU4-R78-INDEPENDENT-RAW-SEED-REVIEW/1', scope='raw_RIP_address_and_cached_six_byte_sample_mapping_only',
        subject_source_manifest=rev.pins[base + 'source-manifest.json'], subject_producer=rev.pins[base + 'produce.py'],
        subject_entry_seed=rev.pins[base + 'entry-seed.json'], data_rva=target, requested_bytes=6, cached_file_offset=where,
        retained_rows_equal_owned=4, raw_lea_hex=lea.hex(), unfollowed_call_target='0x95110',
        precision_notes=[
            'LEA computes an address and does not read the addressed data. Retained decoder memory read:true for LEA is not a physical-read witness.',
            'R8D=6 zeroextends the scalar6; no callee consumption or string length is proved. Six bytes are a root-selected sample only.',
            'The source content is still unread. No byte7, terminator search, GUI file, other cue or callee is allowed.',
            'The currentRBX/entryRCX association remains conditional on prior normal nonvolatile/frame/alias premises. Resource, class, mode, receiver and host compatibility remain unknown.',
            'R76 complete review and cached section header are fixed retained witnesses, not a repeated upstream or native audit. Sourcepeer and separate root once grant remain required.'
        ]))


def r79():
    rev = Review('war-peace-api-20261016-r79-entry-independent-review')
    base = 'work/reports/war-peace-api-20261016-r79-null-selector-callee/'
    assert not any((ROOT / (base + n)).exists() for n in ('run-authorization.json', 'claim.json', 'capture.json', 'owned-code.json', 'failure.json'))
    source = rev.read(base + 'source-manifest.json', pair(21830, 'a6d3c5282e46c9ede2da9c6cfaee29edb584636941411714a081331bcd584ab8'))
    rev.read(base + 'produce.py', pair(24180, '29bb97220b025814190a858e36cc24ce67373ed27304e5e7c69e9d4aa013b978'))
    seed = rev.read(base + 'entry-seed.json', pair(9256, 'b1765705ff97112640173079605d3ab077837052be5c4cbeeeb85e71c59d4689'))
    for n in ('produce.py', 'entry-seed.json'):
        assert source['source_pins'][base + n] == rev.pins[base + n]
    def prior(rel):
        return rev.read(rel, source['source_pins'][rel])
    r69 = 'work/reports/war-peace-api-20261016-r69-generator-divisor-source/'
    owned = prior(r69 + 'owned-code.json'); selected = prior(r69 + 'selected-evidence.json')
    prior(r69 + 'capture.json'); prior(r69 + 'manifest.json')
    full = prior('work/reports/war-peace-api-20261016-r69-actual-independent-review/findings.json')
    prior('work/reports/war-peace-api-20261016-r69-actual-independent-review/manifest.json')
    assert full['sealed'] and full['passed'] and full['blocking_findings'] == []
    assert full['subject_manifest'] == seed['upstream_manifest_pin'] == rev.pins[r69 + 'manifest.json']
    assert full['subject_capture'] == seed['upstream_capture_pin'] == rev.pins[r69 + 'capture.json']
    assert seed['upstream_owned_pin'] == rev.pins[r69 + 'owned-code.json']
    assert seed['upstream_selected_pin'] == rev.pins[r69 + 'selected-evidence.json']
    assert owned['window'] == selected['window'] == ['0x993570', '0x9935a7']
    raw = bytes.fromhex(owned['raw_hex']); assert len(raw) == 55 and selected['raw_hex'] == owned['raw_hex']
    rows = {r['rva']: r for r in selected['instructions']}
    expected = [('0x993570','4055'),('0x993572','56'),('0x993573','4154'),('0x993575','4155'),
        ('0x993577','4156'),('0x993579','4883ec30'),('0x99357d','33f6'),('0x99357f','498be8'),
        ('0x993582','8932'),('0x993584','4c8bf2'),('0x993587','4c8be9'),('0x99358a','e8a187feff')]
    assert [(r['rva'],r['bytes']) for r in seed['retained_caller_rows']] == expected
    assert seed['retained_caller_bytes'] == 31
    for row in seed['retained_caller_rows']:
        assert row == rows[row['rva']]
        at = int(row['rva'], 16)-0x993570; body = bytes.fromhex(row['bytes'])
        assert raw[at:at+len(body)] == body
    call = bytes.fromhex(seed['raw_call_hex']); rel32 = struct.unpack('<i', call[1:])[0]
    assert len(call) == 5 and call[0] == 0xe8 and rel32 == seed['signed_rel32'] == -96351
    assert seed['entry_rva'] == '0x97bd30' and seed['call_site_rva'] == '0x99358a'
    assert 0x99358a + len(call) + rel32 == 0x97bd30 and seed['return_rva'] == '0x99358f'
    # Raw opcodes prove these input registers are not overwritten before the selected CALL.
    # RDX is used for the one DWORD zero store; copies only change nonvolatile temporaries.
    assert expected[6:11] == [('0x99357d','33f6'),('0x99357f','498be8'),('0x993582','8932'),('0x993584','4c8bf2'),('0x993587','4c8be9')]
    rev.finish(dict(schema='EU4-R79-INDEPENDENT-RAW-ENTRY-REVIEW/1', scope='raw_direct_call_entry_seed_only',
        subject_source_manifest=rev.pins[base+'source-manifest.json'], subject_producer=rev.pins[base+'produce.py'],
        subject_entry_seed=rev.pins[base+'entry-seed.json'], entry_rva='0x97bd30', call_site_rva='0x99358a', raw_call_hex='e8a187feff',
        signed_rel32=rel32, retained_rows_equal_owned=12, retained_caller_bytes=31,
        machine_inputs=dict(RCX='entry993570RCX unchanged beforeCALL', RDX='entry993570RDX; exactlyDWORD zero store beforeCALL',
            R8='entry993570R8; copied toRBP, no visible overwrite', R9_XMM_RAX='opaque inherited bits, no formal consumption inferred',
            temporaries='RBP=entryR8, RSI=0, R14=entryRDX, R13=entryRCX', last_flag_writer='XOR ESI:ZF1/SF0/PF1/CF0/OF0/AFundefined;DFunknown'),
        stack=dict(caller_entry='S69', beforeCALL='S69-0x58', callee_entry='S69-0x60',
            return_RVA='0x99358f', actual_pushed_return_QWORD='loaded module base +0x99358f', valid_stack_and_alias_integrity_required=True),
        precision_notes=[
            'The seed returnQWORD wording uses RVA shorthand. An actual normal CALL pushes loaded module base+99358f, never the unrebased RVA constant.',
            'CALL transfer target and preCALL register flow are proved machine facts, not formal parameters, C++ types or sideeffect contracts.',
            'D0 is only a preCALL store. The callee can alias or mutate pointed storage; no finalD/header/amount/units/lifetime proof follows.',
            'Full R69 review is a pinned retained witness, not recursive reauthentication. New sourcepeer and root once grant remain separate; no callee bytes have been read.'
        ]))


if __name__ == '__main__':
    r78()
    r79()
