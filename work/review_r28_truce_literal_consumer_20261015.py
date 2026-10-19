"""R28 independent retained-source/raw review: no PE open, decoder or tests."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT/'work/reports/war-peace-api-20261015-r28-truce-literal-consumer/war'
OUT = ROOT/'work/reports/war-peace-api-20261015-r28-independent-review/war'
GAME_SHA = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
GAME_BYTES = 38462504


def pin(path):
    assert path.resolve().is_relative_to(ROOT.resolve()) and path.stat().st_size <= 1024*1024
    raw = path.read_bytes()
    return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def load(path):
    assert path.stat().st_size <= 1024*1024
    def unique(pairs):
        value = {}
        for k,v in pairs:
            assert k not in value; value[k] = v
        return value
    return json.loads(path.read_bytes().decode('utf-8'),object_pairs_hook=unique)


def write_new(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(value if isinstance(value,str) else json.dumps(value,indent=2)+'\n')


def edge_target(row):
    raw = bytes.fromhex(row['bytes']); at = int(row['rva'],16)
    if raw[0] in (0xe8,0xe9):
        assert len(raw) == 5
        return at+5+struct.unpack('<i',raw[1:])[0]
    if raw[0] == 0x0f:
        assert len(raw) == 6 and 0x80 <= raw[1] <= 0x8f
        return at+6+struct.unpack('<i',raw[2:])[0]
    assert len(raw) == 2 and (0x70 <= raw[0] <= 0x7f or raw[0] == 0xeb)
    return at+2+struct.unpack('<b',raw[1:])[0]


def check():
    m = load(OUT/'manifest.json'); assert m['sealed'] is True
    for name,wanted in m['source_pins'].items(): assert pin(ROOT/name) == wanted,name
    print(json.dumps({'status':'pass','local_pins':len(m['source_pins']),'PE_reads':0,
        'decoder_runs':0,'producer_runs':0,'tests_run':0,'target_process_accesses':0}))


def main():
    assert pin(SRC/'manifest.json') == {'bytes':1963,'sha256':'d0e6cd0e2753dcd83c022f342f315136d19ee0c764f42e817f69282b6e0983db'}
    assert pin(SRC/'contract.json') == {'bytes':8727,'sha256':'e2e9d5c415b30a4e55ba66a405146007fc11b13f4b4894462d03b263944f4870'}
    assert pin(SRC/'selected-decode.json') == {'bytes':46367,'sha256':'72827666dd55ddf333948a40e05bf02ac451e7d9cd11ad32a5d3a6f60633e14a'}
    m = load(SRC/'manifest.json'); assert m['sealed'] is True and m['native_ready'] is False
    selected = dict(m['sources'])
    selected.update({(SRC/name).relative_to(ROOT).as_posix():wanted for name,wanted in m['files'].items()})
    assert len(m['files']) == 6 and len(m['sources']) == 4
    for name,wanted in selected.items(): assert pin(ROOT/name) == wanted,name
    meta = load(SRC/'metadata.json'); d = load(SRC/'selected-decode.json'); c = load(SRC/'contract.json')
    receipt = load(SRC/'verification.json')
    assert receipt['manifest'] == pin(SRC/'manifest.json') and receipt['PE_reads'] == receipt['Capstone_runs'] == 0
    assert meta['game_sha256'] == d['game_sha256'] == c['game_sha256'] == GAME_SHA
    assert meta['source_pins'] == d['source_pins'] and len(d['source_pins']) == 5
    for name,wanted in d['source_pins'].items(): assert selected[name] == wanted
    assert meta['source_guard_post_equal'] is d['source_guard_post_equal'] is True
    assert d['metadata_pin'] == pin(SRC/'metadata.json')
    anchors = load(ROOT/meta['mapping_source'])
    optional = bytes.fromhex(anchors['PE_header_reads'][2]['raw_hex'])
    prva,pbytes = struct.unpack_from('<II',optional,136)
    assert (prva,pbytes) == (0x2465000,958968)
    assert meta['exception_directory'] == {'rva':'0x2465000','bytes':958968,'record_count':79914}
    def offset(rva,size):
        matches = [section['raw_file_offset']+rva-int(section['rva'],16) for section in anchors['sections']
                   if int(section['rva'],16) <= rva and rva+size <= int(section['rva'],16)+section['raw_size']]
        assert len(matches) == 1
        return matches[0]
    def pdata(row):
        value = bytes.fromhex(row['raw_hex']); assert len(value) == 12
        begin,end,unwind = struct.unpack('<III',value)
        assert row['rva'] == hex(prva+row['index']*12) and row['file_offset'] == offset(prva+row['index']*12,12)
        assert [row['begin_rva'],row['end_exclusive'],row['unwind_rva']] == [hex(begin),hex(end),hex(unwind)]
        return begin,end,unwind
    assert len(meta['binary_search']) == 16 and len(meta['pdata_requests']) == 19
    assert meta['pdata_record_requests'] == 19 and meta['pdata_unique_records'] == 17
    assert len(d['pdata_verification_requests']) == 3 and d['total_pdata_requests'] == 22
    requests = meta['pdata_requests']+d['pdata_verification_requests']
    assert len(requests) == 22 and len({row['index'] for row in requests}) == 17
    for row in requests: pdata(row)
    lo,hi = 0,79914
    for row in meta['binary_search']:
        mid = (lo+hi)//2; assert row['index'] == mid
        if int(row['begin_rva'],16) <= 0xe7a28f: lo = mid+1
        else: hi = mid
    assert lo == hi == 29235
    assert meta['selected']['index'] == lo-1 == 29234
    assert meta['previous']['index'] == lo-2 == 29233 and meta['next']['index'] == lo == 29235
    assert pdata(meta['selected']) == (0xe79ec0,0xe7a986,0x1ed2380)
    assert int(meta['previous']['end_exclusive'],16) <= 0xe79ec0 < 0xe7a986 <= int(meta['next']['begin_rva'],16)
    for row,key in zip(d['pdata_verification_requests'],('selected','previous','next')):
        assert row['reason'] == 'verify_'+key
        assert {k:v for k,v in row.items() if k != 'reason'} == meta[key]
    assert [row['reason'] for row in meta['pdata_requests']] == ['binary_search']*16+['selected','previous','next']
    assert [{k:v for k,v in row.items() if k != 'reason'} for row in meta['pdata_requests'][:16]] == meta['binary_search']
    assert [ {k:v for k,v in row.items() if k != 'reason'} for row in meta['pdata_requests'][16:]] == [meta['selected'],meta['previous'],meta['next']]
    for record,read in zip(meta['pdata_requests'],meta['sparse_reads']):
        assert read == {'kind':'pdata_record','rva':record['rva'],'file_offset':record['file_offset'],'bytes':12}
    assert len(meta['sparse_reads']) == 19 and len(d['sparse_reads']) == 4
    for record,read in zip(d['pdata_verification_requests'],d['sparse_reads'][:3]):
        assert read == {'kind':'pdata_record','rva':record['rva'],'file_offset':record['file_offset'],'bytes':12}
    assert d['sparse_reads'][-1] == {'kind':'one_new_code_window','rva':'0xe79ec0','file_offset':15176384,'bytes':1071}
    for phase in (meta,d):
        assert [a['phase'] for a in phase['full_PE_authentication_reads']] == ['before','after']
        for auth in phase['full_PE_authentication_reads']:
            assert auth['bytes_read'] == GAME_BYTES and auth['file_range'] == [0,GAME_BYTES] and auth['sha256'] == GAME_SHA
    assert meta['new_code_bytes_read'] == meta['new_decoded_bytes'] == 0
    assert meta['planned_window'] == d['window'] == ['0xe79ec0','0xe7a2ef']
    assert 0xe7a2ef == 0xe7a28f+96 and meta['planned_code_bytes'] == d['new_code_bytes_read'] == 1071
    assert meta['new_decode_permitted'] is True and meta['scope_limit_bytes'] == 4096
    assert d['file_offset'] == offset(0xe79ec0,1071) == 15176384
    raw = bytes.fromhex(d['raw_hex']); assert len(raw) == 1071
    assert hashlib.sha256(raw).hexdigest() == d['raw_sha256'] == '7b2ad83b45a24a598afaad32c88e397143c687ebd04c0b4e3a0a928e03ef4507'
    cursor = 0xe79ec0; joined = bytearray()
    rows = {int(row['rva'],16):row for row in d['instructions']}
    assert len(rows) == len(d['instructions']) == 260
    for row in d['instructions']:
        assert int(row['rva'],16) == cursor
        value = bytes.fromhex(row['bytes']); joined.extend(value); cursor += len(value)
    assert cursor == 0xe7a2ed and len(joined) == d['new_decoded_bytes'] == 1069
    assert bytes(joined) == raw[:1069] and raw[1069:].hex() == d['undecoded_tail_hex'] == '488d'
    assert d['ret_sites'] == [] and not any(row['mnemonic'] == 'ret' for row in rows.values())
    assert d['complete_pdata_extent_in_window'] is False
    candidate = anchors['raw_candidates'][0]
    assert rows[0xe7a28f] == d['candidate_instruction']
    assert rows[0xe7a28f]['bytes'] == candidate['raw_hex'] == '4c8d053647eb00'
    assert rows[0xe7a28f]['mnemonic'] == 'lea' and rows[0xe7a28f]['operands'] == 'r8, [rip + 0xeb4736]'
    assert 0xe7a28f+7+struct.unpack('<i',bytes.fromhex(candidate['raw_hex'])[3:])[0] == 0x1d2e9cc
    assert d['candidate_reached_on_continuous_decode'] is True and d['linear_decode_is_not_dynamic_reachability'] is True
    assert c['candidate']['instruction_boundary_verified'] is True and c['candidate']['actual_runtime_reachability_proved'] is False
    assert c['candidate']['literal_bytes_hex'] == next(row['literal_bytes_with_terminator_hex'] for row in anchors['literals'] if row['literal_rva'] == '0x1d2e9cc') == '747275636500'
    assert len(d['edges']) == 51
    for edge in d['edges']:
        row = rows[int(edge['site'],16)]; target = edge_target(row)
        assert row['mnemonic'] == edge['kind'] and row['operands'] == edge['target'] == hex(target)
        assert edge['inside_window'] == (0xe79ec0 <= target < 0xe7a2ef) and edge['followed'] is False
    calls = [edge for edge in d['edges'] if edge['kind'] == 'call']
    external = [edge for edge in d['edges'] if edge['kind'] != 'call' and not edge['inside_window']]
    assert calls == c['unfollowed_calls'] and len(calls) == 13
    assert len({edge['target'] for edge in calls}) == 7 and c['unfollowed_unique_callees'] == sorted({edge['target'] for edge in calls},key=lambda v:int(v,16))
    assert external == c['external_branches'] and len(external) == 13
    unresolved = [edge for edge in d['edges'] if edge['kind'] != 'call' and edge['inside_window'] and int(edge['target'],16) not in rows]
    assert len(unresolved) == 1 and unresolved[0]['site'] == '0xe7a2dd' and unresolved[0]['target'] == '0xe7a2ed'
    loop_bytes = {0xe7a281:'488d55b8',0xe7a285:'4883fe10',0xe7a289:'480f43d3',0xe7a28d:'33c9',
        0xe7a2a0:'0fb6040a',0xe7a2a4:'48ffc1',0xe7a2a7:'413a4408ff',0xe7a2ac:'750e',
        0xe7a2ae:'4883f906',0xe7a2b2:'75ec',0xe7a2b4:'8d5103',0xe7a2b7:'e95d020000'}
    for rva,value in loop_bytes.items(): assert rows[rva]['bytes'] == value
    assert edge_target(rows[0xe7a2ac]) == 0xe7a2bc and edge_target(rows[0xe7a2b2]) == 0xe7a2a0
    assert edge_target(rows[0xe7a2b7]) == 0xe7a519 and 0xe7a519 not in rows
    assert not any(row['mnemonic'] == 'call' for at,row in rows.items() if 0xe7a281 <= at < 0xe7a2bc)
    equal_loop = [{'input_index':i,'literal_byte':value,'RCX_after_INC':i+1,
                   'continue_equal_loop':i+1 != 6} for i,value in enumerate(b'truce\0')]
    assert equal_loop[-1]['literal_byte'] == 0 and equal_loop[-1]['RCX_after_INC']+3 == 9
    for at,value in {0xe7a270:'e8cb2fbe00',0xe7a275:'85c0',0xe7a277:'7508',0xe7a279:'8d5008',0xe7a27c:'e998020000'}.items():
        assert rows[at]['bytes'] == value
    assert edge_target(rows[0xe7a277]) == 0xe7a281 and edge_target(rows[0xe7a27c]) == 0xe7a519
    for at,value in {0xe79ee4:'4c8be1',0xe79ee7:'33db',0xe79eec:'8819',0xe79eee:'4c8d7908',
        0xe79ef2:'49891f',0xe79ef5:'49895f10',0xe79ef9:'49c747180f000000',0xe79f01:'41881f',
        0xe7a060:'41c6042401',0xe79fff:'488b05725e4c01',0xe7a006:'488bb8001e0000'}.items():
        assert rows[at]['bytes'] == value
    assert 0xe79fff+7+struct.unpack('<i',bytes.fromhex(rows[0xe79fff]['bytes'])[3:])[0] == 0x233fe78
    assert c['function']['pdata_extent'] == ['0xe79ec0','0xe7a986'] and c['function']['whole_function_closed'] is False
    assert all(value is False for value in c['authority'].values())
    source = (SRC/'produce.py').read_text(encoding='utf-8'); tree = ast.parse(source)
    funcs = {node.name:node for node in tree.body if isinstance(node,ast.FunctionDef)}
    metadata_src,decode_src = [ast.get_source_segment(source,funcs[name]) for name in ('metadata','decode')]
    assert "end = min(int(selected['end_exclusive'],16),SITE+96)" in metadata_src
    assert "for key in ('selected','previous','next')" in decode_src
    assert "raw=pe.at(begin,end-begin,'one_new_code_window')" in decode_src
    assert "for insn in engine.disasm(raw,begin)" in decode_src and "cursor+=insn.size;guard()" in decode_src
    assert 'finally:pe.close()' in metadata_src and 'finally:pe.close()' in decode_src
    assert "pe.authenticate('before')" in metadata_src and "pe.authenticate('after')" in metadata_src
    assert "pe.authenticate('before')" in decode_src and "pe.authenticate('after')" in decode_src
    assert 'sources()==initial' in metadata_src and 'sources()==initial' in decode_src
    assert 'external_data_or_unwind_reads=0' in decode_src
    for data in (meta,d):
        assert data['memory_guard_bytes'] == 805306368 and data['hard_job_object_installed'] is False
        for key in ('process_accesses','Frida_operations','native_game_calls','tests_run'): assert data[key] == 0
        assert data['native_ready'] is False
    assert (meta['peak_committed_bytes'],d['peak_committed_bytes']) == (20975616,30203904)
    assert c['resources']['full_PE_SHA_bytes'] == 4*GAME_BYTES == 153850016
    assert c['resources']['pdata_total_bytes'] == 22*12 == 264
    assert c['resources']['total_PE_file_bytes_read'] == 153850016+264+1071 == 153851351
    report = {'schema':'EU4-R28-INDEPENDENT-TRUCE-LEXICAL-CONSUMER-REVIEW/1',
        'status':'pass_retained_entry_continuity_and_six_byte_lexical_branch','findings':[],
        'source_manifest':pin(SRC/'manifest.json'),'source_contract':pin(SRC/'contract.json'),
        'source_pins_verified':{'local':6,'selected_sources':4,'metadata_and_decode_source_graph':5},
        'pdata':{'exception_directory_rva':'0x2465000','record_count':79914,'selected_index':29234,
            'selected_record_raw':'c09ee70086a9e7008023ed01','extent':['0xe79ec0','0xe7a986'],
            'binary_steps':16,'selected_and_neighbor_rereads':3,'metadata_requests':19,
            'decode_rereads':3,'total_requests':22,'unique_records':17,'raw_retained_bytes':264,
            'unwind_rva_metadata_only':'0x1ed2380','unwind_read':False},
        'selected_raw':{'window':['0xe79ec0','0xe7a2ef'],'file_offset':15176384,'read_bytes':1071,
            'continuous_decoded_bytes':1069,'instruction_rows':260,'raw_SHA256':d['raw_sha256'],
            'partial_tail_rva':'0xe7a2ed','partial_raw':'488d','normal_RET_sites':[],
            'unread_extent_tail_bytes':0xe7a986-0xe7a2ef},
        'candidate':{'rva':'0xe7a28f','raw':'4c8d053647eb00','target':'0x1d2e9cc',
            'boundary_grade':'continuous ordinaryCapstone instruction table from retained pdata begin',
            'old_R27_artifacts_unchanged':True,'actual_dynamic_reachability_verified':False},
        'lexical_branch':{'selection':'RDX=RBP-48; unsignedRSI>=16 selects currentRBX; ECX=0',
            'literal_hex':'747275636500','literal_length_with_NUL':6,'equal_iterations':equal_loop,
            'on_mismatch':'JNEe7a2bc','on_all_six_equal':'RCX6; LEA EDX,[RCX+3] gives9; JMPe7a519',
            'visible_predecessor':'1a5d240 callreturnEAXnonzero enters truceblock; zero selectsEDX8/shared externaljump',
            'local_loop_calls':0,'local_loop_explicit_character_buffer_writes':0,
            'EDX9_business_meaning_verified':False,'e7a519_consumer_read_or_followed':False},
        'selected_control_flow':{'edges':51,'unfollowed_CALL_sites':13,'unfollowed_unique_callees':7,
            'unfollowed_external_branch_sites':13,'one_inside_read_window_partial_target':'e7a2dd ->e7a2ed',
            'complete_function_or_normal_returns_closed':False},
        'prefix_has_explicit_writes':True,'whole_function_pure_readonly_proven':False,
        'source_visible_write_anchors':['e79eec [RCX]byte0','e79ef2 [R15]qword0',
            'e79ef5 [R15+10]qword0','e79ef9 [R15+18]qword15','e79f01 [R15]byte0','e7a060 [R12]byte1'],
        'static_module_root_expression':'e79fff RIP->233fe78 thene7a006 RDI=[RAX+1e00]; no runtime read/type proof',
        'recorded_PE_accounting':{'full_sha_four_passes':153850016,'pdata22records':264,
            'new_code_window':1071,'headers_newly_read':0,'total':153851351},
        'recorded_own_peak_committed_bytes':{'metadata':20975616,'decode':30203904},
        'limits':['This reviewer did not open/stat/hash PE, runCapstone/producer/verifier/tests, or access game/Frida/native. All reconstruction uses pinnedproject files and ownedraw.',
            'Selected code/pdata raw and rel32/RIP arithmetic replay independently; original disk reads, four fullSHA results, sourcepost checks and memory peak remain pinnedproducer witnesses.',
            'Pdata binarytrace and neighbors are checked, not the entire directory/global ordering or unwind contents. Function metadata does not prove exception/whole-CFG coverage.',
            'Continuous entry decode supplies new ordinary static instruction boundary evidence beyond R27rawcandidate, not dynamic reachability or callableprovenance. OldR27 sealedclaims remain historical.',
            'Sixbyte comparison includes finalNUL. It is a lexical branch selectingEDX9; caller inputnormalization, field/enum meaning and shared tailconsumer are unknown.',
            'Only local comparison loop is free of explicitCALL/bufferwrites. Prefix writes and13unfollowedCALLs preclude promoting the function to a puregetter.',
            'No branchtargetdata/literal beyondR27truce, callee, externaljump or partialtail is newly read. Insidereadwindow does not mean decodedbranchclosed.',
            'Serialization/console/business identity, typedtruce object/index/expiry/dateunits/removed, worldlease and peace request causalcompletion remain unknown.'],
        'authority':c['authority'],'PE_reads':0,'new_decode_bytes':0,'producer_runs':0,'tests_run':0,
        'target_process_accesses':0,'Frida_operations':0,'game_native_calls':0,'requests_published':0}
    assert not OUT.exists(); OUT.mkdir(parents=True)
    write_new(OUT/'findings.json',report)
    write_new(OUT/'report.md',
        '# R28 字符比较 consumer 独立静态复核\n\n'
        '通过6本地/4来源pin、pdata22次/17unique记录与1071B原像重放。260条指令连续1069B从e79ec0抵达e7a28f，'
        'LEA7B与R27一致；尾部488d两字节未解码、窗口无RET。\n\n'
        '局部循环逐字节比较truce末NUL在内的六字节，相等令RCX6→EDX9并跳未读e7a519。'
        '这只闭lexical分支，不识别序列化/停战枚举/期限。前缀明确写入口对象，13CALL/7target未跟，不能称只读查询器。\n\n'
        '原读取分账153851351B相符；原PE/SHA/scan/资源是固定producer见证。本审计0PE读取/解码/producer/测试/游戏/Frida/native。'
        '连续静态边界不证明动态可达，R27旧封存不改；全部nativeReady/业务权限仍false。\n')
    for path in (SRC/'manifest.json',SRC/'verification.json',Path(__file__).resolve(),OUT/'findings.json',OUT/'report.md'):
        selected[path.relative_to(ROOT).as_posix()] = pin(path)
    write_new(OUT/'manifest.json',{'schema':'EU4-R28-INDEPENDENT-RETAINED-REVIEW-MANIFEST/1','sealed':True,
        'source_pins':dict(sorted(selected.items())),'PE_reads':0,'new_decode_bytes':0,'native_ready':False})
    print(json.dumps({'status':report['status'],'findings':pin(OUT/'findings.json'),
        'manifest':pin(OUT/'manifest.json'),'local_pins':len(selected),'PE_reads':0,'new_decode_bytes':0}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true')
    check() if parser.parse_args().check else main()
