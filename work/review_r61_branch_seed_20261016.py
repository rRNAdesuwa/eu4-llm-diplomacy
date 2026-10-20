"""Review the R59 taken edge and inherited state for the unread R61 suffix."""
import ast
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = 'work/reports/war-peace-api-20261016-r59-pending-id-kind5/'
NEW = 'work/reports/war-peace-api-20261016-r61-pending-id-return/'
OUT = ROOT / 'work/reports/war-peace-api-20261016-r61-entry-root-review'
FIXED = {
    OLD + 'manifest.json': (14507, '633a4ba43344f5b4041470189e93b2caafd01271b795b6516d1793f0d173beaa'),
    OLD + 'owned-code.json': (891, '305e85db6e323e3366f5cc84f5832491a901cc980d9c26a211a5342d0fa1650e'),
    OLD + 'capture.json': (104164, 'a74721614ef632ee0875089e296f81c8f25c0787dfa1c678353fa3f9e5a21483'),
    'work/reports/war-peace-api-20261016-r59-independent-review/findings.json':
        (7859, '8cdc789336619307d0f75f6aed0f3761b3a43a41cabe663c99ae7763b508d382'),
    NEW + 'entry-seed.json': (3279, '1d04c10f3b2799df3e6aa812b5a7015c45b1010f4d65e103a4c7c33b22bbc7ac'),
    NEW + 'source-manifest.json': (19904, 'c9f384a05880f6e5e5be4e31200e347b204209db1e998b347bfd633b80a7632e'),
    NEW + 'produce.py': (22783, '0527ffbde41a5524970ccb04152f5f9f38093db805044f5311190abcdbfdecb1'),
    NEW + 'budget.json': (1558, '13705de93ac43d89cbcd3def43b992aa14d65b6d636f4e1563ec67f041e84074'),
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
    save('claim.json', {'scope': 'raw_fragment_seed_only', 'PE_engine_decoder_game': 0})
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
    owned = json.loads(files[OLD + 'owned-code.json'])
    capture = json.loads(files[OLD + 'capture.json'])
    seed = json.loads(files[NEW + 'entry-seed.json'])
    audit = json.loads(files['work/reports/war-peace-api-20261016-r59-independent-review/findings.json'])
    assert audit['sealed'] and audit['passed'] and audit['blocking_findings'] == []
    code = bytes.fromhex(owned['raw_hex'])
    assert len(code) == 183 and hashlib.sha256(code).hexdigest() == owned['sha256']
    tail = bytes.fromhex('488b8608250000428b0cb04a8d14b04c8b7c24608bc1488b7c2458488b5c245083fdff740a')
    assert code[0x771c98 - 0x771c06:] == tail
    assert code[-2:] == bytes.fromhex('740a')
    target = 0x771cbb + 2 + struct.unpack('<b', code[-1:])[0]
    assert target == 0x771cc7
    neighbor = capture['next']
    begin, end, unwind = struct.unpack('<III', bytes.fromhex(neighbor['raw_hex']))
    assert neighbor['index'] == 14174 and begin == 0x771cbd and end == 0x771cf6 and unwind == 0x1e54e8c
    assert begin < target < end and target - begin == 10 and end - target == 47
    assert seed['containing_pdata'] == {k: neighbor[k] for k in seed['containing_pdata']}
    assert seed['branch_site_rva'] == '0x771cbb' and seed['raw_branch'] == '740a'
    assert seed['fragment_rva'] == hex(target) and seed['fragment_bytes'] == 47
    state = seed['state_at_successor']
    assert state['fragment_is_independent_callable_entry'] is False and state['RSP'] == 'Q-0x48'
    assert state['R14'] == '0x0000000000000005' and state['RBP'] == '0x00000000ffffffff'
    assert state['RAX'] == 'zero_extend64(V) afterMOV EAX,ECX771cac'
    assert state['RCX'] == 'zero_extend64(V) fromMOV ECX memory771c9f' and state['RDX'] == 'P+0x14 formed771ca3'
    assert state['RBX'] == 'entryRBX restored771cb3 fromQ+8'
    assert state['RDI'] == 'entryRDI restored771cae fromQ+0x10'
    assert state['R15'] == 'entryR15 restored771ca7 fromQ+0x18'
    assert state['flags'] == 'CMP EBPffffffff,-1 =>ZF1/CF0/SF0/OF0/PF1/AF0; JE taken'
    assert 'pathdependent' in state['R8'] and 'clobberedby42d850' in state['R9']
    assert 'overwrotelowDWORD1' in state['Q+0x20']
    budget = json.loads(files[NEW + 'budget.json'])
    assert budget['new_unique_code_bytes_max'] == 47 and budget['old_prefix_targeted_code_read_bytes'] == 0
    source = files[NEW + 'produce.py'].decode()
    ast.parse(source)
    assert "size==47" in source and "full_extent_owned=False" in source
    assert "int(selected['begin_rva'],16)<=ENTRY<int(selected['end_exclusive'],16)" in source
    assert "selected['index']==14174" in source and "selected['raw_hex']=='bd1c7700f61c77008c4ee501'" in source
    for rel, (size, digest) in FIXED.items():
        raw = (ROOT / rel).read_bytes()
        assert pin(raw) == {'bytes': size, 'sha256': digest}
        events.append({'path': rel, 'phase': 'after', **pin(raw)})
        total += len(raw)
    assert total <= 4 * 1024 * 1024
    findings = save('findings.json', {
        'schema': 'EU4-R61-INDEPENDENT-RAW-FRAGMENT-SEED-REVIEW/1',
        'sealed': True, 'passed': True, 'blocking_findings': [],
        'entry_seed_pin': pin(files[NEW + 'entry-seed.json']),
        'branch_site_rva': '0x771cbb', 'raw_branch': '740a', 'entry_rva': hex(target),
        'scope': 'raw_fragment_seed_only', 'source_pins': events,
        'checks': ['Retained37B exit sequence and signedrel8 authenticate selected JE successor.',
                   'Pdata containing record begins10B beforetarget; only47B suffix is allowed.',
                   'Fresh slotV zeroextends intoRAX/RCX; RDX is slotaddress, frameQ-48 retained.',
                   'RBX/RDI/R15 restoration and CMP equality flags match rawinstructions.',
                   'R8/R9/shadowDWORD remain pathdependent; no fabricated fresh-entry ABI.'],
        'limits': ['Rawseed only: separate full producer source review still required before root actual start.',
                   'No new suffix code, PE, decoder, nativeID semantic or runtime was inspected.'],
        'physical_source_bytes': total, 'PE_decoder_tests_game_native_requests': 0,
        'authority': {'callable': False, 'native_ready': False, 'effect_verified': False,
                      'lease': False, 'retry': False}})
    manifest = save('manifest.json', {'sealed': True, 'findings': findings, 'sources': events,
                                     'script': pin(Path(__file__).read_bytes())})
    print(json.dumps({'passed': True, 'findings': findings, 'manifest': manifest, 'source_bytes': total}))

if __name__ == '__main__':
    main()
