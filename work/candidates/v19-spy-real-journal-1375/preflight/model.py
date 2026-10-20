"""Proposed no-send event contract; pure offline model, not a native validator.

No v18 native producer exists. Supplied events are assertions, not authenticated
runtime evidence. Object IDs are producer-assigned local ordinals, not pointers.
"""
from copy import deepcopy
import hashlib
import json
import re
import protocol as p

MAX_LOG=256*1024
MAX_LINE=8192
MAX_EVENTS=256
FRA='0x0100007a00415246'
ENG='0x0100002e00474e45'
SENTINEL='0x00000000002d2d2d'
DATE_SENTINEL=43808760
FAMILY_ROWS=(
    ('corrupt_officials',0x337c,'0x1c7c4a8','0x582730'),
    ('sabotage_reputation',0x2ddd,'0x1c7cfd8','0x57e900'),
    ('sow_discontent',0x2ddf,'0x1c7c9e8','0x585020'),
    ('slander_merchants',0x337b,'0x1c7c378','0x580260'),
    ('sabotage_recruitment',0x33bf,'0x1c7c5d8','0x581450'))
STEPS={
    'lifecycle':('factory','clone','destroy_clone','destroy_original'),
    'family_preview':('factory','initialize','full_preview','destroy_original'),
    'owned_command':('factory','initialize','wrap_owned','destroy_original','command_gate','destroy_command')}
SESSION_FIELDS={'pid','creation','session','dll_sha256','manifest_sha256','thread','world_cookie','raw_date'}
COMMON={'event','ordinal','pid','creation','session','dll_sha256','manifest_sha256','thread',
        'world_cookie','raw_date','player_handle','target_handle','uptime_ms','frame','paused','durable','no_send'}
EXTRA={
    'health':{'completed_stages','owned_count'},
    'claim':{'wire_ascii','wire_sha256','claim_created'},
    'case_begin':{'sequence','stage','family'},
    'step_begin':{'sequence','stage','family','step'},
    'step_complete':{'sequence','stage','family','step','exception_code','result'},
    'case_complete':{'sequence','stage','family','owned_count'},
    'stage_complete':{'sequence','stage','case_count','owned_count'},
    'fault':{'reason','exception_code'}}


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
def same(a,b):return canonical(a)==canonical(b)
def exact(value,expected):p.require(same(value,expected),'Exact typed result differs')


def action_fields(family,raw_date=None):
    row=FAMILY_ROWS[p.FAMILIES.index(family)]
    return dict(size=64,vtable_rva=row[2],actor_handle=FRA if raw_date else SENTINEL,
        controller_handle=FRA if raw_date else SENTINEL,target_handle=ENG if raw_date else SENTINEL,
        date_primary=raw_date or DATE_SENTINEL,date_secondary=raw_date or DATE_SENTINEL,
        envoy=-1,state=0,value=True,flag39=False,identifier=0)


