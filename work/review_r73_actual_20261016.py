"""R73 nonauthor retained actual audit; no producer/decoder/PE/runtime execution."""
import ast,ctypes,hashlib,json,struct,sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
B='work/reports/war-peace-api-20261016-r73-divisor-nonpositive-fragment/'
O='work/reports/war-peace-api-20261016-r73-actual-independent-review/'
OUT=ROOT/O;LIMIT=24*1024*1024;FILE=4*1024*1024;reads=[];peak=0
EXPECTED={
'actual-manifest.json':(24623,'a5eb1ebbfe46c9d590aa118729a330499a226d828458248c45530ada0feb987b'),
'actual-contract.json':(13212,'5eb88b02b2a454104799c18703af2f7fdf3487e507661f6af6cad013ceb41857'),
'actual-selected-evidence.json':(8070,'724057630e576f976d48ad6e3044cdbdde7d0359e98bfd27f992f285cb680eea'),
'capture.json':(73174,'362d4112a31856da813b1a4c5499fa4bb5257b227c4f1ba72be5d91ef9f06b6c'),
'owned-code.json':(906,'531d218c6d62d25eedee87756f347cb6089fd5f32afeec51ceb634f22760482c'),
'actual-verification.json':(22701,'52eb3bd157918b1463f832ebe8dc6aeec47e630644420d7f631d09fa1eac2112'),
'actual-delivery.json':(1720,'aab3b40d6ad9cc4e123c33515062329217178f18d1693f905f73a43cca290f8a'),
'actual-final-filecheck.json':(7684,'425311602d583ee7f8672d3dc84fded7053ed8fb38929801c325aed976a08b91'),
'actual-publication-manifest.json':(2326,'31998bcfd764c9afae7e1e262652fe579d5943ba343ed7e0c253e7b106aca542')}
class PMC(ctypes.Structure):
 _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(x,ctypes.c_size_t)for x in('pw','w','pp','p','pn','n','pf','ppf','private')]
k=ctypes.WinDLL('kernel32',use_last_error=True);k.GetCurrentProcess.restype=ctypes.c_void_p;p=ctypes.WinDLL('psapi',use_last_error=True)
def guard():
 global peak
 c=PMC();c.cb=ctypes.sizeof(c);assert p.GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()),ctypes.byref(c),c.cb)
 peak=max(peak,c.pw,c.ppf,c.private);assert peak<768*1024*1024
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
 f=ROOT/path;s=f.stat();assert s.st_size<=FILE;r=f.read_bytes();a=f.stat();assert(len(r),s.st_size,s.st_mtime_ns)==(a.st_size,a.st_size,a.st_mtime_ns)
 if q:assert pin(r)==q,path
 reads.append(dict(path=path,**pin(r)));assert sum(x['bytes']for x in reads)<LIMIT;return r
