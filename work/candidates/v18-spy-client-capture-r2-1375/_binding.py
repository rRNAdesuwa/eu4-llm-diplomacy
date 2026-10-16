"""Fixed private imports. Original __file__/bytes and DLL identity are preserved."""
from pathlib import Path
import builtins, hashlib, json, types

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OLD=ROOT/'work/candidates/v18-spy-bootstrap-lab-1375'
R2=ROOT/'work/candidates/v18-spy-bootstrap-capture-r2-1375'
PIN_SHA='3bad827be55a80a01cccf585984e7707dd36aef78672101a09ec87169ab6be29'
MAX_FILE=2*1024*1024

def require(ok,why):
    if not ok:raise ValueError(why)

def read(path,limit=MAX_FILE):
    path=Path(path).absolute()
    for node in (path,*path.parents):
        if node.exists():require(not node.is_symlink() and not(getattr(node.stat(),'st_file_attributes',0)&0x400),'Reparse dependency')
    with path.open('rb') as stream:raw=stream.read(limit+1)
    require(len(raw)<=limit,'Wrapper dependency read budget')
    return raw

def sha(raw):return hashlib.sha256(raw).hexdigest()

def _pins():
    raw=read(HERE/'input-pins.json',131072)
    require(sha(raw)==PIN_SHA,'Wrapper lineage changed')
    pins=json.loads(raw)
    require(type(pins)is dict and 1<=len(pins)<=128,'Wrapper lineage bound')
    return pins

PINS=_pins()

def _source(path):
    path=path.resolve();require(path.is_relative_to(ROOT),'Escaped dependency')
    name=path.relative_to(ROOT).as_posix();require(name in PINS,'Unlisted dependency')
    raw=read(path);require(PINS[name]=={'bytes':len(raw),'sha256':sha(raw)},'Frozen dependency changed: '+name)
    return raw

def _module(path,aliases):
    # Alias maps are private constants below, not CLI/request arguments. No
    # sys.path edits or sys.modules replacements, and no replacement validator.
    raw=_source(path)
    normal=builtins.__import__
    def import_fixed(name,globals=None,locals=None,fromlist=(),level=0):
        if level==0 and name in aliases:return aliases[name]
        return normal(name,globals,locals,fromlist,level)
    module=types.ModuleType('_spy18_client_r2_'+path.stem)
    module.__file__=str(path)
    module.__dict__['__builtins__']=dict(vars(builtins),__import__=import_fixed)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module

_frozen=_module(R2/'_frozen.py',{})
reader=_module(R2/'real_capture.py',{'_frozen':_frozen})
loader=_module(OLD/'loader.py',{'build_manifest':_frozen.b,'wire':_frozen.wire})
client=_module(OLD/'client.py',{'build_manifest':_frozen.b,'wire':_frozen.wire,'loader':loader,'real_capture':reader})

def check():
    require(_pins()==PINS,'Lineage replaced after import')
    total=0
    for name in sorted(PINS):
        raw=_source(ROOT/name);total+=len(raw)
        require(total<=16*1024*1024,'Lineage total budget')
    index=json.loads(read(HERE/'candidate-index.json',65536))
    require(index['input_pins_sha256']==PIN_SHA and 1<=len(index['sources'])<=12,'Wrapper index')
    for name,pin in index['sources'].items():
        path=(HERE/name).resolve();require(path.is_relative_to(HERE),'Escaped wrapper source')
        raw=read(path);require(pin=={'bytes':len(raw),'sha256':sha(raw)},'Wrapper source changed: '+name)
    require(Path(client.__file__)==OLD/'client.py' and Path(loader.__file__)==OLD/'loader.py','Original source origins')
    require(Path(reader.__file__)==R2/'real_capture.py','Reader revision origin')
    require(client.real_capture is reader and client.loader is loader and client.b is _frozen.b and client.wire is _frozen.wire,'Private dependency roles')
    require(loader.build is client.b and reader.b is client.b and reader.wire is client.wire,'Same original build/identity authority')
    manifest,digest=client.b.verify_build(OLD/'build-final')
    require(digest==index['original_manifest_sha256'] and manifest['dll_sha256']==index['original_dll_sha256'],'Original DLL/manifest identity')
    return {'checked':True,'lineage_inputs':len(PINS),'original_manifest_sha256':digest,'original_dll_sha256':manifest['dll_sha256'],
            'reader_sha256':sha(_source(R2/'real_capture.py')),'reader_revision':'v18-spy-bootstrap-capture-r2-1375',
            'native_recompiled':False,'runtime_verified':False,'production_ready':False}
