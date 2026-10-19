"""Finite Python bootstrap/stage wire codecs, never publishing by themselves."""
import hashlib
import re
from pathlib import Path
import types

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def require(ok,why):
    if not ok:raise ValueError(why)


def _protocol():
    path=ROOT/'work/candidates/v18-spy-no-send-contract-1375/protocol.py'
    with path.open('rb') as stream:raw=stream.read(32769)
    require(len(raw)<=32768 and hashlib.sha256(raw).hexdigest()=='3da952bc3ab0836f951a3df091972655792de82f33c07be5f4e679603131604d','Sealed protocol changed')
    m=types.ModuleType('_spy18_wire_contract');m.__file__=str(path);exec(compile(raw,str(path),'exec'),m.__dict__);return m
p=_protocol()
IDENTITY={'pid','creation','session','dll_sha256','manifest_sha256'}


def identity(value):
    require(type(value)is dict and set(value)==IDENTITY,'Exact bootstrap identity')
    require(type(value['pid'])is int and 0<value['pid']<=0xffffffff,'PID')
    for name,length in (('creation',16),('session',32),('dll_sha256',64),('manifest_sha256',64)):
        require(type(value[name])is str and re.fullmatch('[0-9a-f]{'+str(length)+'}',value[name]) and int(value[name],16)>0,'Canonical identity hex')
    return dict(value)


def encode_boot(value):
    i=identity(value)
    data=(f'EU4SPYBOOT/1\npurpose=restricted_spy_no_send_lab_1375_v18\ngame_sha256={p.GAME_SHA256}\npid={i["pid"]}\ncreation={i["creation"]}\nsession={i["session"]}\ndll_sha256={i["dll_sha256"]}\nmanifest_sha256={i["manifest_sha256"]}\ndisposable_test=1\nno_send=1\n').encode('ascii')
    require(len(data)<=1024,'Bootstrap byte budget');return data


def decode_boot(raw):
    require(type(raw)is bytes and 0<len(raw)<=1024 and raw.endswith(b'\n'),'Bootstrap byte contract')
    text=raw.decode('ascii');lines=text.splitlines()
    require(len(lines)==10,'Bootstrap line count')
    keys=['purpose','game_sha256','pid','creation','session','dll_sha256','manifest_sha256','disposable_test','no_send']
    values={}
    for key,line in zip(keys,lines[1:]):
        require(line.startswith(key+'='),'Bootstrap field order');values[key]=line[len(key)+1:]
    require(re.fullmatch('[1-9][0-9]{0,9}',values['pid']),'Canonical PID')
    i={k:values[k] for k in IDENTITY};i['pid']=int(i['pid'])
    require(encode_boot(i)==raw,'Canonical bootstrap bytes');return i


def session_path(build,i):
    i=identity(i)
    return Path(build)/f'spy18-{i["pid"]}-{i["creation"]}-{i["session"]}'
