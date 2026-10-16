"""Review retained callers of3383b0; does not execute a decoder or open the PE."""
import ast
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEW = 'work/reports/war-peace-api-20261016-r60-balance-sink/'
OLD = 'work/reports/native-pair-extension-v11-1375.json'
AUDIT = 'work/reports/war-peace-gold-helper-crosswalk-independent-review-20261016-r1/findings.json'
OUT = ROOT / 'work/reports/war-peace-api-20261016-r60-entry-root-review'
FIXED = {
    OLD: (2010953, 'ac4559379e218aaf1fa8ffc1dd7dc6b8332ed5b7bf681c4b66bfc59349944344'),
    AUDIT: (7480, '7241a6f2de11d9757154885f36c10de4a539da240d264a53f15a551bd9f57c05'),
    NEW + 'source-manifest.json': (22020, '6632b627119ae5905390310b78d94fe3fb0e40ab47a695fdfb2bc3b1c621051b'),
    NEW + 'entry-seed.json': (10836, '1798bc406f1761db3e5f0b55d898d1f820f1e07619a43176452db97c2d5a94d7'),
    NEW + 'produce.py': (22048, '0a595fbc87ce34782ef3e13c79358ea930379fbb7e8c0ef575be78db1a1aeca6'),
    NEW + 'budget.json': (1524, '522bc44ffe148ec02dc8041081c03ac76ec8c47a3fd6216b9de40304f41741e3'),
    NEW + 'PROTOCOL.md': (2771, '8a091459675c30657f042aff203214ffc396ff782f434a4e7a604809216bd97b'),
}

def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def save(name, value):
    raw = (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode()
    with (OUT / name).open('xb') as stream:
        stream.write(raw)
    return pin(raw)

def resolve(data, pointer):
    for key in pointer.strip('/').split('/'):
        data = data[int(key)] if isinstance(data, list) else data[key]
    return data

def main():
    OUT.mkdir(parents=True, exist_ok=False)
    save('claim.json', {'scope': 'raw_caller_entry_only', 'PE_decoder_game': 0})
    files = {}
    events = []
    total = 0
    for rel, (size, digest) in FIXED.items():
        path = ROOT / rel
        assert path.stat().st_size == size <= 4 * 1024 * 1024
        raw = path.read_bytes()
        assert pin(raw) == {'bytes': size, 'sha256': digest}
        files[rel] = raw
        events.append({'path': rel, 'phase': 'before', **pin(raw)})
        total += len(raw)
    source = json.loads(files[OLD])
    seed = json.loads(files[NEW + 'entry-seed.json'])
    budget = json.loads(files[NEW + 'budget.json'])
    independent = json.loads(files[AUDIT])
    assert independent['sealed'] and independent['passed'] and independent['blocking_findings'] == []
    assert independent['subject_manifest'] == seed['crosswalk_manifest']
    assert independent['subject_crosswalk'] == seed['crosswalk']
    assert seed['entry_rva'] == '0x3383b0' and seed['original_source_pin'] == pin(files[OLD])
    assert seed['proven_call_sites'] == ['0x3385d3', '0x3388b8']
    assert seed['proven_raw_calls'] == ['e8d8fdffff', 'e8f3faffff']
    refs = 0
    for item in seed['raw_caller_seeds']:
        for row in item['relevant_entry_captures'] + item['contiguous_context'] + [item['call']]:
            original = resolve(source, row['json_pointer'])
            assert all(row[k] == original[k] for k in ('rva', 'bytes', 'instruction'))
            refs += 1
        cursor = int(item['contiguous_context'][0]['rva'], 16)
        for row in item['contiguous_context']:
            assert int(row['rva'], 16) == cursor
            cursor += len(bytes.fromhex(row['bytes']))
        call = item['call']
        raw = bytes.fromhex(call['bytes'])
        assert raw[0] == 0xe8 and len(raw) == 5
        assert int(call['rva'], 16) + 5 + struct.unpack('<i', raw[1:])[0] == 0x3383b0
        assert item['R8'].startswith('volatile current value unknown')
        assert item['R9'] == 'volatile current value unknown at sink CALL'
        assert item['stack_arguments'] == 'unknown'
    income, expense = seed['raw_caller_seeds']
    assert [r['bytes'] for r in income['contiguous_context']] == ['8b06', '894530', '488d5530', '488bcf', 'e8d8fdffff']
    assert [r['bytes'] for r in expense['contiguous_context']][-6:] == [
        '418b06', 'f7d8', '898424b0000000', '488d9424b0000000', '488bcf', 'e8f3faffff']
    preceding = expense['contiguous_context'][-7]
    assert preceding['rva'] == '0x33889c' and preceding['bytes'] == 'e8bf957b00'
    assert 0x33889c + 5 + struct.unpack('<i', bytes.fromhex(preceding['bytes'])[1:])[0] == 0xaf1e60
    assert income['relevant_entry_captures'][1]['bytes'] == '498bf0'
    assert expense['relevant_entry_captures'][1]['bytes'] == '4d8bf0'
    assert income['relevant_entry_captures'][-1]['bytes'] == expense['relevant_entry_captures'][-1]['bytes'] == '488bf9'
    assert budget['new_unique_code_bytes_max'] == 8192 and budget['pdata_record_requests_max'] == 32
    producer = files[NEW + 'produce.py'].decode()
    ast.parse(producer)
    assert "ENTRY=0x3383b0" in producer and "amount=extent if extent<=8192 else 2048" in producer
    assert producer.index("cross_review.get('subject_crosswalk')") < producer.index('initial=sources()') < producer.index('pe=SelectedPE(')
    for rel, (size, digest) in FIXED.items():
        raw = (ROOT / rel).read_bytes()
        assert pin(raw) == {'bytes': size, 'sha256': digest}
        events.append({'path': rel, 'phase': 'after', **pin(raw)})
        total += len(raw)
    assert total <= 8 * 1024 * 1024
    findings = save('findings.json', {
        'schema': 'EU4-R60-INDEPENDENT-CALLER-SEED-REVIEW/1',
        'sealed': True, 'passed': True, 'blocking_findings': [],
        'entry_seed_pin': pin(files[NEW + 'entry-seed.json']), 'entry_rva': '0x3383b0',
        'callsite_rvas': seed['proven_call_sites'], 'raw_calls': seed['proven_raw_calls'],
        'scope': 'raw_caller_entry_only', 'source_pins': events, 'verified_row_references': refs,
        'checks': ['Both original E8 signed-relative calls resolve3383b0.',
                   'Income freshly reads saved originalR8 pointer, copies DWORD and passes its address.',
                   'Expense af1e60 return precedes fresh originalR8 read, NEG32 and local-copy address.',
                   'RCX restored from nonvolatileRDI; current R8/R9/stack remain unknown.',
                   'Full crosswalk review subjects agree; source-only producer AST gate before PE/engine.'],
        'limits': ['Only raw callers and future scope checked; no callee formal or balance write established.',
                   'Normal ABI preserves registers, not their pointed-to contents; amount unit remains unknown.',
                   'No complete producer or runtime audit is asserted.'],
        'physical_source_bytes': total, 'PE_decoder_tests_game_native_requests': 0,
        'authority': {'callable': False, 'native_ready': False, 'effect_verified': False,
                      'lease': False, 'retry': False}})
    manifest = save('manifest.json', {'sealed': True, 'findings': findings, 'sources': events,
                                     'script': pin(Path(__file__).read_bytes())})
    print(json.dumps({'passed': True, 'findings': findings, 'manifest': manifest, 'source_bytes': total}))

if __name__ == '__main__':
    main()
