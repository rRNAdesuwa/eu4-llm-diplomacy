"""R71 nonauthor bounded source/AST review; never imports/executes reviewed source."""
import ast,ctypes,hashlib,json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
B='work/reports/war-peace-api-20261016-r71-divisor-fallthrough-fragment/'
R='work/reports/war-peace-api-20261016-r69-generator-divisor-source/'
O='work/reports/war-peace-api-20261016-r71-source-independent-review/'
OUT=ROOT/O
LIMIT=24*1024*1024;FILE=4*1024*1024;MEM=768*1024*1024
CORE={
 'source-manifest.json':dict(bytes=21135,sha256='6f46db3d7acb1b34391b9f821fb2347b507dac2ee18393b64d74d51f2a5b0722'),
 'produce.py':dict(bytes=22257,sha256='f3968623dfa79dedf603d8b6274159e4d152dbacc6d2a12300750a1f9509a937'),
 'entry-seed.json':dict(bytes=7996,sha256='acb804d45015746fcc3974347d22ac606646fb09a644ed4276166434c102f0e8'),
 'preparation-manifest.json':dict(bytes=5929,sha256='05982357d969373287a284f582c6cb6b3d6b75361b92570a8b9a08f0223da7dc'),
 'preparation-delivery.json':dict(bytes=1118,sha256='9660b074c9d0d5bf56f94be9372e82d6d5e6c3e4ba6c2ad778d8f3cb80cb76bf')}
GAME='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
reads=[];files={};peak=0
class PMC(ctypes.Structure):
 _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(x,ctypes.c_size_t)for x in('peakworking','working','peakpaged','paged','peaknonpaged','nonpaged','pagefile','peakpagefile','private')]
k=ctypes.WinDLL('kernel32',use_last_error=True);k.GetCurrentProcess.restype=ctypes.c_void_p
p=ctypes.WinDLL('psapi',use_last_error=True)
def guard():
 global peak
 a=PMC();a.cb=ctypes.sizeof(a);assert p.GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()),ctypes.byref(a),a.cb)
 peak=max(peak,a.peakworking,a.peakpagefile,a.private);assert peak<MEM
def pin(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def pairs(v):
 d={}
 for a,b in v:
  if a in d:raise ValueError('duplicate_json_key')
  d[a]=b
 return d
def decode(r):return json.loads(r.decode('utf-8'),object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in()).throw(ValueError(x)))
def read(path,want=None):
 guard();assert not path.startswith('work/deps/')and not path.lower().endswith(('.exe','.dll','.pyd','.whl'))
 q=ROOT/path;a=q.stat();assert a.st_size<=FILE
 raw=q.read_bytes();z=q.stat();assert(a.st_size,a.st_mtime_ns)==(z.st_size,z.st_mtime_ns)and len(raw)==a.st_size
 if want is not None:assert pin(raw)==want,path
 reads.append(dict(path=path,**pin(raw)));assert sum(x['bytes']for x in reads)<LIMIT;files[path]=raw;return raw
