"""Independent R72 R2 source review; no reviewed modules, fixtures, or engines run."""
import ast,ctypes,hashlib,json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
B='work/reports/server-vtable-current-reference-owner-20261016-r2/'
R1='work/reports/server-vtable-current-reference-owner-20261016-r1/'
O='work/reports/server-vtable-current-reference-owner-source-independent-review-20261016-r2/'
OLD_CACHE_PATH='work/reports/server-vtable-current-reference-owner-source-independent-review-20261016-r1/retained-files-r1.json'
OUT=ROOT/O;LIMIT=24*1024*1024;FILE=4*1024*1024;MEM=768*1024*1024
CACHE=dict(bytes=903989,sha256='e86650deb438058df362cfe0bc940d86e330658d9d05f395444e996109eb809d')
OLD_CACHE=dict(bytes=621515,sha256='66e185ace58d8c6664ffd940872a2fa3514f7378b27535cae39f09650267c847')
SUBJECT={
 'source-manifest.json':dict(bytes=24090,sha256='ba3735d36f60978d6bfff31c6740eabacd3427b7944832d888999882db52a6c4'),
 'produce.py':dict(bytes=26805,sha256='902a2908148870876719f8b086553ea553e87cf9000703af61787be87d9a875d'),
 'entry-seed.json':dict(bytes=4236,sha256='0ad3aeb8e360b020b238185778a3d0d1718b24323b00d44b4267bec25da749af')}
GAME='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
reads=[];peak=0
class PMC(ctypes.Structure):
 _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(x,ctypes.c_size_t)for x in('pw','w','pp','p','pn','n','pf','ppf','private')]
k=ctypes.WinDLL('kernel32',use_last_error=True);k.GetCurrentProcess.restype=ctypes.c_void_p;p=ctypes.WinDLL('psapi',use_last_error=True)
def guard():
 global peak
 x=PMC();x.cb=ctypes.sizeof(x);assert p.GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()),ctypes.byref(x),x.cb)
 peak=max(peak,x.pw,x.ppf,x.private);assert peak<MEM
def pin(r):return dict(bytes=len(r),sha256=hashlib.sha256(r).hexdigest())
def pairs(v):
 d={}
 for a,b in v:
  if a in d:raise ValueError('duplicate_json_key')
  d[a]=b
 return d
def decode(r):return json.loads(r.decode('utf-8'),object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in()).throw(ValueError(x)))
def read(path,q=None):
 guard();assert not path.startswith('work/deps/')and not path.lower().endswith(('.exe','.dll','.pyd','.whl'))
 f=ROOT/path;a=f.stat();assert a.st_size<=FILE
 r=f.read_bytes();z=f.stat();assert(a.st_size,a.st_mtime_ns)==(z.st_size,z.st_mtime_ns)and len(r)==a.st_size
 if q is not None:assert pin(r)==q,path
 reads.append(dict(path=path,**pin(r)));assert sum(x['bytes']for x in reads)<LIMIT;return r
