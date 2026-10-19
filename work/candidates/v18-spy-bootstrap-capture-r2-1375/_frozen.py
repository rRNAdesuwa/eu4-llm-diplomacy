"""Pinned, file-only dependencies from the original v18 build.

Their __file__ remains the original path, so original manifest verification
still refers to original sources. No old module, DLL or metadata is rewritten.
"""
from pathlib import Path
import hashlib,json,types

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OLD=ROOT/'work/candidates/v18-spy-bootstrap-lab-1375'
PIN_SHA='2fda82d505aab8fd1028f133a5a8d2f1434b9a0fe32ccfc5964ee07156a9f297'


def read(path,limit):
    with Path(path).open('rb')as stream:raw=stream.read(limit+1)
    if len(raw)>limit:raise ValueError('R2 dependency read budget')
    return raw


def sha(raw):return hashlib.sha256(raw).hexdigest()
pinraw=read(HERE/'input-pins.json',131072)
if sha(pinraw)!=PIN_SHA:raise ValueError('R2 lineage changed')
PINS=json.loads(pinraw)


def load(name):
    if name not in ('build_manifest.py','wire.py','native_trace.py'):raise ValueError('Fixed dependency names only')
    path=OLD/name;descriptor=PINS[path.relative_to(ROOT).as_posix()];raw=read(path,32768)
    if len(raw)!=descriptor['bytes']or sha(raw)!=descriptor['sha256']:raise ValueError('Frozen helper changed')
    module=types.ModuleType('_v18_capture_r2_'+name[:-3]);module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module


b=load('build_manifest.py');wire=load('wire.py');trace=load('native_trace.py')
