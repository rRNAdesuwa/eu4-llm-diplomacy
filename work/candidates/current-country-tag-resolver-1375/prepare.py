"""Bounded file-only source inventory check."""
from pathlib import Path
import hashlib,json,argparse
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def check():
    index=json.loads((HERE/'source-index.json').read_bytes());assert len(index['files'])<=32
    total=0
    for name,h in index['files'].items():
        path=ROOT/name;assert path.resolve().is_relative_to(ROOT) and not name.startswith('bridge/')
        with path.open('rb') as f:raw=f.read(8*1024*1024+1)
        total+=len(raw);assert len(raw)<=8*1024*1024 and total<=16*1024*1024 and hashlib.sha256(raw).hexdigest()==h,name
    return dict(files=len(index['files']),bytes=total,process_access=False,native_calls=False)
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--check',action='store_true',required=True);a.parse_args();print(json.dumps(check()))
