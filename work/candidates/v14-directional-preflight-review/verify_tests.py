"""CreateNew evidence for bounded offline tests; preserve all attempts."""
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
    with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
def main():
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=HERE/'validation-results'/(stamp+'-'+uuid.uuid4().hex);out.mkdir(parents=True)
    report=dict(schema_version=1,purpose='v14_directional_offline_preflight_reviewer_validation',passed=False,
        synthetic_game_evidence_only=True,game_accessed=False,dll_built=False,execution_verified=False,steps=[])
    create(out/'claim.json',b'{"purpose":"offline_candidate_tests_only"}\n')
    try:
        review=json.loads((HERE/'review.json').read_bytes());report['review_sha256']=digest(HERE/'review.json')
        report['sources']=review['sources']+[dict(path='review.json',sha256=report['review_sha256']),dict(path='candidate.diff',sha256=review['diff_sha256'])]
        report['inputs']=review['input_pins']
        for name,args in [('prepare-check',[str(HERE/'prepare.py'),'--check']),('tests',[str(HERE/'test_reviewer.py')]),('post-check',[str(HERE/'prepare.py'),'--check'])]:
            value=subprocess.run([sys.executable,'-B',*args],cwd=ROOT,capture_output=True,timeout=60)
            if len(value.stdout)+len(value.stderr)>2*1024*1024:raise ValueError('Output budget exceeded')
            create(out/(name+'.stdout.txt'),value.stdout);create(out/(name+'.stderr.txt'),value.stderr)
            report['steps'].append(dict(name=name,exit_code=value.returncode,stdout_sha256=digest(out/(name+'.stdout.txt')),stderr_sha256=digest(out/(name+'.stderr.txt'))))
            if name=='tests':report['tests']=json.loads(value.stdout.decode())
            if value.returncode:raise ValueError('Step failed: '+name)
        report['source_before_after_equal']=all(digest(HERE/r['path'])==r['sha256'] for r in report['sources']) and all(digest(ROOT/p)==d for p,d in report['inputs'].items())
        if not report['source_before_after_equal']:raise ValueError('Source changed during offline review')
        report['passed']=True
    except Exception as error:report['error']=type(error).__name__+': '+str(error)
    p=out/'validation.json';create(p,(json.dumps(report,indent=2)+'\n').encode())
    print(json.dumps(dict(path=str(p),sha256=digest(p),passed=report['passed'],tests={k:v for k,v in report.get('tests',{}).items() if k!='details'},error=report.get('error'))))
    return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
