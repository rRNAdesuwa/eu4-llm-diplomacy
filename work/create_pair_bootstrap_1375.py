"""Create a fresh no-send owner-hook candidate; never install it."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
HERE=ROOT/'work/candidates/v22-pair-nosend-bootstrap-1375'
OLD=ROOT/'work/candidates/v19-spy-bootstrap-lab-1375'
def desc(p):
 assert p.stat().st_size<=4*1024*1024
 b=p.read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
HERE.mkdir(exist_ok=False);pins={}
for name in ['installer.cpp','installer.h','thread_freeze.inc','frame.asm']:
 data=(OLD/name).read_bytes()
 with (HERE/name).open('xb') as f:f.write(data)
 pins[str((OLD/name).relative_to(ROOT)).replace('\\','/')]=desc(OLD/name)
for candidate in ['v21-native-pair-port-r2-1375','v21-native-pair-guard-r2-1375','core-five-full88-and-spy-entry-r2-1375']:
 base=ROOT/'work/candidates'/candidate
 for index in ['input-pins.json','source-index.json']:
  for name,pin in json.loads((base/index).read_bytes()).items():
   path=ROOT/name if index=='input-pins.json' else base/name
   assert desc(path)==pin;pins[str(path.relative_to(ROOT)).replace('\\','/')]=pin
 for name in ['review.json','source-index.json']:pins[str((base/name).relative_to(ROOT)).replace('\\','/')]=desc(base/name)
pins['work/create_pair_bootstrap_1375.py']=desc(Path(__file__))
with (HERE/'input-pins.json').open('x') as f:json.dump(pins,f,indent=2,sort_keys=True)
print(json.dumps(dict(created=str(HERE),inputs=len(pins),DLL_installed=False)))
