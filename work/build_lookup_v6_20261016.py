"""Root-authorized v6 file-only build. No query, old program, PE or native decoder."""
import ast,copy,ctypes,hashlib,json,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'work/candidates/war-peace-api-lookup-1375-v6'
V5='work/candidates/war-peace-api-lookup-1375-v5/'
PLAN='work/reports/war-peace-api-lookup-v6-plan-20261016-r2/'
GRANT='work/reports/war-peace-api-lookup-v6-root-authorization-20261016-r2/'
GAME='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
ENGINE='ea030ce19461b2e414e0cdbc42f4933551fa9e654f7a7a43db948670b27fa466'
JOB='work/candidates/frida-entry-observer-1375-v1/job_tree.py'
JOBPIN={'bytes':8615,'sha256':'5fca5b41161829a15554b08371e3fc64765164479e41bda015fec910972e9011'}
FILE=4*1024**2;LIMIT=32*1024**2;MANUAL=2*1024**2;SEAL_RESERVE=16*1024**2
P={};C={};READS=[]
FLAGS=('callable','native_ready','sender_authorized','gameplay_effect_verified','process_authenticated','selected_effect_verified','world_lease','atomic_snapshot','authorizes_retry')

RUNNER=r'''"""First four v6 queries only; no fixtures or old query re-execution."""
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
 rp=write('receipt.json',receipt);print(json.dumps(dict(passed=error is None,receipt=rp,combined_physical=physical,error=error,self_peak_bytes=peak)));return0=0 if error is None else2
 return return0
if __name__=='__main__':raise SystemExit(main())
'''.replace('else2','else 2')

