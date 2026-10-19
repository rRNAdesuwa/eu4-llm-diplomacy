import hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
FILES=['contract.py','test_contract.py','test_stack_alias.py','README.md','prepare.py','validate.py','build_test.cmd','report.json','input-pins.json',
 'preimages/contract.py','preimages/test_contract.py','preimages/report.json']
def desc(p):
 assert p.stat().st_size<=4*1024*1024
 b=p.read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def current():return {name:desc(HERE/name) for name in FILES}
def inputs():
 pins=json.loads((HERE/'input-pins.json').read_bytes());assert all(desc(ROOT/k)==v for k,v in pins.items());return pins
if __name__=='__main__':
 inputs()
 if sys.argv[1:]==['--index']:
  with (HERE/'source-index.json').open('xb') as f:f.write((json.dumps(current(),indent=2,sort_keys=True)+'\n').encode())
 else:assert sys.argv[1:]==['--check'] and current()==json.loads((HERE/'source-index.json').read_bytes())
