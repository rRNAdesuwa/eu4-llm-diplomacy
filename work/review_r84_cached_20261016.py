"""Non-author finite cached-source review; no subject execution or decoding."""
from pathlib import Path
import hashlib
import json
import struct

ROOT = Path(__file__).resolve().parents[1]
DIR = 'work/reports/war-peace-api-20261016-r84-selector-call-rcx-crosswalk/'
OUT = ROOT / 'work/reports/war-peace-api-20261016-r84-independent-review'
LIMIT = 8 * 1024 * 1024
events = []
raws = {}
def pin(b):
    return {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}
def read(rel, phase):
    p = ROOT / rel
    assert p.resolve().is_relative_to(ROOT.resolve()) and p.stat().st_size <= 4194304
    b = p.read_bytes()
    events.append({'path': rel, 'phase': phase, **pin(b)})
    assert sum(e['bytes'] for e in events) + 1048576 < LIMIT
    return b
def check(rel, expected):
    b = read(rel, 'before')
    assert pin(b) == expected, rel
    raws[rel] = b

assert not OUT.exists()
check(DIR+'manifest.json', {'bytes': 5593, 'sha256': 'dd02b62f4e12933dc91028192e18ee0a5870a096a96b390d3c0d5dbb9b57a927'})
m = json.loads(raws[DIR+'manifest.json'])
assert m['sealed'] and m['all_authority'] is False
for rel, expected in m['inputs'].items():
    check(rel, expected)
for item in m['outputs']:
    check(item['path'], {k: item[k] for k in ('bytes', 'sha256')})
check(DIR+'verification.json', {'bytes': 6983, 'sha256': '4d5e45163cc6d2156418149c7fa3d987635bb133b97fcaf70ea209104323ef59'})
f = json.loads(raws[DIR+'findings.json'])
assert f['sealed'] and f['passed'] and f['blocking_findings'] == []
assert all(v is False for v in f['authority'].values())
assert all(f[k] == 0 for k in ('process_reads', 'PE_reads', 'decoder_calls', 'native_game_calls', 'game_field_writes', 'new_requests'))
for key in ('upstream_source_manifest', 'upstream_crosswalk', 'upstream_selected_context', 'optional_original_source'):
    item = f[key]
    check(item['path'], {k: item[k] for k in ('bytes', 'sha256')})
e = json.loads(raws[DIR+'rcx-window-evidence.json'])
source = json.loads(raws[f['optional_original_source']['path']])
rows = source['functions']['0x97ed00']['instructions']
assert len(e['windows']) == 2 and e['selected_row_total'] == 64
assert e['all_other_function_bodies_examined'] is False and e['new_decoder_calls'] == 0
assert not e['game_access'] and not e['native_calls']
selected = {}
replayed = []
total_raw = 0
for w, (start, end, ci) in zip(e['windows'], [(0, 31, 14), (241, 274, 257)]):
    assert (w['start_index'], w['end_index_exclusive'], w['call_index']) == (start, end, ci)
    assert w['rows_before'] <= 16 and w['rows_after'] <= 16
    assert len(w['selected_rows']) == end-start and w['linear_address_gaps'] == []
    end_rva = None
    count = 0
    for item, i in zip(w['selected_rows'], range(start, end)):
        assert item['array_index'] == i and item['json_pointer'] == '/functions/0x97ed00/instructions/'+str(i)
        assert item['row'] == rows[i]
        row = item['row']; raw = bytes.fromhex(row['bytes']); rva = int(row['rva'], 16)
        assert len(raw) == item['byte_count']
        if end_rva is not None:
            assert rva == end_rva
        end_rva = rva + len(raw); count += len(raw)
        selected[i] = row
    assert count == w['selected_raw_bytes']
    total_raw += count
    row = selected[ci]; raw = bytes.fromhex(row['bytes'])
    assert len(raw) == 5 and raw[0] == 0xe8
    displacement = struct.unpack('<i', raw[1:])[0]
    target = int(row['rva'], 16) + 5 + displacement
    assert target == 0x97bd30 and displacement == w['signed_rel32']
    replayed.append({'site': row['rva'], 'raw': raw.hex(), 'signed_rel32': displacement, 'target': hex(target)})
