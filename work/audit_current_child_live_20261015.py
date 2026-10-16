"""Retained child-context sample replay; files/AST only, no imported producer."""
import argparse
import ast
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import struct

ROOT=Path(__file__).resolve().parents[1]
LIVE=ROOT/'work/reports/war-peace-api-20261015-r16-child-current/live-80340-child-current.json'
PRODUCER=ROOT/'work/capture_child_context_current_20261015.py'
HOST=ROOT/'work/candidates/frida-entry-observer-1375-v1'
R15=ROOT/'work/reports/war-peace-api-20261015-r15-child-context/war'
R15REVIEW=ROOT/'work/reports/war-peace-api-20261015-r15-child-context-independent-review/war'
READERREVIEW=ROOT/'work/reports/current-child-reader-review-20261015-r1'
OUT=ROOT/'work/reports/current-child-live-review-20261015-r1'
MIN,MAX=0x10000,0x7fffffff0000


def pin(path):
    count=0;sha=hashlib.sha256()
    with path.open('rb') as stream:
        while raw:=stream.read(65536):count+=len(raw);sha.update(raw)
    return {'bytes':count,'sha256':sha.hexdigest()}


def load(path):
    assert path.stat().st_size<=1024*1024
    def unique(pairs):
        out={}
        for name,value in pairs:
            assert name not in out,'Duplicate JSON key';out[name]=value
        return out
    def no_constant(value):raise ValueError('Nonfinite JSON constant')
    value=json.loads(path.read_bytes().decode('utf-8'),object_pairs_hook=unique,parse_constant=no_constant)
    def bounds(node,depth=0):
        assert depth<=24
        if type(node) is float:assert math.isfinite(node)
        elif type(node) is dict:
            assert len(node)<=1024
            for key,val in node.items():assert type(key) is str;bounds(val,depth+1)
        elif type(node) is list:
            assert len(node)<=2048
            for val in node:bounds(val,depth+1)
        else:assert node is None or type(node) in (bool,int,str)
    bounds(value);return value # General host metadata: finite floats and full64 integer handles are valid.


