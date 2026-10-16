"""Author retained-only v5 seal after first fixture/query jobs; no reruns/imports."""
import ast,ctypes,hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
LIMIT=32*1024*1024;FILE=4*1024*1024;reads=[];peak=0
FLAGS=('callable','native_ready','sender_authorized','gameplay_effect_verified','process_authenticated','selected_effect_verified','world_lease','atomic_snapshot','authorizes_retry')
class PMC(ctypes.Structure):
 _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(x,ctypes.c_size_t)for x in('pw','w','pp','p','pn','n','pf','ppf','private')]
k=ctypes.WinDLL('kernel32',use_last_error=True);k.GetCurrentProcess.restype=ctypes.c_void_p;p=ctypes.WinDLL('psapi',use_last_error=True)
def guard():
 global peak
 c=PMC();c.cb=ctypes.sizeof(c);assert p.GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()),ctypes.byref(c),c.cb)
 peak=max(peak,c.pw,c.ppf,c.private);assert peak<1024*1024*1024 and peak<=768*1024*1024
def pin(r):return dict(bytes=len(r),sha256=hashlib.sha256(r).hexdigest())
def read(path,q=None):
 guard();path=Path(path).resolve();assert path.is_relative_to(ROOT)and not path.is_relative_to(ROOT/'work/deps')
 a=path.stat();assert a.st_size<=FILE;r=path.read_bytes();z=path.stat();assert(len(r),a.st_size,a.st_mtime_ns)==(z.st_size,z.st_size,z.st_mtime_ns)
 if q:assert pin(r)==q,str(path)
 reads.append(dict(path=path.relative_to(ROOT).as_posix(),**pin(r)));assert sum(x['bytes']for x in reads)<LIMIT;return r
def write(name,obj):
 r=(json.dumps(obj,sort_keys=True,ensure_ascii=True,indent=2)+'\n').encode();assert len(r)<=FILE
 with(HERE/name).open('xb')as f:f.write(r)
 return pin(r)
def pointer(v,ptr):
 for t in ptr.split('/')[1:]:
  t=t.replace('~1','/').replace('~0','~');v=v[int(t)]if type(v)is list else v[t]
 return v
