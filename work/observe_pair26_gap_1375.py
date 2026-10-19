"""One final read-only selected curry graph after the single-action batch."""
import ctypes as C, hashlib, json, runpy, types
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT/'work/candidates/v26-gap-curry-private-client-1375/client.py'
data = CLIENT.read_bytes()
assert hashlib.sha256(data).hexdigest() == '7eeb3f7e84c31e7694cd03351bbf00131a3e725ce23d74edc5885e11b459f928'
c = types.ModuleType('_checked_pair26'); c.__file__ = str(CLIENT)
exec(compile(data,str(CLIENT),'exec'), c.__dict__)
m = c.manifest(); identity = c.identity(55236,'01dd5a327a01c62a','087a283cb10ad7e2e09f5e22ff413496',m)
audit = c.inspect(identity)
assert audit['complete'] and not audit['terminal'] and audit['dispatched'] == 1
o = runpy.run_path(str(ROOT/'work/candidates/curry-favors-observer-1375/observer.py'))
o['dependencies'](o['contract']())
g = c.graph(); ro = g.local('readonly.py'); h = ro.Held(identity)
try:
    c.loaded(h,m,audit)
    bases = [b for b,p in h.modules() if h.injector._canonical(p)==h.injector._canonical(h.injector.GAME)]
    assert len(bases)==1
    class Reader:
        def __init__(self): self.calls=0; self.bytes=0
        def read(self,address,size):
            assert type(address)is int and 0x10000<=address<2**47 and 0<size<=65536 and address+size<2**47
            assert self.calls<4096 and self.bytes+size<=1024*1024
            self.calls+=1; self.bytes+=size
            buf=C.create_string_buffer(size); actual=C.c_size_t()
            if not h.kernel.ReadProcessMemory(h.handle,C.c_void_p(address),buf,size,C.byref(actual)) or actual.value!=size:
                raise OSError('Read-only memory unavailable')
            return buf.raw
    h.identity_check(); report = o['capture'](Reader(),bases[0]); h.identity_check()
    report['source_kind'] = 'held_process_readonly'
    report['process'] = dict(identity=dict(pid=identity['pid'],creation_filetime=identity['creation'],exit_filetime=0,module_base=bases[0]),
        path=str(h.injector.GAME),disk_exe_sha256=c.GAME_SHA,loaded_full_image_hash_verified=False,
        rights=['PROCESS_QUERY_INFORMATION','PROCESS_VM_READ'])
    o['inspect_capture'](report)
    out = ROOT/'work/runtime/v26-gap-curry-selected-55236.json'
    with out.open('x',encoding='ascii') as f: json.dump(report,f,indent=2,sort_keys=True); f.write('\n')
    print(json.dumps(dict(state=report['state'],reads=report['read_budget'],envoys=len(report['passes'][0]['envoys']['fields']['entries']))))
finally: h.close()
