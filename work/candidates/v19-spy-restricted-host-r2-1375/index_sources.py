"""Create the bounded local R2 index before validation; never edits its input."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def desc(p):
    with p.open('rb') as f:b=f.read(262145)
    assert len(b)<=262144
    return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
old=json.loads((ROOT/'work/candidates/v19-spy-restricted-host-1375/source-index.json').read_text())
names=set(old['sources'])|{'derive.py','test_host_r2.cpp','predecessor-README.md','host-r2.diff','index_sources.py'}
assert len(names)<=64
value={'schema_version':1,'input_pins_sha256':desc(HERE/'input-pins.json')['sha256'],
       'sources':{n:desc(HERE/n) for n in sorted(names)}}
with (HERE/'source-index.json').open('x',encoding='utf-8') as f:json.dump(value,f,sort_keys=True,indent=2);f.write('\n')
print(json.dumps({'sources':len(names),'index':desc(HERE/'source-index.json')}))
