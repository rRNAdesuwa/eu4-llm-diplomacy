"""Freeze new source before its first fake suite. No libraries/PE/process access."""
from pathlib import Path
import hashlib
import json
import types
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def pin(path):
 b=path.read_bytes();assert 0<len(b)<=4194304;return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(name,value):
 with (HERE/name).open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,ensure_ascii=True,sort_keys=True,indent=2);f.write('\n')
def main():
 raw=(HERE/'peace_current_pending.py').read_bytes();module=types.ModuleType('_peace_manifest_source');module.__file__=str(HERE/'peace_current_pending.py')
 exec(compile(raw,module.__file__,'exec'),module.__dict__)
 owner_path=ROOT/(module.DESIGN+'manifest.json');assert pin(owner_path)['sha256']==module.FIXED[module.DESIGN+'manifest.json']
 owner=json.loads(owner_path.read_bytes());pins={**owner['local_pins'],**owner['captured_source_pins']}
 for n in module.FIXED:
  p=pin(ROOT/n);assert p['sha256']==module.FIXED[n];pins[n]=p
 for n in module.REQUIRED:pins[n]=pin(ROOT/n)
 assert sum(p['bytes'] for p in pins.values())<=16*1024*1024 and len(pins)<=96
 for n,p in pins.items():assert pin(ROOT/n)==p
 value=dict(schema='EU4-PEACE-CURRENT-PENDING-MANIFEST/1',sealed=False,runtime_capture_authorized=False,
  stage='draft_source_frozen_before_first_new_fake_suite',game_sha256=module.GAME_SHA,
  source_pins=pins,source_graph_sha256=module.graph_digest(pins),
  independent_source_review=None,production_review=None,native_ready=False,selected_effect_verified=False)
 save('source-manifest.json',value)
 checked=module.verify_sources()
 save('preparation.json',dict(schema='EU4-PEACE-PENDING-PREPARATION/1',source_manifest=pin(HERE/'source-manifest.json'),
  source_pins=pins,source_graph_sha256=value['source_graph_sha256'],owner_graph_complete=True,
  delegated_closure='Frozen direct-v1 Libraries verifies its selected sources and old host closure when check/catalog are first run.',
  tests_run=0,actual_status_run=False,PE_game_access=0,Win32_process_reads=0,
  native_calls=0,independent_candidate_source_review='pending',production_review='pending'))
 print(json.dumps(dict(status='draft_frozen',source_manifest=pin(HERE/'source-manifest.json'),source_count=len(pins),
  source_bytes=sum(p['bytes'] for p in pins.values()),source_graph_sha256=value['source_graph_sha256'],runtime_capture_authorized=False)))
if __name__=='__main__':main()
