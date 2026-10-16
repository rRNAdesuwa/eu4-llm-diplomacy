"""Run isolated Python candidate offline tests; new evidence files only."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def create(p,raw):
    with p.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
def main():
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    parent=HERE/'validation-results';parent.mkdir(exist_ok=True)
    out=parent/(stamp+'-'+uuid.uuid4().hex);out.mkdir()
    report={'schema_version':1,'purpose':'v13_host_offline_validation','passed':False,'game_accessed':False,
        'dll_built':False,'materialized':False,'server_started':False,'runtime_verified':False,'execution_verified':False,'steps':[]}
    create(out/'claim.json',(json.dumps({'purpose':report['purpose'],'created_utc':stamp})+'\n').encode())
    try:
        review=json.loads((HERE/'review.json').read_bytes());report['review_sha256']=digest(HERE/'review.json')
        report['inputs']=review['candidate_sources']+review['outputs']+[{'path':'review.json','sha256':report['review_sha256']}]
        for name,args in [('prepare-check',[str(HERE/'prepare.py'),'--check']),('tests',[str(HERE/'test_candidate.py')]),
                          ('post-check',[str(HERE/'prepare.py'),'--check'])]:
            value=subprocess.run([sys.executable,'-B',*args],cwd=ROOT,capture_output=True,timeout=60)
            if len(value.stdout)+len(value.stderr)>2*1024*1024:raise ValueError('Output budget exceeded')
            stdout=out/(name+'.stdout.txt');stderr=out/(name+'.stderr.txt')
            create(stdout,value.stdout);create(stderr,value.stderr)
            report['steps'].append({'name':name,'exit':value.returncode,'stdout_sha256':digest(stdout),'stderr_sha256':digest(stderr)})
            if name=='tests':
                report['tests']=json.loads(value.stdout.decode('utf-8'))
            if value.returncode:raise ValueError('Offline step failed: '+name)
        if any(digest(HERE/i['path'])!=i['sha256'] for i in report['inputs']):raise ValueError('Candidate changed during tests')
        report['passed']=True
    except Exception as error:report['error']=type(error).__name__+': '+str(error)
    target=out/'validation.json';create(target,(json.dumps(report,indent=2)+'\n').encode())
    summary={k:v for k,v in report.get('tests',{}).items() if k!='details'}
    print(json.dumps({'path':str(target),'sha256':digest(target),'passed':report['passed'],'tests':summary,'error':report.get('error')}))
    return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
