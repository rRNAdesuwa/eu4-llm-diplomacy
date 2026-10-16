"""Pure synthetic contract checks. No memory reader, process or native calls.

This models ONLY the selected graph and scalar layout; never grants permission
to allocate, preview or execute anything in the game.
"""
import struct
ACTION_VT=0x1c7aef8
RELATION_VT=0x1c7b178
MISSION_VT=0x1c4b2b8
TOKEN=0x3acc
SENTINEL=0x29c77f8
INVALID_HANDLE=0x2d2d2d
MAX_COUNT=4096
def integer(v,lo,hi):
 if type(v) is not int or not lo<=v<=hi:raise ValueError('strict integer')
 return v
def handle(v):
 integer(v,0,2**64-1)
 if not (v>>56) or (v>>32)&0xffff>=MAX_COUNT:raise ValueError('full handle')
 return v
def boolean(v):
 if type(v) is not bool:raise ValueError('strict bool')
 return v
def model_action(actor=None,target=None,date=SENTINEL,value=True):
 """Synthetic semantic fields only; padding is deliberately not constrained."""
 integer(date,-2**31,2**31-1);boolean(value)
 if actor is None and target is None:a=b=INVALID_HANDLE
 else:
  a=handle(actor);b=handle(target)
  if a==b:raise ValueError('same country')
 return {'vtable':ACTION_VT,'size':64,'marker':0x165,'actor':a,'original':a,
         'target':b,'date':date,'last_command_date':date,'envoy':-1,'state':0,
         'value':value,'flag39':False,'id':0}
def model_clone(source):
 clone=dict(source);clone['last_command_date']=source['date'];clone['flag39']=False
 return clone
def select_graph(actor,target,entries,relation,mission,envoys):
 """Validate a proposed raw snapshot's selected outgoing graph, not its truth.

Only the actor's outgoing index is supplied. No reciprocal curry index is
assumed. Unknown vtables are rejected before any derived field access.
"""
 handle(actor);handle(target)
 if actor==target:raise ValueError('same country')
 if type(entries) is not list or len(entries)>MAX_COUNT:raise ValueError('index bound')
 seen=set();hits=[]
 for item in entries:
  if type(item) is not dict or set(item)!={'slot','pointer'}:raise ValueError('entry schema')
  slot=integer(item['slot'],0,MAX_COUNT-1);ptr=integer(item['pointer'],1,2**64-1)
  if slot in seen:raise ValueError('duplicate slot')
  seen.add(slot)
  if slot==(target>>32)&0xffff:hits.append(ptr)
 if not hits:
  if relation is not None or mission is not None:raise ValueError('unindexed graph')
  return {'selected_state':'absent','authorization':False,'effect_verified':False}
 if type(relation) is not dict or relation.get('vtable')!=RELATION_VT or type(relation.get('vtable')) is not int:raise ValueError('unknown relation type')
 keys={'pointer','vtable','marker','actor','target','start','removed','mission'}
 if set(relation)!=keys:raise ValueError('relation schema')
 if integer(relation['pointer'],1,2**64-1)!=hits[0]:raise ValueError('index pointer')
 if integer(relation['marker'],0,2**32-1)!=0x165:raise ValueError('relation marker')
 if handle(relation['actor'])!=actor or handle(relation['target'])!=target:raise ValueError('wrong relation direction')
 integer(relation['start'],-2**31,2**31-1)
 if integer(relation['removed'],0,1)!=0:raise ValueError('removed relation')
 if type(mission) is not dict or type(mission.get('vtable')) is not int or mission.get('vtable')!=MISSION_VT:raise ValueError('unknown mission type')
 keys={'pointer','vtable','actor','target','token','entry','envoy'}
 if set(mission)!=keys:raise ValueError('mission schema')
 if integer(mission['pointer'],1,2**64-1)!=integer(relation['mission'],1,2**64-1):raise ValueError('relation mission link')
 if handle(mission['actor'])!=actor or handle(mission['target'])!=target:raise ValueError('mission direction')
 if integer(mission['token'],0,2**32-1)!=TOKEN:raise ValueError('wrong task token')
 integer(mission['entry'],1,2**64-1);integer(mission['envoy'],0,2**31-1)
 if type(envoys) is not list or len(envoys)>MAX_COUNT:raise ValueError('envoy bound')
 ids=set();pointers=set();matches=[]
 for envoy in envoys:
  if type(envoy) is not dict or set(envoy)!={'pointer','id','status','mission'}:raise ValueError('envoy schema')
  p=integer(envoy['pointer'],1,2**64-1);i=integer(envoy['id'],0,2**31-1)
  integer(envoy['status'],0,255);integer(envoy['mission'],0,2**64-1)
  if p in pointers or i in ids:raise ValueError('duplicate envoy identity')
  ids.add(i);pointers.add(p)
  if p==mission['entry'] or i==mission['envoy'] or envoy['mission']==mission['pointer']:matches.append(envoy)
 if len(matches)!=1:raise ValueError('ambiguous envoy link')
 e=matches[0]
 if e['pointer']!=mission['entry'] or e['id']!=mission['envoy'] or e['mission']!=mission['pointer'] or e['status']!=2:raise ValueError('envoy links/status')
 return {'selected_state':'active_selected_graph','cancel_action_envoy':-1,
         'observed_existing_envoy':e['id'],'authorization':False,'effect_verified':False}

def phase_sequence(start_allowed,stop_allowed):
 """Proposed future two-action experiment, with no native or effect claim."""
 boolean(start_allowed);boolean(stop_allowed)
 return {'order':['initial_selected_census','curry_favors_legality',
                  'curry_favors_submit_if_allowed','wait_dispatch_ownership_and_pause',
                  'advance_under_supervisor_if_cooldown_requires',
                  'stop_currying_favors_fresh_legality','stop_submit_if_allowed',
                  'final_selected_census'],
         'start_dispatch_candidate':start_allowed,'stop_dispatch_candidate':stop_allowed,
         'effect_verified':False,'causality_verified':False,'production_ready':False}