def write_new(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(value if isinstance(value,str) else json.dumps(value,indent=2)+'\n')


def checked_span(address,size):
    assert type(address) is int and type(size) is int and 0<size<=8
    assert MIN<=address<address+size<=MAX


def pointer(value):
    checked_span(value,8);assert value%8==0


def check():
    data=load(OUT/'manifest.json');assert data['sealed'] is True
    for name,wanted in data['source_pins'].items():assert pin(ROOT/name)==wanted,name
    for name,wanted in data['selected_external_pins'].items():assert pin(Path(name))==wanted,name
    print(json.dumps({'status':'pass','local_pins':len(data['source_pins']),
        'selected_external_pins':len(data['selected_external_pins']),'process_read':False,'producer_executed':False}))


def main():
    assert pin(LIVE)=={'bytes':21006,'sha256':'de14261a17a79cb513c3f4d4224a4caa59c906c9252156a00e8614c1b20df0e7'}
    assert pin(PRODUCER)=={'bytes':7417,'sha256':'5481f4efb2a61198ededbd3247079d17e5f6dca780c65185e0d548da9a04786e'}
    assert pin(HOST/'host-manifest.json')=={'bytes':43987,'sha256':'e7673b0e07c052788d6d2c6378939e176f57e79a45ea09888b957741b7370166'}
    result=load(LIVE);manifest=load(HOST/'host-manifest.json');contract=load(R15/'current-read-contract.json')
    assert manifest['sealed'] is True and len(manifest['source_pins'])==215 and len(manifest['selected_external_pins'])==11
    selected={}
    def add(path,wanted=None):
        actual=pin(path);assert wanted is None or actual==wanted,str(path)
        assert path.resolve().is_relative_to(ROOT.resolve())
        name=path.relative_to(ROOT).as_posix();assert name not in selected or selected[name]==actual
        selected[name]=actual
    for name,wanted in manifest['source_pins'].items():
        assert not Path(name).is_absolute() and '..' not in Path(name).parts
        add(ROOT/name,wanted)
    for name,wanted in manifest['selected_external_pins'].items():assert Path(name).is_absolute() and pin(Path(name))==wanted,name
    assert len(result['source_pins'])==12
    for name,wanted in result['source_pins'].items():add(ROOT/name,wanted)
    for directory in (R15REVIEW,READERREVIEW):
        data=load(directory/'manifest.json');assert data['sealed'] is True
        add(directory/'manifest.json')
    assert pin(READERREVIEW/'independent-source-ready.json')['sha256']=='5e368dc3203b7a979f96643e851581e9fb2fbb72a854b43eedd5fe922157dcaf'
    assert load(READERREVIEW/'independent-source-ready.json')['status']=='source_ready_selected_contract'
    static_review=load(R15REVIEW/'findings.json')
    assert static_review['findings']==[] and static_review['sealed'] is True
    assert static_review['status']=='static_current_read_contract_verified_no_call_or_lease_authority'
    for row in load(R15/'manifest.json')['files']:
        add(ROOT/row['path'],{key:row[key] for key in ('bytes','sha256')})
    assert result['schema']=='EU4-CHILD-CONTEXT-CURRENT-READONLY/1'
    assert result['status']=='sampled_equal' and result['errors']==[]
    assert result['host_manifest_sha256']==pin(HOST/'host-manifest.json')['sha256']
    assert result['identity']['pid']==80340 and type(result['identity']['pid']) is int
    assert result['identity']['creation']=='01dd5c075fcf8c26'
    assert re.fullmatch('[0-9a-f]{32}',result['identity']['session'])
    assert result['identity']['manifest_sha256']=='d4b3069cfac70cf9ff8e1270733ad64592c3d545a6d005fd0ed8b26c6070728a'
    assert result['identity']['dll_sha256']=='6a0683dacc069b743979b7442ad02205f13e8be972ce5c4f26a46fd9b530ed2a'
    assert datetime.fromisoformat(result['captured_utc']).tzinfo is not None
    assert type(result['duration_ms_including_host_checks']) is float and result['duration_ms_including_host_checks']==1766.796
    base=int(result['module_base'],16);pointer(base)
    rows=contract['root_reads']+contract['core_child_reads']+contract['sender_diagnostic_reads']
    assert len(rows)==25 and sum(row['size'] for row in rows)==164
    assert len(result['samples'])==2 and result['samples'][0]==result['samples'][1]
    assert result['selected_two_pass_equal'] is True and result['selected_current_state']=='typed_context_transport_observed'
    replay=[]
    for sample in result['samples']:
        assert sample['status']=='typed_context_transport_observed' and sample['schema']=='EU4-CURRENT-CHILD-CONTEXT-PROJECTION/1'
        assert sample['requested_reads']==len(sample['reads'])==25
        assert sample['requested_bytes']==sample['exact_bytes']==164
        assert sample['limits']=={'reads':25,'bytes':164,'single_read':8}
        values={'module_base':base};decoded_fields={};total=0
        for proof,read in zip(rows,sample['reads']):
            name,receiver,size=proof['name'],proof['receiver'],proof['size']
            assert read['field']==name and read['receiver']==('base' if receiver=='module_base' else receiver)
            address=values[receiver]+int(proof['offset'],16);checked_span(address,size)
            assert read['address']=='0x'+format(address,'016x') and type(read['size']) is int and read['size']==size
            assert re.fullmatch('[0-9a-f]{'+str(size*2)+'}',read['raw_hex'])
            raw=bytes.fromhex(read['raw_hex']);total+=len(raw)
            value=struct.unpack('<i' if name=='command_word_source68' else '<I' if size==4 else '<Q' if size==8 else '<B',raw)[0]
            display='0x'+format(value,'016x') if size==8 else value
            assert type(read['value']) is type(display) and read['value']==display
            decoded_fields[name]=display
            if size==8:pointer(value)
            if proof['expected'].startswith('module_base+0x'):
                expected=int(proof['expected'].split(';')[0].split('+')[1],16)
                assert value==base+expected
            values[name]=value
            if name=='server':assert value==values['current']
            if name=='holder':assert value==values['outer']
            if name=='transport_context_backlink':assert value==values['context']
        assert sample['fields']==decoded_fields and total==164
        for key in ('sender_authorized','native_ready','lifetime_lease','atomic_snapshot',
            'native_entry_authenticated','diagnostics_are_predicate_results','endpoint_code_bytes_verified','owner_reference_or_lock_acquired'):
            assert sample[key] is False,key
        assert sample['native_game_calls']==sample['game_fields_written']==0
        replay.append({'reads':25,'bytes':total,'max_read':8,'receiver_raw_type_checks':True})
    fields=result['samples'][0]['fields']
    assert fields['context']=='0x00000197af9f9f00' and fields['transport']=='0x00000197ba3e25b0'
    diag={key:fields[key] for key in ('sender_flag55','sender_flag80d','command_word_source68','command_dword_source8c','dispatch_flag7d4','dispatch_flag841')}
    assert list(diag.values())==[1,1,65098,1,0,0]
    assert result['selected_rpm_budget']=={'calls':50,'bytes':328,'largest':8}
    pre=result['precheck'];assert pre==result['postcheck']
    assert pre['process_identity_checked'] is True and pre['module_set_equal'] is True
    assert pre['rpm_budget']=={'calls':46,'bytes':300,'largest':32}
    assert int(pre['outer'],16)==int(fields['outer'],16)
    assert int(pre['roots']['server'],16)==int(fields['server'],16) and int(pre['roots']['game'],16)==int(fields['game'],16)
    assert pre['roots']['manual_pause']==1 and pre['roots']['date']==56461512
    assert pre['roots']['capacity']==pre['roots']['count']==1380
    assert int(pre['prefix_address'],16)==base+0x10a6ec0
    assert pre['prefix32_hex']=='4c89442418555357488d6c24b04881ec50010000488b159d8f2901488bf9440f'
    assert [struct.unpack('<Q',bytes.fromhex(raw))[0] for raw in pre['outer_vtable_hex']]==[base+0x1c48bf8,base+0x1c48c80]
    assert struct.unpack('<Q',bytes.fromhex(pre['children_hex'][0]))[0]==int(fields['server'],16)
    assert pre['children_hex'][1:]==['00','0000000000000000','0000000000000000','00']
    for key in ('Frida_called','atomic_snapshot','automatic_retry','historical_Q_or_heap_used',
        'lifetime_lease','native_callback_observed','native_entry_authenticated','native_ready',
        'new_API_effect_tested','sender_authorized','sentinel_header_lease'):
        assert result[key] is False,key
    assert result['pure_RPM'] is True
    for key in ('game_fields_written','hooks_installed','native_game_calls','reloads','requests_published','saves'):
        assert type(result[key]) is int and result[key]==0,key
    # Read/parse producer text, never import/execute. Success assignment must
    # be a sibling after the with; a failed __exit__ cannot reach it.
    source=PRODUCER.read_text(encoding='utf-8');tree=ast.parse(source)
    main_node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
    outer=next(n for n in main_node.body if isinstance(n,ast.Try) and any(isinstance(s,ast.With) for s in n.body))
    assert isinstance(outer.body[0],ast.With) and isinstance(outer.body[1],ast.If)
    assert "if not result['errors']:\n            result['status'] = 'sampled_equal'" in source
    assert len(outer.handlers)==1 and isinstance(outer.handlers[0].type,ast.Name) and outer.handlers[0].type.id=='Exception'
    selected_try=next(n for n in ast.walk(outer.body[0]) if isinstance(n,ast.Try) and any(isinstance(s,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='first' for t in s.targets) for s in n.body))
    first_index=next(i for i,n in enumerate(selected_try.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='first' for t in n.targets))
    second_index=next(i for i,n in enumerate(selected_try.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='second' for t in n.targets))
    assert first_index<second_index and any(isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name) and n.value.func.id=='require' for n in selected_try.body[first_index+1:second_index])
    assert selected_try.finalbody and selected_try.handlers[0].type.id=='Exception'
    assert "First selected projection unknown; stop without retry" in source
    assert "result['postcheck'] == result['precheck'] and cap.held.modules() == cap.modules" in source
    assert "observer.pins() == cap.initial_pins and host.verify_manifest() == frozen" in source
    assert "sources() == initial_sources" in source
    assert not any(isinstance(n,(ast.For,ast.While)) for n in ast.walk(selected_try))
    attrs={n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)}
    assert not attrs.intersection({'attach','spawn','inject','instrument_with_frida','WriteProcessMemory','CreateRemoteThread','SuspendThread','SetThreadContext'})
    report={'schema':'EU4-CURRENT-CHILD-INDEPENDENT-LIVE-FILE-AUDIT/1','status':'pass_selected_retained_current_chain','findings':[],
        'capture':pin(LIVE),'producer':pin(PRODUCER),'verified_host_local_pins':215,'verified_selected_external_pins':11,
        'verified_current_capture_source_pins':12,'static_and_reader_ready_receipts_pinned':True,
        'pid':80340,'creation':'01dd5c075fcf8c26','two_pass_equal':True,'selected_raw_replay':replay,
        'selected_total_reads':50,'selected_raw_bytes':328,'context':fields['context'],'transport':fields['transport'],
        'typed_chain_and_backlink':True,'four_endpoint_slots_match':True,'diagnostics':diag,
        'diagnostics_are_health_or_sender_permission':False,'host_pre_post_projection_equal':True,
        'host_each_pre_post_counter':pre['rpm_budget'],'host_each_retained_raw_bytes':74,
        'duration_ms_including_host_checks':result['duration_ms_including_host_checks'],
        'producer_flow':{'first_unknown_stops_second_pass':True,'no_selected_retry':True,
            'selected_finally_performs_postchecks':True,'outer_Exception_keeps_unknown':True,
            'success_after_normal_with_exit':True,'RuntimeCapture_enter_failure_and_exit_cleanup_per_pinned_source':True,
            'producer_executed_by_auditor':False},
        'limits':[
            'Files and producer AST/text only. No process/Frida/REA/test/producer execution or historicalQ/heap dereference.',
            'All50 selected records/328B replay from retained raw with fresh receiver chains. Equal ordered passes do not exclude intervening release, ABA or mutation.',
            'Host pre/post counters are46reads300B each; only74B raw(prefix32/header16/children26) each are retained. Identity, full modules, PE header, complete root reads and normal handle closure remain pinned-producer witnesses, not complete raw replay.',
            'RuntimeCapture setup also reads loaded-image identity outside the selected50 and host92 reported read counts; this audit does not claim exhaustive process-read accounting.',
            'Current215/11 selected source files match frozenhost pins. External11 is not the completeREA/npm graph. Historical before/after source/identity checks follow the sealedproducer protocol.',
            'General finite-float/full64 integer metadata parsing is intentional. Evidence safeinteger restrictions do not apply to this Python-owned hostjournal.',
            'The four slots establish current endpoint pointer values only. No endpoint codebyte verification, call, command predicate, TLS, objectownership/reference/lock, sender permission or gameplay effect is observed.',
            'This is current externalRPM state, separate from the earlier natural onEnter capture. Its map/server values do not inherit historical RCX/R8/Q/thread authority.',
            'Flags55/80d are both1 and raw signed68 is65098. They are diagnostics, not health failures, native gates or evidence of an executed command. Sentinelheader was not read.'
        ],
        'pure_RPM':True,'temporary_code_hook':False,'native_game_calls':0,'game_fields_written':0,
        'requests_published':0,'saves':0,'reloads':0,'new_API_effects':0,'native_ready':False,
        'native_entry_authenticated':False,'sender_authorized':False,'lifetime_lease':False,
        'sentinel_header_lease':False,'atomic_snapshot':False,'process_read_by_auditor':False,'tests_reexecuted':False}
    assert not OUT.exists();OUT.mkdir(parents=True)
    write_new(OUT/'independent-file-audit.json',report)
    write_new(OUT/'independent-file-audit.md',
        '# 当前 C/T 实采独立文件审计\n\n通过。保留的双遍 50 条 / 328B 全部按 fresh receiver、地址、原始 bytes、类型与解码值重放；'
        'C/T 选定类型、T+70→C 和四个 endpoint 槽匹配。当前值 55=1、80d=1、68(signed32)=65098、8c=1、7d4=0、841=0，仅作诊断。\n\n'
        '215 个宿主本地 pin、11 个所选外部 pin 及 12 个本次源 pin 核对通过。源码路径在 first unknown 时停止第二遍，finally 做后核验，with 正常退出后才提交成功。'
        'host 前后投影相同，端到端计时 1766.796ms。\n\n'
        '宿主身份/完整模块与 PE 检查未留全部 raw，仍是固定 producer 见证；不证明对象寿命、原子性、sender 权限或效果。未重采、未执行 producer 或测试，未访问进程。所有 authority 保持 false。\n')
    for p in (LIVE,PRODUCER,Path(__file__).resolve(),OUT/'independent-file-audit.json',OUT/'independent-file-audit.md'):
        add(p)
    write_new(OUT/'manifest.json',{'schema':'EU4-CURRENT-CHILD-INDEPENDENT-LIVE-AUDIT-MANIFEST/1','sealed':True,
        'source_pins':dict(sorted(selected.items())),'selected_external_pins':manifest['selected_external_pins']})
    print(json.dumps({'status':report['status'],'report':pin(OUT/'independent-file-audit.json'),
        'manifest':pin(OUT/'manifest.json'),'local_pins':len(selected),'selected_external_pins':11}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    check() if args.check else main()
