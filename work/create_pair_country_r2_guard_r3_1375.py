"""Fresh isolated repair for passive nonordinary country rows; no game access."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def desc(p):
    assert p.stat().st_size<=4*1024*1024
    b=p.read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def put(p,b):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:f.write(b if isinstance(b,bytes) else b.encode('ascii'))
def seal(p,v):put(p,json.dumps(v,indent=2,sort_keys=True)+'\n')
def replace(b,a,c):
    a=a.encode();assert b.count(a)==1,a;return b.replace(a,c.encode())
def clone(old,new):
    old=ROOT/'work/candidates'/old;new=ROOT/'work/candidates'/new;new.mkdir(exist_ok=False)
    index=json.loads((old/'source-index.json').read_bytes());pins=json.loads((old/'input-pins.json').read_bytes())
    assert all(desc(old/k)==v for k,v in index.items()) and all(desc(ROOT/k)==v for k,v in pins.items())
    for n in index:
        if n=='input-pins.json':continue
        b=(old/n).read_bytes();put(new/n,b);pins[(old/n).relative_to(ROOT).as_posix()]=desc(old/n)
    pins[(old/'source-index.json').relative_to(ROOT).as_posix()]=desc(old/'source-index.json')
    pins[(old/'review.json').relative_to(ROOT).as_posix()]=desc(old/'review.json')
    return old,new,pins
old,here,pins=clone('current-country-tag-cpp-1375','current-country-tag-cpp-r2-1375')
p=here/'country_resolver.cpp';b=p.read_bytes()
b=replace(b,'(handle>>56)!=0&&((handle>>48)&255)==0&&((handle>>24)&255)==0','(handle>>56)!=0&&((handle>>48)&255)<=7&&((handle>>24)&255)==0')
b=replace(b,'"research generation/type profile"','"bounded passive selector/generation profile"')
b=replace(b,'bindings.push_back(Binding{tag,found->slot,found->address,found->handle});',
'''// Passive selectors 1..7 are retained and compared, never authorized.
            demand(((found->handle>>48)&255)==0,Status::UnsupportedLayout,"requested TAG requires ordinary selector0");
            bindings.push_back(Binding{tag,found->slot,found->address,found->handle});''')
p.write_bytes(b)
diagnostic=ROOT/'work/runtime/pair22-session-20261012a/lease-diagnostic.json'
d=json.loads(diagnostic.read_bytes());assert len(d['country_rows'])==1380 and all('handle' in x for x in d['country_rows'])
assert not any(x.get('vt') for x in d['resolver_profile_failures'])
handles=[x['handle'] for x in d['country_rows']]
put(here/'captured_country_handles.h','#pragma once\n#include <array>\n// Passive captured handles only; no addresses, OS reader or native call.\ninline constexpr std::array<std::uint64_t,1380> CapturedHandles{{\n'+','.join('0x%016xULL'%h for h in handles)+'\n}};\n')
p=here/'test_country_resolver.cpp';b=p.read_bytes()
b=replace(b,'#include "selected_pins.h"','#include "selected_pins.h"\n#include "captured_country_handles.h"')
extra='''    group("passive_selectors_preserved_but_requested_nonordinary_refused",[] {
        for(std::uint8_t selector=1;selector<=7;++selector) {Memory m(4);m.row(3,"C00");
            const auto h=handle("C00",3)|(std::uint64_t{selector}<<48);m.put(Objects+0x3020,h);
            const auto r=run(m);assert(r.status==Status::Resolved&&r.snapshot.rows[3].handle==h);
            const auto denied=run(m,{"C00"});assert(denied.status==Status::UnsupportedLayout&&denied.bindings.empty());
        }});
    group("unknown_passive_selector_still_refused",[] {for(std::uint8_t selector:{std::uint8_t{8},std::uint8_t{255}}) {
        Memory m(4);m.row(3,"C00");m.put(Objects+0x3020,handle("C00",3)|(std::uint64_t{selector}<<48));rejected(m,Status::UnsupportedLayout);}});
    group("passive_selector_change_between_passes_refused",[] {Memory m(4);m.row(3,"C00");std::size_t n=0;
        m.callback=[&](Memory& x,std::uint64_t a,std::size_t){if(a==Base+0x233d8d0&&++n==3)x.put(Objects+0x3020,handle("C00",3)|(std::uint64_t{2}<<48));};rejected(m,Status::Changed);});
    group("captured_1380_typed_handle_table_405_nonordinary_replay",[] {
        Memory m(static_cast<std::uint32_t>(CapturedHandles.size()));unsigned nonordinary=0;
        for(std::size_t i=0;i<CapturedHandles.size();++i) {const auto h=CapturedHandles[i];const auto slot=static_cast<std::uint32_t>(i);
            m.row(slot,"AAA");m.put(Objects+std::uint64_t{slot}*0x1000+0x20,h);if((h>>48)&255)++nonordinary;}
        m.put(Game+0x1e60,CapturedHandles[122]);const auto r=run(m);assert(nonordinary==405&&r.status==Status::Resolved&&r.stable_two_pass);
        assert(r.bindings[0].slot==122&&r.bindings[1].slot==46&&r.bindings[0].handle==CapturedHandles[122]&&r.snapshot.rows.size()==1380);
        for(std::size_t i=0;i<CapturedHandles.size();++i)assert(r.snapshot.rows[i].handle==CapturedHandles[i]);
    });
'''
b=replace(b,'    std::printf("groups=%zu native_calls=0 game_access=0\\n",groups);return 0;',extra+'    std::printf("groups=%zu native_calls=0 game_access=0\\n",groups);return 0;')
p.write_bytes(b)
p=here/'validate.py';b=p.read_bytes().replace(b'groups=22 native_calls=0 game_access=0',b'groups=26 native_calls=0 game_access=0').replace(b'groups=22,inputs=',b'groups=26,inputs=');p.write_bytes(b)
put(here/'R2-NOTES.md',"The old resolver rejected all 405 passive selectors in the captured table. R2 permits only opaque passive selector values 0..7, preserves exact full handles and two whole passes, and still rejects requests selecting any nonzero selector. No semantics or native authorization for dynamic countries is inferred. The captured 1380-row replay uses analysis-owned memory. Old evidence and failure remain unchanged.\n")
pins[diagnostic.relative_to(ROOT).as_posix()]=desc(diagnostic);pins[Path(__file__).relative_to(ROOT).as_posix()]=desc(Path(__file__))
seal(here/'input-pins.json',pins)
seal(here/'source-index.json',{p.relative_to(here).as_posix():desc(p) for p in here.rglob('*') if p.is_file()})
print(json.dumps(dict(candidate=here.name,sources=len(json.loads((here/'source-index.json').read_bytes())),inputs=len(pins))))

old,here,pins=clone('v21-native-pair-guard-r2-1375','v21-native-pair-guard-r3-1375')
for n in ['native_guard.h','test_native_guard.cpp','build_test.cmd']:
    p=here/n;b=p.read_bytes().replace(b'current-country-tag-cpp-1375',b'current-country-tag-cpp-r2-1375');p.write_bytes(b)
p=here/'test_native_guard.cpp';b=p.read_bytes()
b=replace(b,'    std::printf("guard_groups=%zu native_calls=0 game_access=0\\n",groups);return 0;',
'''    group("passive_nonordinary_country_does_not_block_six_modes",[] {for(unsigned i=0;i<12;i+=2) {
        Model m;m.memory.put(DB+0x120,std::int32_t{4});m.memory.put(DB+0x124,std::int32_t{4});m.memory.row(3,"C00");
        m.memory.put(Objects+0x3020,handle("C00",3)|(std::uint64_t{2}<<48));
        v21guard::NativePairGuardDraft g(m.environment());auto r=request();r.action=static_cast<v21pair::Action>(i);
        assert(g.begin_frame()&&g.lease(r,1020));BoundPlatform p(g);v21port::NativePairEngineDraft engine(p);
        const auto result=v21pair::preflight_no_send(r,g,engine,1020,&g,Base);
        assert(result.status==v21pair::Status::ModelComplete&&!g.frozen()&&engine.diagnostics().live==0);
    }});
    std::printf("guard_groups=%zu native_calls=0 game_access=0\\n",groups);return 0;''')
p.write_bytes(b)
p=here/'validate.py';p.write_bytes(p.read_bytes().replace(b'guard_groups=22 ',b'guard_groups=23 '))
put(here/'R3-NOTES.md','R3 changes only the country resolver binding and adds a six-family passive-selector regression. The actual native environment, pair core, port and authority checks are unchanged. Ordinary current player and requested pair restrictions remain. No game access in validation.\n')
new=ROOT/'work/candidates/current-country-tag-cpp-r2-1375'
for n,pin in json.loads((new/'source-index.json').read_bytes()).items():pins[(new/n).relative_to(ROOT).as_posix()]=pin
pins[Path(__file__).relative_to(ROOT).as_posix()]=desc(Path(__file__))
seal(here/'input-pins.json',pins)
seal(here/'source-index.json',{p.relative_to(here).as_posix():desc(p) for p in here.rglob('*') if p.is_file()})
print(json.dumps(dict(candidate=here.name,inputs=len(pins))))
