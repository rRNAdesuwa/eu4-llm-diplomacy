"""Independent R73 source/preparation review. Never imports author/decoder/PE."""
import ast,ctypes,hashlib,json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
B='work/reports/war-peace-api-20261016-r73-divisor-nonpositive-fragment/'
O='work/reports/war-peace-api-20261016-r73-source-independent-review/'
OUT=ROOT/O;LIMIT=24*1024*1024;FILE=4*1024*1024;reads=[];peak=0
PINS={
B+'preparation-final-manifest.json':dict(bytes=14947,sha256='c967a839241afe7f99caaa4b2b3e0b9865fd86a70803ea316152b61e43c18637'),
B+'source-manifest.json':dict(bytes=24203,sha256='7d06b37f47bdda3a77898f185434994d5f4f0c85d0e856eb0e9fe30bd877ca3f'),
B+'produce.py':dict(bytes=23386,sha256='d23bc4861c7d1a2fe17ecfde2090eda3ee77a9c87cbf9f45649817b51705800b'),
B+'entry-seed.json':dict(bytes=21609,sha256='34014d40471b0f79a9ed37a5013461e4afa1a31d43e22f4558080375a6ca3ca4'),
B+'preparation-delivery.json':dict(bytes=3928,sha256='4cd48ba1716e90cec2e893781de4e93fc5bad0ec257cdcde46fcf6a3cc5152a8'),
'work/reports/war-peace-api-20261016-r73-entry-root-review/findings.json':dict(bytes=2515,sha256='7fb5775b39a1c715f2d44a4475fda1d52b23fcacac2f4e117615f9b02b0b03f4'),
'work/reports/war-peace-api-20261016-r73-entry-root-review/manifest.json':dict(bytes=2649,sha256='2dafb89a56acab3bf03c2be22f9b3385f2e7d6ee9f40cb2972a11020117545e4')}
class PMC(ctypes.Structure):
 _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(x,ctypes.c_size_t)for x in('pw','w','pp','p','pn','n','pf','ppf','private')]
k=ctypes.WinDLL('kernel32',use_last_error=True);k.GetCurrentProcess.restype=ctypes.c_void_p;p=ctypes.WinDLL('psapi',use_last_error=True)
def guard():
 global peak
 a=PMC();a.cb=ctypes.sizeof(a);assert p.GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()),ctypes.byref(a),a.cb)
 peak=max(peak,a.pw,a.ppf,a.private);assert peak<768*1024*1024
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
 f=ROOT/path;a=f.stat();assert a.st_size<=FILE;r=f.read_bytes();z=f.stat()
 assert (a.st_size,a.st_mtime_ns)==(z.st_size,z.st_mtime_ns)and len(r)==a.st_size
 if q is not None:assert pin(r)==q,path
 reads.append(dict(path=path,**pin(r)));assert sum(x['bytes']for x in reads)<LIMIT;return r
