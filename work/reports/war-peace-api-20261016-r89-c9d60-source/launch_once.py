"""Future exact-once owned analysis child. Never executed at source-build stage."""
from pathlib import Path
import hashlib,json,sys,types
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
CONTRACT_PIN={'bytes': 7777, 'sha256': '824eba3705c3bd0b7f33917f40c6bfc34de9de31e1093115e3ad47ceab7f1e67'}
READS=[]
def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def read(path):
    path=Path(path);size=path.stat().st_size
    if not 0<size<=4194304 or sum(x['bytes'] for x in READS)+size+1>2097152:raise ValueError('Parent2MiB reserve/ordinary4MiB')
    with path.open('rb') as f:raw=f.read(size+1)
    READS.append({'path':str(path),**pin(raw)})
    if len(raw)!=size:raise ValueError('Parent source changed/short')
    return raw
def save(name,value):
    with (HERE/name).open('x',encoding='ascii',newline='\n') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
def main():
    if len(sys.argv)!=2:raise ValueError('Only exact future authorization SHA')
    if any((HERE/n).exists() for n in ('launcher-claim.json','launcher-receipt.json','claim.json','capture.json','failure.json')):raise ValueError('Attempt/history already exists')
    raw=read(HERE/'runtime_contract.py')
    if pin(raw)!=CONTRACT_PIN:raise ValueError('Pinned runtime contract')
    runtime=types.ModuleType('_r89_launcher_contract');runtime.__file__=str(HERE/'runtime_contract.py')
    exec(compile(raw,runtime.__file__,'exec'),runtime.__dict__)
    before=runtime.verify(read,sys.argv[1])
    save('launcher-claim.json',{'schema':'EU4-R89-LAUNCH-ONCE-CLAIM/1','authorization_pin':before['auth_pin'],
      'source_manifest':before['manifest_pin'],'actual_attempts_max':1,'automatic_retry':False})
    job_name='work/candidates/frida-entry-observer-1375-v1/job_tree.py'
    job_raw=before['data'][job_name];job=types.ModuleType('_r89_exact_job');job.__file__=str(ROOT/job_name)
    exec(compile(job_raw,job.__file__,'exec'),job.__dict__)
    result=None;after=None;failure=None;child=None
    argv=[sys.executable,'-B',str(HERE/'produce.py'),sys.argv[1]]
    try:
        result=job.run_cli_tree(argv,str(ROOT),str(HERE/'producer.stdout.txt'),str(HERE/'producer.stderr.txt'),timeout_seconds=45,memory_limit=805306368)
        if not(result['exit_code']==0 and result['error']is None and result['job_active_processes_final']==0
          and result['direct_child_collected']is True and 1<=result['job_total_processes']<=8
          and result['memory_limit']==805306368):raise ValueError('Contained producer did not succeed/collect')
        after=runtime.verify(read,sys.argv[1])
        if after['auth_pin']!=before['auth_pin'] or after['manifest_pin']!=before['manifest_pin'] or after['review_pins']!=before['review_pins']:raise ValueError('Parent postguard differs')
        child=runtime.decode(read(HERE/'capture.json'))
        if (child['authorization_pin']!=before['auth_pin'] or child['normal_target_context_exit']is not True
          or child['commit_after_target_close_and_final_guards']is not True):raise ValueError('Child normal capture binding')
        if child['source_file_read_bytes']+sum(x['bytes'] for x in READS)>33554432:raise ValueError('Combined parent/child source32MiB')
    except BaseException as exc:failure={'type':type(exc).__name__,'message':str(exc)}
    finally:
        save('launcher-receipt.json',{'schema':'EU4-R89-OWNED-JOB-ACTUAL-RECEIPT/1','passed':failure is None,
          'authorization_pin':before['auth_pin'],'source_manifest':before['manifest_pin'],'argv':argv,
          'job':result,'failure':failure,'parent_source_reads':READS,'parent_source_bytes':sum(x['bytes'] for x in READS),
          'parent2MiB_child30MiB_subbudgets':True,'child_capture_source_bytes':None if child is None else child['source_file_read_bytes'],
          'all_shells_collected':result is not None and result['direct_child_collected']is True and result['job_active_processes_final']==0,
          'raw_stdout_stderr_retained':True,'automatic_retry':False,'game_process_accesses':0,'native_ready':False})
    return 0 if failure is None else 1
if __name__=='__main__':raise SystemExit(main())
