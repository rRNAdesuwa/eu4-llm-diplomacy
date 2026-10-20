"""Deterministic bounded inventory; check is read-only."""
import argparse,hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SOURCES=['README.md','explore.py','trace.py','constructor_model.py','test_model.py','prepare.py','validate.py','input-pins.json','report.json']
def digest(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def load(p):
 with p.open('rb')as f:b=f.read(2*1024*1024+1)
 if len(b)>2*1024*1024:raise ValueError('bound')
 return json.loads(b)
def render():
 inputs=load(HERE/'input-pins.json')
 for p,h in inputs.items():assert digest(ROOT/p)==h,p
 sources={str((HERE/n).relative_to(ROOT)).replace('\\','/'):{'sha256':digest(HERE/n),'bytes':(HERE/n).stat().st_size}for n in SOURCES}
 return {'schema':1,'purpose':'four_spy_normal_AI_static_candidate','inputs':inputs,'sources':sources,'runtime_verified':False,'production_ready':False}
def main():
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
 b=(json.dumps(render(),ensure_ascii=False,indent=2)+'\n').encode();out=HERE/'source-index.json'
 if a.check:assert out.read_bytes()==b
 else:
  with out.open('xb')as f:f.write(b)
 print(json.dumps({'check':a.check,'sha256':hashlib.sha256(b).hexdigest()}))
if __name__=='__main__':main()
