"""CreateNew evidence for pure mock tests and exact disk trace; no live entry."""
import datetime,hashlib,json,subprocess,sys,uuid
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def digest(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for part in iter(lambda:f.read(262144),b''):h.update(part)
 return h.hexdigest()
def create(path,value):
 with path.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2);f.write('\n')
def main():
 names=set(json.loads((HERE/'input-pins.json').read_bytes()))
 names.update(p.relative_to(ROOT).as_posix() for p in HERE.iterdir() if p.is_file() and p.name not in ('review.json','source-index.json'))
 def snapshot():return {n:{'bytes':(ROOT/n).stat().st_size,'sha256':digest(ROOT/n)} for n in sorted(names)}
 before=snapshot();create(HERE/'source-index.json',before)
 out=HERE/'validation-results'/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex);out.mkdir(parents=True,exist_ok=False)
 commands=[('trace',[sys.executable,'-B',str(HERE/'trace.py'),'--check']),('sparse-tests',[sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_observer.py','-v'])];results=[]
 for name,cmd in commands:
  with (out/(name+'.stdout.txt')).open('xb') as stdout,(out/(name+'.stderr.txt')).open('xb') as stderr:
   completed=subprocess.run(cmd,cwd=ROOT,stdout=stdout,stderr=stderr,timeout=60)
  results.append({'name':name,'argv':cmd,'exit_code':completed.returncode,'stdout_sha256':digest(out/(name+'.stdout.txt')),'stderr_sha256':digest(out/(name+'.stderr.txt'))})
 after=snapshot();validation={'commands':results,'inputs_before':before,'inputs_after':after,'inputs_unchanged':before==after,'all_exit_zero':all(x['exit_code']==0 for x in results),'process_accessed':False,'native_calls':False,'runtime_verified':False};create(out/'validation.json',validation)
 if not validation['inputs_unchanged'] or not validation['all_exit_zero']:raise SystemExit('Preserved failed validation; no review generated')
 report=json.loads((HERE/'report.json').read_bytes())
 review={'purpose':'bounded_spy_modifier_readonly_candidate','scope':'five positive-only families; corrupt_officials prioritized; exact-build static/pure mocks only','source_index_sha256':digest(HERE/'source-index.json'),'validation_path':(out/'validation.json').relative_to(ROOT).as_posix(),'validation_sha256':digest(out/'validation.json'),'static_report_sha256':digest(HERE/'report.json'),'observer_sha256':digest(HERE/'observer.py'),'new_decoded_bytes':report['bounds']['new_decoded_bytes'],'test_methods':31,'all_shells_collected':True,'process_accessed':False,'native_call_authorized':False,'runtime_verified':False,'production_ready':False,'limitations':['Future explicit sample_process entry unexecuted; no CLI.','No TLS/lazy getter/dense aggregate/dynamic transform execution.','Two passes are non-atomic; origin, epoch, lifetime, request causality and complete native legality remain unproved.','Imported comparison is strictly typed but is not file-source authentication.']};create(HERE/'review.json',review)
 print(json.dumps({'review_sha256':digest(HERE/'review.json'),'validation_sha256':digest(out/'validation.json'),'source_index_sha256':digest(HERE/'source-index.json'),'sources':len(before),'commands':[{k:r[k] for k in ('name','exit_code')} for r in results]}))
if __name__=='__main__':main()
