"""Author file-only v5 inventory/build. All old candidates/evidence remain read-only."""
import ast,ctypes,hashlib,json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
V4='work/candidates/war-peace-api-lookup-1375-v4/'
V5='work/candidates/war-peace-api-lookup-1375-v5/'
OUT=ROOT/V5;REPORT=ROOT/'work/reports/war-peace-api-lookup-v5-preparation-20261016-r1'
LIMIT=32*1024*1024;FILE=4*1024*1024;reads=[];peak=0
GAME='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
ENGINE='work/candidates/war-peace-api-lookup-1375-v1/war_peace_lookup.py'
ENGINE_PIN=dict(bytes=16583,sha256='d4237d98c58e89be9419ff736f01d97f5fde0129c07c5c7f778baf010071746e')
JOB='work/candidates/frida-entry-observer-1375-v1/job_tree.py'
V4PINS={
'source-manifest.json':(16303,'65760adaec1a818d8cefa1b29dafd42ca77bd04202e5c8bf00100aa477fcf97e'),
'data-manifest.json':(11680,'31325f2fb4b60025107a5ef0521edc9d4ab419b1fa0bac8e809a382a335d8fe1'),
'index.json':(171988,'b1428fb60dae03c9857beef8269c61723c9ff7ba0edbaedfadfe67ac3d94011b'),
'war_peace_lookup.py':(3606,'ee60c332fec94ce321acb10e5917ce94369d089a0ceb313d1229781ecfe99c14')}
NEW={
'work/reports/war-peace-api-20261016-r69-generator-divisor-source/manifest.json':(27579,'3ca9f6aff9c0ceffd0d0096a4ace1a1f7ff294b36acb0f88ed0c3a0f9f9ec69b'),
'work/reports/war-peace-api-20261016-r69-generator-divisor-source/contract.json':(7825,'cf685af0d0287802ed06d830e804ee12c75865c4b527b3a676f3950cc96ef6cc'),
'work/reports/war-peace-api-20261016-r69-generator-divisor-source/selected-evidence.json':(19444,'e3f4d304acf93f674ec407c4cfdd330a5163ea8e328bc6a8afe5deab893a237f'),
'work/reports/war-peace-api-20261016-r69-actual-independent-review/findings.json':(6300,'529f00a30baeba2c1f600018455c1e050f6061429951da8ce2daf9c44de17f56'),
'work/reports/war-peace-api-20261016-r69-actual-independent-review/manifest.json':(13503,'bceee11bb0cc11bb648d0b2e8d65b9862df971ecc10e161118ee762e3acf8058'),
'work/reports/war-peace-api-20261016-r71-divisor-fallthrough-fragment/actual-manifest.json':(24771,'df5a1d0e3918347ff95d7199b184adefed4a816b2f08dc3dd2bba4576823777f'),
'work/reports/war-peace-api-20261016-r71-divisor-fallthrough-fragment/actual-contract.json':(12229,'3d370deb33fc006ecb8a0cee93e8744bc112da8fffe66154afee3dfe9f92ff98'),
'work/reports/war-peace-api-20261016-r71-divisor-fallthrough-fragment/actual-selected-evidence.json':(41810,'12f1041c5d62da5d28fa9234e06e7081b3a2a73ad028ad83219e17a22917e5ae'),
'work/reports/war-peace-api-20261016-r71-actual-independent-review/findings.json':(8035,'40dbb7199f02244bcf1f95dba475db87171a81e226b7e0238004f788312cb045'),
'work/reports/war-peace-api-20261016-r71-actual-independent-review/manifest.json':(12660,'9bcd6706361cb07936763b868f9f384e399194f4900f774ef91fe042c2eb3a96'),
'work/reports/war-peace-api-20261016-r73-divisor-nonpositive-fragment/actual-manifest.json':(24623,'a5eb1ebbfe46c9d590aa118729a330499a226d828458248c45530ada0feb987b'),
'work/reports/war-peace-api-20261016-r73-divisor-nonpositive-fragment/actual-contract.json':(13212,'5eb88b02b2a454104799c18703af2f7fdf3487e507661f6af6cad013ceb41857'),
'work/reports/war-peace-api-20261016-r73-divisor-nonpositive-fragment/actual-selected-evidence.json':(8070,'724057630e576f976d48ad6e3044cdbdde7d0359e98bfd27f992f285cb680eea'),
'work/reports/war-peace-api-20261016-r73-actual-independent-review/findings.json':(5251,'5794b82df03b9fd1f407d3384f81fb366349f6cc7133c010f50d2206cfa2fd88'),
'work/reports/war-peace-api-20261016-r73-actual-independent-review/manifest.json':(18044,'49d74153ee25a06a54fa03cb3711647e7fa5939a19a9183f4e7c4cc03f416afb')}
FLAGS=('callable','native_ready','sender_authorized','gameplay_effect_verified','process_authenticated','selected_effect_verified','world_lease','atomic_snapshot','authorizes_retry')
class PMC(ctypes.Structure):
 _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(x,ctypes.c_size_t)for x in('pw','w','pp','p','pn','n','pf','ppf','private')]