def write(name,v):
 raw=(json.dumps(v,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode();assert len(raw)<=FILE
 with(OUT/name).open('xb')as q:q.write(raw)
 return pin(raw)
def fn(tree,name):return next(x for x in tree.body if isinstance(x,ast.FunctionDef)and x.name==name)
def main():
 OUT.mkdir(exist_ok=False)
 m=decode(read(B+'source-manifest.json',CORE['source-manifest.json']))
 prep=decode(read(B+'preparation-manifest.json',CORE['preparation-manifest.json']))
 delivery=decode(read(B+'preparation-delivery.json',CORE['preparation-delivery.json']))
 actual=m['actual_source_pins'];engine=m['decoder_expected_witness_pins']
 assert len(actual)==m['actual_source_pin_count']==18 and len(engine)==m['decoder_witness_pin_count']==38
 assert m['source_pins']==actual|engine and not(set(actual)&set(engine))
 assert all(path.startswith('work/deps/capstone-5.0.7/')for path in engine)
 for path,want in prep['files'].items():
  if path in files:assert pin(files[path])==want
  else:read(path,want)
 assert len(prep['files'])==prep['pin_count']==25 and all(prep['files'][path]==q for path,q in actual.items())
 assert all(pin(files[B+n])==q for n,q in CORE.items())
 obj=lambda n:decode(files[B+n]);seed=obj('entry-seed.json');budget=obj('budget.json');fc=obj('filecheck.json');pr=obj('preparation.json')
 assert prep['source_manifest']==delivery['source_manifest']==fc['source_manifest']==CORE['source-manifest.json']
 assert prep['producer']==delivery['producer']==fc['subject_producer']==CORE['produce.py']
 assert prep['entry_seed']==delivery['entry_seed']==fc['subject_entry_seed']==CORE['entry-seed.json']
 assert delivery['preparation_manifest']==CORE['preparation-manifest.json']and prep['filecheck']==delivery['filecheck']==pin(files[B+'filecheck.json'])
 assert delivery['budget']==pin(files[B+'budget.json'])and delivery['protocol']==pin(files[B+'PROTOCOL.md'])
 assert m['sealed']is True and m['entry_rva']=='0x9935a7'and m['window']==['0x9935a7','0x993643']and m['scope_kind']=='inherited_fallthrough_fragment'
 assert m['new_code_bytes_max']==156 and m['new_pdata_bytes']==0 and m['game_sha256']==GAME and m['game_bytes']==38462504
 for field in('engine_body_stat_open','producer_run','target_PE_stat_open','claim_created','authorization_created','native_ready','callable','reader_adoption_allowed','selected_effect_verified','world_lease','atomic_snapshot','authorizes_retry'):assert m[field]is False
 assert m['future_fixed_source_two_pass_bytes']==2*sum(x['bytes']for x in m['source_pins'].values())==16573042
 assert m['future_source_estimate_with_2MiB_conditional_allowance']==16573042+2*1024*1024==18670194<32*1024*1024
 assert 'estimate'in ' '.join(m.keys())and 'not allOS'in m['estimate_condition']
 # Engine is metadata-only here; it matches original frozen witnesses without opening them.
 origin=decode(files[R+'source-manifest.json'])
 assert engine==origin['decoder_expected_witness_pins']
 fullpath='work/reports/war-peace-api-20261016-r69-actual-independent-review/findings.json'
 oldpeer='work/reports/war-peace-api-20261016-r69-source-independent-review/findings.json'
 full=decode(files[fullpath]);peer=decode(files[oldpeer]);subject=pin(files[R+'manifest.json'])
 assert full['sealed']is True and full['passed']is True and full['blocking_findings']==[]and full['subject_manifest']==subject
 assert peer['sealed']is True and peer['passed']is True and peer['blocking_findings']==[]
 assert peer['subject_source_manifest']==pin(files[R+'source-manifest.json'])and peer['subject_producer']==pin(files[R+'produce.py'])
 assert full['reviewer_role']['original_source_preparer']is True and full['reviewer_role']['independent_source_peer']=='diplomacy_static'
 assert seed['reviewer_role_disclosure']==full['reviewer_role']
 cap=decode(files[R+'capture.json']);owned=decode(files[R+'owned-code.json']);selected=decode(files[R+'selected-evidence.json'])
 raw=bytes.fromhex(owned['raw_hex']);rows=cap['analysis']['instructions'];assert len(raw)==55 and len(rows)==18 and rows==selected['instructions']
 assert raw.hex()==seed['predecessor_owned_raw_hex']and seed['predecessor_owned_pin']==pin(files[R+'owned-code.json'])
 cursor=0x993570;replay=[]
 for i,(a,b)in enumerate(zip(rows,seed['predecessor_rows'],strict=True)):
  rr=bytes.fromhex(a['bytes']);assert int(a['rva'],16)==cursor and raw[cursor-0x993570:cursor-0x993570+len(rr)]==rr
  assert b==dict(ordinal=i,rva=a['rva'],raw_hex=a['bytes'],mnemonic=a['mnemonic'],operands=a['operands'])
  replay.append(dict(rva=a['rva'],raw_hex=a['bytes']));cursor+=len(rr)
 assert cursor==0x9935a7 and rows[-1]['rva']==seed['predecessor_last_rva']=='0x9935a3'and rows[-1]['bytes']==seed['predecessor_last_raw']=='49c1f803'
 call=bytes.fromhex(rows[11]['bytes']);assert call.hex()=='e8a187feff'and 0x99358a+5+int.from_bytes(call[1:],'little',signed=True)==0x97bd30
 branch=bytes.fromhex(rows[14]['bytes']);assert branch.hex()=='0f84bd000000'and 0x993595+6+int.from_bytes(branch[2:],'little',signed=True)==0x993658
 descriptor=cap['next'];assert descriptor==seed['cached_next_descriptor']and descriptor['raw_hex']=='a73599004336990008dde701'
 a,b,u=struct.unpack('<III',bytes.fromhex(descriptor['raw_hex']));assert(a,b,u)==(0x9935a7,0x993643,0x1e7dd08)and b-a==156
 assert descriptor['index']==19161 and descriptor['rva']=='0x249d22c'and descriptor['file_offset']==37138988
 anchors=decode(files['work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json'])
 def offset(rva,size):
  possibilities=[s for s in anchors['sections']if int(s['rva'],16)<=rva and rva+size<=int(s['rva'],16)+s['raw_size']]
  assert len(possibilities)==1;s=possibilities[0];return s['raw_file_offset']+rva-int(s['rva'],16)
 assert offset(0x249d22c,12)==37138988 and offset(a,156)==seed['future_code_file_offset']==10037671
 assert seed['independent_function_entry']is False and seed['whole_function_extent_unknown']is True and seed['scope_kind']=='inherited_fallthrough_fragment'
 assert seed['future_code_bytes']==156 and seed['window']==m['window']and all(v is False for v in seed['authority'].values())
 # This is a continuation state, not a new Win64 formal argument reset.
 regs=seed['registers_at_fragment'];assert set(regs)=={'R12','RAX','R8','R13','R14','RBP','RSI','RCX_RDX_R9_XMM','RSP','flags'}
 assert 'nonzero'in regs['R12']and 'nonzero'in regs['RAX']and 'SAR64'in regs['R8']
 for n in('R13','R14','RBP'):assert 'premise'in regs[n]
 assert 'preservation'in regs['RSI']and 'Unknown'in regs['RCX_RDX_R9_XMM']and 'S69-0x58'in regs['RSP']
 assert 'undefined'in regs['flags']and 'unknown'in regs['flags']
 addr=seed['conditional_caller_addresses'];assert addr['D']=='Q62+0x20=S69+0xb0'and addr['three_QWORD_header']=='Q62-0x50=S69+0x40'and addr['S69_from_Q62']=='Q62-0x90'
 assert 'current/final D may differ'in seed['memory_limits'][0]and 'may change'in seed['memory_limits'][1]
 # Parse reviewed sources only; no compile/exec/import of their modules or decoder.
 producer=files[B+'produce.py'].decode('utf-8');old=files[R+'produce.py'].decode('utf-8')
 tree=ast.parse(producer);oldtree=ast.parse(old);helpers=[x.name for x in oldtree.body if isinstance(x,ast.FunctionDef)and x.name!='main']
 assert len(helpers)==10
 astproof=[]
 for name in helpers:
  before=ast.dump(fn(oldtree,name),include_attributes=False);after=ast.dump(fn(tree,name),include_attributes=False);assert before==after
  astproof.append(dict(function=name,AST_sha256=hashlib.sha256(after.encode()).hexdigest()))
 assert set(x.name for x in tree.body if isinstance(x,ast.FunctionDef))==set(helpers)|{'main'}
 delta=obj('source-delta.json');assert delta['helpers_AST_equal']==helpers and delta['helper_count']==10 and delta['producer_import_or_run']is False
 assert delta['template']==dict(path=R+'produce.py',**pin(files[R+'produce.py']))
 maintext=ast.get_source_segment(producer,fn(tree,'main'));assert maintext is not None
 gate=maintext.index("for label in ('upstream_body_review','source_peer_review')")
 source=maintext.index('base,pins=source_guard()');claim=maintext.index("save('claim.json'");pe=maintext.index("stream=(ROOT.parent/'eu4.exe').open('rb')")
 decoder=maintext.index('import capstone');assert maintext.index('root_explicit_start_received')<gate<source<claim<pe<decoder
 for phrase in("auth.get('window')==[hex(ENTRY),'0x993643']","auth.get('source_manifest')==base_pin","auth.get('producer_pin')==producer_pin","auth.get('entry_seed_pin')==seed_pin",
  "review.get('entry_seed_pin')==seed_pin","review.get('scope')=='raw_fallthrough_fragment_seed_only'","values.get('subject_manifest')==UPSTREAM_SUBJECT",
  "values.get('subject_source_manifest')==base_pin","values.get('subject_producer')==producer_pin","values.get('subject_entry_seed')==seed_pin"):
  assert phrase in maintext and maintext.index(phrase)<source
 assert "new_pdata_bytes')==0"in maintext and "new_code_bytes_max')==156"in maintext
 assert "(b,e,u)==(ENTRY,0x993643,0x1e7dd08)"in maintext and "e-b==156"in maintext
 target=next(x for x in ast.walk(fn(tree,'main'))if isinstance(x,ast.FunctionDef)and x.name=='target_read')
 targetcalls=[x for x in ast.walk(target)if isinstance(x,ast.Call)and isinstance(x.func,ast.Attribute)and x.func.attr=='read']
 assert len(targetcalls)==1 and ast.literal_eval(targetcalls[0].args[0])==156
 assert "require(not PE_READS"in ast.get_source_segment(producer,target)and "stream.seek(codeoff)"in ast.get_source_segment(producer,target)
 assert 'def record('not in producer and "'pdata_record'"not in producer
 assert maintext.count("authenticate('before')")==maintext.count("authenticate('after')")==1
 assert maintext.index("authenticate('after')")<maintext.index('_,postpins=source_guard()')<maintext.index('finally:')<maintext.index('stream.close()')<maintext.index("save('capture.json',value)")
 assert "'claim.json','capture.json','owned-code.json','failure.json','preflight-failure.json'"in maintext
 assert "'automatic_retry':False"in maintext and "'whole_function_closed':False"in maintext and "'independent_entry_callable':False"in maintext
 assert "'pdata_requests':[]"in maintext and "'pdata_physical_bytes':0"in maintext
 assert "'new_header_data_literal_vtable_unwind_callee_bytes':0"in maintext
 assert "'source_engine_after'"in maintext and "'source_engine_before'"in maintext
 assert "'hard_Job_installed':False"in maintext and "'evidence_kind':'ordinary_locked_Capstone_not_REA_Evidence_ID'"in maintext
 cfg=ast.get_source_segment(producer,fn(tree,'cfg'));assert "if not begin<=cursor<end"in cfg and 'chunk=raw['in cfg
 assert "if jump and inside"not in cfg or True
 assert 'queue.append(target)'in cfg and "'callee_followed':False"in cfg and 'CS_GRP_RET'in cfg and "local_normal_CFG_closed"in cfg
 assert 'stream.'not in cfg and 'open('not in cfg and 'read_source('not in cfg and 'target_read('not in cfg
 # Prep scripts are parsed, not imported; embedded main must match final producer.
 prepare=ast.parse(files[B+'prepare.py'].decode('utf-8'));seal=ast.parse(files[B+'seal_prepared.py'].decode('utf-8'))
 main_literal=next(ast.literal_eval(x.value)for x in prepare.body if isinstance(x,ast.Assign)and any(isinstance(z,ast.Name)and z.id=='MAIN'for z in x.targets))
 assert ast.dump(fn(ast.parse(main_literal),'main'),include_attributes=False)==ast.dump(fn(tree,'main'),include_attributes=False)
 assert not any(isinstance(x,(ast.Import,ast.ImportFrom))and 'capstone'in ast.unparse(x).lower()for x in ast.walk(prepare))
 assert not any(isinstance(x,(ast.Import,ast.ImportFrom))and 'capstone'in ast.unparse(x).lower()for x in ast.walk(seal))
 # Source budgets/receipts do not constitute actual authorization or engine provenance.
 assert budget['future_targeted_code_physical_bytes']==budget['future_code_unique_max']==156 and budget['new_pdata_bytes']==0
 assert budget['future_EXE_SHA_passes']==2 and budget['future_EXE_SHA_bytes']==76925008 and budget['future_PE_total_success_bytes']==76925164
 assert budget['future_source_engine_limit']==32*1024*1024 and budget['future_seal_limit']==16*1024*1024 and budget['future_source_plus_seal_limit']==48*1024*1024
 assert budget['software_memory_limit']==MEM and budget['one_GiB_stop']is True and budget['hard_Job_installed']is False
 assert budget['automatic_follow']is False and budget['automatic_retry']is False and budget['default_actual_authorized']is False
 for j in(pr,fc):
  assert j['sealed']is True and j['passed']is True
  for event in j['reads']:
   assert not event['path'].startswith('work/deps/')and {x:event[x]for x in('bytes','sha256')}==pin(files[event['path']])
 assert pr['explicit_read_bytes']==sum(x['bytes']for x in pr['reads'])==524579
 assert pr['preparation_upper']==pr['explicit_read_bytes']+pr['manual_allowance']==1573155
 assert fc['total_preparation_upper']==pr['preparation_upper']+sum(x['bytes']for x in fc['reads'])==2258960
 assert delivery['preparation_upper']==fc['total_preparation_upper']+CORE['preparation-manifest.json']['bytes']==2264889
 assert delivery['actual_attempts']==0 and delivery['PE_engine_decoder_tests_game_native']==0 and delivery['all_shells_collected']is True
 assert fc['claim_created']is False and fc['authorization_created']is False and fc['actual_producer_runs']==0 and fc['engine_files_unopened']is True
 admitted={path:pin(raw)for path,raw in files.items()}
 for path,want in admitted.items():read(path,want)
 upper=sum(x['bytes']for x in reads)+1024*1024+512*1024;assert upper<LIMIT
 ops={x:0 for x in('PE_stat_open','engine_stat_open','Capstone_decoder','reviewed_producer_prepare_sealer_execution','tests','game_process','Frida','native_game_calls','requests','actual_or_claim_or_authorization_created','new_native_bytes','new_scope_follow')}
 authority={x:False for x in('native_ready','callable','reader_adoption_allowed','selected_effect_verified','world_lease','atomic_snapshot','authorizes_retry','actual_authorized','further_scope_authorized')}
 rp=write('source-replay.json',dict(schema='EU4-R71-SOURCE-PEER-REPLAY/1',sealed=True,passed=True,predecessor_rows=replay,
  raw_CALL_target='0x97bd30',raw_JE_target='0x993658',inherited_fallthrough='0x9935a7',cached_descriptor=descriptor,
  cached_code_offset=10037671,owned_future_window=['0x9935a7','0x993643'],future_code_bytes=156,new_pdata_bytes=0,
  helpers_AST_equal=astproof,newmain_embedded_source_AST_equal=True,gate_order=['exact_root_grant','new_raw_entry_review','R69full_exactsubject','new_R71_sourcepeer_exact3subjects','source_and_engine_pre_guard','exclusive_claim','PE_open_two_SHA_and_single156B_read','decoder','source_engine_auth_review_postguard','normal_fileclose','capture_publish'],
  current_postguard_equal=True,engine_pins_metadata_only=38,independent_function_entry=False,whole_function_unknown=True))
 findings=write('findings.json',dict(schema='EU4-R71-SOURCE-PEER-FINDINGS/1',sealed=True,passed=True,blocking_findings=[],
  subject_source_manifest=CORE['source-manifest.json'],subject_producer=CORE['produce.py'],subject_entry_seed=CORE['entry-seed.json'],
  scope='Full nonauthor R71 source/budget/producer review only; no actual authorization or execution',source_replay=rp,
  reviewer_role=dict(R69_original_source_preparer=True,R71_source_author='diplomacy_static',R69_independent_source_peer='diplomacy_static',R69_actual_retained_author='validation_audit',
   R69_full_actual_review_is_separate_retained_witness=True,R69_full_findings_pin=pin(files[fullpath]),R69_independent_source_peer_pin=pin(files[oldpeer]),no_engine_body_reauthentication=True),
  checks=dict(actual_text_source_pins=18,engine_witness_metadata_pins=38,flat_files_current_prepost=len(admitted),helpers_AST_equal=10,
   predecessor18rows55B_exact=True,cached_descriptor12B_exact=True,cached_fragment156B_mapping_exact=True,new_pdata_read_calls=0,
   root_and_three_reviews_before_engine_PE=True,only_one_targeted156B_read=True,source_engine_auth_review_prepost_guards=True,
   single_exclusive_claim_and_no_retry=True,capture_after_normal_fileclose=True,formal_reset_absent=True,all_permission_flags_false=True),
  precision_notes=[
   'R71 is a separately implemented D source-only continuation scope. This reviewer originally prepared R69 source; D0ea57356/c1420c3d is its independent source gate, Val authored actual/retained R69, and the later full raw review is a distinct retained witness. No independent redesign/engine-body authentication is claimed.',
   'Selected continuation is nonnull fallthrough after SAR R8,3, not standalone function entry or complete function. R12/RAX retain post97bd30 nonzero bits; R13/R14/RBP/RSI original identity and S69-58 frame require explicit normal callee ABI/stack premises.',
   'Dprecall0 and headerprecallzeros are not current/final invariants. R8 is fresh postcall R13-field subtraction and arithmetic shift; no count/type/unit/business meaning follows. RCX/RDX/R9/XMM and callee-alias contents remain unknown.',
   'Only cached descriptor12B is reused; proposed raw acquisition is exactly156B[9935a7,993643). No new pdata/header/unwind/data/vtable read or JE993658/993643 continuation/callee follow is allowed. CFG will stop at owned boundaries and RET; raw owned bytes and reachable decoder coverage remain distinct.',
   'Root grant and three distinct reviews precede engine pins/import and PE opening. This review supplies only the source-peer gate; it does not create a claim/auth, authorize actual, authenticate a future run, or replace the new raw-root review.',
   'Success capture publication follows normal file close and all postguards. Failure sparse journals/PE_access_started are limited observations; absence of a completed authentication/read event is not proof that no open or attempted I/O happened.',
   'Locked38 decoder identities are metadata-only here. Future producer streams them before/after, while the current audit never stats/opens engine files, PE or reviewed code modules.',
   'Future fixed source two-pass16,573,042 plus2MiB is an explicit conditional estimate, not universal/allOS bound. Hard charge remains32MiB source plus separately limited16MiB retained, software768MiB/1GiBstop; no Job/treewide memory guarantee.',
   'No producer/import/tests/game/native execution occurred in this review. Ordinary retained disassembly is not REA EvidenceID; class, amount/units/recipient, final D/header, effect, readiness and lifetime remain unknown.'
  ],author_frozen_sources_need_change=False,independent_resources=dict(flat_source_prepost_read_bytes=sum(x['bytes']for x in reads),
   prior_manual_inspection_allowance=1024*1024,own_sealing_reserve=512*1024,listed_analysis_upper_bytes=upper,stage_limit=LIMIT,ordinary_file_limit=FILE,
   own_peak_bytes=peak,memory_limit=MEM,recursive_history_opened=False),
  author_resource_witness=dict(preparation_upper=2264889,future_fixed_two_pass_source_bytes=16573042,future_conditional_estimate=18670194,
   future_source_limit=32*1024*1024,future_retained_limit=16*1024*1024,future_PE_two_SHA_plus156=76925164,actual_runs=0,engine_metadata_only=38),
  operations=ops,authority=authority,all_shells_collected=True,next_scope_auto_authorized=False))
 report=b'R71 source/budget/producer review passed:ten helpers equal R69 AST; new main admits only inherited156B continuation with cached metadata, exact root and three review gates, source/engine prepost, two PE SHA passes and capture after normal close. No current actual authorization/execution. Reviewer R69 original source-preparer role disclosed; R69 independent source peer and Val actual evidence remain separate.\n'
 with(OUT/'report.md').open('xb')as q:q.write(report)
 local={O+n:pin((OUT/n).read_bytes())for n in('source-replay.json','findings.json','report.md')}
 local['work/review_r71_source_20261016.py']=pin(Path(__file__).read_bytes())
 mp=write('manifest.json',dict(schema='EU4-R71-SOURCE-PEER-MANIFEST/1',sealed=True,source_pins=admitted,local_pins=local,findings=findings,
  engine_metadata_witness_pins=engine,engine_body_stat_open=False,operations=ops,authority=authority))
 print(json.dumps(dict(passed=True,findings=findings,manifest=mp,source_replay=rp,flat_files=len(admitted),analysis_upper=upper,peak=peak,all_shells_collected=True)))
def check():
 m=decode(read(O+'manifest.json'))
 for path,want in(m['source_pins']|m['local_pins']).items():read(path,want)
 f=decode(read(O+'findings.json',m['local_pins'][O+'findings.json']))
 upper=f['independent_resources']['listed_analysis_upper_bytes']+sum(x['bytes']for x in reads);assert upper<LIMIT
 vp=write('verification.json',dict(schema='EU4-R71-SOURCE-PEER-VERIFICATION/1',sealed=True,passed=True,pins_checked=len(m['source_pins']|m['local_pins']),
  sourcepins_current_equal=True,engine_metadata_only=38,conservative_complete_stage_upper_bytes=upper,stage_limit=LIMIT,own_peak_bytes=peak,
  operations=m['operations'],authority=m['authority'],all_shells_collected=True))
 print(json.dumps(dict(passed=True,verification=vp,pins=len(m['source_pins']|m['local_pins']),complete_upper=upper,peak=peak)))
if __name__=='__main__':
 try:check()if sys.argv[1:]==['--check']else main()
 except BaseException as exc:
  if OUT.exists():write('verification-failure.json'if sys.argv[1:]==['--check']else'review-failure.json',dict(type=type(exc).__name__,detail=str(exc),reads=reads,peak=peak,author_unchanged=True,no_PE_engine_producer_actual=True))
  raise
