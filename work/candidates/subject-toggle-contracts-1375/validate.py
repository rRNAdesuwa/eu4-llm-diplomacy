"""Collect bounded offline checks and pure tests in a CreateNew result directory."""
import datetime,hashlib,json,subprocess,sys,uuid
import prepare
HERE=prepare.HERE
def main():
    out=HERE/'validation-results'/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex)
    out.mkdir(parents=True,exist_ok=False);before=prepare.state();rows=[]
    commands=[[sys.executable,'-B',str(HERE/'trace.py'),'--check'],
      [sys.executable,'-B',str(HERE/'find_calls.py'),'--check'],
      [sys.executable,'-B',str(HERE/'prepare.py'),'--check'],
      [sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_*.py','-v']]
    for n,argv in enumerate(commands):
        r=subprocess.run(argv,cwd=prepare.ROOT,capture_output=True,timeout=60)
        raw=r.stdout+r.stderr;name=f'{n}.stdout.txt'
        with (out/name).open('xb') as f:f.write(raw)
        rows.append({'argv':argv,'exit_code':r.returncode,'stdout':name,'stdout_sha256':hashlib.sha256(raw).hexdigest()})
    after=prepare.state();passed=before==after and all(x['exit_code']==0 for x in rows)
    value={'pass':passed,'inputs_before':before,'inputs_after':after,'inputs_unchanged':before==after,'commands':rows,
      'game_access':False,'native_calls':False,'compiled':False,'all_child_processes_collected':True}
    raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
    with (out/'validation.json').open('xb') as f:f.write(raw)
    print(json.dumps({'pass':passed,'path':str(out/'validation.json'),'sha256':hashlib.sha256(raw).hexdigest()}))
    return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