k=ctypes.WinDLL('kernel32',use_last_error=True);k.GetCurrentProcess.restype=ctypes.c_void_p;p=ctypes.WinDLL('psapi',use_last_error=True)
def guard():
 global peak
 c=PMC();c.cb=ctypes.sizeof(c);assert p.GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()),ctypes.byref(c),c.cb)
 peak=max(peak,c.pw,c.ppf,c.private);assert peak<1024*1024*1024 and peak<=768*1024*1024
def pin(r):return dict(bytes=len(r),sha256=hashlib.sha256(r).hexdigest())
def pairs(v):
 d={}
 for a,b in v:
  if a in d:raise ValueError('duplicate_key')
  d[a]=b
 return d
def decode(r):return json.loads(r.decode('utf-8'),object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in()).throw(ValueError(x)))
def read(path,q=None):
 guard();assert not path.startswith('work/deps/')and not path.lower().endswith(('.exe','.dll','.pyd','.whl'))
 f=ROOT/path;a=f.stat();assert a.st_size<=FILE;r=f.read_bytes();z=f.stat();assert(len(r),a.st_size,a.st_mtime_ns)==(z.st_size,z.st_size,z.st_mtime_ns)
 if q:assert pin(r)==q,path
 reads.append(dict(path=path,**pin(r)));assert sum(x['bytes']for x in reads)<LIMIT;return r
