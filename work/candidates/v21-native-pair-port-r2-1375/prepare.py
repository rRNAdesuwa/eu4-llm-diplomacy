"""Verify the private revision and its pinned immutable inputs."""
import hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
FILES=['component/pair_component.h','component/pair_component.cpp','native_pair_engine.h','native_pair_engine.cpp',
 'native_platform.h','native_platform.cpp','native_pins.h','pin-provenance.json','test_native_pair_engine.cpp',
 'test_heap_and_r3.cpp','test_r3_integration.cpp','typed_fixture.h','build_test.cmd','validate.py','prepare.py','README.md','input-pins.json']
def read(p):
    assert p.stat().st_size<=4*1024*1024
    return p.read_bytes()
def desc(p):
    b=read(p);return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def current():
    names=FILES+[str(p.relative_to(HERE)).replace('\\','/') for p in sorted((HERE/'preimages').rglob('*')) if p.is_file()]
    return {name:desc(HERE/name) for name in names}
def inputs():
    pins=json.loads(read(HERE/'input-pins.json'));assert 0<len(pins)<=64
    assert all(name.startswith('work/') and '..' not in Path(name).parts for name in pins)
    assert all(desc(ROOT/name)==pin for name,pin in pins.items())
    return pins
def check():
    before=inputs();index=json.loads(read(HERE/'source-index.json'));assert current()==index
    for name in ['pair_component.h','pair_component.cpp']:
        assert read(HERE/'component'/name)==read(ROOT/'work/candidates/v21-core-pair-nosend-r3-1375'/name)
    assert read(HERE/'component/pair_component.h')==read(ROOT/'work/candidates/v21-core-pair-nosend-r2-1375/pair_component.h')
    for name in ['native_platform.cpp','native_platform.h','native_pins.h','pin-provenance.json']:
        assert read(HERE/name)==read(ROOT/'work/candidates/v21-native-pair-port-1375'/name)
    assert current()==index and inputs()==before
    print(json.dumps(dict(check='passed',sources=len(index),inputs=len(before),native_called=False,new_decode=0)))
if __name__=='__main__':
    if sys.argv[1:]==['--index']:
        inputs()
        with (HERE/'source-index.json').open('xb') as f:f.write((json.dumps(current(),indent=2,sort_keys=True)+'\n').encode())
    else:
        assert sys.argv[1:]==['--check'];check()
