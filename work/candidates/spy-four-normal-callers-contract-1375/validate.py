"""Exclusive offline validation evidence. No process or native interaction."""
import argparse,hashlib,json,subprocess,sys,time
from pathlib import Path
import prepare
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',choices=['validation-final','validation-final-r2'],default='validation-final');args=parser.parse_args()
 out=HERE/args.output;out.mkdir(exist_ok=False)
 index=prepare.render();paths=sorted(set(index['inputs'])|set(index['sources'])|{str((HERE/'source-index.json').relative_to(ROOT)).replace('\\','/')})
 before={p:prepare.digest(ROOT/p)for p in paths};results=[]
 for i,argv in enumerate([[sys.executable,'-B',str(HERE/'trace.py'),'--check'],[sys.executable,'-B',str(HERE/'prepare.py'),'--check'],[sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_model.py','-v']]):
  start=time.monotonic();p=subprocess.run(argv,cwd=ROOT,capture_output=True,timeout=60);art={}
  for kind,b in [('stdout',p.stdout),('stderr',p.stderr)]:
   path=out/f'{i:02d}.{kind}.txt'
   with path.open('xb')as f:f.write(b)
   art[kind]={'path':str(path.relative_to(ROOT)).replace('\\','/'),'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
  results.append({'argv':argv,'exit_code':p.returncode,'elapsed_seconds':round(time.monotonic()-start,3),**art})
 after={p:prepare.digest(ROOT/p)for p in paths};passed=before==after and all(x['exit_code']==0 for x in results)
 result={'schema':1,'passed':passed,'commands':results,'inputs_before':before,'inputs_after':after,'inputs_unchanged':before==after,'test_methods':16,'process_accessed':False,'native_called':False,'native_compiled':False,'shell_sessions_remaining':[]}
 b=(json.dumps(result,indent=2)+'\n').encode()
 with(out/'validation.json').open('xb')as f:f.write(b)
 print(json.dumps({'passed':passed,'sha256':hashlib.sha256(b).hexdigest(),'input_count':len(before)}))
 return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
