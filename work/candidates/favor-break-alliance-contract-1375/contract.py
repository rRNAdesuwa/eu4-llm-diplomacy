"""Offline conservative request/ownership model; no memory or engine adapter."""
from dataclasses import dataclass,replace
def integer(x,lo,hi):
 if type(x) is not int or not lo<=x<=hi:raise ValueError('integer domain')
 return x
def country(x):
 integer(x,1,(1<<64)-1)
 if not (x>>56) or ((x>>32)&0xffff)>=4096 or x&0xffffff==0x2d2d2d:raise ValueError('full handle required')
 return x
@dataclass(frozen=True)
class Action:
 actor:int;current_actor:int;recipient:int;third_party:int;primary_date:int;secondary_date:int
 envoy:int=-1;state:int=0;value:bool=True;flag:int=0;identifier:int=0
def request(actor,recipient,third,date,*,value=True,state=0):
 handles=[country(x) for x in (actor,recipient,third)]
 if len(set(handles))!=3 or len({(x>>32)&0xffff for x in handles})!=3:raise ValueError('distinct live roles')
 integer(date,0,0x7fffffff)
 if value is not True or type(state) is not int or state!=0:raise ValueError('only normal pending proposal, no cancel/force')
 return Action(actor,actor,recipient,third,date,date)
def clone(a):
 if type(a) is not Action:raise ValueError('action type')
 return replace(a,secondary_date=a.primary_date,flag=0)
def wrapped_clone(a,current_date):
 integer(current_date,0,0x7fffffff)
 return replace(clone(a),secondary_date=current_date)
def selected_readonly_predicates(now,entries,favors_milli,cost_units,opinion,required_opinion,allied_actor,actor_war,recipient_war):
 """Necessary selected fields only; even True never means full native permission."""
 integer(now,0,0x7fffffff);integer(favors_milli,0,100000);integer(cost_units,0,2147483)
 integer(opinion,-32768,32767);integer(required_opinion,-32768,32767)
 if type(entries) is not list or len(entries)>256:raise ValueError('bounded cooldown vector')
 if any(type(b) is not bool for b in (allied_actor,actor_war,recipient_war)):raise ValueError('typed flags')
 seen=set();blocked=False
 for row in entries:
  if type(row) is not tuple or len(row)!=2:raise ValueError('token/expiry row')
  token,expiry=row;integer(token,0,0xffffffff);integer(expiry,0,0x7fffffff)
  if token in seen:raise ValueError('duplicate cooldown token ambiguity')
  seen.add(token);blocked|=token==0x3bcb and expiry>now
 return {'selected_pass':not blocked and allied_actor and not actor_war and not recipient_war and favors_milli>=cost_units*1000 and opinion>=required_opinion,'full_permission':None,'construct_authorized':False}
def effect_classification(native_state):
 integer(native_state,0,2)
 return ('pending_no_acceptance_effect','rejected_response_effects','accepted_multirelation_effects')[native_state]
class Ownership:
 def __init__(self):self.original=True;self.command=False;self.clone=False;self.frozen=False
 def wrap(self):
  if self.frozen or not self.original or self.command:raise ValueError('wrap stage')
  self.command=True;self.clone=True
 def destroy_original(self):
  if self.frozen or not self.original:raise ValueError('original ownership')
  self.original=False
 def destroy_command(self):
  if self.frozen or not self.command:raise ValueError('command ownership')
  self.command=False;self.clone=False
 def exception(self):self.frozen=True