SEALER=r'''"""Retained-only v6 final author sealing, not independent acceptance."""
import ctypes,hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
REPORT=ROOT/'work/reports/war-peace-api-lookup-v6-first-queries-20261016-r1'
reads=[];peak=0;LIMIT=16*1024**2;FILE=4*1024**2
class PMC(ctypes.Structure):
 _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(n,ctypes.c_size_t)for n in('pw','w','pp','p','pn','n','pf','ppf','private')]
k=ctypes.WinDLL('kernel32');k.GetCurrentProcess.restype=ctypes.c_void_p;p=ctypes.WinDLL('psapi')
def guard():
 global peak
 c=PMC();c.cb=ctypes.sizeof(c);assert p.GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()),ctypes.byref(c),c.cb)
 peak=max(peak,c.private,c.ppf);assert peak<1024**3 and peak<=768*1024**2
def pin(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def read(path):
 guard();assert path.resolve().is_relative_to(ROOT.resolve());size=path.stat().st_size;assert size<=FILE and sum(x['bytes']for x in reads)+size<=LIMIT
 raw=path.read_bytes();assert len(raw)==size;reads.append(dict(path=path.relative_to(ROOT).as_posix(),**pin(raw)));return raw
def write(n,d):
 raw=(json.dumps(d,ensure_ascii=True,indent=2,sort_keys=True)+'\n').encode();assert len(raw)<=FILE
 with(HERE/n).open('xb')as f:f.write(raw)
 return pin(raw)
def main():
 assert len(sys.argv)==3;expected=dict(bytes=int(sys.argv[1]),sha256=sys.argv[2])
 write('seal-claim.json',dict(schema='EU4-LOOKUP-V6-SEAL-CLAIM/1',source_manifest=expected,no_repeated_query=True))
 raw=read(HERE/'source-manifest.json');assert pin(raw)==expected;m=json.loads(raw)
 pins=dict(m['files']);pins['work/candidates/war-peace-api-lookup-1375-v6/source-manifest.json']=expected
 for n,q in pins.items():assert pin(read(ROOT/n))==q
 receipt_raw=read(REPORT/'receipt.json');receipt=json.loads(receipt_raw)
 assert receipt['passed']and receipt['error']is None and receipt['command_count']==4 and receipt['first_only_no_retries']and receipt['all_jobs_and_direct_children_collected']
 for n in ['claim.json','receipt.json',*[f'{i:02d}.{suffix}'for i in range(4)for suffix in('stdout.json','stderr.txt')]]:
  path=REPORT/n;pins[path.relative_to(ROOT).as_posix()]=pin(read(path))
 for n in ['build-receipt.json','source-manifest.json','seal-claim.json']:
  path=HERE/n;pins[path.relative_to(ROOT).as_posix()]=pin(read(path))
 for n,q in pins.items():assert pin(read(ROOT/n))==q
 own_measured=sum(x['bytes']for x in reads)
 author=dict(schema='EU4-LOOKUP-V6-AUTHOR-MANIFEST/1',sealed=True,status='author_final_pending_non_author_full_review',files=pins,file_count=len(pins),source_manifest=expected,
  first_query_receipt=dict(path=(REPORT/'receipt.json').relative_to(ROOT).as_posix(),**pin(receipt_raw)),selected_JSON_sources=94,entry_count=60,
  source_pins_before_after_equal=True,query_calls=4,no_retry=True,independent_review_passed=False,native_ready=False,authority=m['authority'],
  resource_scope='flat explicit owned-source reads; not OS/loader IO or native decoder work',seal_read_journal=reads,seal_completed_bytes=own_measured,seal_budget_bytes=LIMIT,self_peak_bytes=peak)
 ap=write('author-manifest.json',author)
 pubpins={'work/candidates/war-peace-api-lookup-1375-v6/author-manifest.json':ap,**{n:q for n,q in pins.items()if n.startswith('work/candidates/war-peace-api-lookup-1375-v6/')or n.startswith('work/reports/war-peace-api-lookup-v6-first-queries-')}}
 pp=write('publication-manifest.json',dict(schema='EU4-LOOKUP-V6-PUBLICATION-MANIFEST/1',sealed=True,status='research_candidate_not_published',files=pubpins,file_count=len(pubpins),full_author_manifest=ap,independent_review_passed=False,authority=m['authority']))
 upper=own_measured+2*1024**2
 write('delivery.json',dict(schema='EU4-LOOKUP-V6-AUTHOR-DELIVERY/1',sealed=True,source_manifest=expected,author_manifest=ap,publication_manifest=pp,first_query_receipt=pin(receipt_raw),
  source_schema_keys=list(m),author_schema_keys=list(author),publication_schema='files flat map, no recursive source expansion',selected_JSON_sources=94,entry_count=60,
  seal_completed_read_bytes=own_measured,remaining_delivery_check_reserve_bytes=2*1024**2,seal_successful_upper_bytes=upper,seal_limit=LIMIT,
  build_seal_budget=32*1024**2,query_batch_completed_bytes=receipt['combined_physical_explicit_bytes'],query_limit=64*1024**2,all_shells_collected=True,author_not_independent=True,authority=m['authority']))
 assert upper<=LIMIT
 print(json.dumps(dict(status='sealed_author_pending_review',author_manifest=ap,publication_manifest=pp,seal_completed_bytes=own_measured,self_peak_bytes=peak,all_shells_collected=True)))
if __name__=='__main__':main()
'''

def need(v,m):
 if not v:raise AssertionError(m)
def memory():
 class PMC(ctypes.Structure):
  _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(x,ctypes.c_size_t)for x in('pw','w','pp','p','pn','n','pf','ppf','private')]
 k=ctypes.WinDLL('kernel32');k.GetCurrentProcess.restype=ctypes.c_void_p;p=ctypes.WinDLL('psapi');c=PMC();c.cb=ctypes.sizeof(c)
 need(p.GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()),ctypes.byref(c),c.cb),'self memory')
 peak=max(c.private,c.ppf);need(peak<=768*1024**2 and peak<1024**3,'own memory limit');return peak