assert total_raw == f['new_selected_raw_bytes'] == 279 and f['new_selected_rows'] == 64
prologue = ['48895c2408','55','56','57','4154','4155','4156','4157','488dac24e0feffff','4881ec20020000','4c8bf1','4533ed','4489ad68010000','4489ad70010000']
assert [selected[i]['bytes'] for i in range(14)] == prologue
assert selected[10]['instruction'] == 'mov r14, rcx'
assert selected[254]['bytes'] == '498d8e88000000'
assert selected[255]['bytes'] == 'e882d074ff'
assert selected[256]['bytes'] == '498bce' and selected[256]['instruction'] == 'mov rcx, r14'
branches = []
for i, opcode, target in [(249, 0x74, 0x97f18b), (252, 0xeb, 0x97f19e)]:
    row = selected[i]; raw = bytes.fromhex(row['bytes'])
    assert len(raw) == 2 and raw[0] == opcode
    displacement = struct.unpack('<b', raw[1:])[0]
    assert int(row['rva'], 16)+2+displacement == target
    branches.append({'site': row['rva'], 'raw': raw.hex(), 'target': hex(target)})
assert int(selected[255]['rva'],16)+5+struct.unpack('<i',bytes.fromhex(selected[255]['bytes'])[1:])[0] == 0xcc220
assert f['results'][0]['answer_pointer'] == '/observations/1'
assert f['results'][0]['upstream_crosswalk'] == f['upstream_crosswalk']
assert json.loads(raws[DIR+'raw-replay.json'])['results'] == f['results']
for rel, b in raws.items():
    assert read(rel, 'after') == b, rel
OUT.mkdir()
def save(name, value):
    b = (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode()
    with (OUT/name).open('xb') as file:
        file.write(b)
    return pin(b)
findings = {
 'schema': 'EU4-R84-ROOT-INDEPENDENT-CACHED-REVIEW/1', 'sealed': True, 'passed': True, 'blocking_findings': [],
 'subject_findings': {'path': DIR+'findings.json', **pin(raws[DIR+'findings.json'])},
 'subject_manifest': {'path': DIR+'manifest.json', **pin(raws[DIR+'manifest.json'])},
 'subject_windows': {'path': DIR+'rcx-window-evidence.json', **pin(raws[DIR+'rcx-window-evidence.json'])},
 'flat_pin_count': len(raws), 'source_before_after_equal': True,
 'verified': ['64 retained rows/279B match two exact original JSON windows with continuous addresses', 'two signed E8 targets97bd30 and two local rel8 branch targets independently recalculated', 'selected97ed00 prologue preserves entryRCX until97ed33; R14 copy does not modifyRCX', '97f19e explicitly setsRCX=currentR14 after earlier LEA/call; original entry identity across middle/callee is unproved', '97beaa answer reused acceptedR82 observation, without another native extraction', 'original author schema failure/source/logs retained'],
 'replayed_calls': replayed, 'replayed_branches': branches,
 'limits': ['Retained raw/text are inherited evidence; no PE or new instruction decoder.', 'Pointed memory writes and callees may alter contents; scalar provenance authenticates no object type or endpoint direction.', 'Unselected indices31..240, callee behavior and other incoming edges remain unknown.', 'No runtime reachability, original request, effect, settlement, lifetime or lease proof.', 'Historical resource/collection chronology is a producer witness; before/after equality is not atomicity or ABA exclusion.'],
 'author_upper_witness': f['accounting']['whole_stage_upper'],
 'resources': {'explicit_read_bytes': sum(e['bytes'] for e in events), 'manual_allowance': 524288, 'seal_reserve': 524288, 'upper_bytes': sum(e['bytes'] for e in events)+1048576, 'limit_bytes': LIMIT, 'ordinary_limit': 4194304},
 'authority': f['authority'], 'operations': {'author_programs': 0, 'tests': 0, 'PE_decoder': 0, 'game_native': 0, 'child_sessions': 0},
}
fp = save('findings.json', findings)
mp = save('manifest.json', {'schema': 'EU4-R84-ROOT-CACHED-REVIEW-DELIVERY/1', 'sealed': True, 'passed': True, 'flat_pins': {r: pin(b) for r,b in raws.items()}, 'findings': fp, 'read_events': events, 'reviewer_source_pin': pin(Path(__file__).read_bytes()), 'no_subject_execution': True})
print(json.dumps({'passed': True, 'findings': fp, 'manifest': mp, 'flat_pins': len(raws), 'upper_bytes': findings['resources']['upper_bytes']}, ensure_ascii=True))
