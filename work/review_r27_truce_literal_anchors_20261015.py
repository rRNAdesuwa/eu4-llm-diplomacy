"""Independent R27 retained-file/source review. Never open the PE or scan bytes."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT/'work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war'
OUT = ROOT/'work/reports/war-peace-api-20261015-r27-independent-review/war'
GAME_SHA = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
GAME_BYTES = 38462504


def pin(path):
    assert path.resolve().is_relative_to(ROOT.resolve()),'Only projectfiles, never PE/external artifacts'
    assert path.stat().st_size <= 1024*1024
    value = path.read_bytes()
    return {'bytes':len(value),'sha256':hashlib.sha256(value).hexdigest()}


def load(path):
    assert path.stat().st_size <= 1024*1024
    def unique(pairs):
        out = {}
        for key,value in pairs:
            assert key not in out; out[key] = value
        return out
    return json.loads(path.read_bytes().decode('utf-8'),object_pairs_hook=unique)


def write_new(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(value if isinstance(value,str) else json.dumps(value,indent=2)+'\n')


def check():
    m = load(OUT/'manifest.json'); assert m['sealed'] is True
    for name,wanted in m['source_pins'].items(): assert pin(ROOT/name) == wanted,name
    print(json.dumps({'status':'pass','local_pins':len(m['source_pins']),'PE_opened':False,
        'search_repeated':False,'decoder_executed':False,'tests_run':0,'target_process_accessed':False}))


def main():
    assert pin(SRC/'manifest.json') == {'bytes':1348,'sha256':'dae78fc218585483d51f9370a9a10dbe503f0349e990d66b4c9b67de52f8c50f'}
    assert pin(SRC/'anchors.json') == {'bytes':12398,'sha256':'0d10e6676653d92a440fe14259729719219e2c1c008a114da42df1d92287b94e'}
    m = load(SRC/'manifest.json'); assert m['sealed'] is True and m['native_ready'] is False
    selected = dict(m['sources'])
    selected.update({(SRC/name).relative_to(ROOT).as_posix():wanted for name,wanted in m['files'].items()})
    assert len(m['files']) == 5 and len(m['sources']) == 2
    for name,wanted in selected.items(): assert pin(ROOT/name) == wanted,name
    d = load(SRC/'anchors.json'); claim = load(SRC/'claim.json'); receipt = load(SRC/'verification.json')
    assert d['status'] == 'complete_bounded_raw_anchor_inventory' and d['errors'] == []
    assert d['game_sha256'] == claim['game_sha256'] == GAME_SHA
    assert d['game_bytes'] == claim['game_bytes'] == GAME_BYTES
    assert d['source_pins'] == claim['source_pins'] and d['source_guard_post_equal'] is True
    assert len(d['source_pins']) == 3
    for name,wanted in d['source_pins'].items(): assert selected[name] == wanted
    assert d['literal_pattern_hex'] == claim['literal_pattern_hex'] == '00747275636500'
    assert d['chunk_bytes'] == claim['chunk_bytes'] == 65536 and d['overlap_bytes'] == claim['overlap_bytes'] == 6
    assert d['max_literals'] == claim['max_literals'] == 64 and d['max_candidates'] == claim['max_candidates'] == 128
    assert d['literal_limit_exceeded'] is d['candidate_limit_exceeded'] is False
    assert d['literal_search_complete'] is d['candidate_search_complete_for_found_literals'] is True
    assert claim['arbitrary_targets_allowed'] is claim['retry_authorized'] is False
    assert receipt['manifest'] == pin(SRC/'manifest.json') and receipt['PE_reads_by_verifier'] == 0
    auth = d['full_PE_authentication_reads']
    assert [row['phase'] for row in auth] == ['before','after']
    for row in auth:
        assert row['file_range'] == [0,GAME_BYTES] and row['bytes_read'] == GAME_BYTES
        assert row['sha256'] == GAME_SHA and row['complete'] is row['fixed_sha_matches'] is True
    headers = d['PE_header_reads']; assert len(headers) == 4
    for row in headers:
        raw = bytes.fromhex(row['raw_hex']); start,end = row['file_range']
        assert 0 <= start < end <= GAME_BYTES and len(raw) == end-start == row['bytes_read'] <= 2048
    dos,coff,opt,table = [bytes.fromhex(row['raw_hex']) for row in headers]
    pe = struct.unpack_from('<I',dos,60)[0]; count = struct.unpack_from('<H',coff,6)[0]
    optional_bytes = struct.unpack_from('<H',coff,20)[0]
    assert dos[:2] == b'MZ' and coff[:4] == b'PE\0\0'
    assert struct.unpack_from('<H',coff,4)[0] == 0x8664 and count == 7 and optional_bytes == 240
    assert struct.unpack_from('<H',opt)[0] == 0x20b and struct.unpack_from('<Q',opt,24)[0] == 0x140000000
    assert [row['file_range'] for row in headers] == [[0,64],[pe,pe+24],
        [pe+24,pe+24+optional_bytes],[pe+24+optional_bytes,pe+24+optional_bytes+count*40]]
    sections = d['sections']; assert len(sections) == count
    for index,row in enumerate(sections):
        raw = table[index*40:(index+1)*40]
        virtual,rva,size,offset = struct.unpack_from('<IIII',raw,8)
        flags = struct.unpack_from('<I',raw,36)[0]
        assert row['index'] == index and row['section_header_raw_hex'] == raw.hex()
        assert row['name'] == raw[:8].rstrip(b'\0').decode('ascii')
        assert row['virtual_size'] == virtual and row['rva'] == hex(rva)
        assert row['raw_size'] == size and row['raw_file_offset'] == offset
        assert row['characteristics'] == hex(flags) and row['executable'] is bool(flags&0x20000000)
        assert row['raw_file_range'] == [offset,offset+size] and 0 <= offset <= offset+size <= GAME_BYTES
        assert row['raw_mapped_rva_range'] == [hex(rva),hex(rva+size)] and rva+size <= 2**32
    spans = sorted(row['raw_file_range'] for row in sections if row['raw_size'])
    mapped = sorted((int(row['rva'],16),int(row['rva'],16)+row['raw_size']) for row in sections if row['raw_size'])
    assert all(left[1] <= right[0] for left,right in zip(spans,spans[1:]))
    assert all(left[1] <= right[0] for left,right in zip(mapped,mapped[1:]))
    assert spans[0][0] == 1024 and spans[-1][1] == 38452224
    assert all(left[1] == right[0] for left,right in zip(spans,spans[1:]))
    assert len([row for row in sections if row['name'] == '.text' and row['executable'] and row['raw_size']]) == 1
    assert len(d['literals']) == 2 and len(d['raw_candidates']) == 1
    literal_rows = []; offsets = set()
    for item in d['literals']:
        section = sections[item['section_index']]; offset = item['literal_file_offset']
        assert section['name'] == item['section'] and section['executable'] is False
        assert section['raw_file_offset'] <= offset-1 < offset+6 <= section['raw_file_offset']+section['raw_size']
        rva = int(section['rva'],16)+offset-section['raw_file_offset']
        assert item['literal_rva'] == hex(rva)
        assert item['boundary_file_range'] == [offset-1,offset+6] and item['boundary_raw_hex'] == '00747275636500'
        assert item['literal_bytes_with_terminator_hex'] == '747275636500'
        assert item['complete_leading_and_trailing_NUL'] is True
        assert item['within_declared_virtual_size'] is (rva+6 <= int(section['rva'],16)+section['virtual_size']) is True
        assert offset not in offsets; offsets.add(offset)
        literal_rows.append({'section':item['section'],'literal_rva':item['literal_rva'],
            'literal_file_offset':offset,'boundary_file_range':item['boundary_file_range']})
    assert [row['literal_rva'] for row in literal_rows] == ['0x1d2e9cc','0x21e9cb4']
    item = d['raw_candidates'][0]; section = sections[item['section_index']]
    raw = bytes.fromhex(item['raw_hex']); at = item['file_offset']; rva = int(item['rva'],16)
    assert section['name'] == item['section'] == '.text' and section['executable'] is True
    assert raw.hex() == '4c8d053647eb00' and len(raw) == item['raw_bytes'] == 7
    assert raw[:2] in (b'\x48\x8d',b'\x4c\x8d') and raw[2]&0xc7 == 0x05
    assert section['raw_file_offset'] <= at < at+7 <= section['raw_file_offset']+section['raw_size']
    assert rva == int(section['rva'],16)+at-section['raw_file_offset'] == 0xe7a28f
    disp = struct.unpack_from('<i',raw,3)[0]
    assert disp == item['signed_disp32'] == 15419190 and rva+7+disp == 0x1d2e9cc
    assert item['arithmetic_target_rva'] == '0x1d2e9cc'
    assert hashlib.sha256(raw).hexdigest() == item['raw_sha256']
    for key in ('instruction_boundary_verified','analyzer_xref_verified','function_entry_verified'): assert item[key] is False
    expected = [row for row in sections if not row['executable'] and row['raw_size']]+[sections[0]]
    scans = d['raw_section_scan_reads']; assert len(scans) == 7 and d['text_scan_skipped_reason'] is None
    chunks = reused = 0
    for scan,section in zip(scans,expected):
        assert scan['section_index'] == section['index'] and scan['section'] == section['name']
        assert scan['file_range'] == section['raw_file_range'] and scan['raw_mapped_rva_range'] == section['raw_mapped_rva_range']
        assert scan['planned_bytes'] == scan['bytes_read'] == section['raw_size'] and scan['completed'] is True
        expected_phase = 'text_raw_RIP_LEA_encoding_filter' if section['executable'] else 'nonexecuting_exact_NUL_truce_NUL'
        assert scan['phase'] == expected_phase
        n = (section['raw_size']+65535)//65536
        assert scan['chunk_reads'] == n and scan['overlap_bytes_reused_in_memory'] == 6*(n-1)
        chunks += n; reused += 6*(n-1)
    assert chunks == 591 and reused == 3504
    accounts = {'full_PE_authentication_bytes':2*GAME_BYTES,'PE_header_bytes':sum(row['bytes_read'] for row in headers),
        'nonexecuting_section_raw_scan_bytes':sum(row['raw_size'] for row in sections if not row['executable']),
        'executable_text_raw_scan_bytes':sections[0]['raw_size']}
    assert accounts == {k:d['accounting'][k] for k in accounts}
    assert sum(accounts.values()) == d['accounting']['total_PE_file_bytes_read'] == 115376816
    assert d['accounting']['overlap_is_in_memory_not_extra_file_read'] is True and d['accounting']['new_decoded_bytes'] == 0
    assert d['complete_RIP_LEA_pattern_count'] == 156106
    assert d['memory_guard_bytes'] == 805306368 and d['peak_committed_bytes'] == 26128384
    assert d['hard_job_object_installed'] is False
    for key in ('disassembled_instruction_count','new_decoded_bytes','callee_expansions','process_accesses',
        'Frida_operations','native_game_calls','requests_published','tests_run'): assert type(d[key]) is int and d[key] == 0
    for key in ('native_ready','callable','expiry_verified','truce_object_layout_verified'): assert d[key] is False
    source = (SRC/'produce.py').read_text(encoding='utf-8'); tree = ast.parse(source)
    functions = {node.name:node for node in tree.body if isinstance(node,ast.FunctionDef)}
    classes = {node.name:node for node in tree.body if isinstance(node,ast.ClassDef)}
    methods = {node.name:node for node in classes['SparseFile'].body if isinstance(node,ast.FunctionDef)}
    windows = ast.get_source_segment(source,methods['windows'])
    literals = ast.get_source_segment(source,functions['literal_scan'])
    candidates = ast.get_source_segment(source,functions['raw_candidate_scan'])
    main_src = ast.get_source_segment(source,functions['main'])
    for fragment in ('want = min(CHUNK, section[\'raw_size\']-total)', 'window = carry+block',
        'window_offset = start+total-len(carry)', 'carry = window[-6:]', "row['completed'] = True"):
        assert fragment in windows
    for fragment in ('raw.find(LITERAL)', 'raw.find(LITERAL, position+1)', 'boundary not in seen',
        "if section['executable'] or not section['raw_size']", 'MAX_LITERALS', 'literal_offset = boundary+1'):
        assert fragment in literals
    for fragment in ("b'\\x48\\x8d', b'\\x4c\\x8d'", 'position+7 <= len(raw)', 'raw[position+2] & 0xc7 == 0x05',
        'file_offset in seen', 'code = raw[position:position+7]', "struct.unpack_from('<i', code, 3)[0]",
        'destination = rva+7+displacement', 'destination not in targets', 'MAX_CANDIDATES'):
        assert fragment in candidates
    assert main_src.index("reader.authenticate('before')") < main_src.index('reader.sections()') < main_src.index('literal_scan(')
    assert main_src.index('literal_scan(') < main_src.index('raw_candidate_scan(') < main_src.index("reader.authenticate('after')")
    assert main_src.index("reader.authenticate('after')") < main_src.index('source_graph() == initial')
    assert "not (HERE/'claim.json').exists() and not (HERE/'anchors.json').exists()" in main_src
    assert "'complete_bounded_raw_anchor_inventory'" in main_src and "except Exception as exc" in main_src
    assert "with (HERE/name).open('x'" in source
    attrs = {node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute)}
    assert not attrs.intersection({'disasm','OpenProcess','ReadProcessMemory','WriteProcessMemory','attach','publish','submit'})
    guard_source = (ROOT/'work/discover_diplomacy.py').read_text(encoding='utf-8')
    guard_tree = ast.parse(guard_source)
    guard = next(node for node in guard_tree.body if isinstance(node,ast.FunctionDef) and node.name == 'check_memory_budget')
    guard_text = ast.get_source_segment(guard_source,guard)
    assert 'GetCurrentProcess' in guard_text and '768 * 1024 * 1024' in guard_text and 'OpenProcess' not in guard_text
    report = {'schema':'EU4-R27-INDEPENDENT-RETAINED-LITERAL-ANCHOR-REVIEW/1',
        'status':'pass_raw_anchor_encoding_arithmetic_only','findings':[],
        'source_manifest':pin(SRC/'manifest.json'),'anchors':pin(SRC/'anchors.json'),
        'source_pins_verified':{'local':5,'selected_sources':2,'claimed_initial_and_post_source_graph':3},
        'raw_headers_replayed_bytes':608,'section_mapping_and_nonoverlap_replayed':True,
        'literal_count':2,'literals':literal_rows,'raw_candidate_count':1,
        'raw_candidate':{'rva':'0xe7a28f','file_offset':15177359,'raw_hex':raw.hex(),'raw_bytes':7,
            'signed_disp32':15419190,'arithmetic_target_rva':'0x1d2e9cc','encoding_filter':'48or4c 8d; (ModRM&c7)==05',
            'instruction_boundary_verified':False,'xref_verified':False,'function_verified':False,'serialization_verified':False},
        'source_stream_logic':{'window_chunk_bytes':65536,'max_window_bytes':65542,'carry_bytes':6,
            'exact_seven_byte_pattern_boundary_covered':True,'carry_reset_per_section':True,
            'literal_and_candidate_file_offset_dedup':True,'literal_limit':64,'retained_target_candidate_limit':128,
            'all_encoding_shape_seen_set_bounded_by_fixed_section_not128':True,
            'retained7byte_slice_only_no_neighbor_read':True,'success_requires_both_search_complete_and_no_errors':True,
            'memory_guard_applies_to_own_analysis_process':True},
        'recorded_pattern_count_producer_witness':156106,'recorded_scan_chunk_reads':591,
        'in_memory_overlap_reuse_bytes':3504,'recorded_PE_accounting':accounts,
        'recorded_total_PE_file_bytes_read':115376816,
        'excluded_from_section_pattern_scan':{'header_prefix_file_range':[0,1024],
            'trailing_nonsection_file_range':[38452224,GAME_BYTES],'trailing_bytes':10280,
            'uninitialized_virtual_tails_scanned':False,'raw_alignment_padding_in_scope':True},
        'recorded_own_peak_committed_bytes':26128384,'recorded_memory_guard_bytes':805306368,
        'hard_job_object_installed':False,
        'precision_notes':['Before/after fullEXE hashes, fullscan completion/counts and sourcepost equality are pinnedproducer witnesses. This reviewer did not open/stat/hash EXE or reproduce scans.',
            'Retained608B header and selected7B candidate allow independent ownedbyte mapping/filter/rel32 replay; absence/scan-completeness requires producerwitness.',
            'Literal boundary_raw_hex is assigned the constant LITERAL after raw.find exactmatch, not an independent secondfile read; this retained projection does not certify freshdisk content.',
            'Zero instruction decode is not zero code/file reading: executable.text raw scan28724736B was performed by originalproducer and included separately.',
            'MAX_CANDIDATES128 bounds retained targetmatches only; seen contains all156106 complete encoding shapes. Memory is bounded by fixedfile/stream and selfguard, not a128-entry whole-scanner bound.'],
        'limits':['Exact lowerASCII NULtruceNUL within declared nonexecuting rawsections only. Widerencodings/plural/prefix/suffix, headers, overlay and uninitializedvirtual bytes are outside literalsearch.',
            'Candidatefilter only accepts sevenbyte48/4c8d ModRM00/rm101 forms inside executable.text rawsection; otherencodings, indirect/tabled/data/runtime references are not searched.',
            'Second.data literal has zero retained matches in thisfilter only; it must not be described as unreferenced.',
            'Rawcode may be embedded data or interiorinstruction/prefix sequence; no instructionstart, analyzerxref, functionrange or serializer/deserializer business meaning is established.',
            'Before/after hashes on oneopenedfile do not exclude transient mutation between ordered scans or prove an atomic artifactversion.',
            'No actualtypedtruce object/index/expiry/dateunits/removed/peace causalcompletion or nativepermission follows. No arbitrarycallee, gameprocess, Frida or oldtest is invoked.',
            'Auditor reads only fixedproject sources/JSON, parsesAST and replays retained bytes/arithmetic/accounting. No PE/search/decoder/producer/test execution.'],
        'PE_opened_by_reviewer':False,'search_repeated':False,'decoder_executed':False,'tests_run':0,
        'target_process_accesses':0,'Frida_operations':0,'game_native_calls':0,'requests_published':0,
        'native_ready':False,'callable':False,'expiry_verified':False,'peace_completion_verified':False}
    assert not OUT.exists(); OUT.mkdir(parents=True)
    write_new(OUT/'findings.json',report)
    write_new(OUT/'report.md',
        '# R27 字面量候选独立文件复核\n\n'
        '通过5本地/2来源pin、608B原始PEheaders、2个NUL界定truce投影及唯一7B候选的mapping/filter/rel32重放。'
        'e7a28f的4c8d053647eb00按signeddisp32算术指向1d2e9cc。未读取PE或重跑扫描。\n\n'
        '原读取分账115376816B正确；591chunk、3504B内存carry复用，不额外算文件读。'
        '全部扫描及156106编码形状、EXE前后hash仍是固定producer见证。128只限保留目标候选，seen计数并非128上限。\n\n'
        '保留7B候选不证明指令边界/xref/function/serialization；另一21e9cb4字面量未命中当前过滤不等于无引用。'
        'literal扫描仅非执行rawsections，排除headers/10280B trailing非节数据/虚拟零填充，rawpadding仍在范围。'
        '所有nativeReady/expiry/议和完成权限保持false；0进程/Frida/native/测试。\n')
    for path in (SRC/'manifest.json',SRC/'verification.json',Path(__file__).resolve(),OUT/'findings.json',OUT/'report.md'):
        selected[path.relative_to(ROOT).as_posix()] = pin(path)
    write_new(OUT/'manifest.json',{'schema':'EU4-R27-INDEPENDENT-FILE-REVIEW-MANIFEST/1','sealed':True,
        'source_pins':dict(sorted(selected.items())),'PE_reads':0,'new_decode_bytes':0,'native_ready':False})
    print(json.dumps({'status':report['status'],'findings':pin(OUT/'findings.json'),
        'manifest':pin(OUT/'manifest.json'),'local_pins':len(selected),'PE_reads':0,'new_decode_bytes':0}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true')
    check() if parser.parse_args().check else main()
