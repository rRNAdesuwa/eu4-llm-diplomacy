"""Verify sealed source/build provenance; file-only, no game/native invocation."""
from pathlib import Path
import argparse,json
import build_manifest as b

HERE=Path(__file__).resolve().parent
def check():
    index=b.json_value(b.bounded(HERE/'candidate-index.json',131072))
    b.require(set(index)=={'sources','predecessors','build'} and len(index['sources'])<=64,'Index shape')
    for name,pin in index['sources'].items():
        path=b.no_links(HERE/name).resolve();b.require(path.is_relative_to(HERE),'Local source origin')
        raw=b.bounded(path,2*1024*1024);b.require(b.exact(pin,{'bytes':len(raw),'sha256':b.sha(raw)}),'Local source changed '+name)
    pins=b.json_value(b.bounded(HERE/'predecessor-pins-r2.json',131072))
    b.require(b.exact(pins,index['predecessors']),'Lineage inventory changed')
    total=0
    for name,pin in pins.items():
        path=b.no_links(b.ROOT/name).resolve();b.require(path.is_relative_to(b.ROOT) and not name.startswith('bridge/'),'Dependency origin')
        raw=b.bounded(path,2*1024*1024);total+=len(raw);b.require(total<=16*1024*1024,'Lineage read budget')
        b.require(b.exact(pin,{'bytes':len(raw),'sha256':b.sha(raw)}),'Predecessor changed '+name)
    original=b.bounded(b.ROOT/'work/native/v17/research-lab-bootstrap-1375.inc',65536)
    excerpt=original[original.index(b'// Freeze only this process'):original.index(b'static BOOL CALLBACK find_window_thread')]
    b.require(b.bounded(HERE/'thread_freeze.inc',16384)==excerpt,'Thread freeze preimage changed')
    b.require(b.bounded(HERE/'frame.asm',16384)==b.bounded(b.ROOT/'work/native/v17/research-frame-v6-1375.asm',16384),'Unwind trampoline preimage changed')
    manifest,sha=b.verify_build(HERE/index['build']['directory'])
    b.require(sha==index['build']['manifest_sha256'] and manifest['dll_sha256']==index['build']['dll_sha256'],'Exact build changed')
    return {'checked':True,'sources':len(index['sources']),'predecessors':len(pins),'dll_sha256':manifest['dll_sha256'],
            'game_accessed':False,'runtime_verified':False,'effect_verified':False,'production_ready':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',required=True,action='store_true');p.parse_args();print(json.dumps(check(),sort_keys=True))
