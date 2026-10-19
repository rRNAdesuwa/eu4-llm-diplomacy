"""Check the isolated fixed-core sources and lineage; no DLL/game operations."""
from pathlib import Path
import argparse,hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
PIN_SHA='429013ad3fdca8f82211ed7b070ec539eb6b6c40633502b02cb420272675b8fc'

def read(path,limit=8388608):
    path=path.absolute()
    for p in (path,*path.parents):
        if p.exists() and (p.is_symlink() or getattr(p.stat(),'st_file_attributes',0)&0x400):raise ValueError('Reparse source')
    with path.open('rb') as f:raw=f.read(limit+1)
    if len(raw)>limit:raise ValueError('Source byte budget')
    return raw

def desc(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}

def check():
    raw=read(HERE/'input-pins.json',131072)
    if desc(raw)['sha256']!=PIN_SHA:raise ValueError('Input index changed')
    pins=json.loads(raw);total=0
    if type(pins)is not dict or not 1<=len(pins)<=64:raise ValueError('Input count')
    for name,pin in pins.items():
        if name.startswith('bridge/'):raise ValueError('No mutable formal API dependency')
        path=(ROOT/name).resolve()
        if not path.is_relative_to(ROOT):raise ValueError('Input path')
        raw=read(path);total+=len(raw)
        if total>16777216 or desc(raw)!=pin:raise ValueError('Changed input '+name)
    for name,pin in json.loads(read(HERE/'preimage-index.json')).items():
        raw=read(HERE/'v18-preimage'/name)
        if desc(raw)!={k:pin[k] for k in ('bytes','sha256')} or raw!=read(ROOT/pin['source']):raise ValueError('v18 preimage differs')
    if read(HERE/'sender-pins.h')!=read(ROOT/'work/candidates/v19-spy-send-context-pins-1375/sender-pins.h'):raise ValueError('Sender constants differ')
    index=json.loads(read(HERE/'source-index.json',65536))
    if index['input_pins_sha256']!=PIN_SHA or len(index['sources'])>20:raise ValueError('Local index contract')
    for name,pin in index['sources'].items():
        path=(HERE/name).resolve()
        if not path.is_relative_to(HERE) or desc(read(path,262144))!=pin:raise ValueError('Local source changed '+name)
    return {'checked':True,'inputs':len(pins),'source_files':len(index['sources']),'game_access':False,'dll_built':False,'production_ready':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true',required=True);p.parse_args();print(json.dumps(check(),sort_keys=True))
