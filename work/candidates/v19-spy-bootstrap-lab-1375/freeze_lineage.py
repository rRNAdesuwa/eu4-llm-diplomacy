"""Freeze explicit sealed predecessor bytes for the new bootstrap; file-only."""
from pathlib import Path
import hashlib,json

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
HOST=ROOT/'work/candidates/v19-spy-restricted-host-r2-1375'
HOST_REVIEW='b3553d5c291c83bf2d3159e7781f03dc521b90d1d4030f9ada78262e1243fcbd'
HOST_INDEX='dd029391a73b7582afbba2a8bfaacf854343ff54410ba98a68b5cf9eb25a0833'

def read(path,maximum=2*1024*1024):
    path=Path(path).absolute()
    for q in (path,*path.parents):
        if q.exists() and (q.is_symlink() or getattr(q.stat(),'st_file_attributes',0)&0x400):raise ValueError('Reparse path')
    with path.open('rb') as f:raw=f.read(maximum+1)
    if len(raw)>maximum:raise ValueError('Source budget')
    return raw

def desc(path):
    raw=read(path);return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}

def main():
    if desc(HOST/'review.json')['sha256']!=HOST_REVIEW or desc(HOST/'source-index.json')['sha256']!=HOST_INDEX:raise ValueError('Sealed Host identity')
    old=ROOT/'work/candidates/v18-spy-bootstrap-lab-1375'
    pins=json.loads(read(old/'predecessor-pins.json'))
    pins.update(json.loads(read(HERE/'v18-preimages.json')))
    index=json.loads(read(HOST/'source-index.json'))
    for name,pin in index['sources'].items():
        path=HOST/name
        if desc(path)!=pin:raise ValueError('Sealed Host source '+name)
        pins[path.relative_to(ROOT).as_posix()]=pin
    for name,pin in json.loads(read(HOST/'input-pins.json')).items():
        if name in pins and pins[name]!=pin:raise ValueError('Conflicting source pin')
        pins[name]=pin
    for name in ('review.json','source-index.json'):
        path=HOST/name;pins[path.relative_to(ROOT).as_posix()]=desc(path)
    if not 1<=len(pins)<=192:raise ValueError('Source inventory budget')
    total=0
    for name,pin in pins.items():
        path=(ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or name.startswith('bridge/'):raise ValueError('Source origin')
        actual=desc(path);total+=actual['bytes']
        if actual!=pin or total>16*1024*1024:raise ValueError('Changed/budgeted predecessor '+name)
    with (HERE/'predecessor-pins-r2.json').open('x',encoding='ascii',newline='\n') as f:f.write(json.dumps(pins,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'sources':len(pins),'bytes':total,'game_accessed':False,'compiled':False,'loaded':False}))

if __name__=='__main__':main()
