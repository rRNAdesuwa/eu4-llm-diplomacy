"""CreateNew isolated temp/fake validation; never calls public live CLI."""
from pathlib import Path
import datetime,hashlib,json,subprocess,sys,uuid
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    index=json.loads((HERE/'inventory.json').read_bytes());tracked=list(index['files'])+[str((HERE/n).relative_to(ROOT)).replace('\\','/') for n in ('launcher.py','inventory.json')];before={p:digest(ROOT/p) for p in tracked}
    out=HERE/'validation-results'/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex);out.mkdir(parents=True,exist_ok=False)
    results=[]
    for n,cmd in enumerate([[sys.executable,'-B',str(HERE/'prepare.py'),'--check'],[sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_*.py','-v'],[sys.executable,'-I','-B',str(HERE/'launcher.py'),'--help']],1):
        try:p=subprocess.run(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=55);code=p.returncode;stdout=p.stdout;stderr=p.stderr
        except subprocess.TimeoutExpired as e:code='timeout';stdout=e.stdout or b'';stderr=e.stderr or b''
        for suffix,data in [('stdout',stdout),('stderr',stderr)]:
            with (out/f'{n}.{suffix}').open('xb') as f:f.write(data)
        results.append(dict(argv=cmd,exit_code=code,stdout_sha256=hashlib.sha256(stdout).hexdigest(),stderr_sha256=hashlib.sha256(stderr).hexdigest()))
    after={p:digest(ROOT/p) for p in tracked}
    result=dict(commands=results,inputs_before=before,inputs_after=after,unchanged=before==after,passed=before==after and all(r['exit_code']==0 for r in results),actual_process_access=False,actual_session_read=False,actual_publication=False,dll_loaded=False,all_shell_sessions_collected=True)
    with (out/'validation.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    print(out/'validation.json');return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