def write(name,v):
 r=(json.dumps(v,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode();assert len(r)<=FILE
 with(OUT/name).open('xb')as f:f.write(r)
 return pin(r)
def intake():
 OUT.mkdir(exist_ok=False);files={}
 def take(path,q):
  if path in files:assert {k:files[path][k]for k in('bytes','sha256')}==q
  else:
   r=read(path,q);files[path]=dict(**q,text=r.decode('utf-8'))
 for name in('actual-manifest.json','actual-publication-manifest.json'):
  n,h=EXPECTED[name];take(B+name,dict(bytes=n,sha256=h))
 m=decode(files[B+'actual-manifest.json']['text'].encode());pub=decode(files[B+'actual-publication-manifest.json']['text'].encode())
 assert len(m['source_pins'])==40 and len(m['output_pins'])==3 and len(m['pins'])==43 and len(m['decoder_expected_witness_pins'])==38
 assert m['pins']==m['source_pins']|m['output_pins']
 for path,q in m['pins'].items():take(path,q)
 for path,q in pub['pins'].items():take(path,q)
 for name,(n,h)in EXPECTED.items():take(B+name,dict(bytes=n,sha256=h))
 cp=write('retained-files.json',dict(files=files))
 write('intake-receipt.json',dict(cache=cp,files=len(files),read_bytes=sum(x['bytes']for x in reads),reads=reads,peak_bytes=peak,engine_opened=False))
 print(json.dumps(dict(passed=True,files=len(files),cache=cp,read_bytes=sum(x['bytes']for x in reads),peak_bytes=peak)))
def audit():
 cp=dict(bytes=754973,sha256='3c831c75b19a8e5e63e7364cf265d590ccf6d01bde9216caffd9ff20a01b8379')
 files=decode(read(O+'retained-files.json',cp))['files'];docs={}
 for path,e in files.items():
  assert pin(e['text'].encode())=={k:e[k]for k in('bytes','sha256')}
  if path.endswith('.json')and e['bytes']:docs[path]=decode(e['text'].encode())
 def pn(path):return {k:files[path][k]for k in('bytes','sha256')}
 def obj(name):return docs[B+name]
 m=obj('actual-manifest.json');pub=obj('actual-publication-manifest.json');c=obj('capture.json');o=obj('owned-code.json');sel=obj('actual-selected-evidence.json');con=obj('actual-contract.json');delivery=obj('actual-delivery.json')
 assert len(files)==51 and len(m['source_pins'])==40 and len(m['output_pins'])==3 and m['pins']==m['source_pins']|m['output_pins']
 assert all(pn(path)==q for path,q in m['pins'].items())and all(pn(path)==q for path,q in pub['pins'].items())
 assert len(pub['pins'])==7 and pub['subject_manifest']==pn(B+'actual-manifest.json')and pub['actual_attempts']==1
 assert con['source_pins']==m['source_pins']and con['capture_pin']==sel['capture_pin']==delivery['capture']==pn(B+'capture.json')
 assert con['owned_code_pin']==sel['owned_code_pin']==delivery['owned']==c['owned_code_pin']==pn(B+'owned-code.json')
 assert con['selected_evidence_pin']==delivery['selected']==pn(B+'actual-selected-evidence.json')and delivery['contract']==pn(B+'actual-contract.json')
 assert c['source_pins']==obj('source-manifest.json')['source_pins']==obj('claim.json')['source_pins']
 assert len(c['source_pins'])==64 and len(c['decoder_expected_pins'])==len(m['decoder_expected_witness_pins'])==38
 assert c['decoder_expected_pins']==m['decoder_expected_witness_pins']
 for path,q in c['source_pins'].items():
  if path not in c['decoder_expected_pins']:assert pn(path)==q
 assert not set(files)&set(c['decoder_expected_pins'])
 assert c['window']==o['window']==sel['window']==['0x993643','0x993658']
 assert c['game_sha256']==o['game_sha256']==sel['game_sha256']==con['game_sha256']=='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
 raw=bytes.fromhex(o['raw_hex']);assert raw.hex()==sel['raw_hex']=='4c8b7c2478498bc64883c430415e415d415c5e5dc3'and len(raw)==o['bytes']==21
 assert hashlib.sha256(raw).hexdigest()==o['sha256']and o['file_offset']==10037827
 a=c['analysis'];rows=a['instructions'];assert rows==sel['rows']and len(rows)==9
 expected=[(0x993643,'4c8b7c2478','mov','r15, qword ptr [rsp + 0x78]'),(0x993648,'498bc6','mov','rax, r14'),(0x99364b,'4883c430','add','rsp, 0x30'),
  (0x99364f,'415e','pop','r14'),(0x993651,'415d','pop','r13'),(0x993653,'415c','pop','r12'),(0x993655,'5e','pop','rsi'),(0x993656,'5d','pop','rbp'),(0x993657,'c3','ret','')]
 cursor=0x993643
 for r,(at,b,mn,op)in zip(rows,expected):
  b0=bytes.fromhex(b);assert r['rva']==hex(at)and at==cursor and r['bytes']==b and r['mnemonic']==mn and r['operands']==op
  assert raw[at-0x993643:at-0x993643+len(b0)]==b0;cursor+=len(b0)
 assert cursor==0x993658
 # Fixed raw encodings: REX.W/RXB, ModRM/SIB and register POP opcode semantics.
 assert raw[:5]==bytes.fromhex('4c8b7c2478')and(raw[1],raw[2]>>6,(raw[2]>>3)&7,raw[3],raw[4])==(0x8b,1,7,0x24,0x78)
 mem=dict(base='rsp',index=None,scale=1,displacement=0x78,segment=None,width_bytes=8,read=True,write=False,rip_target_rva=None)
 assert rows[0]['memory_operands']==[mem]and all(r['memory_operands']==[]for r in rows[1:])
 assert rows[0]['registers_written']==['r15']and rows[1]['registers_read']==['r14']and rows[1]['registers_written']==['rax']
 assert rows[2]['immediates']==[0x30]and set(rows[2]['registers_written'])=={'rsp','rflags'}
 for r,target in zip(rows[3:8],['r14','r13','r12','rsi','rbp']):assert set(r['registers_written'])=={'rsp',target}and r['registers_read']==['rsp']
 assert rows[8]['registers_read']==rows[8]['registers_written']==['rsp']
 assert all(not any(x['write']for x in r['memory_operands'])for r in rows)
 assert sel['explicit_memory_store_count']==sel['explicit_D_or_header_access_count']==sel['CALLsites']==sel['branchsites']==sel['INT3sites']==0
 assert sel['RETsites']==1 and sel['normal_path_stack_read_bytes']==7*8==56
 assert sel['explicit_stack_loads']==[dict(site='0x993643',address='F+78=S69+20',bytes=8)]
 pop_sources=[];sp=0x30
 for r in rows[3:8]:pop_sources.append(dict(site=r['rva'],kind='stack_qword_pop',target_register=r['operands'],address_relative_to_F=hex(sp),RSP_increment=8));sp+=8
 pop_sources.append(dict(site='0x993657',kind='near_RET_stack_qword_read',address_relative_to_F=hex(sp),RSP_increment=8,target='QWORD[F+58]',target_validity_and_no_alias_corruption_required=True))
 assert pop_sources==sel['implicit_stack_reads']and sp==0x58 and sp+8==0x60 and -0x58+0x60==8 and -0x58+0x78==0x20
 assert a['edges']==[]and a['terminals']==[dict(kind='normal_ret',rva='0x993657')]and a['local_normal_CFG_closed']and sel['local_CFG_closed']
 assert c['whole_function_closed']is False and sel['whole_function_closed']is False and a['dynamic_reachability_verified']is False
 look=a['lookahead_inputs'];assert [(x['rva'],x['bytes'])for x in look]==[(r['rva'],min(15,0x993658-int(r['rva'],16)))for r in rows]
 union=set()
 for x in look:union.update(range(int(x['rva'],16),int(x['rva'],16)+x['bytes']))
 assert sum(x['bytes']for x in look)==a['decoder_input_total_bytes']==sel['lookahead_total']==70
 assert len(union)==a['decoder_input_unique_bytes']==a['decoded_unique_bytes']==sel['lookahead_unique']==21 and a['decoder_overlap_bytes']==sel['lookahead_repeated']==49
 # Cached predecessor/descriptor and frame premises, no old native bytes re-read.
 seed=obj('entry-seed.json');R69='work/reports/war-peace-api-20261016-r69-generator-divisor-source/';R71='work/reports/war-peace-api-20261016-r71-divisor-fallthrough-fragment/'
 assert seed['cached_descriptor']==c['cached_pdata_descriptor']==docs[R69+'capture.json']['pdata_requests'][14]
 assert struct.unpack('<III',bytes.fromhex(seed['cached_descriptor']['raw_hex']))==(0x993643,0x993658,0x1e7dd24)
 assert seed['R71_short_entry_to_branch_rows']==docs[R71+'actual-selected-evidence.json']['rows'][:4]
 branch=seed['R71_short_entry_to_branch_rows'][-1];assert branch['bytes']=='0f8e8b000000'and int(branch['rva'],16)+6+struct.unpack('<i',bytes.fromhex(branch['bytes'])[2:])[0]==0x993643
 assert 5*8+0x30==0x58
 assert c['pdata_requests']==[]and c['pdata_physical_bytes']==c['pdata_unique_bytes']==0 and c['new_header_data_literal_vtable_unwind_callee_bytes']==0
 assert c['sparse_reads']==[dict(kind='single_inherited_fragment_code',rva='0x993643',file_offset=10037827,requested_bytes=21,bytes=21)]
 assert [x['phase']for x in c['full_PE_authentication_reads']]==['before','after']and all(x['completed']and x['bytes_read']==38462504 and x['sha256']==c['game_sha256']for x in c['full_PE_authentication_reads'])
 assert sum(x['bytes_read']for x in c['full_PE_authentication_reads'])+21==c['total_PE_physical_bytes']==76925029
 journal=c['source_file_reads'];assert len(journal)==162 and sum(x['bytes']for x in journal)==c['source_file_read_bytes']==17382203
 assert Counter(x['phase']for x in journal)==Counter(authorization_preflight=14,source_engine_before=72,source_engine_after=76)
 def relative(path):return str(Path(path).relative_to(ROOT)).replace('\\','/')
 for phase in('source_engine_before','source_engine_after'):
  phase_stream={relative(x['path']):x['bytes']for x in journal if x['phase']==phase and x['operation'].startswith('streaming')}
  assert all(phase_stream.get(path)==q['bytes']for path,q in c['source_pins'].items())
 auth=obj('run-authorization.json');claim=obj('claim.json')
 assert auth['schema']=='EU4-R73-ROOT-AUTHORIZATION/1'and auth['single_attempt']and auth['root_explicit_start_received']and auth['authorizes_retry']is False
 assert auth['source_manifest']==c['source_manifest']==o['source_manifest']==claim['source_manifest']==pn(B+'source-manifest.json')
 assert auth['producer_pin']==pn(B+'produce.py')and auth['entry_seed_pin']==c['entry_seed_pin']==pn(B+'entry-seed.json')
 assert c['authorization_pin']==claim['authorization_pin']==pn(B+'run-authorization.json')and claim['automatic_retry']is False
 assert c['seed_review_pin']==auth['seed_review_pin']==pn(auth['seed_review_path'])
 rv=docs[auth['seed_review_path']];assert rv['sealed']and rv['passed']and rv['blocking_findings']==[]and rv['entry_seed_pin']==pn(B+'entry-seed.json')
 for g in('source_peer_review','upstream_body_review'):
  for part,q in auth[g].items():assert pn(q['path'])=={k:q[k]for k in('bytes','sha256')}
  f=docs[auth[g]['findings']['path']];assert f['sealed']and f['passed']and f['blocking_findings']==[]
  if g=='upstream_body_review':assert f['subject_manifest']==pn(R71+'actual-manifest.json')
  else:assert f['subject_source_manifest']==pn(B+'source-manifest.json')and f['subject_producer']==pn(B+'produce.py')and f['subject_entry_seed']==pn(B+'entry-seed.json')
 rr=docs['work/reports/war-peace-api-20261016-r73-root-authorization/receipt.json'];assert rr['before']==rr['after']and rr['authorization']==pn(B+'run-authorization.json')
 assert all(pn(path)==q for path,q in rr['before'].items())
 for path,q in c['upstream_and_source_peer_pins'].items():assert pn(relative(path))==q
 # Already reviewed exact source; selected source order checked again as text, never imported.
 src=files[B+'produce.py']['text'];fm={x.name:x for x in ast.parse(src).body if isinstance(x,ast.FunctionDef)}
 sg=ast.unparse(fm['source_guard']);main=ast.unparse(fm['main'])
 assert sg.index('== expected_manifest_pin')<sg.index('manifest = json.loads(raw_manifest)')<sg.index('for name, expected in pins.items()')
 assert main.count('source_guard(base_pin)')==2 and main.index('root_explicit_start_received')<main.index("PHASE = 'source_engine_before'")<main.index('base, pins = source_guard(base_pin)')<main.index("stream = (ROOT.parent / 'eu4.exe').open('rb')")
 assert main.index('before source guard')<main.index('base, pins = source_guard(base_pin)')<main.index('after source guard')
 assert main.index('_, postpins = source_guard(base_pin)')<main.index('stream.close()')<main.index("save('capture.json', value)")
 assert "'Sources/engine/authorization/reviews changed'"in main and c['source_engine_before_after_equal']
 run=obj('actual-run.json');sealrun=obj('actual-seal-run.json');check=obj('actual-final-filecheck.json');ver=obj('actual-verification.json')
 assert run['actual_attempts']==1 and run['exit_code']==0 and run['direct_child_collected']and run['automatic_retry']is False
 assert sealrun['exit_code']==0 and sealrun['direct_child_collected']and sealrun['actual_rerun']is False
 for record in(run,sealrun):
  for key,v in record.items():
   if key.endswith('.txt'):assert pn(B+key)==v
 assert pub['all_shells_collected']and delivery['all_shells_collected']and delivery['actual_attempts']==1 and delivery['actual_exit_code']==0
 assert ver['flat_pins']==m['pins']and ver['source_prepost_equal']and check['passed']and check['flat_pins_checked']==43
 assert sum(x['bytes']for x in ver['read_events'])==ver['retained_measured_bytes']==1211856
 assert sum(x['bytes']for x in check['read_events'])==check['final_measured_bytes']==678846
 assert 1211856+678846==check['retained_total_measured']==1890702
 assert 1890702+1048576==check['retained_measured_plus_manual']==2939278
 assert check['retained_frozen_upper']==ver['retained_explicit_upper_bytes']==3309008 and 2939278<3309008
 assert c['source_file_read_bytes']+pn(B+'capture.json')['bytes']==con['resource_witness']['producer_source_including_print_pin']==17455377
 assert all(v is False for v in con['authority'].values())and con['authority']==sel['authority']==m['authority']==pub['authority']==delivery['authority']
 for path,e in files.items():read(path,{k:e[k]for k in('bytes','sha256')})
 replay=dict(sealed=True,window=['0x993643','0x993658'],raw_hex=raw.hex(),rows=[dict(rva=hex(at),raw_hex=b,mnemonic=mn,operands=op)for at,b,mn,op in expected],
  rows_raw_equal=True,local_CFG_closed=True,whole_function_closed=False,CALLsites=0,branches=0,RET='0x993657',INT3=0,
  explicit_stores=0,explicit_D_header_dereferences=0,stack_reads=[dict(site='0x993643',offset_F='0x78',bytes=8)]+pop_sources,
  stack_read_bytes=56,RAX_source='CurrentR14 before POPR14; originalD only if earlier normal nonvolatile/frame/alias premises hold; not DWORD[D]',
  RSP_projection='entryF=S69-58;ADD30;5POPs=28;RET+8; normal final S69+8',
  R15='Load currentQWORD[F+78]; equals earlier savedR15 only if saved memory valid/uncorrupted. No longer low32count after load.',
  flags='ADD64 RSP30 overwrites arithmetic flags; no preservation of TEST32 flags is claimed; DF unknown and untouched',
  unknown='Stack memory/returntarget validity, arbitrary aliases, earlier97bd30 effects, current/finalD/header, NULL993658, fullfunction/type/units/recipient/effect/lease',
  lookahead_input=70,union=21,repeated=49,new_pdata=0,PE_producer_separate=76925029,reviewer_PE_decoder_engine_native=0)
 rp=write('raw-replay.json',replay)
 intake=decode(read(O+'intake-receipt.json'));explicit=intake['read_bytes']+sum(x['bytes']for x in reads)
 upper=explicit+2*754973+524288+2000000;assert upper<LIMIT
 findings=dict(schema='EU4-R73-ACTUAL-INDEPENDENT-REVIEW/1',sealed=True,passed=True,blocking_findings=[],scope='Full retained sole21B inherited branch acquisition/raw/conditional exit audit; no new actual operation',
  reviewer_role='Nonauthor of R73 D producer/actual/sealer; same reviewer previously source-peer and historical R69 template designer/R71 full reviewer. Root raw review/grant and validation_audit R69 acquisition remain distinct retained witnesses; no engine reauthentication.',
  subject_manifest=pn(B+'actual-manifest.json'),subject_actual_manifest=pn(B+'actual-manifest.json'),subject_contract=pn(B+'actual-contract.json'),subject_capture_pin=pn(B+'capture.json'),subject_owned=pn(B+'owned-code.json'),subject_selected_evidence=pn(B+'actual-selected-evidence.json'),subject_publication_manifest=pn(B+'actual-publication-manifest.json'),raw_replay=rp,
  checks=dict(author_sources=40,author_outputs=3,author_combined_pins=43,publication_exact_pins=7,full_explicit_flat_files=51,engine38_metadata_not_opened=True,
   raw21_and_nine_rows_exact=True,local_exit_and_seven_stack_QWORD_reads=True,conditional_inherited_R14_R15_frame_boundaries=True,three_reviews_and_newgrant_exact=True,
   rawbuffer_guard_preparse_two_basepin_calls=True,soleclaim_no_rerun=True,source_engine_PE_auth_postguards_and_normal_close_before_publish_retained=True,all_current_flat_source_prepost_equal=True),
  precision_notes=[
   'MOV RAX,R14 occurs before POPR14. Return is currentR14 bits, and only conditionally originalD pointer; it is not a new balance/amount, boolean or DWORD[D] return.',
   'One explicit stack QWORD load plus5 POPs andRET give7 reads/56B. POP/RET missing explicit memory operands do not erase reads. No explicit writes or direct D/header dereference in selected21B does not prove their aliases disjoint or wholefunction contents unchanged.',
   'R15 reads current[F+78], the address earlier used to saveR15; equality to the saved value needs memory/alias integrity. F+78=S69+20 is an address identity, not a prior memory-copy source.',
   'Local oneRET CFG closure assumes valid stack/return target and priornormal frame. It does not close R69 NULL993658/unfollowed97bd30 or arbitrary-input behavior; no new independent Win64 entry ABI is inferred.',
   'Source R73 rawmanifest buffer is pinned before parsing/source-selected engine access, pre/post calls use authorizedbasepin and first exterior checks remain. Before/after hashes and normal close are retained source/acquisition witnesses, not an atomic/ABA proof.',
   'All51 explicit source/publication files are repinned;38 decoder metadata remains unopened and whole recursive history is not expanded. Full engine/PE/timing/peak and direct-child collection are producer witnesses.',
   'Source17455377 includes postcapture73174 print-pin read; target76925029 is separate. Retained measured1890702+manual1048576=2939278, frozenupper3309008 covers named later small publication reads; no wholeOS/loader or hardJob claim.'],
  author_resource_witness=dict(source_through_capture=17382203,postcapture_print_pin=73174,source_total=17455377,retained_measured=1890702,retained_manual_allowance=1048576,retained_measured_plus_manual=2939278,retained_frozen_upper=3309008,PE_separate=76925029,producer_peak=24043520),
  independent_resources=dict(explicit_intake_and_audit=explicit,manual_cache_queries=2*754973,other_manual_allowance=524288,sealing_and_check_reserve=2000000,complete_stage_upper=upper,limit=LIMIT,own_peak=peak),
  operations=dict(PE=0,engine_body=0,decoder=0,author_programs=0,tests=0,game=0,Frida=0,native=0,requests=0),
  authority={k:False for k in('native_ready','callable','independent_entry_callable','reader_adoption_allowed','selected_effect_verified','amount_units_verified','recipient_direction_verified','world_lease','atomic_snapshot','external_ABA_excluded','authorizes_retry','whole_function_closed','runtime_verified','persistence_verified','further_actual_authorized')},
  author_frozen_sources_need_change=False,all_shells_collected=True)
 fp=write('findings.json',findings)
 local={O+'raw-replay.json':rp,O+'findings.json':fp,O+'retained-files.json':cp,O+'intake-receipt.json':pin(read(O+'intake-receipt.json')),'work/review_r73_actual_20261016.py':pin(read('work/review_r73_actual_20261016.py'))}
 mp=write('manifest.json',dict(sealed=True,passed=True,subject_manifest=pn(B+'actual-manifest.json'),source_pins={path:pn(path)for path in files}|local,flat_text_files=51,engine_metadata_only=c['decoder_expected_pins'],native_ready=False,actual_authorized=False))
 print(json.dumps(dict(passed=True,findings=fp,manifest=mp,raw_replay=rp,complete_stage_upper=upper,peak_bytes=peak)))
def check():
 m=decode(read(O+'manifest.json'))
 for path,q in m['source_pins'].items():read(path,q)
 r=dict(sealed=True,passed=True,pins=len(m['source_pins']),read_bytes=sum(x['bytes']for x in reads),peak_bytes=peak,engine_metadata_only=38,author_program_tests_PE_decoder_runtime=0,all_shells_collected=True,actual_authorized=False)
 z=write('verification.json',r);print(json.dumps(dict(passed=True,verification=z,pins=r['pins'],read_bytes=r['read_bytes'],peak_bytes=peak)))
if __name__=='__main__':
 try:
  if sys.argv[1:]==['--intake']:intake()
  elif sys.argv[1:]==['--audit']:audit()
  elif sys.argv[1:]==['--check']:check()
  else:raise ValueError('own intake only')
 except BaseException as e:
  if OUT.exists()and not(OUT/'own-failure-r1.json').exists():write('own-failure-r1.json',dict(error=type(e).__name__,message=str(e),reads=reads,peak_bytes=peak))
  raise
