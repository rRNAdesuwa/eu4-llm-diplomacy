"""CreateNew evidence for finite static check and pure mocked tests only."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import sys
import uuid

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def pin(path):
    raw=path.read_bytes();return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}

def sources():
    return {p.name:pin(p) for p in sorted(HERE.iterdir()) if p.is_file() and p.name!='review.json'}

def main():
    before=sources();contract=json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    deps={p:pin(ROOT/p) for p in contract['dependencies']}
    directory=HERE/'validation-results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex)
    directory.mkdir(parents=True,exist_ok=False);runs=[]
    for name,args in [('static-check',[str(HERE/'trace.py'),'--check']),
                      ('sparse-tests',['-m','unittest','discover','-s',str(HERE),'-p','test_*.py','-v'])]:
        out=directory/(name+'.stdout.txt');err=directory/(name+'.stderr.txt')
        with out.open('xb') as stdout,err.open('xb') as stderr:
            done=subprocess.run([sys.executable,'-B',*args],cwd=ROOT,stdout=stdout,stderr=stderr,timeout=60,check=False)
        runs.append({'name':name,'argv':[sys.executable,'-B',*args],'exit_code':done.returncode,
                     'stdout':pin(out),'stderr':pin(err)})
    record={'schema_version':1,'purpose':'ordinary_insult_candidate_offline_validation','inputs':before,
       'dependencies':deps,'inputs_unchanged':before==sources(),
       'dependencies_unchanged':deps=={p:pin(ROOT/p) for p in deps},'runs':runs,
       'all_passed':all(r['exit_code']==0 for r in runs),'game_accessed':False,'native_called':False,
       'process_opened':False,'native_built':False,'materialized':False}
    output=directory/'validation.json'
    with output.open('x',encoding='utf-8',newline='\n') as f:json.dump(record,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps({'path':output.relative_to(ROOT).as_posix(),**pin(output),'passed':record['all_passed']}))
    return 0 if record['all_passed'] and record['inputs_unchanged'] and record['dependencies_unchanged'] else 1

if __name__=='__main__':raise SystemExit(main())
