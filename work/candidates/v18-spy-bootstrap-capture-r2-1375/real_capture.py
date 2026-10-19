"""Source-bound private capture verifier. Only bounded files; no process access.

The loader/build chain is local research evidence, not cryptographic attestation
against a malicious user who can replace every file. Every raw row is checked
before health compaction. Complete native calls are inferred only from normal
return records; a core step_begin alone is an intent, never actual entry.
"""
from pathlib import Path
import re
from _frozen import b, wire, trace

COMMON={'schema','event','pid','creation','session','game_sha256','dll_sha256','manifest_sha256','image_base','owner_thread','thread','ordinal','uptime_ms','send_supported','strict_sp_verified','world_epoch_verified','production_ready'}
EXTRA={'bootstrap_verified':{'disposable_test_premise','native_environment_initialized','automatic_stage','runtime_verified'},
       'install_attempt':{'detail'},'hook_installed':{'frame_rva','prefix_bytes','stage_limit','health_interval_ms','poll_interval_ms','hot_unload_supported'},
       'owner_call_begin':{'owner_entry','controller_frame_before','raw_start','raw_first_ordinal','request_sequence'},
       'owner_call_return':{'owner_entry','controller_frame_after','raw_end','raw_last_ordinal','raw_segment_sha256','controller_returned','input_closed','state','failure','claimed','completed','success'},
       'completed_no_send':{'owner_entry','controller_frame','stages','owned_objects_remaining','individual_effect_verified'}}
DETAIL={'event','attempt','result','prefix_unchanged','retrying','failure_stage','error','failure_thread','collected','suspended','resume_failures','resume_error','resume_thread','rip','send_supported'}


def integer(v,lo=0,hi=2**64-1):return type(v)is int and lo<=v<=hi
def require(ok,why):b.require(ok,why)
def exact(a,c,why):require(b.exact(a,c),why)


def records(raw,limit,count):
    require(type(raw)is bytes and 0<len(raw)<=limit and raw.endswith(b'\n'),'Complete bounded raw capture')
    lines=raw.splitlines(keepends=True)
    require(len(lines)<=count and all(0<len(line)<=8192 for line in lines),'Capture row budget')
    rows=[b.json_value(line) for line in lines]
    require(all(type(row)is dict for row in rows),'Object capture rows')
    return rows,lines


