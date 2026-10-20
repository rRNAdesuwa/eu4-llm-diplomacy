"""One bounded read-only context diagnostic after the V24 terminal, no effects."""
import hashlib, importlib.util, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'work/run_pair24_session_r2_1375.py'
s=importlib.util.spec_from_file_location('_pair24_context_root',p)
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
assert sys.flags.isolated
c=m.verified_client();manifest=c.manifest()
identity=c.identity(m.PID,m.CREATION,'dfd56862d97a41dd56e3595228011b3a',manifest)
audit=c.inspect(identity);assert audit['terminal'] and not audit['complete']
ro=c.graph().local('readonly.py');h=ro.Held(identity)
try:
 h.identity_check();c.loaded(h,manifest,audit)
 base=[b for b,p in h.modules() if h.injector._canonical(p)==h.injector._canonical(h.injector.GAME)]
 assert len(base)==1;base=base[0];r=m.Reader(h);passes=[]
 for _ in range(2):
  game=r.at(base+0x233fe78);server=r.at(game+0x1e00)
  holder=r.at(server+0x330);context=r.at(holder+0x370);transport=r.at(context+0x58)
  vt=r.at(transport)
  passes.append(dict(game=game,server=server,server_vtable=r.at(server),holder=holder,context=context,transport=transport,
   transport_vtable=vt,instance_plus_30=r.at(transport+0x30),vtable_plus_30=r.at(vt+0x30),
   expected_transport_vtable=base+0x1d96178,expected_submit=base+0x1580370,
   ready55=r.at(context+0x55,1),ready80d=r.at(context+0x80d,1)))
 h.identity_check();assert passes[0]==passes[1]
 report=dict(identity=identity,read_only=True,effects_observed=False,passes=passes,equal=True,atomic=False,reads=r.calls,bytes=r.bytes,
  audit_sha256=audit['audit_sha256'],diagnostic_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
 m.dump_new(m.OUT/'submission-context.json',report);print(json.dumps(report))
finally:h.close()
