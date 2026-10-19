"""Narrow post-failure completion; retain first builder and all existing products."""
from pathlib import Path
import ast
import ctypes
from ctypes import wintypes
import hashlib
import json

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
MAX_FILE=4*1024*1024;BUDGET=24*1024*1024;MEMORY=768*1024*1024
reads=[];peak=0
class PMC(ctypes.Structure):
 _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(x,ctypes.c_size_t) for x in
 ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
k=ctypes.WinDLL('kernel32',use_last_error=True);p=ctypes.WinDLL('psapi',use_last_error=True)
k.GetCurrentProcess.restype=wintypes.HANDLE
p.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(PMC),wintypes.DWORD]
prior_upper=1024*1024
def guard():
 global peak
 x=PMC();x.cb=ctypes.sizeof(x);assert p.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(x),x.cb)
 peak=max(peak,x.PrivateUsage,x.PeakPagefileUsage,x.WorkingSetSize,x.PeakWorkingSetSize);assert peak<=MEMORY
def pin(b):return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def read(path,expected=None):
 guard();a=path.stat();assert a.st_size<=MAX_FILE
 assert prior_upper+sum(x['bytes'] for x in reads)+a.st_size<=BUDGET
 b=path.read_bytes();z=path.stat();assert (a.st_size,a.st_mtime_ns)==(z.st_size,z.st_mtime_ns) and len(b)==a.st_size
 if expected is not None:assert pin(b)==expected,(str(path),'changed')
 reads.append(dict(path=path.relative_to(ROOT).as_posix(),**pin(b)));return b
def write(name,obj):
 b=(json.dumps(obj,ensure_ascii=True,indent=2,sort_keys=True)+'\n').encode()
 with (HERE/name).open('xb') as f:f.write(b)
 return pin(b)
