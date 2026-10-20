"""Non-author replay of a known CALL and cached gap-fenced64B scope; no PE."""
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = 'work/reports/war-peace-api-20261016-r80-unregistered-call-prefix/'
R79 = 'work/reports/war-peace-api-20261016-r79-null-selector-callee/'
R69 = 'work/reports/war-peace-api-20261016-r69-generator-divisor-source/'
OUT = ROOT / 'work/reports/war-peace-api-20261016-r80-entry-independent-review'
PINS = {}; READS = []


def pair(n, sha):
    return dict(bytes=n, sha256=sha)


def read(rel, expected):
    path = (ROOT / rel).resolve()
    assert path.is_relative_to(ROOT) and not path.is_relative_to((ROOT / 'work/deps').resolve())
    assert path.suffix.lower() not in ('.exe','.dll','.pyd')
    a = path.stat(); assert a.st_size <= 4 * 1024 * 1024
    assert sum(r['bytes'] for r in READS) + a.st_size + 512 * 1024 < 4 * 1024 * 1024
    raw = path.read_bytes(); b = path.stat(); value = pair(len(raw),hashlib.sha256(raw).hexdigest())
    READS.append(dict(path=rel, **value))
    assert (len(raw), a.st_size, a.st_mtime_ns) == (b.st_size, b.st_size, b.st_mtime_ns)
    assert value == expected and (rel not in PINS or PINS[rel] == value), rel
    PINS[rel] = value
    return json.loads(raw) if rel.endswith('.json') else raw


