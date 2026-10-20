"""Two-pass bounded read-only aggregate snapshot. Never calls game functions."""
import argparse,ctypes as C,hashlib,json,struct,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--stage',required=True,choices=['before','after']);p.add_argument('--session',default='1'*32);a=p.parse_args()
path=ROOT/'work/candidates/v29-gap-private-client-1375/client.py';b=path.read_bytes()
assert hashlib.sha256(b).hexdigest()=='fa6f5d73bbef94df7ba4611542cab364bc3e6fb0bb9d090e67c1e67c3522d148'
c=types.ModuleType('_checked_pair29');c.__file__=str(path);exec(compile(b,str(path),'exec'),c.__dict__)
m=c.manifest();identity=c.identity(37816,'01dd5a40957e7dea',a.session,m)
h=c.graph().local('readonly.py').Held(identity)
calls=total=0
try:
 h.identity_check();base=next(b for b,p in h.modules() if h.injector._canonical(p)==h.injector._canonical(h.injector.GAME))
 def read(p,n):
  global calls,total
  assert 0x10000<=p<p+n<2**47 and 0<n<=4096 and calls<10000 and total+n<262144
  calls+=1;total+=n;buf=C.create_string_buffer(n);got=C.c_size_t()
  assert h.kernel.ReadProcessMemory(h.handle,C.c_void_p(p),buf,n,C.byref(got)) and got.value==n
  return buf.raw
 def q(p):return struct.unpack('<Q',read(p,8))[0]
 def i(p):return struct.unpack('<i',read(p,4))[0]
 def once():
  db=q(base+0x233d8d0);game=q(base+0x233fe78);array=q(db+0x118);count=i(db+0x124);assert 0<count<=4096
  wanted={'FRA','POR','ENG','BRI','NAV','SCO'};countries={}
  for off in range(0,count*8,4096):
   pointers=struct.unpack('<'+'Q'*(min(4096,count*8-off)//8),read(array+off,min(4096,count*8-off)))
   for j,ptr in enumerate(pointers):
    if not ptr:continue
    handle=q(ptr+0x20);tag=(handle&0xffffffff).to_bytes(4,'little').rstrip(b'\0').decode('ascii',errors='ignore')
    if tag not in wanted:continue
    ordinal=off//8+j;assert (handle>>32)&0xffff==ordinal and q(ptr)==base+0x1c574a0 and tag not in countries
    countries[tag]=(ptr,ordinal,handle)
  assert set(countries)==wanted
  actor,ordinal,handle=countries['FRA'];records=q(actor+0x1510);selected={}
  for tag,(ptr,slot,full) in countries.items():
   fields={'ordinal':slot,'handle':hex(full),'treasury_milli':i(ptr+0xbb0),'manpower_milli':i(ptr+0xdb8),'sailors_milli':i(ptr+0xdc0),
    'war_prep_date':i(ptr+0x2728),'war_prep_actor':hex(q(ptr+0x272c)),'last_favor_date':i(ptr+0xe00)}
   if tag!='FRA':
    record=q(ptr+0x1510)+ordinal*0x48;other=records+slot*0x48
    assert q(record+0x10)==handle and q(other+0x10)==full
    income=struct.unpack('<19i',read(ptr+0x770,76));expenses=struct.unpack('<38i',read(ptr+0x7bc,152))
    fields.update(target_record_actor_favors_milli=i(record+0x20),target_trust_actor=read(record+0x1e,1)[0],actor_trust_target=read(other+0x1e,1)[0],
     cached_income=list(income),cached_expenses=list(expenses),selected_monthly_balance_milli=sum(income[x] for x in [0,1,2,3,4,5,6,7,8,15,16])-sum(expenses[x] for x in [0,1,2,3,4,5,6,7,8,9,10,15,21,22,23,24,25,26,27,30,31,33,34]))
   selected[tag]=fields
  return {'date':i(game+0x1dd0),'player':hex(q(game+0x1e60)),'trust_amount':i(base+0x233db7c),'trust_cost':i(base+0x233db80),'countries':selected}
 passes=[once(),once()];h.identity_check();assert passes[0]==passes[1]
 if a.stage=='after':
  audit=c.inspect(identity);assert audit['complete'] and not audit['terminal'];c.loaded(h,m,audit)
 report={'schema':'pair29_readonly_aggregate_v1','stage':a.stage,'identity':identity,'read_only':True,'two_pass_equal':True,'passes':passes,'budget':{'calls':calls,'bytes':total},'causality_proven':False}
 out=ROOT/f'work/runtime/v29-gap-favors-{a.stage}-37816.json'
 with out.open('x',encoding='utf8') as f:json.dump(report,f,indent=2);f.write('\n')
 print(json.dumps({'path':str(out),'budget':report['budget'],'sample':passes[0]}))
finally:h.close()
