"""Pinned pure helpers. No OS process APIs or mutable production API import."""
import hashlib
import importlib.util
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PINS = json.loads((HERE/'dependencies.json').read_bytes())
def load(name, path, digest=None):
    path=Path(path); raw=path.read_bytes()
    if digest is not None and hashlib.sha256(raw).hexdigest()!=digest: raise ValueError('Dependency changed: '+str(path))
    spec=importlib.util.spec_from_file_location(name,path); module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module); return module
_path='work/candidates/v19-spy-send-projection-1375/project.py'
t=load('_v19_interval_types',ROOT/_path,PINS[_path])
trace=load('_v19_preflight_trace',HERE/'preflight/native_trace.py')
wire=load('_v19_wire',HERE/'wire.py')
require=t.require
same=t.same
integer=t.integer
exact=t.exact
