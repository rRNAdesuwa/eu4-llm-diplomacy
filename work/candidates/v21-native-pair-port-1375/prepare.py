"""Verify fixed inputs and exact source bytes; never materializes formal files."""
import hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
FILES=('component/pair_component.h','component/pair_component.cpp','native_pair_engine.h','native_pair_engine.cpp',
 'native_platform.h','native_platform.cpp','native_pins.h','pin-provenance.json','test_native_pair_engine.cpp',
 'test_r2_spy_setter.cpp','build_test.cmd','collect_pins.py','validate.py','prepare.py','seal.py','README.md','input-pins.json','input-pins-initial.json')
def read(p,limit=4*1024*1024):
 with p.open('rb') as f:b=f.read(limit+1)
 assert len(b)<=limit, str(p)
 return b
def desc(p):
 b=read(p);return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def current():return {name:desc(HERE/name) for name in FILES}
def inputs():
 pins=json.loads(read(HERE/'input-pins.json'));assert type(pins) is dict and len(pins)<=32
 total=0
 for name,expected in pins.items():
  assert name.startswith('work/') and '..' not in Path(name).parts
  got=desc(ROOT/name);assert got==expected,name;total+=got['bytes']
 assert total<=8*1024*1024
 initial=json.loads(read(HERE/'input-pins-initial.json'))
 assert all(pins[k]==v for k,v in initial.items())
 return pins
def check():
 before=inputs();index=json.loads(read(HERE/'source-index.json'));assert index==current()
 # Copy lineage is exact, not a rewrite of the historical interface declaration.
 for name in ['pair_component.h','pair_component.cpp']:
  assert read(HERE/'component'/name)==read(ROOT/'work/candidates/v21-core-pair-nosend-r2-1375'/name)
 from collect_pins import generate
 evidence,header=generate();assert evidence==json.loads(read(HERE/'pin-provenance.json'));assert header==read(HERE/'native_pins.h')
 if (HERE/'review.json').exists():
  review=json.loads(read(HERE/'review.json'))
  for k in ['report','validation','source_index']:
   path={'report':'report.json','validation':'validation-final/validation.json','source_index':'source-index.json'}[k]
   assert desc(HERE/path)==review[k]
  validation=json.loads(read(HERE/'validation-final/validation.json'))
  assert validation['passed'] and validation['before']==index and validation['after']==index
  total=0
  for name,v in validation['outputs'].items():
   assert '..' not in Path(name).parts;got=desc(HERE/'validation-final'/name);assert got==v;total+=got['bytes']
  assert total<=16*1024*1024
 assert inputs()==before and current()==index
 print(json.dumps({'check':'passed','sources':len(index),'inputs':len(before),'game_accessed':False,'new_decode':0,'native_platform_executed':False}))
if __name__=='__main__':
 assert sys.argv[1:]==['--check'];check()
