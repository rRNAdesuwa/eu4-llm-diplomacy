"""Read-only fixed candidate check. Never invokes a process reader."""
import argparse,hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(262144),b''):h.update(b)
 return h.hexdigest()
def bounded(p,limit=8*1024*1024):
 with p.open('rb') as f:b=f.read(limit+1)
 if len(b)>limit:raise ValueError('read bound')
 return b
def check():
 r=json.loads(bounded(HERE/'review.json'));b=bounded(HERE/'source-index.json');assert hashlib.sha256(b).hexdigest()==r['source_index_sha256']
 for name,row in json.loads(b).items():
  p=ROOT/name;assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],name
 p=ROOT/r['validation_path'];assert sha(p)==r['validation_sha256'];v=json.loads(bounded(p))
 assert v['all_exit_zero'] is True and v['inputs_unchanged'] is True
 assert r['process_accessed'] is False and r['native_call_authorized'] is False and r['runtime_verified'] is False
 print(json.dumps({'check':True,'review_sha256':sha(HERE/'review.json'),'fixed_inputs':len(json.loads(b)),'process_accessed':False}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true',required=True);p.parse_args();check()
