"""Retained-only author delivery after first four queries. Never re-runs a command."""
import ctypes,hashlib,json,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
BASE='work/candidates/war-peace-api-lookup-1375-v6/'
REPORT='work/reports/war-peace-api-lookup-v6-first-queries-20261016-r1/'
OUT=ROOT/'work/reports/war-peace-api-lookup-v6-author-delivery-20261016-r1'
LIMIT=2*1024**2;J=[];P={};C={}
HARD={
 BASE+'source-manifest.json':dict(bytes=25179,sha256='9e292ce2c077be0af996bad24ba44dab98ea88566726f88cd36093fc45828765'),
 BASE+'author-manifest.json':dict(bytes=86208,sha256='4bfd8b13053dfc3880e8190db329f8ce8c343b6c4137198b16c1133a57b9e979'),
 BASE+'publication-manifest.json':dict(bytes=5910,sha256='b75c189e30de5ab171e32559d069bc8211cfa65fb48fbce3b229eeb8a68b162c'),
 REPORT+'receipt.json':dict(bytes=64309,sha256='20286c76b9037200cb616c4571b5f185c7c531583a27a833ee0893e7f922a79e')}
def pin(b):return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def guard():
 class PMC(ctypes.Structure):
  _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(n,ctypes.c_size_t)for n in('pw','w','pp','p','pn','n','pf','ppf','private')]
 k=ctypes.WinDLL('kernel32');k.GetCurrentProcess.restype=ctypes.c_void_p;p=ctypes.WinDLL('psapi');c=PMC();c.cb=ctypes.sizeof(c)
 assert p.GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()),ctypes.byref(c),c.cb)
 assert max(c.private,c.ppf)<1024**3 and max(c.private,c.ppf)<=768*1024**2
 return max(c.private,c.ppf)
def read(n,phase,q=None):
 p=ROOT/n;assert p.resolve().is_relative_to(ROOT.resolve())and not n.startswith('work/deps/')and p.name.lower()!='eu4.exe'
 size=p.stat().st_size;assert size<=4*1024**2 and sum(e['bytes']for e in J)+size<=LIMIT;guard()
 raw=p.read_bytes();assert len(raw)==size;d=pin(raw);J.append(dict(path=n,phase=phase,**d))
 if q is not None:assert d==q
 return raw
def admit(n,q):
 if n in P:assert P[n]==q
 else:C[n]=read(n,'before',q);P[n]=q
def obj(n):return json.loads(C[n])
def write(n,x):
 b=(json.dumps(x,sort_keys=True,ensure_ascii=True,indent=2)+'\n').encode()
 with(OUT/n).open('xb')as f:f.write(b)
 return pin(b)
