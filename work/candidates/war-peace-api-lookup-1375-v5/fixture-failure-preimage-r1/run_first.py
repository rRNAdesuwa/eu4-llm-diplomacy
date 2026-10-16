"""First-only v5 fixture/query controller; source pin argument is internal author preparation."""
import ctypes,hashlib,json,sys,types
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
JOB=ROOT/'work/candidates/frida-entry-observer-1375-v1/job_tree.py'
JOB_SHA='5fca5b41161829a15554b08371e3fc64765164479e41bda015fec910972e9011'
MEMORY=768*1024*1024;FILE=4*1024*1024
FLAGS=('callable','native_ready','sender_authorized','gameplay_effect_verified','process_authenticated','selected_effect_verified','world_lease','atomic_snapshot','authorizes_retry')
COMMANDS=[['check'],['catalog'],['lookup','0x993570'],['search','993643','--family','peace','--limit','20']]
reads=[];peak=0;query_bytes=0;child_fixture_bytes=0;LIMIT=0;REPORT=None
class PMC(ctypes.Structure):
 _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(x,ctypes.c_size_t)for x in('pw','w','pp','p','pn','n','pf','ppf','private')]
k=ctypes.WinDLL('kernel32',use_last_error=True);k.GetCurrentProcess.restype=ctypes.c_void_p;p=ctypes.WinDLL('psapi',use_last_error=True)
def guard():
 global peak
 c=PMC();c.cb=ctypes.sizeof(c);assert p.GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()),ctypes.byref(c),c.cb)
 peak=max(peak,c.pw,c.ppf,c.private);assert peak<1024*1024*1024 and peak<=MEMORY
def pin(r):return dict(bytes=len(r),sha256=hashlib.sha256(r).hexdigest())
def read(path):
 guard();assert path.resolve().is_relative_to(ROOT.resolve());a=path.stat();assert a.st_size<=FILE
 assert sum(x['bytes']for x in reads)+query_bytes+child_fixture_bytes+a.st_size<=LIMIT
 raw=path.read_bytes();b=path.stat();assert(len(raw),a.st_size,a.st_mtime_ns)==(b.st_size,b.st_size,b.st_mtime_ns)
 reads.append(dict(path=str(path.relative_to(ROOT)).replace('\\','/'),**pin(raw)));return raw
def write(name,obj):
 raw=(json.dumps(obj,sort_keys=True,indent=2)+'\n').encode();assert len(raw)<=FILE
 with(REPORT/name).open('xb')as f:f.write(raw)
 return pin(raw)
def source_guard(expected):
 raw=read(HERE/'source-manifest.json');assert pin(raw)==expected
 m=json.loads(raw);assert m['sealed']and m['native_ready']is False and m['independent_review_passed']is False
 for path,q in m['files'].items():assert pin(read(ROOT/path))==q
 return m