def pin(b):return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def read(n,phase='before',expected=None):
 p=(ROOT/n).resolve();need(p.is_relative_to(ROOT)and not p.relative_to(ROOT).as_posix().startswith('work/deps/')and p.name.lower()!='eu4.exe','admitted file only')
 size=p.stat().st_size;need(size<=FILE and sum(x['bytes']for x in READS)+size+MANUAL+SEAL_RESERVE<=LIMIT,'build preread budget')
 memory();b=p.read_bytes();q=pin(b);READS.append(dict(path=p.relative_to(ROOT).as_posix(),phase=phase,**q));need(len(b)==size,'stable size')
 if expected is not None:need(q=={k:expected[k]for k in('bytes','sha256')},'exact pin '+str(n))
 return b
def admit(n,p):
 n=(ROOT/n).resolve().relative_to(ROOT).as_posix();p={k:p[k]for k in('bytes','sha256')}
 if n in P:need(P[n]==p,'pin consistent')
 else:C[n]=read(n,expected=p);P[n]=p
def obj(n):return json.loads(C[n])
def save(n,d):
 b=(json.dumps(d,sort_keys=True,ensure_ascii=True,indent=2)+'\n').encode();need(len(b)<=FILE,'output filecap')
 with(OUT/n).open('xb')as f:f.write(b)
 return pin(b)
def text(n,s):
 b=s.encode();need(len(b)<=FILE,'text cap')
 with(OUT/n).open('xb')as f:f.write(b)
 return pin(b)
