"""Create a new private adapter revision. Never edit a sealed predecessor."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'work/candidates/v21-native-pair-port-1375'
CORE=ROOT/'work/candidates/v21-core-pair-nosend-r3-1375'
HERE=ROOT/'work/candidates/v21-native-pair-port-r2-1375'
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
assert desc(OLD/'review.json')['sha256']=='0bbcf1e9f93e45e8822b733561b1a98323cc7f8b3c3d4ee1305586de8d8b6435'
assert desc(CORE/'review.json')['sha256']=='00d51a15b915a0d4a8daff85241baeaf299157ab1b4816906315334c843190f2'
for base in [OLD,CORE]:
    index=json.loads(raw(base/'source-index.json'))
    assert all(desc(base/name)==pin for name,pin in index.items())
    pins=json.loads(raw(base/'input-pins.json'))
    assert all(desc(ROOT/name)==pin for name,pin in pins.items())
HERE.mkdir(exist_ok=False)
copied=['native_pair_engine.h','native_pair_engine.cpp','native_platform.h','native_platform.cpp','native_pins.h',
        'pin-provenance.json','test_native_pair_engine.cpp','validate.py','build_test.cmd']
lineage={}
for name in copied:
    data=raw(OLD/name);put('preimages/'+name,data);lineage['work/candidates/v21-native-pair-port-1375/'+name]=desc(OLD/name)
    if name=='native_pair_engine.cpp':
        data=replace(data,'if(v.text.capacity>=16) {chars=get<Address>(p+0x40);if(!pointer(chars))fail(Fault::Fields);}',
            '// RW storage does not prove allocator ownership. Until an allocator-aware\n        // certificate exists, refuse every heap String32 before reading its pointer\n        // or entering any deleting destructor. Retain all issued objects.\n        if(v.text.capacity>=16) fail(Fault::Ownership);\n        if(v.text.capacity!=15) fail(Fault::Fields);')
    if name=='native_pair_engine.h':
        data=replace(data,'#include "component/pair_component.h"','#include "../v21-core-pair-nosend-r2-1375/pair_component.h"')
    if name=='test_native_pair_engine.cpp':
        start=data.index(b'    Fake f;f.heap_string=true;NativePairEngineDraft e(f);auto x=wrapped')
        end=data.index(b'    for(std::int32_t envoy:',start)
        data=data[:start]+b'    // Heap storage is conservatively unsupported until allocator ownership is proven.\n    {Fake f;f.heap_string=true;NativePairEngineDraft e(f);auto a=initialized(e,profiles()[1]);\n     rejects([&]{e.full88(profiles()[1],a,nullptr,false);},e,f);CHECK(f.deletes==0 && e.diagnostics().fault==Fault::Ownership);}\n'+data[end:]
        data=replace(data,'std::map<Address,Block> memory;Address next=', 'std::vector<Address> read_addresses;\n    std::map<Address,Block> memory;Address next=')
        data=replace(data,'++reads;CHECK(n>0 && n<=64);','++reads;read_addresses.push_back(p);CHECK(n>0 && n<=64);')
    if name=='build_test.cmd':
        data=replace(data,'test_r2_spy_setter.cpp','test_heap_and_r3.cpp')
    put(name,data)
for name in ['pair_component.h','pair_component.cpp']:
    put('component/'+name,raw(CORE/name));lineage['work/candidates/v21-core-pair-nosend-r3-1375/'+name]=desc(CORE/name)
put('typed_fixture.h',raw(CORE/'typed_fixture.h'))
lineage['work/candidates/v21-core-pair-nosend-r3-1375/typed_fixture.h']=desc(CORE/'typed_fixture.h')
data=raw(CORE/'test_r3_integration.cpp')
put('preimages/test_r3_integration.cpp',data)
put('test_r3_integration.cpp',replace(data,'#include "adapter/test_native_pair_engine.cpp"','#include "test_native_pair_engine.cpp"'))
lineage['work/candidates/v21-core-pair-nosend-r3-1375/test_r3_integration.cpp']=desc(CORE/'test_r3_integration.cpp')
for name,pin in json.loads(raw(OLD/'input-pins.json')).items():
    assert name not in lineage or lineage[name]==pin
    lineage[name]=pin
for name in ['work/candidates/v21-core-pair-nosend-r3-1375/review.json',
 'work/candidates/v21-core-pair-nosend-r2-1375/pair_component.h',
 'work/review-results/v21-native-pair-port-favor-20261008a/review.json',
 'work/review-results/v21-native-pair-port-favor-20261008a/report.json',
 'work/review-results/v21-native-pair-port-favor-20261008a/finding-locations.json',
 'work/review-results/v21-native-pair-port-favor-20261008a/test_independent.cpp',
 'work/candidates/v21-native-pair-port-1375/review.json','work/AGENTS.md',
 'work/create_native_pair_port_r2_1375.py']:
    lineage[name]=desc(ROOT/name)
assert raw(CORE/'pair_component.h')==raw(ROOT/'work/candidates/v21-core-pair-nosend-r2-1375/pair_component.h')
put('input-pins.json',(json.dumps(lineage,indent=2,sort_keys=True)+'\n').encode())
print(json.dumps(dict(created=str(HERE),inputs=len(lineage),native_called=False)))
