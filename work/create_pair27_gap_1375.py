"""Fresh include-tree copy; extend only unverified pair actions, never old inputs."""
import hashlib, json, re, runpy, struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'work/candidates/v26-gap-curry-bootstrap-1375'
OUT=ROOT/'work/candidates/v27-gap-batch-1375'
prep=runpy.run_path(str(OLD/'prepare.py')); pins=prep['inputs'](); closure=prep['include_closure']()
assert prep['current']()==json.loads((OLD/'source-index.json').read_bytes())
OUT.mkdir(exist_ok=False)
def write(p,data):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f: f.write(data)
for name,pin in closure.items():
    b=(ROOT/name).read_bytes(); assert dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())==pin
    write(OUT/'src'/name,b)
src=OUT/'src/work/candidates'
host=src/'v26-gap-curry-bootstrap-1375'
for name in ['frame.asm','build_test.cmd']:
    write(host/name,(OLD/name).read_bytes())
def change(path,old,new,count=None):
    s=path.read_text(); n=s.count(old); assert n>0 and (count is None or n==count),(path,old,n)
    path.write_text(s.replace(old,new),encoding='utf-8',newline='\n')
for p in host.iterdir():
    if p.is_file():
        s=p.read_text().replace('pair26','pair27').replace('_v26','_v27')
        p.write_text(s,encoding='utf-8',newline='\n')
names='"offer_fleet_basing_rights","insult","form_coalition","support_independence","trade_favors_for_gold"'
component=src/'v21-core-pair-nosend-r2-1375/pair_component.h'
change(component,'SpyNetwork, Curry };','SpyNetwork, Curry, FleetOffer, Insult, Coalition, Independence, FavorGold };',1)
change(component,'SpyNetwork, StopSpyNetwork, Curry, StopCurry','SpyNetwork, StopSpyNetwork, Curry, StopCurry, FleetOffer, Insult, Coalition, Independence, FavorGold',1)
change(component,'std::array<Profile, 6>','std::array<Profile, 11>')

# Read only the PE headers, virtual slots and specific instruction prefixes.
exe=ROOT.parent/'eu4.exe'
assert hashlib.file_digest(exe.open('rb'),'sha256').hexdigest()=='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
with exe.open('rb') as f:
    h=f.read(8192); nt=struct.unpack_from('<I',h,60)[0]
    optional=struct.unpack_from('<H',h,nt+20)[0]
    sections=[struct.unpack_from('<IIII',h,nt+24+optional+i*40+8) for i in range(struct.unpack_from('<H',h,nt+6)[0])]
    def read(rva,n):
        for vs,va,size,raw in sections:
            if va<=rva and rva+n<=va+size:
                f.seek(raw+rva-va); b=f.read(n); assert len(b)==n; return b
        raise ValueError(hex(rva))
    definitions=[
        ('FleetOffer',0x2dd7,0x40,0x1c7f1f0,0x534900,0x129450,0x533fa0),
        ('Insult',0x2947,0x48,0x1c7f6b0,0x538e20,0x129500,0x538700),
        ('Coalition',0x2de0,0x40,0x1c7c788,0x58a840,0x129450,0x58a120),
        ('Independence',0x2f2e,0x40,0x1c805f0,0x50f090,0x129450,0x50e0f0),
        ('FavorGold',0x3bce,0x40,0x1c80980,0x4f5bd0,0x129450,0x4f4ee0)]
    rows=[]; instruction_pins={}; facts=[]
    for family,token,size,vt,clone,dtor,local in definitions:
        full=struct.unpack('<Q',read(vt+0x88,8))[0]-0x140000000
        assert 0<full<0x1c00000
        assert struct.unpack('<Q',read(vt,8))[0]==0x140000000+dtor
        assert struct.unpack('<Q',read(vt+0xb0,8))[0]==0x140000000+clone
        rows.append('    {Family::%s,0x%x,0x%x,0x%x,0x%x,0x%x,0x4e99d0,0x%x,0x%x,FullCallerEvidence::StaticSlotOnly}'%(family,token,size,vt,clone,dtor,local,full))
        for address in [clone,dtor,full]: instruction_pins[address]=read(address,32).hex()
        facts.append(dict(family=family,token=token,size=size,vtable=vt,clone=clone,destructor=dtor,full88=full,local80=local,full88_arguments='NULL,false',caller_evidence='static_vtable_slot'))