def canonical(d):return hashlib.sha256(json.dumps(d,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
def pointer(d,ps):
 for k in ps.split('/')[1:]:k=k.replace('~1','/').replace('~0','~');d=d[int(k)]if isinstance(d,list)else d[k]
 return d
def main():
 need(sys.argv[1:]==[],'fixed build only');OUT.mkdir(exist_ok=False)
 for n,q in [('authorization.json',dict(bytes=6779,sha256='6ff710b74288f303a01df3049aab67901d49f7f1f2fbcfe0a0423251ce237de5')),('receipt.json',dict(bytes=6648,sha256='e2eb2bdad426c40d08d2ba958e7ab24d4f0819ea829bd6c85e1262586949f7fc'))]:admit(GRANT+n,q)
 grant=obj(GRANT+'authorization.json');need(grant['owner']=='/root/war_api'and grant['plan_revision']==2 and grant['exclusive_claim_required_before_build'],'exact build grant')
 save('build-claim.json',dict(schema='EU4-LOOKUP-V6-BUILD-CLAIM/1',authorization=P[GRANT+'authorization.json'],single_build=True,no_query_run_yet=True,no_retry=True))
 for n,q in grant['accepted_fixed_inputs'].items():admit(n,q)
 plan=obj(PLAN+'plan.json');need(plan['stage'].startswith('author_planning')and plan['planned_scope']['result_entry_count_if_ready']==60,'accepted plan')
 # Explicit proposal inputs only, not its transitive manifest graph.
 planmanifest=obj(PLAN+'manifest.json')
 for n in ['source-inventory.json','reference-plan.json','old-entry-preservation.json']:admit(PLAN+n,planmanifest['source_pins'][PLAN+n])
 inventory=obj(PLAN+'source-inventory.json');refsplan=obj(PLAN+'reference-plan.json');proof=obj(PLAN+'old-entry-preservation.json')
 for n,q in inventory['current_new15_sources'].items():admit(n,q)
 roles=obj('work/reports/war-peace-api-20261016-r81-actual-independent-review/lookup-source-roles.json')['roles']
 need(roles==grant['accepted_R81_five_roles']and len(roles)==5,'exact accepted R81roles')
 for v in roles.values():admit(v['path'],v)
 oldindex=obj(V5+'index.json');olddata=obj(V5+'data-manifest.json');sources=copy.deepcopy(olddata['sources'])
 need(len(sources)==74 and sources==inventory['old74_JSON_source_pins_unchanged'],'old74 fixed')
 sources.update(inventory['current_new15_sources']);sources.update({v['path']:{k:v[k]for k in('bytes','sha256')}for v in roles.values()});need(len(sources)==94,'exact94sources')
 for n,q in sources.items():admit(n,q)
 admit(JOB,JOBPIN)
 own=Path(__file__).relative_to(ROOT).as_posix();raw=read(own);P[own]=pin(raw);C[own]=raw
 for group in ('independent_full_findings',):
  f=obj(roles[group]['path']);need(f['sealed']and f['passed']and f['blocking_findings']==[],'R81full gate')
  for k,role in [('subject_actual_manifest','author_actual_manifest'),('subject_contract_pin','author_contract'),('subject_selected_pin','author_selected_evidence')]:need(f[k]==roles[role],'R81five role binding')
 index=copy.deepcopy(oldindex);rows=index['entries'];gen=next(e for e in rows if e['rva']=='0x993570');oldgen=copy.deepcopy(gen)
 grouprefs=[dict(r)for r in refsplan['references']if '20261016-r75-'in r['path']or'20261016-r77-'in r['path']]
 need(len(set(x['path']for x in grouprefs))==10,'R75/R77 ten direct sources')
 r75='work/reports/war-peace-api-20261016-r75-null-successor-fragment/actual-contract.json';r77='work/reports/war-peace-api-20261016-r77-fragment-composition/contract.json'
 gen['later_checked_context']=[dict(report='R75',scope='later NULL-return successor, not independent API',condition='97bd30 returns0 and inherited valid normal frame/nonvolatile/alias premises; no reset to new formals.',projection=obj(r75)['return_register_contract'],stack=obj(r75)['stack_contract'],unknown=obj(r75)['unknowns']),dict(report='R77',scope='later conditional R69/R71/R73/R75 composition, not wholefunction proof',conditions=obj(r77)['normal_conditions'],cases=obj(r77)['conditional_cases'],unknown=obj(r77)['unresolved'])]
 gen['historical_base_scope']=dict(version=5,base_row_canonical_sha256=canonical(oldgen),original_fields='All old fields, signature/summary/unresolved/later_conditional_context remain v5 historical evidence; later_checked_context supplements limited earlier unknowns under independent conditions.',R79_direct_context_added=False)
 gen['evidence'].extend(grouprefs)
 old80='work/reports/war-peace-api-20261016-r80-unregistered-call-prefix/';rev80='work/reports/war-peace-api-20261016-r80-actual-independent-review-r3/'
 newrefs=[dict(r)for r in refsplan['references']if r['path'].startswith(old80)or r['path'].startswith(rev80)]
 rp={roles['author_actual_manifest']['path']:['/files','/authority','/engine_witness_only_not_rehashed_by_sealer'],roles['author_contract']['path']:['/observations','/conditional_projection','/normal_CFG','/unknowns','/resources','/authority'],roles['author_selected_evidence']['path']:['/all17_raw_reviewed_rows','/branch_signed_rel8_arithmetic','/normal_model_terminals','/retained_unreached_suffix'],roles['independent_full_findings']['path']:['/passed','/subject_actual_manifest','/subject_capture_pin','/subject_contract_pin','/subject_owned_pin','/subject_selected_pin','/machine_projection','/limits'],roles['independent_full_manifest']['path']:['/files','/subject_actual_manifest','/engine_metadata_only']}
 for n,ps in rp.items():
  for ps1 in ps:newrefs.append(dict(path=n,json_pointer=ps1,**sources[n]))
 entry=dict(id='peace.generator_selector_callee',rva='0x97bd30',kind='function',stage='static',actions=['peace'],title='Opaque selector callee: known CALL entry and conditional search returns',
  summary='Known CALL97bd30: R80 prefix loads two truncated indices through module233d8d0 and selected pointers. R81 continuation searches16B records by DWORD key and returns firstmatching QWORD+8 or0; matching value can also0. Bounds/type/units/recipient/effect unknown.',
  stage_scope='Fixed retained machine evidence and later continuation only. No native execution, authenticated current roots, fullfunction extent/class/prototype or gameplay acceptance.',
  scope_kind='known_CALL_entry_selected_prefix_with_later_continuation',signature=dict(complete_prototype='unknown',status='partial_static',parameters=['RCX opaque entry pointer: selected prefix readsQWORD+18/+10; two bits32..47 indices use distinct sign-extension widths.','IncomingRDX/originalD and incomingR8/header are overwritten before selected address use; aliases to loaded pointers/stack remain unknown.','R9/XMM/formal semantic types are not inferred; selected R9 is a load-derived register, not an authenticated input role.'],returns='Conditional valid stable range/nonnegativeN traversal: firstDWORDkey-match returns QWORDrecord+8, otherwise0; value0 can be a real match. No pointer type/ownership, amount or Boolean contract.'),
  ownership=dict(owned=['No allocation/free/retained ownership is established; returnedQWORD may0 and its type/lifetime are unknown.'],borrowed=['Opaque entry/pointer-chain data and inherited controlstack; no bounds, alias-disjointness, class, world lease or stable allocation proof.']),
  call_sites=[dict(rva='0x99358a',relationship='Inherited retainedE8a187feff signedrel32 target97bd30; known CALL entry only.')],aliases=['opaque selector callee','selector DWORD key','97bd30 conditional return'],evidence=newrefs,
  unresolved=['Actual function extent/unwind registration/class/complete prototype unknown; R80/R81 local normal paths do not establish wholefunction identity.','No negative-count/capacity/fullhandle/generation/type/lifecycle/endpoint or key uniqueness guards; valid stable range and finite traversal are extra premises.','OriginalD/header final contents, alias and CALL-stack integrity/lifetime remain unknown; no current process/world authentication.','Units/currency/recipient weights/settlement/request-session/peace effects and persistence remain unknown.','R80 historical partial/noRET and R79 bounded pdata-miss files are unchanged; later R81 context supplements selected returns only.'],
  owned_ranges=[dict(window=['0x97bd30','0x97bd70'],bytes=64,role='R80 prefix:62decoded+2partial historical evidence'),dict(window=['0x97bd6e','0x97bda0'],bytes=50,role='R81 cached2+new48 continuation:46decoded+4ownedCC not decoded')],
  range_accounting=dict(unique_owned_bytes=112,overlap_bytes=2,complete_decoded_unique_bytes=108,complete_rows=30,unreached_owned_CC_bytes=4,new_R81_targeted_bytes=48),
  later_conditional_context=dict(report='R81',independent_Win64_entry=False,local_normal_CFG_closed=True,unconditional_termination=False,conditions='Inherited R80 GP, valid normal controlstack and valid stable range; nonnegativeN for finite N-record interpretation.',K='zext64(sext16_to32((currentRAX>>32)&ffff))',B='M64[currentR8+50]',N='signed32(M32[currentR8+5c])',end='B+16N modulo64',returns=['RET97bd96 RAX0 on empty/end','RET97bd9b RAX=M64[firstDWORDmatch+8], may0']),whole_function_closed=False,**{k:False for k in FLAGS})
 rows.append(entry);rows.sort(key=lambda x:x['id']);need(len(rows)==60,'60entries')
 lineage=[]
 for old in oldindex['entries']:
  current=next(e for e in rows if e['id']==old['id'])
  if old['id']!=gen['id']:need(current==old,'old58strict dataequal')
  else:
   for key,value in old.items():need((current[key][:len(value)]==value)if key=='evidence'else current[key]==value,'generator oldfield exact '+key)
   need(set(current)-set(old)=={'later_checked_context','historical_base_scope'},'only2appendkeys')
  lineage.append(dict(id=old['id'],old_canonical_sha256=canonical(old),preserved=True))
 used=set();resolved=[]
 for row in rows:
  need(all(row[k]is False for k in FLAGS),'falseauthority')
  for r in row['evidence']:
   need({k:r[k]for k in('bytes','sha256')}==sources[r['path']],'ref pin agrees')
   value=pointer(obj(r['path']),r['json_pointer']);used.add(r['path']);resolved.append(dict(entry=row['id'],path=r['path'],json_pointer=r['json_pointer'],canonical_value_sha256=canonical(value)))
 need(used==set(sources),'all94 directly referenced')
 ip=save('index.json',index);data=dict(schema=olddata['schema'],version=olddata['version'],game_sha256=GAME,scope=olddata['scope'],index=ip,sources=sources);dp=save('data-manifest.json',data)
 oldwrapper=C[V5+'war_peace_lookup.py'].decode();newwrapper=oldwrapper.replace(olddata_hash:=P[V5+'data-manifest.json']['sha256'],dp['sha256']).replace('tool_revision=5','tool_revision=6').replace('revision 5;','revision 6;')
 need(oldwrapper.count(olddata_hash)==1 and oldwrapper.count('tool_revision=5')==2 and oldwrapper.count('revision 5;')==1,'exact wrapper metadata occurrences')
 text('war_peace_lookup.py',newwrapper)
 treeold=ast.parse(oldwrapper);treenew=ast.parse(newwrapper)
 for n in treeold.body:
  if isinstance(n,(ast.FunctionDef,ast.ClassDef))and n.name in ('base_bytes','engine','Parser'):
   counterpart=next(x for x in treenew.body if type(x)is type(n)and x.name==n.name);need(ast.dump(n,include_attributes=False)==ast.dump(counterpart,include_attributes=False),'unchangedguard/parserAST')
 need(P[V5+'query_engine.py']==dict(bytes=16583,sha256=ENGINE),'existing queryengine exact, no copy')
 text('run_first.py',RUNNER);text('seal_candidate.py',SEALER);ast.parse(RUNNER);ast.parse(SEALER)
 save('lineage-proof.json',dict(schema='EU4-LOOKUP-V6-LINEAGE/1',old58_dataequal=True,generator_oldfields_preserved_except_evidence_append=True,allowed_newkeys=['later_checked_context','historical_base_scope'],old74pins_unchanged=True,old59rows=lineage,engine_reused_existing_path=V5+'query_engine.py',engine_pin=P[V5+'query_engine.py'],engine_forked=False,wrapper_metadata_replacements=['DATA_SHA','two tool_revision5to6','help revision5to6'],guard_parser_engine_AST_equal=True,old_files_modified=False))
 save('reference-verification.json',dict(schema='EU4-LOOKUP-V6-REFS/1',selected_JSON_sources=94,entry_count=60,reference_count=len(resolved),resolved=resolved,R81_exact_pointer_lists=rp,old74pins=sources.keys()>=olddata['sources'].keys(),all_sources_used=True))
 perpass=dp['bytes']+ip['bytes']+sum(q['bytes']for q in sources.values());perquery=2*perpass+3*16583
 budget=dict(schema='EU4-LOOKUP-V6-BUDGET/1',build_seal_limit=LIMIT,query_batch_limit=64*1024**2,ordinary_limit=FILE,memory_software_limit=768*1024**2,one_GiB_stop=True,build_manual_allowance=MANUAL,seal_reserved_bytes=SEAL_RESERVE,
  actual94_source_bytes=sum(q['bytes']for q in sources.values()),actual_index_bytes=ip['bytes'],actual_data_bytes=dp['bytes'],actual_selected_bytes_per_pass=perpass,actual_query_explicit_read_bytes=perquery,
  fourquery_explicit_bytes=4*perquery,controller_source_output_allowance=12*1024**2,fourquery_plus_controller_upper_bytes=4*perquery+12*1024**2,Python_engine_pin_reads_per_query=3,
  aggregate32M_is_successful_acceptance_not_OS_failedread_bound=True,PE_native_decoder_game=0)
 need(budget['fourquery_plus_controller_upper_bytes']<64*1024**2,'actual batch bound before queries');save('budget.json',budget)
 text('README.md','EU4 1.37.5 offline war/peace API evidence lookup v6\n\n60 records/94 fixed JSON sources; research-only, all callable/native-ready/effect/lease flags false. Existing v5 Python query engine ea030 is reused by exact original path. Original58 rows remain dataequal; generator old fields remain historical v5 scope with R75/R77 later contexts appended. One new97bd30 known-CALL record carries R80/R81 conditional machine dataflow/search returns, not class, full function or gameplay API completion.\n\nExamples (first four controlled queries are preserved separately): check; catalog; lookup0x993570; lookup0x97bd30. No PE/process/native sender/Frida or installation. Source/data checks occur before and after every query. RVA-to-VA, if requested, is conditional arithmetic only. Non-author v6 review is pending; this directory is not a public capability map or release.\n')
 for n,q in list(P.items()):read(n,'after',q)
 completed=sum(x['bytes']for x in READS);need(completed+MANUAL+SEAL_RESERVE<LIMIT,'build+reservedseal32M')
 snapshot=dict(P)
 for n in ['index.json','data-manifest.json','war_peace_lookup.py','run_first.py','seal_candidate.py','lineage-proof.json','reference-verification.json','budget.json','README.md','build-claim.json']:
  rel=(OUT/n).relative_to(ROOT).as_posix();snapshot[rel]=pin(read(rel,'new_frozen_source'))
 sm=save('source-manifest.json',dict(schema='EU4-LOOKUP-V6-SOURCE-MANIFEST/1',sealed=True,status='source_frozen_pending_non_author_review',files=snapshot,selected_JSON_sources=94,entry_count=60,game_sha256=GAME,native_ready=False,callable=False,independent_review_passed=False,authority={x:False for x in FLAGS},build_analysis_budget=LIMIT,first_query_batch_budget=64*1024**2,dependency_scope='flat exact selectedJSON/query/source/auth/plan pins only; no recursive historical engine closure'))
 save('build-receipt.json',dict(schema='EU4-LOOKUP-V6-BUILD-RECEIPT/1',sealed=True,author_build_only=True,source_manifest=sm,index=ip,data_manifest=dp,entry_count=60,JSONsource_count=94,reference_count=len(resolved),old58equal=True,generator_append_only=True,old74pinsunchanged=True,source_before_after_equal=True,
  explicit_read_journal=READS,explicit_completed_read_bytes=sum(x['bytes']for x in READS),manual_allowance=MANUAL,seal_reserve=SEAL_RESERVE,build_plus_seal_prequery_upper_bytes=sum(x['bytes']for x in READS)+MANUAL+SEAL_RESERVE,limit=LIMIT,self_peak_witness=memory(),new_query_count=0,old_programs_tests_fixtures_PE_decoder_game_native=0,all_shells_collected=True,authority={x:False for x in FLAGS}))
 print(json.dumps(dict(status='source_frozen_pending_review_queries_not_run',source_manifest=sm,index=ip,data_manifest=dp,entries=60,sources=94,reference_count=len(resolved),perpass=perpass,perquery=perquery,query_batch_upper=budget['fourquery_plus_controller_upper_bytes'],build_completed_bytes=sum(x['bytes']for x in READS))))
if __name__=='__main__':
 try:main()
 except BaseException:
  if OUT.exists():
   with(OUT/'build-failure.json').open('x',encoding='utf-8')as f:json.dump(dict(traceback=traceback.format_exc(),read_journal=READS,completed_bytes=sum(x['bytes']for x in READS),no_queries_run_by_builder=True),f,indent=2)
  raise
