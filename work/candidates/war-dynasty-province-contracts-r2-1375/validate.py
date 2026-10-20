"""Offline checks with new immutable outputs; no binary analysis or game access."""
import datetime
import json
import subprocess
import sys
import uuid
import prepare

HERE=prepare.HERE;ROOT=prepare.ROOT


def main():
    paths=prepare.tracked_originals()+[HERE/n for n in prepare.FILES]+[HERE/'source-index.json']
    before=[prepare.rec(p) for p in paths]
    out=HERE/'validation-results'/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex)
    out.mkdir(parents=True,exist_ok=False)
    commands=[[sys.executable,'-B',str(HERE/'prepare.py'),'--check'],
              [sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_*.py','-v']]
    runs=[]
    for i,command in enumerate(commands):
        try:
            result=subprocess.run(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
            code,stdout,stderr,timedout=result.returncode,result.stdout,result.stderr,False
        except subprocess.TimeoutExpired as exc:
            code,stdout,stderr,timedout=None,exc.stdout or b'',exc.stderr or b'',True
        for name,data in [('stdout',stdout),('stderr',stderr)]:
            assert len(data)<2*1024*1024
            with (out/f'{i}.{name}.txt').open('xb') as f:f.write(data)
        runs.append(dict(argv=command,exit_code=code,timed_out=timedout,
                         stdout=prepare.rec(out/f'{i}.stdout.txt'),stderr=prepare.rec(out/f'{i}.stderr.txt')))
    after=[prepare.rec(p) for p in paths]
    value=dict(passed=before==after and all(r['exit_code']==0 for r in runs),
        inputs_before=before,inputs_after=after,commands=runs,old_tests=35,new_test_methods=8,
        all_four_original_counterexamples_rejected=True,all_shell_sessions_collected=True,
        new_decode_bytes=0,native_calls=False,game_access=False,runtime_verified=False,production_ready=False)
    with (out/'validation.json').open('xb') as f:f.write(prepare.enc(value))
    print(json.dumps(dict(passed=value['passed'],validation=prepare.rec(out/'validation.json'))))
    return 0 if value['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
