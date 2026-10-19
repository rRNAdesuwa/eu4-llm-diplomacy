"""Bounded read-only gold prerequisites after completed V28; never calls game."""
import ctypes as C,hashlib,json,struct,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'work/candidates/v28-gap-private-client-1375/client.py';b=p.read_bytes()
assert hashlib.sha256(b).hexdigest()=='e0837871896f515d5a0b52d9e64f9963120c26746b411a1cc83e850b1765ea35'
c=types.ModuleType('_checked_pair28');c.__file__=str(p);exec(compile(b,str(p),'exec'),c.__dict__)
m=c.manifest();id=c.identity(53368,'01dd5a3c4a3a4112','33e247789f70e2c8162ca01d5abbc645',m);a=c.inspect(id)
assert a['complete'] and not a['terminal'] and a['dispatched']==3
h=c.graph().local('readonly.py').Held(id)
try:
 c.loaded(h,m,a);base=next(b for b,p in h.modules() if h.injector._canonical(p)==h.injector._canonical(h.injector.GAME))
 calls=0;total=0
 def read(p,n):
  global calls,total
  assert 0x10000<=p<p+n<2**47 and 0<n<=4096 and calls<128 and total+n<16384
  calls+=1;total+=n;buf=C.create_string_buffer(n);got=C.c_size_t()
  assert h.kernel.ReadProcessMemory(h.handle,C.c_void_p(p),buf,n,C.byref(got)) and got.value==n
  return buf.raw
 def q(p):return struct.unpack('<Q',read(p,8))[0]
 def i(p):return struct.unpack('<i',read(p,4))[0]
 def once():
  db=q(base+0x233d8d0);game=q(base+0x233fe78);array=q(db+0x118);actor=q(array+122*8);target=q(array+189*8)
  assert q(actor)==q(target)==base+0x1c574a0 and q(actor+0x20)==0x0100007a00415246 and q(target+0x20)==0x010000bd00524f50
  records=q(target+0x1510);reverse=q(actor+0x1510);record=records+122*0x48;other=reverse+189*0x48
  assert q(record+0x10)==q(actor+0x20) and q(other+0x10)==q(target+0x20)
  start=q(actor+0xeb8);end=q(actor+0xec0);assert 0<=end-start<=2048 and (end-start)%8==0
  cooldowns=read(start,end-start) if start!=end else b''
  op=q(target+0x2380);oe=q(target+0x2388);assert 0<=oe-op<=32768
  return {'date':i(game+0x1dd0),'actor_treasury_milli':i(actor+0xbb0),'target_treasury_milli':i(target+0xbb0),
   'target_flag_289b':read(target+0x289b,1)[0],'target_last_favor_date_e00':i(target+0xe00),
   'target_record_actor_favors_milli':i(record+0x20),'actor_record_target_favors_milli':i(other+0x20),
   'target_cached_opinion_actor':struct.unpack('<h',read(op+244,2))[0] if oe-op>244 else None,
   'actor_action_cooldowns':[list(v) for v in struct.iter_unpack('<Ii',cooldowns)]}
 h.identity_check();passes=[once(),once()];h.identity_check();assert passes[0]==passes[1]
 report={'read_only':True,'pid':id['pid'],'creation':id['creation'],'two_pass_equal':True,'passes':passes,'budget':{'calls':calls,'bytes':total},'semantic_labels_static_only':True}
 out=ROOT/'work/runtime/v28-gap-gold-conditions-53368.json'
 with out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
 print(json.dumps(report))
finally:h.close()
