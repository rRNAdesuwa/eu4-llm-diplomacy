"""Private imports from the launcher's verified byte snapshot.
No candidate module is taken from sys.modules, sys.path, pyc, or a later source
read. Sealed modules keep their original __file__ and unchanged source bytes.
"""
import builtins
import importlib.util
import sys
import types
from pathlib import Path
import uuid

class Graph:
    def __init__(self,root,here,snapshot):
        self.root=Path(root);self.here=Path(here);self.snapshot=dict(snapshot);self.cache={};self.active=set()
        pure=self.root/'work/candidates/v19-spy-real-journal-1375'
        boot=self.root/'work/candidates/v19-spy-bootstrap-lab-1375'
        self.paths={name:self.here/(name+'.py') for name in ('client','frozen','provenance','readonly')}
        self.paths.update({name:pure/(name+'.py') for name in ('fixed','interval','reader')})
        self.paths.update(protocol=pure/'preflight/protocol.py',build_manifest=boot/'build_manifest.py',wire=boot/'wire.py',
                          local_config=self.root/'work/local_config.py',probe_native_state=self.root/'work/probe_native_state.py',inject_probe=self.root/'work/native/inject_probe.py')
        self.sys=types.ModuleType('_v19_private_sys');self.sys.__dict__.update(vars(sys));self.sys.path=list(sys.path);self.sys.modules={}
        util=types.ModuleType('_v19_private_importlib_util');util.__dict__.update(vars(importlib.util))
        graph=self
        class Loader:
            def __init__(self,path):self.path=Path(path)
            def create_module(self,spec):return None
            def exec_module(self,module):graph.execute(self.path,module.__dict__)
        def spec(name,path,*args,**kwargs):
            graph.source(path)
            return importlib.util.spec_from_loader(name,Loader(path),origin=str(path))
        util.spec_from_file_location=spec
        self.importlib=types.ModuleType('_v19_private_importlib');self.importlib.util=util
    def source(self,path):
        path=Path(path).resolve();key=str(path)
        if key not in self.snapshot:raise ValueError('Unverified execution source '+key)
        return self.snapshot[key]
    def _import(self,name,globals=None,locals=None,fromlist=(),level=0):
        if level==0 and name in self.paths:return self.load(self.paths[name])
        if level==0 and name=='sys':return self.sys
        if level==0 and name in ('importlib','importlib.util'):
            return self.importlib.util if fromlist and name=='importlib.util' else self.importlib
        return builtins.__import__(name,globals,locals,fromlist,level)
    def _exec(self,code,globals=None,locals=None):
        if not isinstance(code,types.CodeType) or globals is None or (locals is not None and locals is not globals):
            raise ValueError('Only verified module execution')
        return self.execute(Path(code.co_filename),globals)
    def execute(self,path,namespace):
        path=Path(path).resolve();raw=self.source(path)
        namespace['__file__']=str(path)
        namespace['__builtins__']=dict(vars(builtins),__import__=self._import,exec=self._exec)
        namespace['__verified_source__']=self.source;namespace['__verified_load__']=self.load
        # dataclasses with deferred annotations consult sys.modules by a class's
        # __module__. A fresh unguessable name is registered only during eval;
        # no existing cached module is read or replaced.
        old_name=namespace.get('__name__');name='_v19_r2_'+uuid.uuid4().hex
        if name in sys.modules:raise ValueError('Private module-name collision')
        namespace['__name__']=name
        holder=types.ModuleType(name);holder.__dict__.update(namespace);sys.modules[name]=holder
        try:
            builtins.exec(compile(raw,str(path),'exec'),namespace)
        finally:sys.modules.pop(name,None)
    def load(self,path):
        path=Path(path).resolve();key=str(path)
        if key in self.cache:return self.cache[key]
        if key in self.active:raise ValueError('Unexpected private import cycle '+key)
        self.source(path);self.active.add(key)
        module=types.ModuleType('_v19_r2_payload');module.__file__=key
        try:self.execute(path,module.__dict__)
        finally:self.active.remove(key)
        self.cache[key]=module;return module
    def local(self,name):
        if name not in ('client.py','frozen.py','provenance.py','readonly.py'):raise ValueError('Unknown local module')
        return self.load(self.here/name)
