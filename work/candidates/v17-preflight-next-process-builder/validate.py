"""CREATE_NEW offline validation records, bounded check and synthetic tests only."""
from pathlib import Path
import datetime,hashlib,json,subprocess,sys,time,uuid
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def wire(v):return (json.dumps(v,sort_keys=True,indent=2)+'\n').encode()
def digest(p):
 with p.open('rb') as f:b=f.read(8*1024*1024+1)
 if len(b)>8*1024*1024:raise ValueError('Input bound')
 return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def save(p,b):
 with p.open('xb') as f:f.write(b)
def main():
 index=json.loads((HERE/'candidate-index.json').read_bytes());pins=json.loads((HERE/'source-pins.json').read_bytes())['files']
 inputs={str(HERE/n):digest(HERE/n) for n in [*index['sources'],'candidate-index.json']}
 inputs.update({str(ROOT/n):digest(ROOT/n) for n in pins})
 run=HERE/'validation-results'/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ-')+uuid.uuid4().hex)
 run.mkdir(parents=True,exist_ok=False);save(run/'inputs-before.json',wire(inputs));results=[]
 cmds=[('check',[sys.executable,'-B',str(HERE/'prepare.py'),'--check']),('tests',[sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_*.py','-v'])]
 for name,args in cmds:
  start=time.monotonic();code=None;timed=False
  try:
   result=subprocess.run(args,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240);out=result.stdout;code=result.returncode
  except subprocess.TimeoutExpired as exc:out=exc.stdout or b'';timed=True
  if len(out)>1024*1024:raise ValueError('Unexpected large validation output')
  save(run/(name+'.txt'),out);results.append({'name':name,'argv':args,'exit_code':code,'timeout':timed,'elapsed_seconds':round(time.monotonic()-start,3),'output':name+'.txt','output_sha256':hashlib.sha256(out).hexdigest()})
 after={n:digest(Path(n)) for n in inputs};save(run/'inputs-after.json',wire(after))
 report={'schema_version':1,'scope':'offline synthetic builder checks only','results':results,'inputs_unchanged':inputs==after,'actual_case_read':False,'process_accessed':False,'native_called':False,'passed':inputs==after and all(x['exit_code']==0 and not x['timeout'] for x in results)}
 save(run/'validation.json',wire(report));print(str(run/'validation.json'));raise SystemExit(0 if report['passed'] else 1)
if __name__=='__main__':main()
