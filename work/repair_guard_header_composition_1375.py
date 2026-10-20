"""Preserve failed draft; normalize only duplicate component include identity."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
HERE=ROOT/'work/candidates/v21-native-pair-guard-1375'
before=HERE/'development-attempt1/source-preimages';before.mkdir(exist_ok=False)
index=json.loads((HERE/'source-index.json').read_bytes())
for name in [*index,'source-index.json']:
    data=(HERE/name).read_bytes()
    with (before/name).open('xb') as f:f.write(data)
copy=HERE/'port';copy.mkdir(exist_ok=False)
engine=(ROOT/'work/candidates/v21-native-pair-port-1375/native_pair_engine.h').read_bytes()
old=b'#include "component/pair_component.h"'
new=b'#include "../../v21-core-pair-nosend-r2-1375/pair_component.h"'
assert engine.count(old)==1
engine=engine.replace(old,new)
with (copy/'native_pair_engine.h').open('xb') as f:f.write(engine)
platform=(ROOT/'work/candidates/v21-native-pair-port-1375/native_platform.h').read_bytes()
with (copy/'native_platform.h').open('xb') as f:f.write(platform)
def d(data):return dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
record=dict(reason='two physical pragma-once headers with identical declarations caused C2011; one canonical shared component header is required',
    engine_original=d((ROOT/'work/candidates/v21-native-pair-port-1375/native_pair_engine.h').read_bytes()),engine_composed=d(engine),
    exact_include_change=dict(old=old.decode(),new=new.decode()),platform_exact_copy=d(platform),native_call_or_semantics_changed=False,
    frozen_sources_modified=False,game_accessed=False)
with (HERE/'header-composition.json').open('xb') as f:f.write((json.dumps(record,indent=2,sort_keys=True)+'\n').encode('ascii'))
print(json.dumps(record))