def triple(n):return dict(path=n,**P[n])
def main():
 OUT.mkdir(exist_ok=False)
 for n,q in HARD.items():admit(n,q)
 src=obj(BASE+'source-manifest.json');author=obj(BASE+'author-manifest.json');pub=obj(BASE+'publication-manifest.json');receipt=obj(REPORT+'receipt.json')
 for n in ['index.json','data-manifest.json','lineage-proof.json','reference-verification.json','budget.json','repair-record.json','repair-authorization.json']:
  admit(BASE+n,src['files'][BASE+n])
 for n in ['build-receipt.json','delivery.json']:
  q=author['files'][BASE+n]if BASE+n in author['files']else pub['files'][BASE+n]if BASE+n in pub['files']else pin(read(BASE+n,'delivery_exact_current'))
  admit(BASE+n,q)
 for i,r in enumerate(receipt['records']):
  admit(REPORT+f'{i:02d}.stdout.json',r['stdout']);admit(REPORT+f'{i:02d}.stderr.txt',r['stderr'])
 own=Path(__file__).relative_to(ROOT).as_posix();raw=read(own,'ownsource');P[own]=pin(raw);C[own]=raw
 assert len(obj(BASE+'index.json')['entries'])==60 and len(obj(BASE+'data-manifest.json')['sources'])==94
 assert src['selected_JSON_sources']==author['selected_JSON_sources']==94 and src['entry_count']==author['entry_count']==60
 assert receipt['passed']and receipt['error']is None and receipt['command_count']==4 and receipt['first_only_no_retries']and receipt['all_jobs_and_direct_children_collected']
 assert receipt['commands']==[['check'],['catalog'],['lookup','0x993570'],['lookup','0x97bd30']]
 values=[]
 for i,r in enumerate(receipt['records']):
  value=obj(REPORT+f'{i:02d}.stdout.json');job=r['job']
  assert job['exit_code']==0 and job['error']is None and job['job_active_processes_final']==0 and job['direct_child_collected']and 1<=job['job_total_processes']<=8
  assert not job['completed_command_descendants_terminated']and not C[REPORT+f'{i:02d}.stderr.txt']
  assert value['status']=='ok'and value['tool_revision']==6 and value['native_calls']==value['requests_published']==0
  values.append(dict(operation=value['operation'],count=value.get('count'),entry_count=value.get('entry_count'),ids=[x['id']for x in value.get('entries',[])],Job=job,provenance=value['provenance']))
 assert values[0]['entry_count']==60 and values[1]['count']==60 and values[2]['ids']==['peace.generator_divisor_source']and values[3]['ids']==['peace.generator_selector_callee']
 assert all(v['provenance']['selected_source_count']==94 and v['provenance']['source_guard_before_and_after']for v in values)
 build=obj(BASE+'build-receipt.json');repair=obj(BASE+'repair-record.json');budget=obj(BASE+'budget.json');delivery=obj(BASE+'delivery.json')
 assert build['failed_stage_completed_bytes']==3015196 and build['repair_stage_completed_bytes']==repair['repair_explicit_read_bytes']==70488 and build['explicit_completed_read_bytes']==6527447
 assert author['seal_completed_bytes']==7709113 and receipt['combined_physical_explicit_bytes']==30469489 and receipt['query_source_explicit_bytes']==4*5823301
 cumulative_upper=3015196+70488+6527447+7709113+2*1024**2+LIMIT
 assert cumulative_upper==21516548 and cumulative_upper<32*1024**2 and receipt['combined_physical_explicit_bytes']<64*1024**2
 assert budget['actual_selected_bytes_per_pass']==2886776 and budget['actual_query_explicit_read_bytes']==5823301
 refs=obj(BASE+'reference-verification.json');lineage=obj(BASE+'lineage-proof.json')
 assert refs['reference_count']==346 and refs['selected_JSON_sources']==94 and lineage['old58_dataequal']and lineage['old74pins_unchanged']and lineage['generator_oldfields_preserved_except_evidence_append']and not lineage['engine_forked']
 for n,q in P.items():read(n,'after',q)
 charged=sum(e['bytes']for e in J);assert charged<LIMIT
 completion=dict(schema='EU4-LOOKUP-V6-AUTHOR-COMPLETION/1',sealed=True,status='author_final_pending_non_author_full_review',
  canonical_source_manifest=triple(BASE+'source-manifest.json'),canonical_author_manifest=triple(BASE+'author-manifest.json'),canonical_publication_manifest=triple(BASE+'publication-manifest.json'),first_query_receipt=triple(REPORT+'receipt.json'),
  canonical_source_schema_keys=list(src),canonical_author_schema_keys=list(author),canonical_publication_schema_keys=list(pub),
  schema_precision='All three use files flat mappings; source manifest excludes itself; author includes exact source manifest, build receipt and first-query raw outputs; publication is a selected local/delivery subset plus author pin. No recursive history closure is claimed.',
  R81_five_JSON_pointer_lists=refs['R81_exact_pointer_lists'],query_results=values,old58_dataequal=True,old74pins_unchanged=True,generator_append_only=True,engine_reused_existing_ea030_path=True,entry_count=60,selected_JSON_sources=94,reference_count=346,
  first_build_failure=dict(stage='pre-index/source writing',reason='Own assertion wrongly required optional selected_effect_verified field on every legacy row',completed_read_bytes=3015196,source_and_fullfailure_preserved=True),
  root_approved_repair=dict(stage='builder-only core5 + present optional flags and cumulative bookkeeping',explicit_bytes=70488,attempts=1,engine_oldrows_unchanged=True,query_attempts_before_repair=0),
  build_R2_completed_bytes=6527447,seal_completed_bytes=7709113,build_manual_allowance_bytes=2*1024**2,final_delivery_limit_bytes=LIMIT,build_failure_repair_build_seal_delivery_upper_bytes=cumulative_upper,build_seal_limit_bytes=32*1024**2,
  final_delivery_completed_bytes=charged,query_batch_explicit_bytes=30469489,query_batch_limit_bytes=64*1024**2,actual_query_source_bytes=4*5823301,query_controller_explicit_bytes=receipt['controller_explicit_bytes'],
  own_final_peak=guard(),all_shells_collected=True,tool_receipts=[dict(stage='first_build',chunk='79c741',exit_code=1),dict(stage='repair_prepare',chunk='524c64',exit_code=0),dict(stage='builder_R2',chunk='0e0a46',exit_code=0),dict(stage='first_four_queries',chunk='af4c71',exit_code=0),dict(stage='retained_seal',chunk='d5b352',exit_code=0)],
  source_pins_before_after_equal=True,no_queries_repeated=True,no_old_programs_tests_fixtures_PE_native_decoder_game_native_install_package_publication=True,independent_review_passed=False,
  limits=['Author final is not non-author acceptance or public capability-map publication.','No type/fullhandle/bounds/termination/lifetime/units/recipient/peace effect is established.','Explicit source bills are not all OS/interpreter/loader IO; Job receipts are actual new first-query witnesses only.'],authority=src['authority'])
 cp=write('completion.json',completion)
 write('read-accounting.json',dict(schema='EU4-LOOKUP-V6-DELIVERY-READ-BILL/1',events=J,completed_bytes=charged,limit=LIMIT,included_in_build_seal_upper=True,full_OS_IO_claimed=False))
 files=dict(P)
 for n in ['completion.json','read-accounting.json']:
  b=(OUT/n).read_bytes();files[(OUT/n).relative_to(ROOT).as_posix()]=pin(b)
 mp=write('manifest.json',dict(schema='EU4-LOOKUP-V6-AUTHOR-DELIVERY-MANIFEST/1',sealed=True,files=files,file_count=len(files),completion_pin=cp,independent_review_passed=False,authority=src['authority']))
 print(json.dumps(dict(status='author_delivery_frozen',completion=cp,manifest=mp,final_delivery_completed_bytes=charged,cumulative_build_seal_upper=cumulative_upper,all_shells_collected=True)))
if __name__=='__main__':
 try:main()
 except BaseException:
  if OUT.exists():
   with(OUT/'failure.json').open('x',encoding='utf-8')as f:json.dump(dict(traceback=traceback.format_exc(),reads=J,bytes=sum(e['bytes']for e in J),no_command_rerun=True),f,indent=2)
  raise
