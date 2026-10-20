"""R71 independent retained actual audit. No reviewed module/decoder/target is run."""
import ctypes,hashlib,json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
B='work/reports/war-peace-api-20261016-r71-divisor-fallthrough-fragment/'
O='work/reports/war-peace-api-20261016-r71-actual-independent-review/'
OUT=ROOT/O
LIMIT=24*1024*1024;FILE=4*1024*1024;MEM=768*1024*1024
CACHE=dict(bytes=690036,sha256='e5f501c43bcdb53044438935961292877ecb1100ee087f09d3e3a17f14880c5c')
GAME='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
reads=[];peak=0
class PMC(ctypes.Structure):
 _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(x,ctypes.c_size_t)for x in('pw','w','pp','p','pn','n','pf','ppf','private')]
k=ctypes.WinDLL('kernel32',use_last_error=True);k.GetCurrentProcess.restype=ctypes.c_void_p;p=ctypes.WinDLL('psapi',use_last_error=True)
def guard():
 global peak
 x=PMC();x.cb=ctypes.sizeof(x);assert p.GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()),ctypes.byref(x),x.cb)
 peak=max(peak,x.pw,x.ppf,x.private);assert peak<MEM
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
 r=q.read_bytes();b=q.stat();assert(a.st_size,a.st_mtime_ns)==(b.st_size,b.st_mtime_ns)and len(r)==a.st_size
 if want is not None:assert pin(r)==want,path
 reads.append(dict(path=path,**pin(r)));assert sum(x['bytes']for x in reads)<LIMIT;return r
