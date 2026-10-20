"""File-only draft source pins; no process/decoder/old capture."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import linked_truce_projection as module


def main():
 require=module.require;out=module.MANIFEST
 require(not out.exists(),'Draft manifest already exists; preserve before any revised source')
 selected=set(module.FIXED)|module.REQUIRED
 pins={n:module.pin(module.local_path(n)) for n in sorted(selected)}
 for n,h in module.FIXED.items():require(pins[n]['sha256']==h,'Fixed source changed')
 value=dict(schema='EU4-LINKED-TRUCE-PROJECTION-MANIFEST/1',sealed=False,game_sha256=module.GAME_SHA,
  source_pins=pins,runtime_capture_authorized=False,stage='candidate_waiting_independent_source_review',
  native_ready=False)
 with out.open('x',encoding='utf-8',newline='\n') as f:f.write(json.dumps(value,indent=2)+'\n')
 verified=module.verify_sources()
 print(json.dumps(dict(manifest=module.pin(out),source_pins=len(verified['source_pins']),sealed=False,
  runtime_capture_authorized=False,process_accesses=0)))


if __name__=='__main__':main()
