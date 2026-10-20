"""Source inventory only; exclusive initial creation, subsequent read-only check."""
import argparse,hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SOURCES=['README.md','trace.py','explore.py','contract.json','contract_model.py','test_contract.py','prepare.py','validate.py','input-pins.json','report.json']
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for x in iter(lambda:f.read(1024*1024),b''):h.update(x)
 return h.hexdigest()
def render():
 pins=json.loads((HERE/'input-pins.json').read_text())
 for path,expected in pins.items():
  if digest(ROOT/path)!=expected:raise ValueError('input differs '+path)
 source={str((HERE/name).relative_to(ROOT)).replace('\\','/'):{'sha256':digest(HERE/name),'bytes':(HERE/name).stat().st_size} for name in SOURCES}
 return {'schema':1,'purpose':'curry_favors_static_candidate_sources','inputs':pins,'sources':source,'runtime_verified':False,'production_ready':False}
def main():
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
 data=(json.dumps(render(),ensure_ascii=False,indent=2)+'\n').encode();out=HERE/'source-index.json'
 if a.check:
  if out.read_bytes()!=data:raise ValueError('source index differs')
 else:
  with out.open('xb') as f:f.write(data)
 print(json.dumps({'check':a.check,'sha256':hashlib.sha256(data).hexdigest()}))
if __name__=='__main__':main()