def write(name,obj):
 raw=(json.dumps(obj,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode();assert len(raw)<=FILE
 with(OUT/name).open('xb')as f:f.write(raw)
 return pin(raw)
SPECS='''
4c897c2478 mov
4d63f8 movsxd
4585c0 test
0f8e8b000000 jle
48895c2460 mov
48897c2470 mov
0f1f4000 nop
66660f1f840000000000 nop
498b7d70 mov
488d542468 lea
498bcc mov
488b3cf7 mov
4c8bc7 mov
e8c8234000 call
488b5508 mov
8b5c2468 mov
895c2420 mov
48897c2424 mov
483b5510 cmp
740d je
891a mov
48897a04 mov
488345080c add
eb0d jmp
4c8d442420 lea
488bcd mov
e817380000 call
41011e add
48ffc6 inc
493bf7 cmp
7cac jl
488b7c2470 mov
498bc6 mov
488b5c2460 mov
4c8b7c2478 mov
4883c430 add
415e pop
415d pop
415c pop
5e pop
5d pop
c3 ret
'''
STORES={
 0x9935a7:('4c897c2478',8,'rsp',0x78,'syntactic_stack'),
 0x9935b8:('48895c2460',8,'rsp',0x60,'syntactic_stack'),
 0x9935bd:('48897c2470',8,'rsp',0x70,'syntactic_stack'),
 0x9935f0:('895c2420',4,'rsp',0x20,'syntactic_stack'),
 0x9935f4:('48897c2424',8,'rsp',0x24,'syntactic_stack'),
 0x9935ff:('891a',4,'rdx',0,'returned_or_external_pointer'),
 0x993601:('48897a04',8,'rdx',4,'returned_or_external_pointer'),
 0x993605:('488345080c',8,'rbp',8,'header_candidate'),
 0x993619:('41011e',4,'r14',0,'D_candidate')}
def main():
 cache=decode(read(O+'retained-files.json',CACHE));f=cache['files'];objects={}
 for path,e in f.items():
  raw=e['text'].encode('utf-8');assert pin(raw)=={k:e[k]for k in('bytes','sha256')}
  if path.endswith('.json'):objects[path]=decode(raw)
 def obj(name):return objects[B+name]
 def pn(path):return {k:f[path][k]for k in('bytes','sha256')}
 def relative(path):return Path(path).relative_to(ROOT).as_posix()
 m=obj('actual-manifest.json');contract=obj('actual-contract.json');capture=obj('capture.json');owned=obj('owned-code.json');s=obj('actual-selected-evidence.json')
 v=obj('actual-verification.json');delivery=obj('actual-delivery.json');source=obj('source-manifest.json')
 assert len(m['actual_source_pins'])==40 and len(m['local_output_pins'])==3 and len(m['pins'])==m['pin_count']==43 and len(f)==46
 assert m['pins']==m['actual_source_pins']|m['local_output_pins']and all(pn(path)==q for path,q in m['pins'].items())
 assert len(m['engine_metadata_witness_pins'])==38 and m['engine_bodies_opened_by_this_seal']is False and m['new_PE_or_decoder']is False
 assert source['decoder_expected_witness_pins']==m['engine_metadata_witness_pins']==capture['decoder_expected_pins']
 assert v['manifest']==delivery['pins']['actual-manifest.json']==pn(B+'actual-manifest.json')
 assert all(pn(B+path)==q for path,q in delivery['pins'].items())
 for name,field in(('capture.json','subject_capture'),('owned-code.json','subject_owned'),('actual-selected-evidence.json','subject_selected_evidence'),('source-manifest.json','subject_source_manifest')):assert contract[field]==pn(B+name)
 assert capture['game_sha256']==owned['game_sha256']==s['game_sha256']==GAME
 assert contract['game']==dict(bytes=38462504,sha256=GAME)
 assert capture['window']==owned['window']==s['window']==['0x9935a7','0x993643']
 assert capture['scope_kind']=='inherited_fallthrough_fragment'and capture['whole_function_closed']is False and capture['independent_entry_callable']is False
 assert owned['bytes']==156 and owned['whole_function_extent_owned']is False and owned['entire_cached_fragment_owned']is True
 raw=bytes.fromhex(owned['raw_hex']);assert len(raw)==156 and hashlib.sha256(raw).hexdigest()==owned['sha256']
 assert owned['file_offset']==10037671 and owned['new_pdata_bytes']==0
 a=capture['analysis'];rows=a['instructions'];assert len(rows)==a['instruction_count']==42 and rows==s['rows']and a['decoded_unique_bytes']==156
 assert a['local_normal_CFG_closed']is False and a['undecoded_owned_intervals']==[] and a['dynamic_reachability_verified']is False
 specs=[x.split()for x in SPECS.splitlines()if x.strip()];assert len(specs)==42
 cursor=0x9935a7;by={};replay=[]
 for row,(rawhex,mnemonic)in zip(rows,specs,strict=True):
  rr=bytes.fromhex(rawhex);assert row['rva']==hex(cursor)and row['bytes']==rawhex and row['mnemonic']==mnemonic
  assert raw[cursor-0x9935a7:cursor-0x9935a7+len(rr)]==rr
  by[cursor]=row;replay.append(dict(rva=hex(cursor),raw_hex=rawhex,mnemonic=mnemonic,operands=row['operands']));cursor+=len(rr)
 assert cursor==0x993643
 edges=[]
 for row in rows:
  at=int(row['rva'],16);rr=bytes.fromhex(row['bytes']);op=row['mnemonic']
  if op not in('jle','je','jmp','jl','call'):continue
  pos=2 if rr[0]==0x0f else 1;displacement=int.from_bytes(rr[pos:],'little',signed=True);target=at+len(rr)+displacement
  inside=0x9935a7<=target<0x993643
  edges.append(dict(site=hex(at),raw_hex=rr.hex(),target_rva=hex(target),signed_displacement=displacement,inside_owned_window=inside,kind=op))
 assert len(edges)==6
 expected_targets={0x9935b2:0x993643,0x9935e3:0xd959b0,0x9935fd:0x99360c,0x99360a:0x993619,0x993614:0x996e30,0x993622:0x9935d0}
 assert {int(x['site'],16):int(x['target_rva'],16)for x in edges}==expected_targets
 for e,p,q in zip(edges,a['edges'],s['raw_arithmetic_edges'],strict=True):
  assert all(p[k]==e[k]for k in('site','target_rva','inside_owned_window'))and p['callee_followed']is False
  assert all(q[k]==e[k]for k in('site','target_rva','raw_hex','signed_displacement','inside_owned_window'))
  assert q['target_bytes_followed']==(e['inside_owned_window']and e['kind']!='call')
 assert a['terminals']==s['terminals']==[dict(kind='external_or_indirect_branch',rva='0x9935b2',target='0x993643'),dict(kind='normal_ret',rva='0x993642')]
 # Independent finite local graph: CALL fallthrough only, no target body expansion.
 pending=[0x9935a7];seen=set()
 while pending:
  at=pending.pop()
  if at in seen:continue
  assert at in by;seen.add(at);row=by[at];op=row['mnemonic'];following=at+len(bytes.fromhex(row['bytes']))
  if op=='ret':continue
  if op in('jle','je','jmp','jl'):
   target=expected_targets[at]
   if target in by:pending.append(target)
   if op=='jmp':continue
  assert following in by;pending.append(following)
 assert len(seen)==42
 # Reconcile all explicit destination-memory operations from fixed raw opcodes/widths.
 got=[]
 for at,row in by.items():
  dest=[x for x in row['memory_operands']if x['write']]
  if at in STORES:
   rawhex,width,base,disp,category=STORES[at];assert row['bytes']==rawhex and len(dest)==1
   z=dest[0];assert(z['width_bytes'],z['base'],z['displacement'])==(width,base,disp)
   assert row['raw_memory_write_review']['explicit_memory_write']is True
   got.append(dict(rva=hex(at),raw_hex=rawhex,width_bytes=width,base=base,displacement=disp,category=category))
  else:assert not dest
  if row['mnemonic']in('nop','lea'):
   # Capstone may mark the address operand read; fixed NOP/LEA encodings do
   # not dereference that address. Keep annotations, do not equate them to RPM.
   assert not any(x['write']for x in row['memory_operands'])
 assert len(got)==s['explicit_store_count']==9 and s['store_categories']=={'syntactic_stack':5,'returned_or_external_pointer':2,'header_candidate':1,'D_candidate':1}
 for z,q in zip(got,s['explicit_stores'],strict=True):
  assert all(q[k]==z[k]for k in('rva','raw_hex','width_bytes','category'))and q['source_row']==by[int(z['rva'],16)]
 assert s['implicit_stack_effects']['CALL_return_address_writes']==2 and s['implicit_stack_effects']['POP_QWORD_reads']==5 and s['implicit_stack_effects']['RET_QWORD_read']==1
 # Concrete widths/receiver sources, not C++ semantics or assumed immutable callee outputs.
 assert by[0x9935ac]['bytes']=='4d63f8'and by[0x9935af]['bytes']=='4585c0'
 assert by[0x9935dc]['memory_operands'][0]['scale']==8 and by[0x9935dc]['memory_operands'][0]['index']=='rsi'
 assert by[0x9935ec]['memory_operands'][0]['width_bytes']==4 and by[0x9935ec]['memory_operands'][0]['displacement']==0x68
 assert by[0x993619]['memory_operands'][0]['read']is True and by[0x993619]['memory_operands'][0]['width_bytes']==4
 assert by[0x993605]['memory_operands'][0]['read']is True and by[0x993605]['immediates']==[12]
 assert by[0x993629]['bytes']=='498bc6'and [r['mnemonic']for r in rows[-7:]]==['add','pop','pop','pop','pop','pop','ret']
 # S69 frame arithmetic: inherited five PUSHes +SUB30, here ADD30/five POP/RET.
 frame={'F_from_S':-(5*8+0x30),'saved_R15_from_S':-0x58+0x78,'saved_RBX_from_S':-0x58+0x60,'saved_RDI_from_S':-0x58+0x70,
  'fresh_DWORD_from_S':-0x58+0x68,'record_start_from_S':-0x58+0x20,'record_end_exclusive_from_S':-0x58+0x20+12,
  'pre_RET_RSP_from_S':-0x58+0x30+5*8,'post_RET_RSP_from_S':8,'fresh_DWORD_from_Q62':-0x90-0x58+0x68}
 assert frame==dict(F_from_S=-88,saved_R15_from_S=32,saved_RBX_from_S=8,saved_RDI_from_S=24,fresh_DWORD_from_S=16,
  record_start_from_S=-56,record_end_exclusive_from_S=-44,pre_RET_RSP_from_S=0,post_RET_RSP_from_S=8,fresh_DWORD_from_Q62=-128)
 assert contract['frame']['F']=='S-0x58 under balanced97bd30'and contract['store_summary']['D_ADD32']==1
 # Known admission identities, distinct reviewers and one author actual invocation.
 auth=obj('run-authorization.json');acq=obj('acquisition-receipt.json');claim=obj('claim.json');rootclaim=obj('root-invocation-claim.json')
 for n,kfield in(('source-manifest.json','source_manifest'),('produce.py','producer_pin'),('entry-seed.json','entry_seed_pin')):assert auth[kfield]==pn(B+n)
 assert auth['sealed']is True and auth['schema']=='EU4-R71-ROOT-AUTHORIZATION/1'and auth['single_attempt']is True and auth['authorizes_retry']is False
 assert auth['entry_rva']=='0x9935a7'and auth['window']==capture['window']and auth['root_explicit_start_received']is True
 reviews={auth['seed_review_path']:auth['seed_review_pin'],auth['root_review_manifest']['path']:{k:auth['root_review_manifest'][k]for k in('bytes','sha256')}}
 for label in('upstream_body_review','source_peer_review'):
  for z in auth[label].values():reviews[z['path']]={k:z[k]for k in('bytes','sha256')}
 assert reviews==contract['admission']['reviews']==acq['reviews']==rootclaim['reviews']and all(pn(path)==q for path,q in reviews.items())
 for path in(auth['seed_review_path'],auth['upstream_body_review']['findings']['path'],auth['source_peer_review']['findings']['path']):
  j=objects[path];assert j['sealed']is True and j['passed']is True and j['blocking_findings']==[]
 peer=objects[auth['source_peer_review']['findings']['path']]
 assert peer['subject_source_manifest']==pn(B+'source-manifest.json')and peer['subject_producer']==pn(B+'produce.py')and peer['subject_entry_seed']==pn(B+'entry-seed.json')
 upstream=objects[auth['upstream_body_review']['findings']['path']]
 assert upstream['subject_manifest']==pn('work/reports/war-peace-api-20261016-r69-generator-divisor-source/manifest.json')
 assert peer['reviewer_role']['R69_original_source_preparer']is True and upstream['reviewer_role']['original_source_preparer']is True
 assert acq['authorization']==rootclaim['authorization']==capture['authorization_pin']==pn(B+'run-authorization.json')
 assert acq['stdout']==pn(B+'producer.stdout.json')and acq['stderr']==pn(B+'producer.stderr.txt')and not f[B+'producer.stderr.txt']['text']
 assert acq['runner']==pn(B+'run_once.py')and acq['all_admission_pins_prepost_equal']is True and acq['direct_owned_child_collected']is True
 assert acq['exit_code']==0 and acq['exit_and_file_success']is True and acq['failure_files']==[]and acq['automatic_retry']is False
 assert acq['hard_Job_installed']is False and acq['child_tree_peak_claimed']is False
 rootreceipt='work/reports/war-peace-api-20261016-r71-root-authorization/receipt.json'
 assert acq['root_receipt']==rootclaim['root_receipt']==pn(rootreceipt)
 root=objects[rootreceipt];assert root['sealed']is True and root['passed']is True and root['blocking_findings']==[]and root['before']==root['after']
 for path,q in root['before'].items():assert pn(path)==q
 assert claim['authorization_pin']==pn(B+'run-authorization.json')and claim['new_code_bytes']==156 and claim['new_pdata_bytes']==0 and claim['automatic_retry']is False
 assert capture['source_pins']==claim['source_pins']==source['source_pins']
 producer=f[B+'produce.py']['text'];maintext=producer[producer.index('def main():'):]
 assert maintext.index("for label in ('upstream_body_review','source_peer_review')")<maintext.index('base,pins=source_guard()')<maintext.index("save('claim.json'")<maintext.index("stream=(ROOT.parent/'eu4.exe').open('rb')")
 assert maintext.index("authenticate('after')")<maintext.index('_,postpins=source_guard()')<maintext.index('finally:')<maintext.index('stream.close()')<maintext.index("save('capture.json',value)")
 # Journals/authentication remain producer witnesses; no new PE/engine authentication here.
 assert capture['pdata_requests']==[]and capture['pdata_physical_bytes']==capture['pdata_unique_bytes']==0
 assert capture['sparse_reads']==[dict(kind='single_inherited_fragment_code',rva='0x9935a7',file_offset=10037671,requested_bytes=156,bytes=156)]
 assert len(capture['full_PE_authentication_reads'])==2
 for e in capture['full_PE_authentication_reads']:assert e['bytes_read']==38462504 and e['completed']is True and e['sha256']==GAME
 assert capture['total_PE_physical_bytes']==2*38462504+156==76925164
 journal=capture['source_file_reads'];assert len(journal)==144 and sum(e['bytes']for e in journal)==capture['source_file_read_bytes']==16957772
 engine=m['engine_metadata_witness_pins']
 for phase in('source_engine_before','source_engine_after'):
  events=[e for e in journal if e['phase']==phase and e['operation']=='streaming_engine_pin']
  assert len(events)==38 and {relative(e['path']):e['bytes']for e in events}=={path:q['bytes']for path,q in engine.items()}
 for e in journal:
  path=relative(e['path'])
  if e['operation']!='streaming_engine_pin':assert e['bytes']==pn(path)['bytes']
 assert capture['source_engine_before_after_equal']is True and capture['hard_Job_installed']is False
 lookahead=a['lookahead_inputs'];assert len(lookahead)==42 and all(e['bytes']==min(15,0x993643-int(e['rva'],16))for e in lookahead)
 union=set()
 for e in lookahead:union.update(range(int(e['rva'],16),int(e['rva'],16)+e['bytes']))
 assert len(union)==156 and sum(e['bytes']for e in lookahead)==a['decoder_input_total_bytes']==565 and a['decoder_overlap_bytes']==409
 assert a['decoder_input_unique_bytes']==156
 assert v['flat_pin_count']==43 and v['passed']is True and v['sealed']is True and v['independent_full_review_complete']is False
 for e in v['file_reads']:assert e['bytes']==pn(e['path'])['bytes']
 assert len(v['file_reads'])==124 and sum(e['bytes']for e in v['file_reads'])==1640246
 before={e['path']:e['bytes']for e in v['file_reads']if e['phase']=='source_before'}
 after={e['path']:e['bytes']for e in v['file_reads']if e['phase']=='source_after'}
 assert before==after=={path:q['bytes']for path,q in m['actual_source_pins'].items()}
 final={e['path']:e['bytes']for e in v['file_reads']if e['phase']=='flat_filecheck'};assert final=={path:q['bytes']for path,q in m['pins'].items()}
 for e in acq['wrapper_file_reads']:assert e['bytes']==pn(e['path'])['bytes']
 assert sum(e['bytes']for e in acq['wrapper_file_reads'])==acq['wrapper_explicit_file_bytes']==238959
 accounting=v['read_accounting'];assert accounting['combined_upper']==1640246+238959+1048576==2927781==delivery['read_upper_including_wrapper_and_manual']
 assert contract['resources']['source_including_final_capture_pin']==16957772+95356==17053128<32*1024*1024
 assert accounting['combined_upper']<16*1024*1024 and contract['resources']['producer_peak_committed_witness']==capture['peak_committed_bytes_observed']==23527424
 for j in(contract,s,m,v,delivery):assert all(x is False for x in j['authority'].values())
 for path,e in f.items():read(path,{k:e[k]for k in('bytes','sha256')})
 upper=cache['source_bytes']+24771+4*CACHE['bytes']+1024*1024+sum(x['bytes']for x in reads)+1024*1024;assert upper<LIMIT
 model=dict(inherited='R71 is nonnullR69fallthrough, not a new function/formal ABI. R13/R14/RBP/RSI and F=S69-58 require stated normalcalleeABI/stack premises. D0/headerzeros not current invariants.',
  low32_count='MOVSXD R15,R8D; TEST32 R8D; signed<=0 leavesownedbytes at993643. Positive N is signed low32, not authenticated length.',
  input_reload='Each reached iteration rereads QWORD[currentR13+70] and QWORD[base+RSI*8]. RCX=R12/RDX=&F68/R8=currentRDI to d959b0; externalreturn then freshDWORD[F68]->EBX. No local initialization or callee output proof.',
  record='DWORD[F20]=EBX,QWORD[F24]=RDI, exactly12B local payload. FreshP8 cursor compared only for equality with freshP10; non-equal writes DWORD[cursor]/QWORD[cursor+4] then ADD64[currentP8],12. No bounds/capacity proof; writes may aliasheader/D/stack and theADD rereads header.',
  equal='RCX=currentRBP,RDX=comparedcursor,R8=&F20 to996e30. R9/XMM/formals/effects unknown; no local equal-branch headerincrement beforejoin.',
  D='ADD32[currentR14],EBX read-modify-write modulo2^32. No64-bitamount/units/finalD assertion; externalcalls/aliases can change destination or priorvalue.',
  loop='INC64RSI/CMP64RSI,R15/JL. Under normal-preservation,validmemory,RSI0 and positive signed32N premises, localindices0..N-1; no arbitrary-memory/callee termination guarantee.',
  result='Ownedpositiveepilogue MOVRAX,R14; RAX is currentpointerbits, notDWORDvalue. ADDRSP30/fivePOPs restoreS69,RET givesS69+8 only under validunaliasedsaved/controlstack premises. Otherlowcount/nullpaths unread; localCFGfalse.')
 ops={x:0 for x in('PE_stat_open','engine_stat_open','Capstone_decoder','reviewed_producer_runner_sealer','tests','game_process','Frida','native_game_calls','requests','outside_callee_or_tail_follow','new_actual_authorized')}
 authority={x:False for x in contract['authority']}
 rawpin=write('raw-review.json',dict(schema='EU4-R71-INDEPENDENT-ACTUAL-RAW/1',sealed=True,passed=True,rows=replay,owned_bytes=156,
  raw_arithmetic_edges=edges,reachable_owned_rows=42,terminals=a['terminals'],local_normal_CFG_closed=False,
  explicit_stores=got,implicit_stack_effects=s['implicit_stack_effects'],frame_arithmetic=frame,machine_contract=model,
  decoder_inputs_witness=dict(total=565,unique=156,overlap=409,new_decodes=0),sourcepins_prepost_current=True))
 findings=write('findings.json',dict(schema='EU4-R71-INDEPENDENT-ACTUAL-REVIEW/1',sealed=True,passed=True,blocking_findings=[],
  subject_manifest=pn(B+'actual-manifest.json'),subject_contract=pn(B+'actual-contract.json'),subject_capture=pn(B+'capture.json'),
  subject_owned=pn(B+'owned-code.json'),subject_selected=pn(B+'actual-selected-evidence.json'),raw_review=rawpin,
  reviewer_role=dict(R71_prior_source_peer=True,R69_original_source_preparer=True,R71_source_and_actual_author='diplomacy_static',
   R69_actual_retained_author='validation_audit',root_raw_and_R69_full_review_are_distinct_retained_witnesses=True,
   R69_independent_source_review_remains_separate=True,no_independent_engine_body_reauthentication=True),
  checks=dict(author_flat_pins=43,author_source_pins=40,author_local_outputs=3,current_flat_files=46,engine_metadata_only=38,
   all42rows156B_raw_equal=True,all6relative_edges_replayed=True,explicit_stores=9,syntactic_stack_stores=5,cursor_stores=2,header_ADD64=1,D_ADD32=1,
   new_pdata=0,CALLsites=2,branchsites=4,RETsites=1,local_normal_CFG_closed=False,three_review_root_auth_exactsubjects=True,
   single_actual_and_direct_child_collected=True,source_engine_prepost_witness_equal=True,normalclose_beforecapture=True,all_current_postguard_pins_equal=True),
  machine_contract=model,precision_notes=[
   'Complete156B cached-fragment ownership is not whole-function closure. Signed-low32 nonpositive edge993643 and previousR69null edge993658 remain unread. Two externalcalls d959b0/996e30 and all effects remain unexamined.',
   'Fresh F68 DWORD has no explicit initialization before d959b0 in this fragment. Passing its address does not prove callee writes it; priorstack/callee/alias values remain possible.',
   'Two cursor stores may alias header,D orsaved/controlstack. ADD64[P8] rereads the destination afterthose stores; equality check alone does not prove allocation/capacity. The equal branch externalcallee may change finalheader/D.',
   'ADD32[D],EBX is modular32 arithmetic, not a complete gold-total/units/recipient proof. Current D may differ from precall0, and no final application value or conservation follows.',
   'One owned RET yields a conditional positive-path pointerbits resultRAX=currentR14. It does not supply arbitrary-input/whole-function result, valid memory, safe nativecall, lifetime orbusiness-effect authority.',
   'This reviewer was R71 sourcepeer and originalR69source preparer; D authoredR71source/actual package, Val authoredR69actual, and rootraw/R69full are separately pinned witnesses. No independently redesigned producer or engine-body authentication is claimed.',
   'PE twoSHA+156 and decoder identity/annotations are retained producerwitnesses. This review replays raw bytes/arithmetic/CFG from frozenfiles; it never opens PE/enginebody or invokes originalprograms/tests.',
   '495,600,000ns/23,527,424B are producerlaunch/source/engine/twoSHA witnesses, not APIlatency or hardJob/treepeak. Source32MiB andretained16MiB explicit accounting remain separate; neither is allOS/loaderIO.',
   'Reviewer intakeR1 assumed wrong manifest grouping43 instead of40+3, failed after24771B and preservedexactsource/diagnostic. R2 changed only metadata keys. A separate inlineinspection used defaultGBK and failed reading knownUTF8cache; bounded690036B attempt charged below, correctedUTF8inspection did not runauthorcode.',
   'Reviewer full-auditR1 incorrectly required Capstone memory-read flags to be false for NOP/LEA address operands. Exactsource/failure preserved; fixed knownraw NOP/LEA do not dereference those addresses despite annotations. R2 preserves annotations and checks only the explicit-store flag there; authorbytes/semantics unchanged. Failedcache read690036B charged separately.'
  ],resource_witness=dict(PE_separate_bytes=76925164,source_journal_through_capture=16957772,final_capture_pin=95356,producer_source_including_capture_pin=17053128,
   retained_measured_reads=1640246,wrapper_charged_to_retained=238959,manual_retained_allowance=1048576,retained_explicit_upper=2927781,
   combined_source_retained_upper=17053128+2927781,producer_elapsed_ns=495600000,producer_peak_bytes=23527424,hard_Job_installed=False),
  independent_resources=dict(retained_intake_bytes=cache['source_bytes'],prior_failed_intake_bytes=24771,prior_three_cache_inspection_attempts_upper=3*CACHE['bytes'],prior_failed_review_cache_read=CACHE['bytes'],
   manual_smallinspection_allowance=1024*1024,current_cache_and_postguard_bytes=sum(x['bytes']for x in reads),own_sealing_reserve=1024*1024,
   listed_analysis_upper_bytes=upper,stage_limit=LIMIT,ordinary_file_limit=FILE,own_peak_bytes=peak,memory_limit=MEM),
  operations=ops,authority=authority,author_frozen_sources_changed=False,all_shells_collected=True,next_scope_auto_authorized=False))
 report=b'R71 actual retained review passed:42rows/156B,6relativeedges and9explicitstores replayed. ADD32 currentR14 is modular32; unequalcursor branch writes12B/headerADD12; externalcallee/alias/units/finalD unknown. OneownedRET does not closeallpaths. Prior source-peer role disclosed. NoPE/engine/decoder/authorprogram/tests/game/native operations.\n'
 with(OUT/'report.md').open('xb')as q:q.write(report)
 encoding=write('inspection-encoding-diagnostic.json',dict(error='UnicodeDecodeError',reason='Inline inspection omitted UTF8, GBK conversion refused fixedretainedJSON. Originalcache/authorfilesunchanged; correctedinspection usedUTF8. Noauthorprogram orPE/engine operation.',charged_upper_bytes=CACHE['bytes']))
 local={O+n:pin((OUT/n).read_bytes())for n in('retained-files.json','raw-review.json','findings.json','report.md','intake-r1-source.py','intake-r1-diagnostic.json','inspection-encoding-diagnostic.json','reviewer-r1-source.py','review-failure.json')}
 for path in('work/retain_r71_actual_review_20261016.py','work/review_r71_actual_20261016.py'):local[path]=pin((ROOT/path).read_bytes())
 mp=write('manifest.json',dict(schema='EU4-R71-INDEPENDENT-ACTUAL-MANIFEST/1',sealed=True,source_pins={path:pn(path)for path in f},local_pins=local,findings=findings,
  engine_witness_count=38,engine_body_opened=False,operations=ops,authority=authority))
 print(json.dumps(dict(passed=True,findings=findings,manifest=mp,raw_review=rawpin,analysis_upper=upper,peak=peak,all_shells_collected=True)))
def check():
 m=decode(read(O+'manifest.json'))
 for path,q in(m['source_pins']|m['local_pins']).items():read(path,q)
 f=decode(read(O+'findings.json',m['local_pins'][O+'findings.json']))
 upper=f['independent_resources']['listed_analysis_upper_bytes']+sum(x['bytes']for x in reads);assert upper<LIMIT
 vp=write('verification.json',dict(schema='EU4-R71-INDEPENDENT-ACTUAL-VERIFICATION/1',sealed=True,passed=True,pins_checked=len(m['source_pins']|m['local_pins']),
  sourcepins_current_equal=True,engine_metadata_only=38,conservative_complete_stage_upper_bytes=upper,stage_limit=LIMIT,own_peak_bytes=peak,
  operations=m['operations'],authority=m['authority'],all_shells_collected=True))
 print(json.dumps(dict(passed=True,verification=vp,pins=len(m['source_pins']|m['local_pins']),complete_upper=upper,peak=peak)))
if __name__=='__main__':
 try:check()if sys.argv[1:]==['--check']else main()
 except BaseException as exc:
  n='verification-failure.json'if sys.argv[1:]==['--check']else'review-r2-failure.json'
  if not(OUT/n).exists():write(n,dict(type=type(exc).__name__,detail=str(exc),reads=reads,peak=peak,author_sources_unchanged=True,no_author_execution_PE_engine_decoder_game_native=True))
  raise
