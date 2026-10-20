"""Strict offline byte-layout/ownership model. Never an engine adapter or verifier."""
from dataclasses import dataclass
import struct

PROFILES={
 'claim_throne':{'size':0x40,'vt':0x1c7ebc0,'token':0x2949,'reply':False,'params':()},
 'sell_province':{'size':0x48,'vt':0x1c7e498,'token':0x2a29,'reply':True,'params':('price_integer','province_id')},
 'enforce_peace':{'size':0x48,'vt':0x1c7de98,'token':0x2dda,'reply':True,'params':('opposing_country',)},
 'threaten_war':{'size':0x50,'vt':0x1c7ee60,'token':0x3307,'reply':True,'params':('province_id','taker_country')},
}
INVALID_HANDLE=0x2d2d2d
DEFAULT_DATE=0x29c77f8

def require(x,msg):
 if not x:raise ValueError(msg)

def integer(x,low,high):
 require(type(x) is int and low<=x<=high,'strict bounded integer');return x

def profile(name):
 require(type(name) is str and name in PROFILES,'unreviewed family');return PROFILES[name]

def put(buf,off,fmt,x):struct.pack_into('<'+fmt,buf,off,x)
def get(buf,off,fmt):return struct.unpack_from('<'+fmt,buf,off)[0]

def factory(name):
 p=profile(name);b=bytearray(p['size'])
 put(b,0,'Q',0x140000000+p['vt']);put(b,8,'I',0x165)
 for off in (0x10,0x18,0x20):put(b,off,'Q',INVALID_HANDLE)
 for off in (0x28,0x2c):put(b,off,'i',DEFAULT_DATE)
 put(b,0x30,'i',-1);b[0x38]=1
 if name=='sell_province':put(b,0x40,'i',-1);put(b,0x44,'i',-1)
 elif name=='enforce_peace':put(b,0x40,'Q',INVALID_HANDLE)
 elif name=='threaten_war':put(b,0x40,'i',-1);put(b,0x44,'Q',INVALID_HANDLE)
 return b

def country(handle,live_full_handles):
 # A supplied mock mapping represents a previously authenticated full identity.
 # It neither reads a live table nor certifies any actual generation/world.
 integer(handle,1,2**64-1)
 require(type(live_full_handles) is dict,'mock full-handle table')
 for slot,value in live_full_handles.items():
  integer(slot,1,4095);integer(value,1,2**64-1)
  require((value>>32)&0xffff==slot,'mock slot binding')
 slot=(handle>>32)&0xffff
 require(handle!=INVALID_HANDLE and live_full_handles.get(slot)==handle,'full handle identity')
 return handle

