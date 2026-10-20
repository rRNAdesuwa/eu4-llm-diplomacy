"""Pure proposed v19 transition model. No resolver, file IO or execution API.

All inputs are synthetic assertions, not authenticated native evidence. In
particular phase() does NOT verify a v18/v19 journal or authorize game work.
"""
from copy import deepcopy
import json
import re

FAMILIES=('corrupt_officials','sabotage_reputation','sow_discontent',
          'slander_merchants','sabotage_recruitment')
GAME='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
OLD_DLL='6aff9a9fc4d46692c9be0ac39b0c741bf8eeb840abaf8731d0144510a938f00b'
PROTOCOL='EU4SPYSEND/1'; PURPOSE='restricted_spy_send_plan_1375_v19'
INTS={'pid':(1,2**32-1),'thread':(1,2**32-1),'date':(1,2**31-1)}
COOKIES=('world','database','countries','server','holder','context','transport')
STAMP=set(INTS)|set(COOKIES)|{'creation','session','dll_sha256','manifest_sha256',
                           'actor_handle','target_handle','player_handle'}
REQUEST={'protocol','purpose','game_sha256','pid','creation','session','dll_sha256',
         'manifest_sha256','sequence','expires','operation','actor','target','profile'}

def require(test,why):
    if not test:raise ValueError(why)
def integer(x,lo,hi):return type(x) is int and lo<=x<=hi
def hx(x,n):return type(x) is str and re.fullmatch('[0-9a-f]{'+str(n)+'}',x) is not None and int(x,16)>0
def stamp(s):
    require(type(s) is dict and set(s)==STAMP,'exact private stamp')
    for k,(lo,hi) in INTS.items():require(integer(s[k],lo,hi),'stamp '+k)
    for k in COOKIES:require(integer(s[k],0x10000,0x7fffffffffff) and s[k]%8==0,'cookie '+k)
    for k,n in [('creation',16),('session',32),('dll_sha256',64),('manifest_sha256',64)]:require(hx(s[k],n),'stamp '+k)
    require(s['dll_sha256']!=OLD_DLL,'v18 DLL cannot send')
    for k,v in [('actor_handle','0100007a00415246'),('target_handle','0100002e00474e45'),('player_handle','0100007a00415246')]:
        require(type(s[k]) is str and s[k]==v,'full handle '+k)
    return deepcopy(s)

def encode_request(r):
    require(type(r) is dict and set(r)==REQUEST,'exact fixed request fields')
    constants={'protocol':PROTOCOL,'purpose':PURPOSE,'game_sha256':GAME,
      'operation':'submit_fixed_spy5','actor':'FRA','target':'ENG','profile':'spy5_true_state0_envoy_minus1_v19'}
    for k,v in constants.items():require(type(r[k]) is str and r[k]==v,'request '+k)
    require(integer(r['pid'],1,2**32-1) and integer(r['sequence'],4,4),'request pid/sequence')
    require(integer(r['expires'],1,2**64-1),'request expiry')
    for k,n in [('creation',16),('session',32),('dll_sha256',64),('manifest_sha256',64)]:require(hx(r[k],n),'request '+k)
    require(r['dll_sha256']!=OLD_DLL,'v18 DLL cannot send')
    raw=(json.dumps(r,sort_keys=True,separators=(',',':'),ensure_ascii=True)+'\n').encode('ascii')
    require(len(raw)<=1024,'request byte budget');return raw

def decode_request(raw):
    require(type(raw) is bytes and 0<len(raw)<=1024 and raw.endswith(b'\n'),'request bounded bytes')
    require(all(x==10 or 32<=x<=126 for x in raw),'request ASCII')
    def pairs(items):
        d={}
        for k,v in items:require(k not in d,'duplicate key');d[k]=v
        return d
    r=json.loads(raw,object_pairs_hook=pairs)
    require(encode_request(r)==raw,'canonical request bytes');return r

