"""Root-owned, one-use V22 operation recorder and bounded RO group diagnostic.

No UI automation. Native loading/publication is only through the separately
sealed client. Diagnostic absence never establishes rejection or full effects.
"""
import argparse, ctypes as C, hashlib, json, os, struct, subprocess, sys, types
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HERE=ROOT/'work/candidates/v22-pair-private-client-r2-1375'
CLIENT_SHA='92af9ef91e0aad41c4d1b9b39ca8d2d325d434066157de1fad5c704839b9c03d'
INDEX_SHA='551671c8ae9fa5fb6b2cb00a8d28e9f03830ca2056a74a436a3d36b29fb55ff6'
PINS_SHA='bdf93948601af0e223ca082ef498f8fe263969bef4f9f0dbd92a4a4ab46fa326'
OUT=ROOT/'work/runtime/pair22-session-20261012a'
PID=50684
CREATION='01dd5a131399ebb8'
HANDLES={'FRA':0x0100007a00415246,'ENG':0x0100002e00474e45}

def need(ok,why):
    if not ok:raise ValueError(why)
def sha(b):return hashlib.sha256(b).hexdigest()
def bounded(p,n):
    p=Path(p);s=p.stat();need(0<s.st_size<=n and s.st_nlink==1,'File budget/link')
    cursor=p
    while cursor!=ROOT.parent:
        t=cursor.lstat();need(not cursor.is_symlink() and not getattr(t,'st_file_attributes',0)&0x400,'Reparse path')
        if cursor==ROOT:break
        cursor=cursor.parent
    need(p.is_relative_to(ROOT) and p.resolve()==p,'Fixed root path')
    with p.open('rb') as f:
        a=os.fstat(f.fileno());b=f.read(n+1);z=os.fstat(f.fileno())
    need(len(b)==s.st_size and (s.st_dev,s.st_ino)==(a.st_dev,a.st_ino) and (a.st_size,a.st_mtime_ns)==(z.st_size,z.st_mtime_ns),'Changed input')
    return b
