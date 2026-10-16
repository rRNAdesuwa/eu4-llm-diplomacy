"""Bounded file-only R3 seal checks; no process/game/PE access."""
import hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
FILES=('pair_component.h','pair_component.cpp','test_pair_component.cpp','test_r2_counter.cpp','profile-registry.json','typed_fixture.h',
 'test_r3_integration.cpp','build_test.cmd','adapter/native_pair_engine.cpp','adapter/native_pair_engine.h','adapter/test_native_pair_engine.cpp',
 'adapter/component/pair_component.h','prepare.py','validate.py','seal.py','README.md','input-pins.json','r3-delta.diff')
def read(path):
 with path.open('rb') as f:b=f.read(4*1024*1024+1)
 assert len(b)<=4*1024*1024,path
 return b
def desc(path):
 b=read(path);return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def current():return {k:desc(HERE/k) for k in FILES if (HERE/k).exists()}
def inputs():
 pins=json.loads(read(HERE/'input-pins.json'));assert len(pins)<=40;total=0
 for name,v in pins.items():
  assert name.startswith('work/') and '..' not in Path(name).parts
  got=desc(ROOT/name);assert got==v,name;total+=got['bytes']
 assert total<=8*1024*1024
 return pins
def check():
 old=ROOT/'work/candidates/v21-core-pair-nosend-r2-1375'
 adapter=ROOT/'work/candidates/v21-native-pair-port-1375'
 before=inputs();own=current();assert len(own)==len(FILES)
 assert own==json.loads(read(HERE/'source-index.json'))
 assert read(HERE/'pair_component.h')==read(old/'pair_component.h')==read(HERE/'adapter/component/pair_component.h')
 for name in ['native_pair_engine.h','native_pair_engine.cpp','test_native_pair_engine.cpp']:
  assert read(HERE/'adapter'/name)==read(adapter/name)
 for name in ['pair_component.h','pair_component.cpp','test_pair_component.cpp','test_r2_counter.cpp','profile-registry.json','build_test.cmd']:
  assert read(HERE/'preimages'/name)==read(old/name)
 assert read(HERE/'test_r2_counter.cpp')==read(old/'test_r2_counter.cpp')
 assert read(HERE/'profile-registry.json')==read(old/'profile-registry.json')
 if (HERE/'review.json').exists():
  review=json.loads(read(HERE/'review.json'))
  for key,path in [('validation','validation-final/validation.json'),('report','report.json'),('index','source-index.json')]:assert review[key]==desc(HERE/path)
  v=json.loads(read(HERE/'validation-final/validation.json'));assert v['passed'] and v['before']==v['after']==own
  for name,h in v['outputs'].items():assert desc(HERE/'validation-final'/name)==h
 assert inputs()==before and current()==own
 print(json.dumps({'check':'passed','sources':len(own),'inputs':len(before),'native_calls':0,'new_decode':0}))
if __name__=='__main__':assert sys.argv[1:]==['--check'];check()
