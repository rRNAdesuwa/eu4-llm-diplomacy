"""Pinned private R2 dependencies; no source/manifest rewriting."""
from pathlib import Path
import hashlib,json,types
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
R2CLIENT=ROOT/'work/candidates/v18-spy-client-capture-r2-1375'
PIN_SHA='c4a1bceb6c82cf7a8457a311f79a92fcea077307ced50aecf6ac7ad7d26bd4c8'
def require(ok,why):
    if not ok:raise ValueError(why)
def read(path,limit):
    path=Path(path).absolute()
    for p in (path,*path.parents):
        if p.exists():require(not p.is_symlink() and not(getattr(p.stat(),'st_file_attributes',0)&0x400),'Reparse source')
    with path.open('rb') as f:raw=f.read(limit+1)
    require(len(raw)<=limit,'Source read budget');return raw
def sha(raw):return hashlib.sha256(raw).hexdigest()
pinraw=read(HERE/'input-pins.json',196608);require(sha(pinraw)==PIN_SHA,'Pinned lineage changed');PINS=json.loads(pinraw)
def source(path):
    path=path.resolve();require(path.is_relative_to(ROOT),'Source outside root');name=path.relative_to(ROOT).as_posix()
    raw=read(path,2097152);require(name in PINS and PINS[name]=={'bytes':len(raw),'sha256':sha(raw)},'Source changed: '+name);return raw
base=types.ModuleType('_private_spy18_r2_binding');base.__file__=str(R2CLIENT/'_binding.py')
exec(compile(source(Path(base.__file__)),base.__file__,'exec'),base.__dict__)
def check():
    require(sha(read(HERE/'input-pins.json',196608))==PIN_SHA,'Lineage replaced');total=0
    require(type(PINS)is dict and len(PINS)<=128,'Lineage count')
    for name in PINS:
        total+=len(source(ROOT/name));require(total<=16777216,'Lineage total')
    index=json.loads(read(HERE/'source-index.json',65536));require(index['input_pins_sha256']==PIN_SHA and len(index['sources'])<=10,'Source index')
    for name,pin in index['sources'].items():
        p=(HERE/name).resolve();require(p.is_relative_to(HERE),'Escaped helper');raw=read(p,131072)
        require(pin=={'bytes':len(raw),'sha256':sha(raw)},'R3 helper changed')
    result=base.check();result['coherent_reader_revision']='v18 health-tail R3';result['max_read_attempts']=3;return result
