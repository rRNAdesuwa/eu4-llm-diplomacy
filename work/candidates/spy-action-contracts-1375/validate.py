"""CreateNew offline validation. Explicit inputs; never enumerate runtime."""
import hashlib,json,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
FILES=('trace.py','contract.py','test_contract.py','README.md','input-pins.json','report.json','validate.py')

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def main():
    if (HERE/'validation.json').exists():raise ValueError('validation already exists')
    inputs=[HERE/n for n in FILES]
    inputs.extend(ROOT/p for p in json.loads((HERE/'input-pins.json').read_text(encoding='utf-8')))
    before={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in inputs}
    calls=[]
    commands=[('trace-check',[sys.executable,'-B',str(HERE/'trace.py'),'--check']),
              ('tests',[sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_contract.py','-v'])]
    for label,cmd in commands:
        r=subprocess.run(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
        p=HERE/(label+'.stdout.txt')
        with p.open('xb') as f:f.write(r.stdout)
        calls.append(dict(command=cmd,exit=r.returncode,stdout=str(p.relative_to(ROOT)).replace('\\','/'),stdout_sha256=sha(p)))
        print(label,'exit',r.returncode, r.stdout.decode('utf-8',errors='replace'))
    after={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in inputs}
    ok=before==after and all(x['exit']==0 for x in calls)
    result=dict(schema=1,scope='disk-only static replay and synthetic tests',passed=ok,
                source_before_sha256=before,source_after_sha256=after,source_unchanged=before==after,
                commands=calls,process_accessed=False,native_called=False,dll_built=False,
                runtime_verified=False,all_shell_sessions_collected=True)
    with (HERE/'validation.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    review=dict(schema=1,scope=result['scope'],passed=ok,
                candidate_files_sha256={n:sha(HERE/n) for n in FILES},
                validation_sha256=sha(HERE/'validation.json'),runtime_verified=False,
                production_ready=False,restrictions=['No native executor added','No game process accessed','No frozen files changed'])
    with (HERE/'review.json').open('x',encoding='utf-8') as f:json.dump(review,f,indent=2);f.write('\n')
    print(json.dumps({'passed':ok,'review_sha256':sha(HERE/'review.json'),
                      'validation_sha256':sha(HERE/'validation.json'),'report_sha256':sha(HERE/'report.json')}))
    return 0 if ok else 1

if __name__=='__main__':raise SystemExit(main())
