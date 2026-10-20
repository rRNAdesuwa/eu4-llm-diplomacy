"""Finite offline validation; each artifact CreateNew, every child collected."""
import datetime,hashlib,json,subprocess,sys,uuid
from pathlib import Path
import prepare
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def write(p,value):
    raw=value if type(value) is bytes else (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
    with p.open('xb') as f:f.write(raw)
def main():
    name=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex
    out=HERE/'validation-results'/name;out.mkdir(parents=True,exist_ok=False)
    before=prepare.state();write(out/'source-before.json',before);commands=[]
    for label,args in [('trace',[sys.executable,'-B',str(HERE/'trace.py'),'--check']),
      ('prepare',[sys.executable,'-B',str(HERE/'prepare.py'),'--check']),
      ('tests',[sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_*.py','-v'])]:
        done=subprocess.run(args,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
        p=out/(label+'.stdout.txt');write(p,done.stdout)
        commands.append({'name':label,'argv':args,'exit_code':done.returncode,'stdout':str(p.relative_to(ROOT)),**prepare.digest(p)})
    after=prepare.state();write(out/'source-after.json',after)
    result={'schema_version':1,'commands':commands,'source_before':before,'source_after':after,
      'inputs_unchanged':before==after,'all_children_collected':True,
      'pass':before==after and all(c['exit_code']==0 for c in commands),
      'game_accessed':False,'native_calls':False,'compiled':False,'old_sources_modified':False}
    write(out/'validation.json',result)
    print(json.dumps({'path':str((out/'validation.json').relative_to(ROOT)),'pass':result['pass'],**prepare.digest(out/'validation.json')}))
    return 0 if result['pass'] else 1
if __name__=='__main__':raise SystemExit(main())
