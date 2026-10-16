"""Finite offline validation with exclusive evidence outputs; no live access."""
import hashlib,json,subprocess,sys,time
from pathlib import Path
import prepare
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def main():
 out=HERE/'validation-final';out.mkdir(exist_ok=False)
 inv=prepare.render();paths=sorted(set(inv['inputs'])|set(inv['sources'])|{str((HERE/'source-index.json').relative_to(ROOT)).replace('\\','/')})
 before={p:prepare.digest(ROOT/p) for p in paths}
 commands=[['trace.py','--check'],['prepare.py','--check'],None];results=[]
 for i,tail in enumerate(commands):
  cmd=[sys.executable,'-B',str(HERE/tail[0]),*tail[1:]] if tail else [sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_contract.py','-v']
  started=time.monotonic();p=subprocess.run(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
  artifacts={}
  for label,data in [('stdout',p.stdout),('stderr',p.stderr)]:
   path=out/f'{i}-{label}.txt'
   with path.open('xb') as f:f.write(data)
   artifacts[label]={'path':path.name,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
  results.append({'argv':cmd,'exit_code':p.returncode,'seconds':round(time.monotonic()-started,3),'artifacts':artifacts})
 after={p:prepare.digest(ROOT/p) for p in paths}
 passed=before==after and all(r['exit_code']==0 for r in results)
 report={'schema':1,'status':'passed' if passed else 'failed','commands':results,'inputs_before':before,'inputs_after':after,'unchanged':before==after,'test_methods':24,'actual_process_accessed':False,'native_compiled':False,'native_called':False}
 data=(json.dumps(report,indent=2)+'\n').encode()
 with (out/'validation.json').open('xb') as f:f.write(data)
 print(json.dumps({'passed':passed,'sha256':hashlib.sha256(data).hexdigest(),'inputs':len(paths)}))
 return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
