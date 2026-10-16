"""Prepared candidate integrity only; no test, real reader or frozen input replay."""
import hashlib,json
from pathlib import Path
here=Path(__file__).resolve().parent;root=here.parents[2]
m=json.loads((here/'delivery-manifest.json').read_text(encoding='utf-8'))
for name,expected in m['candidate_files'].items():
 p=root/name;assert p.is_relative_to(here)
 raw=p.read_bytes();assert dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())==expected,name
r=json.loads((here/'offline-r1/receipt.json').read_text(encoding='utf-8'))
assert r['passed'] is True and r['source_guard_equal'] is True
assert {n:r['source_pins_before'][n] for n in m['selected_frozen_inputs']}==m['selected_frozen_inputs']
assert r['source_pins_before']==r['source_pins_after']
print(json.dumps(dict(ok=True,candidate_files=len(m['candidate_files']),frozen_source_pin_metadata=len(m['selected_frozen_inputs']),
                      old_input_reopens=0,tests_repeated=0,target_access=False)))
