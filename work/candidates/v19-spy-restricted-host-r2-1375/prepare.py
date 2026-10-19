"""Read-only source and exact versioned preimage verifier."""
from pathlib import Path
import argparse,hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
PIN_SHA='221ec4a99e315dd1034121adf1ca47d41e8ddad5beacbbc226a212e863eef0bc'
def read(p,maximum=8388608):
    for q in (p,*p.parents):
        if q.exists() and (q.is_symlink() or getattr(q.stat(),'st_file_attributes',0)&0x400):raise ValueError('reparse source')
    with p.open('rb') as f:b=f.read(maximum+1)
    if len(b)>maximum:raise ValueError('read budget')
    return b
def desc(p):
    b=read(p);return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def require(ok,message):
    if not ok:raise ValueError(message)
def check():
    require(desc(HERE/'input-pins.json')['sha256']==PIN_SHA,'input index')
    inputs=json.loads(read(HERE/'input-pins.json'));require(type(inputs)is dict and len(inputs)<=64,'input count');total=0
    for name,pin in inputs.items():
        p=(ROOT/name).resolve();require(p.is_relative_to(ROOT) and not name.startswith('bridge/'),'input path')
        value=desc(p);total+=value['bytes'];require(total<=16777216 and value==pin,'input changed '+name)
    for name,pin in json.loads(read(HERE/'preimage-index.json')).items():
        require(desc(HERE/name)=={k:pin[k] for k in ('bytes','sha256')},'preimage changed '+name)
        require(read(HERE/name)==read(ROOT/pin['source']),'preimage differs '+name)
    index=json.loads(read(HERE/'source-index.json'));require(index['input_pins_sha256']==PIN_SHA and len(index['sources'])<=64,'source index')
    for name,pin in index['sources'].items():
        p=(HERE/name).resolve();require(p.is_relative_to(HERE) and desc(p)==pin and pin['bytes']<=262144,'local source changed '+name)
    return {'checked':True,'inputs':len(inputs),'sources':len(index['sources']),'mutable_api_dependency':False,'actual_process_access':False,'dll_built':False}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',required=True,action='store_true');p.parse_args();print(json.dumps(check(),sort_keys=True))