def save(path, obj):
    raw = (json.dumps(obj, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode()
    with path.open('xb') as f:
        f.write(raw)
    return pair(len(raw),hashlib.sha256(raw).hexdigest())


assert not OUT.exists()
assert not any((ROOT / (BASE+n)).exists() for n in ('run-authorization.json','claim.json','capture.json','failure.json','owned-code.json'))
source = read(BASE+'source-manifest.json',pair(24123,'42b2d958a64df12ea3083402db08519226218876c51d526dae3285cc95bf5ce2'))
read(BASE+'produce.py',pair(24738,'60009c332eedc75f766200e611930a299d1ec0dcb04f161dd8917c9a7c359c90'))
seed = read(BASE+'entry-seed.json',pair(10512,'a48da80c1e754b13033d0733656e27d0f13ec51d1146bec76675e41185e58384'))
for name in ('produce.py','entry-seed.json'):
    assert source['source_pins'][BASE+name] == PINS[BASE+name]


def prior(rel):
    return read(rel,source['source_pins'][rel])


owned = prior(R69+'owned-code.json'); selected = prior(R69+'selected-evidence.json')
old_seed = prior(R79+'entry-seed.json')
capture = prior(R79+'capture.json'); fence_evidence = prior(R79+'actual-selected-evidence.json')
prior(R79+'actual-manifest.json'); prior(R79+'actual-contract.json')
anchors = prior('work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json')
review = 'work/reports/war-peace-api-20261016-r79-actual-independent-review/'
full = read(review+'findings.json',pair(9030,'8d2277950f717a9d5769bb20c8bb0fe9ce699180247c51dc63b8bccd24fbdf9b'))
read(review+'manifest.json',pair(11402,'aaca888b33d4cce78f1781448c76526b7a034be82fb0aea152ad1d972e009211'))
assert full['sealed'] and full['passed'] and full['blocking_findings'] == []
for key,name in (('subject_actual_manifest','actual-manifest.json'),('subject_capture_pin','capture.json'),
                 ('subject_contract_pin','actual-contract.json'),('subject_selected_pin','actual-selected-evidence.json')):
    assert full[key] == dict(path=R79+name, **PINS[R79+name])
assert seed['caller_owned_pin'] == PINS[R69+'owned-code.json']
assert seed['caller_selected_pin'] == PINS[R69+'selected-evidence.json']
assert seed['caller_source_seed_pin'] == PINS[R79+'entry-seed.json']
assert seed['retained_caller_rows'] == old_seed['retained_caller_rows']
assert seed['caller_register_evidence'] == old_seed['caller_register_evidence']
raw = bytes.fromhex(owned['raw_hex']); assert len(raw) == 55 and owned['window'] == ['0x993570','0x9935a7']
rows = {r['rva']:r for r in selected['instructions']}
for row in seed['retained_caller_rows']:
    assert row == rows[row['rva']]
    at = int(row['rva'],16)-0x993570; body = bytes.fromhex(row['bytes'])
    assert raw[at:at+len(body)] == body
call = bytes.fromhex(seed['raw_call_hex'])
assert call == raw[0x99358a-0x993570:0x99358f-0x993570] == bytes.fromhex('e8a187feff')
rel32 = struct.unpack('<i',call[1:])[0]
assert rel32 == seed['signed_rel32'] == -96351 and 0x99358a+5+rel32 == 0x97bd30
assert seed['entry_rva'] == '0x97bd30' and seed['end_exclusive'] == '0x97bd70'
assert seed['requested_bytes'] == 64 and seed['new_window'] == ['0x97bd30','0x97bd70'] and seed['new_pdata_bytes'] == 0
assert seed['function_extent_known'] is False and seed['R79_unknown_unchanged'] and seed['R80_is_separate_new_scope_not_R79_fallback']
assert seed['cached_previous'] == capture['selected'] == capture['pdata_requests'][17] == fence_evidence['selected']
assert seed['cached_next'] == capture['next'] == capture['pdata_requests'][19] == fence_evidence['next']
assert fence_evidence['analysis'] is fence_evidence['owned_code_pin'] is None and fence_evidence['decoder_loaded'] is False
pd = next(s for s in anchors['sections'] if s['name'] == '.pdata')
records = []
for name,expected_index,raw_hex in (('cached_previous',19063,'90bc970021bd9700e4c0e701'),('cached_next',19064,'a0bd97003cbe97001898dc01')):
    item = seed[name]; b = bytes.fromhex(item['raw_hex']); begin,end,unwind = struct.unpack('<III',b)
    assert item['raw_hex'] == raw_hex and item['index'] == expected_index
    assert (hex(begin),hex(end),hex(unwind)) == (item['begin_rva'],item['end_exclusive'],item['unwind_rva_unfollowed'])
    assert int(item['rva'],16) == int(pd['rva'],16)+12*item['index']
    assert item['file_offset'] == pd['raw_file_offset']+12*item['index']
    records.append(dict(index=item['index'],raw_hex=raw_hex,begin=begin,end_exclusive=end,unwind_unfollowed=unwind))
assert seed['cached_gap'] == ['0x97bd21','0x97bda0']
assert 0x97bd21 <= 0x97bd30 < 0x97bd70 <= 0x97bda0
assert seed['unread_before_entry_bytes'] == 0x97bd30-0x97bd21 == 15
assert seed['unread_after_window_bytes'] == 0x97bda0-0x97bd70 == 48
sections = [s for s in anchors['sections'] if int(s['rva'],16)<=0x97bd30 and 0x97bd70<=int(s['rva'],16)+s['raw_size']]
assert len(sections) == 1 and sections[0]['name'] == '.text'
sec = sections[0]; start = int(sec['rva'],16); h = bytes.fromhex(sec['section_header_raw_hex'])
assert len(h) == 40 and h[:8].rstrip(b'\0') == b'.text'
assert struct.unpack_from('<IIII',h,8) == (sec['virtual_size'],start,sec['raw_size'],sec['raw_file_offset'])
assert 0x97bd70 <= start+sec['virtual_size']
where = sec['raw_file_offset']+0x97bd30-start
assert 0 <= where <= anchors['game_bytes']-64 and anchors['game_bytes'] == 38462504
before = dict(PINS)
for rel,value in before.items():
    read(rel,value)
OUT.mkdir()
finding = dict(schema='EU4-R80-RAW-ENTRY-SEED-INDEPENDENT-REVIEW/1',sealed=True,passed=True,blocking_findings=[],
    scope='raw_known_CALL_prefix_seed_only', subject_source_manifest=PINS[BASE+'source-manifest.json'],
    subject_producer=PINS[BASE+'produce.py'],subject_entry_seed=PINS[BASE+'entry-seed.json'],
    entry_rva='0x97bd30',end_exclusive='0x97bd70',requested_bytes=64,call_site_rva='0x99358a',raw_call_hex='e8a187feff',
    signed_rel32=rel32,cached_fences=records,cached_gap=['0x97bd21','0x97bda0'],cached_file_offset=where,
    retained_caller_rows_equal_owned=len(seed['retained_caller_rows']),new_pdata_bytes=0,
    precision_notes=[
        'The entry is known from a retained directCALL. The64B window is a fixed root-selected prefix, not a declared whole function extent or a R79 fallback.',
        'R79 bounded exact-begin lookup under its ordered-table premise is not an exhaustive global function/unwind absence proof. Two cached descriptors are physical scope fences only.',
        'Preceding15B/following48B are excluded from targeted owned-code requests; whole EXE SHA authentication still traverses the complete file.',
        'CALL entryRSP=originalS69-0x60 and returnQWORD=loaded module base+99358f under valid memory/controlstack. Register bits are not proved callee formals; D0 is only a precallstore.',
        'R79 fullreview is a pinned accepted flat witness, not recursively re-audited. Sourcepeer and a separate new root once grant remain mandatory. No newcallee byte, metadata, engine or game access occurred.'
    ],resources=dict(selected_read_bytes=sum(r['bytes']for r in READS),manual_inspection_allowance=512*1024,maximum=4*1024*1024),
    PE_engine_decoder_game_operations=0,author_programs_or_tests_run=0,actual_authorized=False,native_ready=False,callable=False,
    authorizes_retry=False,reader_adoption_allowed=False,selected_effect_verified=False,world_lease=False,atomic_snapshot=False)
fp = save(OUT/'findings.json',finding)
mp = save(OUT/'manifest.json',dict(sealed=True,passed=True,pins=before,findings=fp,read_journal=READS,before_after_equal=True,
    scope='selected flat retained CALL/cache/source files only',actual_authorized=False))
print(json.dumps(dict(findings=fp,manifest=mp,selected_read_bytes=sum(r['bytes']for r in READS),files=len(PINS)),ensure_ascii=True))
