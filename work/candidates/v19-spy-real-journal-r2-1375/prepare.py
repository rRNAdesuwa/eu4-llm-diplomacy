"""Read-only bounded candidate verification, no actual trace invocation."""
from pathlib import Path
import argparse,hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def check():
    with (HERE/'source-index.json').open('rb') as f:raw=f.read(128*1024+1)
    assert len(raw)<=128*1024;index=json.loads(raw);assert index['schema']==2 and len(index['files'])<=128
    total=0
    for name,digest in index['files'].items():
        path=(ROOT/name).resolve();assert path.is_relative_to(ROOT)
        with path.open('rb') as f:raw=f.read(2*1024*1024+1)
        total+=len(raw);assert len(raw)<=2*1024*1024 and total<=16*1024*1024
        assert hashlib.sha256(raw).hexdigest()==digest,name
    return dict(checked=len(index['files']),bytes=total,actual_process_access=False,new_decoded_bytes=0)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',required=True,action='store_true');p.parse_args();print(json.dumps(check()))