class Batch:
    """Single-use abstract ownership model; no real native implementation."""
    def __init__(self,binding):
        self.binding=stamp(binding);self.phase_count=0;self.frame=0;self.now=0
        self.state='preflight';self.frozen=False;self.rows=[];self.owned=set()
        self.expires=0;self.initial=None;self.final=None;self.entered=False
        self.item_frame=0;self.outcome=None;self.claimed=False;self.events=0
    def fail(self,why):
        self.frozen=True;self.state='frozen';raise ValueError(why)
    def guard(self,s,frame,now,*,work):
        if self.frozen:self.fail('permanently frozen')
        try:
            require(stamp(s)==self.binding,'identity changed; cookies are not epoch proof')
            require(integer(frame,1,2**64-1) and integer(now,0,2**64-1),'strict frame/clock')
            require(frame>=self.frame and now>=self.now,'frame/clock rollback')
            if work and self.claimed:require(now<self.expires,'work TTL expired')
        except ValueError as e:self.fail(str(e))
        self.frame=frame;self.now=now
    def phase(self,number,s,frame,now,*,core_passed,later_clean_health):
        old=self.frame;self.guard(s,frame,now,work=False)
        if not (self.state=='preflight' and integer(number,1,3) and number==self.phase_count+1
                and core_passed is True and later_clean_health is True and frame>old):self.fail('phase proof assertion/order')
        self.phase_count=number
        if number==3:self.state='ready'
    def claim(self,raw,s,frame,now,*,exclusive_durable,initial_sha256):
        previous=self.frame;self.guard(s,frame,now,work=False)
        try:
            r=decode_request(raw)
            require(self.state=='ready' and not self.claimed and frame>previous,'single later batch claim')
            require(exclusive_durable is True and hx(initial_sha256,64),'durable claim + initial census')
            require(now<r['expires']<=now+60000,'claim TTL')
            for k in ['pid','creation','session','dll_sha256','manifest_sha256']:require(type(r[k]) is type(s[k]) and r[k]==s[k],'request identity '+k)
        except ValueError as e:self.fail(str(e))
        self.expires=r['expires'];self.initial=initial_sha256;self.claimed=True;self.state='next'
    def event(self,kind,s,frame,now,**data):
        # Cleanup after a normal returned call may cross TTL, but never identity.
        cleanup=kind in ('destroy_command','destroy_original','health','submit_result')
        previous=self.frame;self.guard(s,frame,now,work=not cleanup)
        self.events+=1
        if self.events>256:self.fail('model event budget')
        schemas={'item_claim':{'family','durable'},'factory':{'verified'},'initialize':{'verified'},
          'preview':{'allowed'},'wrapper':{'verified'},'gate':{'allowed'},'destroy_original':{'returned'},
          'destroy_command':{'returned'},'dispatch_intent':{'durable'},'submit_enter':{'guard_passed'},
          'submit_result':{'returned','accepted','consumed'},'health':{'healthy'},'fault':{'reason'}}
        if kind not in schemas or set(data)!=schemas[kind]:self.fail('event exact schema')
        for k,v in data.items():
            if k in ('accepted','consumed') and v is None:continue
            if k in ('family','reason'):
                if type(v) is not str:self.fail('event string type')
            elif type(v) is not bool:self.fail('event boolean type')
        if kind=='fault':self.fail('fault/SEH/audit: '+data['reason'])
        if kind!='item_claim' and frame!=self.item_frame and kind!='health':self.fail('call escaped owner frame')
        if kind=='item_claim':
            if self.state!='next' or len(self.rows)>=5 or frame<=previous or data['family']!=FAMILIES[len(self.rows)] or data['durable'] is not True:self.fail('fixed order/later frame/durable item claim')
            self.item_frame=frame;self.state='factory';self.outcome=None;self.entered=False
        elif kind=='factory':
            if self.state!='factory' or data['verified'] is not True:self.fail('factory unknown; no guessed cleanup')
            self.owned={'original'};self.state='initialize'
        elif kind=='initialize':
            if self.state!='initialize' or data['verified'] is not True:self.fail('fixed fields mismatch')
            self.state='preview'
        elif kind=='preview':
            if self.state!='preview':self.fail('full preview order')
            self.state='wrapper' if data['allowed'] else 'cleanup_original'
            if not data['allowed']:self.outcome='full_preview_rejected'
        elif kind=='wrapper':
            if self.state!='wrapper' or data['verified'] is not True:self.fail('wrapper/clone alias unknown')
            self.owned={'original','command_owns_clone'};self.state='gate'
        elif kind=='gate':
            if self.state!='gate':self.fail('command gate order')
            self.state='destroy_original' if data['allowed'] else 'cleanup_command'
            if not data['allowed']:self.outcome='command_gate_rejected'
        elif kind=='destroy_command':
            if self.state!='cleanup_command' or self.entered or data['returned'] is not True:self.fail('destructor/ownership unknown')
            self.owned.remove('command_owns_clone');self.state='cleanup_original'
        elif kind=='destroy_original':
            if self.state not in ('destroy_original','cleanup_original') or data['returned'] is not True:self.fail('original destructor unknown')
            self.owned.remove('original');self.state='intent' if self.state=='destroy_original' else 'health'
        elif kind=='dispatch_intent':
            if self.state!='intent' or data['durable'] is not True:self.fail('durable dispatch audit missing')
            self.state='enter'
        elif kind=='submit_enter':
            if self.state!='enter' or data['guard_passed'] is not True:self.fail('final guard rejected; stop batch')
            self.entered=True;self.owned.clear();self.state='submitted'
        elif kind=='submit_result':
            if self.state!='submitted':self.fail('return without enter')
            if not (data['returned'] is True and data['accepted'] is True and data['consumed'] is True):
                self.outcome='dispatch_unknown';self.fail('transfer not acknowledged; no cleanup/retry')
            self.outcome='dispatched';self.state='health'
        elif kind=='health':
            if self.state!='health' or frame<=self.item_frame or data['healthy'] is not True or self.owned:self.fail('later health/cleanup missing')
            self.rows.append({'family':FAMILIES[len(self.rows)],'outcome':self.outcome,'effect_verified':False})
            self.state='complete' if len(self.rows)==5 else 'next'
    def observe_final(self,s,frame,now,sha256):
        previous=self.frame;self.guard(s,frame,now,work=False)
        if self.state!='complete' or self.final is not None or frame<=previous or not hx(sha256,64):self.fail('only terminal final census')
        self.final=sha256
    def summary(self):
        return {'origin':'pure_synthetic_state_model','state':self.state,'rows':deepcopy(self.rows),
          'initial_sha256':self.initial,'final_sha256':self.final,'frozen':self.frozen,
          'all_five_dispatched':len(self.rows)==5 and all(x['outcome']=='dispatched' for x in self.rows),
          'native_calls_performed':False,'native_runtime_verified':False,'effect_verified':False,
          'causal_effect_verified':False,'strict_sp_verified':False,'production_ready':False,
          'retry_allowed':False,'actual_journal_validated':False}
