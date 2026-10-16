"""Fresh V28: preserve native coalition state=2; reject prior successes."""
import hashlib,json,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'work/candidates/v27-gap-batch-1375'
OUT=ROOT/'work/candidates/v28-gap-batch-1375'
def pin(p):
    b=p.read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def write(p,b):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:f.write(b)
inputs=json.loads((OLD/'input-pins.json').read_bytes())
for n,v in inputs.items():assert pin(ROOT/n)==v,n
sources=json.loads((OLD/'source-index.json').read_bytes())
for n,v in sources.items():assert pin(OLD/n)==v,n
OUT.mkdir(exist_ok=False)
for n in sources:
    if n.startswith('src/') or n in ('build_test.cmd','profile-facts.json'):
        write(OUT/n,(OLD/n).read_bytes())
src=OUT/'src/work/candidates'
host=src/'v26-gap-curry-bootstrap-1375'
for p in [*host.iterdir(),OUT/'build_test.cmd']:
    if p.is_file():p.write_text(p.read_text().replace('pair27','pair28').replace('_v27','_v28'),encoding='utf-8',newline='\n')
def change(p,old,new,count):
    s=p.read_text();assert s.count(old)==count,(p,old,s.count(old));p.write_text(s.replace(old,new),encoding='utf-8',newline='\n')
engine=src/'v24-pair-send-port-r2-1375/native_pair_engine.cpp'
change(engine,'|| v.envoy!=e.envoy || v.state ||','|| v.envoy!=e.envoy || v.state!=(e.profile->family==Family::Coalition?2u:0u) ||',1)
change(engine,'put(e,0x34,std::uint32_t{0});','put(e,0x34,std::uint32_t{e.profile->family==Family::Coalition?2u:0u});',1)
core=src/'v24-pair-send-core-r2-1375/pair_send.cpp'
change(core,'v.state==0','v.state==(p.family==Family::Coalition?2u:0u)',2)
submit=src/'v24-pair-send-port-r2-1375/submission_guard.cpp'
change(submit,'!at(e.clone,0x34,u) || u ||','!at(e.clone,0x34,u) || u!=(e.profile.family==Family::Coalition?2u:0u) ||',1)
change(host/'codec.h','(a<11)','(a!=11 && a<14)',1)
change(host/'test_codec.cpp','if(action<11)','if(action!=11 && action<14)',1)
# Exact factory constructor and tail independently pin state and dates.
exe=ROOT.parent/'eu4.exe'
with exe.open('rb') as f:
    assert hashlib.file_digest(f,'sha256').hexdigest()=='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
    f.seek(0); h=f.read(8192);nt=struct.unpack_from('<I',h,60)[0];op=struct.unpack_from('<H',h,nt+20)[0]
    sections=[struct.unpack_from('<IIII',h,nt+24+op+40*i+8) for i in range(struct.unpack_from('<H',h,nt+6)[0])]
    def read(r,n):
        for vs,va,sz,raw in sections:
            if va<=r and r+n<=va+sz:f.seek(raw+r-va);return f.read(n)
        raise ValueError(hex(r))
    selected={0x35e051:'c7413402000000',0x35e061:'488d0520e79101',0x36045c:'c7412cf8779c02c74128f8779c02',0x58a899:'8b433441894034'}
    for r,b in selected.items():assert read(r,len(b)//2).hex()==b,(hex(r),read(r,len(b)//2).hex())
pins=src/'v24-pair-send-port-r2-1375/native_pins.h'
change(pins,'inline constexpr CodePin kCodePins[]={','inline constexpr CodePin kCodePins[]={\n'+''.join(' {0x%x,"%s"},\n'%(r,b) for r,b in selected.items()),1)
write(OUT/'coalition-contract.json',(json.dumps({'native_state':2,'other_family_state':0,'factory_date_sentinels':'0x29c77f8','code_pins':{hex(k):v for k,v in selected.items()},'normal_ai_evidence':'work/reports/native-coalition-queue-1375.json','runtime_verified':False},indent=2)+'\n').encode())
inputs['work/reports/native-coalition-queue-1375.json']=pin(ROOT/'work/reports/native-coalition-queue-1375.json')
write(OUT/'input-pins.json',(json.dumps(inputs,indent=2,sort_keys=True)+'\n').encode())
index={p.relative_to(OUT).as_posix():pin(p) for p in OUT.rglob('*') if p.is_file()}
index['../../create_pair28_gap_1375.py']=pin(Path(__file__))
write(OUT/'source-index.json',(json.dumps(index,indent=2,sort_keys=True)+'\n').encode())
print(json.dumps({'directory':str(OUT),'sources':len(index),'coalition_state':2,'insult_blocked':True}))
