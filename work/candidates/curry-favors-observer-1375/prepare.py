"""Verify frozen disk inputs and candidate source inventory only."""
import argparse,hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def bounded(p,n):
 with p.open('rb') as f:b=f.read(n+1)
 if len(b)>n:raise ValueError('file budget')
 return b
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def check():
 report=json.loads(bounded(HERE/'report.json',4*1024*1024));index=json.loads(bounded(HERE/'source-index.json',65536))
 assert len(report['sources'])<=128 and len(index)<=24
 total=0
 for name,digest in report['sources'].items():
  path=(ROOT/name).resolve();path.relative_to(ROOT);assert sha(path)==digest,name
 for name,value in index.items():
  path=(HERE/name).resolve();path.relative_to(HERE);raw=bounded(path,4*1024*1024);total+=len(raw)
  assert {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}==value,name
 assert total<16*1024*1024
 assert sha(ROOT.parent/'eu4.exe')==report['game_sha256']
 return {'sources':len(report['sources']),'candidate_files':len(index),'bytes':total,'runtime_verified':False,'process_access':False}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--check',required=True,action='store_true');p.parse_args();print(json.dumps(check()))
