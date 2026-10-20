"""CreateNew offline validation record. No game/process observation."""
import hashlib,json,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def d(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return dict(bytes=p.stat().st_size,sha256=h.hexdigest())
def main():
 out=HERE/'validation-final';out.mkdir(exist_ok=False)
 report=json.loads((HERE/'report.json').read_text());index=json.loads((HERE/'source-index.json').read_text())
 names=set(report['sources'])|{(HERE/name).relative_to(ROOT).as_posix() for name in index}|{(HERE/'source-index.json').relative_to(ROOT).as_posix()}
 before={n:d(ROOT/n) for n in sorted(names)};results=[]
 commands=[('trace',[sys.executable,'-B',str(HERE/'trace.py'),'--check']),('prepare',[sys.executable,'-B',str(HERE/'prepare.py'),'--check']),('tests',[sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_observer.py','-v'])]
 for label,argv in commands:
  start=time.monotonic()
  with (out/(label+'.stdout')).open('xb') as a,(out/(label+'.stderr')).open('xb') as b:r=subprocess.run(argv,cwd=ROOT,stdout=a,stderr=b,timeout=60)
  results.append(dict(name=label,argv=argv,exit_code=r.returncode,elapsed_seconds=round(time.monotonic()-start,3),stdout=d(out/(label+'.stdout')),stderr=d(out/(label+'.stderr'))))
 after={n:d(ROOT/n) for n in sorted(names)}
 record=dict(status='passed' if before==after and all(r['exit_code']==0 for r in results) else 'failed',commands=results,inputs_before=before,inputs_after=after,inputs_unchanged=before==after,game_process_accessed=False,native_calls=False,all_shells_collected=True)
 with (out/'validation.json').open('x',encoding='utf-8') as f:json.dump(record,f,indent=2,sort_keys=True)
 print(json.dumps({'status':record['status'],'inputs':len(before),'validation':d(out/'validation.json')}));return int(record['status']!='passed')
if __name__=='__main__':raise SystemExit(main())
