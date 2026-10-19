"""Bounded assertions over our isolated mock serializer, never a live verifier."""
import json
from pathlib import Path

def read(path, maximum=1048576):
    with Path(path).open('rb') as f:raw=f.read(maximum+1)
    if len(raw)>maximum:raise ValueError('capture budget')
    return raw

def require(ok, message):
    if not ok:raise ValueError(message)

def verify(path):
    raw=read(path);require(raw.endswith(b'\n'),'complete lines')
    lines=raw.splitlines();require(len(lines)<=512,'row limit')
    rows=[]
    for line in lines:
        require(0<len(line)<=8191,'line limit')
        row=json.loads(line);require(type(row)is dict,'object')
        rows.append(row)
    preflight=[r for r in rows if r.get('schema')=='EU4SPYHOST/1']
    sent=[r for r in rows if r.get('schema')=='EU4SPYSENDHOST/1']
    require(len(preflight)+len(sent)==len(rows),'known schemas')
    results=[r for r in preflight if r.get('event')=='run_result']
    require(len(results)==3,'three actual preflight result captures')
    for i,r in enumerate(results,1):
        value=r['result'];require(value['stage']==i and value['cases_complete']==5 and value['completed'] is True and value['audit_complete'] is True,'stage result')
        require(value['freeze_session'] is False and value['ownership_uncertain'] is False and value['exception_code']==0,'known cleanup')
        require(value['allowed_observed']==([False]*5 if i==1 else [True]*5),'original observed fields')
        require(value['allowed']==([False]*5 if i==1 else [True]*5),'all-true captured scenario')
        require(r['send_supported'] is False and r['production_ready'] is False,'old false fields not relabeled')
    require(sent,'new send records')
    last_ordinal=0;last_frame=0
    for r in sent:
        require(r['mock_environment'] is True,'only mock capture')
        require(type(r['ordinal'])is int and r['ordinal']>last_ordinal,'ordinal');last_ordinal=r['ordinal']
        require(type(r['owner_frame'])is int and r['owner_frame']>=last_frame,'frame');last_frame=r['owner_frame']
        require(r['sequence']==4 and r['pid']==1234 and r['creation']=='0000000000000001','fixed synthetic scope')
        require(r['third_stage_health_frame']<r['owner_frame'],'independent preflight boundary')
        for key in ('runtime_verified','effect_verified','strict_sp_verified','epoch_verified','production_ready'):require(r[key] is False,'no runtime promotion')
        if r['event']=='send_core':
            c=r['core'];require(c['request_sequence']==4 and c['frame']==r['owner_frame'] and c['identity']['pid']==r['pid'],'complete typed core identity')
            require(c['identity']['creation_filetime']==1 and c['identity']['session']==r['session'],'core creation/session')
            require(c['mock_resolver'] is True,'mock core')
            for key in ('production_ready','strict_sp_verified','epoch_verified','effect_verified'):require(c[key] is False,'core permissions')
            for key in ('claimed','call_entered','call_returned','preview_observed','preview_allowed','gate_observed','gate_allowed','original_destroyed','command_destroyed','clone_destroyed','submit_entered','submit_returned','submit_value_observed','submit_value','slot_observed','slot_consumed','has_local_original','has_local_command','has_local_clone','current'):
                require(type(c['item'][key])is bool,'bool preserved '+key)
    core=[r['core'] for r in sent if r['event']=='send_core']
    require(sum(c['kind']==4 for c in core)==5,'five durable dispatch intents')
    require(sum(c['kind']==5 for c in core)==5,'five item returns')
    require(sum(c['kind']==6 for c in core)==5,'five later health records')
    endings=[r for r in sent if r['event']=='operation_result'];require(len(endings)==11,'begin and five item/health pairs')
    require([r['operation'] for r in endings]==[1]+[2,3]*5,'actual invoke order')
    previous=0
    for i,r in enumerate(endings):
        v=r['result'];require(v['accepted_call'] is True and v['audit_complete'] is True and v['freeze_session'] is False,'result acknowledgement')
        require(r['owner_frame']>previous,'separate actual callbacks');previous=r['owner_frame']
        require(v['completed']==i//2,'only later health completes item')
        if i and i%2:
            x=v['current_item'];require(x['submit_entered'] is True and x['submit_returned'] is True and x['slot_observed'] is True and x['slot_consumed'] is True and x['outcome']==5,'dispatched only')
            require(x['has_local_command'] is False and x['has_local_clone'] is False,'no transferred ownership')
    require(endings[-1]['result']['completed_outcomes']==[5]*5,'all five dispatched in mock')
    return {'mock_capture_verified':True,'rows':len(rows),'bytes':len(raw),'preflight_records':len(preflight),'send_records':len(sent),'actual_log_verified':False}
