"""New fixed-batch private client for the separately sealed V25 DLL."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'work/candidates/v24-pair-send-private-client-1375'
HERE=ROOT/'work/candidates/v25-pair-send-private-client-1375'
manifest=ROOT/'work/candidates/v25-pair-send-bootstrap-1375/development-attempt1/build/build.json'
def desc(p):
 b=p.read_bytes();assert len(b)<4*1024*1024
 return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
ix=json.loads((OLD/'source-index.json').read_bytes());assert all(desc(OLD/n)==v for n,v in ix.items())
new_sha=desc(manifest)['sha256'];old_sha='3e6a875c0dbe622d83e51b14a3a3d5206b614b7206eb600a62fa4a6a1d5b8268'
HERE.mkdir(exist_ok=False);(HERE/'preimages').mkdir()
for name in ix:
 data=(OLD/name).read_bytes()
 with (HERE/'preimages'/name).open('xb') as f:f.write(data)
 text=data.decode('ascii').replace('v24-pair-send-bootstrap','v25-pair-send-bootstrap').replace('pair24','pair25').replace('_v24','_v25').replace('V24','V25').replace(old_sha,new_sha)
 if name=='client.py':text=text.replace('fixed six-positive no-send batch','fixed six-positive send batch')
 with (HERE/name).open('xb') as f:f.write(text.encode('ascii'))
print(json.dumps(dict(candidate=str(HERE),manifest_sha256=new_sha)))
