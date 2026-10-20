"""Verify the isolated pure-model revision; never materialize old sources."""
from pathlib import Path
import argparse,hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
PIN_SHA='daef9191acd57995805efefd695b88e8ba79042dd6ec1a444ec3e6e910da830a'

def read(path,limit=8388608):
    path=path.absolute()
    for node in (path,*path.parents):
        if node.exists():
            if node.is_symlink() or getattr(node.stat(),'st_file_attributes',0)&0x400:raise ValueError('Reparse input')
    with path.open('rb') as stream:raw=stream.read(limit+1)
    if len(raw)>limit:raise ValueError('Read budget')
    return raw

def desc(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}

def check():
    raw=read(HERE/'input-pins.json',131072)
    if desc(raw)['sha256']!=PIN_SHA:raise ValueError('Lineage replaced')
    pins=json.loads(raw);total=0
    if type(pins)is not dict or not 1<=len(pins)<=64:raise ValueError('Lineage count')
    for name,pin in pins.items():
        path=(ROOT/name).resolve()
        if not path.is_relative_to(ROOT):raise ValueError('Escaped input')
        raw=read(path);total+=len(raw)
        if total>33554432 or desc(raw)!=pin:raise ValueError('Lineage budget/hash: '+name)
    index=json.loads(read(HERE/'source-index.json',65536))
    if index['input_pins_sha256']!=PIN_SHA or not 1<=len(index['sources'])<=10:raise ValueError('Index contract')
    for name,pin in index['sources'].items():
        path=(HERE/name).resolve()
        if not path.is_relative_to(HERE) or desc(read(path,131072))!=pin:raise ValueError('Local source changed')
    old=ROOT/'work/candidates/v19-spy-send-plan-1375'
    for name in ('contract.json','test_model.py'):
        if read(HERE/name)!=read(old/name):raise ValueError('Unchanged baseline differs')
    return {'checked':True,'lineage_inputs':len(pins),'sources':len(index['sources']),'native_calls_performed':False,'production_ready':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true',required=True);parser.parse_args();print(json.dumps(check(),sort_keys=True))
