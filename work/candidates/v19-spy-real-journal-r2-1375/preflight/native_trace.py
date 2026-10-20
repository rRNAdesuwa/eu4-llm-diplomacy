"""Strict native-origin Host reducer. Authentication is in real_capture.py.
This module never promotes caller-supplied rows into source provenance.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import types

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PROJECTION=HERE/'native_projection.py'
PROJECTION_SHA='33694272877980abab447b656a9cf7eeb877a5b406cd80fadef0cade18fc11c5'
MAX_BYTES=1048576
MAX_LINES=512
MAX_LINE=8192


def require(ok,why):
    if not ok:raise ValueError(why)


def bounded(path,limit):
    with Path(path).open('rb') as stream:raw=stream.read(limit+1)
    require(len(raw)<=limit,'Hard read byte budget')
    return raw


def load_projection():
    raw=bounded(PROJECTION,32768)
    require(hashlib.sha256(raw).hexdigest()==PROJECTION_SHA,'Sealed R2 projection changed')
    module=types.ModuleType('_restricted_host_projection_r2');module.__file__=str(PROJECTION)
    exec(compile(raw,str(PROJECTION),'exec'),module.__dict__)
    return module


x=load_projection()
COMMON={'event','schema','pid','creation','session','game_sha256','dll_sha256','manifest_sha256','ordinal','frame','uptime_ms','thread',
        'mock_environment','send_supported','strict_sp_verified','epoch_verified','production_ready','observed','current_observation_verified','image_base'}
EXTRA={'health':{'claimed_sequence','completed_stages','owner_hook_installed','loader_implemented','runtime_verified'},
       'claim':{'sequence','stage','expires','wire_hex','claim_created_and_flushed'},
       'core_event':{'sequence','expires','allocation_link','core'},
       'run_result':{'claimed_sequence','completed_stages','owner_hook_installed','loader_implemented','runtime_verified','result'}}
ROOT_FIELDS={'game','database','countries','actor_country','target_country','server','pause_manager'}
OBSERVED=ROOT_FIELDS|{'actor','target','player','raw_date','country_count','actor_overlord','target_overlord','effective_player',
                    'manual_pause','reset','ironman','selector','alternate_selector','speed_index','multiplayer_classifier','load_source'}


def read_records(path):
    raw=bounded(path,MAX_BYTES)
    require(raw and raw.endswith(b'\n'),'Complete journal')
    lines=raw.splitlines(keepends=True)
    require(0<len(lines)<=MAX_LINES and all(0<len(line)<=MAX_LINE for line in lines),'Journal line budget')
    def unique(pairs):
        out={}
        for key,value in pairs:
            require(key not in out,'Duplicate key');out[key]=value
        return out
    return [json.loads(line,object_pairs_hook=unique,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite'))) for line in lines]


def inspect(records,complete=True,allow_pending=False):
    require(type(records)is list and 0<len(records)<=MAX_LINES,'Bounded record list')
    projected=[];pending_health=None;last_health=None;need_post=False;identity=None;locked=None;clock=0;frame=0;claimed=0;completed=0;request=None;image_base=None
    for index,row in enumerate(records,1):
        require(type(row)is dict and row.get('event') in EXTRA,'Fault/unknown/incomplete Host trace cannot pass')
        require(set(row)==COMMON|EXTRA[row['event']],'Exact Host record shape')
        require(row['mock_environment'] is False,'Native environment flag required')
        require(row['schema']=='EU4SPYHOST/1' and row['game_sha256']==x.p.GAME_SHA256,'Wrong private Host schema/build')
        require(all(row[k] is False for k in ('send_supported','strict_sp_verified','epoch_verified','production_ready'))
                and row['current_observation_verified'] is True,'Non-current/permission claims')
        require(x.integer(row['ordinal'],index,index) and x.integer(row['uptime_ms'],clock) and x.integer(row['frame'],max(1,frame)),'Host event ordering')
        clock=row['uptime_ms'];frame=row['frame'];o=row['observed']
        require(x.integer(row['image_base'],65536,2**47-1) and row['image_base']%8==0,'Image base')
        if image_base is None:image_base=row['image_base']
        x.exact(row['image_base'],image_base,'Image base changed')
        require(type(o)is dict and set(o)==OBSERVED,'Complete selected-root envelope')
        require(all(x.integer(o[k],65536,2**47-1) and o[k]%8==0 for k in ROOT_FIELDS),'Root pointer type/range')
        require(all(x.integer(o[k]) for k in OBSERVED-ROOT_FIELDS-{'multiplayer_classifier'}),'Strict observed scalar types')
        require(123<=o['country_count']<=4096 and o['actor_country']!=o['target_country']
                and all(o[k]==int(x.model.FRA,16) for k in ('actor','player','effective_player'))
                and o['target']==int(x.model.ENG,16) and o['actor_overlord']>>56==0 and o['target_overlord']>>56==0
                and 1<=o['raw_date']<=2**31-1 and o['manual_pause']==1 and o['reset']==o['ironman']==o['load_source']==0
                and 0<=o['speed_index']<=4 and o['selector']<=255 and o['alternate_selector']<=255
                and o['multiplayer_classifier'] is False,'Selected paused/FRA/independent-target profile')
        ident={k:row[k] for k in ('pid','creation','session','dll_sha256','manifest_sha256','thread')}
        ident.update(world_cookie=hex(o['game']),raw_date=o['raw_date'])
        if identity is None:identity=ident;locked=deepcopy(o)
        x.exact(ident,identity,'Foreign Host identity');x.exact(o,locked,'Changed selected roots/profile')
        common=dict(identity,frame=frame,uptime_ms=clock,player_handle=x.model.FRA,target_handle=x.model.ENG,paused=True,durable=True,no_send=True)
        event=row['event']
        if event in ('health','run_result'):
            require(all(row[k] is False for k in ('owner_hook_installed','loader_implemented','runtime_verified')),'Unsupported runtime claim')
            require(x.integer(row['claimed_sequence'],claimed,claimed) and x.integer(row['completed_stages'],completed,completed),'Host completed counters')
        if event=='health':
            pending_health=dict(origin='source_bound_native',kind='host',event=dict(common,event='health',completed_stages=list(x.p.STAGES[:completed]),owned_count=0))
            if not projected or need_post:
                projected.append(pending_health);last_health=pending_health;need_post=False
        elif event=='claim':
            require(pending_health is not None,'Claim lacks preceding actual health')
            if pending_health is not last_health:
                projected.append(pending_health);last_health=pending_health
            require(row['claim_created_and_flushed'] is True and type(row['wire_hex'])is str and len(row['wire_hex'])<=2048,'Claim receipt')
            raw=bytes.fromhex(row['wire_hex']);require(raw.hex()==row['wire_hex'],'Canonical wire hex')
            request=x.p.validate_claim_wire(raw,{k:identity[k] for k in ('pid','creation','session','dll_sha256','manifest_sha256')},clock,x.p.STAGES[claimed])
            require(x.integer(row['sequence'],claimed+1,claimed+1) and row['stage']==request['stage'] and type(row['stage'])is str
                    and x.integer(row['expires'],request['expires'],request['expires']),'Claim metadata differs')
            claimed+=1;projected.append(dict(origin='source_bound_native',kind='host',event=dict(common,event='claim',wire_ascii=raw.decode('ascii'),wire_sha256=hashlib.sha256(raw).hexdigest(),claim_created=True)))
        else:
            require(request is not None,'Missing prior claim')
            env=dict(common,image_base=image_base)
            if event=='core_event':
                require(x.integer(row['sequence'],claimed,claimed) and x.integer(row['expires'],request['expires'],request['expires'])
                        and row['allocation_link']=='pinned_core_control_flow_only','Private core binding')
                projected.append(dict(origin='source_bound_native',kind='core',envelope=env,event=deepcopy(row['core'])))
            else:
                projected.append(dict(origin='source_bound_native',kind='result',envelope=env,result=deepcopy(row['result'])));completed+=1;need_post=True
    require((records[-1]['event']=='health' and not need_post) or (allow_pending is True and complete is False and records[-1]['event']=='run_result' and need_post),'Independent health or explicitly non-ready complete result required')
    if pending_health is not last_health and not need_post:
        projected.append(pending_health)
    reducer=x.Projection(identity)
    for row in projected:reducer.feed(row)
    require(reducer.stage is None and reducer.wait_result is None,'Unfinished semantic operation')
    if complete:
        output,result=reducer.finish()
        require(result['proposed_model_completed'] is True,'All three stages and later health required')
    else:
        output=b''.join(reducer.output)
        result={'output_events':len(reducer.output),'legality_results':None}
        reducer.closed=True # Partial status is a one-shot view, never a resumable proof.

    return dict(native_trace_model_checked=True,completed_stages=completed,complete_contract=bool(complete),input_records=len(records),model_events=result['output_events'],
                projected_sha256=hashlib.sha256(output).hexdigest(),legality_results=result['legality_results'],
                actual_host_authenticated=False,actual_native_log_replayed=False,owner_hook_installed=False,
                runtime_verified=False,strict_single_player_verified=False,world_epoch_verified=False,production_ready=False,send_supported=False)


