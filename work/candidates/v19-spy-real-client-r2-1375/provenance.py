"""Build/loader/permanent-file provenance; pure file reads only."""
import re
from pathlib import Path
from frozen import b,wire,reader,files,verify_build,same,integer,exact,require

def hexint(value):
    require(type(value)is str and re.fullmatch('0x[0-9a-f]+',value) and hex(int(value,16))==value,'Canonical address hex')
    result=int(value,16);integer(result,0x10000,2**47-1);return result

def loader_record(record,identity,manifest,directory,boot):
    exact(record,set('schema purpose identity process_path plan_only disposable_test_premise strict_sp_verified world_epoch_verified production_ready automatic_stage restricted_research_send stage_request_written bootstrap_sha256 bootstrap_bytes installation held_identity_checked_after'.split()))
    same([record['schema'],record['purpose'],record['identity']],['EU4SPYSENDLOAD/1',wire.PURPOSE,identity])
    require(type(record['process_path'])is str and record['process_path'],'Recorded image path')
    for key in ('plan_only','strict_sp_verified','world_epoch_verified','production_ready','automatic_stage','stage_request_written'):same(record[key],False)
    for key in ('disposable_test_premise','restricted_research_send','held_identity_checked_after'):same(record[key],True)
    same([record['bootstrap_sha256'],record['bootstrap_bytes']],[b.sha(boot),len(boot)])
    call=record['installation']
    exact(call,set('pid process dll dll_module_base bridge_rva bridge_remote_address load_library_owner load_library_rva load_library_remote_address load_thread_exit_status bridge_thread_exit_status test_save_acknowledged dll_unloaded warnings'.split()))
    same([call['pid'],call['process'],call['dll'],call['bridge_rva'],call['bridge_thread_exit_status'],call['test_save_acknowledged'],call['dll_unloaded']],
         [identity['pid'],record['process_path'],str((directory/b.DLL).resolve()),hex(manifest['pe']['bridge_start_rva']),'0x0',True,False])
    base=hexint(call['dll_module_base']);require(base%65536==0,'Module allocation alignment')
    same(call['bridge_remote_address'],hex(base+manifest['pe']['bridge_start_rva']))
    for key in ('load_library_owner','load_library_rva','load_library_remote_address','load_thread_exit_status'):require(type(call[key])is str and call[key],'Loader result string')
    require(Path(call['load_library_owner']).is_absolute(),'Absolute loader owner path')
    require(re.fullmatch('0x[0-9a-f]+',call['load_library_rva']) and hex(int(call['load_library_rva'],16))==call['load_library_rva'] and 0<int(call['load_library_rva'],16)<0x4000000,'Canonical bounded loader RVA')
    hexint(call['load_library_remote_address'])
    require(re.fullmatch('0x[0-9a-f]+',call['load_thread_exit_status']) and int(call['load_thread_exit_status'],16)==(base&0xffffffff),'LoadLibrary truncated module return')
    require(type(call['warnings'])is list and not call['warnings'],'Clean loader completion')
    return base

