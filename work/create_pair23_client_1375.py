"""Create fresh V23 client from unchanged V22 R2 behavior; no process access."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OLD=ROOT/'work/candidates/v22-pair-private-client-r2-1375';HERE=ROOT/'work/candidates/v23-pair-private-client-1375'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(OLD/'review.json')=='d1cdbb2f337313fdb453ce3dc4fcac987d16b9069e57132e19297d378d113c28'
HERE.mkdir(exist_ok=False)
for name,pin in json.loads((OLD/'source-index.json').read_bytes()).items():
    data=(OLD/name).read_bytes();assert len(data)==pin['bytes'] and hashlib.sha256(data).hexdigest()==pin['sha256']
    data=data.replace(b'v22-pair-nosend-bootstrap-1375',b'v23-pair-nosend-bootstrap-1375').replace(b'pair22',b'pair23').replace(b'_v22',b'_v23').replace(b'V22',b'V23')
    if name=='client.py':data=re.sub(rb"MANIFEST_SHA='[0-9a-f]{64}'",b"MANIFEST_SHA='"+sha(ROOT/'work/candidates/v23-pair-nosend-bootstrap-1375/development-attempt1/build/build.json').encode()+b"'",data)
    with (HERE/name).open('xb') as f:f.write(data)
print(str(HERE))
