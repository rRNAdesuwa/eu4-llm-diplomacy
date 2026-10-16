"""CreateNew pure-static/sparse-mock validation; no live API/reader invocation."""
import datetime,hashlib,json,subprocess,sys,time,uuid
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
FILES=('trace.py','report.json','observer.py','test_observer.py','README.md','input-pins.json','prepare.py','validate.py')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(262144),b''):h.update(b)
 return h.hexdigest()
def create(p,v):
 b=v if isinstance(v,bytes) else (json.dumps(v,indent=2,ensure_ascii=False)+'\n').encode()
 with p.open('xb') as f:f.write(b)
 return hashlib.sha256(b).hexdigest()
def inputs():
 with (HERE/'input-pins.json').open('rb') as f:raw=f.read(65537)
 assert len(raw)<=65536,'pin input bound'
 pins=json.loads(raw)
 for name,digest in pins.items():assert sha(ROOT/name)==digest,name
 names=list(pins)+[str((HERE/x).relative_to(ROOT)).replace('\\','/') for x in FILES]+['../eu4.exe']
 return {name:{'bytes':(ROOT/name).stat().st_size,'sha256':sha(ROOT/name)} for name in sorted(set(names))}
def main():
 directory=HERE/'validation-results'/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex);directory.mkdir(parents=True,exist_ok=False)
 before=inputs();create(directory/'source-before.json',before)
 rows=[]
 for index,args in enumerate([['trace.py','--check'],['-m','unittest','discover','-s',str(HERE),'-p','test_observer.py','-v']],1):
  command=[sys.executable,'-B']+([str(HERE/args[0])]+args[1:] if args[0].endswith('.py') else args)
  started=time.monotonic();r=subprocess.run(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
  h=create(directory/f'{index:02d}.stdout.txt',r.stdout)
  row={'argv':command,'exit_code':r.returncode,'stdout_sha256':h,'stdout':f'{index:02d}.stdout.txt','elapsed_seconds':round(time.monotonic()-started,3)};rows.append(row);print(json.dumps(row),flush=True)
 after=inputs();create(directory/'source-after.json',after)
 v={'input_count':len(before),'inputs_unchanged':before==after,'commands':rows,'all_exit_zero':all(x['exit_code']==0 for x in rows),'all_children_collected':True,'new_disassembly_limit':32768,'process_accessed':False,'native_call_authorized':False,'runtime_verified':False,'production_ready':False}
 h=create(directory/'validation.json',v);print(json.dumps({'validation':str((directory/'validation.json').relative_to(ROOT)),'sha256':h,'passed':v['all_exit_zero'] and v['inputs_unchanged']}),flush=True)
 return 0 if v['all_exit_zero'] and v['inputs_unchanged'] else 1
if __name__=='__main__':raise SystemExit(main())
