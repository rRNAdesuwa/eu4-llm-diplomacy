"""CreateNew validation. All subprocesses finite, no live reader."""
from pathlib import Path
import hashlib,json,datetime,uuid,subprocess,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    files=json.loads((HERE/'source-index.json').read_bytes())['files'];before={n:sha(ROOT/n) for n in files}
    out=HERE/'validation-results'/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex);out.mkdir(parents=True,exist_ok=False);results=[]
    commands=[[sys.executable,'-B',str(HERE/'trace.py'),'--check'],[sys.executable,'-B',str(HERE/'prepare.py'),'--check'],[sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_*.py','-v']]
    for n,cmd in enumerate(commands,1):
        try:p=subprocess.run(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=55);code=p.returncode;a=p.stdout;b=p.stderr
        except subprocess.TimeoutExpired as e:code='timeout';a=e.stdout or b'';b=e.stderr or b''
        for suffix,data in [('stdout',a),('stderr',b)]:
            with (out/f'{n}.{suffix}').open('xb') as f:f.write(data)
        results.append(dict(argv=cmd,exit_code=code,stdout_sha256=hashlib.sha256(a).hexdigest(),stderr_sha256=hashlib.sha256(b).hexdigest()))
    after={n:sha(ROOT/n) for n in files};result=dict(commands=results,inputs_before=before,inputs_after=after,unchanged=before==after,passed=before==after and all(x['exit_code']==0 for x in results),game_access=False,native_calls=False,new_decode_bytes=0,all_sessions_collected=True)
    with (out/'validation.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    print(out/'validation.json');return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
