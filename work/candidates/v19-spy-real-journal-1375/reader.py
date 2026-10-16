"""File-only private journal validation. No publisher, process API or execution.

validate_stream authenticates exact byte correspondence, not provenance against
a file forger. Build/loader chain is deliberately a separate mandatory gate.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from fixed import trace,t,wire,require,same,integer,exact
from interval import Interval

COMMON=set('schema event pid creation session game_sha256 dll_sha256 manifest_sha256 image_base owner_thread thread ordinal uptime_ms restricted_research_send strict_sp_verified world_epoch_verified production_ready'.split())
EXTRA={'bootstrap_verified':set('disposable_test_premise native_environment_initialized automatic_stage runtime_verified'.split()),
 'install_attempt':{'detail'},'hook_installed':set('frame_rva prefix_bytes stage_limit fixed_items health_interval_ms poll_interval_ms hot_unload_supported'.split()),
 'owner_call_begin':set('owner_entry controller_frame_before raw_start raw_first_ordinal request_sequence'.split()),
 'owner_call_return':set('owner_entry controller_frame_after raw_end raw_last_ordinal raw_segment_sha256 controller_returned input_closed state failure claimed_sequence preflight_stages authenticated_stages preflight_ready completed_items batch_claimed success'.split()),
 'completed_send_batch':set('owner_entry controller_frame preflight_stages completed_items individual_effect_verified'.split()),
 'terminal':{'owner_entry','unknown_no_retry'}}
DETAIL=set('event attempt result prefix_unchanged retrying failure_stage error failure_thread collected suspended resume_failures resume_error resume_thread rip send_supported'.split())

class Tail(ValueError): pass

def sha(raw):return hashlib.sha256(raw).hexdigest()
def records(raw,limit=1048576,count=512):
    require(type(raw)is bytes and 0<len(raw)<=limit and raw.endswith(b'\n'),'Complete bounded LF journal')
    lines=raw.splitlines(keepends=True);require(len(lines)<=count and all(0<len(x)<=8192 for x in lines),'Row budget')
    def pairs(items):
        d={}
        for k,v in items:require(k not in d,'Duplicate key');d[k]=v
        return d
    rows=[json.loads(x,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite'))) for x in lines]
    require(all(type(x)is dict for x in rows),'Object rows');return rows,lines

def typed_claims(claims,identity):
    require(type(claims)is dict,'Claim map');decoded={}
    for key,raw in claims.items():
        require(type(key)is str and (key in ('1','2','3','4') or key in tuple('4.item-'+str(i) for i in range(1,6))),'Fixed claim names')
        require(type(raw)is bytes and 0<len(raw)<=1024,'Bounded claim bytes')
        if '.item-' not in key:
            d=wire.decode_request(raw);same(d['identity'],identity);same(d['sequence'],int(key));decoded[key]=d
        else:
            require('4' in claims,'Item requires batch claim')
    if '4' in decoded:
        for key,raw in claims.items():
            if '.item-' in key:require(raw==wire.encode_item(identity,int(key[-1]),decoded['4']['expires']),'Exact item wire')
    return decoded

def validate_stream(raw,outer,identity,claims,complete=False):
    require(type(complete)is bool,'Typed complete');identity=wire.identity(identity)
    rows,lines=records(raw);outside,_=records(outer,2097152,1024);requests=typed_claims(claims,identity)
    # Validate all old preflight rows, including unpaired tails; never compact
    # first or borrow a future health frame for an earlier core event.
    split=next((i for i,r in enumerate(rows) if r.get('schema')!='EU4SPYHOST/1'),len(rows))
    pre=rows[:split]; require(pre,'Initial preflight health required')
    for index,row in enumerate(rows,1):integer(row.get('ordinal'),index,index)
    require(all(r.get('schema')=='EU4SPYSENDHOST/1' for r in rows[split:]),'No preflight after send/no foreign schema')
    # A requested stage returns before its later health. A partial view cannot
    # publish; schema and core must still replay. Use the exact prefix ending
    # at last real health only for a readiness proof, and reject unfinished
    # requested work below unless its complete run_result is present.
    last_h=max((i for i,r in enumerate(pre) if r.get('event')=='health'),default=-1)
    require(last_h>=0,'No actual health')
    proof=trace.inspect(pre[:last_h+1],complete=bool(split<len(rows)))
    if last_h+1<len(pre):
        require(pre[-1].get('event')=='run_result','Unfinished preflight operation')
        # Do not fabricate health: replay pending exact core/results directly.
        _validate_preflight_pending(pre,proof)
    owner=image=None;clock=0;phase='bootstrap';attempt=0;installed=False;begin=None
    frame=offset=ordinal=entry=claimed=stages=auth=items=0;ready=False;batch=False;footer=False;terminal=False
    third=None;send=None;ahead=False
    for n,e in enumerate(outside,1):
        event=e.get('event');require(event in EXTRA,'Unknown outer event');exact(e,COMMON|EXTRA[event])
        same({k:e[k] for k in wire.IDENTITY},identity);same(e['schema'],'EU4SPYSENDBOOTSTRAP/1');same(e['game_sha256'],wire.GAME_SHA)
        integer(e['ordinal'],n,n);integer(e['uptime_ms'],clock);clock=e['uptime_ms']
        integer(e['owner_thread'],1,2**32-1);integer(e['thread'],1,2**32-1);t.pointer(e['image_base'])
        if owner is None:owner=e['owner_thread'];image=e['image_base']
        same([e['owner_thread'],e['image_base']],[owner,image])
        require(e['restricted_research_send'] is True and all(e[k] is False for k in ('strict_sp_verified','world_epoch_verified','production_ready')),'Outer research scope')
        require(not footer and not terminal,'No records after terminal/footer')
        if event=='bootstrap_verified':
            require(n==1 and phase=='bootstrap','Unique initial bootstrap');same([e[k] for k in ('disposable_test_premise','native_environment_initialized','automatic_stage','runtime_verified')],[True,True,False,False]);phase='install'
        elif event=='install_attempt':
            require(phase=='install' and not installed,'Install phase');d=e['detail'];exact(d,DETAIL);attempt+=1
            same(d['event'],'hook_install_attempt');integer(d['attempt'],attempt,attempt);require(attempt<=3,'Install retry bound')
            for k in DETAIL-{'event','prefix_unchanged','retrying','send_supported'}:integer(d[k])
            for k in ('prefix_unchanged','retrying','send_supported'):t.boolean(d[k])
            require(d['send_supported'] is False,'Installer no-send');require(all(d[k]==0 for k in ('resume_failures','resume_error','resume_thread')),'Thread restoration')
            require(d['collected']<=512 and d['suspended']<=d['collected'],'Thread count bound')
            if d['result']==0:
                require(d['collected']>=1 and all(d[k]==0 for k in ('failure_stage','error','failure_thread','rip')) and d['prefix_unchanged'] is False and d['retrying'] is False,'Successful install diagnostics');installed=True
            else:require(d['result']==21 and d['prefix_unchanged'] is True and d['retrying'] is True and attempt<3,'Only bounded prepatch retry')
        elif event=='hook_installed':
            require(phase=='install' and installed,'Verified install first');same({k:e[k] for k in EXTRA[event]},dict(frame_rva=0x10a6ec0,prefix_bytes=20,stage_limit=4,fixed_items=5,health_interval_ms=1000,poll_interval_ms=100,hot_unload_supported=False));phase='owner';ready=True
        elif event=='owner_call_begin':
            require(phase=='owner' and begin is None,'Nonoverlapping owner call');same(e['thread'],owner)
            integer(e['owner_entry'],entry+1);same([e['controller_frame_before'],e['raw_start'],e['raw_first_ordinal']],[frame,offset,ordinal+1])
            integer(e['request_sequence'],0,4)
            if e['request_sequence']:require(ready and e['request_sequence']==claimed+1 and claimed<4,'No request without prior independent readiness')
            begin=e;entry=e['owner_entry']
        elif event=='owner_call_return':
            require(begin is not None,'Return needs begin');same(e['thread'],owner);same(e['owner_entry'],entry)
            integer(e['controller_frame_after'],frame+1,frame+1);integer(e['raw_end'],offset+1,1048576);integer(e['raw_last_ordinal'],ordinal+1,512)
            t.digest(e['raw_segment_sha256'])
            if e['raw_end']>len(raw) or e['raw_last_ordinal']>len(rows):
                # The second file may include one health call after the first
                # file snapshot. Only that final exact outer pair can be
                # deferred; its complete raw bytes must appear on next read.
                require(n==len(outside) and begin['request_sequence']==0 and not batch and offset==len(raw) and ordinal==len(rows),'Only final future health pair may be reread')
                same(e['raw_last_ordinal'],ordinal+1)
                same([e['state'],e['failure'],e['claimed_sequence'],e['preflight_stages'],e['authenticated_stages'],e['preflight_ready'],e['completed_items'],e['batch_claimed'],e['controller_returned'],e['input_closed'],e['success']],
                     [1,0,claimed,stages,3 if stages==3 else 0,True,0,False,True,True,True])
                ahead=True;begin=None;continue
            end=e['raw_last_ordinal'];segment=b''.join(lines[ordinal:end]);same([len(segment),sha(segment)],[e['raw_end']-offset,e['raw_segment_sha256']])
            selected=rows[ordinal:end];seq=begin['request_sequence'];frame+=1
            for r in selected:
                same({k:r[k] for k in wire.IDENTITY},identity);same(r['image_base'],image)
                same(r['frame' if r['schema']=='EU4SPYHOST/1' else 'owner_frame'],frame)
                same(r['thread' if r['schema']=='EU4SPYHOST/1' else 'owner_thread'],owner)
                integer(r['uptime_ms'],begin['uptime_ms'],e['uptime_ms'])
            if selected[0]['schema']=='EU4SPYHOST/1':
                require(not batch and selected[0]['event']=='health','Preflight call starts with health')
                if seq:
                    require(seq<=3 and seq==claimed+1 and str(seq) in requests,'Stage request/claim')
                    cs=[r for r in selected if r['event']=='claim'];rs=[r for r in selected if r['event']=='run_result']
                    require(len(cs)==len(rs)==1 and selected[-1]['event']=='run_result','Complete stage in one callback')
                    same(cs[0]['wire_hex'],claims[str(seq)].hex());claimed=stages=seq;ready=False
                else:
                    require(len(selected)==1,'Preflight health-only call');ready=True
                    if stages==3:
                        auth=3
                        if third is None:third=frame
                wanted=1
            else:
                require(auth==3 and third is not None,'Authenticated three-stage proof')
                if send is None:
                    require(seq==4 and '4' in requests,'First send request/claim');send=Interval(identity,image,owner,pre[0]['observed'],third,requests['4'])
                send.begin(frame,begin['uptime_ms'],seq)
                for r in selected:send.feed(r)
                send.end();batch=True;ready=False;claimed=4;items=send.completed
                wanted=5 if send.terminal else {1:2,2:3,3:4}[send.state]
            same([e['state'],e['claimed_sequence'],e['preflight_stages'],e['authenticated_stages'],e['preflight_ready'],e['completed_items'],e['batch_claimed']],
                 [wanted,claimed,stages,auth,ready,items,batch])
            if send and send.terminal:
                same([e['failure'],e['controller_returned'],e['input_closed'],e['success']],[12,False,True,False])
            else:same([e['failure'],e['controller_returned'],e['input_closed'],e['success']],[0,True,True,True])
            offset=e['raw_end'];ordinal=end;begin=None
        elif event=='completed_send_batch':
            require(begin is None and send and send.final_health and items==5,'Extra independent final health required')
            same(e['thread'],owner);same({k:e[k] for k in EXTRA[event]},dict(owner_entry=entry,controller_frame=frame,preflight_stages=3,completed_items=5,individual_effect_verified=False));footer=True
        else:
            require(begin is None and send and send.terminal,'Only complete typed terminal result supported')
            same(e['thread'],owner);same(e['owner_entry'],entry);same(e['unknown_no_retry'],True);terminal=True
    require(phase=='owner','Not installed')
    if ahead:raise Tail('Outer final health pair ahead of raw snapshot')
    if begin is not None or offset!=len(raw) or ordinal!=len(rows):
        # Only a fully validated health-only end may be coherently reread.
        tail=rows[ordinal:]
        require((tail or begin is not None) and all(r.get('event')=='health' for r in tail) and not batch and (begin is None or begin['request_sequence']==0),'Unpaired non-health tail')
        trace.inspect(rows,complete=False)
        raise Tail('Unpaired complete health tail')
    expected={str(i) for i in range(1,claimed+1)}|set('4.item-'+str(i) for i in (send.item_claims if send else []))
    require(set(claims)==expected,'Unbound/missing claim file')
    if complete:require(footer,'Complete footer required')
    require(not(send and send.terminal) or terminal,'Terminal result requires outer terminal')
    next_sequence=claimed+1 if ready and claimed<4 and not terminal else None
    return dict(status='frozen' if terminal else 'complete' if footer else 'ready' if next_sequence else 'in_progress',next_sequence=next_sequence,
                preflight_ready=ready,authenticated_stages=auth,claimed_sequence=claimed,completed_items=items,controller_frames=frame,
                owner_thread=owner,image_base=image,last_owner_uptime_ms=clock,selected_world=deepcopy(pre[0]['observed']),
                last_raw_record=deepcopy(rows[-1]),
                intervals=send.intervals if send else [],completed_outcomes=send.outcomes if send else [0]*5,
                dispatched_count=(send.outcomes.count(5) if send else 0),known_legality_rejected_count=(sum(v in (2,3) for v in send.outcomes) if send else 0),
                terminal_result=send.terminal if send else None,raw_sha256=sha(raw),outer_sha256=sha(outer),
                raw_bytes=len(raw),outer_bytes=len(outer),identity=identity,preflight=proof,
                source_bound_origin_verified=False,build_loader_verified=False,runtime_authorized=False,effect_verified=False,
                strict_sp_verified=False,world_epoch_verified=False,production_ready=False,retry_allowed=False)

def _validate_preflight_pending(pre,proof):
    trace.inspect(pre,complete=False,allow_pending=True)


def coherent(read_pair,identity,claims,complete=False):
    """At most three complete bounded reads. No sleep, trimming, or retries of
    a request/native operation. This function never reads a process."""
    previous=None
    for attempt in range(1,4):
        raw,outer=read_pair()
        if previous:
            oldraw,oldouter=previous
            require(raw.startswith(oldraw) and outer.startswith(oldouter),'Whole byte prefixes must continue')
            new,_=records(raw[len(oldraw):]) if len(raw)>len(oldraw) else ([],[])
            require(all(r.get('schema')=='EU4SPYHOST/1' and r.get('event')=='health' for r in new),'No newly claimed/core work while coherently rereading')
            additions,_=records(outer[len(oldouter):],2097152,1024) if len(outer)>len(oldouter) else ([],[])
            require(all(r.get('event') in ('owner_call_begin','owner_call_return') and (r.get('event')!='owner_call_begin' or type(r.get('request_sequence'))is int and r['request_sequence']==0) for r in additions),'Health-only outer continuation')
        try:
            result=validate_stream(raw,outer,identity,claims,complete);result['coherent_reads']=attempt;return result
        except Tail:
            if attempt==3:raise
            previous=(raw,outer)
    raise AssertionError('Bounded loop')
