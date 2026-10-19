"""Fresh five-favor gap batch, file-only, never mutate prior experiments."""
import hashlib,json,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'work/candidates/v28-gap-batch-1375'
OUT=ROOT/'work/candidates/v29-gap-batch-1375'
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
    if n.startswith('src/') or n in ('build_test.cmd','profile-facts.json','coalition-contract.json'):
        write(OUT/n,(OLD/n).read_bytes())
src=OUT/'src/work/candidates';host=src/'v26-gap-curry-bootstrap-1375'
for p in [*host.iterdir(),OUT/'build_test.cmd']:
    if p.is_file():p.write_text(p.read_text().replace('pair28','pair29').replace('_v28','_v29'),encoding='utf-8',newline='\n')
def change(p,a,b,n=1):
    s=p.read_text();assert s.count(a)==n,(p,a,s.count(a));p.write_text(s.replace(a,b),encoding='utf-8',newline='\n')
families=', FavorMen, FavorSailors, FavorTrust, FavorWarPrep'
header=src/'v21-core-pair-nosend-r2-1375/pair_component.h'
change(header,'Independence, FavorGold','Independence, FavorGold'+families,2)
change(header,'array<Profile, 11>','array<Profile, 15>')
core=src/'v24-pair-send-core-r2-1375/pair_send.cpp'
change(core,'array<Profile, 11>','array<Profile, 15>',2)
change(core,'array<std::string_view, 17>','array<std::string_view, 21>')
change(core,'>=17','>=21',2)
extra=[('FavorMen',0x3bcf,0x40,0x1c80ff0,0x4f83f0,0x129450,0x4f75d0,0x4f7c70,0x35ff1a),
       ('FavorSailors',0x3bd0,0x40,0x1c81250,0x4fa7f0,0x129450,0x4f9920,0x4fa010,0x35ff99),
       ('FavorTrust',0x3bd3,0x48,0x1c80c60,0x4fe740,0x129500,0x4fdfa0,0x4fe2a0,0x3600b1),
       ('FavorWarPrep',0x3bd4,0x40,0x1c80ec0,0x500000,0x129450,0x4ff860,0x4ffcc0,0x360152)]
registry=''.join(',\n    {Family::%s,0x%x,0x%x,0x%x,0x%x,0x%x,0x4e99d0,0x%x,0x%x,FullCallerEvidence::StaticSlotOnly}'%e[:8] for e in extra)
anchor='{Family::FavorGold,0x3bce,0x40,0x1c80980,0x4f5bd0,0x129450,0x4e99d0,0x4f4ee0,0x4f5680,FullCallerEvidence::StaticSlotOnly}'
change(core,anchor,anchor+registry)
names=',"trade_favors_for_men","trade_favors_for_sailors","trade_favors_for_trust","trade_favors_for_war_prep"'
for p in [core,host/'codec.h']:
    change(p,'"trade_favors_for_gold"}}','"trade_favors_for_gold"'+names+'}}')
change(host/'codec.h','array<const char*,17>','array<const char*,21>')
change(host/'codec.h','(a!=11 && a<14)','(a<16)')
test=host/'test_codec.cpp'
change(test,'action<17','action<21')
change(test,'action!=11 && action<14','action<16')
change(test,'stop_currying_favors','trade_favors_for_gold',2)
guard=src/'v21-native-pair-guard-r3-1375/native_guard.cpp'
change(guard,'action>=17','action>=21')
for p in [core,src/'v21-five-cancel-reader-1375/cancel_reader.cpp']:
    prefix='v21pair::' if p.name=='cancel_reader.cpp' else ''
    a='case '+prefix+'Family::FavorGold: return false;'
    b='case '+prefix+'Family::FavorGold: '+''.join('case '+prefix+'Family::'+e[0]+': ' for e in extra)+'return false;'
    change(p,a,b)
