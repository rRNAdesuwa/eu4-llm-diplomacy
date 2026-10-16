"""Independent fixed-file R23 replay. No decoder, author producer, or process use."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'work/reports/war-peace-api-20261015-r23-truce-observation-contract/war'
OUT = ROOT / 'work/reports/war-peace-api-20261015-r23-independent-review/war'
EXE = ROOT.parent / 'eu4.exe'
GAME_SHA = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'


def pin(path):
    h = hashlib.sha256(); size = 0
    with path.open('rb') as stream:
        while block := stream.read(65536):
            size += len(block); h.update(block)
    return {'bytes': size, 'sha256': h.hexdigest()}


def load(path):
    assert path.stat().st_size <= 8 * 1024 * 1024
    return json.loads(path.read_text(encoding='utf-8'))


def write_new(path, data):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(data if isinstance(data, str) else json.dumps(data, indent=2) + '\n')


class FilePE:
    def __init__(self, stream):
        self.stream = stream; self.reads = self.bytes = 0
        dos = self.at(0, 64); assert dos[:2] == b'MZ'
        start = struct.unpack_from('<I', dos, 60)[0]
        coff = self.at(start, 24)
        assert coff[:4] == b'PE\0\0' and struct.unpack_from('<H', coff, 4)[0] == 0x8664
        n, size = struct.unpack_from('<H', coff, 6)[0], struct.unpack_from('<H', coff, 20)[0]
        assert 0 < n <= 32 and 112 <= size <= 512
        opt = self.at(start + 24, size)
        assert struct.unpack_from('<H', opt)[0] == 0x20b
        assert struct.unpack_from('<Q', opt, 24)[0] == 0x140000000
        raw = self.at(start + 24 + size, n * 40)
        self.sections = [struct.unpack_from('<IIII', raw, i + 8)[1:] for i in range(0, len(raw), 40)]
        self.header_reads, self.header_bytes = self.reads, self.bytes
        self.reads = self.bytes = 0

    def at(self, offset, size):
        assert 0 < size <= 4096 and 0 <= offset <= 38462504 - size
        self.stream.seek(offset); value = self.stream.read(size)
        assert len(value) == size
        self.reads += 1; self.bytes += size
        return value

    def offset(self, rva, size):
        matches = [offset + rva - va for va, count, offset in self.sections
                   if va <= rva and rva + size <= va + count]
        assert len(matches) == 1
        return matches[0]

    def rva(self, rva, size):
        return self.at(self.offset(rva, size), size)


def raw(row):
    return bytes.fromhex(row['bytes'])


def target(row):
    b = raw(row); at = int(row['rva'], 16)
    if b[0] == 0xe8:
        assert len(b) == 5
        return at + 5 + struct.unpack('<i', b[1:])[0]
    assert b[0] in (0x74, 0x75) and len(b) == 2
    return at + 2 + struct.unpack('<b', b[1:])[0]


def rip_target(row):
    b = raw(row)
    assert len(b) == 7 and b[:3] in (bytes.fromhex('488b05'), bytes.fromhex('488d15'))
    return int(row['rva'], 16) + 7 + struct.unpack('<i', b[3:])[0]


def check():
    m = load(OUT / 'manifest.json'); assert m['sealed'] is True
    for name, wanted in m['source_pins'].items():
        assert pin(ROOT / name) == wanted, name
    for name, wanted in m['artifact_pins'].items():
        assert pin(Path(name)) == wanted, name
    print(json.dumps({'status': 'pass', 'source_pins': len(m['source_pins']),
                     'artifact_pins': len(m['artifact_pins']), 'new_decode_bytes': 0,
                     'process_accessed': False, 'producer_executed': False}))


def main():
    assert pin(SRC / 'manifest.json') == {'bytes': 2375, 'sha256': '27173b65e73e13f64c42c0891b7b299602a6a7944b2946f48907d17a3d9f7778'}
    m = load(SRC / 'manifest.json')
    assert m['sealed'] is True and m['native_ready'] is False
    assert len(m['files']) == 6 and len(m['sources']) == 7
    selected = dict(m['sources'])
    selected.update({(SRC / name).relative_to(ROOT).as_posix(): value for name, value in m['files'].items()})
    for name, wanted in selected.items():
        assert pin(ROOT / name) == wanted, name
    assert pin(EXE) == {'bytes': 38462504, 'sha256': GAME_SHA}
    c = load(SRC / 'contract.json'); d = load(SRC / 'selected-decode.json')
    e = load(SRC / 'retained-evidence.json'); v = load(SRC / 'verification.json')
    assert c['game_sha256'] == d['game_sha256'] == e['game_sha256'] == GAME_SHA
    assert v['status'] == 'file_only_verified' and v['new_decoded_bytes'] == 0
    assert all(value is False for value in c['authority'].values())
    receipt = load(ROOT / 'work/deps/capstone-5.0.7.receipt.json')
    assert len(d['selected_dependency_pins']) == 38
    assert all(receipt['files'][name] == value for name, value in d['selected_dependency_pins'].items())
    # This compares retained dependency metadata only. No Capstone import/engine invocation.
    window = bytes.fromhex(d['read_raw_hex']); code = bytes.fromhex(d['selected_instruction_bytes_hex'])
    assert d['authorized_window'] == ['0x506d70', '0x506e60']
    assert len(window) == d['read_bytes'] == 240 and len(code) == d['new_decoded_bytes'] == 229
    assert window[:229] == code and window[229:] == b'\xcc' * 11
    assert hashlib.sha256(window).hexdigest() == d['read_raw_sha256']
    assert hashlib.sha256(code).hexdigest() == d['selected_instruction_bytes_sha256']
    rows = {int(row['rva'], 16): row for row in d['instructions']}
    cursor = 0x506d70; joined = bytearray()
    for row in d['instructions']:
        assert int(row['rva'], 16) == cursor
        joined.extend(raw(row)); cursor += len(raw(row))
    assert cursor == 0x506e55 and joined == code and len(rows) == len(d['instructions'])
    assert [row['rva'] for row in d['instructions'] if row['mnemonic'] == 'ret'] == d['ret_rvas'] == ['0x506e42', '0x506e54']
    edges = []
    for edge in d['edges']:
        row = rows[int(edge['source_rva'], 16)]
        actual = target(row)
        assert actual == int(edge['target_rva'], 16)
        assert row['mnemonic'] == edge['kind'] and edge['callee_followed'] is False
        assert edge['target_is_selected_instruction'] == (actual in rows)
        edges.append((int(edge['source_rva'], 16), actual, edge['kind']))
    assert [x for x in edges if x[2] == 'call'] == [(0x506dba, 0x2f1590, 'call'), (0x506e05, 0x40a6d0, 'call'), (0x506e0d, 0x7ae260, 'call')]
    assert len([x for x in edges if x[2] != 'call']) == 5
    assert len(edges) == len([r for r in rows.values() if r['mnemonic'] in ('call', 'je', 'jne')]) == 8
    assert rip_target(rows[0x506d7f]) == rip_target(rows[0x506def]) == 0x233d8d0
    original_rows = {}; old_bytes = 0; old_rows = 0
    for name in {b['source'] for b in e['selected_blocks']}:
        original = load(ROOT / name)
        assert original['game_sha256'] == GAME_SHA
        original_rows[name] = {f['entry_rva']: {row['rva']: row for row in f['instructions']} for f in original['functions']}
    with EXE.open('rb') as stream:
        pe = FilePE(stream)
        assert pe.offset(0x506d70, 240) == d['file_offset'] == 5267824
        assert pe.rva(0x506d70, 240) == window
        for block in e['selected_blocks']:
            original = original_rows[block['source']][block['function_rva']]
            start, end = int(block['start_rva'], 16), int(block['end_exclusive'], 16)
            chunk = b''.join(raw(row) for row in block['instructions'])
            assert len(chunk) == block['bytes'] == end - start
            assert chunk.hex() == block['raw_hex']
            assert hashlib.sha256(chunk).hexdigest() == block['raw_sha256']
            at = start
            for row in block['instructions']:
                assert int(row['rva'], 16) == at and original[row['rva']] == row
                at += len(raw(row))
            assert at == end and pe.rva(start, len(chunk)) == chunk
            old_bytes += len(chunk); old_rows += len(block['instructions'])
        for literal in e['selected_literals']:
            at = literal['instruction_rva']
            matching = [r for f in original_rows[literal['source']].values() for key, r in f.items() if key == at]
            assert matching and all(row == matching[0] for row in matching)
            assert rip_target(matching[0]) == int(literal['string_rva'], 16)
            text = literal['text'].encode('ascii') + b'\0'
            assert pe.rva(int(literal['string_rva'], 16), len(text)) == text
            assert hashlib.sha256(text).hexdigest() == literal['sha256']
        replay = {'selected_reads': pe.reads, 'selected_bytes': pe.bytes,
                  'header_reads': pe.header_reads, 'header_bytes': pe.header_bytes}
    assert len(e['selected_blocks']) == 7 and old_bytes == 504
    assert raw(rows[0x506d89]) == bytes.fromhex('488b5110')
    assert raw(rows[0x506da7]) == bytes.fromhex('488b4120')
    assert raw(rows[0x506dbf]) == bytes.fromhex('4c8b83f0180000')
    assert raw(rows[0x506dc9]) == bytes.fromhex('48c1e938')
    assert raw(rows[0x506de8]) == raw(rows[0x506e2a]) == bytes.fromhex('f644d04501')
    assert raw(rows[0x506de1]) == raw(rows[0x506e23]) == bytes.fromhex('488b8710150000')
    assert raw(rows[0x506dd9]) == bytes.fromhex('410fbfc0') and raw(rows[0x506e1e]) == b'\x98'
    assert raw(rows[0x506d9b]) == bytes.fromhex('480fbfc2')
    assert raw(rows[0x506daf]) == bytes.fromhex('480fbfc0')
    assert raw(rows[0x506df6]) == bytes.fromhex('490fbfd0')
    # Replay only selected conditional edges. Callee AL values are hypothetical inputs,
    # not executed helpers, simultaneous world observations, or semantic assertions.
    def branch_path(high_byte, first_al, linked_bit, last_al, direct_bit):
        path = []; calls = []; at = 0x506d70
        decisions = {0x506dcf: not high_byte, 0x506dd3: not first_al,
                     0x506ded: not linked_bit, 0x506e14: not last_al, 0x506e2f: direct_bit}
        while True:
            row = rows[at]; path.append(row['rva'])
            if row['mnemonic'] == 'call': calls.append(hex(target(row)))
            if row['mnemonic'] == 'ret': break
            at = target(row) if at in decisions and decisions[at] else at + len(raw(row))
        assert len(path) <= len(rows)
        return {'path': path, 'unfollowed_calls': calls, 'AL_true_return': path[-1] == '0x506e54'}
    shortcut = branch_path(True, True, True, False, False)
    direct_false = branch_path(False, False, False, False, False)
    direct_true = branch_path(False, False, False, False, True)
    assert shortcut['AL_true_return'] and not direct_false['AL_true_return'] and direct_true['AL_true_return']
    assert shortcut['unfollowed_calls'] == ['0x2f1590', '0x40a6d0', '0x7ae260']
    assert direct_false['unfollowed_calls'] == direct_true['unfollowed_calls'] == ['0x2f1590']
    reader_source = (ROOT / 'bridge/diplomacy_effect_observer.py').read_text(encoding='utf-8')
    reader_lines = reader_source.splitlines()
    for line in e['existing_reader_profile']['lines']:
        assert reader_lines[line['line'] - 1] == line['text']
    tree = ast.parse(reader_source)
    funcs = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    ptr_node, handle_node = funcs['ptr'], funcs['full_handle']
    assert not any(isinstance(node, ast.Mod) for node in ast.walk(ptr_node))
    assert '0x10000 <= value < 2**47' in ast.get_source_segment(reader_source, ptr_node)
    assert '0 < slot < min(count, 32768)' in ast.get_source_segment(reader_source, handle_node)
    assert 0x14f8 + 0x18 == 0x1510
    signed16 = lambda value: value if value < 0x8000 else value - 0x10000
    malformed = {'slot_bits': '0xffff', 'signed16': signed16(0xffff),
                 'cache_RAX_after_EAX_write': hex(signed16(0xffff) & 0xffffffff),
                 'signed64_RAX': hex(signed16(0xffff) & ((1 << 64) - 1)),
                 'accepted_by_frozen_full_handle_slot_bounds': False}
    assert malformed['cache_RAX_after_EAX_write'] != malformed['signed64_RAX']
    unaligned = {'begin': hex(0x100001), 'end': hex(0x100001 + 1380 * 0x48),
                 'capacity': hex(0x100001 + 1380 * 0x48), 'selected_slot': 1,
                 'passes_canonical_and_extent_algebra_only': True,
                 'begin_eight_aligned': False, 'complete_typed_fixture_executed': False}
    assert 0x10000 <= 0x100001 < 2**47 and 1380 * 0x48 <= 4096 * 0x48
    assert 0x100001 % 8 != 0
    report = {
        'schema': 'EU4-R23-INDEPENDENT-TRUCE-STATIC-REVIEW/1',
        'status': 'static_ready_selected_direct_pair_cache_with_precision_clarifications',
        'source_manifest': pin(SRC / 'manifest.json'), 'source_contract': pin(SRC / 'contract.json'),
        'source_pins_verified': {'local': 6, 'selected_external': 7},
        'retained_dependency_metadata_count': 38, 'dependency_engine_executed': False,
        'review_prepublication_correction': 'Initial review wrapper incorrectly required selected38 dependencies equal the full102-file receipt. It stopped before outputs. Corrected to exact selected subset matching; no source evidence changed.',
        'review_new_decode_bytes': 0, 'retained_new_decode_bytes': 229,
        'selected_instruction_rows': len(rows), 'retained_blocks': 7, 'retained_block_bytes': old_bytes,
        'retained_block_instruction_rows': old_rows, 'PE_file_replay': replay,
        'window': ['0x506d70', '0x506e60'], 'selected_extent': ['0x506d70', '0x506e55'],
        'normal_RET_sites': d['ret_rvas'], 'internal_conditional_edges': 5,
        'unfollowed_callees': ['0x2f1590', '0x40a6d0', '0x7ae260'],
        'observed_static_field': {'owner_array_pointer_offset': '0x1510', 'typed_root_offset': '0x14f8',
            'typed_root_array_offset': '0x18', 'row_stride': '0x48', 'field_byte': '0x45', 'mask': '0x01',
            'safe_formula_scope': 'valid positive typed slot below min(country_count,32768); row=begin+slot*0x48',
            'directional': True, 'reverse_equality_proven': False,
            'semantics': 'native-consumed directional truce cache flag; not typed truce object or expiry'},
        'literal_anchors': e['selected_literals'],
        'helper_is_direct_flag_getter': False, 'helper_side_effect_free_proven': False,
        'conditional_path_examples': {'linked_shortcut_true_with_direct_bit_clear': shortcut,
            'direct_bit_clear': direct_false, 'direct_bit_set': direct_true,
            'example_grade': 'data-only selected CFG replay with hypothetical callee AL, not runtime/whole-world Boolean evaluation'},
        'findings': [
            {'id': 'R23-PRECISION-1', 'severity': 'scope_clarification',
             'location': 'contract.json pair_cache.record_address; native_consumer.ordered_control_flow',
             'evidence': '506dd9 MOVSX EAX,R8W and506e1e CWDE write EAX, zero-extending upper RAX; country resolution uses64-bit MOVSX instead.',
             'counterexample': malformed,
             'required_scope': 'For valid positive typed slots the formula is correct. Do not generalize signed16 address algebra to malformed negative slots; these are rejected before a future observer read.'},
            {'id': 'R23-PRECISION-2', 'severity': 'contract_guard_overstatement',
             'location': 'contract.json typed_pair_identity_reuse.bounds; frozen observer.ptr59..61/relation168..171',
             'evidence': 'Frozen ptr checks exact-int and canonical range, not modulo alignment; ordered extent differences divisible by0x48 do not imply begin alignment.',
             'counterexample': unaligned,
             'required_scope': 'Describe reused guard as canonical only, or add explicit8-byte alignment checks in a new standalone reader before claiming aligned pointers. Do not modify frozen reader.'}],
        'future_read_side_scope': {
            'country_identity': 'fresh typed country vtable/marker and exact complete handle',
            'relation_identity': 'fresh typed root357/owner, bounded ordered begin/end/cap, exact row root/owner/other handles, unchanged header',
            'directions': 'Resolve and guard both owner-to-other rows independently; keep raw bytes and sampled flag separately.',
            'additional_alignment_if_claimed': 'explicit selected country/root/begin/row8-byte alignment in independent new layer',
            'helper_or_callee_execution': False, 'peace_completion_or_request_causality': False,
            'actual_reader_implemented_or_run_in_review': False},
        'unknown': ['truce object type/index/global membership', 'expiry/deadline/date units/removed lifecycle',
                    'callee semantics/effects/reentrancy', 'current runtime flags', 'pair symmetry',
                    'atomic/world/header lease', 'peace completion and request causality'],
        'limits': ['Two RETs/internal branch closure cover the selected normal body only; no pdata/unwind/exception proof.',
                   'Existing relation deadline+0x30 is not established as truce expiry; war flag+0x46 mask4 is separate.',
                   'Static current flag means sampled at native-consumer time, not a runtime sample made in this review.',
                   'No new decoding, author producer/verifier, tests, Capstone engine, process access, REA, Frida or native execution.',
                   'Disk PE identity and exact selected code/string bytes are replayed; no callee, table, or full-PE instruction scan.'],
        'producer_executed': False, 'tests_executed': False, 'process_accessed': False, 'Frida_loaded': False,
        'new_native_calls': 0, 'new_API_effects': 0, 'authority': c['authority']}
    assert not OUT.exists(); OUT.mkdir(parents=True)
    write_new(OUT / 'findings.json', report)
    write_new(OUT / 'report.md',
        '# R23 停战缓存合同独立静态复核\n\n'
        '6本地与7来源pin、229B helper、7旧slice/504B、3个literal和对应PE字节一致。'
        '两RET、5个内部条件分支及3个外callee目标相符；未展开callee。\n\n'
        '可采用的静态范围：已验证正slot对应的方向性relation row+45 mask1停战缓存位。'
        'helper始终调用2f1590，并有target+18f0关联国家短路，因此不能作为directflag getter或证明纯读取；反向位须独立取样。\n\n'
        '两处精度修正必须随采用保留：缓存slot的EAX写入会清RAX高32位，signed16地址公式仅限合法正slot；'
        '冻结ptr只有canonical范围检查，未显式检查8字节对齐，不能宣称旧reader已含该guard。新观察层可另加对齐核验，旧文件不改。\n\n'
        'truce对象、期限、removed、dateunits、当前状态、议和完成与请求因果均未知。'
        '本审计仅文件与选定PE字节重放，0新decode/进程/Frida/native/test；所有authority仍false。\n')
    for path in (SRC / 'manifest.json', SRC / 'verification.json', Path(__file__).resolve(), OUT / 'findings.json', OUT / 'report.md'):
        selected[path.relative_to(ROOT).as_posix()] = pin(path)
    write_new(OUT / 'manifest.json', {'schema': 'EU4-R23-INDEPENDENT-STATIC-REVIEW-MANIFEST/1',
        'sealed': True, 'source_pins': dict(sorted(selected.items())), 'artifact_pins': {str(EXE): pin(EXE)},
        'native_ready': False, 'source_contract_unchanged': True})
    print(json.dumps({'status': report['status'], 'findings': pin(OUT / 'findings.json'),
        'manifest': pin(OUT / 'manifest.json'), 'source_pins': len(selected), 'PE_file_replay': replay}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--check', action='store_true')
    check() if parser.parse_args().check else main()