def write(path,value,text=False):
 r=value.encode('utf-8')if text else(json.dumps(value,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode()
 assert len(r)<=FILE
 with(ROOT/path).open('xb')as f:f.write(r)
 return pin(r)
def intake():
 OUT.mkdir(exist_ok=False);REPORT.mkdir(exist_ok=False);files={}
 def take(path,q):
  if path in files:assert {k:files[path][k]for k in('bytes','sha256')}==q
  else:
   r=read(path,q);files[path]=dict(**q,text=r.decode('utf-8'))
 for name,(n,h)in V4PINS.items():take(V4+name,dict(bytes=n,sha256=h))
 source=decode(files[V4+'source-manifest.json']['text'].encode());data=decode(files[V4+'data-manifest.json']['text'].encode());index=decode(files[V4+'index.json']['text'].encode())
 assert len(index['entries'])==58 and len(data['sources'])==59 and len(source['files'])==82
 assert all(int(row['rva'],16)!=0x993570 for row in index['entries'])
 assert source['files'][ENGINE]==ENGINE_PIN;take(ENGINE,ENGINE_PIN);take(JOB,source['files'][JOB])
 for path,q in data['sources'].items():take(path,q)
 assert not set(NEW)&set(data['sources'])
 for path,(n,h)in NEW.items():take(path,dict(bytes=n,sha256=h))
 assert len(NEW)==15
 inv=dict(schema='EU4-LOOKUP-V5-LOCKED-SOURCE-INVENTORY/1',sealed=True,old_data_manifest=pin(files[V4+'data-manifest.json']['text'].encode()),old_JSON_sources=data['sources'],new_direct_JSON_sources={path:dict(bytes=n,sha256=h)for path,(n,h)in NEW.items()},
  old58_RVA_absence_993570_checked=True,old59_plus_new15=74,graph_is_flat_not_recursive=True,source_inventory_pins={path:{k:e[k]for k in('bytes','sha256')}for path,e in files.items()},
  new_entry_only='0x993570 known entry, selected55B prefix; later R71/R73 conditional fragments are not independent Win64 APIs',
  root_source_guard_delta_authorization='Parent explicitly approved new independent Python queryengine copy: only sources<=64 changes to<=96. Oldd423/v1-v4 frozen. WrapperBASEpath/SHA plusDATA_SHA/revision/help may update; other semantics retain.',
  operations=dict(PE=0,Capstone=0,game=0,native=0,old_programs_or_tests=0),authority={x:False for x in FLAGS})
 ip=write(V5+'source-inventory.json',inv)
 cache=write(V5+'build-inputs.json',dict(files=files))
 failure=write(V5+'initial-inspection-failure.json',dict(sealed=True,scope='manual source inventory before any v5 build/query execution',type='UnicodeDecodeError',
  reason='One ad hoc inspection called pathlib.read_text without UTF8 on frozen v4 builder; default GBK failed. V4 source guard manifest read had succeeded; no old builder/CLI was run.',
  affected_source=V4+'build_index.py',bytes_from_fixed_v4_source_manifest=source['files'][V4+'build_index.py'],default_decoder='GBK',narrow_followup='Read bytes then explicit UTF8; no source changes or native operations',
  queries_executed=0,author_programs_executed=0,diagnostic='gbk could not decode byte0xae at position7486; bounded manual-inspection allowance covers the read'))
 budget=write(V5+'budget.json',dict(sealed=True,build_and_seal_explicit_limit=LIMIT,build_manual_allowance=2*1024*1024,ordinary_file_limit=FILE,query_batch_independent_limit=64*1024*1024,
  new_guard_fixture_physical_independent_limit=16*1024*1024,new_guard_fixture_synthetic_returned_limit=40*1024*1024,
  synthetic_limit_note='Aggregate32MiB fixture uses a repeated2MiB owned byte buffer through virtualfile reader; physical fakefile reads are counted separately; no claim of32MiB OS disk reads.',
  first_queries=[['check'],['catalog'],['lookup','0x993570'],['search','993643','--family','peace','--limit','20']],first_queries_max=7,
  guard_fixtures=['97sources_rejected_before_index_or_body','single_fake_source_4MiBplus1_rejected','aggregate_virtual32MiB_limit_retained'],old_suites_or_old_CLI_runs=0,
  software_memory_guard=768*1024*1024,stop_at_or_above_1GiB=True,no_OS_loader_IO_claim=True,no_PE_or_Capstone_or_game=True))
 receipt=dict(sealed=True,passed=True,cache=cache,inventory=ip,budget=budget,initial_manual_failure=failure,files=len(files),read_bytes=sum(x['bytes']for x in reads),reads=reads,peak_bytes=peak,old_entry_count=58,old_JSON_count=59,new_JSON_count=15,
  first_query_or_fixture_executions=0,independent_review_passed=False)
 rp=write(V5+'intake-receipt.json',receipt)
 print(json.dumps(dict(passed=True,cache=cache,inventory=ip,budget=budget,intake=rp,files=len(files),read_bytes=receipt['read_bytes'],peak_bytes=peak)))
def pointer(doc,p):
 for token in p.split('/')[1:]:
  token=token.replace('~1','/').replace('~0','~');doc=doc[int(token)]if type(doc)is list else doc[token]
 return doc
def build():
 claim=write(V5+'build-claim.json',dict(sealed=True,one_author_build=True,root_authorized_only_engine_source_limit_delta=[64,96],PE_game_native=0))
 cache_pin=dict(bytes=2851613,sha256='53b564d7dd5a37f4eeabb15e815785624e5cfcd44e61a8cfc026b6e604e243d7')
 files=decode(read(V5+'build-inputs.json',cache_pin))['files'];docs={}
 for path,e in files.items():
  assert pin(e['text'].encode())=={k:e[k]for k in('bytes','sha256')}
  if path.endswith('.json'):docs[path]=decode(e['text'].encode())
 def pn(path):return {k:files[path][k]for k in('bytes','sha256')}
 oldindex=docs[V4+'index.json'];olddata=docs[V4+'data-manifest.json'];all_sources=olddata['sources']|{path:dict(bytes=n,sha256=h)for path,(n,h)in NEW.items()}
 assert len(all_sources)==74 and len(oldindex['entries'])==58
 R69='work/reports/war-peace-api-20261016-r69-generator-divisor-source/';R71='work/reports/war-peace-api-20261016-r71-divisor-fallthrough-fragment/';R73='work/reports/war-peace-api-20261016-r73-divisor-nonpositive-fragment/'
 for review,subject in [('work/reports/war-peace-api-20261016-r69-actual-independent-review/findings.json',R69+'manifest.json'),('work/reports/war-peace-api-20261016-r71-actual-independent-review/findings.json',R71+'actual-manifest.json'),('work/reports/war-peace-api-20261016-r73-actual-independent-review/findings.json',R73+'actual-manifest.json')]:
  d=docs[review];assert d['sealed']and d['passed']and d['blocking_findings']==[]and d['subject_manifest']==pn(subject)
 refs=[]
 def ref(path,p):
  value=pointer(docs[path],p);refs.append(dict(path=path,json_pointer=p,**all_sources[path]));return value
 for path in NEW:
  if path.endswith('contract.json'):ps=['/entry','/machine_dataflow','/result_limits']if path.startswith(R69)else['/scope','/observations','/unresolved']if path.startswith(R71)else['/scope','/conditional_projection','/remaining_unknown']
  elif path.endswith('selected-evidence.json'):ps=['/instructions','/edges','/metadata']if path.startswith(R69)else['/rows','/terminals','/explicit_stores']if path.startswith(R71)else['/rows','/implicit_stack_reads','/local_CFG_closed']
  elif path.endswith('findings.json'):ps=['/passed','/subject_manifest']
  elif path.startswith((R71,R73))and path.endswith('actual-manifest.json'):ps=['/pins']
  else:ps=['/source_pins']
  for p0 in ps:ref(path,p0)
 assert {x['path']for x in refs}==set(NEW)
 entry=dict(id='peace.generator_divisor_source',actions=['peace'],rva='0x993570',kind='function',stage='static',scope_kind='known_entry_selected_prefix_with_later_conditional_fragments',
  title='Divisor-source candidate entry; selected prefix and conditional exits',
  summary='Known993570 entry:55B R69 prefix storesDWORD0 before unknown97bd30. Later R71 positive context9935a7..993643 and R73 nonpositive context0x993643..993658 are inherited fragments, not independent Win64 APIs. FinalD/units/effects unknown.',
  stage_scope='Fixed retained PE evidence only. Later contexts supplement the frozen R69 prefix contract independently; no native execution, fullfunction closure, current process or gameplay acceptance.',
  aliases=['generator divisor source','993643 conditional context','nonpositive divisor context'],
  signature=dict(status='partial_static',complete_prototype='unknown',parameters=['RCX opaque incoming copied toR13 before97bd30; original W binding conditional across unfollowed calls',
   'RDX borrowed address: native writes exactlyDWORD0 before97bd30; current/finalD not established',
   'R8 opaque pointer copied toRBP and passed onward; selected R69 prefix never dereferences header',
   'R9 and XMM consumption unknown; no semantic type/units assumed'],
   returns='R69 prefix has noRET. Later R73 selected nonpositive exit returns currentR14 beforePOPR14, conditionally originalRDX pointer, never provedDWORD[D]/newbalance/boolean.'),
  ownership=dict(owned=['Unknown97bd30 and positivepathhelpers may allocate/retain or alias storage; no wholefunction ownership/cleanup proof.'],borrowed=['Opaque incomingRCX/RDX/R8 and conditional saved frame/control stack; pointed contents and lifetime across callees unknown.']),
  call_sites=[dict(rva='0x98453d',relationship='retained directCALL e82ef00000→993570; entry seed only'),dict(rva='0x99358a',relationship='selected prefix directCALL97bd30; callee body not followed')],
  owned_ranges=[dict(window=['0x993570','0x9935a7'],bytes=55,role='R69 known-entry selectedprefix; noRET'),dict(window=['0x9935a7','0x993643'],bytes=156,role='R71 inherited nonnull continuation; not standalone function'),dict(window=['0x993643','0x993658'],bytes=21,role='R73 inherited signedlow32(R8)<=0 exit; not standalone function')],
  whole_function_closed=False,independent_fragments_callable=False,
  later_conditional_context=[dict(report='R71',entry='0x9935a7',independent_function=False,condition='97bd30 returned nonzero; prior normal ABI/frame/alias premises. TEST32 R8D uses signedlow32; positive branch has its own saves and unknown d959b0/996e30 calls.',
   facts='Positive selected context includes ADD32[currentR14],EBX modulo32, cursorDWORD+QWORD copy and headerend+12. D0/headerzero cannot survive unknown calls by assumption.',unknown='Whole output, aliases, helper effects, meaning/units and ownership remain unknown.'),
   dict(report='R73',entry='0x993643',independent_function=False,condition='Same nonnull continuation and R71 JLE signedlow32(R8)<=0. F=S69-58 only under normal prior frame.',
    facts='21B:loadR15[F78],MOVRAX,currentR14 beforePOP,ADD RSP30,5POPs,RET. Seven stackQWORD reads56B;0explicitstores/0directD-headerdereferences.',
    unknown='CurrentR14 is originalD only with prior nonvolatile/frame premises; currentD/header/saved/controlstack alias integrity not established; RAX is not amount.')],
  unresolved=['NULL target993658 unread; no wholefunction or arbitrary-input normalreturn proof.',
   '97bd30, d959b0 and996e30 remain unfollowed; register/frame preservation is conditional and pointed memory/aliases can change.',
   'PreCALL DWORD[D]=0 does not establish finalD0 or positive/nonzeroD. R8 arithmetic is not authenticated count/divisor/coin units.',
   'Units, recipients, typed class, allocation/lifetime, peace request/session correlation, settlement and effects remain unknown.',
   'Ordinary static Capstone evidence is not REA EvidenceID or native_ready. No reader adoption, sender/retry or runtime authority.'],evidence=refs,**{k:False for k in FLAGS})
 assert not any(r['id']==entry['id']or int(r['rva'],16)==0x993570 for r in oldindex['entries'])
 index={**oldindex,'entries':sorted(oldindex['entries']+[entry],key=lambda r:r['id'])}
 assert {r['id']:r for r in index['entries']if r['id']!=entry['id']}=={r['id']:r for r in oldindex['entries']}
 ip=write(V5+'index.json',index)
 dm={**olddata,'sources':all_sources,'index':ip};dp=write(V5+'data-manifest.json',dm)
 raw=files[ENGINE]['text'].encode();before=b'1 <= len(sources) <= 64';after=b'1 <= len(sources) <= 96';assert raw.count(before)==1
 newraw=raw.replace(before,after);assert len(newraw)==len(raw)==16583 and pin(newraw)['sha256']=='ea030ce19461b2e414e0cdbc42f4933551fa9e654f7a7a43db948670b27fa466'
 (OUT/'lineage').mkdir();originalcopy=write(V5+'lineage/frozen_query_engine.py',raw.decode(),text=True);ep=write(V5+'query_engine.py',newraw.decode(),text=True)
 oldtree=ast.parse(raw);newtree=ast.parse(newraw)
 class Revert(ast.NodeTransformer):
  changed=0
  def visit_Compare(self,node):
   if ast.unparse(node)=='1 <= len(sources) <= 96':node.comparators[-1]=ast.Constant(64);self.changed+=1
   return self.generic_visit(node)
 revert=Revert();reverted=revert.visit(ast.parse(newraw));assert revert.changed==1 and ast.dump(reverted,include_attributes=False)==ast.dump(oldtree,include_attributes=False)
 wrapper=files[V4+'war_peace_lookup.py']['text'];newwrapper=wrapper.replace("work/candidates/war-peace-api-lookup-1375-v1/war_peace_lookup.py",V5+'query_engine.py').replace(ENGINE_PIN['sha256'],ep['sha256']).replace(V4PINS['data-manifest.json'][1],dp['sha256']).replace('tool_revision=4','tool_revision=5').replace('revision 4;','revision 5;')
 assert newwrapper!=wrapper and 'tool_revision=4'not in newwrapper
 oldfunctions={n.name:ast.dump(n,include_attributes=False)for n in ast.parse(wrapper).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
 newfunctions={n.name:ast.dump(n,include_attributes=False)for n in ast.parse(newwrapper).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
 assert all(newfunctions[n]==oldfunctions[n]for n in('Parser','base_bytes','engine'))
 assert {n for n in oldfunctions if oldfunctions[n]!=newfunctions[n]}=={'unknown','run','main'}
 wp=write(V5+'war_peace_lookup.py',newwrapper,text=True)
 de=write(V5+'engine-delta.json',dict(sealed=True,root_explicitly_authorized=True,original_engine_path=ENGINE,original_engine_pin=ENGINE_PIN,original_owned_copy=originalcopy,new_engine_pin=ep,
  source_change='Only1<=len(sources)<=64 to1<=len(sources)<=96',changed_byte_offsets=[i for i,(a,b)in enumerate(zip(raw,newraw))if a!=b],only_AST_compare_constant_changed=True,
  all_other_engine_AST_equal_after_reverting_one_constant=True,MAX_FILE_4MiB_unchanged=True,MAX_TOTAL_32MiB_unchanged=True,expectedmanifest_raw_pin_before_JSON_unchanged=True,
  new_engine_is_not_original_identity=True,old_engine_modified=False,original_parser_or_oldtests_rerun=False))
 ld=write(V5+'lineage-proof.json',dict(sealed=True,old_v4_source_manifest=pn(V4+'source-manifest.json'),old_v4_data_manifest=pn(V4+'data-manifest.json'),old_v4_index=pn(V4+'index.json'),old_v4_wrapper=pn(V4+'war_peace_lookup.py'),
  old58_data_equal=True,old59_JSON_pins_unchanged=all(all_sources[path]==q for path,q in olddata['sources'].items()),old_source_files_not_modified=True,
  new_entry_ids=[entry['id']],new_entry_RVAs=['0x993570'],new_JSON_paths=sorted(NEW),old_JSON_sources=59,new_JSON_sources=15,total_JSON_sources=74,total_entries=59,
  wrapper_unchanged_AST=['Parser','base_bytes','engine'],wrapper_changed_functions=['unknown','run','main'],wrapper_changed_globals=['BASE','BASE_SHA','DATA_SHA'],
  fragment_contexts_not_independent_endpoints=True,no_R72_R74_type_or_R65_entry_added=True,independent_review_passed=False))
 refchecks=[]
 for row in index['entries']:
  for r in row['evidence']:
   assert {k:r[k]for k in('bytes','sha256')}==all_sources[r['path']];v=pointer(docs[r['path']],r['json_pointer'])
   refchecks.append(dict(endpoint=row['id'],path=r['path'],json_pointer=r['json_pointer'],value_type=type(v).__name__))
 assert {r['path']for r in refchecks}==set(all_sources)
 rv=write(V5+'reference-verification.json',dict(sealed=True,JSON_pointer_checks=refchecks,count=len(refchecks),old58_data_equal=True,old59pins_unchanged=True,new15_all_directly_guarded=True,
  owner_fullreviews_pinned=True,conditional_fragments_not_independent_API=True,author_selfcheck_not_independent=True,PE_game_native_decoder=0))
 readme='''# EU4 1.37.5 offline API lookup v5

59 retained research endpoints,74 directly guarded JSON sources. The original
v4 58 records and59 source pins are preserved. The only new entry is993570;
R71/R73 are later conditional inherited-fragment context, not standalone APIs.
NULL993658, unknowncallees/finalD/units/recipients/effects/lifetime stay unknown.

This version uses a NEW16583B Python queryengine identity. The sole engine
change is source-count ceiling64→96;4MiB perfile/32MiB total guards and parser
semantics are unchanged. Frozen d423engine/v1-v4 files are untouched. Source
hardening and engine delta await a nonauthor review. Every authority staysfalse.

File-only commands: check; catalog; lookup0x993570; search993643. Exit0 means
local evidence query succeeded, never nativeAPI readiness. No process access,
game call, request, installer, listener, publication or package is included.
--base remains conditional user-supplied arithmetic, not module authentication.

engine-delta.json,lineage-proof.json andreference-verification.json preserve
the narrow delta and allflat provenance. First newguardfixtures distinguish
real boundedfakefile reads from synthetic aggregate returnedbytes; receipts
and allstdout/stderr are retained. Oldtests/CLI suites are not repeated.
'''
 rp=write(V5+'README.md',readme,text=True)
 for name in('guard_fixtures.py','run_first.py','seal_candidate.py'):
  code=read(V5+name);ast.parse(code)
  compile(code,name,'exec')
 # Re-pin admitted flat upstreams once; do not walk any nested engine/history graph.
 for path,e in files.items():read(path,{k:e[k]for k in('bytes','sha256')})
 localnames=['index.json','data-manifest.json','query_engine.py','lineage/frozen_query_engine.py','war_peace_lookup.py','guard_fixtures.py','run_first.py','seal_candidate.py','README.md','source-inventory.json','budget.json','engine-delta.json','lineage-proof.json','reference-verification.json','initial-inspection-failure.json']
 locals0={V5+name:pin(read(V5+name))for name in localnames}
 locals0['work/build_lookup_v5_20261016.py']=pin(read('work/build_lookup_v5_20261016.py'))
 allfiles={path:pn(path)for path in files}|locals0
 sm=write(V5+'source-manifest.json',dict(schema='EU4-LOOKUP-V5-SOURCE-MANIFEST/1',sealed=True,status='SOURCE_READY_PENDING_NONAUTHOR_REVIEW',files=allfiles,
  game_sha256=GAME,entry_count=59,selected_JSON_sources=74,build_analysis_budget=LIMIT,first_query_batch_budget=64*1024*1024,fixture_budget=16*1024*1024,
  dependency_scope='flat selected evidence plus fixed v4 lineage/query/job/source tooling; nested native/Capstone refs metadata only',independent_review_passed=False,native_ready=False,callable=False,authority={k:False for k in FLAGS}))
 intake0=decode(read(V5+'intake-receipt.json'));explicit=intake0['read_bytes']+sum(x['bytes']for x in reads)
 upper=explicit+2851613+2*1024*1024;assert upper<LIMIT
 perpass=dp['bytes']+ip['bytes']+sum(x['bytes']for x in all_sources.values());query=2*perpass+3*16583
 record=dict(sealed=True,passed=True,claim=claim,source_manifest=sm,new_engine=ep,wrapper=wp,index=ip,data=dp,engine_delta=de,lineage=ld,references=rv,
  locked_upstream_files=len(files),source_manifest_files=len(allfiles),old58equal=True,old59pinsunchanged=True,newJSON=15,totalJSON=74,newentries=1,allentries=59,
  build_read_bytes=sum(x['bytes']for x in reads),prior_intake_read_bytes=intake0['read_bytes'],manual_cache_inspection_bytes=2851613,other_manual_allowance=2*1024*1024,build_stage_upper=upper,
  explicit_read_journal=reads,peak_bytes=peak,per_query_selected_bytes_per_pass=perpass,per_query_explicit_source_bytes=query,four_query_sources_only=query*4,query_controller_guard_graph_bytes=sum(x['bytes']for x in allfiles.values()),
  query_source_and_controller_upper_estimate=query*4+2*sum(x['bytes']for x in allfiles.values())+4*1024*1024,
  fixtures_and_queries_not_yet_run=True,independent_review_passed=False,PE_Capstone_game_native=0,all_shells_collected=True)
 assert record['query_source_and_controller_upper_estimate']<64*1024*1024
 bp=write(V5+'build-receipt.json',record)
 print(json.dumps(dict(passed=True,source_manifest=sm,new_engine=ep,wrapper=wp,index=ip,data=dp,build_receipt=bp,build_stage_upper=upper,per_query_source=query,four_query_estimate=record['query_source_and_controller_upper_estimate'],peak_bytes=peak)))
if __name__=='__main__':
 try:
  if sys.argv[1:]==['--intake']:intake()
  elif sys.argv[1:]==['--build']:build()
  else:raise ValueError('intake only at this preparation revision')
 except BaseException as e:
  if OUT.exists()and not(OUT/'build-failure-r1.json').exists():write(V5+'build-failure-r1.json',dict(error=type(e).__name__,message=str(e),reads=reads,peak_bytes=peak,automatic_retry=False))
  raise
