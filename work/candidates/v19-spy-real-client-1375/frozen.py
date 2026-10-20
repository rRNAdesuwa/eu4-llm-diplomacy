"""Exact private module graph; no loader/initializer entrypoint is invoked."""
import builtins
import hashlib
import json
from pathlib import Path
import types
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
BOOT=ROOT/'work/candidates/v19-spy-bootstrap-lab-1375'
PURE=ROOT/'work/candidates/v19-spy-real-journal-1375'
BUILD=BOOT/'build-attempt2'
DLL_SHA='d907f38e5bc108489b315a37b564d565b9fc4ff333012b62af586058691ab31f'
MANIFEST_SHA='b8e85393c96122949a60173ecec83f657a1d6dec24c5af0483aa7abb32d8e49a'
PINS=json.loads((HERE/'pins.json').read_bytes())
def require(ok,why):
    if not ok:raise ValueError(why)
def source(path):
    path=Path(path).resolve();name=path.relative_to(ROOT).as_posix();require(name in PINS,'Unpinned import')
    with path.open('rb') as f:raw=f.read(2*1024*1024+1)
    require(len(raw)<=2*1024*1024 and hashlib.sha256(raw).hexdigest()==PINS[name],'Changed source '+name);return raw
def load(name,path,mapping=None):
    path=Path(path).resolve();raw=source(path);module=types.ModuleType('_v19_private_'+name);module.__file__=str(path)
    normal=builtins.__import__;mapping=mapping or {}
    def private_import(name,globals=None,locals=None,fromlist=(),level=0):
        if level==0 and name in mapping:return mapping[name]
        return normal(name,globals,locals,fromlist,level)
    module.__dict__['__builtins__']=dict(vars(builtins),__import__=private_import)
    exec(compile(raw,str(path),'exec'),module.__dict__);return module
def verify_sources():
    require(len(PINS)<=256,'Source inventory budget');total=0
    for name in PINS:
        require(not name.startswith('bridge/'),'No mutable formal API dependency')
        total+=len(source(ROOT/name));require(total<=20*1024*1024,'Source total budget')
    return len(PINS)
verify_sources()
b=load('build',BOOT/'build_manifest.py')
wire=load('wire',BOOT/'wire.py')
fixed=load('fixed',PURE/'fixed.py')
interval=load('interval',PURE/'interval.py',{'fixed':fixed})
reader=load('reader',PURE/'reader.py',{'fixed':fixed,'interval':interval})
files=load('files',PURE/'files.py',{'fixed':fixed,'reader':reader})
loader=load('loader',BOOT/'loader.py',{'build_manifest':b,'wire':wire})
same=fixed.same;integer=fixed.integer;exact=fixed.exact
def verify_build(directory):
    directory=b.no_links(directory).resolve();require(directory==BUILD.resolve(),'Only sealed build-attempt2 directory')
    manifest,digest=b.verify_build(directory)
    same([digest,manifest['dll_sha256']],[MANIFEST_SHA,DLL_SHA])
    same(manifest['schema'],'EU4SPYSENDBUILD/1');same(manifest['purpose'],wire.PURPOSE)
    return manifest,digest
