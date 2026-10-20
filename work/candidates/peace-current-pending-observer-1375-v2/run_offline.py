"""Exactly six new fake methods and first v2 check/catalog, under frozen Jobs."""
from pathlib import Path
import hashlib, json, sys, time, types
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
READS=0
def read(path):
 global READS
 size=path.stat().st_size;assert 0<=size<=4194304
 b=path.read_bytes();assert len(b)==size;READS+=len(b);return b
def pin(path):
 b=read(path);return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(path,value):
 with path.open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,ensure_ascii=True,sort_keys=True,indent=2);f.write('\n')
def main():
 assert sys.argv[1:]==[]
 budget=json.loads(read(HERE/'budget.json'));auth=budget['delegated_budget_authorization'];assert pin(ROOT/auth['path'])=={k:auth[k] for k in ('bytes','sha256')}
 out=HERE/'offline-r1';out.mkdir(exist_ok=False)
 manifest=json.loads(read(HERE/'source-manifest.json'));assert manifest['sealed'] is False and manifest['runtime_capture_authorized'] is False
 initial={n:pin(ROOT/n) for n in manifest['source_pins']};assert initial==manifest['source_pins']
 manifest_pin=pin(HERE/'source-manifest.json')
 save(out/'claim.json',dict(schema='EU4-PEACE-V2-NEW-OFFLINE-CLAIM/1',source_manifest=manifest_pin,source_graph_sha256=manifest['source_graph_sha256'],
  operations=['six_new_fake_methods','check','catalog'],automatic_retry=False,budget=budget,timeout_seconds_each=45,
  memory_limit=768*1024*1024,per_stream_acceptance_limit=2*1024*1024,real_status_authorized=False))
 jobpath=ROOT/'work/candidates/frida-entry-observer-1375-v1/job_tree.py';raw=read(jobpath)
 assert len(raw)==8615 and hashlib.sha256(raw).hexdigest()=='5fca5b41161829a15554b08371e3fc64765164479e41bda015fec910972e9011'
 jobmodule=types.ModuleType('_peace_v2_frozen_job');jobmodule.__file__=str(jobpath);exec(compile(raw,str(jobpath),'exec'),jobmodule.__dict__)
 totals=dict(ordinary=0,delegated_fixed_host=0);delegated_attempts=0;results=[];started=time.perf_counter();passed=True
 for operation in ('new_fake_suite','check','catalog'):
  ordinary=budget['batch_new_explicit_limit']-READS-totals['ordinary']-budget['controller_and_output_reserve']
  delegated=budget['batch_delegated_fixed_host_limit']-totals['delegated_fixed_host']
  remaining_attempts=budget['batch_delegated_read_attempt_limit']-delegated_attempts
  assert ordinary>0 and delegated>0 and remaining_attempts>0
  argv=[sys.executable,'-I','-B',str(HERE/'offline_child.py'),operation,str(ordinary),str(delegated),str(remaining_attempts)]
  job=jobmodule.run_cli_tree(argv,ROOT,out/(operation+'-stdout.txt'),out/(operation+'-stderr.txt'),timeout_seconds=45,memory_limit=768*1024*1024)
  io_path=out/(operation+'-io.json');meter=json.loads(read(io_path)) if io_path.exists() else None
  if meter:
   for key in totals:totals[key]+=meter['explicit_read_bytes'][key]
   delegated_attempts+=meter['read_attempts']['delegated_fixed_host']
  post={n:pin(ROOT/n) for n in manifest['source_pins']}
  same=post==initial and pin(HERE/'source-manifest.json')==manifest_pin
  good=(job.get('exit_code')==0 and job.get('error') is None and job.get('direct_child_collected') is True and
   job.get('job_active_processes_final')==0 and same and meter is not None and meter['exit_code']==0 and meter['error'] is None)
  stdout=pin(out/(operation+'-stdout.txt'));stderr=pin(out/(operation+'-stderr.txt'))
  fake_pins={}
  if operation=='new_fake_suite' and good:
   expected=('minus-one-absent','one-absent','one-present','scalar-change','short-scalar','structural-refusal')
   for name in expected:fake_pins[name]=pin(out/('fake-'+name+'.json'))
   log=read(out/(operation+'-stderr.txt')).decode('utf-8')
   good='Ran 6 tests in ' in log and log.rstrip().endswith('OK') and len(fake_pins)==6
  if operation!='new_fake_suite' and good:
   response=json.loads(read(out/(operation+'-stdout.txt')))
   good=(response['operation']==operation and response['status']=='files_verified' and response['errors']==[] and response['selected_queue_presence'] is None
    and response['source_graph']['candidate']['sealed'] is False and response['source_graph']['candidate']['runtime_capture_authorized'] is False
    and all(response[k] is False for k in ('selected_effect_verified','peace_completed','native_ready','callable','world_lease','atomic_snapshot')))
  within=(READS+totals['ordinary']<=budget['batch_new_explicit_limit'] and totals['delegated_fixed_host']<=budget['batch_delegated_fixed_host_limit']
   and delegated_attempts<=budget['batch_delegated_read_attempt_limit'])
  good=good and within
  item=dict(operation=operation,passed=good,job=job,source_unchanged=same,stdout=stdout,stderr=stderr,
   explicit_child_reads=None if meter is None else meter['explicit_read_bytes'],cumulative_child_reads=dict(totals),controller_reads_so_far=READS,
   cumulative_new_explicit=READS+totals['ordinary'],new_explicit_limit=budget['batch_new_explicit_limit'],delegated_limit=budget['batch_delegated_fixed_host_limit'],delegated_read_attempts=delegated_attempts,
   fake_capture_pins=fake_pins,old_test_methods_run=0,real_status_run=False,game_access=0,native_game_calls=0)
  save(out/(operation+'-receipt.json'),item);results.append(item)
  if not good:passed=False;break
 final=dict(schema='EU4-PEACE-V2-FIRST-OFFLINE/1',status='offline_passed' if passed else 'offline_failed_no_retry',source_manifest=manifest_pin,
  source_graph_sha256=manifest['source_graph_sha256'],operations=results,automatic_retry=False,
  new_fake_methods=6 if results and results[0]['passed'] else None,old_test_methods_run=0,actual_status_captures=0,game_access=0,native_game_calls=0,
  explicit_new_read_bytes=READS+totals['ordinary'],delegated_fixed_host_streamed_bytes=totals['delegated_fixed_host'],delegated_read_attempts=delegated_attempts,budget=budget,
  duration_seconds=round(time.perf_counter()-started,6),all_direct_children_collected=all(x['job']['direct_child_collected'] for x in results),
  all_jobs_active_zero=all(x['job']['job_active_processes_final']==0 for x in results))
 save(out/'receipt.json',final)
 print(json.dumps(dict(status=final['status'],receipt=pin(out/'receipt.json'),new_explicit_bytes=READS+totals['ordinary'],delegated_bytes=totals['delegated_fixed_host'],
  operations=[dict(operation=x['operation'],passed=x['passed'],exit_code=x['job'].get('exit_code'),active=x['job'].get('job_active_processes_final'),peak=x['job'].get('peak_job_commit')) for x in results]),ensure_ascii=True))
 return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