def main():
 assert len(sys.argv)==3;expected=dict(bytes=int(sys.argv[1]),sha256=sys.argv[2]);assert len(expected['sha256'])==64
 claim=write('seal-claim.json',dict(sealed=True,retained_only_once=True,source_manifest=expected,rerun_fixture_or_queries=False,PE_game_native=0))
 raw=read(HERE/'source-manifest.json',expected);m=json.loads(raw);assert m['sealed']and m['independent_review_passed']is False
 cache={path:read(ROOT/path,q)for path,q in m['files'].items()}
 rel=HERE.relative_to(ROOT).as_posix()+'/'
 oldprefix='work/candidates/war-peace-api-lookup-1375-v4/'
 index=json.loads(cache[rel+'index.json']);old=json.loads(cache[oldprefix+'index.json']);data=json.loads(cache[rel+'data-manifest.json']);olddata=json.loads(cache[oldprefix+'data-manifest.json'])
 assert len(index['entries'])==59 and len(data['sources'])==74 and len(old['entries'])==58 and len(olddata['sources'])==59
 rows={r['id']:r for r in index['entries']};oldrows={r['id']:r for r in old['entries']};newids=set(rows)-set(oldrows)
 assert newids=={'peace.generator_divisor_source'}and all(rows[k]==v for k,v in oldrows.items())
 assert all(data['sources'][path]==q for path,q in olddata['sources'].items())
 new=rows['peace.generator_divisor_source'];assert new['rva']=='0x993570'and new['kind']=='function'and new['whole_function_closed']is False and new['independent_fragments_callable']is False
 assert all(new[x]is False for x in FLAGS)and len(new['owned_ranges'])==3
 docs={path:json.loads(cache[path])for path in data['sources']};used=set();refcount=0
 for row in index['entries']:
  for e in row['evidence']:
   assert {k:e[k]for k in('bytes','sha256')}==data['sources'][e['path']];pointer(docs[e['path']],e['json_pointer']);used.add(e['path']);refcount+=1
 assert used==set(data['sources'])
 delta=json.loads(cache[rel+'engine-delta.json']);oldengine=cache['work/candidates/war-peace-api-lookup-1375-v1/war_peace_lookup.py'];newengine=cache[rel+'query_engine.py']
 assert oldengine.replace(b'1 <= len(sources) <= 64',b'1 <= len(sources) <= 96')==newengine and oldengine.count(b'1 <= len(sources) <= 64')==1
 assert [i for i,(a,b)in enumerate(zip(oldengine,newengine))if a!=b]==[9450,9451]and delta['new_engine_pin']==pin(newengine)
 receiptpins={};all_outputs={};receipts={}
 for phase,label in [('fixtures','guard-fixtures'),('queries','first-queries')]:
  directory=ROOT/f'work/reports/war-peace-api-lookup-v5-{label}-20261016-r1'
  rr=read(directory/'receipt.json');receipt=json.loads(rr);receipts[phase]=receipt;receiptpins[(directory/'receipt.json').relative_to(ROOT).as_posix()]=pin(rr)
  assert receipt['passed']and receipt['error']is None and receipt['source_manifest']==expected and receipt['first_only_no_retries']and receipt['all_jobs_and_direct_children_collected']
  assert receipt['command_count']==(1 if phase=='fixtures'else 4)
  assert receipt['combined_physical_explicit_bytes']<=receipt['physical_limit']
  for n,r in enumerate(receipt['records']):
   job=r['job'];assert job['exit_code']==0 and job['error']is None and job['job_active_processes_final']==0 and job['direct_child_collected']and job['completed_command_descendants_terminated']is False
   out=read(directory/f'{n:02d}.stdout.json',r['stdout']);err=read(directory/f'{n:02d}.stderr.txt',r['stderr']);assert not err
   for name,z in [(f'{n:02d}.stdout.json',out),(f'{n:02d}.stderr.txt',err)]:all_outputs[(directory/name).relative_to(ROOT).as_posix()]=pin(z)
   value=json.loads(out)
   if phase=='fixtures':assert value['first_new_methods']==3 and value['passed']and value['synthetic_returned_or_charged_bytes']<40*1024*1024
   else:assert value['tool_revision']==5 and value['status']=='ok'and all(value[x]is False for x in FLAGS)and value['provenance']['selected_source_count']==74
  cr=read(directory/'claim.json',receipt['claim']);receiptpins[(directory/'claim.json').relative_to(ROOT).as_posix()]=pin(cr)
 assert receipts['queries']['query_source_explicit_bytes']==sum(r['explicit_query_source_bytes']for r in receipts['queries']['records'])
 buildraw=read(HERE/'build-receipt.json');build=json.loads(buildraw)
 # Re-pin only fixed admitted source graph; nested historical manifests/Capstone metadata are not expanded.
 for path,q in m['files'].items():read(ROOT/path,q)
 read(HERE/'source-manifest.json',expected)
 upper=build['build_stage_upper']+sum(x['bytes']for x in reads)+1024*1024
 assert upper<LIMIT
 metrics=dict(entry_count=59,selected_JSON_count=74,old58_data_equal=True,old59pins_unchanged=True,new_entry_count=1,new_entry_RVA='0x993570',new_fragment_entrypoints=0,JSON_pointer_refs=refcount,
  query_count_first_only=4,new_guard_fixture_methods_first_only=3,build_stage_upper=build['build_stage_upper'],sealer_explicit_bytes=sum(x['bytes']for x in reads),seal_remaining_allowance=1024*1024,
  combined_build_seal_upper=upper,build_seal_limit=LIMIT,query_batch_separate_physical=receipts['queries']['combined_physical_explicit_bytes'],query_limit=64*1024*1024,
  fixture_batch_separate_physical=receipts['fixtures']['combined_physical_explicit_bytes'],fixture_limit=16*1024*1024,fixture_synthetic_returned_separate=receipts['fixtures']['synthetic_fixture_bytes_separate'],
  self_peak_bytes=peak,complete_OS_loader_IO_claimed=False,engine_is_new_identity=True,ordinary_frozen_old_engine_changed=False,all_shells_collected=True)
 vp=write('verification.json',dict(sealed=True,passed=True,author_selfcheck_not_independent=True,metrics=metrics,source_prepost_equal=True,receipt_pins=receiptpins,query_fixture_output_pins=all_outputs,
  read_events=reads,PE_Capstone_game_native=0,authority={x:False for x in FLAGS}))
 sourcepins=m['files']|{rel+'source-manifest.json':expected,rel+'build-receipt.json':pin(buildraw),rel+'verification.json':vp,rel+'seal-claim.json':claim}|receiptpins|all_outputs
 for name in('intake-receipt.json','build-claim.json'):
  r=read(HERE/name);sourcepins[rel+name]=pin(r)
 ap=write('author-manifest.json',dict(schema='EU4-LOOKUP-V5-AUTHOR-MANIFEST/1',sealed=True,status='SOURCE_READY_PENDING_NONAUTHOR_FULL_ENGINE_SOURCE_REVIEW',local_and_selected_source_pins=sourcepins,pin_count=len(sourcepins),
  subject_source_manifest=expected,metrics=metrics,source_graph_and_first_outputs_prepost_equal=True,independent_review_passed=False,authority={x:False for x in FLAGS}))
 dp=write('delivery.json',dict(sealed=True,stage='author_completed_pending_nonauthor_full_review_not_published',author_manifest=ap,source_manifest=expected,verification=vp,index=m['files'][rel+'index.json'],data=m['files'][rel+'data-manifest.json'],
  query_engine=m['files'][rel+'query_engine.py'],new_query_engine_identity=True,first_queries=4,first_guard_methods=3,old_sources_modified=False,all_shells_collected=True,independent_review_passed=False,
  metrics=metrics,authority={x:False for x in FLAGS}))
 print(json.dumps(dict(passed=True,author_manifest=ap,verification=vp,delivery=dp,combined_build_seal_upper=upper,peak_bytes=peak)))
if __name__=='__main__':
 try:main()
 except BaseException as exc:
  if not(HERE/'seal-failure-r1.json').exists():write('seal-failure-r1.json',dict(type=type(exc).__name__,message=str(exc),read_events=reads,automatic_retry=False,PE_game_native=0))
  raise