def write(name,obj):
 r=(json.dumps(obj,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode();assert len(r)<=FILE
 with(OUT/name).open('xb')as f:f.write(r)
 return pin(r)
def intake():
 OUT.mkdir(exist_ok=False);files={}
 def take(path,q):
  if path in files:assert {k:files[path][k]for k in('bytes','sha256')}==q
  else:
   r=read(path,q);files[path]=dict(**q,text=r.decode('utf-8'))
 take(B+'preparation-final-manifest.json',PINS[B+'preparation-final-manifest.json'])
 m=decode(files[B+'preparation-final-manifest.json']['text'].encode());assert len(m['pins'])==38 and len(m['engine_metadata_only_excluded_from_filecheck'])==38
 for path,q in m['pins'].items():take(path,q)
 for path,q in PINS.items():take(path,q)
 cp=write('retained-files.json',dict(files=files))
 write('intake-receipt.json',dict(cache=cp,files=len(files),read_bytes=sum(x['bytes']for x in reads),reads=reads,peak_bytes=peak,engine_opened=False))
 print(json.dumps(dict(passed=True,cache=cp,files=len(files),read_bytes=sum(x['bytes']for x in reads),peak_bytes=peak)))
def fmap(text):return {n.name:n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)}
def dump(node):return ast.dump(node,include_attributes=False)
def audit():
 cp=dict(bytes=582914,sha256='0d50c76057d72f95aad65c99fa28c6a91d0a83dd4ce55b28980856dc6ce21040')
 files=decode(read(O+'retained-files.json',cp))['files'];docs={}
 for path,e in files.items():
  assert pin(e['text'].encode())=={k:e[k]for k in('bytes','sha256')}
  if path.endswith('.json')and e['bytes']:docs[path]=decode(e['text'].encode())
 def pn(path):return {k:files[path][k]for k in('bytes','sha256')}
 def obj(name):return docs[B+name]
 m=obj('preparation-final-manifest.json');s=obj('source-manifest.json');seed=obj('entry-seed.json');budget=obj('budget.json');delta=obj('source-delta.json');delivery=obj('preparation-delivery.json')
 assert len(files)==42 and len(m['pins'])==38 and all(pn(path)==q for path,q in m['pins'].items())
 assert len(s['actual_source_pins'])==26 and len(s['decoder_expected_witness_pins'])==38 and len(s['source_pins'])==64
 assert s['source_pins']==s['actual_source_pins']|s['decoder_expected_witness_pins']and all(pn(path)==q for path,q in s['actual_source_pins'].items())
 assert m['engine_metadata_only_excluded_from_filecheck']==s['decoder_expected_witness_pins']and all(path.startswith('work/deps/')for path in s['decoder_expected_witness_pins'])
 assert not set(files)&set(s['decoder_expected_witness_pins'])
 assert s['window']==seed['window']==budget['window']==['0x993643','0x993658']and s['scope_kind']==seed['scope_kind']=='inherited_branch_target_fragment'
 assert s['new_code_bytes_max']==budget['new_code_unique_max']==budget['new_code_physical_max']==21
 assert s['new_pdata_bytes']==seed['new_pdata_bytes']==budget['new_pdata_records']==budget['new_pdata_bytes']==0
 assert budget['fallback_allowed']is False and budget['new_header_data_unwind_vtable_callee_bytes']==0 and budget['future_claim_count']==1 and budget['automatic_retry']is False
 assert budget['two_full_EXE_SHA_bytes']==76925008 and budget['future_PE_physical_total']==76925029
 R71='work/reports/war-peace-api-20261016-r71-divisor-fallthrough-fragment/'
 R69='work/reports/war-peace-api-20261016-r69-generator-divisor-source/'
 R72='work/reports/server-vtable-current-reference-owner-20261016-r2/'
 src=files[B+'produce.py']['text'];old=files[R71+'produce.py']['text'];fix=files[R72+'produce.py']['text']
 n=fmap(src);p=fmap(old);f=fmap(fix);assert set(n)==set(p)=={'require','save','digest','charge','read_source','stream_pin','memory_guard','source_guard','raw_write_review','cfg','main'}
 same=delta['unchanged_AST_helpers'];assert len(same)==9 and all(dump(n[x])==dump(p[x])for x in same)
 assert delta['template']==pn(R71+'produce.py')and delta['raw_guard_witness']==pn(R72+'produce.py')
 ng=ast.parse(ast.unparse(n['source_guard'])).body[0];fg=ast.parse(ast.unparse(f['source_guard'])).body[0]
 class Normalize(ast.NodeTransformer):
  def visit_Constant(self,node):
   if node.value=='anchor_site_rva':return ast.copy_location(ast.Constant('entry_rva'),node)
   return node
  def visit_Name(self,node):
   if node.id=='ANCHOR_SITE':return ast.copy_location(ast.Name(id='ENTRY',ctx=node.ctx),node)
   return node
 fg=Normalize().visit(fg);assert dump(ng)==dump(fg)
 assert [a.arg for a in ng.args.args]==['expected_manifest_pin']and len(ng.body)==8
 # Control order is established from exact AST statements and reviewed source; no code is executed.
 guardtext=ast.unparse(ng)
 assert guardtext.index('raw_manifest = read_source')<guardtext.index('== expected_manifest_pin')<guardtext.index('manifest = json.loads(raw_manifest)')<guardtext.index('for name, expected in pins.items()')
 main=ast.unparse(n['main']);sourcecalls=[x for x in ast.walk(n['main'])if isinstance(x,ast.Call)and isinstance(x.func,ast.Name)and x.func.id=='source_guard']
 assert len(sourcecalls)==2 and all([ast.unparse(a)for a in x.args]==['base_pin']and not x.keywords for x in sourcecalls)
 assert main.index('root_explicit_start_received')<main.index("for label in ('upstream_body_review', 'source_peer_review')")<main.index("PHASE = 'source_engine_before'")<main.index('base, pins = source_guard(base_pin)')<main.index('save(\'claim.json\'')<main.index("stream = (ROOT.parent / 'eu4.exe').open('rb')")
 assert main.index('before source guard')<main.index('base, pins = source_guard(base_pin)')<main.index('after source guard')
 assert "values.get('subject_manifest') == UPSTREAM_SUBJECT"in main
 for subject,var in(('subject_source_manifest','base_pin'),('subject_producer','producer_pin'),('subject_entry_seed','seed_pin')):assert "values.get('"+subject+"') == "+var in main
 assert "'EU4-R73-ROOT-AUTHORIZATION/1'"in main and "'raw_inherited_branch_fragment_seed_only'"in main
 assert all(t in main for t in ("'0f8e8b000000'","'433699005836990024dde701'","'0x9935b2'"))
 assert "sys.argv[1:] == []"in main and "('claim.json', 'capture.json', 'owned-code.json', 'failure.json', 'preflight-failure.json')"in main
 assert "with (HERE / name).open('x'"in ast.unparse(n['save'])
 assert main.count("stream.read(21)")==1 and "codeoff = offset(ENTRY, 21)"in main and "require(not PE_READS"in main
 assert "capture['pdata_requests'][14]"in main and 'SparsePE'not in src and 'pdata_record'not in main
 assert main.index("authenticate('before')")<main.index('raw = target_read()')<main.index('import capstone')<main.index("authenticate('after')")<main.index('_, postpins = source_guard(base_pin)')
 assert main.index('stream.close()')<main.index("save('capture.json', value)")
 assert main.index("'Sources/engine/authorization/reviews changed'")<main.index('stream.close()')
 assert "'work/deps/capstone-5.0.7'"in main and "capstone.__version__ == '5.0.7'"in main
 # Retained branch/descriptor data are verified without target or old decoder access.
 up=docs[R71+'actual-selected-evidence.json'];owned=docs[R71+'owned-code.json'];raw=bytes.fromhex(owned['raw_hex'])
 assert len(raw)==156 and owned['window']==['0x9935a7','0x993643']and seed['R71_owned_pin']==pn(R71+'owned-code.json')
 short=seed['R71_short_entry_to_branch_rows'];assert short==up['rows'][:4]
 expected=[('0x9935a7','4c897c2478'),('0x9935ac','4d63f8'),('0x9935af','4585c0'),('0x9935b2','0f8e8b000000')]
 assert[(r['rva'],r['bytes'])for r in short]==expected
 for r in short:
  at=int(r['rva'],16)-0x9935a7;b=bytes.fromhex(r['bytes']);assert raw[at:at+len(b)]==b
 assert 0x9935b2+6+struct.unpack('<i',bytes.fromhex(short[3]['bytes'])[2:])[0]==0x993643
 earlier=docs[R69+'capture.json'];assert seed['R69_nonnull_predecessor_rows']==earlier['analysis']['instructions']
 assert seed['cached_descriptor']==earlier['pdata_requests'][14]
 d=seed['cached_descriptor'];assert struct.unpack('<III',bytes.fromhex(d['raw_hex']))==(0x993643,0x993658,0x1e7dd24)and d['index']==19162
 assert int(d['rva'],16)==0x2465000+19162*12 and d['file_offset']==int(d['rva'],16)-0x132000
 anchors=docs['work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json']
 sec=[x for x in anchors['sections']if int(x['rva'],16)<=0x993643 and 0x993658<=int(x['rva'],16)+x['raw_size']];assert len(sec)==1
 assert sec[0]['raw_file_offset']+0x993643-int(sec[0]['rva'],16)==seed['future_code_file_offset']==10037827
 assert 5*8+0x30==0x58 and -0x58+0x78==0x20
 assert seed['entry_path']['no_new_function_or_Win64_formal_reset']and seed['entry_path']['no_R71_positive_path_calls_before_this_target']
 assert seed['target_bytes_not_yet_read']and seed['new_metadata_needed']is False
 root=docs['work/reports/war-peace-api-20261016-r73-entry-root-review/findings.json']
 assert root['sealed']and root['passed']and root['blocking_findings']==[]and root['entry_seed_pin']==pn(B+'entry-seed.json')
 assert root['entry_rva']=='0x993643'and root['scope']=='raw_inherited_branch_fragment_seed_only'and root['branch_raw']=='0f8e8b000000'
 for subject,path in(('subject_source_manifest','source-manifest.json'),('subject_producer','produce.py'),('subject_entry_seed','entry-seed.json')):assert root[subject]==pn(B+path)and delivery[subject]==pn(B+path)
 rv=docs['work/reports/war-peace-api-20261016-r71-actual-independent-review/findings.json'];assert rv['sealed']and rv['passed']and rv['blocking_findings']==[]and rv['subject_manifest']==pn(R71+'actual-manifest.json')
 assert pin(files[R71+'produce.py']['text'].encode())==delta['template']
 prep=obj('preparation-result.json');check=obj('preparation-filecheck.json')
 assert prep['source_prepost_equal']and check['passed']and check['source_prepost_equal']and check['flat_pins_checked']==29
 assert sum(x['bytes']for x in prep['preparation_read_events'])==prep['preparation_measured_bytes']==808051
 assert sum(x['bytes']for x in check['read_events'])==check['explicit_read_bytes']==969157
 assert prep['future_source_estimate_bytes']==delivery['future_source_estimate_conditional']==19614346
 assert prep['future_estimate_is_conditional_not_OS_worstcase']is True and prep['future_estimate_extra_allowance']==2097152
 assert sum(x['bytes']for x in delivery['seal_final_reads'])==delivery['seal_usage_including_filecheck']-969157
 assert 808051+delivery['seal_usage_including_filecheck']+1048576==delivery['explicit_plus_manual_upper']==2867565
 for name in('preparation-run.json','filecheck-run.json'):
  run=obj(name);assert run['exit_code']==0 and run['direct_child_collected']and run['producer_executed']is False
  for key in run:
   if key.endswith(('.txt',)):assert run[key]==pn(B+key)
 assert all(v is False for v in s['authority'].values())and s['authority']==seed['authority']==budget['authority']==m['authority']==delivery['authority']
 for path,e in files.items():read(path,{k:e[k]for k in('bytes','sha256')})
 replay=dict(sealed=True,nine_helpers_AST_equal_to_frozen_R71=same,rawbuffer_guard_AST_equal_to_R72r2_after_only_scope_identity_normalization=True,
  source_guard_rawbuffer_pin_before_parse_and_engine_loop=True,pre_and_post_guard_both_authorized_basepin=True,first_guard_exterior_exact_checks=True,
  three_review_gates_before_source_engine_and_PE=True,new_root_exact_once_grant_still_required=True,
  targeted_code_read_plan=dict(window=['0x993643','0x993658'],bytes=21,metadata=0,no_fallback=True,no_external_follow=True),
  old_rows_replayed=[dict(rva=r['rva'],raw=r['bytes'])for r in short],descriptor_raw=d['raw_hex'],future_fileoffset=10037827,
  inherited_state=dict(frame='F=S69-0x58 conditional normal prior CALL frame',R15='signextend(low32(R8))<=0',RAX_R12='prior97bd30 nonzero raw bits',
   R8='SAR64(wrapped fresh [currentR13+78]-[currentR13+70],3)',old_R15_store='MOV QWORD[F+0x78],R15; same address F+0x78=S69+0x20; no read of old memory',
   flags='TEST32 R8D:CF0 OF0 ZF/SF/PF result-dependent AFundefined DFunknown',
   unknown='postcallee RCX/RDX/R9/XMM; D/header contents; object type/units/final output/epilogue; saved/control stack alias safety'),
  author_preparation_selfchecks_only=True,author_programs_run_by_reviewer=0)
 rp=write('source-replay.json',replay)
 intake=decode(read(O+'intake-receipt.json'));failed=decode(read(O+'own-assertion-failure-r1/failure.json'));failed_read=sum(x['bytes']for x in failed['reads']);explicit=sum(x['bytes']for x in reads)+intake['read_bytes']+failed_read;manual_cache=3*582914
 upper=explicit+manual_cache+524288+2000000;assert upper<LIMIT
 findings=dict(schema='EU4-R73-SOURCE-INDEPENDENT-REVIEW/1',sealed=True,passed=True,blocking_findings=[],scope='source_budget_and_producer_only_no_actual',
  subject_source_manifest=pn(B+'source-manifest.json'),subject_producer=pn(B+'produce.py'),subject_entry_seed=pn(B+'entry-seed.json'),subject_preparation_final_manifest=pn(B+'preparation-final-manifest.json'),source_replay=rp,
  reviewer_role='Nonauthor of R73/D source. Reviewer previously designed R69 template and audited R71 source/actual and R72 R2 source/actual; D R71 implementation and validation_audit R69 actual, root raw-seed review are distinct retained witnesses. No engine/body or historical execution replay.',
  checks=dict(flat_text_files=42,author_final_flat_pins=38,actual_source_text_pins=26,engine38_metadata_only=True,all_source_prepost_exact=True,
   nine_common_helper_AST_equal=True,rawbuffer_pins_dominate_parse_engine_selection=True,all_new_review_exact_subject_gates_before_engine_PE=True,
   singleclaim_exclusive_no_retry=True,code21_only_metadata0=True,normal_close_and_postguards_before_capture=True,new_actual_not_authorized=True),
  precision_notes=[
   'SavedR15 prose is an address identity only: raw4c897c2478 writes currentR15 to[F+78], and F+78=S69+20. It does not read old QWORD[S69+20]. This nonblocking clarification leaves frozen seed unchanged.',
   'JLE tests signed low32(R8), not the full64 result as a count. R15 is the sign-extended low32; flags derive from TEST32 and DF is unknown. No fresh Win64 formal ABI or entryCALL at993643.',
   'RAX/R12 retain nonzero post97bd30 raw bits on the selected normal continuation. R13/R14/RBP/RSI and frame correspondence additionally require normal prior nonvolatile/frame preservation. D0/headerzero and saved/control-stack memory contents are not invariant.',
   'Skipped positive-path savesF60/F70 and d959b0/996e30 have not executed. The21 target bytes, epilogue/result/units/recipients/completefunction remain unknown until separately authorized acquisition.',
   'R73 adopts R72R2 single rawbuffer pin-before-parse/source selection and exterior first checks. External atomic coherence/ABA is not proved. Frozen historical R71 late-check facts are not retroactively upgraded or rerun.',
   'Root raw review is retained exact entry witness, not actual authority. Future root grant and all three review gates are required before engine/PE. Sourcepeer passing alone grants no actual operation.',
   '19614346 future source estimate includes2097152 conditional allowance; not universal OS/loader I/O worstcase. Author preparation/check exit0/peaks/collection remain retained witnesses, not repeated tests or hardJob proof.'],
  author_resource_witness=dict(preparation=808051,filecheck=969157,seal_including_filecheck=1010938,manual_allowance=1048576,combined_upper=2867565,future_source_conditional=19614346,engine_not_opened=True),
  independent_resources=dict(explicit_intake_and_audit=explicit,manual_cache_inspection=manual_cache,other_manual_allowance=524288,sealing_check_reserve=2000000,complete_stage_upper=upper,limit=LIMIT,self_peak=peak),
  operations=dict(author_producer_import_run=0,author_preparation_verifier_run=0,tests=0,PE_stat_open_hash=0,engine_body=0,decoder=0,game=0,Frida=0,native=0,actual_claim_or_auth_created=0),
  authority={k:False for k in('native_ready','callable','independent_entry_callable','actual_scope_authorized','effect_verified','runtime_authorized','reader_adoption_allowed','world_lease','atomic_snapshot','external_ABA_excluded','authorizes_retry')},
  own_audit_assertion_failure=dict(preserved=True,reason='Reviewer substring expected bare quoted capstone-5.0.7 instead of full literal work/deps/capstone-5.0.7; narrow assertion fix only',failed_read_bytes=failed_read,author_reruns=0),
  author_frozen_sources_need_change=False,all_shells_collected=True)
 fp=write('findings.json',findings)
 local={O+'source-replay.json':rp,O+'findings.json':fp,O+'retained-files.json':cp,'work/review_r73_source_20261016.py':pin(read('work/review_r73_source_20261016.py')),O+'intake-receipt.json':pin(read(O+'intake-receipt.json'))}
 for name in('own-assertion-failure-r1/review.py','own-assertion-failure-r1/failure.json'):local[O+name]=pin(read(O+name))
 mp=write('manifest.json',dict(sealed=True,passed=True,source_pins={path:pn(path)for path in files}|local,subject_source_manifest=pn(B+'source-manifest.json'),subject_producer=pn(B+'produce.py'),subject_entry_seed=pn(B+'entry-seed.json'),engine_metadata_only=s['decoder_expected_witness_pins'],actual_authorized=False,native_ready=False))
 print(json.dumps(dict(passed=True,findings=fp,manifest=mp,source_replay=rp,complete_stage_upper=upper,peak_bytes=peak)))
def check():
 m=decode(read(O+'manifest.json'))
 for path,q in m['source_pins'].items():read(path,q)
 r=dict(sealed=True,passed=True,pins=len(m['source_pins']),read_bytes=sum(x['bytes']for x in reads),peak_bytes=peak,engine_files_opened=0,actual_authorized=False,author_programs_PE_tests_native=0,all_shells_collected=True)
 z=write('verification.json',r);print(json.dumps(dict(passed=True,verification=z,pins=len(m['source_pins']),read_bytes=r['read_bytes'],peak_bytes=peak)))
if __name__=='__main__':
 try:
  if sys.argv[1:]==['--intake']:intake()
  elif sys.argv[1:]==['--audit']:audit()
  elif sys.argv[1:]==['--check']:check()
  else:raise ValueError('unsupported own mode')
 except BaseException as e:
  if OUT.exists()and not(OUT/'own-failure-r1.json').exists():write('own-failure-r1.json',dict(error=type(e).__name__,message=str(e),reads=reads,peak_bytes=peak))
  raise
