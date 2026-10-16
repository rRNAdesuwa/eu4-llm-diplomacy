"""Pin actual quoted include closure and fixed external translation units."""
import hashlib,json,re,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
FILES=['bootstrap.cpp','codec.h','installer.cpp','installer.h','thread_freeze.inc','frame.asm','test_codec.cpp','build_test.cmd','README.md','prepare.py','validate.py','input-pins.json']
EXTERNAL=['v21-native-pair-guard-r3-1375/native_guard.cpp','v21-native-pair-guard-r3-1375/native_env.cpp',
 'v24-pair-send-port-r2-1375/native_pair_engine.cpp','v24-pair-send-port-r2-1375/native_platform.cpp','v24-pair-send-port-r2-1375/submission_guard.cpp',
 'v24-pair-send-core-r2-1375/pair_send.cpp','current-country-tag-cpp-r2-1375/country_resolver.cpp','v21-five-cancel-reader-1375/cancel_reader.cpp']
def raw(p):
 assert p.stat().st_size<=4*1024*1024
 return p.read_bytes()
def desc(p):
 b=raw(p);return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def current():return {k:desc(HERE/k) for k in FILES}
def include_closure():
 pending=[HERE/'bootstrap.cpp',HERE/'installer.cpp',HERE/'test_codec.cpp']+[ROOT/'work/candidates'/k for k in EXTERNAL]
 seen={}
 while pending:
  p=pending.pop().resolve();key=str(p.relative_to(ROOT)).replace('\\','/')
  if key in seen:continue
  assert len(seen)<256;data=raw(p);seen[key]=desc(p)
  for name in re.findall(rb'^\s*#include\s+"([^"]+)"',data,re.M):
   child=(p.parent/name.decode('ascii')).resolve();assert child.is_relative_to(ROOT);pending.append(child)
 return seen
def inputs():
 pins=json.loads(raw(HERE/'input-pins.json'));assert all(desc(ROOT/k)==v for k,v in pins.items())
 closure=include_closure()
 for k,v in closure.items():
  if not (ROOT/k).is_relative_to(HERE):assert pins.get(k)==v,k
 return pins
if __name__=='__main__':
 if sys.argv[1:]==['--index']:
  pins=json.loads(raw(HERE/'input-pins.json'))
  # New, not-yet-sealed candidate: preserve the initial input list before adding
  # the concrete compiler include closure. No historical inputs are replaced.
  with (HERE/'input-pins-initial.json').open('xb') as f:f.write(raw(HERE/'input-pins.json'))
  for k,v in include_closure().items():
   if not (ROOT/k).is_relative_to(HERE):
    assert k not in pins or pins[k]==v;pins[k]=v
  (HERE/'input-pins.json').write_bytes((json.dumps(pins,indent=2,sort_keys=True)+'\n').encode())
  inputs()
  with (HERE/'source-index.json').open('xb') as f:f.write((json.dumps(current(),indent=2,sort_keys=True)+'\n').encode())
 else:
  assert sys.argv[1:]==['--check'];inputs();assert current()==json.loads(raw(HERE/'source-index.json'))
  print(json.dumps(dict(check=True,sources=len(current()),inputs=len(inputs()),include_closure=len(include_closure()))))