def dump_new(p,obj):
    with p.open('x',encoding='ascii',newline='\n') as f:
        json.dump(obj,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
def verified_client():
    data=bounded(HERE/'client.py',65536);need(sha(data)==CLIENT_SHA,'External client SHA')
    idx=bounded(HERE/'source-index.json',65536);need(sha(idx)==INDEX_SHA,'External source index SHA')
    pins=bounded(HERE/'input-pins.json',131072);need(sha(pins)==PINS_SHA,'External input pins SHA')
    for root,values in ((HERE,json.loads(idx)),(ROOT,json.loads(pins))):
        need(len(values)<=512,'Pin count')
        for name,pin in values.items():
            p=root/name;need(p.is_relative_to(ROOT) and '..' not in Path(name).parts,'Relative pin')
            b=bounded(p,4*1024*1024);need({'bytes':len(b),'sha256':sha(b)}==pin,'Changed pin '+name)
    module=types.ModuleType('_root_pair22_checked_client');module.__file__=str(HERE/'client.py')
    exec(compile(data,module.__file__,'exec'),module.__dict__)
    return module

class Reader:
    def __init__(self,held):self.h=held;self.calls=0;self.bytes=0
    def read(self,a,n):
        need(type(a)is int and 0x10000<=a<2**47 and 0<n<=65536 and a+n<2**47,'RO address/size')
        need(self.calls<8192 and self.bytes+n<=1024*1024,'Shared diagnostic budget')
        self.calls+=1;self.bytes+=n;b=C.create_string_buffer(n);actual=C.c_size_t()
        need(self.h.kernel.ReadProcessMemory(self.h.handle,C.c_void_p(a),b,n,C.byref(actual)) and actual.value==n,'RO memory unavailable')
        return b.raw
    def at(self,a,n=8):return int.from_bytes(self.read(a,n),'little')
    def typed(self,p,vt,marker=0x165):
        need(p>=0x10000 and p%8==0 and self.at(p)==vt and self.at(p+8,4)==marker,'Native type/marker')
    def roots(self,base):
        db=self.at(base+0x233d8d0);game=self.at(base+0x233fe78);arr=self.at(db+0x118)
        cap=self.at(db+0x120,4);count=self.at(db+0x124,4);need(123<=count<=cap<=4096,'Country count')
        countries={}
        for tag,h in HANDLES.items():
            p=self.at(arr+((h>>32)&65535)*8);self.typed(p,base+0x1c574a0)
            need(self.at(p+0x20)==h,'Full country handle');countries[tag]=p
        date=self.at(game+0x1dd0,4);player=self.at(game+0x1e60)
        need(0<date<=0x7fffffff and player==HANDLES['FRA'],'Paused baseline country/date')
        return dict(database=db,game=game,array=arr,capacity=cap,count=count,date=date,player=player,countries=countries)
    def index(self,country,owner,other,offset,count):
        records=self.at(country+0x1510);rec=records+((other>>32)&65535)*0x48;root=self.at(rec)
        need(self.at(rec+8)==owner and self.at(rec+16)==other,'Current relation record handles')
        arr=self.at(root+offset);cap=self.at(root+offset+8,4);size=self.at(root+offset+12,4)
        need(0<=size<=cap<=4096 and (arr!=0 if cap else arr==0),'Index bounds')
        data=self.read(arr,size*16) if size else b'';seen=set();objects=set();selected=0
        for i in range(size):
            slot,p=struct.unpack_from('<I4xQ',data,i*16)
            need(slot<count and slot not in seen and p>=0x10000 and p%8==0 and p not in objects,'Index identity')
            seen.add(slot);objects.add(p)
            if slot==((other>>32)&65535):selected=p
        need(self.at(country+0x1510)==records and self.at(rec)==root and self.at(root+offset)==arr and self.at(root+offset+8,4)==cap and self.at(root+offset+12,4)==size,'Changed index header')
        return dict(root=root,array=arr,count=size,capacity=cap,selected=selected)
    def sample(self,base):
        world=self.roots(base);fra=world['countries']['FRA'];eng=world['countries']['ENG'];pair={}
        for name,aoff,boff,vt in [('offer_vassalization',0x128,0x128,0x1c81758),('royal_marriage',0x68,0x68,0x1c80be0),('improve_relations',0x1d0,0x1e8,0x1c81658),('guarantee',0x1a0,0x1a0,0x1c817d8),('curry_favors',0x158,None,0x1c7b178)]:
            left=self.index(fra,HANDLES['FRA'],HANDLES['ENG'],aoff,world['count'])
            right=self.index(eng,HANDLES['ENG'],HANDLES['FRA'],boff,world['count']) if boff is not None else None
            obj=left['selected'];body=None
            if obj:
                self.typed(obj,base+vt);body=self.read(obj,0x40).hex()
            pair[name]=dict(outgoing=left,reciprocal=right,selected_body_hex=body)
        holder=self.at(fra+0x1480);hend=self.at(fra+0x1488);hcap=self.at(fra+0x1490)
        need(holder>=0x10000 and holder%8==0 and hend>=holder+32 and hcap>=hend and (hend-holder)%8==0 and (hcap-holder)%8==0 and hcap-holder<=128,'Manager holder bounds')
        manager=self.at(holder+24);self.typed(manager,base+0x1cac380)
        need(self.at(manager+16,4)==0x2746 and self.at(manager+20,1)==3 and self.at(manager+22)==HANDLES['FRA'],'Diplomat manager owner/kind')
        begin=self.at(manager+32);end=self.at(manager+40);cap=self.at(manager+48)
        need(begin>=0x10000 and begin%8==0 and begin<=end<=cap and (end-begin)%8==0 and (cap-begin)%8==0 and cap-begin<=256*8,'Envoy bounds')
        entries=[];ids=set();ptrs=set();missions=set()
        for i in range((end-begin)//8):
            p=self.at(begin+i*8);self.typed(p,base+0x1cac2f0);need(self.at(p+64,1)==3,'Envoy kind')
            need(p not in ptrs,'Duplicate envoy');ptrs.add(p)
            state=self.at(p+24,1);eid=self.at(p+68,4);mp=self.at(p+16)
            need(state<=2 and eid<2**31 and eid not in ids,'Envoy status/ID');ids.add(eid)
            mission=None
            if mp:
                need(state in (1,2) and mp not in missions,'Mission status/identity');missions.add(mp)
                self.typed(mp,base+0x1c4b2b8,0x182)
                need(self.at(mp+72)==p and self.at(mp+80,4)==eid and self.at(mp+128)==HANDLES['FRA'],'Mission ownership')
                target=self.at(mp+136);token=self.at(mp+168,4);task=self.at(mp+160)
                mission=dict(pointer=mp,target=target,token=token,task=task)
                if target==HANDLES['ENG'] and token==0x3378 and task:
                    self.typed(task,base+0x1ce3ba0)
            else:need(state==0,'Idle envoy has no mission')
            entries.append(dict(pointer=p,id=eid,state=state,mission=mission))
        records=self.at(fra+0x1510);cooldown=self.at(records+46*0x48+0x30,4)
        need(self.roots(base)==world and self.at(fra+0x1480)==holder and self.at(holder+24)==manager and self.at(manager+32)==begin and self.at(manager+40)==end and self.at(manager+48)==cap,'Changed roots/manager')
        return dict(world=world,pair_indexes=pair,diplomats=dict(holder=holder,manager=manager,begin=begin,end=end,capacity=cap,entries=entries),cooldown_raw=cooldown,
                    spy_evidence='FRA envoy missions only; target task list and spy cost are not observed')

def census(client,label):
    m=client.manifest();g=client.graph();ro=g.local('readonly.py')
    id=client.identity(PID,CREATION,'00000000000000000000000000000001',m)
    h=ro.Held(id)
    try:
        modules=h.modules();bases=[b for b,p in modules if h.injector._canonical(p)==h.injector._canonical(h.injector.GAME)]
        need(len(bases)==1,'Exact game module');h.identity_check();r=Reader(h)
        a=r.sample(bases[0]);b=r.sample(bases[0]);h.identity_check()
        report=dict(schema='EU4PAIR22GROUPDIAG/1',pid=PID,creation=CREATION,label=label,read_only=True,passes=[a,b],equal=a==b,atomic=False,reads=r.calls,bytes=r.bytes,
                    observer_sha256=sha(Path(__file__).read_bytes()),production_ready=False,gameplay_effects_verified=False)
        dump_new(OUT/(label+'.json'),report);need(a==b,'Repeated group diagnostic differs')
        print(json.dumps(dict(label=label,equal=True,date=a['world']['date'],envoys=len(a['diplomats']['entries']),idle=sum(e['state']==0 for e in a['diplomats']['entries']),selected_relations={k:v['outgoing']['selected']!=0 for k,v in a['pair_indexes'].items()},reads=r.calls,bytes=r.bytes)))
    finally:h.close()

def main():
    need(sys.flags.isolated==1,'Run python -I -B')
    p=argparse.ArgumentParser();p.add_argument('op',choices=['check','initial','load','batch','inspect','final']);p.add_argument('--session');a=p.parse_args()
    OUT.mkdir(exist_ok=True);client=verified_client()
    if a.op in ('initial','final'):census(client,a.op);return 0
    intent=OUT/(a.op+'.operation.json');dump_new(intent,dict(operation=a.op,pid=PID,creation=CREATION,session=a.session,client_sha256=CLIENT_SHA,unknown=True))
    args=[sys.executable,'-I','-B',str(HERE/'client.py'),'--pid',str(PID),'--creation',CREATION,'--ack-disposable-test']
    if a.session:args+=['--session',a.session]
    args+=[a.op]
    with (OUT/(a.op+'.stdout')).open('xb') as out,(OUT/(a.op+'.stderr')).open('xb') as err:
        run=subprocess.run(args,stdout=out,stderr=err,timeout=40)
    stdout=(OUT/(a.op+'.stdout')).read_bytes();stderr=(OUT/(a.op+'.stderr')).read_bytes()
    dump_new(OUT/(a.op+'.completed.json'),dict(exit_code=run.returncode,stdout_bytes=len(stdout),stdout_sha256=sha(stdout),stderr_bytes=len(stderr),stderr_sha256=sha(stderr)))
    print(stdout.decode('ascii') if len(stdout)<8192 else 'Large result preserved '+str(OUT/(a.op+'.stdout')))
    if stderr:print(stderr.decode('ascii'),file=sys.stderr)
    return run.returncode
if __name__=='__main__':raise SystemExit(main())