# Trust +40/+44 are native factory fields, never caller-controlled or overwritten.
engine=src/'v24-pair-send-port-r2-1375/native_pair_engine.cpp'
anchor='    const auto v=view(e);const auto h='
change(engine,anchor,'    if(e.profile->family==Family::FavorTrust && (get<std::int32_t>(e.address+0x40)!=5000 || get<std::int32_t>(e.address+0x44)!=1))fail(Fault::Fields);\n'+anchor)
submit=src/'v24-pair-send-port-r2-1375/submission_guard.cpp'
anchor='    if(e.profile.family==Family::Marriage) {'
change(submit,anchor,'    if(e.profile.family==Family::FavorTrust && (!at(e.clone,0x40,s) || s!=5000 || !at(e.clone,0x44,s) || s!=1))return false;\n'+anchor)
with (ROOT.parent/'eu4.exe').open('rb') as f:
    assert hashlib.file_digest(f,'sha256').hexdigest()=='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
    f.seek(0);h=f.read(8192);nt=struct.unpack_from('<I',h,60)[0];op=struct.unpack_from('<H',h,nt+20)[0]
    sections=[struct.unpack_from('<IIII',h,nt+24+op+40*i+8) for i in range(struct.unpack_from('<H',h,nt+6)[0])]
    def read(r,n):
        for vs,va,sz,raw in sections:
            if va<=r and r+n<=va+sz:f.seek(raw+r-va);return f.read(n)
        raise ValueError(hex(r))
    selected={}
    facts=json.loads((OUT/'profile-facts.json').read_bytes())
    for name,token,size,vt,clone,dtor,local,full,factory in extra:
        assert struct.unpack('<Q',read(vt,8))[0]==0x140000000+dtor
        assert struct.unpack('<Q',read(vt+0x80,8))[0]==0x140000000+local
        assert struct.unpack('<Q',read(vt+0x88,8))[0]==0x140000000+full
        assert struct.unpack('<Q',read(vt+0xb0,8))[0]==0x140000000+clone
        lea=read(factory,7);assert lea[:3]==b'\x48\x8d\x05' and factory+7+struct.unpack('<i',lea[3:])[0]==vt
        for r,n in [(factory,7),(clone,32),(dtor,32),(local,32),(full,32)]:selected[r]=read(r,n).hex()
        facts.append(dict(family=name,token=token,size=size,vtable=vt,clone=clone,destructor=dtor,local80=local,full88=full,full88_arguments='NULL,false',caller_evidence='static_vtable_slot'))
    for r,n in [(0x3600bb,25),(0x4fe7be,13)]:selected[r]=read(r,n).hex()
    assert read(0x3600bb,10).hex()=='6905b7dafd01e8030000'
    assert read(0x3600c8,6).hex()=='8b05b2dafd01'
pins=src/'v24-pair-send-port-r2-1375/native_pins.h'
change(pins,'inline constexpr CodePin kCodePins[]={','inline constexpr CodePin kCodePins[]={\n'+''.join(' {0x%x,"%s"},\n'%(r,b) for r,b in selected.items()))
(OUT/'profile-facts.json').write_text(json.dumps(facts,indent=2)+'\n')
write(OUT/'favor-contract.json',(json.dumps(dict(trust_amount_milli=5000,trust_cost=1,amount_global_rva=0x233db7c,cost_global_rva=0x233db80,code_pins={hex(k):v for k,v in selected.items()},runtime_verified=False),indent=2)+'\n').encode())
write(OUT/'input-pins.json',(json.dumps(inputs,indent=2,sort_keys=True)+'\n').encode())
index={p.relative_to(OUT).as_posix():pin(p) for p in OUT.rglob('*') if p.is_file()}
index['../../create_pair29_gap_1375.py']=pin(Path(__file__))
write(OUT/'source-index.json',(json.dumps(index,indent=2,sort_keys=True)+'\n').encode())
print(json.dumps(dict(directory=str(OUT),sources=len(index),new_profiles=4,codec_allowed=[16,17,18,19,20])))