class Session:
    def __init__(self,identity):
        p.require(type(identity) is dict and set(identity)==SESSION_FIELDS,'Exact model session')
        probe=dict(purpose=p.PURPOSE,game_sha256=p.GAME_SHA256,profile=p.PROFILE,
            **{k:identity[k] for k in ('pid','creation','session','dll_sha256','manifest_sha256')},
            sequence=1,stage='lifecycle',expires=1,actor='FRA',target='ENG',value=True,state=0,envoy=-1)
        p.encode(probe)
        p.require(p.integer(identity['thread'],1,2**32-1) and p.integer(identity['raw_date'],1,2**31-1)
            and type(identity['world_cookie']) is str and re.fullmatch('0x[1-9a-f][0-9a-f]{0,15}',identity['world_cookie']),
            'Exact model world/thread/date')
        self.identity=deepcopy(identity);self.ordinal=0;self.clock=0;self.frame=0
        self.latest_health=None;self.completed=[];self.pending=None;self.waiting_health=None
        self.family_index=0;self.step_index=0;self.case_active=False;self.call=None
        self.objects={};self.used_ids=set();self.original=None;self.clone=None;self.command=None
        self.fields=None;self.results={'family_preview':{},'owned_command':{}}
        self.terminal=False;self.failure=None

    def common(self,event):
        p.require(type(event) is dict and type(event.get('event')) is str and event['event'] in EXTRA,'Unknown event')
        p.require(set(event)==COMMON|EXTRA[event['event']],'Exact event fields')
        exact({k:event[k] for k in SESSION_FIELDS},self.identity)
        p.require(self.ordinal<MAX_EVENTS and p.integer(event['ordinal'],self.ordinal+1,self.ordinal+1),'Missing/duplicate/out-of-order event')
        p.require(p.integer(event['uptime_ms'],self.clock,p.MAX_UPTIME)
            and p.integer(event['frame'],max(1,self.frame),p.MAX_UPTIME),'Regressed event clock/frame')
        p.require(event['player_handle']==FRA and type(event['player_handle']) is str
            and event['target_handle']==ENG and type(event['target_handle']) is str,'Full country identities differ')
        p.require(event['paused'] is True and event['durable'] is True and event['no_send'] is True,'Unpaused/undurable/send event')
        if event['event']!='health':p.require(event['frame']==self.frame,'Only health may advance frame')
        self.ordinal=event['ordinal'];self.clock=event['uptime_ms'];self.frame=event['frame']

    def binding(self,event):
        p.require(self.pending is not None,'No durable stage claim')
        for key in ('sequence','stage'):exact(event[key],self.pending[key])
        if 'family' in event:exact(event['family'],p.FAMILIES[self.family_index])

    def fresh(self):
        p.require(self.pending is not None and self.clock<self.pending['expires'],'Stage expired before fresh work')

    def allocate(self,ident,kind):
        p.require(p.integer(ident,1,128) and ident not in self.used_ids,'Object ordinal reused or mistyped')
        self.used_ids.add(ident);self.objects[ident]=kind;return ident

    def step_result(self,step,result,family):
        p.require(type(result) is dict,'Exact result object')
        if step=='factory':
            p.require(set(result)=={'object_id','fields'},'Factory fields')
            exact(result['fields'],action_fields(family));self.fields=deepcopy(result['fields'])
            self.original=self.allocate(result['object_id'],'action')
        elif step=='initialize':
            exact(result,dict(object_id=self.original,fields=action_fields(family,self.identity['raw_date'])))
            self.fields=deepcopy(result['fields'])
        elif step=='clone':
            p.require(set(result)=={'object_id','source_id','fields','source_fields'},'Clone fields')
            exact(result['source_id'],self.original);exact(result['source_fields'],self.fields)
            expected=dict(self.fields,date_secondary=self.fields['date_primary'],flag39=False)
            exact(result['fields'],expected);self.clone=self.allocate(result['object_id'],'action_clone')
        elif step=='wrap_owned':
            p.require(set(result)=={'source_id','source_fields','command_id','clone_id','clone_fields','command_size','command_vtable_rva'},'Wrapper fields')
            exact(result['source_id'],self.original);exact(result['source_fields'],self.fields)
            exact(result['clone_fields'],dict(self.fields,date_secondary=self.fields['date_primary'],flag39=False))
            exact(result['command_size'],88);exact(result['command_vtable_rva'],'0x1c814b0')
            self.command=self.allocate(result['command_id'],'command');self.clone=self.allocate(result['clone_id'],'owned_action_clone')
        elif step in ('full_preview','command_gate'):
            p.require(type(result.get('allowed')) is bool,'Legality must be a strict bool, not approval')
            if step=='full_preview':
                expected=dict(object_id=self.original,returned=True,allowed=result['allowed'],
                    route='action_vtable_0x88',function_rva=FAMILY_ROWS[p.FAMILIES.index(family)][3],string_output=None,mode=False)
                self.results['family_preview'][family]=result['allowed']
            else:
                expected=dict(object_id=self.command,returned=True,allowed=result['allowed'],
                    route='command_vtable_0x40',function_rva='0x4e8630')
                self.results['owned_command'][family]=result['allowed']
            exact(result,expected)
        else:
            ident={'destroy_original':self.original,'destroy_clone':self.clone,'destroy_command':self.command}[step]
            expected=dict(object_id=ident,returned=True)
            if step=='destroy_command':expected['owned_clone_id']=self.clone
            exact(result,expected);p.require(ident in self.objects,'Double destruction')
            del self.objects[ident]
            if step=='destroy_command':
                p.require(self.clone in self.objects,'Lost owned clone');del self.objects[self.clone]

    def feed(self,event):
        p.require(not self.terminal,'Session already terminal; never retry or resume')
        try:
            self.common(event);kind=event['event']
            if kind=='fault':
                p.require(event['reason'] in ('pin_mismatch','guard_failed','exception','ownership_unknown','audit_failure')
                    and p.integer(event['exception_code'],0,2**32-1),'Fault shape')
                raise ValueError('Native diagnostic requires terminal stop: '+event['reason'])
            if kind=='health':
                p.require(self.pending is None and not self.case_active and self.call is None and not self.objects,'Health interrupted active ownership')
                exact(event['owned_count'],0);exact(event['completed_stages'],self.completed)
                if self.latest_health is not None:p.require(event['frame']>self.latest_health['frame'],'Health frame not advanced')
                if self.waiting_health is not None:
                    p.require(event['frame']>self.waiting_health,'Need later health after stage completion')
                    self.waiting_health=None
                self.latest_health=deepcopy(event);return
            if kind=='claim':
                p.require(len(self.completed)<3 and self.pending is None and self.latest_health is not None
                    and self.waiting_health is None and not self.objects,'Stage order or health prerequisite missing')
                p.require(self.clock-self.latest_health['uptime_ms']<=2500,'Stale stage health')
                p.require(type(event['wire_ascii']) is str and event['claim_created'] is True,'Missing durable claim')
                raw=event['wire_ascii'].encode('ascii')
                exact(event['wire_sha256'],hashlib.sha256(raw).hexdigest())
                session={k:self.identity[k] for k in ('pid','creation','session','dll_sha256','manifest_sha256')}
                self.pending=p.validate_claim_wire(raw,session,self.clock,p.STAGES[len(self.completed)])
                self.family_index=0;self.step_index=0;return
            self.binding(event)
            if kind=='case_begin':
                p.require(not self.case_active and not self.objects and self.call is None,'Reentrant family')
                self.fresh();self.case_active=True;self.step_index=0
            elif kind in ('step_begin','step_complete'):
                p.require(self.case_active and self.step_index<len(STEPS[self.pending['stage']]),'No next case step')
                step=STEPS[self.pending['stage']][self.step_index];exact(event['step'],step)
                if kind=='step_begin':
                    p.require(self.call is None,'Reentrant call')
                    if not step.startswith('destroy_'):self.fresh()
                    self.call=dict(step=step,frame=self.frame)
                else:
                    p.require(self.call is not None and self.call['step']==step and self.call['frame']==self.frame,'Unpaired return')
                    exact(event['exception_code'],0);self.step_result(step,event['result'],event['family'])
                    self.call=None;self.step_index+=1
            elif kind=='case_complete':
                p.require(self.case_active and self.call is None and not self.objects
                    and self.step_index==len(STEPS[self.pending['stage']]),'Case missing cleanup or steps')
                exact(event['owned_count'],0);self.case_active=False;self.family_index+=1
            elif kind=='stage_complete':
                p.require(not self.case_active and self.call is None and not self.objects and self.family_index==5,'Incomplete five-family matrix')
                exact(event['case_count'],5);exact(event['owned_count'],0)
                self.completed.append(self.pending['stage']);self.pending=None;self.waiting_health=self.frame
        except (ValueError,KeyError,TypeError,IndexError,UnicodeError) as exc:
            self.terminal=True;self.failure=str(exc);raise ValueError(self.failure) from exc

    def finish(self):
        if self.pending is not None or self.waiting_health is not None or self.call is not None or len(self.completed)!=3:
            self.terminal=True;self.failure=self.failure or 'Incomplete no-send stage log'
        return dict(proposed_model_completed=not self.terminal,terminal=self.terminal,failure=self.failure,
            completed_stages=list(self.completed),legality_results=deepcopy(self.results),
            send_supported=False,native_call_authorized=False,native_log_authenticated=False,
            actual_native_log_replayed=False,runtime_verified=False,production_ready=False,
            effects_verified=False,strict_single_player_verified=False,world_epoch_verified=False)


def replay(raw,identity):
    p.require(type(raw) is bytes and 0<len(raw)<=MAX_LOG and raw.endswith(b'\n'),'Bounded complete log bytes')
    lines=raw.splitlines(keepends=True);p.require(len(lines)<=MAX_EVENTS,'Event budget')
    session=Session(identity)
    def unique(pairs):
        out={}
        for k,v in pairs:p.require(k not in out,'Duplicate JSON key');out[k]=v
        return out
    for line in lines:
        p.require(len(line)<=MAX_LINE and line.endswith(b'\n'),'Line bound')
        event=json.loads(line,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite number')))
        session.feed(event)
    return session.finish()
