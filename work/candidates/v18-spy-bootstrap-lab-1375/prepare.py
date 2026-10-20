"""Read-only sealed candidate source/lineage checker; never runs game/native."""
from pathlib import Path
import argparse
import json
import build_manifest as b

HERE=Path(__file__).resolve().parent


def check():
    index=b.json_value(b.bounded(HERE/'candidate-index.json',131072))
    b.require(set(index)=={'sources','predecessors','build'} and len(index['sources'])<=64,'Candidate index shape/budget')
    for name,descriptor in index['sources'].items():
        path=b.no_links(HERE/name).resolve();b.require(path.is_relative_to(HERE),'Candidate path escapes')
        raw=b.bounded(path,2*1024*1024)
        b.require(b.exact(descriptor,{'sha256':b.sha(raw),'bytes':len(raw)}),'Candidate source changed: '+name)
    pins=b.json_value(b.bounded(HERE/'predecessor-pins.json',131072))
    b.require(b.exact(pins,index['predecessors']),'Lineage inventory changed')
    for name,descriptor in pins.items():
        raw=b.bounded(b.no_links(b.ROOT/name),2*1024*1024)
        b.require(b.exact(descriptor,{'sha256':b.sha(raw),'bytes':len(raw)}),'Predecessor changed: '+name)
    original=b.bounded(b.ROOT/'work/native/v17/research-lab-bootstrap-1375.inc',65536)
    excerpt=original[original.index(b'// Freeze only this process'):original.index(b'static BOOL CALLBACK find_window_thread')]
    b.require(b.bounded(HERE/'thread_freeze.inc',16384)==excerpt,'Freeze implementation changed')
    b.require(b.bounded(HERE/'frame.asm',16384)==b.bounded(b.ROOT/'work/native/v17/research-frame-v6-1375.asm',16384),'Static unwind trampoline changed')
    directory=HERE/index['build']['directory'];manifest,sha=b.verify_build(directory)
    b.require(sha==index['build']['manifest_sha256'] and manifest['dll_sha256']==index['build']['dll_sha256'],'Candidate build changed')
    return {'checked':True,'source_count':len(index['sources']),'predecessor_count':len(pins),'dll_sha256':manifest['dll_sha256'],
            'runtime_verified':False,'production_ready':False,'game_accessed':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true',required=True);p.parse_args()
    print(json.dumps(check(),sort_keys=True))
