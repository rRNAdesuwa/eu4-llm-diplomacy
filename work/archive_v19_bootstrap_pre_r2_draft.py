"""Preserve uncompiled bootstrap draft before changing its Host dependency."""
from pathlib import Path
import hashlib,json

ROOT=Path(__file__).resolve().parent.parent
HERE=ROOT/'work/candidates/v19-spy-bootstrap-lab-1375'
OUT=HERE/'development-pre-r2-host'
FILES=('README.md','bootstrap.cpp','bootstrap_codec.h','scheduler.h','installer.h','installer.cpp',
       'thread_freeze.inc','frame.asm','build.cmd','build_manifest.py','wire.py','loader.py',
       'test_bootstrap.cpp','test_claims.cpp','test_wire.py','v18-preimages.json','predecessor-pins.json','freeze_lineage.py','prepare.py')
def main():
    OUT.mkdir(exist_ok=False);pins={};total=0
    for name in FILES:
        raw=(HERE/name).read_bytes();total+=len(raw)
        if len(raw)>262144 or total>2097152:raise ValueError('Draft budget')
        with (OUT/name).open('xb') as f:f.write(raw)
        pins[name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    with (OUT/'source-index.json').open('x',encoding='ascii',newline='\n') as f:f.write(json.dumps({'sources':pins,'compiled':False,'game_accessed':False},sort_keys=True,indent=2)+'\n')
    print(json.dumps({'files':len(pins),'bytes':total,'compiled':False,'game_accessed':False}))
if __name__=='__main__':main()