def validate_stream(raw,outer,identity,claims,complete):
    """Internal pure validator; callers cannot supply a replacement checker."""
    require(type(complete)is bool and type(claims)is dict and all(type(k)is int and 1<=k<=3 and type(v)is bytes for k,v in claims.items()),'Typed completion/claim map')
    identity=wire.identity(identity);rows,lines=records(raw,trace.MAX_BYTES,trace.MAX_LINES)
    outside,_=records(outer,2097152,1024)
    clock=0;owner=None;image=None;phase='bootstrap';attempt=0;installed=False;begin=None
    frame=0;offset=0;ordinal=0;entry=0;claimed=0;completed=0;footer=False
    for n,e in enumerate(outside,1):
        event=e.get('event');require(event in EXTRA and set(e)==COMMON|EXTRA[event],'Exact successful outer event shape')
        exact({k:e[k] for k in wire.IDENTITY},identity,'Foreign outer identity')
        require(e['schema']=='EU4SPYBOOTSTRAP/1' and e['game_sha256']==wire.p.GAME_SHA256,'Outer protocol/build')
        require(integer(e['ordinal'],n,n) and integer(e['uptime_ms'],clock),'Outer record ordering');clock=e['uptime_ms']
        require(integer(e['owner_thread'],1,0xffffffff) and integer(e['thread'],1,0xffffffff)
                and integer(e['image_base'],65536,2**47-1) and e['image_base']%8==0,'Outer machine identity')
        if owner is None:owner=e['owner_thread'];image=e['image_base']
        exact([e['owner_thread'],e['image_base']],[owner,image],'Outer owner/image changed')
        require(all(e[k] is False for k in ('send_supported','strict_sp_verified','world_epoch_verified','production_ready')),'Unsupported outer permissions')
        require(not footer,'Record after completed footer')
        if event=='bootstrap_verified':
            require(n==1 and phase=='bootstrap' and e['disposable_test_premise'] is True and e['native_environment_initialized'] is True
                    and e['automatic_stage'] is False and e['runtime_verified'] is False,'Explicit verified bootstrap')
            phase='install'
        elif event=='install_attempt':
            require(phase=='install' and not installed and type(e['detail'])is dict and set(e['detail'])==DETAIL,'Install attempt phase')
            d=e['detail'];attempt+=1
            require(d['event']=='hook_install_attempt' and integer(d['attempt'],attempt,attempt) and attempt<=3
                    and d['send_supported'] is False,'Install attempt identity')
            require(all(integer(d[k]) for k in DETAIL-{'event','prefix_unchanged','retrying','send_supported'}),'Strict install scalars')
            require(all(d[k]==0 for k in ('resume_failures','resume_error','resume_thread')),'Suspension restoration failed')
            require(d['collected']<=512 and d['suspended']<=d['collected'],'Suspension bound')
            if d['result']==0:
                require(d['prefix_unchanged'] is False and d['retrying'] is False and d['failure_stage']==0,'Installed patch result')
                require(d['collected']>=1 and all(d[k]==0 for k in ('error','failure_thread','rip')),'Successful installation cannot contain a failure diagnostic or empty thread set')
                installed=True
            else:
                require(d['result']==21 and d['prefix_unchanged'] is True and d['retrying'] is True and attempt<3,'Only prepatch bounded retry')
        elif event=='hook_installed':
            require(phase=='install' and installed,'Hook lacks successful installation')
            exact({k:e[k] for k in EXTRA[event]},dict(frame_rva=0x10a6ec0,prefix_bytes=20,stage_limit=3,health_interval_ms=1000,poll_interval_ms=100,hot_unload_supported=False),'Fixed owner hook contract')
            phase='owner'
        elif event=='owner_call_begin':
            require(phase=='owner' and begin is None and e['thread']==owner,'Owner call pairing/thread')
            require(integer(e['owner_entry'],entry+1) and integer(e['controller_frame_before'],frame,frame)
                    and integer(e['raw_start'],offset,offset) and integer(e['raw_first_ordinal'],ordinal+1,ordinal+1),'Owner/raw starting boundary')
            require(integer(e['request_sequence'],0,3) and e['request_sequence'] in (0,claimed+1),'Strict next request')
            begin=e;entry=e['owner_entry']
        elif event=='owner_call_return':
            require(begin is not None and e['thread']==owner,'Return lacks owner call')
            require(integer(e['owner_entry'],entry,entry) and integer(e['controller_frame_after'],frame+1,frame+1)
                    and integer(e['raw_end'],offset+1,len(raw)) and integer(e['raw_last_ordinal'],ordinal+1,len(rows)),'Owner/raw return boundary')
            end=e['raw_last_ordinal'];segment=lines[ordinal:end]
            require(sum(map(len,segment))==e['raw_end']-offset and b.sha(b''.join(segment))==e['raw_segment_sha256'],'Exact call segment SHA/range')
            selected=rows[ordinal:end]
            require(selected[0]['event']=='health','Each Controller call begins with independent health')
            for row in selected:
                require(integer(row.get('frame'),frame+1,frame+1) and integer(row.get('uptime_ms'),begin['uptime_ms'],e['uptime_ms']),'Actual call frame/time envelope')
                exact({k:row.get(k) for k in wire.IDENTITY},identity,'Foreign raw identity')
                exact([row.get('thread'),row.get('image_base')],[owner,image],'Foreign raw owner/image')
            sequence=begin['request_sequence']
            if sequence:
                require(sequence==claimed+1 and completed==claimed,'Stage must follow independent health')
                claims_in=[r for r in selected if r['event']=='claim'];results=[r for r in selected if r['event']=='run_result']
                require(len(claims_in)==len(results)==1 and selected[-1]['event']=='run_result','Exactly one successful requested stage')
                claim=claims_in[0];require(claim['sequence']==sequence and sequence in claims,'Exact retained request/claim')
                require(claim['wire_hex']==claims[sequence].hex(),'Claim byte binding')
                claimed=completed=sequence;expected_state=3
            else:
                require(len(selected)==1,'Health callback cannot contain core calls')
                expected_state=4 if completed==3 else 1
            exact([e['state'],e['failure'],e['claimed'],e['completed']],[expected_state,0,claimed,completed],'Native Controller terminal state')
            require(all(e[k] is True for k in ('controller_returned','input_closed','success')),'Uncertain call/input lifecycle')
            frame+=1;offset=e['raw_end'];ordinal=end;begin=None
        else:
            require(phase=='owner' and begin is None and completed==3 and rows[ordinal-1]['event']=='health' and e['thread']==owner,'Complete footer requires later owner health')
            exact({k:e[k] for k in EXTRA[event]},dict(owner_entry=entry,controller_frame=frame,stages=3,owned_objects_remaining=0,individual_effect_verified=False),'Complete footer')
            footer=True
    require(phase=='owner' and begin is None and ordinal==len(rows) and offset==len(raw),'No unbound raw tail/incomplete owner call')
    require(set(claims)==set(range(1,claimed+1)),'No unbound retained claim')
    require(footer if complete else not footer or completed==3,'Completed marker contract')
    result=trace.inspect(rows,complete=complete or footer)
    result.update(source_bound_private_capture=True,outer_hook_install_receipt_verified=True,raw_host_hook_field=False,
                  completed=footer,claimed_sequence=claimed,owner_entries_observed=entry,controller_frames=frame,
                  latest_health=rows[-1],outer_sha256=b.sha(outer),raw_sha256=b.sha(raw),raw_bytes=len(raw),outer_bytes=len(outer))
    return result


