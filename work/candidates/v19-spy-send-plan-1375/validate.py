"""Bounded offline subprocess validation; new output directory, never overwrites."""
import datetime,hashlib,json,subprocess,sys,uuid
from pathlib import Path
import prepare
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def main():
    paths=[ROOT/x for x in prepare.SOURCES]+[HERE/x for x in prepare.LOCAL]+[HERE/'source-pins.json',HERE/'candidate-index.json']
    before=[prepare.rec(p) for p in paths]
    out=HERE/'validation-results'/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex)
    out.mkdir(parents=True,exist_ok=False)
    args=[[sys.executable,'-B',str(HERE/'prepare.py'),'--check'],[sys.executable,'-B',str(HERE/'evidence.py'),'--check'],
      [sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_model.py','-v']]
    records=[]
    for i,cmd in enumerate(args):
        try:
            r=subprocess.run(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
            code=r.returncode;stdout=r.stdout;stderr=r.stderr;timeout=False
        except subprocess.TimeoutExpired as e:
            code=None;stdout=e.stdout or b'';stderr=e.stderr or b'';timeout=True
        for name,raw in [('stdout',stdout),('stderr',stderr)]:
            assert len(raw)<=2*1024*1024
            with (out/f'{i}.{name}.txt').open('xb') as f:f.write(raw)
        records.append(dict(argv=cmd,exit_code=code,timed_out=timeout,stdout=prepare.rec(out/f'{i}.stdout.txt'),stderr=prepare.rec(out/f'{i}.stderr.txt')))
    after=[prepare.rec(p) for p in paths]
    value=dict(schema=1,passed=before==after and all(r['exit_code']==0 for r in records),inputs_before=before,inputs_after=after,
      commands=records,synthetic_methods=20,new_decode_this_validation=0,game_access=False,compiled=False,production_ready=False)
    raw=prepare.enc(value)
    with (out/'validation.json').open('xb') as f:f.write(raw)
    print(json.dumps(dict(passed=value['passed'],path=(out/'validation.json').relative_to(ROOT).as_posix(),sha256=hashlib.sha256(raw).hexdigest())))
    return 0 if value['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
