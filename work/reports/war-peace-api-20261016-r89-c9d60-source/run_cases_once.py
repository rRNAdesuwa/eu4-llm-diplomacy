"""Only four new frozen synthetic cases in an owned bounded Job; no actual launcher."""
from pathlib import Path
import hashlib,json,sys,types
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
READS=[]
def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def read(path,expected=None):
 size=path.stat().st_size
 if not 0<size<=4194304 or sum(x['bytes']for x in READS)+size+1>33554432:raise ValueError('Bounded source32MiB/ordinary4MiB')
 with path.open('rb')as f:raw=f.read(size+1)
 READS.append({'path':str(path),**pin(raw)})
 if len(raw)!=size or expected is not None and pin(raw)!=expected:raise ValueError('Source pin/size changed')
 return raw
def save(name,value):
 with(HERE/name).open('x',encoding='ascii')as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
def main():
 if len(sys.argv)!=2 or any((HERE/n).exists()for n in ['cases-run-claim.json','cases-run.json','cases.json']):raise ValueError('One new case batch only')
 manifest_raw=read(HERE/'source-manifest.json')
 if pin(manifest_raw)['sha256']!=sys.argv[1]:raise ValueError('Frozen manifest SHA before parse')
 manifest=json.loads(manifest_raw)
 if manifest['schema']!='EU4-R89-FIXED-PREFIX-SOURCE/1' or manifest['sealed']is not True:raise ValueError('Frozen R89 source')
 owned={name:read(ROOT/name,p)for name,p in manifest['actual_source_pins'].items()}
 save('cases-run-claim.json',{'schema':'EU4-R89-NEW-CASES-RUN-CLAIM/1','source_manifest':pin(manifest_raw),'runs_max':1})
 name='work/candidates/frida-entry-observer-1375-v1/job_tree.py'
 module=types.ModuleType('_r89_new_cases_job');module.__file__=str(ROOT/name)
 exec(compile(owned[name],module.__file__,'exec'),module.__dict__)
 job=cases=None;failure=None
 try:
  job=module.run_cli_tree([sys.executable,'-B',str(HERE/'cases_child.py'),sys.argv[1]],str(ROOT),str(HERE/'cases.stdout.txt'),str(HERE/'cases.stderr.txt'),timeout_seconds=45,memory_limit=805306368)
  if not(job['exit_code']==0 and job['error']is None and job['job_active_processes_final']==0 and job['direct_child_collected']is True and 1<=job['job_total_processes']<=8):raise ValueError('New case child failed/unclean')
  cases=json.loads(read(HERE/'cases.json'))
  if not(cases['passed']is True and len(cases['cases'])==4 and all(v['runs']==1 and v['passed']is True for v in cases['cases'])):raise ValueError('Four first cases did not pass')
  if read(HERE/'source-manifest.json')!=manifest_raw:raise ValueError('Manifest postguard')
  for name,p in manifest['actual_source_pins'].items():read(ROOT/name,p)
  if cases['source_bytes']+sum(v['bytes']for v in READS)>33554432:raise ValueError('Combined synthetic batch source32MiB')
 except BaseException as error:failure={'type':type(error).__name__,'message':str(error)}
 finally:
  save('cases-run.json',{'schema':'EU4-R89-FIRST-FOUR-NEW-CASES-RECEIPT/1','passed':failure is None,'failure':failure,
   'source_manifest':pin(manifest_raw),'Job':job,'runner_source_reads':READS,'runner_source_bytes':sum(v['bytes']for v in READS),
   'child_source_bytes':None if cases is None else cases['source_bytes'],
   'all_shells_collected':job is not None and job['direct_child_collected']is True and job['job_active_processes_final']==0,
   'old_tests_or_cases':0,'producer_or_actual_launcher_runs':0,'PE_engine_decoder_game_access':0,'actual_authorized':False,'native_ready':False})
 return 0 if failure is None else 1
if __name__=='__main__':raise SystemExit(main())
