"""Independent retained-file review of the R59 branch seed; no binary/decoder access."""
import ast
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'work/reports/war-peace-api-20261015-r58-pending-id-source/'
NEW = 'work/reports/war-peace-api-20261016-r59-pending-id-kind5/'
OUT = ROOT / 'work/reports/war-peace-api-20261016-r59-entry-root-review'
FIXED = {
    PREFIX + 'owned-code.json': (591, '5ecb80bc70b0c10ce30741ee6c05d5d844a25fa9c18a7c1964c991685a94d1dc'),
    PREFIX + 'capture.json': (78014, '78a55918483d13fe5e6398afe326df55df907c45379dc34ad88f5bbddb841b7e'),
    PREFIX + 'contract.json': (6262, 'bdf98826b1746f19d2cb0ebc301e057a6be09430cc247034b79a803388803c9c'),
    'work/reports/war-peace-api-20261015-r58-independent-review/findings.json':
        (4475, '1b7537c364fc2bebeb21670294da7e550da75378c9a2b331d1c0a0491e14b8ad'),
    NEW + 'entry-seed.json': (3235, '08c82a8bc83e717f96dda7fe7405d474c0e2d2a5bd59a666b9a36c9672ec19c7'),
    NEW + 'budget.json': (1903, '8364761d120a5fa9799cf907c2bed3093b27fd4b1cce597bca90b3e77a78c398'),
    NEW + 'source-manifest.json': (20530, 'ae2168d74fb483a210f575f8343f25bac023dec7dd22dea68087d288036d1291'),
    NEW + 'produce.py': (22614, '95395e855f9282e01cb59be528e1e8188d16506bdcfeb0b49d6294f64b391cd4'),
}

def identity(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def save(name, value):
    raw = (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode()
    with (OUT / name).open('xb') as stream:
        stream.write(raw)
    return identity(raw)

def main():
    OUT.mkdir(parents=True, exist_ok=False)
    save('claim.json', {'scope': 'raw_fragment_seed_only', 'PE_engine_tests_game': 0})
    raw_files = {}
    events = []
    total = 0
    for rel, (size, digest) in FIXED.items():
        path = ROOT / rel
        assert path.stat().st_size == size <= 4 * 1024 * 1024
        raw = path.read_bytes()
        assert identity(raw) == {'bytes': size, 'sha256': digest}
        raw_files[rel] = raw
        events.append({'path': rel, 'phase': 'before', **identity(raw)})
        total += len(raw)
    owned = json.loads(raw_files[PREFIX + 'owned-code.json'])
    capture = json.loads(raw_files[PREFIX + 'capture.json'])
    seed = json.loads(raw_files[NEW + 'entry-seed.json'])
    budget = json.loads(raw_files[NEW + 'budget.json'])
    review = json.loads(raw_files['work/reports/war-peace-api-20261015-r58-independent-review/findings.json'])
    assert review['sealed'] and review['passed'] and review['blocking_findings'] == []
    code = bytes.fromhex(owned['raw_hex'])
    assert code.hex() == '44884c2420555641564883ec30448bf2418be8488bf183fa0c720b33c04883c430415e5e5dc3'
    assert len(code) == 38 and hashlib.sha256(code).hexdigest() == owned['sha256']
    branch = 0x771bf9
    assert code[branch - 0x771be0:branch - 0x771be0 + 2] == bytes.fromhex('720b')
    target = branch + 2 + struct.unpack('<b', code[26:27])[0]
    assert target == 0x771c06 and 5 < 12
    neighbor = capture['next']
    begin, end, unwind = struct.unpack('<III', bytes.fromhex(neighbor['raw_hex']))
    assert neighbor['index'] == 14173 and begin == target and end == 0x771cbd and end - begin == 183
    assert neighbor['raw_hex'] == '061c7700bd1c7700704ee501' and unwind == 0x1e54e70
    assert seed['neighbor_pdata'] == {k: neighbor[k] for k in seed['neighbor_pdata']}
    assert seed['branch_site_rva'] == hex(branch) and seed['raw_branch'] == '720b'
    assert seed['fragment_rva'] == hex(target) and seed['fragment_end_exclusive'] == hex(end)
    state = seed['state_at_successor']
    assert state['fragment_is_independent_callable_entry'] is False
    assert state['RSP'] == 'Q-0x48' and 3 * 8 + 0x30 == 0x48
    assert state['R14'] == '0x0000000000000005' and state['RBP'] == '0x00000000ffffffff'
    assert state['RAX'] == state['R9'] == 'unchanged original unknown full64'
    assert state['flags'] == 'CMP uint32EDX5,imm12 => CF1/ZF0/SF1/OF0/PF1/AF1; JB taken'
    subtraction = (5 - 12) & 0xffffffff
    assert subtraction == 0xfffffff9 and (subtraction & 255).bit_count() % 2 == 0
    assert state['saved_stack_qwords'] == {'Q-8': 'originalRBP', 'Q-0x10': 'originalRSI', 'Q-0x18': 'originalR14'}
    assert budget['new_unique_code_bytes_max'] == 183 and budget['single_code_reads_max'] == 1
    assert budget['old_prefix_targeted_code_read_bytes'] == budget['old_prefix_new_decode_bytes'] == 0
    source = raw_files[NEW + 'produce.py'].decode()
    ast.parse(source)
    assert "ENTRY=0x771c06" in source and "size==183" in source
    assert "selected['index']==14173" in source and "selected['raw_hex']=='061c7700bd1c7700704ee501'" in source
    assert source.index("review.get('sealed')") < source.index('initial=sources()') < source.index('pe=SelectedPE(')
    for rel, (size, digest) in FIXED.items():
        raw = (ROOT / rel).read_bytes()
        assert identity(raw) == {'bytes': size, 'sha256': digest}
        events.append({'path': rel, 'phase': 'after', **identity(raw)})
        total += len(raw)
    assert total <= 4 * 1024 * 1024
    result = {'schema': 'EU4-R59-INDEPENDENT-RAW-FRAGMENT-SEED-REVIEW/1',
              'sealed': True, 'passed': True, 'blocking_findings': [],
              'entry_seed_pin': identity(raw_files[NEW + 'entry-seed.json']),
              'branch_site_rva': hex(branch), 'raw_branch': '720b', 'entry_rva': hex(target),
              'scope': 'raw_fragment_seed_only', 'source_pins': events,
              'checks': ['Raw retained prefix, rel8 target and next pdata tuple agree.',
                         'EDX5 takes unsigned JB; original Q-48 frame and saved registers retained.',
                         'No new callable-entry ABI is asserted; original unknown R9/RAX retained.',
                         'One fixed183B future read; no old38B targeted read/decode; external reads closed.',
                         'Producer source parsed/read only; root review precedes engine and PE access.'],
              'limits': ['Not a full producer audit, runtime execution, ID semantics or uniqueness proof.',
                         'Eight retained files authenticated before/after; decoder/PE not opened.'],
              'physical_source_bytes': total, 'PE_decoder_tests_game_native_requests': 0,
              'authority': {'native_ready': False, 'callable': False, 'effect_verified': False,
                            'lease': False, 'retry': False}}
    findings = save('findings.json', result)
    manifest = save('manifest.json', {'sealed': True, 'findings': findings, 'sources': events,
                                     'script': identity(Path(__file__).read_bytes())})
    print(json.dumps({'passed': True, 'findings': findings, 'manifest': manifest, 'source_bytes': total}))

if __name__ == '__main__':
    main()
