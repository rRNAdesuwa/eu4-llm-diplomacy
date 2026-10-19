"""One new fake suite, one file-only check and catalog. Never status."""
from pathlib import Path
import hashlib
import json
import sys
import time
import types
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def pin(p):
 b=p.read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(p,value):
 with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,ensure_ascii=True,indent=2);f.write('\n')
def main():
 assert sys.argv[1:]==[]
 out=HERE/'offline-r1';out.mkdir(exist_ok=False)
 names=('peace_current_pending.py','test_peace_current_pending.py','README.md','build_manifest.py','run_offline.py','source-manifest.json')
 initial={n:pin(HERE/n) for n in names};manifest=json.loads((HERE/'source-manifest.json').read_bytes())
 assert manifest['sealed'] is False and manifest['runtime_capture_authorized'] is False
 for name,expected in manifest['source_pins'].items():assert pin(ROOT/name)==expected
 save(out/'claim.json',dict(source_pins=initial,operations=['new_fake_suite','check','catalog'],automatic_retry=False,
  timeout_seconds_each=45,memory_limit=768*1024*1024,real_status_authorized=False))
 p=ROOT/'work/candidates/frida-entry-observer-1375-v1/job_tree.py';raw=p.read_bytes()
 assert hashlib.sha256(raw).hexdigest()=='5fca5b41161829a15554b08371e3fc64765164479e41bda015fec910972e9011'
 jobs=types.ModuleType('_peace_new_offline_job');jobs.__file__=str(p);exec(compile(raw,str(p),'exec'),jobs.__dict__)
 results=[];started=time.perf_counter();passed=True
 for op,argv in [('new_fake_suite',[sys.executable,'-I','-B',str(HERE/'test_peace_current_pending.py')]),
                 ('check',[sys.executable,'-I','-B',str(HERE/'peace_current_pending.py'),'check']),
                 ('catalog',[sys.executable,'-I','-B',str(HERE/'peace_current_pending.py'),'catalog'])]:
  job=jobs.run_cli_tree(argv,ROOT,out/(op+'-stdout.txt'),out/(op+'-stderr.txt'),timeout_seconds=45,memory_limit=768*1024*1024)
  post={n:pin(HERE/n) for n in names}
  good=job.get('exit_code')==0 and job.get('error') is None and job.get('direct_child_collected') is True and job.get('job_active_processes_final')==0 and post==initial
  item=dict(operation=op,passed=good,job=job,source_unchanged=post==initial,stdout=pin(out/(op+'-stdout.txt')),stderr=pin(out/(op+'-stderr.txt')),
   old_suites_run=0,real_status_run=False,game_access=0,native_game_calls=0)
  save(out/(op+'-receipt.json'),item);results.append(item)
  if not good:passed=False;break
 final=dict(schema='EU4-PEACE-PENDING-FIRST-OFFLINE/1',status='offline_passed' if passed else 'offline_failed_no_retry',
  source_pins=initial,source_post_pins={n:pin(HERE/n) for n in names},operations=results,
  duration_seconds=round(time.perf_counter()-started,6),automatic_retry=False,old_suites_run=0,
  actual_status_captures=0,PE_game_access=0,native_calls=0,requests_published=0)
 save(out/'receipt.json',final)
 print(json.dumps(dict(status=final['status'],receipt=pin(out/'receipt.json'),operations=[dict(operation=x['operation'],passed=x['passed'],exit_code=x['job'].get('exit_code'),active=x['job'].get('job_active_processes_final'),peak=x['job'].get('peak_job_commit')) for x in results]),ensure_ascii=True))
 return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
