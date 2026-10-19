"""Read-only R2 source/lineage verification. No build/load/process access."""
from pathlib import Path
import argparse,json
from _frozen import HERE,ROOT,OLD,PINS,b,read,sha


def check():
    index=b.json_value(read(HERE/'candidate-index.json',65536))
    if set(index)!={'schema','sources','input_pins_sha256','original_dll_sha256','original_manifest_sha256'}or index['schema']!=1:raise ValueError('R2 index shape')
    if not b.exact(index['input_pins_sha256'],sha(read(HERE/'input-pins.json',131072))):raise ValueError('R2 input pin index')
    for name,descriptor in index['sources'].items():
        if Path(name).name!=name:raise ValueError('R2 source filename')
        raw=read(HERE/name,131072)
        if not b.exact(descriptor,{'bytes':len(raw),'sha256':sha(raw)}):raise ValueError('R2 source changed '+name)
    if not 1<=len(PINS)<=128:raise ValueError('R2 input count')
    total=0
    for name,descriptor in PINS.items():
        path=(ROOT/name).resolve()
        if not path.is_relative_to(ROOT):raise ValueError('R2 escaped source')
        raw=read(path,2097152);total+=len(raw)
        if total>16777216 or not b.exact(descriptor,{'bytes':len(raw),'sha256':sha(raw)}):raise ValueError('R2 frozen input changed '+name)
    manifest,manifest_sha=b.verify_build(OLD/'build-final')
    if manifest_sha!=index['original_manifest_sha256']or manifest['dll_sha256']!=index['original_dll_sha256']:raise ValueError('Original native metadata changed')
    old=read(OLD/'real_capture.py',32768).decode('ascii')
    expected=old.replace('import build_manifest as b\nimport wire\nimport native_trace as trace','from _frozen import b, wire, trace')
    before="                require(d['prefix_unchanged'] is False and d['retrying'] is False and d['failure_stage']==0,'Installed patch result');installed=True"
    after="                require(d['prefix_unchanged'] is False and d['retrying'] is False and d['failure_stage']==0,'Installed patch result')\n                require(d['collected']>=1 and all(d[k]==0 for k in ('error','failure_thread','rip')),'Successful installation cannot contain a failure diagnostic or empty thread set')\n                installed=True"
    if expected.count(before)!=1:raise ValueError('R2 exact patch preimage')
    expected=expected.replace(before,after)
    if read(HERE/'real_capture.py',32768).decode('ascii').replace('\r\n','\n')!=expected:raise ValueError('R2 unexpected semantic delta')
    return {'checked':True,'sources':len(index['sources']),'unchanged_inputs':len(PINS),'input_bytes':total,
            'original_manifest_preserved':True,'new_native_build':False,'runtime_verified':False,'production_ready':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',required=True,action='store_true');parser.parse_args()
    print(json.dumps(check(),sort_keys=True))
