"""Only public trusted CLI. Run with python -I -B and a root-checked SHA.
The literal inventory digest binds the payload; it does not attest this launcher
or a replaced interpreter/tree. Never import candidate code before verification.
"""
import builtins
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import types

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
INVENTORY_SHA256='fe47d0dc016fbaa523d0f5b0010cd879fb57f7dcd33fd4edce39800b9c0b5e9d'
MAX_FILES=256
MAX_EACH=2*1024*1024
MAX_TOTAL=20*1024*1024

def require(ok,why):
    if not ok:raise ValueError(why)

def _json(raw):
    def unique(pairs):
        out={}
        for k,v in pairs:
            require(k not in out,'Duplicate inventory key');out[k]=v
        return out
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))

def _ordinary(path,root,limit):
    path=Path(path);root=Path(root).resolve()
    require(path.is_absolute() and path.is_relative_to(root),'Source path outside root')
    current=path
    while True:
        st=current.lstat()
        require(not stat.S_ISLNK(st.st_mode) and not getattr(st,'st_file_attributes',0)&0x400,'Linked/reparse source')
        if current==root:break
        current=current.parent
    require(path.resolve()==path,'Noncanonical source')
    before=path.stat();require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and 0<before.st_size<=limit,'Bounded ordinary single-link source')
    with path.open('rb') as f:
        import os
        opened=os.fstat(f.fileno());require((opened.st_dev,opened.st_ino)==(before.st_dev,before.st_ino),'Changed source identity')
        raw=f.read(limit+1);after=os.fstat(f.fileno())
    require(len(raw)==before.st_size and len(raw)<=limit and (opened.st_size,opened.st_mtime_ns)==(after.st_size,after.st_mtime_ns),'Changed or oversized source')
    return raw

def _verify(root,here,expected):
    # Private fixture seam only. The public CLI never accepts roots or digests.
    root=Path(root).resolve();here=Path(here).resolve()
    require(here.is_relative_to(root),'Candidate root')
    raw=_ordinary(here/'inventory.json',root,128*1024)
    require(type(expected)is str and re.fullmatch('[0-9a-f]{64}',expected) and hashlib.sha256(raw).hexdigest()==expected,'Compiled inventory digest changed')
    obj=_json(raw);require(type(obj)is dict and set(obj)=={'schema','files'} and obj['schema']=='EU4SPYCLIENTINVENTORY/2','Exact inventory schema')
    files=obj['files'];require(type(files)is dict and 1<=len(files)<=MAX_FILES,'Inventory count')
    snapshot={};total=0
    for name,digest in files.items():
        require(type(name)is str and re.fullmatch('[A-Za-z0-9_./-]+',name) and str(PurePosixPath(name))==name and not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts,'Canonical relative source')
        require(type(digest)is str and re.fullmatch('[0-9a-f]{64}',digest),'Source SHA256')
        path=root.joinpath(*PurePosixPath(name).parts);data=_ordinary(path,root,MAX_EACH)
        total+=len(data);require(total<=MAX_TOTAL,'Source total budget')
        require(hashlib.sha256(data).hexdigest()==digest,'Changed verified payload '+name)
        snapshot[str(path)]=data
    for name in ('client.py','frozen.py','provenance.py','readonly.py','graph.py','pins.json','source-index.json'):
        require(str(here/name) in snapshot,'Required execution payload '+name)
    index=_json(snapshot[str(here/'source-index.json')]);require(type(index)is dict and set(index)=={'schema','files'} and type(index['schema'])is int and index['schema']==2,'Exact payload source index')
    expected_files=dict(files);expected_files.pop((here/'source-index.json').relative_to(root).as_posix())
    require(index['files']==expected_files,'Inventory/index exact file binding')
    return snapshot

def verified_graph():
    snapshot=_verify(ROOT,HERE,INVENTORY_SHA256)
    path=HERE/'graph.py';module=types.ModuleType('_v19_r2_verified_graph');module.__file__=str(path)
    # graph.py is already captured and verified. No sys.modules lookup occurs.
    exec(compile(snapshot[str(path)],str(path),'exec'),module.__dict__)
    return module.Graph(ROOT,HERE,snapshot)

def main(argv=None):
    require(sys.flags.isolated==1,'Run the trusted CLI with python -I -B')
    graph=verified_graph()
    return graph.local('client.py').main(argv)

if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError,RuntimeError) as exc:
        print(f'v19 R2 trusted client refused: {exc}; retain permanent files; never retry',file=sys.stderr);raise SystemExit(2)
