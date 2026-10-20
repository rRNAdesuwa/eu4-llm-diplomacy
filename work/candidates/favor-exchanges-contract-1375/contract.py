"""Strict offline layout/ownership model. No process, native call, sender or permission."""
from dataclasses import dataclass, replace
import struct

INVALID=0x2d2d2d
FACTORY_DATE=0x29c77f8
SIZES={'reduce_relations_favor':0x48,'trade_favors_for_gold':0x40,
       'trade_favors_for_men':0x40,'trade_favors_for_sailors':0x40,
       'trade_favors_for_trust':0x48,'trade_favors_for_war_prep':0x40}
TOKENS=dict(zip(SIZES,(0x3bcd,0x3bce,0x3bcf,0x3bd0,0x3bd3,0x3bd4)))
def integer(x,lo,hi):
    if type(x) is not int or not lo<=x<=hi:raise ValueError('typed integer range')
    return x
def country(x):
    integer(x,1,(1<<64)-1)
    if not x>>56 or ((x>>32)&0xffff)>=4096 or x&0xffffff==INVALID:
        raise ValueError('full generation/slot/tag shape')
    return x  # Shape only; this does not resolve a live country.
def family(x):
    if type(x) is not str or x not in SIZES:raise ValueError('unsupported family')
    return x
@dataclass(frozen=True)
class Action:
    family:str;actor:int=INVALID;current_actor:int=INVALID;target:int=INVALID
    primary_date:int=FACTORY_DATE;secondary_date:int=FACTORY_DATE
    envoy:int=-1;state:int=0;value:bool=True;flag:int=0;identifier:int=0
    third:int|None=None;favor_milli:int|None=None;trust_points:int|None=None
def validate_action(a):
    if type(a) is not Action:raise ValueError('action type')
    family(a.family)
    for h in (a.actor,a.current_actor,a.target):
        integer(h,1,(1<<64)-1)
        if h!=INVALID:country(h)
    integer(a.primary_date,0,0x7fffffff);integer(a.secondary_date,0,0x7fffffff)
    integer(a.envoy,-1,0x7fffffff);integer(a.state,0,2);integer(a.flag,0,1);integer(a.identifier,0,0xffffffff)
    if type(a.value) is not bool:raise ValueError('typed value')
    extension_bytes(a)
    return a
def factory(name,*,trust_cost_units=None,trust_amount=None):
    """Mock inputs are explicit; defaults are not assertions of live define values."""
    name=family(name)
    if name=='trade_favors_for_trust':
        # Conservative offline profile; the native multiplication is signed32.
        integer(trust_cost_units,0,2147483);integer(trust_amount,0,100)
        return Action(name,favor_milli=trust_cost_units*1000,trust_points=trust_amount)
    if trust_cost_units is not None or trust_amount is not None:raise ValueError('foreign extra fields')
    return Action(name,third=INVALID if name=='reduce_relations_favor' else None)
def initialize_like_normal_ai(a,actor,target,date):
    validate_action(a)
    if a!=factory(a.family,**({'trust_cost_units':a.favor_milli//1000,'trust_amount':a.trust_points} if a.family=='trade_favors_for_trust' else {})):
        raise ValueError('pristine factory required')
    country(actor);country(target);integer(date,0,0x7fffffff)
    if actor==target or ((actor>>32)&0xffff)==((target>>32)&0xffff):raise ValueError('distinct country slots')
    return replace(a,actor=actor,current_actor=actor,target=target,primary_date=date)
def clone(a):
    validate_action(a)
    return replace(a,secondary_date=a.primary_date,flag=0)
def wrapped_clone(a,current_date):
    integer(current_date,0,0x7fffffff)
    return replace(clone(a),secondary_date=current_date)
def extension_bytes(a):
    """Offline wire-layout discriminator only; not an engine serializer."""
    if type(a) is not Action:raise ValueError('action')
    family(a.family)
    if a.family=='trade_favors_for_trust':
        integer(a.favor_milli,0,0x7fffffff);integer(a.trust_points,0,100)
        if a.third is not None:raise ValueError('trust is not country reference')
        return struct.pack('<ii',a.favor_milli,a.trust_points)
    if a.family=='reduce_relations_favor':
        if a.favor_milli is not None or a.trust_points is not None:raise ValueError('third party is not pair of numbers')
        integer(a.third,1,(1<<64)-1)
        if a.third!=INVALID:country(a.third)
        return struct.pack('<Q',a.third)
    if any(v is not None for v in (a.third,a.favor_milli,a.trust_points)):raise ValueError('no amount extension')
    return b''
def parameterized_caller_status(a):
    if type(a) is not Action:raise ValueError('action')
    family(a.family)
    # A full third handle has a known representation but its normal selection
    # caller was not closed. It must never gain execution permission here.
    return {'normal_parameterized_caller_closed':a.family!='reduce_relations_favor',
            'third_selection_closed':False if a.family=='reduce_relations_favor' else None,
            'native_permission':None,'construct_authorized':False,'production_ready':False}
def selected_trust_effect_candidate(trust,favors,cost,amount):
    """Selected accepted-state arithmetic, omits scripts/notifications/dirty flags."""
    integer(trust,0,100);integer(favors,0,100000);integer(cost,0,100000);integer(amount,0,100)
    return {'record_direction':'recipient_to_actor','trust':min(100,trust+amount),
            'favors_milli':max(0,favors-cost),'effect_verified':False}
def classify(state):
    integer(state,0,2)
    return ('pending','refused_with_possible_response_side_effects','accepted_branch_only')[state]
def phase_result(preview,gate):
    if type(preview) is not bool or type(gate) is not bool:raise ValueError('typed bool')
    return {'preview':preview,'command_gate':gate,'submit_authorized':False,'effect_verified':False}
class Ownership:
    """Logical identities, not memory pointers. Terminal on any unknown result."""
    def __init__(self,original):
        integer(original,1,0x7fffffff);self.original=original;self.command=None;self.clone=None;self.frozen=False
    def _ready(self):
        if self.frozen:raise ValueError('unknown ownership terminal')
    def wrap(self,command,clone_id):
        self._ready();integer(command,1,0x7fffffff);integer(clone_id,1,0x7fffffff)
        if self.original is None or self.command is not None or len({self.original,command,clone_id})!=3:raise ValueError('distinct owned objects required')
        self.command=command;self.clone=clone_id
    def destroy_original(self):
        self._ready()
        if self.original is None:raise ValueError('double destruction')
        self.original=None
    def destroy_command(self):
        self._ready()
        if self.command is None:raise ValueError('no known command owner')
        self.command=None;self.clone=None
    def exception(self):self.frozen=True
