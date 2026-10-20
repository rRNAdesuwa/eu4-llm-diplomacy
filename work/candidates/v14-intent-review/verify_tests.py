"""Collect offline candidate validation, preserving every failed or passing run."""
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
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def create(path,raw):
    with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
def main():
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    parent=HERE/'validation-results';parent.mkdir(exist_ok=True)
    out=parent/(stamp+'-'+uuid.uuid4().hex);out.mkdir()
    report={'schema_version':1,'purpose':'v14_actual_filesystem_publication_validation','passed':False,
        'game_accessed':False,'dll_built':False,'materialized':False,'runtime_verified':False,'execution_verified':False,'steps':[]}
    create(out/'claim.json',(json.dumps({'purpose':report['purpose'],'created_at_utc':stamp})+'\n').encode())
    try:
        review=json.loads((HERE/'review.json').read_bytes());report['review_sha256']=digest(HERE/'review.json')
        report['inputs']=review['candidate_sources']+review['outputs']+[{'path':'review.json','sha256':report['review_sha256']}]
        report['offline_fixture_inputs']=review['offline_fixture_inputs']
        for name,args in [('prepare-check',[str(HERE/'prepare.py'),'--check']),('tests',[str(HERE/'test_candidate.py')]),('post-check',[str(HERE/'prepare.py'),'--check'])]:
            value=subprocess.run([sys.executable,'-B',*args],cwd=ROOT,capture_output=True,timeout=60)
            if len(value.stdout)+len(value.stderr)>2*1024*1024:raise ValueError('Output budget exceeded')
            create(out/(name+'.stdout.txt'),value.stdout);create(out/(name+'.stderr.txt'),value.stderr)
            report['steps'].append({'name':name,'exit_code':value.returncode,'stdout_sha256':digest(out/(name+'.stdout.txt')),'stderr_sha256':digest(out/(name+'.stderr.txt'))})
            if name=='tests':report['tests']=json.loads(value.stdout.decode())
            if value.returncode:raise ValueError('Offline step failed: '+name)
        report['source_before_after_equal']=(all(digest(HERE/i['path'])==i['sha256'] for i in report['inputs'])
            and all(digest(ROOT/i['path'])==i['sha256'] for i in report['offline_fixture_inputs']))
        if not report['source_before_after_equal']:raise ValueError('Candidate changed during validation')
        report['passed']=True
    except Exception as error:report['error']=type(error).__name__+': '+str(error)
    path=out/'validation.json';create(path,(json.dumps(report,indent=2)+'\n').encode())
    print(json.dumps({'path':str(path),'sha256':digest(path),'passed':report['passed'],
        'tests':{k:v for k,v in report.get('tests',{}).items() if k!='details'},'error':report.get('error')}))
    return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
