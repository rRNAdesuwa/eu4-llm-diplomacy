"""Offline exact-byte replay and synthetic models, all child output collected."""
import datetime,json,subprocess,sys,uuid
from pathlib import Path
import prepare
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def main():
 names=list(prepare.load(HERE/'input-pins.json'))+[str((HERE/n).relative_to(ROOT)).replace('\\','/') for n in prepare.SOURCES]+[str((HERE/'source-index.json').relative_to(ROOT)).replace('\\','/')]
 before={n:prepare.digest(ROOT/n) for n in names}
 out=HERE/'validation-results'/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex);out.mkdir(parents=True)
 commands=[[sys.executable,'-B',str(HERE/'trace.py'),'--check'],[sys.executable,'-B',str(HERE/'prepare.py'),'--check'],[sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_*.py','-v']]
 rows=[]
 for i,command in enumerate(commands):
  result=subprocess.run(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
  path=out/(str(i)+'.stdout.txt')
  with path.open('xb') as f:f.write(result.stdout)
  rows.append({'argv':command,'exit_code':result.returncode,'stdout':str(path.relative_to(ROOT)).replace('\\','/'),'stdout_sha256':prepare.digest(path)})
 after={n:prepare.digest(ROOT/n) for n in names}
 record={'schema':1,'input_sha256_before':before,'input_sha256_after':after,'source_unchanged':before==after,'commands':rows,
  'all_shells_collected':True,'game_accessed':False,'native_called':False,'compiled':False}
 with (out/'validation.json').open('x',encoding='utf8') as f:json.dump(record,f,indent=2);f.write('\n')
 print(json.dumps({'validation':str((out/'validation.json').relative_to(ROOT)).replace('\\','/'),'sha256':prepare.digest(out/'validation.json'),'exits':[r['exit_code'] for r in rows],'source_unchanged':before==after}))
 if before!=after or any(r['exit_code'] for r in rows):raise SystemExit(1)
if __name__=='__main__':main()
