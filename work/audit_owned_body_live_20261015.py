"""Retained R19 live body-probe file replay. Never follows any captured address."""
import argparse
import ast
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import struct
import types

ROOT=Path(__file__).resolve().parents[1]
CAND=ROOT/'work/candidates/frida-owned-body-probe-1375-v1'
OLD=ROOT/'work/candidates/frida-entry-observer-1375-v1'
LIVE=ROOT/'work/reports/war-peace-api-20261015-r19-body-live'
OUT=ROOT/'work/reports/frida-owned-body-live-review-20261015-r1'


def pin(path):
    h=hashlib.sha256();size=0
    with path.open('rb') as stream:
        while raw:=stream.read(65536):size+=len(raw);h.update(raw)
    return dict(bytes=size,sha256=h.hexdigest())


def load(path):
    assert path.stat().st_size<=1024*1024
    def unique(rows):
        result={}
        for key,value in rows:
            assert key not in result,'Duplicate JSON key';result[key]=value
        return result
    def reject(value):raise ValueError('Nonfinite JSON value')
    result=json.loads(path.read_bytes().decode('utf-8'),object_pairs_hook=unique,parse_constant=reject)
    def bounded(value,depth=0):
        assert depth<=24
        if type(value) is dict:
            assert len(value)<=2048
            for key,item in value.items():assert type(key) is str;bounded(item,depth+1)
        elif type(value) is list:
            assert len(value)<=2048
            for item in value:bounded(item,depth+1)
        elif type(value) is float:assert math.isfinite(value)
        else:assert value is None or type(value) in (str,int,bool)
    bounded(result);return result # Hostjournal permits full64 handles/finite job timingfloat.


def exact_pure_module(path,sha,name):
    raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==sha
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__);return module


