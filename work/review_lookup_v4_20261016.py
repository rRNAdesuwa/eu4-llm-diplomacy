"""Independent file/AST/retained receipt review; never imports or calls target tools."""
import ast,ctypes,hashlib,json,re,sys
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1]
B='work/candidates/war-peace-api-lookup-1375-v4/'
OLD='work/candidates/war-peace-api-lookup-1375-v3/'
Q='work/reports/war-peace-api-lookup-v4-first-queries-20261016-r1/'
O='work/reports/war-peace-api-lookup-v4-independent-review-20261016-r1/'
OUT=ROOT/O
FILE=4*1024*1024;LIMIT=24*1024*1024;MEM=768*1024*1024
CACHE=dict(bytes=3243577,sha256='675da0bef4664b4e071d8e0cb0e564031121c9ac1e1c2b034651d13c9c0516bf')
GAME='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
ENGINE='work/candidates/war-peace-api-lookup-1375-v1/war_peace_lookup.py'
EP=dict(bytes=16583,sha256='d4237d98c58e89be9419ff736f01d97f5fde0129c07c5c7f778baf010071746e')
NEW={'peace.selected_element_scalar_output':'0x97b2c0','peace.element_pointer_selection':'0x97b8a0',
 'peace.generated_record_postprocess':'0x994f00','shared.page_step_register_helper':'0x1a337f0'}
FLAGS=('callable','native_ready','sender_authorized','gameplay_effect_verified','process_authenticated',
 'selected_effect_verified','world_lease','atomic_snapshot','authorizes_retry','runtime_capture_authorized',
 'peace_completion_verified','amount_units_verified','recipient_direction_verified','object_ownership_verified')
reads=[];peak=0
class PMC(ctypes.Structure):
 _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong)]+[(n,ctypes.c_size_t)for n in
 ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
k=ctypes.WinDLL('kernel32',use_last_error=True);k.GetCurrentProcess.restype=ctypes.c_void_p
p=ctypes.WinDLL('psapi',use_last_error=True)
def guard():
 global peak
 a=PMC();a.cb=ctypes.sizeof(a);assert p.GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()),ctypes.byref(a),a.cb)
 peak=max(peak,a.PeakWorkingSetSize,a.PeakPagefileUsage,a.PrivateUsage);assert peak<MEM
def pin(r):return dict(bytes=len(r),sha256=hashlib.sha256(r).hexdigest())
def pairs(a):
 d={}
 for x,y in a:
  if x in d:raise ValueError('duplicate_json_key')
  d[x]=y
 return d
def decode(r):return json.loads(r.decode('utf-8'),object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in()).throw(ValueError(x)))
def canon(x):return json.dumps(x,sort_keys=True,ensure_ascii=True,separators=(',',':')).encode()
def read(path,expected=None):
 guard();z=ROOT/path;a=z.stat();assert a.st_size<=FILE
 r=z.read_bytes();b=z.stat();assert(a.st_size,a.st_mtime_ns)==(b.st_size,b.st_mtime_ns)and len(r)==a.st_size
 if expected is not None:assert pin(r)==expected,path
 reads.append(dict(path=path,**pin(r)));assert sum(x['bytes']for x in reads)<LIMIT
 return r
