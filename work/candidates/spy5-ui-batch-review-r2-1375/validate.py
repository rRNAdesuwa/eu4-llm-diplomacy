"""CreateNew synthetic-only validation; never reads actual census or journal."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import prepare

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(exist_ok=False)
    indexed=prepare.render()
    paths=set(indexed['inputs'])|set(indexed['sources'])|{(HERE/'source-index.json').relative_to(ROOT).as_posix()}
    def snap():return {x:{'sha256':prepare.reviewer.sha(ROOT/x),'bytes':(ROOT/x).stat().st_size}for x in sorted(paths)}
    before=snap();runs=[]
    for index,argv in enumerate([
        [sys.executable,'-B',str(HERE/'prepare.py'),'--check'],
        [sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_*.py','-v']]):
        started=time.monotonic()
        value=subprocess.run(argv,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=55)
        row={'argv':argv,'exit_code':value.returncode,'elapsed_seconds':round(time.monotonic()-started,3)}
        for field,raw in [('stdout',value.stdout),('stderr',value.stderr)]:
            if len(raw)>2*1024*1024:raise ValueError('output bound')
            with (a.output/f'{index:02d}.{field}.txt').open('xb')as out:out.write(raw)
            row[field+'_sha256']=hashlib.sha256(raw).hexdigest()
        runs.append(row)
    after=snap();passed=before==after and all(x['exit_code']==0 for x in runs)
    result=dict(schema=1,status='passed'if passed else'failed',scope='synthetic_only_no_actual_inputs',
                inputs_before=before,inputs_after=after,inputs_unchanged=before==after,runs=runs,
                game_accessed=False,native_called=False,actual_review_executed=False,production_ready=False)
    with (a.output/'validation.json').open('x',encoding='utf-8',newline='\n')as out:
        json.dump(result,out,sort_keys=True,indent=2);out.write('\n')
    print(json.dumps({'status':result['status'],'sha256':prepare.reviewer.sha(a.output/'validation.json')}))
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
