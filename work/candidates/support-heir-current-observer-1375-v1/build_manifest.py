"""Build this fixed draft after the R48/R50 static reviews; grants no capture authority."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import support_heir_current_observer as module

def main():
 assert sys.argv[1:]==[]
 module.require(not module.MANIFEST.exists(),'Manifest exists; preserve exact preimage before a revision')
 pins={n:module.pin(module.local_path(n)) for n in sorted(module.REQUIRED|set(module.FIXED))}
 for n,h in module.FIXED.items():module.require(pins[n]['sha256']==h,'Frozen source changed')
 for n in (module.R48_REVIEW,module.R50_REVIEW):
  review=module.json_file(module.local_path(n))
  module.require(review.get('passed') is True,'Static independent review must have passed')
 value=dict(schema='EU4-SUPPORT-HEIR-OBSERVER-MANIFEST/1',sealed=False,runtime_capture_authorized=False,
  game_sha256=module.GAME_SHA,source_pins=pins,
  static_independent_reviews={role:dict(path=n,**pins[n]) for role,n in (('R48',module.R48_REVIEW),('R50',module.R50_REVIEW))},
  candidate_review_status='pending_independent_source_review',native_ready=False,selected_effect_verified=False)
 with module.MANIFEST.open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,indent=2);f.write('\n')
 checked=module.verify_sources()
 print(json.dumps(dict(manifest=module.pin(module.MANIFEST),source_pins=len(checked['source_pins']),sealed=False,
  runtime_capture_authorized=False,game_process_accesses=0,tests_run=0)))

if __name__=='__main__':main()
