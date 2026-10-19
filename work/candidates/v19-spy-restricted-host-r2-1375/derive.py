"""CreateNew R2 source copy; no compilation, game, or formal materialization."""
from pathlib import Path
import difflib,hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
OLD=ROOT/'work/candidates/v19-spy-restricted-host-1375'
def read(p):
    with p.open('rb') as f:b=f.read(262145)
    if len(b)>262144:raise ValueError('source budget')
    return b
def desc(p):
    b=read(p);return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def create(p,b):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:f.write(b)
def replacement(b,old,new):
    if b.count(old)!=1:raise ValueError('replacement must match once')
    return b.replace(old,new)
assert desc(OLD/'review.json')['sha256']=='5c8adfadfc1ff3c84b1e2ceb23d42a1248925ff561ac37e69a6efa9a1b63df37'
index=json.loads(read(OLD/'source-index.json'))
for name,pin in index['sources'].items():
    assert desc(OLD/name)==pin
    if name in ('input-pins.json','prepare.py','README.md'):continue
    data=read(OLD/name)
    if name=='host.cpp':
        # Preserve original CRLF and every unrelated byte.
        data=replacement(data,b'const auto now=env_.clock(env_.user);if(!healthy()||now<clock_)return fail(Failure::clock);clock_=now;',
            b'const auto now=clock_cb(this);if(!healthy())return false;')
        data=replacement(data,b'if(!env_.begin_frame(env_.user)||!barrier(false))return false;',
            b'if(!begin_frame_cb(this)||!barrier(false))return false;')
        data=replacement(data,b'if(!env_.begin_frame(env_.user)||!barrier(false))return fail(Failure::world);',
            b'if(!begin_frame_cb(this)||!barrier(false))return fail(Failure::world);')
        data=replacement(data,b'std::uint64_t Controller::clock_cb(void* p) { auto& c=*static_cast<Controller*>(p);return c.env_.clock(c.env_.user); }',
            b'std::uint64_t Controller::clock_cb(void* p) {\r\n    auto& c=*static_cast<Controller*>(p);const auto now=c.env_.clock(c.env_.user);\r\n    if(now<c.clock_)c.fail(Failure::clock);else c.clock_=now;\r\n    return now; // Return the actual observation; never clamp or fabricate time.\r\n}')
        data=replacement(data,b'bool Controller::begin_frame_cb(void* p) { auto& c=*static_cast<Controller*>(p);return c.healthy()&&c.env_.begin_frame(c.env_.user)&&c.healthy(); }',
            b'bool Controller::begin_frame_cb(void* p) {\r\n    auto& c=*static_cast<Controller*>(p);if(!c.healthy())return false;\r\n    if(!c.env_.begin_frame(c.env_.user)||!c.healthy())return c.fail(Failure::world);\r\n    return true;\r\n}')
    elif name=='test_host.cmd':
        data=replacement(data,b'/EHsc test_host.cpp ',b'/EHsc test_host_r2.cpp ')
    create(HERE/name,data)
create(HERE/'predecessor-README.md',read(OLD/'README.md'))
create(HERE/'host-r2.diff',''.join(difflib.unified_diff(read(OLD/'host.cpp').decode().splitlines(True),read(HERE/'host.cpp').decode().splitlines(True),fromfile='sealed-v19/host.cpp',tofile='r2/host.cpp')).encode())
pins=json.loads(read(OLD/'input-pins.json'))
for name in index['sources']:pins[(OLD/name).relative_to(ROOT).as_posix()]=desc(OLD/name)
for name in ('review.json','source-index.json'):pins[(OLD/name).relative_to(ROOT).as_posix()]=desc(OLD/name)
for name in ('review.json','test_independent.cpp','independent.stdout.txt'):
    p=ROOT/'work/review-results/v19-host-native-inventory-20261008a'/name;pins[p.relative_to(ROOT).as_posix()]=desc(p)
assert len(pins)<=64
create(HERE/'input-pins.json',(json.dumps(pins,sort_keys=True,indent=2)+'\n').encode())
prepare=read(OLD/'prepare.py').replace(index['input_pins_sha256'].encode(),desc(HERE/'input-pins.json')['sha256'].encode())
create(HERE/'prepare.py',prepare)
print(json.dumps({'copied_sources':len(index['sources']),'input_pins':len(pins),'native_changed':['host.cpp'],'old_modified':False}))
