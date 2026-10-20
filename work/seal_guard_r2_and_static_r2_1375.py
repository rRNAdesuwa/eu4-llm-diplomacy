"""Seal completed validations, without repeating compilation or testing."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def raw(p):
 assert p.stat().st_size<=8*1024*1024
 return p.read_bytes()
def desc(p):
 b=raw(p);return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def put(p,d):
 with p.open('xb') as f:f.write((json.dumps(d,indent=2,sort_keys=True)+'\n').encode())
for candidate in ['v21-native-pair-guard-r2-1375','core-five-full88-and-spy-entry-r2-1375']:
 here=ROOT/'work/candidates'/candidate;assert not (here/'review.json').exists()
 index=json.loads(raw(here/'source-index.json'));pins=json.loads(raw(here/'input-pins.json'))
 assert all(desc(here/k)==v for k,v in index.items()) and all(desc(ROOT/k)==v for k,v in pins.items())
 val=here/'development-attempt1/validation.json';d=json.loads(raw(val));assert d['passed'] and d['build']['all_children_collected'] and d['build']['job_active_processes_final']==0
 assert d['inputs_before']==d['inputs_after']==pins and d['sources_before']==d['sources_after']==index
 if candidate.startswith('v21'):
  assert 'guard_groups=22 ' in d['test_stdout'] and 'native_env_type_groups=3 ' in d['native_environment_type_stdout']
  put(here/'report.json',dict(scope='Author source-bound compile, fake Guard/adapter composition, and actual sampler on analysis-owned allocations only.',
   validation=desc(val),source_count=len(index),inputs=len(pins),guard_groups=22,type_boundary_groups=3,build=d['build'],
   game_accessed=False,native_game_called=False,NativeEnvironment_initialize_called=False,DLL_built=False,
   public_backend_registered=False,production_ready=False,strict_SP_verified=False,world_epoch_verified=False,independently_reviewed=False))
 else:assert 'Ran 20 tests' in d['test_output']
 put(here/'review.json',dict(schema=1,status='AUTHOR_STATIC_SYNTHETIC_PASS',report=desc(here/'report.json'),
  source_index=desc(here/'source-index.json'),validation_path='development-attempt1/validation.json',validation=desc(val),
  independent_review=False,game_accessed=False,native_game_called=False,production_ready=False,sealing_helper=desc(Path(__file__))))
 print(json.dumps(dict(candidate=candidate,review=desc(here/'review.json'))))
