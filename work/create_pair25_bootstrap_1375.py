"""Create fresh V25 DLL source tree using the corrected submission port."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'work/candidates/v24-pair-send-bootstrap-1375'
PORT=ROOT/'work/candidates/v24-pair-send-port-r2-1375'
HERE=ROOT/'work/candidates/v25-pair-send-bootstrap-1375'
def desc(p):
 b=p.read_bytes();assert len(b)<4*1024*1024
 return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
ix=json.loads((OLD/'source-index.json').read_bytes());assert all(desc(OLD/n)==v for n,v in ix.items())
px=json.loads((PORT/'source-index.json').read_bytes());v=json.loads((PORT/'development-attempt1/validation.json').read_bytes())
assert v['passed'] and v['sources_before']==v['sources_after']==px and v['build']['all_children_collected']
assert all(desc(PORT/n)==x for n,x in px.items())
with (PORT/'review.json').open('x') as f:json.dump(dict(status='AUTHOR_SYNTHETIC_PASS',source_index=desc(PORT/'source-index.json'),validation=desc(PORT/'development-attempt1/validation.json'),
 game_accessed=False,native_game_called=False,production_ready=False,independent_review=False),f,indent=2,sort_keys=True)
pins=json.loads((OLD/'input-pins.json').read_bytes())
pins.update({(OLD/n).relative_to(ROOT).as_posix():x for n,x in ix.items()})
pins.update({(PORT/n).relative_to(ROOT).as_posix():x for n,x in px.items()})
for n in ['source-index.json','development-attempt1/validation.json','review.json']:pins[(PORT/n).relative_to(ROOT).as_posix()]=desc(PORT/n)
HERE.mkdir(exist_ok=False);(HERE/'preimages').mkdir()
for name in ix:
 if name=='input-pins.json':continue
 data=(OLD/name).read_bytes()
 with (HERE/'preimages'/name).open('xb') as f:f.write(data)
 text=data.decode('ascii').replace('v24-pair-send-bootstrap','v25-pair-send-bootstrap').replace('pair24','pair25').replace('_v24','_v25').replace('V24','V25')
 text=text.replace('v24-pair-send-port-1375','v24-pair-send-port-r2-1375')
 if name=='README.md':text+='\nV25 uses the corrected R2 transport vtable slot binding; prior V24 terminal session is never reused.\n'
 with (HERE/name).open('xb') as f:f.write(text.encode('ascii'))
with (HERE/'input-pins.json').open('x') as f:json.dump(pins,f,indent=2,sort_keys=True)
print(json.dumps(dict(candidate=str(HERE),input_pins=len(pins))))