def write(name,x):
 r=(json.dumps(x,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode();assert len(r)<=FILE
 with(OUT/name).open('xb')as f:f.write(r)
 return pin(r)
def pointer(v,s):
 assert type(s)is str and s.startswith('/')
 for token in s.split('/')[1:]:
  assert re.search(r'~(?![01])',token)is None
  token=token.replace('~1','/').replace('~0','~')
  if type(v)is list:
   assert re.fullmatch(r'0|[1-9][0-9]*',token);v=v[int(token)]
  else:assert type(v)is dict;v=v[token]
 return v
def parse_tree(text):return ast.parse(text)
def function(tree,name):return next(x for x in tree.body if isinstance(x,(ast.FunctionDef,ast.ClassDef))and x.name==name)
def main():
 c=decode(read(O+'retained-files.json',CACHE));f=c['files'];docs={}
 for path,e in f.items():
  raw=e['text'].encode('utf-8');assert pin(raw)=={x:e[x]for x in('bytes','sha256')}
  if path.endswith('.json'):docs[path]=decode(raw)
 def obj(n):return docs[B+n]
 def pn(path):return {x:f[path][x]for x in('bytes','sha256')}
 def txt(path):return f[path]['text']
 m=obj('author-manifest.json');s=obj('source-manifest.json');d=obj('data-manifest.json');idx=obj('index.json')
 v=obj('verification.json');delivery=obj('delivery.json');receipt=docs[Q+'receipt.json']
 assert len(f)==109 and len(m['local_and_selected_source_pins'])==106 and m['pin_count']==106
 assert len(s['files'])==82 and all(m['local_and_selected_source_pins'][path]==q for path,q in s['files'].items())
 assert m['subject_source_manifest']==v['source_manifest']==delivery['source_manifest']==pn(B+'source-manifest.json')
 assert v['author_manifest']==delivery['author_manifest']==pn(B+'author-manifest.json')
 assert delivery['verification']==pn(B+'verification.json')and delivery['cli']==pn(B+'war_peace_lookup.py')
 assert delivery['data_manifest']==pn(B+'data-manifest.json')and delivery['index']==pn(B+'index.json')
 assert receipt['source_manifest']==pn(B+'source-manifest.json')and delivery['query_receipt']==v['query_receipt']==pn(Q+'receipt.json')
 for a in(s,m):
  assert a['sealed']is True and all(x is False for x in a['authority'].values())
 assert s['native_ready']is False and s['callable']is False and s['entry_count']==58 and s['selected_JSON_sources']==59
 assert d['game_sha256']==idx['game_sha256']==s['game_sha256']==GAME
 assert len(d['sources'])==59 and d['index']==pn(B+'index.json')
 assert all(pn(path)==q for path,q in m['local_and_selected_source_pins'].items())
 assert all(pn(path)==q for path,q in d['sources'].items())
 old=docs[OLD+'index.json'];od=docs[OLD+'data-manifest.json']
 by={x['id']:x for x in idx['entries']};oldby={x['id']:x for x in old['entries']}
 assert len(by)==len(idx['entries'])==58 and len(oldby)==54 and len(od['sources'])==44
 assert [x['id']for x in idx['entries']]==sorted(by)
 assert all(by[x]==a for x,a in oldby.items())
 assert {x:a['rva']for x,a in by.items()if x not in oldby}==NEW
 assert all(d['sources'][path]==q for path,q in od['sources'].items())
 lineage=obj('lineage-proof.json');delta=obj('source-delta.json')
 mapping=[dict(id=e['id'],canonical_sha256=hashlib.sha256(canon(e)).hexdigest())for e in old['entries']]
 assert lineage['per_old_entry']==mapping and lineage['old_index']==pn(OLD+'index.json')
 assert set(lineage['added_ids'])==set(NEW)and lineage['new_count']==58 and lineage['original_entries']==54
 assert delta['current_cli']==pn(B+'war_peace_lookup.py')and delta['prior_cli']==pn(OLD+'war_peace_lookup.py')
 assert delta['data_manifest']==pn(B+'data-manifest.json')and delta['index']==pn(B+'index.json')
 assert delta['original_engine']==pn(ENGINE)==EP and delta['lineage']==pn(B+'lineage-proof.json')
 assert delta['R69_R70_included']is False
 # Byte restoration and independent AST comparisons do not import/execute either wrapper.
 current=txt(B+'war_peace_lookup.py');prior=txt(OLD+'war_peace_lookup.py')
 assert current.count(pn(B+'data-manifest.json')['sha256'])==1 and current.count('tool_revision=4')==2 and current.count('revision 4;')==1
 restored=current.replace(pn(B+'data-manifest.json')['sha256'],pn(OLD+'data-manifest.json')['sha256']).replace('tool_revision=4','tool_revision=3').replace('revision 4;','revision 3;')
 assert restored==prior and ast.dump(parse_tree(restored),include_attributes=False)==ast.dump(parse_tree(prior),include_attributes=False)
 ct=parse_tree(current);pt=parse_tree(prior)
 same=[]
 for name in('base_bytes','engine','Parser'):
  assert ast.dump(function(ct,name),include_attributes=False)==ast.dump(function(pt,name),include_attributes=False);same.append(name)
 assert ast.literal_eval(next(x.value for x in ct.body if isinstance(x,ast.Assign)and any(isinstance(z,ast.Name)and z.id=='BASE_SHA'for z in x.targets)))==EP['sha256']
 imports={x.module.split('.')[0]for x in ct.body if isinstance(x,ast.ImportFrom)}|{z.name.split('.')[0]for x in ct.body if isinstance(x,ast.Import)for z in x.names}
 assert imports=={'__future__','argparse','hashlib','json','pathlib','sys','types'}
 eng=txt(ENGINE);et=parse_tree(eng)
 assert not any(isinstance(x,(ast.Import,ast.ImportFrom))and any(w in ast.unparse(x).lower()for w in('ctypes','subprocess','socket','frida','requests'))for x in ast.walk(et))
 assert "module.SourceGraph(ROOT, HERE, DATA_SHA)"in current and "module.query(graph, operation, selector, family, base, limit)"in current
 assert "graph.verify(parse=True)"in eng and "graph.verify(parse=False)"in eng and "entries=[], count=0"in eng
 assert "_hash(raw) == self.expected_manifest"in eng and "_check_pin(content, pin)"in eng
 # All refs are resolved independently against exactly pinned flat JSON, not recursively followed.
 refs=[];used=set()
 for e in idx['entries']:
  for x in FLAGS[:5]:assert e[x]is False
  assert e['signature']['complete_prototype']=='unknown'
  if e['id']in NEW:
   assert e['stage']=='static'and e['signature']['status']=='partial_static'
   for x in FLAGS:assert e[x]is False
  for r in e['evidence']:
   path=r['path'];parts=PurePosixPath(path).parts
   assert parts[:2]==('work','reports')and '..'not in parts and path.endswith('.json')
   assert {x:r[x]for x in('bytes','sha256')}==d['sources'][path]==pn(path)
   val=pointer(docs[path],r['json_pointer']);used.add(path)
   refs.append(dict(id=e['id'],path=path,json_pointer=r['json_pointer'],selected_value_sha256=hashlib.sha256(canon(val)).hexdigest()))
 assert len(refs)==234 and used==set(d['sources'])
 assert [e['id']for e in idx['entries']if e['stage']=='real_rawbody_postcondition']==['declare_war.body_destructor']
 assert by['declare_war.body_destructor']['rva']=='0x500560'
 # Full review owner bindings and the later conditional context remain distinct.
 owners={63:'gold-scalar-source',64:'gold-element-selection',66:'generated-record-postprocess',67:'entry-helper-register-contract'}
 ownerpins=[]
 for n,owner in owners.items():
  head=f'work/reports/war-peace-api-20261016-r{n}-'
  path=head+owner+'/contract.json';review=head+('actual-independent-review'if n==67 else'independent-review')+'/findings.json'
  j=docs[review];assert j['sealed']is True and j['passed']is True and j['blocking_findings']==[]and j['subject_contract']==pn(path)
  contract=docs[path];assert contract['sealed']is True and all(x is False for x in contract['authority'].values())
  ownerpins.append(dict(contract=dict(path=path,**pn(path)),full_review=dict(path=review,**pn(review))))
 p68='work/reports/war-peace-api-20261016-r68-fixed-frame-projection/projection.json'
 r68='work/reports/war-peace-api-20261016-r68-independent-review/findings.json'
 assert docs[r68]['sealed']is True and docs[r68]['passed']is True and docs[r68]['blocking_findings']==[]and docs[r68]['subject_projection']==pn(p68)
 post=by['peace.generated_record_postprocess']
 assert post['historical_contract']['sha256']==pn('work/reports/war-peace-api-20261016-r66-generated-record-postprocess/contract.json')['sha256']and post['historical_contract']['unchanged']is True
 assert post['later_conditional_context']['sha256']==pn(p68)['sha256']and post['later_conditional_context']['fresh_H_T_required']is True and post['later_conditional_context']['pointee_immutability_proved']is False
 assert post['later_conditional_context']['fixed_frame']=='F=Q-0x1048'
 assert all(x is False for x in docs[p68]['authority'].values())
 # First-query outputs are replayed as retained JSON; no tool function is called.
 commands=[['check'],['catalog'],['lookup','0x97b2c0'],['lookup','0x97b8a0'],['lookup','0x994f00'],['lookup','0x1a337f0'],['search','v4 \u5df2\u5ba1\u5408\u540c','--limit','20']]
 claim=docs[Q+'claim.json'];assert claim['commands']==commands and receipt['claim']==pn(Q+'claim.json')
 assert receipt['sealed']is True and receipt['passed']is True and receipt['error']is None and receipt['command_count']==7 and len(receipt['records'])==7
 assert receipt['first_queries_only']is True and receipt['all_jobs_and_direct_children_collected']is True
 perpass=d['index']['bytes']+pn(B+'data-manifest.json')['bytes']+sum(a['bytes']for a in d['sources'].values());assert perpass==2261683
 perquery=2*perpass+3*EP['bytes'];assert perquery==4573115
 briefkeys=('id','actions','title','rva','kind','stage','stage_scope','summary','evidence')+FLAGS[:5]
 brief=lambda e:{a:e[a]for a in briefkeys}
 queryreplay=[]
 for i,(r,args)in enumerate(zip(receipt['records'],commands,strict=True)):
  assert r['argv'][2:]==args and r['argv'][1].replace('\\','/').endswith('/'+B+'war_peace_lookup.py')
  assert r['stdout']==pn(Q+f'{i:02d}.stdout.json')and r['stderr']==pn(Q+f'{i:02d}.stderr.txt')and not txt(Q+f'{i:02d}.stderr.txt')
  j=r['job'];assert j['exit_code']==0 and j['error']is None and j['job_active_processes_final']==0 and j['direct_child_collected']is True
  assert 1<=j['job_total_processes']<=8 and j['completed_command_descendants_terminated']is False and j['peak_job_commit']<=MEM
  out=docs[Q+f'{i:02d}.stdout.json'];assert out['operation']==r['operation']==args[0]and out['status']==r['status']=='ok'and out['tool_revision']==4
  assert out['native_calls']==out['requests_published']==0 and out['identity_scope']=='retained_evidence_target_only_not_current_process_authentication'
  for flag in FLAGS[:9]:assert out[flag]is False
  prov=out['provenance'];assert prov['selected_source_count']==59 and prov['selected_bytes_per_pass']==perpass
  assert prov['source_guard_before_and_after']is True and prov['manifest_sha256']==pn(B+'data-manifest.json')['sha256']and prov['index_sha256']==pn(B+'index.json')['sha256']
  assert out['original_engine_source_guard_before_and_after']is True and out['reused_engine_sha256']==EP['sha256']
  if i==0:
   assert out['entry_count']==58 and out['stage_counts']=={'static':57,'real_rawbody_postcondition':1}
  elif i==1:assert out['count']==58 and out['entries']==[brief(e)for e in idx['entries']]
  elif i<6:
   match=[e for e in idx['entries']if e['rva']==args[1]];assert out['count']==1 and out['entries']==match
  else:
   expected=[brief(by[x])for x in sorted(NEW)];assert out['count']==out['total_matches']==4 and out['entries']==expected
  assert r['ids']==[x['id']for x in out.get('entries',[])]and r['count']==out.get('count')and r['entry_count']==out.get('entry_count')
  assert r['selected_bytes_per_pass']==perpass and r['explicit_query_source_bytes']==r['query_source_reserved_upper_bytes']==perquery
  assert r['cumulative_query_source_bytes']==(i+1)*perquery
  queryreplay.append(dict(args=args,stdout=r['stdout'],status=out['status'],ids=r['ids'],Job_exit=0,Job_active_final=0,Job_total_processes=j['job_total_processes'],peak_job_commit=j['peak_job_commit']))
 assert receipt['query_source_explicit_bytes']==perquery*7==32011805
 controller=receipt['controller_read_journal'];assert len(controller)==183
 for e in controller:assert {x:e[x]for x in('bytes','sha256')}==pn(e['path'])
 assert sum(e['bytes']for e in controller)==receipt['controller_explicit_bytes']==5379149
 assert receipt['combined_delta_explicit_bytes']==32011805+5379149==37390954<64*1024*1024
 expectedpass=[dict(path=B+'source-manifest.json',**pn(B+'source-manifest.json'))]+[dict(path=x,**a)for x,a in s['files'].items()]
 assert controller[:83]==controller[-83:]==expectedpass
 # Initial generation failure and narrow runner repair retain original product bytes.
 failed=obj('build-failure.json');repair=obj('repair-receipt.json');builder=txt(B+'build_index.py');repairtext=txt(B+'repair_runner.py')
 assert failed['error']=='AssertionError'and failed['retries_authorized']is False and failed['PE_engine_decoder_game_native_requests_tests']==0
 assert 'AssertionError'in txt(B+'build.stderr.txt')and not txt(B+'build.stdout.txt')
 assert repair['sealed']is True and repair['passed']is True and repair['first_failure']==pn(B+'build-failure.json')
 assert repair['new_queries_run']==repair['old_CLI_tests_PE_game_native']==0 and repair['initial_builder_source_preserved']is True and repair['prior_index_data_CLI_byte_identical']is True
 assert "assert \"['lookup','0x97b2c0']\" in runner"in builder
 assert builder.index("write('source-delta.json'")<builder.index('runner=old[')<builder.index("text('run_queries.py',runner)")
 assert "with (HERE/'run_queries.py').open('xb')"in repairtext and "prior_index_data_CLI_byte_identical=True"in repairtext
 for e in failed['reads']+repair['reads']+v['reads']:
  assert {x:e[x]for x in('bytes','sha256')}==pn(e['path'])
 assert repair['prior_upper_including_manual']==sum(x['bytes']for x in failed['reads'])+1024*1024==3322756
 assert repair['repair_explicit_bytes']==sum(x['bytes']for x in repair['reads'])==5188461
 assert repair['analysis_upper_through_repair']==8511217
 assert v['final_analysis_upper']==repair['analysis_upper_through_repair']+sum(x['bytes']for x in v['reads'])==14198701<24*1024*1024
 assert v['passed']is True and v['sealed']is True and v['pins_verified']==106
 assert {x['path']:{a:x[a]for a in('bytes','sha256')}for x in v['reads'][-107:-1]}==m['local_and_selected_source_pins']
 assert len({x['path']for x in v['reads'][-107:-1]})==106 and v['reads'][-1]['path']==B+'author-manifest.json'
 assert v['metrics']==m['metrics']and m['metrics']['evidence_JSONpointers']==234
 # Current postguard reads only the 109 flat explicitly admitted text files.
 for path,e in f.items():read(path,{x:e[x]for x in('bytes','sha256')})
 upper=c['source_bytes']+CACHE['bytes']+2*1024*1024+sum(x['bytes']for x in reads)+3584*1024
 assert upper<LIMIT
 ops={n:0 for n in('CLI','tests','PE_stat_open','native_decoder_engine','Capstone','author_builder_repair_runner_sealer','game_process','Frida','native_game_calls','requests','R71_or_callee_follow')}
 authority={n:False for n in FLAGS}
 replay=write('refs-and-receipts.json',dict(schema='EU4-LOOKUP-V4-INDEPENDENT-REPLAY/1',sealed=True,passed=True,
  old54_canonical_mapping=mapping,new4=NEW,evidence_pointers=refs,refs_count=234,used_sources=59,
  wrapper_exact_restore_equal=True,wrapper_AST_guard_equal=same,query_engine_source_pin=EP,query_engine_not_native_decoder=True,
  new_owner_subject_bindings=ownerpins,later_R68_subject=dict(path=p68,**pn(p68)),query_results=queryreplay,
  perpass_bytes=perpass,perquery_bytes=perquery,firstquery_total=37390954,analysis_total=14198701,
  R1failure_retained_R2runner_only_repair=True,author_sources_unchanged=True,all_source_postguards_equal=True))
 findings=write('findings.json',dict(schema='EU4-LOOKUP-V4-INDEPENDENT-SOURCE-REVIEW/1',sealed=True,passed=True,blocking_findings=[],
  scope='Complete nonauthor file/AST/retained-first-query review; no tool execution or runtime authentication',
  subject_manifest=pn(B+'author-manifest.json'),subject_source_manifest=pn(B+'source-manifest.json'),subject_CLI=pn(B+'war_peace_lookup.py'),
  subject_data_manifest=pn(B+'data-manifest.json'),subject_index=pn(B+'index.json'),subject_firstqueries=pn(Q+'receipt.json'),replay=replay,
  checks=dict(author_source_files=106,current_flat_files=109,source_manifest_subset=82,entries=58,old54_dataequal=True,old44_sourcepins_unchanged=True,
   new4_RVAs=sorted(NEW.values()),selected_JSON_sources=59,evidence_JSONpointers=234,wrapper_only_DATA_SHA_revision_help_changed=True,
   Parser_base_bytes_engine_AST_equal=True,fullreview_subjects_R63_R64_R66_R67_R68_bound=True,first7_results_replayed=True,query_outputs_sources_prepost_equal=True,
   failed_builder_and_narrow_runner_repair_preserved=True,no_API_or_effect_escalation=True),
  precision_notes=[
   'This audits the new v4 data/wrapper/receipts. Earlier 54 rows are data-equal and their 44 selected pins unchanged; historical nested engines/manifests/raw bodies were not recursively authenticated.',
   'The pinned 16,583-byte Python file-query engine is source-only here, distinct from native Capstone. Wrapper hashes it before compile/exec and afterwards; the fixed data graph receives before/after source-pin checks. No target executable loader or process command is exposed.',
   'R63 selected DWORD+30 or zero is an explicit output store; 17394f0 and aliases still prevent final-pointee retention proof. Descriptor RDX differs from original output address, and XMM padding is not all zero.',
   'R64 Pcount clearing/selfcall/append/remove and selector widths remain machine contracts. No enum0=gold, concrete virtual78 return class, units, unique count1, full allocation ownership or final effect follows.',
   'R66 first-helper historical unknown is preserved verbatim. R68 supplies separate later conditional frame F=Q-1048 and argument addresses only under its hypotheses; GS alias, normal return, fresh H/T and later callees remain unknown.',
   'R67 concrete normal-register preservation does not prove contents unchanged, arbitrary-input termination, writable GS-derived addresses, saved/return-slot disjointness or safe-call permission.',
   'The sole historical real_rawbody_postcondition remains 500560; four new entries are static. All callable/readiness/effect/lease/retry flags remain false, and --base is user-supplied conditional RVA-to-VA arithmetic only.',
   'Seven first v4 query receipts exit0 mean retained file queries succeeded. Jobs are retained witnesses, not independently reexecuted here; all report active0/direct collected/no forced descendants. No old test/query was rerun.',
   'The first build failed at newline-sensitive runner generation before queries. Index/data/CLI survive unchanged; a separately retained repair generated the runner and sealed source. Analysis and query-batch budgets remain separate explicit file-read accounting, not all OS/interpreter/loader I/O.',
   'Own inline inspection initially had a Python syntax typo before any read/execution; corrected inspection only read retained JSON. It did not run author code. No independent audit semantic failure occurred.'
  ],resource_witness=dict(build_repair_seal_explicit_upper=14198701,analysis_limit=24*1024*1024,
   first_query_selected_bytes_per_pass=perpass,first_query_bytes_per_query=perquery,seven_query_source_bytes=32011805,controller_bytes=5379149,
   query_batch_total=37390954,query_batch_limit=64*1024*1024,all_OS_IO_claim=False,maximum_query_Job_peak=m['metrics']['maximum_query_Job_peak']),
  independent_resources=dict(intake_source_bytes=c['source_bytes'],prior_single_retained_inspection_bytes=CACHE['bytes'],
   root_and_own_smallinspection_allowance=2*1024*1024,current_cache_plus_postguard_bytes=sum(x['bytes']for x in reads),
   own_sealing_reserve=3584*1024,listed_analysis_upper_bytes=upper,stage_limit=LIMIT,ordinary_file_limit=FILE,own_peak_bytes=peak,memory_limit=MEM),
  operations=ops,authority=authority,all_shells_collected=True,author_frozen_sources_changed=False,next_scope_auto_authorized=False))
 report=('Lookup v4 source/AST/receipt review passed:58entries,59selectedJSONsources,234pointers; old54rowsdataequal/44pinsunchanged. Fournewstaticcontracts remain noncallable. R68 is laterconditionalcontext, not rewritingR66. First7filequeryresults replayed without invokingtheCLI. NoPE/native-decoder/game/nativecalls/tests.\n').encode()
 with(OUT/'report.md').open('xb')as z:z.write(report)
 local={O+n:pin((OUT/n).read_bytes())for n in('retained-files.json','refs-and-receipts.json','findings.json','report.md')}
 for path in('work/retain_lookup_v4_review_20261016.py','work/review_lookup_v4_20261016.py'):local[path]=pin((ROOT/path).read_bytes())
 manifest=write('manifest.json',dict(schema='EU4-LOOKUP-V4-INDEPENDENT-REVIEW-MANIFEST/1',sealed=True,source_pins={path:pn(path)for path in f},
  local_pins=local,findings=findings,flat_source_scope='106authorpins plus author-manifest/verification/delivery; no recursive historical graph',operations=ops,authority=authority))
 print(json.dumps(dict(passed=True,findings=findings,manifest=manifest,replay=replay,analysis_upper=upper,peak=peak,all_shells_collected=True)))
def check():
 m=decode(read(O+'manifest.json'))
 for path,q in(m['source_pins']|m['local_pins']).items():read(path,q)
 f=decode(read(O+'findings.json',m['local_pins'][O+'findings.json']))
 upper=f['independent_resources']['listed_analysis_upper_bytes']+sum(x['bytes']for x in reads);assert upper<LIMIT
 v=write('verification.json',dict(schema='EU4-LOOKUP-V4-INDEPENDENT-VERIFICATION/1',sealed=True,passed=True,
  pins_checked=len(m['source_pins']|m['local_pins']),source_pins_current_equal=True,conservative_complete_stage_upper_bytes=upper,stage_limit=LIMIT,
  own_peak_bytes=peak,operations=m['operations'],authority=m['authority'],all_shells_collected=True))
 print(json.dumps(dict(passed=True,verification=v,pins=len(m['source_pins']|m['local_pins']),complete_upper=upper,peak=peak)))
if __name__=='__main__':
 try:check()if sys.argv[1:]==['--check']else main()
 except BaseException as exc:
  n='verification-failure.json'if sys.argv[1:]==['--check']else'review-failure.json'
  if not(OUT/n).exists():write(n,dict(error=type(exc).__name__,detail=str(exc),reads=reads,peak=peak,author_sources_unchanged=True,no_author_program_or_PE_native_execution=True))
  raise