def inspect(directory,identity,complete=False):
    directory=b.no_links(directory).resolve();identity=wire.identity(identity)
    manifest,manifest_sha=b.verify_build(directory)
    exact([identity['dll_sha256'],identity['manifest_sha256']],[manifest['dll_sha256'],manifest_sha],'Identity build binding')
    boot=b.bounded(b.no_links(directory/f'bootstrap-{identity["pid"]}-{identity["creation"]}.request'),1024)
    exact(wire.decode_boot(boot),identity,'Bootstrap identity')
    loader=b.json_value(b.bounded(b.no_links(directory/f'loader-{identity["pid"]}-{identity["creation"]}.json'),32768))
    require(type(loader)is dict and loader.get('schema')=='EU4SPYLOAD/1' and loader.get('purpose')==b.PURPOSE,'Loader provenance')
    exact(loader.get('identity'),identity,'Loader identity')
    require(loader.get('plan_only') is False and loader.get('disposable_test_premise') is True and loader.get('held_identity_checked_after') is True,'Actual loader identity/return')
    require(all(loader.get(k) is False for k in ('strict_sp_verified','world_epoch_verified','production_ready','automatic_stage','send_supported','stage_request_written')),'Loader cannot authorize sending')
    exact([loader.get('bootstrap_sha256'),loader.get('bootstrap_bytes')],[b.sha(boot),len(boot)],'Bootstrap loader source')
    call=loader.get('installation');require(type(call)is dict,'Missing bootstrap return')
    expected_dll=str((directory/b.DLL).resolve())
    exact([call.get('pid'),call.get('dll'),call.get('bridge_rva'),call.get('bridge_thread_exit_status'),call.get('dll_unloaded'),call.get('test_save_acknowledged')],
          [identity['pid'],expected_dll,hex(manifest['pe']['bridge_start_rva']),'0x0',False,True],'Fixed loaded DLL/entry/normal return')
    require(type(call.get('dll_module_base'))is str and re.fullmatch('0x[0-9a-f]+',call['dll_module_base']) is not None,'Remote DLL base')
    base=int(call['dll_module_base'],16);require(base>=65536 and base%65536==0,'Remote module base bound')
    require(call.get('bridge_remote_address')==hex(base+manifest['pe']['bridge_start_rva']),'Remote entry address binding')
    session=b.no_links(wire.session_path(directory,identity));claims={}
    for sequence in (1,2,3):
        path=session/f'{sequence}.claim'
        if path.exists():
            raw=b.bounded(b.no_links(path),1024);request=b.bounded(b.no_links(session/f'{sequence}.request'),1024)
            require(raw==request,'Permanent claim/request mismatch');decoded=wire.p.decode(raw)
            exact({k:decoded[k] for k in wire.IDENTITY},identity,'Claim file identity');require(decoded['sequence']==sequence,'Claim filename sequence')
            claims[sequence]=raw
    raw=b.bounded(b.no_links(session/'raw-events.jsonl'),trace.MAX_BYTES)
    outer=b.bounded(b.no_links(session/'bootstrap-events.jsonl'),2097152)
    result=validate_stream(raw,outer,identity,claims,complete)
    result.update(identity=identity,loader_sha256=b.sha(b.canonical(loader)),source_manifest_verified=True,
                  source_bound_native_trace_replayed=True,source_bound_not_cryptographic_attestation=True,live_readiness=None,strict_single_player_verified=False,
                  world_epoch_verified=False,production_ready=False,send_supported=False)
    return result
