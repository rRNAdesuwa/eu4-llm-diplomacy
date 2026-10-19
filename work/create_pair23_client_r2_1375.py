"""Preserve first V23 wire-fixture failure; correct only its pinned test constant."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OLD=ROOT/'work/candidates/v23-pair-private-client-1375';HERE=ROOT/'work/candidates/v23-pair-private-client-r2-1375'
v=json.loads((OLD/'development-attempt1/validation.json').read_bytes());assert not v['passed'] and v['build']['all_children_collected']
HERE.mkdir(exist_ok=False)
for name,pin in json.loads((OLD/'source-index.json').read_bytes()).items():
    data=(OLD/name).read_bytes();assert len(data)==pin['bytes'] and hashlib.sha256(data).hexdigest()==pin['sha256']
    if name=='test_wire_fixture.cpp':
        old=b'a938c06e8acd8ff1be9fe8606aeba882d3d8baeeb3acb6b3575156146f8f0aae';assert data.count(old)==1
        data=data.replace(old,b'e5caf4f66f49453e2cb91663cd531ee1df78b47591c59616293022ea818cf184')
    if name=='README.md':data+=b'\nV23 R2 corrects the C++ test manifest constant only. The first wire mismatch is preserved; client.py is byte-identical.\n'
    with (HERE/name).open('xb') as f:f.write(data)
print(str(HERE))
