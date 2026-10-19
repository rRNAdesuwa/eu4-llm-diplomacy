"""Offline candidate and frozen dependency check. No worker invocation."""
import argparse
import hashlib
import json
from pathlib import Path
import adapter


def check():
    adapter.verify_inputs()
    index=adapter.read_json(Path(__file__).parent/'candidate-index.json',65536)
    for name,expected in index.items():
        path=adapter.ROOT/name
        with path.open('rb') as stream:raw=stream.read(adapter.MAX_JSON+1)
        if len(raw)>adapter.MAX_JSON or expected!=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()):
            raise ValueError('Candidate changed: '+name)
    return dict(candidate_files=len(index),game_access=False,publication=False,production=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true',required=True);parser.parse_args()
    print(json.dumps(check()))