def main():
 global prior_upper
 write('repair-claim.json',dict(schema='EU4-LOOKUP-V4-NARROW-REPAIR-CLAIM/1',scope='runner generation and source seal only',
  prior_files_overwritten=False,new_query_attempts=0,tests=0,PE_game_native=0))
 try:
  failure_raw=read(HERE/'build-failure.json');failure=json.loads(failure_raw)
  assert failure['error']=='AssertionError'
  prior_upper+=sum(x['bytes'] for x in failure['reads'])
  oldpins={x['path']:{k:x[k] for k in ('bytes','sha256')} for x in failure['reads']}
  cache={name:read(ROOT/name,expected) for name,expected in oldpins.items()}
  old='work/candidates/war-peace-api-lookup-1375-v3/'
  delta=json.loads(read(HERE/'source-delta.json'))
  for name,key in [('index.json','index'),('data-manifest.json','data_manifest'),('war_peace_lookup.py','current_cli')]:read(HERE/name,delta[key])
  dm=json.loads(read(HERE/'data-manifest.json'))
  idx=json.loads(read(HERE/'index.json'));oldidx=json.loads(cache[old+'index.json'])
  byid={r['id']:r for r in idx['entries']};assert len(byid)==58
  assert all(byid[r['id']]==r for r in oldidx['entries']) and len(oldidx['entries'])==54 and len(dm['sources'])==59
  raw=cache[old+'run_queries.py'];runner=raw.decode().replace('\r\n','\n')
  tree=ast.parse(runner)
  node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='COMMANDS' for t in n.targets))
  lines=runner.splitlines(keepends=True)
  newcommands="COMMANDS=[['check'],['catalog'],['lookup','0x97b2c0'],['lookup','0x97b8a0'],\n          ['lookup','0x994f00'],['lookup','0x1a337f0'],['search','v4 已审合同','--limit','20']]\n"
  runner=''.join(lines[:node.lineno-1])+newcommands+''.join(lines[node.end_lineno:])
  runner=runner.replace('lookup-v3-delta-20261016-r1','lookup-v4-first-queries-20261016-r1')
  runner=runner.replace('f4b5f7e1fe4e5546cdac66a6f9bb45541ead648d311cc2e2e9023e2b56910979',delta['current_cli']['sha256']).replace('V3','V4').replace('_v3_','_v4_')
  runner=runner.replace('file_analysis_budget_separate=32*1024*1024','file_analysis_budget_separate=24*1024*1024').replace('analysis_budget_separate=32*1024*1024','analysis_budget_separate=24*1024*1024')
  runner=runner.replace("value['tool_revision']==3","value['tool_revision']==4").replace("provenance['selected_source_count']==44","provenance['selected_source_count']==59").replace("value['entry_count']==54","value['entry_count']==58").replace("value['count']==54","value['count']==58")
  begin=runner.index("                if args[1]=='0x771be0':");end=runner.index('        sourceguard(sourcepin)',begin)
  runner=runner[:begin]+"            else:assert value['count']==4 and {x['rva'] for x in value['entries']}=={'0x97b2c0','0x97b8a0','0x994f00','0x1a337f0'}\n"+runner[end:]
  # Fixed maximum source-read reservation before each launch, separate from measured successful reads.
  runner=runner.replace("        for index,args in enumerate(COMMANDS):", "        per_query_upper=2*(len((HERE/'data-manifest.json').read_bytes())+sum(v['bytes'] for v in json.loads((HERE/'data-manifest.json').read_bytes())['sources'].values())+json.loads((HERE/'data-manifest.json').read_bytes())['index']['bytes'])+3*FROZEN_ENGINE_BYTES\n        for index,args in enumerate(COMMANDS):\n            assert sum(x['bytes'] for x in reads)+query_bytes+per_query_upper+4*1024*1024<=BATCH_BUDGET")
  # Avoid unjournalled reads in the preceding expression: use one controlled read.
  begin=runner.index('        per_query_upper=');end=runner.index('        for index,args',begin)
  runner=runner[:begin]+"        data_raw=read(HERE/'data-manifest.json');data=json.loads(data_raw)\n        per_query_upper=2*(len(data_raw)+sum(v['bytes'] for v in data['sources'].values())+data['index']['bytes'])+3*FROZEN_ENGINE_BYTES\n"+runner[end:]
  runner=runner.replace("item=dict(argv=argv,job=receipt,stdout=pin(out),stderr=pin(err))", "item=dict(argv=argv,job=receipt,stdout=pin(out),stderr=pin(err),query_source_reserved_upper_bytes=per_query_upper)")
  runner=runner.replace("query_bytes+=explicit", "assert explicit<=per_query_upper\n            query_bytes+=explicit\n            item.update(cumulative_query_source_bytes=query_bytes,cumulative_batch_explicit_bytes=query_bytes+sum(x['bytes'] for x in reads))")
  tree=ast.parse(runner)
  commands=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='COMMANDS' for t in n.targets)))
  assert len(commands)==7 and commands[2]==['lookup','0x97b2c0'] and commands[-1][1]=='v4 已审合同'
  for n in ('sourceguard','guard','read','write'):
   before=next(x for x in ast.parse(raw).body if isinstance(x,ast.FunctionDef) and x.name==n)
   after=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name==n)
   assert ast.dump(before,include_attributes=False)==ast.dump(after,include_attributes=False)
  with (HERE/'run_queries.py').open('xb') as f:f.write(runner.encode())
  # Complete source guards, preserving the initial product bytes exactly.
  for name,expected in oldpins.items():read(ROOT/name,expected)
  local=['README.md','budget.json','build_index.py','build-claim.json','build-failure.json','build.stdout.txt','build.stderr.txt',
   'repair_runner.py','repair-claim.json','index.json','data-manifest.json','war_peace_lookup.py','lineage-proof.json','source-delta.json','run_queries.py']
  files=dict(oldpins)
  for name in local:files[(HERE/name).relative_to(ROOT).as_posix()]=pin(read(HERE/name))
  receipt=write('repair-receipt.json',dict(schema='EU4-LOOKUP-V4-NARROW-REPAIR/1',sealed=True,passed=True,
   first_failure=pin(failure_raw),scope='Only new runner generation/source-manifest completion; no old product overwrite',
   initial_builder_source_preserved=True,prior_index_data_CLI_byte_identical=True,original54_dataequal=True,
   source_prepost_equal=True,source_pins=oldpins,reads=reads,
   prior_upper_including_manual=prior_upper,repair_explicit_bytes=sum(x['bytes'] for x in reads),
   analysis_upper_through_repair=prior_upper+sum(x['bytes'] for x in reads),analysis_budget=BUDGET,
   query_batch_budget_separate=64*1024*1024,self_peak=peak,new_queries_run=0,old_CLI_tests_PE_game_native=0))
  files[(HERE/'repair-receipt.json').relative_to(ROOT).as_posix()]=receipt
  sp=write('source-manifest.json',dict(schema='EU4-LOOKUP-V4-SOURCE-MANIFEST/1',sealed=True,
   status='SOURCE_READY_PENDING_ROOT_INDEPENDENT_REVIEW',native_ready=False,callable=False,
   game_sha256='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a',
   entry_count=58,selected_JSON_sources=59,files=dict(sorted(files.items())),
   dependency_scope='flat selected evidence; nested historical/engine refs remain metadata, no recursive reads',
   first_queries_pending=True,build_analysis_budget=BUDGET,first_query_batch_budget=64*1024*1024,
   authority={x:False for x in ('native_ready','callable','selected_effect_verified','runtime_capture_authorized','world_lease','atomic_snapshot','authorizes_retry')}))
  print(json.dumps(dict(passed=True,source_manifest=sp,cli=delta['current_cli'],index=delta['index'],data=delta['data_manifest'],
   files=len(files),analysis_upper=prior_upper+sum(x['bytes'] for x in reads),peak=peak)))
 except BaseException as exc:
  write('repair-failure.json',dict(error=type(exc).__name__,detail=str(exc),reads=reads,peak=peak,retry_authorized=False));raise
if __name__=='__main__':main()