def write_new(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(value if isinstance(value,str) else json.dumps(value,indent=2)+'\n')


def check():
    m=load(OUT/'manifest.json');assert m['sealed'] is True
    for name,wanted in m['source_pins'].items():assert pin(ROOT/name)==wanted,name
    for name,wanted in m['selected_external_pins'].items():assert pin(Path(name))==wanted,name
    print(json.dumps(dict(status='pass',local_pins=len(m['source_pins']),selected_external_pins=len(m['selected_external_pins']),
        process_accessed=False,Frida_called=False,REA_called=False,tests_reexecuted=False)))


def main():
    capture_path=LIVE/'capture.json';manifest_path=CAND/'body-host-manifest.json'
    assert pin(capture_path)==dict(bytes=61600,sha256='61fe1eecb69fedaa392a4d40893163887bb49fd8cad417553387741e17f563e3')
    assert pin(manifest_path)==dict(bytes=6216,sha256='a9af7b19b34d2b0be71bd2881f958100b8ee49e8110182eafb6b3de8484c663d')
    c=load(capture_path);production=load(manifest_path);selected={}
    def add(path,wanted=None):
        actual=pin(path);assert wanted is None or actual==wanted,str(path)
        assert path.resolve().is_relative_to(ROOT.resolve())
        key=path.relative_to(ROOT).as_posix();assert key not in selected or selected[key]==actual
        selected[key]=actual
    assert production['sealed'] is True and production['source_only_draft'] is False
    assert len(production['source_pins'])==29 and c['source_graph']['source_pins']==production['source_pins']
    for name,wanted in production['source_pins'].items():add(ROOT/name,wanted)
    review_path=ROOT/production['independent_review'];add(review_path,production['independent_review_pin'])
    assert production['independent_review_pin']==dict(bytes=5706,sha256='ae68de5afe71970b3b87393d8aa9e8d024dd5721fa283b156473fd6e5d699fa9')
    review=load(review_path);assert review['findings']==[] and review['sealed'] is True
    draft_path=ROOT/review['prepared_draft']['path'];add(draft_path,{key:review['prepared_draft'][key] for key in ('bytes','sha256')})
    draft=load(draft_path);expected=dict(draft)
    expected.update(sealed=True,source_only_draft=False,independent_review_pin=pin(review_path))
    assert production==expected
    frozen=c['source_graph']['frozen_host'];frozen_manifest=load(OLD/'host-manifest.json')
    assert len(frozen['source_pins'])==215 and len(frozen['selected_external_pins'])==11
    assert frozen['source_pins']==frozen_manifest['source_pins'] and frozen['selected_external_pins']==frozen_manifest['selected_external_pins']
    assert frozen['manifest_sha256']==pin(OLD/'host-manifest.json')['sha256']=='e7673b0e07c052788d6d2c6378939e176f57e79a45ea09888b957741b7370166'
    for name,wanted in frozen['source_pins'].items():add(ROOT/name,wanted)
    for name,wanted in frozen['selected_external_pins'].items():assert pin(Path(name))==wanted,name
    assert c['source_graph']['manifest_sha256']==pin(manifest_path)['sha256']
    assert c['source_graph']['independent_review_pin']==pin(review_path)
    assert c['schema']=='EU4-OWNED-BODY-HOST-CAPTURE/1' and c['status']=='raw_abi_postcondition_match' and c['errors']==[]
    assert c['pid']==80340 and c['creation']=='01dd5c075fcf8c26'
    config=c['config'];base=int(config['base'],16)
    assert base==0x7ff7034b0000 and config['pid']==c['pid'] and config['creation']==c['creation']
    assert config['observer_nonce']=='59d7cac4e345765f134c555ae0b09ca9'
    host=exact_pure_module(OLD/'capture_once.py','b39823564ab26a9da7093e1812b2a1fec28a17141e3c4a1024460664b1943b6e','file_only_old_evidence_helpers')
    parser=exact_pure_module(CAND/'body_parser.py','d04bf897fc14053e5678431c2d20785c631102ff749d0107b74df7c5d8f5418a','file_only_body_parser')
    # Only pure extraction/replay helpers are called, never their capture/main.
    claim=host.strict_json((LIVE/'claim.json').read_bytes(),8192)
    assert claim['schema']=='EU4-OWNED-BODY-CLAIM/1' and claim['pid']==c['pid'] and claim['creation']==c['creation']
    assert claim['manifest_sha256']==c['source_graph']['manifest_sha256'] and claim['automatic_retry'] is False
    assert claim['requests_published']==0 and datetime.fromisoformat(claim['claimed_utc'])<=datetime.fromisoformat(c['captured_utc'])
    script_path=LIVE/'rendered-body-probe.js';rendered=script_path.read_bytes()
    prefix=b'const EU4_BODY_PROBE_CONFIG = ';assert rendered.startswith(prefix)
    firstline,body=rendered.split(b';\n',1)
    assert host.strict_json(firstline[len(prefix):],2048)==config and body==(CAND/'body_probe.js').read_bytes()
    keys=('schema','pid','creation','game_sha256','base','expected_prefix_hex','observer_nonce','max_attempts')
    original_order={key:config[key] for key in keys}
    assert rendered==prefix+json.dumps(original_order,separators=(',',':')).encode('ascii')+b';\n'+body
    assert pin(script_path)==c['rendered_script_pin'] and len(rendered)==21292
    assert (LIVE/'rea.stderr.txt').stat().st_size==0
    evidence,payload=host.extract_evidence((LIVE/'rea.stdout.json').read_bytes(),config,str(script_path.resolve()),pin(script_path)['sha256'])
    assert payload==host.strict_json((LIVE/'owned-payload.json').read_bytes(),32768)
    assert evidence['evidence_id']==c['REA_evidence_id']=='ev_c4caa336fe548e29133151dcc5d6489588676a99b300a0ef1658317a349fd4ed'
    projected={key:value for key,value in evidence.items() if key not in ('evidence_id','relationship_coverage')}
    assert 'ev_'+hashlib.sha256(json.dumps(projected,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()==evidence['evidence_id']
    evaluation=parser.evaluate(payload,config)
    assert evaluation==c['payload_evaluation'] and evaluation['status']=='raw_abi_postcondition_match'
    assert 'native_game_calls' not in c and 'native_game_calls' not in payload
    assert c['top_level_native_game_calls_attempted_observed']==c['top_level_native_game_calls_returned_observed']==1
    assert payload['native_game_calls_attempted']==payload['native_game_calls_returned']==1
    probe=payload['probe'];assert probe['spent'] is True and probe['call']['attempted']==probe['call']['returned']==1
    assert probe['call']['entry_rva']=='0x500560' and probe['call']['signature']=='void(pointer)'
    assert probe['call']['options']==dict(abi='win64',scheduling='exclusive',exceptions='propagate',traps='none')
    assert probe['owned_writes']==dict(attempts=4,returned=4,requested_bytes=264,completed_bytes=264)
    a=int(probe['allocations']['A']['address'],16);g=int(probe['allocations']['G']['address'],16)
    assert a==0x198015e4660 and g==0x198015e4910 and a%16==g%16==0 and (a+152<=g or g+96<=a)
    preA=bytes.fromhex(probe['before']['owned']['A_hex']);postA=bytes.fromhex(probe['after']['owned']['A_hex'])
    preG=bytes.fromhex(probe['before']['owned']['G_hex']);postG=bytes.fromhex(probe['after']['owned']['G_hex'])
    expectedA=bytearray(152);expectedA[0x48:0x50]=struct.pack('<Q',g)
    assert preA==expectedA and preG==struct.pack('<Q',base+0x1d207f8)+bytes(88)
    assert postA[:8]==struct.pack('<Q',base+0x1c3e578) and postA[8:]==preA[8:] and postG==preG
    changed=[i for i,(before,after) in enumerate(zip(preA,postA)) if before!=after]
    assert changed==[0,1,2,3,4,5]
    raw_stack_world=0
    for projection in (payload['observation']['first'],payload['observation']['second']):
        raw_stack_world+=sum(len(bytes.fromhex(row['raw8_hex'])) for row in projection['slots'])
        raw_stack_world+=sum(len(bytes.fromhex(row['raw_hex'])) for row in projection['reads'])
    assert raw_stack_world==308
    raw_code_owned=0
    for phase in ('before','after'):
        snap=probe[phase];assert len(snap['code'])==3
        for row,(rva,offset,size,raw) in zip(snap['code'],parser.CODE):
            assert row==dict(rva=rva,address=parser.h(base+offset),size=size,raw_hex=raw)
            raw_code_owned+=len(bytes.fromhex(row['raw_hex']))
        assert snap['slot']==dict(rva='0x1d20870',address=parser.h(base+0x1d20870),raw8_hex=struct.pack('<Q',base+0x8f450).hex(),value=parser.h(base+0x8f450))
        raw_code_owned+=8+len(bytes.fromhex(snap['owned']['A_hex']))+len(bytes.fromhex(snap['owned']['G_hex']))
    assert raw_code_owned==918
    counters=payload['counters'];assert counters['reads']==56 and counters['requested_bytes']==counters['exact_bytes']==1290
    assert raw_stack_world+raw_code_owned==1226==1290-64
    assert c['precheck']==c['postcheck'] and c['loaded_precheck']==c['loaded_postcheck']
    pre=c['precheck'];assert pre['process_identity_checked'] is True and pre['module_set_equal'] is True
    assert pre['rpm_budget']==dict(calls=46,bytes=300,largest=32)
    assert pre['roots']['manual_pause']==1 and pre['roots']['date']==56461512
    assert pre['prefix32_hex']==c['post_prefix32_hex']==config['expected_prefix_hex']
    assert int(pre['prefix_address'],16)==base+parser.ENTRY_RVA
    assert [struct.unpack('<Q',bytes.fromhex(v))[0] for v in pre['outer_vtable_hex']]==[base+0x1c48bf8,base+0x1c48c80]
    assert pre['children_hex'][1:]==['00','0000000000000000','0000000000000000','00']
    assert struct.unpack('<Q',bytes.fromhex(pre['children_hex'][0]))[0]==int(pre['roots']['server'],16)
    for loaded in (c['loaded_precheck'],c['loaded_postcheck']):
        assert loaded['rpm_budget']==dict(calls=4,bytes=211,largest=109)
        for row,(rva,offset,size,raw) in zip(loaded['code'],parser.CODE):
            assert row==dict(rva=rva,address=hex(base+offset),size=size,raw_hex=raw)
        assert loaded['slot']==dict(rva='0x1d20870',address=hex(base+0x1d20870),raw8_hex=struct.pack('<Q',base+0x8f450).hex(),value=hex(base+0x8f450))
    job=c['job'];assert job['exit_code']==0 and job['error'] is None and job['job_active_processes_final']==0 and job['job_total_processes']==2
    assert job['direct_child_collected'] is True and job['completed_command_descendants_terminated'] is False
    assert job['memory_limit']==805306368 and job['peak_job_commit']==390508544 and job['seconds']==3.765
    assert job['existing_target_game_assigned_to_job'] is job['target_cleanup_proven_by_job'] is False
    assert c['code_restore_verified'] is c['selected_cleanup_checks_passed'] is c['REA_cleanup_reported_success'] is True
    assert c['held_process_identity_bound'] is c['host_image_and_base_verified'] is True
    assert all(v is True for v in payload['cleanup'].values())
    for field in ('native_ready','sender_authorized','native_entry_authenticated','lifetime_lease','atomic_snapshot','pure_RPM',
        'new_API_effect_tested','war_declared','peace_concluded','full_native_lifecycle','legal_Cplusplus_object_construction_proven','automatic_retry','target_full_cleanup_or_agent_unmapping_proven'):
        assert c[field] is False,field
    assert c['raw_owned_ABI_test_double'] is c['temporary_code_hook'] is True
    for field in ('native_game_objects_constructed','field_game_data_writes','requests_published','saves_written','reloads'):
        assert type(c[field]) is int and c[field]==0
    # Source control-flow review only: no host import or capture invocation.
    source=(CAND/'capture_body_once.py').read_text();tree=ast.parse(source)
    fun=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='capture')
    outer=next(n for n in fun.body if isinstance(n,ast.Try))
    with_index=next(i for i,n in enumerate(outer.body) if isinstance(n,ast.With))
    assert isinstance(outer.body[with_index+1],ast.If) and "if not result['errors']:" in source
    assert "result['top_level_native_game_calls_attempted_observed'] = None" in source
    assert "result['top_level_native_game_calls_returned_observed'] = None" in source
    report={'schema':'EU4-OWNED-BODY-INDEPENDENT-LIVE-FILE-AUDIT/1','status':'one_top_level_game_body_normal_return_raw_ABI_postimage_verified',
        'findings':[],'capture':pin(capture_path),'production_manifest':pin(manifest_path),'production_source_pins':29,
        'frozen_host_local_pins':215,'selected_external_pins':11,'production_exact_seal_transformation_verified':True,
        'source_ready':pin(review_path),'REA_evidence_id':evidence['evidence_id'],
        'whole_render_reconstructed':pin(script_path),'pure_parser_equals_recorded_evaluation':True,'owned_payload_equals_unique_REA_send':True,
        'native_call_accounting':{'target_rva':'0x500560','signature':'void(pointer)','explicit_top_level_attempted':1,
            'normal_wrapper_returned':1,'spent':True,'zero_native_call_observation':False,'nested_static_calls_dynamically_counted':False},
        'fresh_context':{'observer_nonce':config['observer_nonce'],'attempts':evaluation['attempts'],'thread_id':evaluation['thread_id'],
            'Q':evaluation['Q'],'five_returns_mainholder_world_sources_replayed':True,'historical_Q_input_or_dereference_by_auditor':False},
        'owned_raw':{'A':parser.h(a),'G':parser.h(g),'sizes':[152,96],'alignment':16,'disjoint':True,
            'explicit_JS_write_requests':4,'explicit_JS_write_bytes':264,'each_full_snapshot_bytes':248,
            'A_final_vptr':parser.h(base+0x1c3e578),'changed_A_byte_offsets':changed,'rest_A_unchanged':True,'all_G_unchanged':True,
            'intermediate_native_stores_observed':False},
        'read_accounting':{'script_requests':56,'script_requested_exact_bytes':1290,'retained_script_raw_bytes':1226,
            'script_prefix_bytes_not_inline':64,'each_script_and_host_code_slot_guard_bytes':211,
            'host_each_pre_post_counter':pre['rpm_budget'],'host_each_retained_raw_bytes':74,'independent_host_post_prefix_raw_bytes':32},
        'authentication_layers':{'pure_parser_host_authenticated':False,'pure_parser_code_restore_verified':False,
            'outer_held_identity_bound':True,'outer_independent_prefix_restored':True,'native_entry_authenticated':False},
        'cleanup':{'script_detach_flush_prefix_reported':True,'REA_inner_outer_cleanup_null':True,'host_loaded_and_world_projection_pre_post_equal':True,
            'normal_held_context_exit_per_pinned_source':True,'Job_exit0':True,'Job_total':2,'Job_active_final':0,
            'Job_peak_commit':390508544,'Job_seconds':3.765,'forced_descendants':False,'all_Frida_resources_unmapped_proven':False},
        'limits':[
            'Files/pure Evidence and body parser replay only. No producer/capture, process, Frida, REA, oldQ/heap dereference or test is run.',
            'This is1 explicit top-level game machine-body attempt and normal NativeFunction-wrapper return, with owned raw ABI test-double postimages. It is not the prior zero-native-call observation or a constructor/deleting/free/game-sender entry test.',
            'CurrentQ/tid may equal older records numerically. This nonce/script/rawREA and callback source are new; no retained historical pointer is supplied as an input or read by this audit.',
            'Owned postimages support final A[0:8]=B+1c3e578, all remainingA/G unchanged. They do not trace the intermediate two native stores or prove exhaustive total memory writes. Framework/hook/native stores are outside264B JS-write counters.',
            '1226B owned stack/world/code/slot/buffer raw is retained;64B script prefix reads are represented by counters and cleanup statements. Separate host prefix raw provides independent selected restoration evidence.',
            'Host each46reads300B projection retains only74B raw. Identity, full module lists, loaded PE header, full roots and normal handle close remain pinned-producer witnesses. Setup RPM and kernel operations are outside these selected counters.',
            'Pure parser hostauth/restore flags remainfalse; outer held-process/prefix verification is separate evidence. Content Evidence ID is not a signature and selected11 external pins are not a complete dependency/OS closure.',
            'Code/world/ASLR-slot prepost equality is non-atomic, excludes no ABA or transient modification and proves no world/header/module lease or full Frida agent unmapping. Soft JS deadline is not a native timeout.',
            'Jobactive0 covers the new CLI tree only, not target-agent memory or all target resources; existing game was not placed in that job.',
            'No legal C++ construction, constructor equivalence, full lifecycle, noCB semantics, declarewar/peace API, gameplay effect, TLS/xstate/exceptional unwind or future native/sender readiness follows.'
        ],
        'native_game_objects_constructed':0,'new_API_effects':0,'war_declared':False,'peace_concluded':False,
        'native_ready':False,'native_ABI_ready':False,'sender_authorized':False,'native_entry_authenticated':False,
        'world_lease':False,'lifetime_lease':False,'sentinel_header_lease':False,'atomic_snapshot':False,
        'process_accessed_by_auditor':False,'Frida_called_by_auditor':False,'tests_reexecuted':False}
    assert not OUT.exists();OUT.mkdir(parents=True)
    write_new(OUT/'independent-file-audit.json',report)
    write_new(OUT/'independent-file-audit.md',
        '# R19 body probe 独立实采文件审计\n\n通过。明确记录一次顶层 500560/void(pointer) 尝试并正常返回；不能沿用零 native 调用描述。'
        '完整 render、REA semantic ID、唯一 payload、parser、owned 全图、ASLR slot、代码及来源 pin 一致。\n\n'
        'A 首 qword 最终为 B+1c3e578，其余 A/G 全部保持；四次显式 JS owned 写共 264B。JS56reads/1290B，其中1226B原始图保留、64B脚本 prefix 未内联；宿主独立32B恢复核验通过。'
        '宿主前后投影及211B代码/slot守卫相同；Job2、active0、exit0，无强制后代收尾。\n\n'
        '这只是 raw ABI test double 的正常返回和最终字节观测；不是 ctor、合法 C++ 对象、完整生命周期、noCB、宣战、议和或 API 效果。'
        '所有 nativeReady/sender/auth/lease/atomic 保持 false，不证明 Frida 内部全部 unmap。本审计未访问进程、重采或重跑测试。\n')
    for p in (manifest_path,capture_path,Path(__file__).resolve(),OUT/'independent-file-audit.json',OUT/'independent-file-audit.md'):
        add(p)
    for name in ('claim.json','owned-payload.json','rea.stderr.txt','rea.stdout.json','rendered-body-probe.js'):add(LIVE/name)
    write_new(OUT/'manifest.json',{'schema':'EU4-OWNED-BODY-INDEPENDENT-LIVE-AUDIT-MANIFEST/1','sealed':True,
        'source_pins':dict(sorted(selected.items())),'selected_external_pins':frozen['selected_external_pins']})
    print(json.dumps({'status':report['status'],'report':pin(OUT/'independent-file-audit.json'),
        'manifest':pin(OUT/'manifest.json'),'local_pins':len(selected),'selected_external_pins':11}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    check() if args.check else main()