def write(name,v):
 r=(json.dumps(v,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode();assert len(r)<=FILE
 with(OUT/name).open('xb')as f:f.write(r)
 return pin(r)
def fn(tree,name):return next(x for x in tree.body if isinstance(x,ast.FunctionDef)and x.name==name)
def dump(x):return ast.dump(x,include_attributes=False)
def is_main_file_pin_guard(node):
 if not isinstance(node,ast.Expr)or not isinstance(node.value,ast.Call)or not isinstance(node.value.func,ast.Name)or node.value.func.id!='require':return False
 condition=node.value.args[0]
 expected=ast.parse("stream_pin(HERE/'source-manifest.json')==base_pin",mode='eval').body
 return dump(condition)==dump(expected)
def main():
 c=decode(read(O+'retained-files.json',CACHE));f=c['files'];oldc=decode(read(OLD_CACHE_PATH,OLD_CACHE));oldf=oldc['files']
 def pn(path):return {x:f[path][x]for x in('bytes','sha256')}
 def text(path):return f[path]['text']
 def obj(n):return decode(text(B+n).encode('utf-8'))
 for path,e in f.items():assert pin(e['text'].encode('utf-8'))==pn(path)
 for path,e in oldf.items():assert pin(e['text'].encode('utf-8'))=={x:e[x]for x in('bytes','sha256')}
 m=obj('source-manifest.json');final=obj('final-manifest.json');delivery=obj('prepared-delivery.json');seed=obj('entry-seed.json');budget=obj('budget.json')
 delta=obj('revision-delta.json');snapshot=obj('r1-preimage.json');receipt=obj('source-preparation-receipt.json');prep=obj('preparation.json');fc=obj('prepared-filecheck.json')
 assert len(f)==58 and len(final['source_pins'])==final['source_pin_count']==56 and len(m['actual_source_pins'])==m['actual_source_pin_count']==26
 # The prepared delivery explicitly pins three post-seal logs/status files
 # published after its 56-file final manifest. Admit only these named texts.
 extra=[]
 for name,q in delivery['selected_local_pins'].items():
  path=B+name
  if path not in f:
   assert name in ('source-seal.stdout.json','source-seal.stderr.txt','R2_SOURCE_STATUS.md')
   rr=read(path,q);f[path]=dict(**q,text=rr.decode('utf-8'));extra.append(path)
 assert len(extra)==3 and len(f)==61
 assert len(m['decoder_expected_witness_pins'])==m['decoder_witness_pin_count']==38
 assert m['source_pins']==m['actual_source_pins']|m['decoder_expected_witness_pins']
 assert final['decoder_expected_witness_pins']==m['decoder_expected_witness_pins']and final['engine_metadata_only']is True
 assert all(pn(path)==q for path,q in final['source_pins'].items())and all(pn(path)==q for path,q in m['actual_source_pins'].items())
 assert all(pn(B+n)==q for n,q in SUBJECT.items())
 assert delivery['subject_source_manifest']==receipt['subject_source_manifest']==fc['subject_source_manifest']==SUBJECT['source-manifest.json']
 assert delivery['subject_producer']==receipt['subject_producer']==SUBJECT['produce.py']and delivery['subject_entry_seed']==receipt['subject_entry_seed']==SUBJECT['entry-seed.json']
 assert all(pn(B+n)==q for n,q in delivery['selected_local_pins'].items())
 assert m['sealed']is True and m['revision']=='r2'and m['anchor_site_rva']=='0x10d24e3'and m['raw_anchor7_hex']=='488d05de83c800'and m['target_vtable_rva']=='0x1d5a8c8'
 assert m['game_sha256']==GAME and m['game_bytes']==38462504 and m['engine_files_accessed_at_preparation']is False
 for name in('actual_authorized','tests_authorized','native_ready','host_guard_change_authorized','class_or_mode_verified','world_lease','atomic_snapshot','authorizes_retry'):assert m[name]is False
 assert final['R1_blocked']is True and final['R1_modified']is False and final['actual_authorized']is False and final['tests_authorized']is False
 # Original R1 files remain blocked; compare R2 snapshots to independently owned prior-stage bytes.
 assert len(snapshot['source_files'])==18 and snapshot['subject_revision']=='r1 blocked, not passed'
 for name,q in snapshot['source_files'].items():
  original=oldf[R1+name];assert {x:original[x]for x in('bytes','sha256')}==q
  assert pn(B+'preimage-r1/'+name)==q and text(B+'preimage-r1/'+name)==original['text']
 assert snapshot['returned_bytes']==sum(q['bytes']for q in snapshot['source_files'].values())==130125
 blocker=delta['r1_blocker'];assert blocker==snapshot['blocker']and pn(blocker['path'])=={x:blocker[x]for x in('bytes','sha256')}
 block=decode(text(blocker['path']).encode('utf-8'));assert block['passed']is False and len(block['blocking_findings'])==1
 assert block['subject_producer']==pn(B+'preimage-r1/produce.py')and block['subject_source_manifest']==pn(B+'preimage-r1/source-manifest.json')
 assert delta['r1_passed']is False and delta['r1_actual_permitted']is False and delta['actual_authorized']is False
 for path,q in delta['r1_affected_source_preimages'].items():assert pn(path)==q
 assert delta['external_file_coherence_atomic']is False and delta['external_file_ABA_excluded']is False
 # All other helpers are unchanged. source_guard is the explicit required raw-buffer change.
 producer=text(B+'produce.py');r1producer=text(B+'preimage-r1/produce.py');r69=text('work/reports/war-peace-api-20261016-r69-generator-divisor-source/produce.py')
 t=ast.parse(producer);t1=ast.parse(r1producer);t69=ast.parse(r69)
 helpers=[x.name for x in t1.body if isinstance(x,ast.FunctionDef)and x.name not in('main','source_guard')]
 assert len(helpers)==9 and helpers==delta['unchanged_helper_AST_names']==prep['unchanged_helper_AST_names']
 helperproof=[]
 for name in helpers:
  assert dump(fn(t,name))==dump(fn(t1,name))==dump(fn(t69,name))
  helperproof.append(dict(name=name,AST_sha256=hashlib.sha256(dump(fn(t,name)).encode()).hexdigest()))
 sg=fn(t,'source_guard');assert [x.arg for x in sg.args.args]==['expected_manifest_pin']and not sg.args.defaults
 body=sg.body
 assert isinstance(body[0],ast.Assign)and dump(body[0])==dump(ast.parse("raw_manifest=read_source(HERE/'source-manifest.json')").body[0])
 assert isinstance(body[1],ast.Expr)and isinstance(body[1].value,ast.Call)and body[1].value.func.id=='require'
 bound=ast.parse("{'bytes':len(raw_manifest),'sha256':digest(raw_manifest)}==expected_manifest_pin",mode='eval').body
 assert dump(body[1].value.args[0])==dump(bound)
 assert dump(body[2])==dump(ast.parse('manifest=json.loads(raw_manifest)').body[0])
 assert len([x for x in ast.walk(sg)if isinstance(x,ast.Call)and isinstance(x.func,ast.Name)and x.func.id=='read_source'])==1
 assert len(body)==8 and isinstance(body[6],ast.For)and 'stream_pin(ROOT/name)'in ast.get_source_segment(producer,body[6])
 assert not any(isinstance(x,ast.Call)and isinstance(x.func,ast.Name)and x.func.id=='stream_pin'for b in body[:6]for x in ast.walk(b))
 oldsg=fn(t1,'source_guard');newrest=body[3:];assert dump(ast.Module(body=newrest,type_ignores=[]))==dump(ast.Module(body=oldsg.body[1:],type_ignores=[]))
 # Full main delta: exactly two outer pin checks and two calls now pass base_pin.
 main=fn(t,'main');oldmain=fn(t1,'main');templates=ast.parse(text(B+'main-template.py.inc'))
 assert dump(main)==dump(fn(templates,'main'))
 guards=[x for x in main.body if is_main_file_pin_guard(x)];assert len(guards)==2
 calls=[x for x in ast.walk(main)if isinstance(x,ast.Call)and isinstance(x.func,ast.Name)and x.func.id=='source_guard']
 assert len(calls)==2 and all(len(x.args)==1 and isinstance(x.args[0],ast.Name)and x.args[0].id=='base_pin'and not x.keywords for x in calls)
 normalized=ast.parse(ast.get_source_segment(producer,main));nm=fn(normalized,'main');nm.body=[x for x in nm.body if not is_main_file_pin_guard(x)]
 for x in ast.walk(nm):
  if isinstance(x,ast.Call)and isinstance(x.func,ast.Name)and x.func.id=='source_guard':x.args=[]
 assert dump(nm)==dump(oldmain)
 # Text-level remaining-main equality additionally excludes hidden changes in selection.
 template=text(B+'main-template.py.inc');temp_tree=ast.parse(template);tm=fn(temp_tree,'main');lines=template.splitlines(keepends=True)
 remove=set()
 for node in tm.body:
  if is_main_file_pin_guard(node):remove.update(range(node.lineno-1,node.end_lineno))
 restored=''.join(line for i,line in enumerate(lines)if i not in remove).replace('source_guard(base_pin)','source_guard()')
 assert restored==text(B+'preimage-r1/main-template.py.inc')
 beforeguard,afterguard=sorted(guards,key=lambda x:x.lineno);firstcall=min(calls,key=lambda x:x.lineno)
 assert beforeguard.lineno<firstcall.lineno<afterguard.lineno
 maintext=ast.get_source_segment(producer,main)
 peindex=maintext.index("with(ROOT.parent/'eu4.exe').open('rb')as target")
 assert maintext.index('root_explicit_start_received')<maintext.index("for label in('upstream_scan_review','source_peer_review')")<maintext.index('base,pins=source_guard(base_pin)')<maintext.index("save('claim.json'")<peindex
 for phrase in("auth.get('source_manifest')==base_pin","auth.get('producer_pin')==producer_pin","auth.get('entry_seed_pin')==seed_pin",
  "review.get('scope')=='raw_encoding_anchor_seed_only'","findings.get('subject_capture_pin')==UPSTREAM_CAPTURE_PIN",
  "findings.get('subject_contract_pin')==UPSTREAM_CONTRACT_PIN","findings.get('subject_scan_final_manifest_pin')==UPSTREAM_FINAL_PIN",
  "findings.get('subject_source_manifest')==base_pin","findings.get('subject_producer')==producer_pin","findings.get('subject_entry_seed')==seed_pin"):
  assert phrase in maintext and maintext.index(phrase)<maintext.index('base,pins=source_guard(base_pin)')
 # Complete original containing-interval/window/CFG algorithm remains bounded and explicit.
 for phrase in("len(PADATA)<32","len(PADATA)<29","ANCHOR_SITE+7<=int(chosen['end_exclusive'],16)",
  "int(previous['end_exclusive'],16)<=int(chosen['begin_rva'],16)","int(chosen['end_exclusive'],16)<=int(following['begin_rva'],16)",
  'amount=extent if extent<=8192 else 2048',"raw=target_read(selected_begin,amount,'containing_fragment_code')",
  'analysis=cfg(raw,selected_begin,capstone)',"unknown_anchor_outside_fixed_prefix","unknown_containing_metadata_or_neighbors_unproved"):
  assert phrase in maintext
 record=next(x for x in ast.walk(main)if isinstance(x,ast.FunctionDef)and x.name=='record')
 assert 'len(PADATA)<32'in ast.get_source_segment(producer,record)
 target_read=next(x for x in ast.walk(main)if isinstance(x,ast.FunctionDef)and x.name=='target_read')
 tr=ast.get_source_segment(producer,target_read)
 assert 'rva==selected_begin'in tr and "not any(v['kind']=='containing_fragment_code'for v in PE_READS)"in tr and '0<size<=8192'in tr
 cfg=ast.get_source_segment(producer,fn(t,'cfg'))
 assert 'queue=[begin]'in cfg and 'ANCHOR_SITE'not in cfg and "'callee_followed':False"in cfg
 assert 'if inside:queue.append(target)'in cfg and 'CS_GRP_RET'in cfg and 'read_source('not in cfg and 'target_read('not in cfg and 'open('not in cfg
 assert maintext.index("authenticate('after')")<maintext.index('TARGET_CONTEXT_NORMAL_EXIT=True')<maintext.index('_,post=source_guard(base_pin)')<maintext.index("save('capture.json',value)")
 assert "'whole_pdata_sort_or_aliases_replayed':False"in maintext and "'class_or_mode_verified':False"in maintext and "'further_actual_authorized':False"in maintext
 # Selected retained raw7 anchor and three upstream subject bindings.
 selected_path='work/reports/server-vtable-rip-reference-seeds-20261016-r1/scan-selected-evidence.json'
 cap_path='work/reports/server-vtable-rip-reference-seeds-20261016-r1/capture.json'
 selected=decode(text(selected_path).encode('utf-8'));cap=decode(text(cap_path).encode('utf-8'))
 chosen=[x for x in selected['candidates']if x['site_rva']==0x10d24e3];direct=[x for x in cap['raw_encoding_scan']['candidates']if x['site_rva']==0x10d24e3]
 assert len(chosen)==len(direct)==1 and chosen[0]==seed['selected_candidate_owned']
 raw=bytes.fromhex(seed['raw_anchor7_hex']);disp=struct.unpack('<i',raw[3:])[0]
 assert raw.hex()=='488d05de83c800'and 0x10d24e3+7+disp==0x1d5a8c8 and disp==seed['signed_disp32']==13140958
 assert direct[0]['raw7_hex']==raw.hex()and direct[0]['target_rva']==0x1d5a8c8 and direct[0]['instruction_boundary_verified']is False
 assert chosen[0]['instruction_boundary_verified']is False and seed['constructor_class_mode_layout_or_guard_verified']is False
 oldseed=decode(text(B+'preimage-r1/entry-seed.json').encode('utf-8'));newseed=dict(seed);assert newseed.pop('revision')=='r2'and newseed==oldseed
 oldbudget=decode(text(B+'preimage-r1/budget.json').encode('utf-8'));newbudget=dict(budget);assert newbudget.pop('revision')=='r2'and newbudget==oldbudget
 anchorpath='work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json';anchors=decode(text(anchorpath).encode('utf-8'))
 sections=anchors['sections'];ss=[x for x in sections if x['name']=='.text'];pp=[x for x in sections if x['name']=='.pdata']
 assert len(ss)==len(pp)==1 and pp[0]['virtual_size']%12==0
 assert ss[0]['raw_file_offset']+0x10d24e3-int(ss[0]['rva'],16)==chosen[0]['file_offset']==0x10d18e3
 full_path='work/reports/server-vtable-rip-scan-independent-review-20261016-r1/findings.json';full=decode(text(full_path).encode('utf-8'))
 assert full['sealed']is True and full['passed']is True and full['blocking_findings']==[]
 expected={'subject_capture_pin':pn(cap_path),'subject_contract_pin':pn('work/reports/server-vtable-rip-reference-seeds-20261016-r1/scan-contract.json'),
  'subject_scan_final_manifest_pin':pn('work/reports/server-vtable-rip-reference-seeds-20261016-r1/scan-final-manifest.json')}
 assert seed['future_gate_upstream_exact_subjects']==expected and all(full[k]==q for k,q in expected.items())
 origin=decode(text('work/reports/war-peace-api-20261016-r69-generator-divisor-source/source-manifest.json').encode('utf-8'))
 assert origin['decoder_expected_witness_pins']==m['decoder_expected_witness_pins']and all(path.startswith('work/deps/capstone-5.0.7/')for path in m['decoder_expected_witness_pins'])
 # Syntax-only first failure is preserved, followed by first prepare/check; no actual retry.
 failbase=B+'source-syntax-failure-r1/';fail=decode(text(failbase+'failure.json').encode('utf-8'))
 assert 'IndentationError'in text(failbase+'stderr.txt')
 assert len([path for path in f if path.startswith(failbase)and path.endswith(('.py','.inc','.md','.json'))])>=6
 run=obj('source-run-receipt.json');assert run['all_children_collected']is True and run['producer_engine_PE_tests_auth_claim_operations']==0
 assert len(run['commands'])==2 and all(x['exit_code']==0 for x in run['commands'])
 assert prep['actual_source_pins']==m['actual_source_pins']and len(prep['unchanged_helper_AST_names'])==9
 assert prep['returned_bytes']==sum(x['bytes']for x in prep['read_events'])==1152608
 assert fc['returned_bytes']==sum(x['bytes']for x in fc['read_events'])==783746 and fc['passed']is True and fc['blocking_findings']==[]
 assert receipt['recorded_prepare_check_finalize_bytes']==1152608+783746+receipt['finalizer_explicit_bytes']==3922191
 assert receipt['preparation_stage_conservative_upper_bytes']==3922191+8388608+2097152==14407951<16*1024*1024
 assert receipt['allowance_is_not_observed_IO']is True and receipt['complete_OS_IO_not_claimed']is True
 assert receipt['future_producer_actual_charge_limit_bytes']==32*1024*1024 and receipt['future_retained_seal_limit_bytes']==16*1024*1024
 estimate=2*sum(x['bytes']for x in m['source_pins'].values())+2*1024*1024+65536
 assert estimate==prep['estimated_future_producer_IO_with2MiB_review_reserve_plus64KiB_ancillary']==19360910
 assert receipt['future_producer_estimate_plus_manifest_guard_reserve']==estimate+6*SUBJECT['source-manifest.json']['bytes']==19505450
 for field in('PE_stat_open_hash','decoder_operations','producer_executions','tests','game_process_accesses','Frida_operations','native_calls','requests'):assert receipt[field]==0
 for field in('auth_or_claim_created','actual_authorized','native_ready','class_or_mode_verified','host_guard_change_authorized','world_lease','atomic_snapshot','external_file_ABA_excluded','independent_source_review_passed'):assert receipt[field]is False
 assert receipt['first_R2_syntax_error_preserved']is True and receipt['R1_blocked_not_passed']is True
 # All admitted R2 final graph text is checked again, without walking metadata engines/history.
 for path,e in f.items():read(path,{x:e[x]for x in('bytes','sha256')})
 upper=c['source_bytes']+2*CACHE['bytes']+OLD_CACHE['bytes']+1024*1024+sum(x['bytes']for x in reads)+2*1024*1024;assert upper<LIMIT
 ops={x:0 for x in('PE_stat_open','engine_stat_open','Capstone_decoder','reviewed_producer_prepare_check_finalizer_execution','fixtures','tests','game_process','Frida','native_game_calls','requests','actual_auth_claim_created','new_callee_vslot_header_unwind_context_follow')}
 authority={x:False for x in('native_ready','callable','reader_adoption_allowed','selected_effect_verified','class_or_mode_verified','host_guard_change_authorized','world_lease','atomic_snapshot','external_file_ABA_excluded','authorizes_retry','actual_authorized','further_actual_authorized')}
 replay=write('source-replay.json',dict(schema='EU4-R72-R2-SOURCE-REPLAY/1',sealed=True,passed=True,
  raw_manifest_guard=dict(read_once=True,bytes_and_SHA256_exact_before_parse=True,parse_precedes_engine_loop=True,pre_and_post_calls_pass_authorized_base_pin=True,
   raw_buffer_pinned_not_external_atomic=True,outer_initial_file_pin_checks=2,final_file_pin_check_preserved=True),
  nine_other_helpers_AST_equal=helperproof,main_only_two_outer_guards_and_two_arguments_delta=True,main_remaining_text_exact_R1=True,
  containing_algorithm_identical_to_R1=True,selected_anchor=dict(site='0x10d24e3',raw7=raw.hex(),signed_disp32=disp,target='0x1d5a8c8',boundary_currently_proved=False),
  R1_preimages_exact_count=18,R1_blocker=blocker,R1_remains_blocked=True,source_syntax_failure_preserved=True,
  current_final_flat_prepost_files=61,final_manifest_files=56,explicit_postseal_delivery_texts=extra,actual_source_pins=26,engine_metadata_only=38))
 findings=write('findings.json',dict(schema='EU4-R72-R2-INDEPENDENT-SOURCE-REVIEW/1',sealed=True,passed=True,blocking_findings=[],
  subject_source_manifest=SUBJECT['source-manifest.json'],subject_producer=SUBJECT['produce.py'],subject_entry_seed=SUBJECT['entry-seed.json'],
  scope='R72 R2 complete nonauthor source/budget/producer plus R1 narrow repair review only; no actual authorization',source_replay=replay,
  reviewer_role=dict(R69_original_template_source_preparer=True,R72_source_author='validation_audit',R69_independent_source_peer='diplomacy_static',
   upstream_R70_full_scan_root_review_is_retained_witness=True,engine_body_reauthenticated_here=False),
  checks=dict(final_flat_source_pins=56,current_flat_files=61,explicit_postseal_delivery_texts=3,actual_source_pins=26,engine_metadata_only=38,nine_other_helper_ASTs_equal=True,
   rawbuffer_pin_check_dominates_parse_and_engine_loop=True,two_source_guard_calls_bind_base_pin=True,outer_pre_post_basefile_guards=True,
   remaining_main_exact_R1=True,rawanchor7_arithmetic_and_selected_sources_equal=True,upstream_fullreview_three_subjects_bound=True,
   three_reviews_and_root_exactsubjects_before_engine_PE=True,unique_containing_neighbor_conditions=True,metadata_limit32=True,
   window_from_selected_begin_full8192_else_prefix2048=True,no_anchor_reseed_or_window_chase=True,normal_target_close_before_final_guard_and_capture=True,
   source_syntax_failure_and_R1_preimages_preserved=True,all_current_flat_prepost_pins_equal=True),
  repaired_blocker=dict(initial=blocker,resolution='source_guard(expected_manifest_pin) validates one raw buffer exact bytes/SHA before parse and engine selection; both main calls bind base_pin and initial outer checks bracket guard.',R1_passed=False,R2_only_source_ready=True),
  precision_notes=[
   'R1 remains blocked and frozen. All18 R2 snapshots match the independently owned prior-stage R1 bytes. Original R1 current-file preservation beyond that prior intake remains author retained-read witness; this review does not reopen originalR1programs or recursively authenticate historical graphs.',
   'The raw buffer used to select engine pins is now checked against the authorization-bound pin before JSON parse and any source/engine loop. Both guard calls receive base_pin, and the initial outer file pin is checked before/after. This is exact buffer binding, not external atomic coherence or an ABA exclusion.',
   'All nine remaining helpers are AST-equal to R69 and blockedR1. source_guard is the explicit narrow repair. Main rest is AST and byte-text equal after removing two new checks and two arguments; containing selection/window/CFG logic is unchanged.',
   'Only raw7 at10d24e3 is selected, signed RIP arithmetic leads1d5a8c8. Retained R70 scan/fullreview remain witnesses, not a new PE scan, instruction-boundary proof, vtable/class/type/constructor/mode or host-guard compatibility proof.',
   'Future metadata is at most32records, selected contains all7bytes and immediate neighbors must be disjoint under ordered-pdata premise. Entire-table ordering/arbitrary nonneighbor aliases remain unknown. Missing selection yields unknown with zero code reads.',
   'Future code starts at selected.begin: full extent<=8192, otherwise fixed first2048. An uncovered/unreached/mismatched anchor remains unknown, with no second window/anchor CFG seed. Only already-owned local branch bytes are traversed; no callees/vslots/data/header/unwind or other candidates are followed.',
   'New root exact grant plus raw/fullupstream/sourcepeer three subject-bound reviews precede engine/PE; this review supplies only the sourcepeer gate. No claim/auth/actual run was created here. Success capture is after normal targetfile context exit and final guards; failure completed journals are not exhaustive attempted I/O.',
   'The first R2 IndentationError was syntax-only before prepare execution; five source preimages/fullstderr remain pinned. Later prepare/check each have their first exit0; no producer, old test, fixture or actual scope was retried.',
   '38 locked Capstone identities are metadata-only. Future source32MiB/retained16MiB and estimates are conditional explicit-read bounds, not allOS I/O. Software768MiB/1GiBstop is not a hard Job/treewide memory guarantee; finalizer peak is finalizer-only.',
   'The reviewer originally prepared R69 template source; its D sourcepeer remains separate. R72 is authored by Val, root R70 full/raw review are retained witnesses, and this review does not independently redesign or authenticate decoder bodies.',
   'Own reviewR1 expected all prepared-delivery local pins inside the earlier56-file final manifest. Three explicitly pinned postseal logs/status files were later published; R2 admits only those named texts and verifies their pins. ExactR1source/failure preserved, source/algorithms unchanged; failed903989B+621515B cache reads charged.'
  ],author_frozen_sources_need_change=False,
  author_resource_witness=dict(recorded_prepare_check_finalize_bytes=3922191,additional_IO_allowance=8388608,receipt_pin_allowance=2097152,preparation_upper=14407951,
   future_source_estimate=19505450,future_source_limit=32*1024*1024,future_retained_limit=16*1024*1024,engine_metadata_only=38,actual_runs=0),
  prior_R1_review_stage_accounting=dict(intake_source_bytes=568356,retained_inspection_bytes=621515,manual_inspection_upper_allowance=1048576,
   explicit_conservative_stage_upper=568356+621515+1048576,stage_is_separate_not_hidden_in_R2=True,initial_blocker_pin={x:blocker[x]for x in('bytes','sha256')}),
  independent_resources=dict(current_intake_bytes=c['source_bytes'],prior_R2_cache_inspection_bytes=CACHE['bytes'],prior_failed_review_cache_bytes=CACHE['bytes']+OLD_CACHE['bytes'],small_manual_inspection_allowance=1024*1024,
   current_cache_R1ownedcache_and_postguard_bytes=sum(x['bytes']for x in reads),own_sealing_reserve=2*1024*1024,
   listed_analysis_upper_bytes=upper,stage_limit=LIMIT,ordinary_file_limit=FILE,own_peak_bytes=peak,memory_limit=MEM),
  operations=ops,authority=authority,all_shells_collected=True,next_scope_auto_authorized=False))
 report=b'R72 R2 source review passed only for new ba3735/902a290/0ad3ae subjects. Single raw manifest pin dominates parse/engine loop; both calls bind authorized base_pin; two initial outer checks/final check retained. Nine other helper ASTs and remaining main text unchanged. R1 remains blocked. No actual/PE/engine/decoder/producer/tests/game/native operations.\n'
 with(OUT/'report.md').open('xb')as fz:fz.write(report)
 local={O+n:pin((OUT/n).read_bytes())for n in('retained-files.json','source-replay.json','findings.json','report.md','reviewer-r1-source.py','review-failure.json')}
 local[OLD_CACHE_PATH]=OLD_CACHE
 for path in('work/retain_r72_r2_source_review_20261016.py','work/review_r72_r2_source_20261016.py'):local[path]=pin((ROOT/path).read_bytes())
 mp=write('manifest.json',dict(schema='EU4-R72-R2-SOURCE-REVIEW-MANIFEST/1',sealed=True,source_pins={path:pn(path)for path in f},local_pins=local,
  engine_witness_metadata_count=38,engine_body_opened=False,findings=findings,operations=ops,authority=authority))
 print(json.dumps(dict(passed=True,findings=findings,manifest=mp,replay=replay,analysis_upper=upper,peak=peak,all_shells_collected=True)))
def check():
 m=decode(read(O+'manifest.json'))
 for path,q in(m['source_pins']|m['local_pins']).items():read(path,q)
 f=decode(read(O+'findings.json',m['local_pins'][O+'findings.json']))
 upper=f['independent_resources']['listed_analysis_upper_bytes']+sum(x['bytes']for x in reads);assert upper<LIMIT
 vp=write('verification.json',dict(schema='EU4-R72-R2-SOURCE-REVIEW-VERIFICATION/1',sealed=True,passed=True,pins_checked=len(m['source_pins']|m['local_pins']),
  sourcepins_current_equal=True,engine_metadata_only=38,complete_R2_stage_upper_bytes=upper,stage_limit=LIMIT,own_peak_bytes=peak,
  operations=m['operations'],authority=m['authority'],all_shells_collected=True))
 print(json.dumps(dict(passed=True,verification=vp,pins=len(m['source_pins']|m['local_pins']),complete_upper=upper,peak=peak)))
if __name__=='__main__':
 try:check()if sys.argv[1:]==['--check']else main()
 except BaseException as exc:
  n='verification-failure.json'if sys.argv[1:]==['--check']else'review-r2-failure.json'
  if not(OUT/n).exists():write(n,dict(type=type(exc).__name__,detail=str(exc),reads=reads,peak=peak,author_sources_unchanged=True,no_author_program_PE_engine_decoder_game_native=True))
  raise
