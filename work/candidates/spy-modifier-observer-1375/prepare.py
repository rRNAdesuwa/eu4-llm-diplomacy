"""Read-only sealed candidate check. No execution of a process sampler."""
import argparse,hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def raw(path,limit=4*1024*1024):
 with Path(path).open('rb') as f:value=f.read(limit+1)
 if len(value)>limit:raise ValueError('bounded input')
 return value
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for part in iter(lambda:f.read(262144),b''):h.update(part)
 return h.hexdigest()
def check():
 r=json.loads(raw(HERE/'review.json'));indexraw=raw(HERE/'source-index.json');assert hashlib.sha256(indexraw).hexdigest()==r['source_index_sha256'];index=json.loads(indexraw)
 for name,row in index.items():
  p=ROOT/name;assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],name
 v=ROOT/r['validation_path'];assert sha(v)==r['validation_sha256'];validation=json.loads(raw(v))
 assert validation['all_exit_zero'] is True and validation['inputs_unchanged'] is True
 assert r['process_accessed'] is False and r['runtime_verified'] is False and r['native_call_authorized'] is False
 print(json.dumps({'check':True,'fixed_sources':len(index),'review_sha256':sha(HERE/'review.json'),'process_accessed':False}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true',required=True);p.parse_args();check()
