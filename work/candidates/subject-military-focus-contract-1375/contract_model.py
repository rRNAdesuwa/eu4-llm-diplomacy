"""Pure byte/schema/ownership model, not native code and not a process reader."""
from __future__ import annotations
import copy, struct

ENUM={'no_focus':0,'aggressive':1,'supportive':2,'passive':3,'defensive':4,'siege':5}
SIZE=0x60
DEFAULT_HANDLE=0x2d2d2d
VT=0x140000000+0x1c54678
COPY=((0x38,4),(0x40,2),(0x44,4),(0x48,2),(0x4a,1),(0x4b,1),(0x4c,4),(0x50,8),(0x58,4))

def integer(x,low,high):
    if type(x) is not int or not low<=x<=high:raise ValueError('strict integer')
    return x

def handle(x,count):
    integer(x,1,2**64-1)
    slot=(x>>32)&65535
    if not x>>56 or slot>=min(count,32768):raise ValueError('full handle/slot')
    return slot

def request(x):
    if type(x) is not dict or set(x)!={'actor','target','focus'}:raise ValueError('request keys')
    if type(x['focus']) is not str:raise ValueError('enum string')
    if x['actor']!='FRA' or x['target']!='NAV' or x['focus'] not in ENUM:raise ValueError('restricted candidate')
    return ENUM[x['focus']]

def put(b,o,n,v): b[o:o+n]=int(v).to_bytes(n,'little',signed=False)
def get(b,o,n):return int.from_bytes(b[o:o+n],'little')

def ctor(poison=0xa5):
    b=bytearray([poison]*SIZE)
    for o,n,v in [(0,8,VT),(8,4,0x165),(0x10,1,0),(0x18,8,0),(0x28,8,0),(0x30,8,15),
      (0x38,4,0xffffffff),(0x3c,4,0),(0x40,2,0),(0x44,4,0x3017),(0x48,8,0xffff),(0x50,8,DEFAULT_HANDLE),(0x58,4,0)]:put(b,o,n,v)
    return b

def default_mask(b):
    if type(b) not in (bytes,bytearray) or len(b)!=SIZE:raise ValueError('object extent')
    expected=ctor(0)
    ranges=((0,8),(8,4),(0x10,1),(0x18,8),(0x28,8),(0x30,8),(0x38,4),(0x3c,4),(0x40,2),(0x44,4),(0x48,8),(0x50,8),(0x58,4))
    return sum(1<<i for i,(o,n) in enumerate(ranges) if b[o:o+n]!=expected[o:o+n])

def clone(source,argument):
    if type(source) not in (bytes,bytearray) or len(source)!=SIZE:raise ValueError('source extent')
    if type(argument) is not bytearray or len(argument)!=32 or any(argument[:24]) or get(argument,24,8)!=15:raise ValueError('owned empty String32 required')
    out=ctor(0xcc)
    for o,n in COPY:out[o:o+n]=source[o:o+n]
    # This is the normal-path consumed String32 model; no native ownership claim.
    argument[:]=bytes(24)+(15).to_bytes(8,'little')
    return out

def native_gate_model(country_status,kind,focus):
    integer(country_status,0,2**32-1);integer(kind,0,255);integer(focus,0,2**32-1)
    return (country_status!=0 or kind==7) and focus<=5

SCHEMA={'pid','creation_filetime','date','game','database','array','count','player_handle','actor_handle','target_handle',
 'actor_subjects','target_overlord','dependency','definition','definition_vtable','uses_military_focus','can_set_mil_focus',
 'country_status','country_kind','focus','paused','selected_country_identity_verified','dependency_identity_verified',
 'prototype_vtable_verified','snapshot_identity_verified','entitlement'}

def ro_preconditions(first,second):
    for x in (first,second):
        if type(x) is not dict or set(x)!=SCHEMA:raise ValueError('snapshot keys')
        for key in ('paused','selected_country_identity_verified','dependency_identity_verified','prototype_vtable_verified','snapshot_identity_verified'):
            if type(x[key]) is not bool or not x[key]:raise ValueError('unproved evidence')
        for key in ('pid','creation_filetime','date','game','database','array','dependency','definition','definition_vtable'):
            integer(x[key],1,2**64-1)
        if x['definition_vtable']!=0x140000000+0x1ce7488:raise ValueError('toy fixed-image definition vtable')
        integer(x['count'],1,4096)
        for key in ('player_handle','actor_handle','target_handle','target_overlord'):handle(x[key],x['count'])
        if x['player_handle']!=x['actor_handle'] or x['target_overlord']!=x['actor_handle'] or x['actor_handle']==x['target_handle']:raise ValueError('authority direction')
        for key in ('uses_military_focus','can_set_mil_focus'):integer(x[key],1,1)
        if type(x['actor_subjects']) is not list or len(x['actor_subjects'])>256:raise ValueError('subject vector budget')
        for h in x['actor_subjects']:handle(h,x['count'])
        if len(set(x['actor_subjects']))!=len(x['actor_subjects']) or x['actor_subjects'].count(x['target_handle'])!=1:raise ValueError('subject vector binding')
        if not native_gate_model(x['country_status'],x['country_kind'],x['focus']):raise ValueError('gate subset')
        if x['entitlement']!='unsupported_tls_identity':raise ValueError('unproved entitlement cannot become permission')
    if first!=second:raise ValueError('unstable snapshots')
    return {'structural_ro_preconditions':True,'entitlement':'unsupported_tls_identity','native_call_authorized':False,'effect_verified':False,'production_supported':False}

class Ownership:
    def __init__(self):self.state='owned';self.destroy_count=0
    def before_dispatch(self):
        if self.state!='owned':raise ValueError('not owned')
        self.state='entered_unknown'
    def destroy(self):
        if self.state!='owned':raise ValueError('unknown/transferred or already freed')
        self.state='destroyed';self.destroy_count+=1
    def returned(self,returned,consumed):
        if self.state!='entered_unknown' or type(returned) is not bool or type(consumed) is not bool:raise ValueError('invalid result')
        # Even a false return does not grant caller ownership back.
        self.state='transferred_observed' if returned and consumed else 'terminal_unknown'
