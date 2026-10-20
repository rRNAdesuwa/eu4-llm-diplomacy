"""Read-only candidate and frozen dependency verification."""
from pathlib import Path
import argparse,hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def check():
    index=json.loads((HERE/'source-index.json').read_bytes());assert index['schema']==1 and len(index['files'])<=256
    total=0
    for name,digest in index['files'].items():
        path=(ROOT/name).resolve();assert path.is_relative_to(ROOT)
        with path.open('rb') as stream:raw=stream.read(2*1024*1024+1)
        total+=len(raw);assert len(raw)<=2*1024*1024 and total<=20*1024*1024
        assert hashlib.sha256(raw).hexdigest()==digest,name
    import frozen
    frozen.verify_build(frozen.BUILD)
    return dict(checked=len(index['files']),bytes=total,actual_process_access=False,publication_attempted=False)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',required=True,action='store_true');p.parse_args();print(json.dumps(check(),sort_keys=True))
