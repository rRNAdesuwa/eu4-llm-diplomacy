"""Preserve the first client's successful tests and failed report wrapper."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OLD=ROOT/'work/candidates/v22-pair-private-client-1375';NEW=ROOT/'work/candidates/v22-pair-private-client-r2-1375'
NEW.mkdir(exist_ok=False)
names=['client.py','test_client.py','test_wire_fixture.cpp','build_test.cmd','validate.py','README.md']
lineage={}
for name in names:
 b=(OLD/name).read_bytes();lineage[name]=dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
 if name=='validate.py':
  assert b.count(b'assert 0<p.stat().st_size<=4*1024*1024')==1
  b=b.replace(b'assert 0<p.stat().st_size<=4*1024*1024',b'assert 0<=p.stat().st_size<=4*1024*1024')
 if name=='README.md':b+=b'\nR2 changes only the offline reporting wrapper to accept empty stdout/stderr\nartifacts. All 15 first-attempt tests passed; its post-test report failed on an\nempty file. The first tree and output remain preserved. Client and tests are\nbyte-identical. No game or native action occurred in that failed wrapper.\n'
 with (NEW/name).open('xb') as f:f.write(b)
with (NEW/'lineage.json').open('x') as f:json.dump(dict(original='v22-pair-private-client-1375',source_preimages=lineage,client_changed=False,tests_changed=False),f,indent=2,sort_keys=True)
print(NEW)
