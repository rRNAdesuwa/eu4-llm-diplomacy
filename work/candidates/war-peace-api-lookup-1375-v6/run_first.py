"""First four v6 queries only; no fixtures or old query re-execution."""
import ctypes,hashlib,json,sys,types
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
JOB=ROOT/'work/candidates/frida-entry-observer-1375-v1/job_tree.py'
JOB_SHA='5fca5b41161829a15554b08371e3fc64765164479e41bda015fec910972e9011'
COMMANDS=[['check'],['catalog'],['lookup','0x993570'],['lookup','0x97bd30']]
FLAGS=('callable','native_ready','sender_authorized','gameplay_effect_verified','process_authenticated','selected_effect_verified','world_lease','atomic_snapshot','authorizes_retry')
MEMORY=768*1024*1024;FILE=4*1024*1024;LIMIT=64*1024*1024
reads=[];query_bytes=0;peak=0;REPORT=ROOT/'work/reports/war-peace-api-lookup-v6-first-queries-20261016-r1'
class PMC(ctypes.Structure):
 _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(x,ctypes.c_size_t)for x in('pw','w','pp','p','pn','n','pf','ppf','private')]
k=ctypes.WinDLL('kernel32');k.GetCurrentProcess.restype=ctypes.c_void_p;p=ctypes.WinDLL('psapi')
def guard():
 global peak
 c=PMC();c.cb=ctypes.sizeof(c);assert p.GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()),ctypes.byref(c),c.cb)
 peak=max(peak,c.pw,c.ppf,c.private);assert peak<1024**3 and peak<=MEMORY
def pin(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def read(path):
 guard();assert path.resolve().is_relative_to(ROOT.resolve());size=path.stat().st_size;assert size<=FILE
 assert sum(x['bytes']for x in reads)+query_bytes+size<=LIMIT
 raw=path.read_bytes();assert len(raw)==size;reads.append(dict(path=path.relative_to(ROOT).as_posix(),**pin(raw)));return raw
def write(name,obj):
 raw=(json.dumps(obj,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode();assert len(raw)<=FILE
 with(REPORT/name).open('xb')as f:f.write(raw)
 return pin(raw)
def sources(expected):
 raw=read(HERE/'source-manifest.json');assert pin(raw)==expected
 m=json.loads(raw);assert m['sealed']and m['independent_review_passed']is False and m['native_ready']is False
 for n,q in m['files'].items():assert pin(read(ROOT/n))==q
 return m
def main():
 global query_bytes
 assert len(sys.argv)==3;expected=dict(bytes=int(sys.argv[1]),sha256=sys.argv[2]);assert len(expected['sha256'])==64
 REPORT.mkdir(exist_ok=False)
 claim=write('claim.json',dict(schema='EU4-LOOKUP-V6-FIRST-CLAIM/1',source_manifest=expected,commands=COMMANDS,single_batch=True,no_retry=True,query_budget=LIMIT,PE_game_native=0))
 records=[];error=None
 try:
  m=sources(expected);budget=json.loads(read(HERE/'budget.json'))
  jobraw=read(JOB);assert hashlib.sha256(jobraw).hexdigest()==JOB_SHA
  job=types.ModuleType('_lookup_v6_exact_job');job.__file__=str(JOB);exec(compile(jobraw,str(JOB),'exec'),job.__dict__)
  raw=read(HERE/'data-manifest.json');data=json.loads(raw);assert len(data['sources'])==94
  perpass=len(raw)+data['index']['bytes']+sum(q['bytes']for q in data['sources'].values())
  perquery=2*perpass+3*16583
  assert perpass==budget['actual_selected_bytes_per_pass'] and perquery==budget['actual_query_explicit_read_bytes']
  assert budget['fourquery_plus_controller_upper_bytes']<=LIMIT
  for i,args in enumerate(COMMANDS):
   assert sum(x['bytes']for x in reads)+query_bytes+perquery+8*1024**2<LIMIT
   stdout=REPORT/f'{i:02d}.stdout.json';stderr=REPORT/f'{i:02d}.stderr.txt';argv=[sys.executable,str(HERE/'war_peace_lookup.py'),*args]
   result=job.run_cli_tree(argv,str(ROOT),str(stdout),str(stderr),timeout_seconds=45,memory_limit=MEMORY)
   out=read(stdout);err=read(stderr);rec=dict(argv=argv,job=result,stdout=pin(out),stderr=pin(err));records.append(rec)
   assert result['exit_code']==0 and result['error']is None and result['job_active_processes_final']==0 and 1<=result['job_total_processes']<=8
   assert result['direct_child_collected']and result['completed_command_descendants_terminated']is False and result['peak_job_commit']<=MEMORY and not err
   value=json.loads(out);assert value['status']=='ok' and value['tool_revision']==6 and all(value[f]is False for f in FLAGS)
   assert value['native_calls']==value['requests_published']==0
   pr=value['provenance'];assert pr['selected_source_count']==94 and pr['selected_bytes_per_pass']==perpass and pr['source_guard_before_and_after']is True
   query_bytes+=perquery
   rec.update(operation=value['operation'],count=value.get('count'),entry_count=value.get('entry_count'),ids=[x['id']for x in value.get('entries',[])],selected_bytes_per_pass=perpass,explicit_query_source_bytes=perquery)
   if args[0]=='check':assert value['entry_count']==60
   elif args[0]=='catalog':assert value['count']==60
   else:assert value['count']==1 and value['entries'][0]['id']==('peace.generator_divisor_source'if args[1]=='0x993570'else'peace.generator_selector_callee')
  sources(expected)
 except Exception as exc:error=dict(type=type(exc).__name__,message=str(exc))
 guard();physical=sum(x['bytes']for x in reads)+query_bytes
 receipt=dict(schema='EU4-LOOKUP-V6-FIRST-QUERY-RECEIPT/1',sealed=True,passed=error is None,error=error,source_manifest=expected,claim=claim,commands=COMMANDS,records=records,command_count=len(records),first_only_no_retries=True,
  controller_read_journal=reads,controller_explicit_bytes=sum(x['bytes']for x in reads),query_source_explicit_bytes=query_bytes,combined_physical_explicit_bytes=physical,physical_limit=LIMIT,self_peak_bytes=peak,
  all_jobs_and_direct_children_collected=all(r['job']['job_active_processes_final']==0 and r['job']['direct_child_collected']for r in records),
  complete_OS_interpreter_loader_IO_claimed=False,Python_query_engine_not_Capstone=True,independent_review_passed=False,old_suites_fixtures_or_old_CLI=0,PE_game_native_requests_install_publish=0,authority={x:False for x in FLAGS})
 rp=write('receipt.json',receipt);print(json.dumps(dict(passed=error is None,receipt=rp,combined_physical=physical,error=error,self_peak_bytes=peak)));return0=0 if error is None else 2
 return return0
if __name__=='__main__':raise SystemExit(main())
