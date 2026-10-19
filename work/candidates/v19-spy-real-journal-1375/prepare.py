"""Read-only source check. No materialization, build, process, or publisher."""
from pathlib import Path
import argparse
import hashlib
import json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def check():
    index=json.loads((HERE/'source-index.json').read_bytes())
    assert index['schema']==1 and len(index['files'])<=64
    total=0
    for name,digest in index['files'].items():
        path=(ROOT/name).resolve();assert path.is_relative_to(ROOT)
        with path.open('rb') as f:raw=f.read(2*1024*1024+1)
        total+=len(raw);assert len(raw)<=2*1024*1024 and total<=8*1024*1024
        assert hashlib.sha256(raw).hexdigest()==digest,name
    print(json.dumps({'checked':len(index['files']),'bytes':total,'source_unchanged':True,'actual_process_access':False}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true',required=True);p.parse_args();check()
