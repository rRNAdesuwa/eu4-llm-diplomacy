"""Explicit synthetic native-format journal from sealed isolated Host mock.
Flipping mock-origin flags below is TEST DATA ONLY, never an origin proof.
"""
from copy import deepcopy
from itertools import groupby
import json
from fixed import ROOT,wire
from reader import sha
def encode(rows):return b''.join(json.dumps(r,separators=(',',':')).encode()+b'\n' for r in rows)
def fixture(last=18):
    rows=[json.loads(x) for x in (ROOT/'work/candidates/v19-spy-restricted-host-1375/validation-final-r2/build/mock-events.jsonl').read_bytes().splitlines()]
    for row in rows:
        row['mock_environment']=False
        if 'core' in row:row['core']['mock_resolver']=False
    final=deepcopy(rows[-1]);final.pop('result');final.update(event='final_health',ordinal=len(rows)+1,owner_frame=18,host_state=4)
    rows.append(final);rows=[r for r in rows if r.get('frame',r.get('owner_frame'))<=last]
    identity={k:rows[0][k] for k in wire.IDENTITY};owner=rows[0]['thread'];base=rows[0]['image_base']
    common=dict(schema='EU4SPYSENDBOOTSTRAP/1',**identity,game_sha256=wire.GAME_SHA,image_base=base,owner_thread=owner,thread=owner,uptime_ms=10000,
                restricted_research_send=True,strict_sp_verified=False,world_epoch_verified=False,production_ready=False)
    out=[]
    def add(event,**kw):out.append(dict(common,event=event,ordinal=len(out)+1,**kw))
    add('bootstrap_verified',disposable_test_premise=True,native_environment_initialized=True,automatic_stage=False,runtime_verified=False)
    add('install_attempt',detail=dict(event='hook_install_attempt',attempt=1,result=0,prefix_unchanged=False,retrying=False,failure_stage=0,error=0,failure_thread=0,collected=1,suspended=0,resume_failures=0,resume_error=0,resume_thread=0,rip=0,send_supported=False))
    add('hook_installed',frame_rva=0x10a6ec0,prefix_bytes=20,stage_limit=4,fixed_items=5,health_interval_ms=1000,poll_interval_ms=100,hot_unload_supported=False)
    offset=ordinal=claimed=stages=auth=items=0;claims={}
    for frame,group in groupby(rows,key=lambda r:r.get('frame',r.get('owner_frame'))):
        group=list(group);segment=encode(group);seq=next((r['sequence'] for r in group if r['event']=='claim'),4 if frame==7 else 0)
        add('owner_call_begin',owner_entry=frame,controller_frame_before=frame-1,raw_start=offset,raw_first_ordinal=ordinal+1,request_sequence=seq)
        if seq<=3 and seq:
            claims[str(seq)]=bytes.fromhex(next(r['wire_hex'] for r in group if r['event']=='claim'));claimed=stages=seq
        if frame==6:auth=3
        if frame==7:claimed=4;claims['4']=wire.encode_request(identity,'send_batch',70000)
        if frame>=8 and frame%2==0 and frame<18:claims['4.item-'+str((frame-6)//2)]=wire.encode_item(identity,(frame-6)//2,70000)
        if frame>=9 and frame%2==1:items=(frame-7)//2
        state=1 if frame<=6 else 2 if frame==7 or frame%2==1 and frame<17 else 3 if frame<17 else 4
        offset+=len(segment);ordinal+=len(group)
        add('owner_call_return',owner_entry=frame,controller_frame_after=frame,raw_end=offset,raw_last_ordinal=ordinal,raw_segment_sha256=sha(segment),controller_returned=True,input_closed=True,state=state,failure=0,claimed_sequence=claimed,preflight_stages=stages,authenticated_stages=auth,preflight_ready=frame<=6 and frame%2==0,completed_items=items,batch_claimed=frame>=7,success=True)
    if last==18:add('completed_send_batch',owner_entry=18,controller_frame=18,preflight_stages=3,completed_items=5,individual_effect_verified=False)
    return rows,out,identity,claims
