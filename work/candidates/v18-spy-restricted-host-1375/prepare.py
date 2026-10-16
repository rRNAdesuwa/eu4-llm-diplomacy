"""Check sealed bounded source pins only. No build, process access or publication."""
import argparse
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
MAX_FILE=2*1024*1024
MAX_TOTAL=16*1024*1024


def bounded(path,limit=MAX_FILE):
    with path.open('rb') as stream:raw=stream.read(limit+1)
    if len(raw)>limit:raise ValueError('Input exceeds read budget: '+str(path))
    return raw


def descriptor(path):
    raw=bounded(path)
    return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def check():
    sources=json.loads(bounded(HERE/'source-pins.json',65536))
    local=json.loads(bounded(HERE/'candidate-index.json',65536))
    if type(sources)is not dict or type(local)is not dict or not 1<=len(sources)<=128 or not 1<=len(local)<=32:raise ValueError('Pin count budget')
    total=0
    for name,want in dict(sources,**local).items():
        p=Path(name)
        if p.is_absolute() or '..' in p.parts or '\\' in name:raise ValueError('Pin path')
        path=ROOT/p
        if not path.resolve().is_relative_to(ROOT.resolve()):raise ValueError('Pin escaped root')
        actual=descriptor(path);total+=actual['bytes']
        if actual!=want:raise ValueError('Source changed: '+name)
        if total>MAX_TOTAL:raise ValueError('Aggregate read budget')
    return dict(status='checked_source_candidate_only',source_pins=len(sources),candidate_files=len(local),bytes=total,
                dll_built=False,owner_hook_installed=False,game_access=False,runtime_verified=False,production_ready=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true',required=True);parser.parse_args()
    print(json.dumps(check(),sort_keys=True))
