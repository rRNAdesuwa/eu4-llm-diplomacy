"""Verify fixed candidate/source bytes only; never build, import native or publish."""
import argparse
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


def bounded(path,limit):
    with path.open('rb') as stream:raw=stream.read(limit+1)
    if len(raw)>limit:raise ValueError('Read budget')
    return raw


def check():
    pins=json.loads(bounded(HERE/'source-pins.json',128*1024))
    index=json.loads(bounded(HERE/'candidate-index.json',128*1024))
    if not 1<=len(pins)<=128 or not 1<=len(index)<=16:raise ValueError('Inventory budget')
    total=0
    for mapping in (pins,index):
        for name,expected in mapping.items():
            path=ROOT/name
            if path.resolve()!=path or not path.is_relative_to(ROOT):raise ValueError('Noncanonical source')
            raw=bounded(path,4*1024*1024);total+=len(raw)
            if total>16*1024*1024 or expected!=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()):
                raise ValueError('Changed source: '+name)
    return dict(source_pins=len(pins),candidate_sources=len(index),checked_bytes=total,
        native_host_implemented=False,native_calls=False,game_access=False,publication=False,production=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true',required=True);parser.parse_args()
    print(json.dumps(check()))
