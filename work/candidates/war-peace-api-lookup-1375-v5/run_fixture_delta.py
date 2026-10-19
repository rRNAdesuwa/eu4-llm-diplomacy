"""One NEW aggregate child only; prior failed receipt/physical charge retained."""
import ctypes,hashlib,json,sys,types
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
REPORT=ROOT/'work/reports/war-peace-api-lookup-v5-aggregate-delta-20261016-r1'
MASTER=dict(bytes=19355,sha256='1c1b0acd82b7ad100c8e6085deb5e994b92defd8212bf61d2a3a5db2b6cdf27f')
JOB=ROOT/'work/candidates/frida-entry-observer-1375-v1/job_tree.py';JOB_SHA='5fca5b41161829a15554b08371e3fc64765164479e41bda015fec910972e9011'
MEMORY=768*1024*1024;LIMIT=16*1024*1024;PRIOR=2973221+5*1024*1024;reads=[];peak=0;child_bytes=0
class PMC(ctypes.Structure):
 _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(x,ctypes.c_size_t)for x in('pw','w','pp','p','pn','n','pf','ppf','private')]
k=ctypes.WinDLL('kernel32');k.GetCurrentProcess.restype=ctypes.c_void_p;p=ctypes.WinDLL('psapi')
def guard():
 global peak
 x=PMC();x.cb=ctypes.sizeof(x);assert p.GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()),ctypes.byref(x),x.cb)
 peak=max(peak,x.pw,x.ppf,x.private);assert peak<1024*1024*1024 and peak<=MEMORY
def pin(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def read(path,expected=None):
 guard();path=Path(path).resolve();assert path.is_relative_to(ROOT);s=path.stat();assert s.st_size<=4*1024*1024
 assert PRIOR+sum(x['bytes']for x in reads)+child_bytes+s.st_size<LIMIT
 raw=path.read_bytes();a=path.stat();assert(len(raw),s.st_size,s.st_mtime_ns)==(a.st_size,a.st_size,a.st_mtime_ns)
 if expected:assert pin(raw)==expected
 reads.append(dict(path=path.relative_to(ROOT).as_posix(),**pin(raw)));return raw
def write(name,value):
 raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
 with(REPORT/name).open('xb')as f:f.write(raw)
 return pin(raw)
def guard_sources(expected):
 raw=read(HERE/'fixture-delta-source-manifest.json',expected);d=json.loads(raw);assert d['sealed']and d['prior_batch_still_failed']
 for path,q in d['files'].items():read(ROOT/path,q)
 master=json.loads(read(HERE/'source-manifest.json',MASTER))
 for path,q in master['files'].items():read(ROOT/path,q)
def main():
 global child_bytes
 assert len(sys.argv)==3;expected=dict(bytes=int(sys.argv[1]),sha256=sys.argv[2]);assert len(expected['sha256'])==64
 REPORT.mkdir(exist_ok=False);claim=write('claim.json',dict(sealed=True,first_aggregate_only=True,delta_manifest=expected,prior_controller=2973221,prior_child_conservative_charge=5*1024*1024,total_fixture_physical_limit=LIMIT,no_prior_case_rerun=True))
 records=[];error=None
 try:
  guard_sources(expected);raw=read(JOB);assert pin(raw)['sha256']==JOB_SHA
  job=types.ModuleType('_v5_aggregate_owned_job');job.__file__=str(JOB);exec(compile(raw,str(JOB),'exec'),job.__dict__)
  argv=[sys.executable,str(HERE/'guard_aggregate.py')];receipt=job.run_cli_tree(argv,str(ROOT),str(REPORT/'00.stdout.json'),str(REPORT/'00.stderr.txt'),timeout_seconds=45,memory_limit=MEMORY)
  out=read(REPORT/'00.stdout.json');err=read(REPORT/'00.stderr.txt');records.append(dict(argv=argv,job=receipt,stdout=pin(out),stderr=pin(err)))
  assert receipt['exit_code']==0 and receipt['error']is None and receipt['job_active_processes_final']==0 and 1<=receipt['job_total_processes']<=8 and receipt['direct_child_collected']and receipt['completed_command_descendants_terminated']is False and not err
  v=json.loads(out);assert v['passed']and v['first_aggregate_only']and v['prior_failed_batch_still_failed']and v['clean_three_fixture_batch_passed']is False
  child_bytes=v['physical_explicit_read_bytes'];assert child_bytes==16583 and v['synthetic_returned_or_charged_bytes']<40*1024*1024
  guard_sources(expected)
 except Exception as exc:error=dict(type=type(exc).__name__,message=str(exc))
 value=dict(schema='EU4-LOOKUP-V5-AGGREGATE-DELTA-RECEIPT/1',sealed=True,passed=error is None,error=error,delta_manifest=expected,claim=claim,records=records,
  controller_read_journal=reads,controller_explicit_bytes=sum(x['bytes']for x in reads),child_physical_bytes=child_bytes,prior_failed_controller_bytes=2973221,prior_failed_child_upper=5*1024*1024,
  cumulative_fixture_physical_upper=PRIOR+sum(x['bytes']for x in reads)+child_bytes,fixture_limit=LIMIT,synthetic_bytes_separate=(v['synthetic_returned_or_charged_bytes']if error is None else None),
  prior_batch_still_failed=True,no_cases97_or_largefile_repeated=True,clean_three_fixture_batch_passed=False,self_peak_bytes=peak,
  all_jobs_and_direct_children_collected=all(x['job']['job_active_processes_final']==0 and x['job']['direct_child_collected']for x in records),PE_Capstone_game_native=0,independent_review_passed=False)
 assert value['cumulative_fixture_physical_upper']<LIMIT
 rp=write('receipt.json',value);print(json.dumps(dict(passed=error is None,receipt=rp,cumulative_fixture_upper=value['cumulative_fixture_physical_upper'],peak_bytes=peak,error=error)))
 return 0 if error is None else 2
if __name__=='__main__':raise SystemExit(main())
