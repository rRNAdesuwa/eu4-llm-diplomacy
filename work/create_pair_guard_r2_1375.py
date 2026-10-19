"""Create an isolated R3/core + repaired-port guard composition."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'work/candidates/v21-native-pair-guard-1375'
HERE=ROOT/'work/candidates/v21-native-pair-guard-r2-1375'
ENV=ROOT/'work/candidates/v19-spy-restricted-host-r2-1375/preflight'
def raw(p):
    assert p.stat().st_size<=4*1024*1024
    return p.read_bytes()
def desc(p):
    b=raw(p);return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def put(name,b):
    p=HERE/name;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:f.write(b)
def replace(b,a,c):
    a=a.encode();c=c.encode();assert b.count(a)==1,a;return b.replace(a,c)
assert desc(OLD/'review.json')['sha256']=='34e9c8cb624fb1d029df3939935949df833a4e2b528ffdbd9e0ffd9b7cd275a8'
assert all(desc(OLD/k)==v for k,v in json.loads(raw(OLD/'source-index.json')).items())
HERE.mkdir(exist_ok=False)
pins=json.loads(raw(OLD/'input-pins.json'))
for name in ['native_guard.h','native_guard.cpp','environment_binding.h','environment_binding.cpp','test_native_guard.cpp','build_test.cmd','validate.py']:
    data=raw(OLD/name);put('preimages/'+name,data);pins['work/candidates/v21-native-pair-guard-1375/'+name]=desc(OLD/name)
    if name=='native_guard.h':
        data=replace(data,'#include "../v19-spy-restricted-host-r2-1375/preflight/native_env.h"','#include "native_env.h"')
        data=replace(data,'#include "port/native_platform.h"','#include "../v21-native-pair-port-r2-1375/native_platform.h"')
        data=replace(data,'cancel1375::Snapshot cancel_{};','cancel1375::Snapshot cancel_{};\n    v21pair::SpyBinding spy_{};bool spy_bound_{};')
    if name=='native_guard.cpp':
        data=replace(data,'if(action>=12||request.action==v21pair::Action::StopSpyNetwork)return fail(); // entry-own-type integration requires new Core revision',
            'if(action>=12)return fail();')
        data=replace(data,'if(!sample_pair(request,baseline_,roots_))return false;bound_=true;',
            'if(!sample_pair(request,baseline_,roots_))return false;bound_=true;\n        if(request.action==v21pair::Action::StopSpyNetwork) {\n            if(!v21pair::bind_spy_two_pass(*this,env_.image_base,baseline_,spy_))return fail();\n            spy_bound_=true;\n        }')
        data=replace(data,'if(!cancel_bound_||!cancel1375::recheck(*this,env_.image_base,v21pair::profile(request_.action).family,baseline_,cancel_))return fail();',
            'if(request_.action==v21pair::Action::StopSpyNetwork) {\n                if(!spy_bound_||!v21pair::recheck_spy(*this,env_.image_base,baseline_,spy_))return fail();\n            } else if(!cancel_bound_||!cancel1375::recheck(*this,env_.image_base,v21pair::profile(request_.action).family,baseline_,cancel_))return fail();')
    if name=='build_test.cmd':
        data=replace(data,'v21-core-pair-nosend-r2-1375','v21-core-pair-nosend-r3-1375')
        pos=data.index(b'cl /nologo /std:c++17 /EHsc /W4 /WX /Od /c "%guard_src%native_guard.cpp"')
        data=data[:pos]+b'cl /nologo /std:c++17 /EHsc /W4 /WX /Od /c "%guard_src%native_env.cpp" /Fo"%guard_out%\\native_env.obj" > "%guard_out%\\native_env.stdout" 2> "%guard_out%\\native_env.stderr"\nif errorlevel 1 exit /b 18\n'+data[pos:]
    put(name,data)
for name in ['native_env.h','native_env.cpp']:
    data=raw(ENV/name);put('preimages/'+name,data);pins['work/candidates/v19-spy-restricted-host-r2-1375/preflight/'+name]=desc(ENV/name)
    if name=='native_env.h':data=replace(data,'#include "host.h"','#include "../v19-spy-restricted-host-r2-1375/preflight/host.h"')
    else:
        data=replace(data,'#include "../core/v18-preimage/pins.h"','#include "../v19-spy-restricted-host-r2-1375/core/v18-preimage/pins.h"')
        data=replace(data,'||!get(s.actor_country+0x20,s.actor)||!get(s.target_country+0x20,s.target)',
            ')return false;\n    // Prove both country headers before reading derived handles/overlords.\n    for(const auto country:{s.actor_country,s.target_country}) {\n        std::uintptr_t type=0;std::uint32_t marker=0;\n        if(!get(country,type)||type!=base_+0x1c574a0||!get(country+8,marker)||marker!=0x165)return false;\n    }\n    if(!get(s.actor_country+0x20,s.actor)||!get(s.target_country+0x20,s.target)')
    put(name,data)
for base in ['v21-native-pair-port-r2-1375','v21-core-pair-nosend-r3-1375']:
    other=ROOT/'work/candidates'/base
    for name,pin in json.loads(raw(other/'source-index.json')).items():
        pins['work/candidates/'+base+'/'+name]=pin
    pins['work/candidates/'+base+'/review.json']=desc(other/'review.json')
for name in ['work/candidates/v21-native-pair-guard-1375/review.json',
 'work/review-results/v21-five-cancel-reader-action-catalog-20261008a/review.json',
 'work/review-results/current-country-tag-cpp-favor-20261008a/review.json',
 'work/create_pair_guard_r2_1375.py']:
    pins[name]=desc(ROOT/name)
assert all(desc(ROOT/k)==v for k,v in pins.items())
put('input-pins.json',(json.dumps(pins,indent=2,sort_keys=True)+'\n').encode())
print(json.dumps(dict(created=str(HERE),inputs=len(pins),native_called=False)))