def main():
 global LIMIT,REPORT,query_bytes,child_fixture_bytes
 assert len(sys.argv)==4 and sys.argv[1]in('fixtures','queries')
 phase=sys.argv[1];expected=dict(bytes=int(sys.argv[2]),sha256=sys.argv[3]);assert len(expected['sha256'])==64
 LIMIT=(16 if phase=='fixtures'else 64)*1024*1024
 REPORT=ROOT/('work/reports/war-peace-api-lookup-v5-'+('guard-fixtures'if phase=='fixtures'else'first-queries')+'-20261016-r1')
 REPORT.mkdir(exist_ok=False)
 claim=write('claim.json',dict(schema='EU4-LOOKUP-V5-FIRST-CLAIM/1',phase=phase,source_manifest=expected,commands=COMMANDS if phase=='queries'else[['guard_fixtures.py']],physical_budget=LIMIT,
  synthetic_fixture_limit=40*1024*1024,old_suites=0,PE_game_native=0))
 records=[];error=None
 try:
  m=source_guard(expected);jobraw=read(JOB);assert hashlib.sha256(jobraw).hexdigest()==JOB_SHA
  job=types.ModuleType('_lookup_v5_fixed_job');job.__file__=str(JOB);exec(compile(jobraw,str(JOB),'exec'),job.__dict__)
  data_raw=read(HERE/'data-manifest.json');data=json.loads(data_raw)
  per_query_upper=2*(len(data_raw)+data['index']['bytes']+sum(x['bytes']for x in data['sources'].values()))+3*16583
  assert len(data['sources'])==74
  commands=COMMANDS if phase=='queries'else[[]]
  for number,args in enumerate(commands):
   needed=per_query_upper if phase=='queries'else 5*1024*1024
   assert sum(x['bytes']for x in reads)+query_bytes+child_fixture_bytes+needed+4*1024*1024<LIMIT
   stdout=REPORT/f'{number:02d}.stdout.json';stderr=REPORT/f'{number:02d}.stderr.txt'
   script=HERE/('war_peace_lookup.py'if phase=='queries'else'guard_fixtures.py')
   argv=[sys.executable,str(script),*args]
   receipt=job.run_cli_tree(argv,str(ROOT),str(stdout),str(stderr),timeout_seconds=45,memory_limit=MEMORY)
   out=read(stdout);err=read(stderr);record=dict(argv=argv,job=receipt,stdout=pin(out),stderr=pin(err));records.append(record)
   assert receipt['exit_code']==0 and receipt['error']is None and receipt['job_active_processes_final']==0 and 1<=receipt['job_total_processes']<=8
   assert receipt['direct_child_collected']and receipt['completed_command_descendants_terminated']is False and receipt['peak_job_commit']<=MEMORY and not err
   value=json.loads(out)
   if phase=='queries':
    assert value['status']=='ok'and value['tool_revision']==5 and all(value[x]is False for x in FLAGS)
    assert value['native_calls']==value['requests_published']==0
    pr=value['provenance'];assert pr['selected_source_count']==74 and pr['source_guard_before_and_after']is True
    actual=2*pr['selected_bytes_per_pass']+3*16583;assert actual<=per_query_upper;query_bytes+=actual
    record.update(operation=value['operation'],count=value.get('count'),entry_count=value.get('entry_count'),ids=[x['id']for x in value.get('entries',[])],selected_bytes_per_pass=pr['selected_bytes_per_pass'],explicit_query_source_bytes=actual)
    if args[0]=='check':assert value['entry_count']==59
    elif args[0]=='catalog':assert value['count']==59
    else:assert value['count']==1 and value['entries'][0]['id']=='peace.generator_divisor_source'
   else:
    assert value['passed']and value['first_new_methods']==3 and len(value['records'])==3
    child_fixture_bytes=value['physical_explicit_read_bytes'];assert child_fixture_bytes<16*1024*1024 and value['synthetic_returned_or_charged_bytes']<40*1024*1024
    record.update(first_new_fixture_methods=3,physical_explicit_read_bytes=child_fixture_bytes,synthetic_returned_or_charged_bytes=value['synthetic_returned_or_charged_bytes'])
   assert sum(x['bytes']for x in reads)+query_bytes+child_fixture_bytes<=LIMIT
  source_guard(expected)
 except Exception as exc:error=dict(type=type(exc).__name__,message=str(exc))
 guard()
 result=dict(schema='EU4-LOOKUP-V5-FIRST-RECEIPT/1',sealed=True,passed=error is None,error=error,phase=phase,source_manifest=expected,claim=claim,records=records,command_count=len(records),first_only_no_retries=True,
  controller_read_journal=reads,controller_explicit_bytes=sum(x['bytes']for x in reads),query_source_explicit_bytes=query_bytes,child_fixture_physical_bytes=child_fixture_bytes,
  combined_physical_explicit_bytes=sum(x['bytes']for x in reads)+query_bytes+child_fixture_bytes,physical_limit=LIMIT,synthetic_fixture_bytes_separate=[r.get('synthetic_returned_or_charged_bytes',0)for r in records],
  self_peak_bytes=peak,all_jobs_and_direct_children_collected=all(r['job']['job_active_processes_final']==0 and r['job']['direct_child_collected']for r in records),
  complete_OS_interpreter_loader_IO_claimed=False,Python_queryengine_not_Capstone=True,independent_review_passed=False,old_suites_or_old_CLI=0,PE_game_native_requests_install_publish=0,authority={x:False for x in FLAGS})
 rp=write('receipt.json',result);print(json.dumps(dict(passed=error is None,phase=phase,receipt=rp,combined_physical=result['combined_physical_explicit_bytes'],peak_bytes=peak,error=error)))
 return0=0 if error is None else 2
 return return0
if __name__=='__main__':raise SystemExit(main())
