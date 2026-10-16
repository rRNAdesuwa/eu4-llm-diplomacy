"""R30 retained-file audit only: no PE, Capstone, author producer or tests."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT/'work/reports/war-peace-api-20261015-r30-truce-call-target/war'
OUT = ROOT/'work/reports/war-peace-api-20261015-r30-independent-review/war'
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


def relative_target(row):
    b = bytes.fromhex(row['bytes']); rva = int(row['rva'],16)
    if b[0] in (0xe8,0xe9):
        assert len(b) == 5
        return rva+5+struct.unpack('<i',b[1:])[0]
    if b[0] == 0x0f:
        assert len(b) == 6 and 0x80 <= b[1] <= 0x8f
        return rva+6+struct.unpack('<i',b[2:])[0]
    assert len(b) == 2 and (0x70 <= b[0] <= 0x7f or b[0] == 0xeb)
    return rva+2+struct.unpack('<b',b[1:])[0]


def check():
    m = load(OUT/'manifest.json'); assert m['sealed'] is True
    for name,wanted in m['source_pins'].items(): assert pin(ROOT/name) == wanted,name
    print(json.dumps({'status':'pass','local_pins':len(m['source_pins']),'PE_reads':0,
        'decoder_runs':0,'producer_runs':0,'tests_run':0,'game_process_accesses':0}))


def main():
    assert pin(SRC/'manifest.json') == {'bytes':3136,'sha256':'4ce3a676d3e355ba57ef695a87c22e43a3334c2c80dcda7b2a6a3f06c7966aa8'}
    assert pin(SRC/'contract.json') == {'bytes':8624,'sha256':'4d0a4e8224c95efd8ad5ffd1cb28ae5469da00e5865590f51fe3f49eaf3223b0'}
    assert pin(SRC/'selected-decode.json') == {'bytes':21301,'sha256':'3258fd106cd61960272b7d2f0e13f16da9b048a37e6c675986996f3cbf89f847'}
    m = load(SRC/'manifest.json'); assert m['native_ready'] is False
    assert len(m['files']) == 9 and len(m['source_pins']) == 8
    selected = dict(m['source_pins'])
    selected.update({(SRC/name).relative_to(ROOT).as_posix():wanted for name,wanted in m['files'].items()})
    for name,wanted in selected.items(): assert pin(ROOT/name) == wanted,name
    meta = load(SRC/'metadata.json'); d = load(SRC/'selected-decode.json'); c = load(SRC/'contract.json')
    claim = load(SRC/'claim.json'); decode_claim = load(SRC/'decode-claim.json'); receipt = load(SRC/'verification.json')
    assert meta['game_sha256'] == d['game_sha256'] == c['game_sha256'] == GAME_SHA
    assert meta['source_pins'] == d['source_pins'] == claim['source_pins'] == decode_claim['source_pins']
    assert len(d['source_pins']) == 9
    for name,wanted in d['source_pins'].items(): assert selected[name] == wanted
    assert meta['source_guard_post_equal'] is d['source_guard_post_equal'] is True
    assert claim['automatic_retry'] is decode_claim['automatic_retry'] is False
    assert claim['max_new_code_bytes'] == 256 and claim['max_combined_pdata_record_requests'] == 32
    assert claim['decode_requires_exact_pdata_begin'] is True
    assert decode_claim['metadata_pin'] == d['metadata_pin'] == c['metadata_pin'] == pin(SRC/'metadata.json')
    assert c['selected_decode_pin'] == pin(SRC/'selected-decode.json')
    assert c['required_parent_roots'] == {name:value for name,value in m['source_pins'].items() if '/r29-' in name or '-r29-' in name}
    parent_paths = list(c['required_parent_roots']); assert len(parent_paths) == 3
    parent_m = load(ROOT/next(n for n in parent_paths if n.endswith('/manifest.json')))
    parent_d = load(ROOT/next(n for n in parent_paths if n.endswith('/selected-decode.json')))
    for name in ('selected-decode.json','contract.json'):
        path = next(n for n in parent_paths if n.endswith('/'+name))
        assert parent_m['files'][name] == c['required_parent_roots'][path]
    pr = {int(row['rva'],16):row for row in parent_d['instructions']}
    assert pr[0xe7a522]['bytes'] == 'e8c97a9aff' and relative_target(pr[0xe7a522]) == 0x821ff0
    assert [pr[at]['bytes'] for at in (0xe7a519,0xe7a51c,0xe7a51f)] == ['4533c9','4533c0','488bcf']
    assert c['source_call'] == meta['source_call'] == claim['source_call'] == {'site':'0xe7a522','raw_hex':'e8c97a9aff','target':'0x821ff0'}
    anchors = load(ROOT/'work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json')
    optional = bytes.fromhex(anchors['PE_header_reads'][2]['raw_hex'])
    prva,pbytes = struct.unpack_from('<II',optional,136)
    assert (prva,pbytes) == (0x2465000,958968)
    def offset(rva,size):
        found = [row['raw_file_offset']+rva-int(row['rva'],16) for row in anchors['sections']
                 if int(row['rva'],16) <= rva and rva+size <= int(row['rva'],16)+row['raw_size']]
        assert len(found) == 1
        return found[0]
    for record in meta['pdata_requests']+d['pdata_verification_requests']:
        raw = bytes.fromhex(record['raw_hex']); assert len(raw) == 12
        begin,end,unwind = struct.unpack('<III',raw)
        assert [record['begin_rva'],record['end_exclusive'],record['unwind_rva']] == [hex(begin),hex(end),hex(unwind)]
        assert int(record['rva'],16) == prva+12*record['index']
        assert record['file_offset'] == offset(prva+12*record['index'],12)
    assert len(meta['binary_search']) == 17 and len(meta['pdata_requests']) == meta['pdata_record_requests'] == 20
    assert len(d['pdata_verification_requests']) == 3 and d['total_pdata_requests'] == 23
    all_records = meta['pdata_requests']+d['pdata_verification_requests']
    assert len(all_records) == 23 and len({r['index'] for r in all_records}) == meta['pdata_unique_records'] == 17
    lo,hi = 0,pbytes//12
    for record in meta['binary_search']:
        mid = (lo+hi)//2; assert record['index'] == mid
        if int(record['begin_rva'],16) <= 0x821ff0: lo = mid+1
        else: hi = mid
    assert lo == hi == 15948 and meta['selected']['index'] == 15947
    assert (meta['previous']['index'],meta['next']['index']) == (15946,15948)
    assert meta['selected']['raw_hex'] == 'f01f820076258200301fe601'
    assert (int(meta['selected']['begin_rva'],16),int(meta['selected']['end_exclusive'],16)) == (0x821ff0,0x822576)
    assert int(meta['previous']['end_exclusive'],16) <= 0x821ff0 < 0x822576 <= int(meta['next']['begin_rva'],16)
    for record,key in zip(d['pdata_verification_requests'],('selected','previous','next')):
        assert record['reason'] == 'verify_'+key and {k:v for k,v in record.items() if k != 'reason'} == meta[key]
    assert [{k:v for k,v in r.items() if k != 'reason'} for r in meta['pdata_requests'][:17]] == meta['binary_search']
    assert [r['reason'] for r in meta['pdata_requests']] == ['binary_search']*17+['selected','previous','next']
    for phase in (meta,d):
        assert [a['phase'] for a in phase['full_PE_authentication_reads']] == ['before','after']
        for a in phase['full_PE_authentication_reads']:
            assert a == {'phase':a['phase'],'bytes_read':GAME_BYTES,'file_range':[0,GAME_BYTES],'sha256':GAME_SHA}
    assert len(meta['sparse_reads']) == 20 and len(d['sparse_reads']) == 4
    for records,reads in ((meta['pdata_requests'],meta['sparse_reads']),
                          (d['pdata_verification_requests'],d['sparse_reads'][:3])):
        for record,read in zip(records,reads):
            assert read == {'kind':'pdata_record','rva':record['rva'],'file_offset':record['file_offset'],'bytes':12}
    assert d['sparse_reads'][-1] == {'kind':'one_new_target_prefix_window','rva':'0x821ff0','file_offset':8524784,'bytes':256}
    assert meta['exact_target_is_pdata_begin'] is meta['new_decode_permitted'] is True
    assert meta['planned_window'] == d['window'] == decode_claim['window'] == ['0x821ff0','0x8220f0']
    assert meta['planned_code_bytes'] == d['new_code_bytes_read'] == d['decoder_input_bytes'] == 256
    assert d['file_offset'] == offset(0x821ff0,256) == 8524784
    raw = bytes.fromhex(d['raw_hex']); assert len(raw) == 256
    assert hashlib.sha256(raw).hexdigest() == d['raw_sha256'] == 'f22b3e130ebc9a95a3722d101a434064d5531b8b2650ec491477f4127ebaafb1'
    cursor = 0x821ff0; joined = bytearray(); rows = {}
    for row in d['instructions']:
        at = int(row['rva'],16); assert at == cursor and at not in rows
        rows[at] = row; b = bytes.fromhex(row['bytes']); joined.extend(b); cursor += len(b)
    assert len(rows) == 64 and cursor == 0x8220ef and len(joined) == d['new_decoded_bytes'] == 255
    assert raw[:255] == joined and raw[255:].hex() == d['undecoded_tail_hex'] == 'e8'
    assert 0x8220ef not in rows and d['ret_sites'] == [] and not any(row['mnemonic'] == 'ret' for row in rows.values())
    assert d['complete_pdata_extent_in_window'] is d['dynamic_reachability_verified'] is False
    direct_edges = []
    for edge in d['edges']:
        row = rows[int(edge['site'],16)]; assert row['mnemonic'] == edge['kind'] and edge['followed'] is False
        if edge['target'] == 'rcx':
            assert row['bytes'] == 'ffe1' and row['operands'] == 'rcx' and edge['inside_window'] is False
        else:
            target = relative_target(row); assert hex(target) == row['operands'] == edge['target']
            assert edge['inside_window'] == (0x821ff0 <= target < 0x8220f0)
            direct_edges.append(edge)
    assert len(direct_edges) == 18 and len(d['edges']) == 19
    assert [(e['site'],e['target']) for e in direct_edges if e['kind'] == 'call'] == [('0x822043','0x1a334c0'),('0x8220dd','0x10a9be0')]
    assert [(e['site'],e['target']) for e in direct_edges if e['kind'] != 'call' and not e['inside_window']] == [('0x822056','0x8223a4')]
    exact = {0x82200d:'410fb6f9',0x822011:'450fb6f0',0x822015:'8bea',0x822017:'488bf1',
        0x82201a:'803d1bdfb10100',0x822023:'803dacdeb10100',0x82202c:'65488b042558000000',
        0x822035:'488b18',0x822038:'b80c000000',0x82203d:'803c1800',0x822048:'b810000000',
        0x82204d:'803c1800',0x822053:'83fd25',0x82205c:'8b5e2c',0x82205f:'8d45fe',
        0x822062:'83f841',0x822067:'4898',0x822069:'488d1590df7dff',
        0x822070:'0fb6840234258200',0x822078:'8b8c8208258200',0x82207f:'4803ca',0x822082:'ffe1',
        0x8220cc:'488b8630030000',0x8220d3:'488b8860030000',0x8220da:'4533c0',
        0x8220e2:'440fb6cf',0x8220e6:'450fb6c6',0x8220ea:'8bd5',0x8220ec:'488bce'}
    for at,b in exact.items(): assert rows[at]['bytes'] == b
    gate_rvas = [at+7+struct.unpack('<i',bytes.fromhex(rows[at]['bytes'])[2:6])[0] for at in (0x82201a,0x822023)]
    assert gate_rvas == [0x233ff3c,0x233fed6]
    assert relative_target(rows[0x822021]) == 0x82202c and relative_target(rows[0x82202a]) == 0x82205c
    assert relative_target(rows[0x822041]) == 0x822048 and relative_target(rows[0x822051]) == 0x82205c
    assert relative_target(rows[0x822056]) == 0x8223a4 and relative_target(rows[0x822065]) == 0x8220c7
    module_base_rva = 0x822069+7+struct.unpack('<i',bytes.fromhex(rows[0x822069]['bytes'])[3:])[0]
    assert module_base_rva == 0
    first_base = struct.unpack('<i',bytes.fromhex(rows[0x822070]['bytes'])[4:])[0]
    second_base = struct.unpack('<i',bytes.fromhex(rows[0x822078]['bytes'])[3:])[0]
    index = (9-2)&0xffffffff
    assert index == 7 and index <= 0x41 and first_base == 0x822534 and first_base+index == 0x82253b and second_base == 0x822508
    cases = [(0x822084,2),(0x82208b,0),(0x82208f,5),(0x822096,6),(0x82209d,7),
        (0x8220a4,3),(0x8220ab,4),(0x8220b2,8),(0x8220b9,9),(0x8220c0,14),(0x8220c7,1)]
    for at,value in cases:
        b = bytes.fromhex(rows[at]['bytes'])
        assert b == (bytes.fromhex('33d2') if value == 0 else b'\xba'+struct.pack('<I',value))
    findings = {item['id']:item for item in c['findings']}
    projection = findings['receiver_state_and_two_level_dispatch']['input_9_conditional_projection']
    assert projection['index'] == 7 and projection['first_byte_rva'] == '0x82253b'
    assert projection['table_values_read'] is False and projection['selected_target'] == 'unknown'
    assert findings['child_receiver_call_and_argument_reconstruction']['call_registers']['R9'] == 'unknown'
    assert c['scope']['partial_tail_has_decoded_target'] is False
    assert all(value is False for value in c['authority'].values())
    prior = load(ROOT/'work/reports/war-peace-api-20261015-r23-truce-observation-contract/war/selected-decode.json')
    assert d['selected_decoder_dependency_pins'] == prior['selected_dependency_pins'] and len(d['selected_decoder_dependency_pins']) == 38
    assert d['decoder_dependencies_post_equal'] is True and receipt['decoder_runtime_files_rehashed'] is False
    source = (SRC/'produce.py').read_text(encoding='utf-8'); tree = ast.parse(source)
    functions = {node.name:node for node in tree.body if isinstance(node,ast.FunctionDef)}
    metadata_source,decode_source = [ast.get_source_segment(source,functions[name]) for name in ('metadata','decode')]
    assert 'end=min(TARGET+256' in metadata_source and 'int(selected[\'begin_rva\'],16)==TARGET' in metadata_source
    assert '0<end-begin<=256' in decode_source and "for key in ('selected','previous','next')" in decode_source
    assert "raw=pe.at(begin,end-begin,'one_new_target_prefix_window')" in decode_source
    assert 'dependencies()==dep_pins' in decode_source and 'legacy.sources()==prior' in decode_source
    assert 'sources()==initial' in metadata_source and 'legacy.sources()==prior' in metadata_source
    assert 'finally:pe.close()' in metadata_source and 'finally:pe.close()' in decode_source
    for data in (meta,d):
        assert data['memory_guard_bytes'] == 805306368 and data['hard_job_object_installed'] is False
        assert data['game_process_accesses'] == data['Frida_operations'] == data['native_game_calls'] == data['tests_run'] == 0
        assert data['native_ready'] is False
    counts = c['resource_accounting']
    assert counts['full_PE_SHA_read_bytes'] == 4*GAME_BYTES == 153850016
    assert counts['pdata_bytes_read'] == 23*12 == 276 and counts['total_PE_read_bytes'] == 153850016+276+256 == 153850548
    assert counts['metadata_peak_committed_bytes'] == meta['peak_committed_bytes'] == 20672512
    assert counts['decode_peak_committed_bytes'] == d['peak_committed_bytes'] == 28610560
    report = {'schema':'EU4-R30-INDEPENDENT-STATIC-CALL-TARGET-REVIEW/1',
        'status':'pass_conditional_index_arithmetic_with_unresolved_dispatch_tables','findings':[],
        'source_manifest':pin(SRC/'manifest.json'),'source_contract':pin(SRC/'contract.json'),
        'source_pins_verified':{'local_files':9,'external_selected_project_sources':8,'initial_post_source_graph':9},
        'manifest_freeze_grade':'fixed parent-suppliedSHA; originalmanifest has no explicitsealed boolean',
        'R29_three_roots_bound':True,'source_call_rel32':'e7a522 e8c97a9aff ->821ff0',
        'pdata':{'selected_index':15947,'extent':['0x821ff0','0x822576'],'extent_bytes':1414,
            'binary_requests':17,'metadata_requests':20,'decode_rechecks':3,'total_requests':23,
            'unique_records':17,'raw_record_bytes':276,'unwind_rva_metadata_only':'0x1e61f30','unwind_read':False},
        'prefix':{'window':['0x821ff0','0x8220f0'],'read_bytes':256,'complete_decoded_bytes':255,
            'rows':64,'partial_rva':'0x8220ef','partial_raw':'e8','partial_target_known':False,
            'RET_count':0,'whole_function_or_normal_exit_closed':False,'dynamic_reachability_verified':False},
        'argument_copies':{'EDI':'zero_extend8(entryR9B)','R14D':'zero_extend8(entryR8B)',
            'EBP':'entryEDX32','RSI':'entryRCX64','across_callees_condition':'normalWin64 ABI nonvolatile preservation; implementations unreviewed'},
        'gates_and_TLS':{'module_byte_rvas':['0x233ff3c','0x233fed6'],
            'TLS_skip_condition':'firstbyte nonzero ANDsecondbyte zero',
            'TLS_chain':'GS:[58] qword ->[RAX] qword ->byte+0c/+10',
            'call1a334c0_condition':'+0c bytezero','external8223a4_condition':'+10 bytezero ANDEBP==0x25',
            'actual_values_or_business_semantics_verified':False},
        'input9_projection':{'condition':'EntryEDX9 and priorcalls return under normalWin64 ABI preservingEBP',
            'EAX_index_uint32':7,'unsigned_range_limit':65,'first_table_base_rva':'0x822534',
            'selected_first_byte_rva':'0x82253b','second_dword_formula':'B+822508+4*uint8(firstbyte)',
            'jump_formula':'B+zero_extend32(seconddword)','table_values_read':False,'selected_case':'unknown',
            'physical_EDX9_case_chosen_proven':False},
        'visible_cases_only':[{'rva':hex(at),'EDX':value,'selected_for_input9':'unknown'} for at,value in cases],
        'visible_merge_call':{'site':'0x8220dd','target':'0x10a9be0','RCX':'qword[qword[currentRSI+330]+360]',
            'EDX':'case-dependent/unknownforinput9','R8D':0,'R9':'unknown across possible priorcallee',
            'reached_by_input9_proven':False,'receiver_type_or_ownership_proven':False},
        'after_call_reconstruction':'MOVZX R9D,DIL; MOVZX R8D,R14B; EDX=EBP; RCX=RSI; nexte8 is partialonly',
        'control_flow':{'relative_edges':18,'unresolved_indirect_edges':1,'completeCALLs':2,
            'unfollowed_calls':['0x1a334c0','0x10a9be0'],'outside_direct_branch':'0x822056 ->0x8223a4',
            'unresolved_indirect_jump':'0x822082 JMPRCX'},
        'write_scope':'Completeprefix explicitstores onlyprologue stack; PUSH/CALLimplicit stackwrites remain. Callees/restoffunction effectsunknown.',
        'recorded_PE_accounting':{'full_SHA_four_passes':153850016,'pdata':276,'new_prefix':256,'total':153850548,
            'new_header_literal_moduledata_unwind_callee_targeted_reads':0},
        'precision_notes':['822534 is firsttablebase,82253b is its selectedbyte atindex7; neither is a changedtableaddress. Reviewerinitialcommentary compared these distinctroles and is corrected here.',
            'Nojump-table byte/dword values were retained/read. The visiblecase that assignsEDX9 is not evidence of input9 selectingit.',
            'R8/R9 entrycopies keep low8bits only. R9 atchildcall cannot inherit entryzero across an optional unreviewedcall; reconstruction occurs afterward.',
            'Originalmanifest is frozen by suppliedSHA rather than a sealed key; this audit seals a separatemanifest without changingit.'],
        'limits':['Only pinnedproject files/AST/ownedraw arithmetic. Reviewer did not open/stat/hashPE, importCapstone, runproducer/verifier/tests or access process/Frida/native.',
            'Code/pdata/parentrel32/selector arithmetic replay independently. FullSHA before/after, source/dependencypostchecks and peakmemory remain originalproducer witnesses.',
            'Pdata trace/neighbors checked, not globaltableorder/unwind. Continuousdecode is ordinary staticevidence, not dynamic callback/callability or wholefunctionproof.',
            'Selected38 decoderpin metadata matches priorretention; decoderfiles/runtime were not imported or rehashed by this review.',
            'Modulebytes/TLS/receiverstate have no observedvalues or businesslabels. NormalABI preservation is conditional, not a claim thatunreviewedcallee implementations were proven.',
            'Input9 enters an unresolved twoleveldispatch. No visiblecase/default/mergecall is attributed to thatinput until separately authorizedtableevidence exists.',
            'Partiale8 is not a completedCALL or knowncallee. All targeteddata/callee successors and remaining1158B functionextent stay outside.',
            'No mapmode/typedtruce/index/expiry/dateunits/removed/peaceeffect/puregetter/lease/sender authority follows.'],
        'authority':c['authority'],'PE_reads':0,'new_decode_bytes':0,'producer_runs':0,'tests_run':0,
        'game_process_accesses':0,'Frida_operations':0,'native_game_calls':0,'requests_published':0}
    assert not OUT.exists(); OUT.mkdir(parents=True)
    write_new(OUT/'findings.json',report)
    write_new(OUT/'report.md',
        '# R30 入口前缀独立文件复核\n\n'
        '通过9本地/8来源pin、R29三根/rel32、23次pdata/17unique与256B原像/255B连续64rows。末e8无完整CALL目标，窗口无RET。\n\n'
        'EDX9在normalWin64 ABI保留EBP前提下得索引7；第一表base822534，选中字节82253b，第二表822508+4*byte。'
        '表内容未读，具体case未知；物理可见EDX9case及+330→+360调用都不能归因输入9。前者与选中字节地址并非地址变更。\n\n'
        'modulebyte/TLS路径与2个未跟CALL/1外跳/1间接跳保持未知语义。prefix只见显式栈store不证明callee/完整函数纯读取。'
        '原读取分账153850548B相符；hash/sourceguard/peak为producer见证。本审计0PE/解码/producer/test/game/Frida/native，所有权限false。\n')
    for path in (SRC/'manifest.json',Path(__file__).resolve(),OUT/'findings.json',OUT/'report.md'):
        selected[path.relative_to(ROOT).as_posix()] = pin(path)
    write_new(OUT/'manifest.json',{'schema':'EU4-R30-INDEPENDENT-STATIC-REVIEW-MANIFEST/1','sealed':True,
        'source_pins':dict(sorted(selected.items())),'PE_reads':0,'new_decode_bytes':0,'native_ready':False})
    print(json.dumps({'status':report['status'],'findings':pin(OUT/'findings.json'),
        'manifest':pin(OUT/'manifest.json'),'local_pins':len(selected),'PE_reads':0,'new_decode_bytes':0}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true')
    check() if parser.parse_args().check else main()
