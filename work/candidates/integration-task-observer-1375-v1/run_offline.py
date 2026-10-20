"""One new fake suite and one file-only check/catalog each, collected 45s Jobs."""
import hashlib
import json
from pathlib import Path
import sys
import time
import types
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def pin(path):
 raw=path.read_bytes();return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def save(path,value):
 with path.open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,indent=2);f.write('\n')
def main():
 assert sys.argv[1:]==[]
 out=HERE/'offline-r1';out.mkdir(exist_ok=False)
 names=('integration_task_observer.py','test_integration_task_observer.py','README.md','build_manifest.py','run_offline.py','source-manifest.json')
 initial={n:pin(HERE/n) for n in names}
 save(out/'claim.json',dict(source_pins=initial,operations=['new_fake_suite','check','catalog'],automatic_retry=False,
  timeout_seconds_each=45,memory_limit=768*1024*1024,real_capture_authorized=False))
 jobpath=ROOT/'work/candidates/frida-entry-observer-1375-v1/job_tree.py';raw=jobpath.read_bytes()
 assert hashlib.sha256(raw).hexdigest()=='5fca5b41161829a15554b08371e3fc64765164479e41bda015fec910972e9011'
 jobmodule=types.ModuleType('_integration_candidate_offline_job');jobmodule.__file__=str(jobpath)
 exec(compile(raw,str(jobpath),'exec'),jobmodule.__dict__)
 results=[];started=time.perf_counter();all_pass=True
 for name,argv in (
   ('new_fake_suite',[sys.executable,'-I','-B',str(HERE/'test_integration_task_observer.py')]),
   ('check',[sys.executable,'-I','-B',str(HERE/'integration_task_observer.py'),'check']),
   ('catalog',[sys.executable,'-I','-B',str(HERE/'integration_task_observer.py'),'catalog'])):
  job=jobmodule.run_cli_tree(argv,ROOT,out/(name+'-stdout.txt'),out/(name+'-stderr.txt'),timeout_seconds=45,memory_limit=768*1024*1024)
  okay=job.get('exit_code')==0 and job.get('error') is None and job.get('direct_child_collected') is True and job.get('job_active_processes_final')==0
  post={n:pin(HERE/n) for n in names};okay=okay and post==initial
  result=dict(operation=name,passed=okay,job=job,source_unchanged=post==initial,
   stdout=pin(out/(name+'-stdout.txt')),stderr=pin(out/(name+'-stderr.txt')),
   game_process_accesses=0,native_game_calls=0,old_suites_run=0,real_capture_run=False)
  save(out/(name+'-receipt.json'),result);results.append(result)
  if not okay:all_pass=False;break
 final=dict(status='offline_passed' if all_pass else 'offline_failed_no_automatic_retry',source_pins=initial,
  source_post_pins={n:pin(HERE/n) for n in names},operations=results,
  duration_seconds=round(time.perf_counter()-started,6),automatic_retry=False,old_suites_run=0,
  actual_status_captures=0,game_process_accesses=0,native_game_calls=0,requests_published=0)
 save(out/'receipt.json',final)
 print(json.dumps(dict(status=final['status'],receipt=pin(out/'receipt.json'),
  operations=[dict(operation=r['operation'],passed=r['passed'],exit_code=r['job'].get('exit_code'),
    active=r['job'].get('job_active_processes_final'),peak=r['job'].get('peak_job_memory')) for r in results])))
 return 0 if all_pass else 1
if __name__=='__main__':raise SystemExit(main())