def initialize(name,actor,target,date,params,live_full_handles,*,value=True):
 p=profile(name);require(value is True,'no reviewed false/cancel caller')
 require(type(params) is dict and set(params)==set(p['params']),'exact parameter schema')
 country(actor,live_full_handles);country(target,live_full_handles);require(actor!=target,'pair identity')
 integer(date,1,2**31-1);b=factory(name)
 for off,h in ((0x10,actor),(0x18,actor),(0x20,target)):put(b,off,'Q',h)
 for off in (0x28,0x2c):put(b,off,'i',date)
 if name=='sell_province':
  # Conservative model range avoids the observed signed32 x1000 overflow.
  # Native permits/scoring may impose further conditions; this is not its complete range.
  put(b,0x40,'i',integer(params['price_integer'],0,(2**31-1)//1000))
  put(b,0x44,'i',integer(params['province_id'],1,2**31-1))
 elif name=='enforce_peace':
  h=country(params['opposing_country'],live_full_handles)
  require(h not in (actor,target),'restricted three-country profile');put(b,0x40,'Q',h)
 elif name=='threaten_war':
  put(b,0x40,'i',integer(params['province_id'],1,2**31-1))
  h=country(params['taker_country'],live_full_handles)
  require(h==actor,'only normal AI taker=actor closed');put(b,0x44,'Q',h)
 return b

def layout(name,b):
 p=profile(name);require(type(b) is bytearray and len(b)==p['size'],'exact action buffer')
 require(get(b,0,'Q')==0x140000000+p['vt'] and get(b,8,'I')==0x165,'typed action')

def clone(name,b):
 layout(name,b);out=factory(name)
 for off,fmt in ((0x10,'Q'),(0x18,'Q'),(0x20,'Q'),(0x28,'i'),(0x30,'i'),(0x34,'i'),(0x38,'B'),(0x3c,'I')):
  put(out,off,fmt,get(b,off,fmt))
 put(out,0x2c,'i',get(b,0x28,'i'));out[0x39]=0
 if name=='sell_province':out[0x40:0x48]=b[0x40:0x48]
 elif name=='enforce_peace':put(out,0x40,'Q',get(b,0x40,'Q'))
 elif name=='threaten_war':out[0x40:0x4c]=b[0x40:0x4c]
 return out

def serialized_parameters(name,b):
 layout(name,b)
 if name=='claim_throne':return {}
 if name=='sell_province':return {0x1a1:get(b,0x40,'i'),0x2843:get(b,0x44,'i')}
 if name=='enforce_peace':return {0x2dda:get(b,0x40,'Q')}
 return {0x2843:get(b,0x40,'i'),0x314d:get(b,0x44,'Q')}

def treasury_milli(price_integer):return integer(price_integer,0,(2**31-1)//1000)*1000

def reply_branch(name,state):
 p=profile(name);integer(state,0,2)
 if not p['reply']:return 'unilateral_claim_effect_no_state2_requirement'
 if state==0:return 'pending_or_unhandled_no_effect_conclusion'
 if state==2:return {'sell_province':'money_and_province_transfer','enforce_peace':'nested_peace_offer_execute','threaten_war':'province_and_truce_paths'}[name]
 return {'sell_province':'decline_notification_path','enforce_peace':'may_execute_join_war','threaten_war':'may_execute_declare_war'}[name]

@dataclass
class OwnedModel:
 """No native functions. Counterexample model for the reviewed ownership boundary."""
 name:str
 original:bytearray
 command_clone:bytearray|None=None
 command_present:bool=False
 original_destroyed:bool=False
 clone_destroyed:bool=False
 terminal_unknown:bool=False
 ever_wrapped:bool=False

 def healthy(self):require(not self.terminal_unknown,'terminal unknown; no retry or guessed cleanup')
 def wrap(self,current_date):
  self.healthy();require(not self.ever_wrapped and not self.original_destroyed and not self.command_present,'single wrapper')
  integer(current_date,1,2**31-1);self.command_clone=clone(self.name,self.original)
  require(self.command_clone is not self.original,'owned clone must differ')
  put(self.command_clone,0x2c,'i',current_date);self.command_present=True;self.ever_wrapped=True
 def destroy_original(self):
  self.healthy();require(not self.original_destroyed,'double original destruction');self.original_destroyed=True
 def destroy_command(self):
  self.healthy();require(self.command_present and not self.clone_destroyed,'owned command required')
  self.clone_destroyed=True;self.command_present=False
 def exception(self):self.terminal_unknown=True
 def send(self):raise ValueError('no sender or execution permission in this offline model')

def gate_observation(full,local,command_gate):
 for b in (full,local,command_gate):require(type(b) is bool,'strict native result bool')
 return {'full_preview':full,'family_local':local,'command_gate':command_gate,'send_permission':False,'effect_verified':False}

def claim_record_bit(actor,target,table,records_actor,record_target,raw):
 country(actor,table);country(target,table)
 require(type(records_actor) is int and records_actor==actor,'actor records identity')
 require(type(record_target) is int and record_target==target,'target record identity')
 return bool(integer(raw,0,255)&1)
