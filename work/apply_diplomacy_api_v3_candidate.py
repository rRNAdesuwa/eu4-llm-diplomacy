"""Apply the eight exact reviewed V3 files once, preserving every preimage.

No game/process access, service startup, DLL, request, or backend registration.
"""
from pathlib import Path
import hashlib
import json
import os

ROOT=Path(__file__).resolve().parent.parent
CANDIDATE=ROOT/'work/candidates/diplomacy-api-contract-v3-review'
OUTPUT=ROOT/'work/runtime/diplomacy-api-v3-application-20261008a'
MANIFEST_SHA='f5c373c0b590ab4c312feb7ee690bac81449bb3e053cea3ae79d04ca19a3d6b0'
REVIEW_SHA='7d12aeeb9044057ee17863c24ea4cac9a88341a0b492b3d17397602368de745e'
INDEPENDENT=ROOT/'work/review-results/diplomacy-api-contract-v3-external-20261008a/review.json'
INDEPENDENT_SHA='01c726158cb7019b5a00d95bf2b60727d7e3f85170b33644f984fd9f7e4228f8'

def require(ok,reason):
    if not ok:raise ValueError(reason)

def ordinary(path):
    path=Path(path).absolute()
    for node in (path,*path.parents):
        if node.exists():
            st=node.stat()
            require(not node.is_symlink() and not getattr(st,'st_file_attributes',0)&0x400,'No link/reparse path')
    if path.exists():require(path.is_file() and path.stat().st_nlink==1,'Ordinary single-link file')
    return path

def read(path):
    with ordinary(path).open('rb') as stream:raw=stream.read(1024*1024+1)
    require(len(raw)<=1024*1024,'Read budget')
    return raw

def descriptor(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}

def write_new(path,raw):
    ordinary(path)
    with path.open('xb') as stream:
        require(stream.write(raw)==len(raw),'Full write');stream.flush();os.fsync(stream.fileno())

def write_json(path,value):
    write_new(path,(json.dumps(value,sort_keys=True,indent=2)+'\n').encode('ascii'))

def main():
    manifest_raw=read(CANDIDATE/'application-manifest.json')
    require(descriptor(manifest_raw)['sha256']==MANIFEST_SHA,'Exact application manifest')
    require(descriptor(read(CANDIDATE/'review.json'))['sha256']==REVIEW_SHA,'Exact candidate review')
    require(descriptor(read(INDEPENDENT))['sha256']==INDEPENDENT_SHA,'Exact independent review')
    manifest=json.loads(manifest_raw)
    require(manifest['protocol']=='EU4DIPLOMACY-CONTRACT/3' and len(manifest['application_files'])==8,'Exact application scope')
    require(manifest['all_execution_unsupported'] is True and manifest['backend_registered'] is False,'Contract only')
    require(not OUTPUT.exists(),'Permanent application record already exists')
    prepared=[]
    for name,pin in manifest['application_files'].items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts,'Relative file')
        target=ordinary(ROOT/name);require(target.resolve().is_relative_to(ROOT),'Target scope')
        before=read(target) if target.exists() else None
        require((descriptor(before) if before is not None else None)==pin['before'],'Current file differs: '+name)
        after=read(CANDIDATE/'files'/name);require(descriptor(after)==pin['after'],'Staged file differs: '+name)
        prepared.append((name,target,before,after))
    OUTPUT.mkdir()
    write_new(OUTPUT/'application-manifest.json',manifest_raw)
    for name,_,before,_ in prepared:
        if before is not None:
            backup=OUTPUT/'before'/name;backup.parent.mkdir(parents=True,exist_ok=True);write_new(backup,before)
    applied=[]
    try:
        for name,target,before,after in prepared:
            current=read(target) if target.exists() else None
            require(current==before,'Target changed after backup: '+name)
            pending=target.with_name('.'+target.name+'.v3-application-pending')
            write_new(pending,after)
            os.replace(pending,target)
            require(read(target)==after,'Applied file differs: '+name)
            applied.append(name)
        result={'schema':1,'status':'applied_exact_eight_files','files':manifest['application_files'],
                'candidate_review_sha256':REVIEW_SHA,'independent_review_sha256':INDEPENDENT_SHA,
                'all_execution_unsupported':True,'production_backend_registered':False,
                'game_accessed':False,'native_called':False,'service_started':False}
        write_json(OUTPUT/'application.json',result)
        print(json.dumps({'applied':len(applied),'output':str(OUTPUT),'game_accessed':False,'backend_registered':False},sort_keys=True))
    except BaseException as exc:
        write_json(OUTPUT/'application-error.json',{'applied':applied,'error':str(exc),'automatic_retry':False,'preimages_preserved':True})
        raise

if __name__=='__main__':main()
