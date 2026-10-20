"""Seal already validated private send components and actual DLL, never load."""
import hashlib,json,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def desc(p):
 b=p.read_bytes();assert len(b)<16*1024*1024;return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
for name in ['v24-pair-send-core-r2-1375','v24-pair-send-port-1375']:
 here=ROOT/'work/candidates'/name;vpath=here/'development-attempt1/validation.json'
 v=json.loads(vpath.read_bytes());ix=json.loads((here/'source-index.json').read_bytes())
 assert v['passed'] and v['sources_before']==v['sources_after']==ix and v['inputs_before']==v['inputs_after']
 assert all(desc(here/k)==p for k,p in ix.items()) and all(desc(ROOT/k)==p for k,p in v['inputs_before'].items())
 assert v['build']['all_children_collected'] and v['build']['job_active_processes_final']==0
 with (here/'review.json').open('x') as f:json.dump(dict(status='AUTHOR_SYNTHETIC_PASS',source_index=desc(here/'source-index.json'),
  validation=desc(vpath),game_accessed=False,native_game_called=False,production_ready=False,independent_review=False),f,indent=2,sort_keys=True)
old=ROOT/'work/seal_pair23_bootstrap_1375.py';data=old.read_bytes()
data=data.replace(b'v23-pair-nosend',b'v24-pair-send').replace(b'eu4_pair_nosend_lab_1375_v23',b'eu4_pair_send_lab_1375_v24')
data=data.replace(b'restricted_pair_nosend_1375_v23',b'restricted_pair_send_1375_v24').replace(b'no_send=True',b'no_send=False')
data=data.replace(b'Actual no-send research DLL compiled and linked; only codec tests executed.',
 b'Actual send-capable private DLL compiled and linked; codec tests only. Legacy installer send_supported=false is retained hook metadata, not Host capability attestation. Native transfer and effects are untested.')
module=types.ModuleType('_new_pair24_send_seal');module.__file__=str(Path(__file__))
exec(compile(data,str(Path(__file__)),'exec'),module.__dict__)
