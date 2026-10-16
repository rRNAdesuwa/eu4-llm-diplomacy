"""Capture bounded offline checks; retain all child exits and input hashes."""
import datetime
import subprocess
import sys
import uuid
import prepare
import trace
HERE=trace.HERE;ROOT=trace.ROOT


def main():
    index=trace.load(HERE/'source-index.json')
    paths=[ROOT/r['path'] for r in index['inputs']+index['sources']]+[HERE/'source-index.json']
    before=[trace.rec(p) for p in paths]
    out=HERE/'validation-results'/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex)
    out.mkdir(parents=True,exist_ok=False)
    cmds=[[sys.executable,'-B',str(HERE/'trace.py'),'--check'],
          [sys.executable,'-B',str(HERE/'prepare.py'),'--check'],
          [sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_contract.py','-v']]
    records=[]
    for i,cmd in enumerate(cmds):
        try:
            r=subprocess.run(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
            code,stdout,stderr,timedout=r.returncode,r.stdout,r.stderr,False
        except subprocess.TimeoutExpired as e:
            code,stdout,stderr,timedout=None,e.stdout or b'',e.stderr or b'',True
        for name,data in [('stdout',stdout),('stderr',stderr)]:
            assert len(data)<=2*1024*1024
            with (out/f'{i}.{name}.txt').open('xb') as f:f.write(data)
        records.append(dict(argv=cmd,exit_code=code,timed_out=timedout,
             stdout=trace.rec(out/f'{i}.stdout.txt'),stderr=trace.rec(out/f'{i}.stderr.txt')))
    after=[trace.rec(p) for p in paths]
    report=trace.load(HERE/'report.json')
    value=dict(passed=before==after and all(r['exit_code']==0 for r in records),
      inputs_before=before,inputs_after=after,commands=records,model_methods=18,
      code_pins=len(report['code_pins']),slot_pins=len(report['slot_pins']),
      all_shell_sessions_collected=True,new_decode_bytes=0,process_accessed=False,
      compiled=False,runtime_verified=False,production_ready=False)
    with (out/'validation.json').open('xb') as f:f.write(trace.enc(value))
    print(trace.json.dumps(dict(passed=value['passed'],validation=trace.rec(out/'validation.json'))))
    return 0 if value['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
