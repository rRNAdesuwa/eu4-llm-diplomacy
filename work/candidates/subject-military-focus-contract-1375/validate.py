"""Run offline check and pure tests, preserve new output once, no engine access."""
import datetime, hashlib, json, subprocess, sys, uuid
from pathlib import Path
import prepare

HERE=Path(__file__).resolve().parent
def main():
    root=HERE/'validation-results'/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex)
    root.mkdir(parents=True,exist_ok=False)
    before=prepare.state();rows=[]
    commands=[[sys.executable,'-B',str(HERE/'trace.py'),'--check'],
      [sys.executable,'-B',str(HERE/'prepare.py'),'--check'],
      [sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_*.py','-v']]
    for n,argv in enumerate(commands):
        r=subprocess.run(argv,cwd=prepare.ROOT,capture_output=True,timeout=60)
        output=r.stdout+r.stderr;name=f'{n}.stdout.txt'
        with (root/name).open('xb') as f:f.write(output)
        rows.append({'argv':argv,'exit_code':r.returncode,'stdout_file':name,'stdout_sha256':hashlib.sha256(output).hexdigest()})
    after=prepare.state();passed=before==after and all(r['exit_code']==0 for r in rows)
    value={'pass':passed,'inputs_before':before,'inputs_after':after,'unchanged':before==after,'commands':rows,
      'process_access':False,'compiled':False,'native_calls':False,'all_child_processes_collected':True}
    raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
    with (root/'validation.json').open('xb') as f:f.write(raw)
    print(json.dumps({'pass':passed,'path':str(root/'validation.json'),'sha256':hashlib.sha256(raw).hexdigest()}))
    return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
