"""Fixed v19 private bootstrap/stage codecs; imports perform no process access."""
from pathlib import Path
import re

GAME_SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
PURPOSE='restricted_spy_lab_1375_v19'
STAGES=('lifecycle','family_preview','owned_command','send_batch')
FAMILIES=('corrupt_officials','sabotage_reputation','sow_discontent','slander_merchants','sabotage_recruitment')
IDENTITY={'pid','creation','session','dll_sha256','manifest_sha256'}

def require(ok,why):
    if not ok:raise ValueError(why)

def identity(value):
    require(type(value)is dict and set(value)==IDENTITY,'Exact bootstrap identity')
    require(type(value['pid'])is int and 0<value['pid']<=0xffffffff,'PID')
    for name,length in (('creation',16),('session',32),('dll_sha256',64),('manifest_sha256',64)):
        require(type(value[name])is str and re.fullmatch('[0-9a-f]{'+str(length)+'}',value[name]) and int(value[name],16)>0,'Canonical identity hex')
    return dict(value)

def encode_boot(value):
    i=identity(value)
    return (f'EU4SPYBOOT19/1\npurpose={PURPOSE}\ngame_sha256={GAME_SHA}\npid={i["pid"]}\ncreation={i["creation"]}\nsession={i["session"]}\ndll_sha256={i["dll_sha256"]}\nmanifest_sha256={i["manifest_sha256"]}\ndisposable_test=1\nrestricted_spy_send=1\n').encode('ascii')

def rows(raw,keys):
    require(type(raw)is bytes and 0<len(raw)<=1024 and raw.endswith(b'\n'),'Bounded packet')
    require(all(32<=b<=126 or b==10 for b in raw),'ASCII LF only')
    lines=raw.decode('ascii').split('\n')[:-1]
    require(len(lines)==len(keys)+1,'Exact line count')
    values={}
    for key,line in zip(keys,lines[1:]):
        require(line.startswith(key+'='),'Exact field order');values[key]=line[len(key)+1:]
    return values

def extract_identity(values):
    require(re.fullmatch('[1-9][0-9]{0,9}',values['pid']),'Canonical PID')
    i={k:values[k] for k in IDENTITY};i['pid']=int(i['pid']);return identity(i)

def decode_boot(raw):
    v=rows(raw,('purpose','game_sha256','pid','creation','session','dll_sha256','manifest_sha256','disposable_test','restricted_spy_send'))
    i=extract_identity(v);require(encode_boot(i)==raw,'Exact bootstrap bytes');return i

def encode_request(value,stage,expires):
    i=identity(value)
    require(type(stage)is str and stage in STAGES,'Fixed stage')
    require(type(expires)is int and 0<expires<=2**64-1,'Expiry uint64')
    q=STAGES.index(stage)+1;schema='EU4SPYSEND/1' if q==4 else 'EU4SPYLAB/1'
    raw=(f'{schema}\npurpose={PURPOSE}\ngame_sha256={GAME_SHA}\npid={i["pid"]}\ncreation={i["creation"]}\nsession={i["session"]}\ndll_sha256={i["dll_sha256"]}\nmanifest_sha256={i["manifest_sha256"]}\nsequence={q}\nexpires={expires}\nstage={stage}\nprofile=spy5_true_state0_v1\nactor=FRA\ntarget=ENG\nvalue=1\nstate=0\nenvoy=-1\n').encode('ascii')
    require(len(raw)<=1024,'Packet budget');return raw

def decode_request(raw):
    v=rows(raw,('purpose','game_sha256','pid','creation','session','dll_sha256','manifest_sha256','sequence','expires','stage','profile','actor','target','value','state','envoy'))
    i=extract_identity(v)
    require(re.fullmatch('[1-9][0-9]{0,19}',v['expires']),'Canonical expiry')
    expiry=int(v['expires']);require(encode_request(i,v['stage'],expiry)==raw,'Exact request bytes')
    return {'identity':i,'sequence':STAGES.index(v['stage'])+1,'stage':v['stage'],'expires':expiry}

def encode_item(value,item,expires):
    i=identity(value);require(type(item)is int and 1<=item<=5,'Fixed item')
    require(type(expires)is int and 0<expires<=2**64-1,'Expiry uint64')
    return (f'EU4SPYITEM/1\npid={i["pid"]}\ncreation={i["creation"]}\nsession={i["session"]}\ndll_sha256={i["dll_sha256"]}\nmanifest_sha256={i["manifest_sha256"]}\nsequence=4\nitem={item}\nfamily={FAMILIES[item-1]}\nexpires={expires}\n').encode('ascii')

def session_path(build,i):
    i=identity(i);return Path(build)/f'spy19-{i["pid"]}-{i["creation"]}-{i["session"]}'
