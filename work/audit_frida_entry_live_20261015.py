"""Replay retained live-entry files only. Never reads a process/address."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import types

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
HERE=ROOT/'work/candidates/frida-entry-observer-1375-v1'
LIVE=ROOT/'work/reports/war-peace-api-20261015-r12-entry-live'
OUT=ROOT/'work/reports/frida-entry-live-review-20261015-r1'

def pin(path):
    sha=hashlib.sha256();count=0
    with path.open('rb') as stream:
        while raw:=stream.read(65536):count+=len(raw);sha.update(raw)
    return dict(bytes=count,sha256=sha.hexdigest())
def load(path):return json.loads(path.read_bytes())
def exact_module(path,sha,name):
    raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==sha
    value=types.ModuleType(name);value.__file__=str(path)
    exec(compile(raw,str(path),'exec'),value.__dict__);return value
def check():
    data=load(OUT/'manifest.json');assert data['sealed'] is True
    for name,wanted in data['source_pins'].items():assert pin(ROOT/name)==wanted,name
    print(json.dumps(dict(status='pass',pins=len(data['source_pins']),process_read=False,Frida_invoked=False)))

def main():
    manifest=HERE/'host-manifest.json'
    assert pin(manifest)==dict(bytes=43987,sha256='e7673b0e07c052788d6d2c6378939e176f57e79a45ea09888b957741b7370166')
    capture=LIVE/'capture.json'
    assert pin(capture)==dict(bytes=50769,sha256='cd96099990856fde385a8499f7e3c1d0a303ed11d6460947d45dab0c9ce83a6b')
    host=exact_module(HERE/'capture_once.py','b39823564ab26a9da7093e1812b2a1fec28a17141e3c4a1024460664b1943b6e','live_file_host')
    verified=host.verify_manifest() # File hashes/closure only, never capture().
    prod=load(manifest);draft=load(HERE/'host-manifest.draft-r4.json')
    assert prod['sealed'] is True and draft['sealed'] is False
    assert prod['source_pins']==draft['source_pins'] and prod['selected_external_pins']==draft['selected_external_pins']
    assert len(verified['source_pins'])==215 and len(verified['selected_external_pins'])==11
    reviewed=prod['independent_source_review'];review_path=ROOT/reviewed['path']
    assert pin(review_path)['sha256']==reviewed['sha256']=='1e6a4d13331e19bfd63047936bf23a2113c2e88f9294026df44ea4577417ffaf'
    assert reviewed['runtime_attach_validated'] is False # The earlier review was source-only.
    # The Python-owned host journal contains full integer handles and finite
    # timing floats. The REA wire envelope remains on its stricter profile.
    result=host.strict_json(capture.read_bytes(),1024*1024,evidence_scalars=False)
    assert result['source_graph']==verified and result['status']=='structural_match' and result['errors']==[]
    config=result['config'];assert config['pid']==80340 and config['creation']=='01dd5c075fcf8c26'
    assert result['pid']==config['pid'] and result['creation']==config['creation']
    claim=host.strict_json((LIVE/'claim.json').read_bytes(),8192)
    assert claim['schema']=='EU4-FRIDA-ENTRY-CLAIM/1' and claim['automatic_retry'] is False
    assert claim['pid']==config['pid'] and claim['creation']==config['creation']
    assert claim['manifest_sha256']==verified['manifest_sha256'] and claim['requests_published']==0
    assert datetime.fromisoformat(claim['claimed_utc'])<=datetime.fromisoformat(result['captured_utc'])
    rendered=LIVE/'rendered-entry.js';raw=rendered.read_bytes()
    prefix=b'const EU4_ENTRY_OBSERVER_CONFIG = '
    assert raw.startswith(prefix)
    line,body=raw.split(b';\n',1)
    decoded=host.strict_json(line[len(prefix):],2048)
    assert decoded==config and body==(HERE/'entry_observer.js').read_bytes()
    # Capture.json sorted its config keys. Reconstruct the original literal
    # ordering from the pinned host, rather than falsely changing source SHA.
    keys=('schema','pid','creation','game_sha256','base','expected_prefix_hex','observer_nonce','max_attempts')
    assert host.rendered_script({key:config[key] for key in keys},verified)==raw
    assert pin(rendered)==result['rendered_script_pin']==dict(bytes=14984,sha256='424dd0b2095353ca25d74b4507a443d7797a2af44ab34ce6d1a7b3724cfbac1c')
    assert (LIVE/'rea.stderr.txt').stat().st_size==0
    evidence,payload=host.extract_evidence((LIVE/'rea.stdout.json').read_bytes(),config,str(rendered.resolve()),pin(rendered)['sha256'])
    assert evidence['evidence_id']==result['REA_evidence_id']=='ev_faef7e7eb9c98a8ff79f50b882ef34253a70db3736aa3c461490f168b45b5a85'
    owned=host.strict_json((LIVE/'owned-payload.json').read_bytes(),16384)
    assert payload==owned
    parser=exact_module(HERE/'entry_observation_parser.py','56639f22de638696388ee7862feb050d800a4797633c25f366812dd5e034c32c','live_file_pure_parser')
    evaluated=parser.evaluate(payload,config)
    assert evaluated==result['payload_evaluation'] and evaluated['status']=='structural_match'
    observation=payload['observation'];base=int(config['base'],16);q=int(observation['Q'],16)
    assert q==0x919bffdd88 and q%16==8 and observation['thread_id']==35220
    assert observation['interceptor_depth']==0 and payload['attempts']==1 and observation['two_pass_equal'] is True
    assert observation['first']==observation['second']
    returns=[(0,0x10a6d61),(0x40,0x81582e),(0x370,0x14c2818),(0x3f0,0x14c2e18),(0x440,0x8781b9)]
    records=[];raw_total=0
    for label in ('first','second'):
        project=observation[label];fields=project['fields']
        assert len(project['slots'])==6 and len(project['reads'])==15
        for index,slot in enumerate(project['slots']):
            number=int.from_bytes(bytes.fromhex(slot['raw8_hex']),'little');raw_total+=8
            assert len(slot['raw8_hex'])==16 and int(slot['address'],16)==q+slot['offset']
            assert int(slot['value'],16)==number
            expected=base+returns[index][1] if index<5 else int(fields['outer'],16)
            assert number==expected
        for read in project['reads']:
            data=bytes.fromhex(read['raw_hex']);raw_total+=len(data)
            assert len(data)==read['size'] in (1,8)
            expected=int.from_bytes(data,'little') if len(data)==1 else '0x'+format(int.from_bytes(data,'little'),'016x')
            assert fields[read['field']]==expected
        outer=int(fields['outer'],16);game=int(fields['game'],16);server=int(fields['current_app'],16)
        holder=int(fields['server_holder'],16)
        addresses={'outer':base+0x242bf50,'game':base+0x233fe78,'outer_vtable':outer,
            'outer_secondary_vtable':outer+0x10,'current_app':outer+0x40,'pending_app':outer+0x70,
            'previous_app':outer+0x78,'transition_byte':outer+0x48,'retain_previous_byte':outer+0x80,
            'game_vtable':game,'game_server':game+0x1e00,'current_vtable':server,
            'current_update':base+0x1cb8460+0x20,'server_holder':server+0x330,'map_object':holder+0x360}
        assert all(int(read['address'],16)==addresses[read['field']] for read in project['reads'])
        assert fields['current_app']==fields['game_server']==observation['original_r8']
        assert fields['map_object']==observation['original_rcx']
        assert fields['outer']==fields['server_holder']==project['slots'][5]['value']
        assert fields['pending_app']==fields['previous_app']=='0x0000000000000000'
        assert fields['pending_vtable'] is fields['previous_vtable'] is None
        assert fields['transition_byte']==fields['retain_previous_byte']==0
        records.append(dict(pass_name=label,slots=6,world_reads=15,owned_raw_bytes=154))
    assert raw_total==308
    categories=payload['counters']['categories']
    assert categories==dict(prefilter=dict(reads=5,bytes=40),prefix_before=dict(reads=1,bytes=32),
        prefix_cleanup=dict(reads=1,bytes=32),stack=dict(reads=7,bytes=56),world=dict(reads=30,bytes=212))
    assert sum(x['reads'] for x in categories.values())==payload['counters']['reads']==44
    assert sum(x['bytes'] for x in categories.values())==payload['counters']['requested_bytes']==payload['counters']['exact_bytes']==372
    pre,post=result['precheck'],result['postcheck'];assert pre==post
    fields=observation['first']['fields']
    assert int(pre['outer'],16)==int(fields['outer'],16)
    assert int(pre['roots']['game'],16)==int(fields['game'],16)
    assert int(pre['roots']['server'],16)==int(fields['game_server'],16)
    assert pre['roots']['manual_pause']==1 and pre['roots']['date']==56461512
    for row,rva in zip(pre['outer_vtable_hex'],(0x1c48bf8,0x1c48c80)):
        assert int.from_bytes(bytes.fromhex(row),'little')==base+rva
    child=pre['children_hex'];assert list(map(lambda x:len(bytes.fromhex(x)),child))==[8,1,8,8,1]
    assert int.from_bytes(bytes.fromhex(child[0]),'little')==int(fields['current_app'],16)
    assert child[1:]==['00','0000000000000000','0000000000000000','00']
    assert pre['prefix32_hex']==post['prefix32_hex']==result['post_prefix32_hex']==host.PREFIX.hex()
    assert int(pre['prefix_address'],16)==base+host.ENTRY_RVA
    assert pre['rpm_budget']==dict(bytes=300,calls=46,largest=32)
    host.accepted_job(result['job']);job=result['job']
    assert job['job_total_processes']==2 and job['completed_command_descendants_terminated'] is False
    assert job['peak_job_commit']==389971968<=job['memory_limit']==805306368
    assert job['target_cleanup_proven_by_job'] is False
    for key in ('attach_may_have_been_attempted','native_callback_observed','native_stack_sampled',
        'temporary_code_hook','held_process_identity_bound','host_image_and_base_verified',
        'code_restore_verified','selected_cleanup_checks_passed','REA_cleanup_reported_success'):
        assert result[key] is True,key
    for layer in (result,payload,evaluated):
        for key in ('native_ready','native_entry_authenticated','lifetime_lease','atomic_snapshot','pure_RPM'):
            assert layer[key] is False,key
    assert evaluated['host_identity_authenticated'] is False and evaluated['code_restore_verified'] is False
    assert evaluated['requires_host_authentication'] is evaluated['requires_independent_code_restore_verification'] is True
    assert result['target_full_cleanup_or_agent_unmapping_proven'] is False
    for key in ('field_game_data_writes','native_game_calls','native_game_objects_constructed',
        'requests_published','saves_written','reloads'):assert type(result[key]) is int and result[key]==0,key
    assert result['new_API_effect_tested'] is False and result['automatic_retry'] is False
    report=dict(schema='EU4-FRIDA-ENTRY-INDEPENDENT-LIVE-FILE-AUDIT/1',
        status='pass_selected_retained_runtime_context',findings=[],capture=pin(capture),
        production_manifest=dict(**pin(manifest),local_pins=215,selected_external_pins=11,source_pins_equal_draft4=True),
        REA_evidence_id=evidence['evidence_id'],semantic_ID_and_complete_rendered_SHA_replayed=True,
        owned_payload_equals_unique_REA_send=True,pure_parser_replay_equals_recorded_evaluation=True,
        observed_context=dict(pid=80340,creation=config['creation'],Q=observation['Q'],thread_id=35220,
            attempts=1,interceptor_depth=0,original_rcx=observation['original_rcx'],original_r8=observation['original_r8'],
            return_offsets=[hex(x[0]) for x in returns],main_holder_offset='0x4a8',two_pass_equal=True,
            raw_replay=records,selected_raw_stack_and_world_bytes=308,script_reads=44,script_requested_bytes=372),
        current_alias_observed=dict(outer_global_value_equals_main_holder=True,server_holder_equals_outer=True,
            current40_equals_read64_game1e00_equals_R8=True,read64_outer360_equals_original_RCX=True,
            pending_previous_null=True,ownership_or_lifetime_inferred=False),
        selected_cleanup=dict(script_detach_flush_prefix_reported=True,REA_both_cleanup_errors_null=True,
            host_independent_prefix32_hex_replayed=True,host_pre_post_projection_equal=True,
            host_held_close_normal_per_sealed_source_protocol=True,job_active_final=0,job_total=2,
            job_peak_commit=389971968,forced_descendant_termination=False,full_agent_unmapping_proven=False),
        authentication_layers=dict(pure_parser_host_authenticated=False,pure_parser_code_restore_verified=False,
            outer_host_held_process_identity_bound=True,outer_host_selected_code_restore_verified=True,
            same_meaning=False,native_entry_authenticated=False),
        evidence_limits=[
            'This audit reads retained files only. No historicalQ/heap address is dereferenced and no process/Frida/REA is invoked or resampled',
            'First auditor pass incorrectly applied Evidence safeinteger rules to the Python-owned hostjournal fullhandles/timingfloats; corrected metadata profile before writing this audit, not a capture failure',
            'Raw12 stackslot and30world reads support the actual retained onEnter structuralcontext; no full1200B stackwindow, atomicworld or borrowedheader lifetime follows',
            'Pure parser verifies supplied owned-data consistency only. Outer heldidentity/image/module/pause assertions come from sealedhost capture protocol and are not created by the parser',
            'RawOS handle/creation telemetry, loadedPEheader and complete modulelist are not retained; those checks cannot be independently byte-replayed from this receipt',
            '308B ownedstack/world raw excludes64B script codeprefixreads. Host retainedprefix bytes independently match selectedoriginal32B; not all hook/runtime resources or mappings are proved released',
            'Tid35220 is the observed Frida callbackthread; no separateOS main/owner-thread attestation is supplied',
            'Jobactive0/389971968B covers the newCLI tree only, not targetagent memory or totalgame resourceusage',
            'Safe argv is bound by pinnedfixedsource; parent retained outerCLI invocation separately. No OS commandline observation is claimed',
            'EvidenceID is a semantic content hash, not signature. Selected external11 pins are not the wholeREA/npm transitive closure',
            'No explicit observer gamefunction/nativeaction call, request, save, reload, objectconstruction or gamefield write is evidenced by this fixedsource; natural originalgamefunction execution is not counted as a sender action',
            'Temporary codehook is true/pureRPMfalse. This observation does not authorize a war/peace executor, prove lifecyclelease or constitute a newdiplomacyAPI effecttest'],
        process_read_by_auditor=False,Frida_invoked_by_auditor=False,REA_invoked_by_auditor=False,
        tests_reexecuted=False,new_API_effects=0,native_ready=False,native_entry_authenticated=False,
        lifetime_lease=False,atomic_snapshot=False)
    OUT.mkdir(exist_ok=False)
    path=OUT/'independent-file-audit.json'
    with path.open('x',encoding='utf-8',newline='\n') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    md=OUT/'independent-file-audit.md'
    with md.open('x',encoding='utf-8',newline='\n') as stream:
        stream.write('固定215来源、11选定外部来源与整份rendered脚本SHA/REA semantic ID一致。两遍12栈槽及30世界字段的原始字节全部重放通过，44次读取/372B，首次callback，线程35220。\n\n')
        stream.write('当前Q+4a8、global outer与server+330的读值相同；current40、game+1e00读值及原R8相同，map为原RCX。此为当前结构及别名观察，不证明ownership或借用寿命。\n\n')
        stream.write('独立宿主32B代码恢复、pre==post和CLI Job active0通过。纯parser的hostauth/code_restore=false与外层held-process/selected-code-restore=true属于不同证据层，不能合并。完整agent解除映射仍未证明。\n\n')
        stream.write('本审计只读文件，未访问游戏或重新采样。临时代码hook=true，pureRPM=false；保存/重载/请求/显式游戏native动作与字段写入为0。native_ready、native_entry_authenticated、lease及atomic均false。\n')
    pins=verified['source_pins'].copy();pins.update(verified['selected_external_pins'])
    for p in (manifest,review_path,HERE/'host-manifest.draft-r4.json',Path(__file__),path,md,*LIVE.iterdir()):
        if p.is_file():pins[p.relative_to(ROOT).as_posix()]=pin(p)
    with (OUT/'manifest.json').open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(dict(schema='EU4-INDEPENDENT-RUNTIME-FILE-AUDIT-MANIFEST/1',sealed=True,
            capture_sha256=pin(capture)['sha256'],source_pins=pins),stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=report['status'],report=pin(path),pins=len(pins),process_read=False,Frida_invoked=False)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true')
    if p.parse_args().check:check()
    else:main()
