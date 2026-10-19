"""Aggregated final read-only snapshot after frozen V27 batch; never sends."""
import ctypes as C, hashlib, json, runpy, struct, types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CLIENT=ROOT/'work/candidates/v27-gap-private-client-1375/client.py'
data=CLIENT.read_bytes()
assert hashlib.sha256(data).hexdigest()=='c0f447e053d2827ce96dca89cc083e7959a48ebb1d5c9e2603821259ffcc0bd1'
c=types.ModuleType('_checked_pair27'); c.__file__=str(CLIENT)
exec(compile(data,str(CLIENT),'exec'),c.__dict__)
m=c.manifest(); identity=c.identity(53332,'01dd5a391fb55b9c','f461729ab8ee8de01ba28e6c32064bc5',m)
audit=c.inspect(identity)
assert audit['terminal'] and audit['dispatched']==2 and not audit['complete']
insult_path=ROOT/'work/candidates/ordinary-insult-observer-1375/observer.py'
assert hashlib.sha256(insult_path.read_bytes()).hexdigest()=='708adae32bf5f16db3678b70ffedb6e855ff8755fd0456044f666db1b4595638'
o=runpy.run_path(str(insult_path)); contract=o['load_contract']()
fleet=runpy.run_path(str(ROOT/'work/probe_pair_extension_v10_1375.py'))
g=c.graph(); h=g.local('readonly.py').Held(identity)
try:
    c.loaded(h,m,audit)
    bases=[b for b,p in h.modules() if h.injector._canonical(p)==h.injector._canonical(h.injector.GAME)]
    assert len(bases)==1
    class Reader:
        def __init__(self): self.calls=0; self.bytes=0
        def read(self,address,size):
            assert type(address)is int and 0x10000<=address<2**47 and 0<size<=65536 and address+size<2**47
            assert self.calls<8192 and self.bytes+size<=2*1024*1024
            self.calls+=1; self.bytes+=size
            buf=C.create_string_buffer(size); actual=C.c_size_t()
            if not h.kernel.ReadProcessMemory(h.handle,C.c_void_p(address),buf,size,C.byref(actual)) or actual.value!=size:
                raise OSError('Read-only memory unavailable')
            return buf.raw
        def qword(self,p): return struct.unpack('<Q',self.read(p,8))[0]
        def dword(self,p): return struct.unpack('<I',self.read(p,4))[0]
    reader=Reader(); h.identity_check()
    observations={}
    for name,fn in [('insult_NAV',lambda:o['capture'](reader,bases[0],'NAV',contract)),
                    ('offer_fleet_basing_rights_ENG',lambda:fleet['capture'](reader,bases[0],'ENG','offer_fleet_access'))]:
        try: observations[name]=fn()
        except Exception as exc: observations[name]={'observation_error':str(exc),'unknown':True}
    h.identity_check()
    report={'schema':'pair27_final_readonly_1375_1','read_only':True,'atomic_snapshot':False,
        'process':{'pid':identity['pid'],'creation':identity['creation'],'module_base':bases[0]},
        'audit_dispatched':2,'audit_terminal':True,'observations':observations,
        'reader_budget':{'calls':reader.calls,'bytes':reader.bytes},'request_causality_verified':False}
    out=ROOT/'work/runtime/v27-gap-final-selected-53332.json'
    with out.open('x',encoding='ascii') as f: json.dump(report,f,indent=2,sort_keys=True); f.write('\n')
    print(json.dumps({'output':str(out),'states':{k:v.get('state',v.get('observation_error')) for k,v in observations.items()},'budget':report['reader_budget']}))
finally: h.close()
