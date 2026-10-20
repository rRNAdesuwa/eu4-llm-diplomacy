"""Post-terminal RO diagnosis only. No native functions, requests or UI calls."""
import ctypes as C, hashlib, json, os, struct, sys, types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'work/run_pair22_session_1375.py';raw=p.read_bytes()
module=types.ModuleType('_pair22_root_diagnostic');module.__file__=str(p)
exec(compile(raw,str(p),'exec'),module.__dict__)
client=module.verified_client();g=client.graph();ro=g.local('readonly.py');m=client.manifest()
id=client.identity(module.PID,module.CREATION,'60c7109d7d019ebd0fae0ba52e986fd8',m)
h=ro.Held(id)
try:
    base=[b for b,p in h.modules() if h.injector._canonical(p)==h.injector._canonical(h.injector.GAME)][0]
    h.identity_check();r=module.Reader(h);world=r.roots(base);game=world['game'];rows=[];tags=set();handles=set();ptrs=set();failures=[]
    data=r.read(world['array'],world['count']*8)
    for slot in range(world['count']):
        p=struct.unpack_from('<Q',data,slot*8)[0];row=dict(slot=slot,pointer=p)
        if p:
            row['header_hex']=r.read(p,12).hex();vt=int.from_bytes(bytes.fromhex(row['header_hex'])[:8],'little');marker=int.from_bytes(bytes.fromhex(row['header_hex'])[8:],'little')
            if vt!=base+0x1c574a0 or marker!=0x165:failures.append(dict(slot=slot,reason='country type before handle',vt=vt,marker=marker))
            else:
                handle=r.at(p+0x20);tag=(handle&0xffffff).to_bytes(3,'little').decode('ascii','replace');row.update(handle=handle,tag=tag)
                if p in ptrs or handle in handles:failures.append(dict(slot=slot,reason='duplicate pointer/handle'))
                if slot==0 and handle==0x2d2d2d:row['sentinel']=True
                else:
                    if slot==0 or (handle>>32)&65535!=slot:failures.append(dict(slot=slot,reason='complete handle ordinal',handle=handle))
                    if handle>>56==0 or (handle>>48)&255 or (handle>>24)&255 or any(not ('A'<=c<='Z' or '0'<=c<='9') for c in tag):failures.append(dict(slot=slot,reason='research generation/type/ASCII profile',handle=handle,tag=tag))
                    if tag in tags:failures.append(dict(slot=slot,reason='duplicate TAG',tag=tag))
                    tags.add(tag)
                ptrs.add(p);handles.add(handle)
        rows.append(row)
    health=dict(reset=r.at(game+0x7485,1),load_source=r.at(game+0x74c8),ironman=r.at(game+0x24d0,1),selector=r.at(game+0x1e66,1),alternate_selector=r.at(game+0x1e6f,1),speed=r.at(game+0x1e08,1),alternate=r.at(game+0x1e68))
    server=r.at(game+0x1e00);pause=r.at(server+0x418)
    health.update(server=server,server_vt=r.at(server)-base,pause=pause,pause_back=r.at(pause+0x50),manual_pause=r.at(pause+0x48,1),pause_begin=r.at(pause),pause_end=r.at(pause+8),server_gate=r.at(server+0x19f1,1))
    if health['server_gate']:
        holder=r.at(server+0x330);context=r.at(holder+0x370)
        health.update(context=context,context54=r.at(context+0x54,1),context55=r.at(context+0x55,1),local=r.at(context+0x8c,4),players_node=r.at(game+0xa50))
    h.identity_check();module.need(r.roots(base)==world,'Changed diagnostic roots')
    report=dict(schema='EU4PAIR22LEASEDIAG/1',identity=id,base=base,world=world,health=health,country_rows=rows,resolver_profile_failures=failures,read_only=True,native_calls=0,reads=r.calls,bytes=r.bytes,root_helper_sha256=hashlib.sha256(raw).hexdigest(),observer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    module.dump_new(module.OUT/'lease-diagnostic.json',report)
    print(json.dumps(dict(health=health,count=world['count'],resolver_profile_failures=failures[:12],total_failures=len(failures),reads=r.calls,bytes=r.bytes)))
finally:h.close()
