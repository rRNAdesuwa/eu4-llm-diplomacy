"""Seal guard R3 author validation and create new, never-loaded V23 sources."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def desc(p):
 assert p.stat().st_size<=8*1024*1024
 b=p.read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def put(p,b):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(b if isinstance(b,bytes) else b.encode())
def seal(p,d):put(p,json.dumps(d,indent=2,sort_keys=True)+'\n')
guard=ROOT/'work/candidates/v21-native-pair-guard-r3-1375'
v=json.loads((guard/'development-attempt1/validation.json').read_bytes())
assert v['passed'] and v['build']['all_children_collected'] and v['build']['job_active_processes_final']==0
assert v['sources_before']==v['sources_after']==json.loads((guard/'source-index.json').read_bytes())
assert v['inputs_before']==v['inputs_after']==json.loads((guard/'input-pins.json').read_bytes())
assert 'guard_groups=23 ' in v['test_stdout']
seal(guard/'review.json',dict(status='AUTHOR_SYNTHETIC_PASS',source_index=desc(guard/'source-index.json'),validation=desc(guard/'development-attempt1/validation.json'),guard_groups=23,type_groups=3,game_accessed=False,native_game_called=False,production_ready=False,independent_review=False))
OLD=ROOT/'work/candidates/v22-pair-nosend-bootstrap-1375';HERE=ROOT/'work/candidates/v23-pair-nosend-bootstrap-1375'
HERE.mkdir(exist_ok=False)
index=json.loads((OLD/'source-index.json').read_bytes());pins=json.loads((OLD/'input-pins.json').read_bytes())
assert all(desc(OLD/k)==v for k,v in index.items()) and all(desc(ROOT/k)==v for k,v in pins.items())
for name in index:
 if name=='input-pins.json':continue
 data=(OLD/name).read_bytes();put(HERE/'preimages'/name,data);pins[(OLD/name).relative_to(ROOT).as_posix()]=desc(OLD/name)
 data=data.replace(b'pair22',b'pair23').replace(b'v22',b'v23').replace(b'V22',b'V23')
 data=data.replace(b'v21-native-pair-guard-r2-1375',b'v21-native-pair-guard-r3-1375').replace(b'current-country-tag-cpp-1375',b'current-country-tag-cpp-r2-1375')
 put(HERE/name,data)
notes='''# V23 no-send repair

V22 terminated before native calls because the full table includes 405 passive
selectors 1..7. V23 binds country resolver R2 and guard R3. Passive handles stay
fully checked and compared; requested nonordinary selectors remain refused.
The sender is absent. Native platform, core, allocator restrictions, hook,
claim protocol and no-retry policy are unchanged. This candidate needs a fresh
process. V22 files and permanent unclaimed requests must never be reused.
'''
(HERE/'README.md').write_text(notes,encoding='ascii')
for base in [guard,ROOT/'work/candidates/current-country-tag-cpp-r2-1375']:
 for name,pin in json.loads((base/'source-index.json').read_bytes()).items():pins[(base/name).relative_to(ROOT).as_posix()]=pin
 pins[(base/'review.json').relative_to(ROOT).as_posix()]=desc(base/'review.json')
pins['work/runtime/pair22-session-20261012a/inspect.stdout']=desc(ROOT/'work/runtime/pair22-session-20261012a/inspect.stdout')
pins[Path(__file__).relative_to(ROOT).as_posix()]=desc(Path(__file__))
seal(HERE/'input-pins.json',pins)
script=(ROOT/'work/seal_pair_bootstrap_1375.py').read_bytes().replace(b'v22',b'v23').replace(b'pair22',b'pair23')
put(ROOT/'work/seal_pair23_bootstrap_1375.py',script)
print(json.dumps(dict(candidate=HERE.name,guard_review=desc(guard/'review.json'),inputs=len(pins))))
