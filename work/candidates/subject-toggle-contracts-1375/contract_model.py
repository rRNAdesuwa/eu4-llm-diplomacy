"""Pure synthetic contract models, never authenticated RO facts or native authority."""
from dataclasses import dataclass

FRA=0x0100007a00415246
NAV=0x010000bc0056414e
FAMILIES={'embargo_rivals':(12762,1),'scutage':(12767,4),'divert_trade':(12836,6)}
FIELDS={'actor','target','overlord','flag_word','actor_presence','actor_marker','target_at_war','rival_count','type_allows'}

def integer(v,lo,hi):
    if type(v) is not int or not lo<=v<=hi:raise ValueError('strict integer/range')
    return v
def boolean(v):
    if type(v) is not bool:raise ValueError('strict boolean')
    return v
def validate_fact(f):
    if type(f) is not dict or set(f)!=FIELDS:raise ValueError('fact fields')
    for k in ['actor','target','overlord']:integer(f[k],0,(1<<64)-1)
    integer(f['flag_word'],0,(1<<32)-1)
    integer(f['actor_presence'],-(1<<31),(1<<31)-1)
    integer(f['actor_marker'],0,255)
    integer(f['target_at_war'],0,1)
    integer(f['rival_count'],0,4096)
    boolean(f['type_allows'])
    if f['actor']!=FRA or f['target']!=NAV:raise ValueError('fixed pair/full generation')
    return f
def current(family,f):
    validate_fact(f)
    if family not in FAMILIES:raise ValueError('family')
    index=FAMILIES[family][1]
    return bool(f['overlord']>>56) and bool(f['flag_word']&(1<<index))
def plan(family,desired,f):
    """Mirror only evidenced raw predicates; always returns native_allowed=None."""
    boolean(desired);validate_fact(f)
    now=current(family,f)
    reason=None
    if f['overlord']!=FRA:reason='not_full_direct_subject'
    elif f['actor_presence']==0 and f['actor_marker']!=7:reason='actor_field_reject'
    elif not f['type_allows']:reason='type_reject'
    elif desired==now:reason='already_desired'
    elif family=='scutage' and f['target_at_war']!=0:reason='scutage_war_reject'
    elif family=='embargo_rivals' and not now and f['rival_count']==0:reason='no_rivals'
    else:reason='requires_native_full_gate'
    return {'reason':reason,'cancel_snapshot':now,'desired_enabled':desired,
      'transition_needed':desired!=now,'native_allowed':None,'native_call_authorized':False,
      'runtime_verified':False,'production_supported':False}
def stale(family,snapshot,f):
    boolean(snapshot)
    return snapshot!=current(family,f)
def bit_write(family,cancel,word):
    """Only the first effect write, explicitly not its complete game effect."""
    boolean(cancel);integer(word,0,(1<<32)-1)
    if family not in FAMILIES:raise ValueError('family')
    mask=1<<FAMILIES[family][1]
    return word&~mask if cancel else word|mask
def token_hash(token):
    integer(token,0,0xffffffff);v=0xcbf29ce484222325
    for x in token.to_bytes(4,'little'):v=((v^x)*0x100000001b3)&0xffffffffffffffff
    return v

@dataclass
class Lifetime:
    """Offline stop-policy; does not model unwinder or prove actual ownership."""
    original:str='owned'
    clone:str='absent'
    temporary_string:str='owned'
    terminal:bool=False
    def clone_normal(self):
        if self.terminal or self.original!='owned' or self.clone!='absent' or self.temporary_string!='owned':raise ValueError('clone state')
        self.clone='owned';self.temporary_string='destroyed'
    def destroy(self,which):
        if which not in ('original','clone') or self.terminal or getattr(self,which)!='owned':raise ValueError('not known owned')
        setattr(self,which,'destroyed')
    def handoff_enter(self,which):
        if which not in ('original','clone') or self.terminal or getattr(self,which)!='owned':raise ValueError('handoff state')
        setattr(self,which,'transferred_or_unknown');self.terminal=True
    def exception(self):
        self.terminal=True
        if self.original=='owned':self.original='unknown'
        if self.clone=='owned':self.clone='unknown'
        if self.temporary_string=='owned':self.temporary_string='unknown'
