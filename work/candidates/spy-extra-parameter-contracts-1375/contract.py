"""Offline field/ownership counterexamples only. No memory reader or engine API."""
from dataclasses import dataclass,replace

PROFILES={'stealmap':(0x33c8,0x1c7d108,'region',-1),
 'support_rebels':(0x2dde,0x1c7c248,'borrowed_faction',0),
 'scriptable_diplomatic_action':(0x3662,0x1ce1e28,'borrowed_definition',0)}
NULL_HANDLE=0x2d2d2d

def integer(v,lo,hi):
    if type(v) is not int or not lo<=v<=hi:raise ValueError('strict integer/range')
    return v

@dataclass(frozen=True)
class Fields:
    family:str;actor:int;controller:int;target:int;primary_date:int;secondary_date:int
    envoy:int=-1;state:int=0;value:bool=True;flag:int=0;identifier:int=0;parameter:int=0

def validate(f):
    if type(f) is not Fields or f.family not in PROFILES:raise ValueError('profile')
    for v in (f.actor,f.controller,f.target):integer(v,1,(1<<64)-1)
    for v in (f.primary_date,f.secondary_date):integer(v,0,0x7fffffff)
    if f.actor!=f.controller or f.actor==f.target:raise ValueError('restricted pair model')
    for k,wanted in (('envoy',-1),('state',0),('flag',0),('identifier',0)):
        if type(getattr(f,k)) is not int or getattr(f,k)!=wanted:raise ValueError(k)
    if type(f.value) is not bool or not f.value:raise ValueError('no cancel contract')
    if f.family=='stealmap':integer(f.parameter,0,0x7fffffff)
    else:integer(f.parameter,1,(1<<64)-1)
    return f

def clone_fields(f):
    validate(f)
    # These three observed clones copy PRIMARY into BOTH date fields.
    return replace(f,secondary_date=f.primary_date,flag=0)

def wrapper_fields(f,current_date):
    integer(current_date,0,0x7fffffff)
    return replace(clone_fields(f),secondary_date=current_date)

def region_selection(index,region_count):
    integer(region_count,1,4096);integer(index,0,region_count-1)
    return {'index':index,'schema_candidate_only':True,'engine_legality_unknown':True,'authorized':False}

def faction_selection(pointer,identity,selected_target,actor,records):
    """Injected mock records only; this is not a live-memory identity proof."""
    integer(pointer,1,(1<<64)-1);integer(actor,1,(1<<64)-1);integer(selected_target,1,(1<<64)-1)
    if type(identity) is not tuple or len(identity)!=2:raise ValueError('identity pair')
    for v in identity:integer(v,0,0xffffffff)
    if type(records) is not list or not 1<=len(records)<=256:raise ValueError('bounded list')
    seen=set();hits=[]
    for r in records:
        if type(r) is not dict or set(r)!= {'pointer','identity','target_handle','supporter_handle'}:raise ValueError('record schema')
        integer(r['pointer'],1,(1<<64)-1);integer(r['target_handle'],1,(1<<64)-1);integer(r['supporter_handle'],0,(1<<64)-1)
        if type(r['identity']) is not tuple or len(r['identity'])!=2:raise ValueError('record identity')
        for v in r['identity']:integer(v,0,0xffffffff)
        if r['pointer'] in seen:raise ValueError('duplicate borrowed pointer')
        seen.add(r['pointer'])
        if r['pointer']==pointer:hits.append(r)
    if len(hits)!=1 or hits[0]['identity']!=identity or hits[0]['target_handle']!=selected_target or hits[0]['supporter_handle']!=NULL_HANDLE:raise ValueError('not selected eligible borrowed record')
    return {'borrowed_pointer':pointer,'free_parameter':False,'native_call_authorized':False,'lifetime_unknown':True}

def technology_scope(name):
    if name=='steal_modern_ideas':return {'family':'scriptable_diplomatic_action','effect':'russian_modernization_government_power','technology_level_change_proven':False,'loaded_definition_unknown':True,'authorized':False}
    return {'family':None,'effect':None,'technology_level_change_proven':False,'unsupported':True,'authorized':False}

def preview_contract(family,slot,sink,mode):
    if family not in PROFILES or type(slot) is not int or slot!=0x88 or sink is not None or type(mode) is not bool or mode:raise ValueError('full-preview NULL,false only')
    return {'family':family,'action_slot':slot,'sink':None,'mode':False,'command_gate_slot':0x40,'command_gate_rva':0x4e8630,'native_call_authorized':False}

class Ownership:
    """Normal-path planning model; no claim that SEH frees a live object."""
    def __init__(self):self.original=True;self.command=False;self.clone=False;self.unknown=False;self.parameter_freed=False
    def guard(self):
        if self.unknown:raise ValueError('terminal unknown')
    def make_command(self):
        self.guard()
        if not self.original or self.command:raise ValueError('one independent clone')
        self.command=True;self.clone=True
    def destroy_original(self):
        self.guard()
        if not self.original:raise ValueError('double destroy original')
        self.original=False
    def destroy_command(self):
        self.guard()
        if not self.command or not self.clone:raise ValueError('double destroy command/clone')
        self.command=False;self.clone=False
    def exception(self):self.unknown=True
    def result(self):return {'original_owned':self.original,'command_owned':self.command,'clone_owned_by_command':self.clone,'unknown':self.unknown,'borrowed_parameter_freed':self.parameter_freed,'submitted':False,'effect_verified':False}
