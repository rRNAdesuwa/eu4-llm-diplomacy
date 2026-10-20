"""CREATE_NEW validation of cold imports and six offline regression tests."""
from pathlib import Path
import hashlib,json,subprocess,sys,time,uuid
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def descriptor(p):
 with p.open('rb') as f:b=f.read(8*1024*1024+1)
 assert len(b)<=8*1024*1024
 return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def save(p,obj):
 with p.open('x',encoding='utf-8') as f:json.dump(obj,f,sort_keys=True,indent=2);f.write('\n')
def main():
 run=HERE/'validation-results'/uuid.uuid4().hex;run.mkdir(parents=True,exist_ok=False)
 pins=json.loads((ROOT/'work/candidates/v17-preflight-case-builder-action-catalog/source-pins.json').read_bytes())['files']
 files={ROOT/n for n in pins}|{HERE/n for n in ('adapter.py','test_adapter.py','README.md','validate.py')}|{ROOT/'work/candidates/v17-preflight-case-builder-action-catalog/build_case.py',ROOT/'work/candidates/v17-preflight-case-builder-action-catalog/source-pins.json',ROOT/'work/runtime/native1375-v17/build.json'}
 before={p.relative_to(ROOT).as_posix():descriptor(p) for p in sorted(files)};save(run/'inputs-before.json',before);results=[]
 commands=[('cold-imports',[sys.executable,'-B',str(HERE/'adapter.py'),'check-imports','--output',str(run/'cold-imports.json')]),('tests',[sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_adapter.py','-v'])]
 for name,args in commands:
  start=time.monotonic();r=subprocess.run(args,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
  with (run/(name+'.txt')).open('xb') as f:f.write(r.stdout)
  results.append({'name':name,'argv':args,'exit_code':r.returncode,'elapsed_seconds':round(time.monotonic()-start,3),'output_sha256':hashlib.sha256(r.stdout).hexdigest()})
 after={p.relative_to(ROOT).as_posix():descriptor(p) for p in sorted(files)};save(run/'inputs-after.json',after)
 report={'results':results,'inputs_unchanged':before==after,'passed':before==after and all(r['exit_code']==0 for r in results),'actual_case_read':False,'game_accessed':False,'native_called':False}
 save(run/'validation.json',report);print(run/'validation.json');raise SystemExit(0 if report['passed'] else 1)
if __name__=='__main__':main()