def startup(raw,outer,identity):
    """Exact empty-raw startup only. Never synthesize a health/core record."""
    require(raw==b'','Startup has no raw data');rows,_=reader.records(outer,2097152,1024)
    require(3<=len(rows)<=5,'Startup exact bounded install history')
    clock=0;owner=image=None;installed=False;attempt=0
    for n,e in enumerate(rows,1):
        event=e.get('event');require(event in ('bootstrap_verified','install_attempt','hook_installed'),'Startup cannot contain owner/core work')
        exact(e,reader.COMMON|reader.EXTRA[event]);same({k:e[k] for k in wire.IDENTITY},identity)
        same([e['schema'],e['game_sha256']],['EU4SPYSENDBOOTSTRAP/1',wire.GAME_SHA]);integer(e['ordinal'],n,n);integer(e['uptime_ms'],clock);clock=e['uptime_ms']
        integer(e['owner_thread'],1,2**32-1);integer(e['thread'],1,2**32-1);integer(e['image_base'],0x10000,2**47-1);require(e['image_base']%65536==0,'Game image alignment')
        if owner is None:owner=e['owner_thread'];image=e['image_base']
        same([owner,image],[e['owner_thread'],e['image_base']]);same(e['restricted_research_send'],True)
        for k in ('strict_sp_verified','world_epoch_verified','production_ready'):same(e[k],False)
        if n==1:
            same(event,'bootstrap_verified');same([e[k] for k in ('disposable_test_premise','native_environment_initialized','automatic_stage','runtime_verified')],[True,True,False,False])
        elif event=='install_attempt':
            require(not installed,'No attempts after success');d=e['detail'];exact(d,reader.DETAIL);attempt+=1
            same(d['event'],'hook_install_attempt');integer(d['attempt'],attempt,attempt)
            for key in reader.DETAIL-{'event','prefix_unchanged','retrying','send_supported'}:integer(d[key])
            for key in ('prefix_unchanged','retrying','send_supported'):require(type(d[key])is bool,'Strict install bool')
            same(d['send_supported'],False);require(d['collected']<=512 and d['suspended']<=d['collected'],'Thread bound')
            require(all(d[k]==0 for k in ('resume_failures','resume_error','resume_thread')),'Thread restoration')
            if d['result']==0:
                require(d['collected']>=1 and all(d[k]==0 for k in ('failure_stage','error','failure_thread','rip')) and d['prefix_unchanged'] is False and d['retrying'] is False,'Clean install');installed=True
            else:require(d['result']==21 and d['prefix_unchanged'] is True and d['retrying'] is True and attempt<3,'Only prepatch retry')
        else:
            require(installed and n==len(rows),'Last hook after successful install')
            same({k:e[k] for k in reader.EXTRA[event]},dict(frame_rva=0x10a6ec0,prefix_bytes=20,stage_limit=4,fixed_items=5,health_interval_ms=1000,poll_interval_ms=100,hot_unload_supported=False))
    require(rows[-1]['event']=='hook_installed','Hook installed startup')
    return dict(status='ready',identity=identity,next_sequence=1,claimed_sequence=0,preflight_ready=True,authenticated_stages=0,completed_items=0,
                controller_frames=0,owner_thread=owner,image_base=image,last_owner_uptime_ms=clock,selected_world=None,last_raw_record=None,
                raw_sha256=b.sha(raw),outer_sha256=b.sha(outer),raw_bytes=0,outer_bytes=len(outer),startup_only=True,
                runtime_authorized=False,effect_verified=False,production_ready=False,strict_sp_verified=False,world_epoch_verified=False,retry_allowed=False)

def inspect(directory,identity,complete=False):
    directory=Path(directory).resolve();identity=wire.identity(identity);manifest,digest=verify_build(directory)
    same([identity['dll_sha256'],identity['manifest_sha256']],[manifest['dll_sha256'],digest])
    boot=files.read(directory/f'bootstrap-{identity["pid"]}-{identity["creation"]}.request',1024);same(wire.decode_boot(boot),identity)
    raw_loader=files.read(directory/f'loader-{identity["pid"]}-{identity["creation"]}.json',32768);record=b.json_value(raw_loader)
    modulebase=loader_record(record,identity,manifest,directory,boot)
    session=wire.session_path(directory,identity)
    raw=files.read(session/'raw-events.jsonl',1048576)
    if raw:
        result=files.inspect_files(session,identity,complete)
    else:
        require(not complete,'Empty raw cannot complete');outer=files.read(session/'bootstrap-events.jsonl',2097152)
        for name in ('1','2','3','4',*('4.item-'+str(i) for i in range(1,6))):require(not(session/(name+'.claim')).exists(),'Startup cannot contain claims')
        result=startup(raw,outer,identity)
        # A first real owner call may appear meanwhile. Never silently retain
        # the less informative empty-raw view; use the complete pure reader.
        if files.read(session/'raw-events.jsonl',1048576):result=files.inspect_files(session,identity,complete)
    result.update(source_bound_origin_verified=True,source_manifest_verified=True,build_loader_verified=True,
                  source_bound_not_cryptographic_attestation=True,loader_sha256=b.sha(raw_loader),
                  installation_module_base=modulebase,installation_process_path=record['process_path'],manifest_pe=manifest['pe'],
                  installation_load_library={k:record['installation'][k] for k in ('load_library_owner','load_library_rva','load_library_remote_address')},
                  live_identity_verified=False,runtime_authorized=False)
    return result
