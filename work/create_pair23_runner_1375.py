"""Bind root recorder to fresh V23 client and exact new process; no process call."""
import hashlib,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];here=ROOT/'work/candidates/v23-pair-private-client-r2-1375'
b=(ROOT/'work/run_pair22_session_1375.py').read_bytes().replace(b'pair22',b'pair23').replace(b'V22',b'V23').replace(b'v22-pair-private-client-r2-1375',b'v23-pair-private-client-r2-1375')
for key,name in [('CLIENT_SHA','client.py'),('INDEX_SHA','source-index.json'),('PINS_SHA','input-pins.json')]:
    new=hashlib.sha256((here/name).read_bytes()).hexdigest().encode();b,n=re.subn(key.encode()+rb"='[a-f0-9]{64}'",key.encode()+b"='"+new+b"'",b);assert n==1
b=b.replace(b'PID=50684',b'PID=52236').replace(b"CREATION='01dd5a131399ebb8'",b"CREATION='01dd5a1a23ab2258'")
with (ROOT/'work/run_pair23_session_1375.py').open('xb') as f:f.write(b)
print('V23 recorder bound to 52236/01dd5a1a23ab2258')
