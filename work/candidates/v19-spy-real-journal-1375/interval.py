"""Independent source-bound interval reducer. Never invents an entry timestamp.

Normal Core returns prove entry and return. The final before_work barrier is
source evidence for pre-expiry entry, not a measured point in this journal.
No events are fed to the sealed point-timestamp model.
"""
from copy import deepcopy
from fixed import t, require, same, integer, exact

BASE=set('game database countries actor_country target_country server pause_manager actor target player date'.split())
EXT=set(t.STAMP_PTR+t.STAMP_U+['date','native_speed_index'])-BASE
COMMON=set('schema event ordinal owner_frame uptime_ms sequence pid creation session game_sha256 dll_sha256 manifest_sha256 owner_thread mock_environment image_base world proof_source third_stage_health_frame host_state host_failure operation expires runtime_verified effect_verified strict_sp_verified epoch_verified production_ready'.split())
PERMS='runtime_verified effect_verified strict_sp_verified epoch_verified production_ready'.split()

class Interval:
    def __init__(self, identity, image, thread, observed, third_health, claim):
        self.identity=dict(identity); self.image=image; self.thread=thread; self.world={k:observed['raw_date' if k=='date' else k] for k in BASE}
        self.observed=observed; self.third=third_health; self.claim=claim
        self.state=0; self.completed=0; self.current=t.zero_item();self.outcomes=[0]*5
        self.next_id=0;self.frame=third_health;self.now=0;self.pending=None;self.next=None
        self.op=None; self.locked=None;self.intervals=[];self.results=[];self.item_claims=[]
        self.fault=None;self.final_health=False;self.terminal=None

    def fields(self, initialized):
        f={k:0 for k in t.FIELD_U+t.FIELD_I}
        f.update(vtable=self.image+t.VTS[self.current['family']],marker=0x165,
                 actor=t.FRA if initialized else 0x2d2d2d,controller=t.FRA if initialized else 0x2d2d2d,
                 target=t.ENG if initialized else 0x2d2d2d,primary_date=self.world['date'] if initialized else 43808760,
                 secondary_date=self.world['date'] if initialized else 43808760,envoy=-1,value=1)
        return f

    def begin(self, frame, begin_time, request_sequence):
        require(self.op is None and self.terminal is None and not self.final_health,'No overlapping/terminal operation')
        integer(frame,self.frame+1,self.frame+1);integer(begin_time,self.now)
        self.frame=frame;self.now=begin_time;self.call_start=begin_time; self.pending=None;self.next=None
        self.op=1 if self.state==0 else 2 if self.state==1 else 3 if self.state==2 else 0
        self.host_state={0:1,1:2,2:3,3:4}[self.state]
        same(request_sequence,4 if self.op==1 else 0)
        if self.op in (1,2): require(begin_time<self.claim['expires'],'Work begins after expiry')

    def feed(self, row):
        event=row.get('event'); extra={'send_core':{'core'},'operation_result':{'result'},'terminal_result':{'result'},'final_health':set()}
        require(event in extra,'Known send event');exact(row,COMMON|extra[event])
        same({k:row[k] for k in self.identity},self.identity)
        same([row['schema'],row['sequence'],row['owner_thread'],row['image_base']],['EU4SPYSENDHOST/1',4,self.thread,self.image])
        same(row['game_sha256'],t.model.GAME)
        same(row['world'],self.world);same(row['third_stage_health_frame'],self.third)
        same(row['proof_source'],'same_controller_typed_run_result_and_later_health')
        require(row['mock_environment'] is False and all(row[k] is False for k in PERMS),'Native source profile/no grants')
        same(row['owner_frame'],self.frame); integer(row['uptime_ms'],self.now); self.now=row['uptime_ms']
        same(row['expires'],self.claim['expires'])
        host_state=self.host_state
        if event=='terminal_result' or event=='send_core' and row['core'].get('kind')==8:
            same(row['host_failure'],12);same(row['host_state'],host_state)
        else:
            same(row['host_state'],host_state);same(row['host_failure'],0)
        same(row['operation'],self.op if self.op else 3)
        if event=='send_core':self.core(row['core'])
        elif event in ('operation_result','terminal_result'):self.result(row['result'],event=='terminal_result')
        else:
            require(self.op==0 and self.state==3,'Final health only after five complete items');self.final_health=True;self.next='done'

    def core(self,e):
        exact(e,set(t.EVENT_U+t.EVENT_B+['identity','stamp','item'])|EXT)
        for key in t.EVENT_U:integer(e[key])
        for key in t.EVENT_B:t.boolean(e[key])
        require(e['mock_resolver'] is False and all(e[k] is False for k in t.EVENT_B if k!='mock_resolver'),'Native core/no grants')
        expected=dict(self.identity);expected['creation_filetime']=int(expected.pop('creation'),16)
        t.identity(e['identity']);same(e['identity'],expected)
        exact(e['stamp'],BASE);same(e['stamp'],self.world)
        full=dict(e['stamp'],**{k:e[k] for k in EXT});t.stamp(full)
        for key in ('actor_overlord','target_overlord','effective_player','country_count'):same(e[key],self.observed[key])
        same(e['native_speed_index'],self.observed['speed_index'])
        if self.locked is None:self.locked=deepcopy(full)
        else:same(full,self.locked)
        same([e['operation'],e['request_sequence'],e['completed'],e['frame'],e['expires_uptime_ms']],
             [self.op,4,self.completed,self.frame,self.claim['expires']])
        integer(e['uptime_ms'],max(self.call_start,self.core_time if hasattr(self,'core_time') else 0),self.now);self.core_time=e['uptime_ms']
        t.item(e['item']);integer(e['kind'],0,8);integer(e['reason'],0,18);integer(e['exception_code'],0,2**32-1)
        if e['kind']==8:
            require(e['reason']!=0 and e['state']==4 and self.fault is None,'Typed terminal fault')
            self.fault=deepcopy(e);return
        require(self.fault is None and e['reason']==e['exception_code']==0,'No continuation after fault')
        same(e['state'],self.state)
        self.transition(e)
        same(e['item'],self.current)
        if hasattr(self,'after_health'):self.current=self.after_health;del self.after_health

    def transition(self,e):
        k=e['kind']; got=e['item']; at=e['uptime_ms']
        if k in (0,1):
            require(self.next is None and self.op==(1 if k==0 else 2),'Single claim/start order')
            require(at<self.claim['expires'],'Durable claim expiry')
            if k==0:require(self.claim['expires']-at<=60000,'Batch maximum TTL')
            if k==0:self.current['step']=1;self.next='returned'
            else:
                self.current=t.zero_item();self.current.update(ordinal=self.completed+1,family=self.completed,token=t.TOKENS[self.completed],owner_frame=self.frame,outcome=1,step=2,current=True,claimed=True)
                self.item_claims.append(self.completed+1);self.next=3
            return
        if k==2:
            step=got['step'];require(self.pending is None and step==self.next,'Ordered unique intent')
            if step not in (8,9):require(at<self.claim['expires'],'Work intent expiry')
            self.current.update(step=step,call_entered=False,call_returned=False)
            if step in (8,9):
                if not self.current['preview_allowed']:self.current['outcome']=2
                elif not self.current['gate_allowed']:self.current['outcome']=3
            self.pending=step;self.intent_time=at;return
        if k==4:
            require(self.pending==10,'Submit intent before durable dispatch intent');require(at<self.claim['expires'],'Dispatch intent expiry')
            self.pending='dispatch';self.intent_time=at;return
        if k==3:
            step=got['step'];require(self.pending==('dispatch' if step==10 else step),'Return requires intent')
            if step!=4:self.intervals.append(dict(family=self.current['family'],step=step,owner_frame=self.frame,intent_uptime=self.intent_time,return_observed_uptime=at,entry_uptime=None,entered=True,returned=True,source_last_before_work_barrier=step not in (8,9)))
            self.current.update(call_entered=step!=4,call_returned=step!=4)
            if step==3:
                self.next_id+=1;self.current.update(original_id=self.next_id,has_local_original=True,original_fields=self.fields(False));self.next=4
            elif step==4:self.current['original_fields']=self.fields(True);self.next=5
            elif step==5:self.current.update(preview_observed=True,preview_allowed=got['preview_allowed']);self.next=6 if got['preview_allowed'] else 8
            elif step==6:
                self.current.update(command_id=self.next_id+1,clone_id=self.next_id+2,has_local_command=True,has_local_clone=True,clone_fields=self.fields(True));self.next_id+=2;self.next=7
            elif step==7:self.current.update(gate_observed=True,gate_allowed=got['gate_allowed']);self.next=8 if got['gate_allowed'] else 9
            elif step==9:self.current.update(command_destroyed=True,clone_destroyed=True,has_local_command=False,has_local_clone=False);self.next=8
            elif step==8:self.current.update(original_destroyed=True,has_local_original=False);self.next=10 if self.current['gate_allowed'] else 'item_return'
            elif step==10:
                self.current.update(submit_entered=True,submit_returned=True,submit_value_observed=True,slot_observed=True,submit_value=got['submit_value'],slot_consumed=got['slot_consumed'],has_local_command=False,has_local_clone=False,outcome=4);self.next='item_return'
            else:raise ValueError('Unknown return')
            self.pending=None;return
        if k==5:
            require(self.pending is None and self.next=='item_return','Complete item path')
            if self.current['outcome']==4:
                require(self.current['submit_value'] is True and self.current['slot_consumed'] is True,'Unknown transfer cannot complete')
                self.current['outcome']=5
            require(self.current['outcome'] in (2,3,5),'Only known outcome')
            self.next='returned';return
        if k==6:
            require(self.op==3 and self.next is None and self.current['current'] is True,'Later distinct owner health')
            same(got,self.current);self.outcomes[self.completed]=self.current['outcome'];self.completed+=1
            self.state=3 if self.completed==5 else 1;self.next='batch_complete' if self.completed==5 else 'returned'
            self.after_health=deepcopy(self.current);self.after_health['current']=False;return
        if k==7:
            require(self.op==3 and self.completed==5 and self.next=='batch_complete','Final batch completion');self.next='returned';return
        raise ValueError('Unsupported core kind')

    def result(self, raw, terminal):
        r=deepcopy(raw);outcomes=r.pop('completed_outcomes',None)
        value=t.typed_result(dict(result=r,completed_outcomes=outcomes))
        require(self.next!='done','Duplicate result')
        if terminal:
            require(r['state']==4 and r['freeze_session'] is True and (r['reason']!=0 or r['exception_code']!=0),'Terminal must freeze')
            if self.fault:same(r['current_item'],self.fault['item']);same(r['reason'],self.fault['reason']);same(r['exception_code'],self.fault['exception_code'])
            same(outcomes,self.outcomes);same(r['completed'],self.completed)
            self.terminal=value;self.next='done';return
        require(self.fault is None and self.pending is None and self.next=='returned','Missing return/completion')
        for key in t.RESULT_B: same(r[key],key in ('accepted_call','audit_complete'))
        same([r['reason'],r['exception_code']],[0,0]);integer(r['read_calls'],1,8192)
        if self.op==1:self.state=1
        elif self.op==2:self.state=2
        same([r['state'],r['completed']],[self.state,self.completed]);same(r['current_item'],self.current);same(outcomes,self.outcomes)
        self.results.append(value);self.next='done'

    def end(self):
        require(self.next=='done','Missing complete Core Result or final health');self.op=None
