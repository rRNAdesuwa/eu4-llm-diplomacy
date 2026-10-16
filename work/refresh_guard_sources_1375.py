"""Refresh only the explicitly unsealed guard draft index; preserve its preimage."""
import importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
HERE=ROOT/'work/candidates/v21-native-pair-guard-1375'
assert not (HERE/'review.json').exists()
spec=importlib.util.spec_from_file_location('guard_draft_prepare',HERE/'prepare.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
assert {p:module.desc(ROOT/p) for p in module.INPUTS}==json.loads(module.raw(HERE/'input-pins.json'))
index=HERE/'source-index.json'
with (HERE/'development-attempt1/source-index-before-header-composition.json').open('xb') as f:f.write(index.read_bytes())
index.write_bytes((json.dumps({p:module.desc(HERE/p) for p in module.SOURCES},sort_keys=True,indent=2)+'\n').encode('ascii'))
print(json.dumps(dict(unsealed_only=True,sources=len(module.SOURCES),inputs=len(module.INPUTS))))
