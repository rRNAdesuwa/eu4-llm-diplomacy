"""Create/check the isolated candidate index; no upstream mutations."""
import argparse,hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SOURCES=['README.md','explore.py','trace.py','facts.json','contract.py','test_contract.py','prepare.py','validate.py','input-pins.json','report.json']+[f'exploration-{n:02}.json' for n in range(1,6)]
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def load(p):
 with p.open('rb') as f:b=f.read(4*1024*1024+1)
 if len(b)>4*1024*1024:raise ValueError('bounded JSON')
 return json.loads(b)
def render():
 pins=load(HERE/'input-pins.json')
 for name,sha in pins.items():assert digest(ROOT/name)==sha,name
 return {'schema':1,'purpose':'war_dynasty_province_static_contract','inputs':pins,
  'sources':{str((HERE/n).relative_to(ROOT)).replace('\\','/'):{'sha256':digest(HERE/n),'bytes':(HERE/n).stat().st_size} for n in SOURCES},
  'runtime_verified':False,'production_ready':False}
def main():
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
 b=(json.dumps(render(),ensure_ascii=False,indent=2)+'\n').encode();path=HERE/'source-index.json'
 if a.check:assert path.read_bytes()==b
 else:
  with path.open('xb') as f:f.write(b)
 print(json.dumps({'check':a.check,'source_index_sha256':hashlib.sha256(b).hexdigest()}))
if __name__=='__main__':main()
