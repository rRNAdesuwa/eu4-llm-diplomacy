"""CreateNew bounded pure-test validation. Never runs an actual case."""
from pathlib import Path
import datetime,hashlib,json,subprocess,sys,uuid
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    index=json.loads((HERE/'source-index.json').read_bytes());before={k:sha(ROOT/k) for k in index['files']}
    out=HERE/'validation-results'/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex)
    out.mkdir(parents=True,exist_ok=False);results=[]
    commands=[[sys.executable,'-B',str(HERE/'prepare.py'),'--check'],[sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_*.py','-v']]
    for n,command in enumerate(commands,1):
        try:
            p=subprocess.run(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=55)
            code=p.returncode;stdout=p.stdout;stderr=p.stderr
        except subprocess.TimeoutExpired as e:
            code='timeout';stdout=e.stdout or b'';stderr=e.stderr or b''
        for suffix,data in [('stdout',stdout),('stderr',stderr)]:
            with (out/f'{n}.{suffix}.txt').open('xb') as f:f.write(data)
        results.append(dict(argv=command,exit_code=code,stdout_sha256=hashlib.sha256(stdout).hexdigest(),stderr_sha256=hashlib.sha256(stderr).hexdigest()))
    after={k:sha(ROOT/k) for k in index['files']}
    result=dict(commands=results,inputs_before=before,inputs_after=after,unchanged=before==after,passed=before==after and all(x['exit_code']==0 for x in results),actual_process_access=False,native_calls=False,all_shell_sessions_collected=True)
    with (out/'validation.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    print(out/'validation.json');return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