core=src/'v24-pair-send-core-r2-1375/pair_send.cpp'
change(core,'std::array<Profile, 6>','std::array<Profile, 11>')
change(core,'FullCallerEvidence::SealedNormalCaller}\n}};','FullCallerEvidence::SealedNormalCaller},\n'+',\n'.join(rows)+'\n}};',1)
change(core,'std::array<std::string_view, 12>','std::array<std::string_view, 17>',1)
change(core,'"stop_currying_favors"}};','"stop_currying_favors",'+names+'}};',1)
change(core,'i>=12','i>=17',1)
change(core,'return registry[i/2];','return registry[i<12?i/2:i-6];',1)
change(core,'return (static_cast<unsigned>(action)&1)==0;','return static_cast<unsigned>(action)>=12 || (static_cast<unsigned>(action)&1)==0;',1)
change(core,'static_cast<unsigned>(request.action)>=12','static_cast<unsigned>(request.action)>=17',1)
change(core,'case Family::SpyNetwork: return false;','case Family::FleetOffer: case Family::Insult: case Family::Coalition: case Family::Independence: case Family::FavorGold: return false;\n    case Family::SpyNetwork: return false;',1)
guard=src/'v21-native-pair-guard-r3-1375/native_guard.cpp'
change(guard,'action>=12','action>=17',1)
cancel=src/'v21-five-cancel-reader-1375/cancel_reader.cpp'
change(cancel,'case v21pair::Family::SpyNetwork:return false;','case v21pair::Family::FleetOffer: case v21pair::Family::Insult: case v21pair::Family::Coalition: case v21pair::Family::Independence: case v21pair::Family::FavorGold: return false;\n        case v21pair::Family::SpyNetwork:return false;',1)
engine=src/'v24-pair-send-port-r2-1375/native_pair_engine.cpp'
change(engine,'const auto v=view(e);const auto h=', 'if(e.profile->family==Family::Insult && get<std::int32_t>(e.address+0x40)!=-1)fail(Fault::Fields);\n    const auto v=view(e);const auto h=',1)
submit=src/'v24-pair-send-port-r2-1375/submission_guard.cpp'
change(submit,'if(e.profile.family==Family::Marriage) {','if(e.profile.family==Family::Insult && (!at(e.clone,0x40,s) || s!=-1))return false;\n    if(e.profile.family==Family::Marriage) {',1)
native_pins=src/'v24-pair-send-port-r2-1375/native_pins.h'
change(native_pins,'inline constexpr CodePin kCodePins[]={','inline constexpr CodePin kCodePins[]={\n'+''.join(' {0x%x,"%s"},\n'%(r,b) for r,b in sorted(instruction_pins.items())),1)
codec=host/'codec.h'
change(codec,'std::array<const char*,12>','std::array<const char*,17>',1)
change(codec,'"stop_currying_favors"}};','"stop_currying_favors",'+names+'}};',1)
change(codec,'a!=10','(a<11)',1) # stop-curry11 plus five never-successful actions12..16
test=host/'test_codec.cpp'
change(test,'action<12','action<17',1)
change(test,'if(action!=10)','if(action<11)',1)
change(test,'"curry_favors"','"stop_currying_favors"')
change(test,'action=curry_favors','action=stop_currying_favors')
cmd=(host/'build_test.cmd').read_text().replace('set "pair27_src=%~dp0"','set "pair27_src=%~dp0src\\work\\candidates\\v26-gap-curry-bootstrap-1375\\"')
write(OUT/'build_test.cmd',cmd.encode('ascii'))
write(OUT/'profile-facts.json',(json.dumps(facts,indent=2)+'\n').encode('ascii'))
write(OUT/'input-pins.json',(json.dumps(pins,indent=2,sort_keys=True)+'\n').encode('ascii'))
def pin(p):
    b=p.read_bytes(); return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
source_pins={p.relative_to(OUT).as_posix():pin(p) for p in OUT.rglob('*') if p.is_file()}
source_pins['../../create_pair27_gap_1375.py']=pin(Path(__file__))
write(OUT/'source-index.json',(json.dumps(source_pins,indent=2,sort_keys=True)+'\n').encode('ascii'))
print(json.dumps(dict(directory=str(OUT),new_profiles=facts,source_files=len(source_pins),old_successes_rejected=True)))
