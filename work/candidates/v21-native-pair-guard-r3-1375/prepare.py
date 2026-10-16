import hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SOURCES=['native_guard.h','native_guard.cpp','environment_binding.h','environment_binding.cpp','native_env.h','native_env.cpp',
 'test_native_guard.cpp','test_native_env_types.cpp','fake_platform.h','build_test.cmd','README.md','prepare.py','validate.py','input-pins.json']
def raw(p):
    assert p.stat().st_size<=4*1024*1024
    return p.read_bytes()
def desc(p):
    b=raw(p);return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def current():
    paths=SOURCES+[str(p.relative_to(HERE)).replace('\\','/') for p in sorted((HERE/'preimages').rglob('*')) if p.is_file()]
    return {p:desc(HERE/p) for p in paths}
def inputs():
    pins=json.loads(raw(HERE/'input-pins.json'));assert len(pins)<=128
    assert all(desc(ROOT/k)==v for k,v in pins.items());return pins
if __name__=='__main__':
    inputs()
    if sys.argv[1:]==['--index']:
        with (HERE/'source-index.json').open('xb') as f:f.write((json.dumps(current(),indent=2,sort_keys=True)+'\n').encode())
    else:
        assert sys.argv[1:]==['--check'];assert current()==json.loads(raw(HERE/'source-index.json'))
        print(json.dumps(dict(check=True,sources=len(current()),inputs=len(inputs()))))
