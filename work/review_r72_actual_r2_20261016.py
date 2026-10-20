"""Independent retained-only R72 R2 actual audit. No author execution/PE/engine."""
import ast, ctypes, hashlib, json, struct, sys
from collections import Counter, deque
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
B='work/reports/server-vtable-current-reference-owner-20261016-r2/'
O='work/reports/server-vtable-current-reference-owner-actual-independent-review-20261016-r2/'
OUT=ROOT/O; FILE=4*1024*1024; LIMIT=24*1024*1024; reads=[]; peak=0
EXPECTED={
'actual-manifest.json':(15979,'889424b7f74e7fb825a2947f48f7b2a6f61d4955d4d0a668c356046108f2d201'),
'actual-contract.json':(5949,'8a477105e79df45d96f1d2aeae8fb795ef6efdb82f6f06f8356b5ed85a3bc456'),
'actual-selected-evidence.json':(502893,'6613fc625042220870a30ca3a1a5c4096c6f4e555cd3d4320f5372f42e0ea529'),
'capture.json':(456041,'86cab6aa6f70acc0ffeae2ce712b2b7d7259012119cca487af069f43625a7c26'),
'owned-code.json':(4824,'03bd9c4022e7812acc2b4dc77e2470af8da5b3954e2ef20fb26db0ef59809d18'),
'actual-delivery.json':(3967,'0479f85fe7a9b10dd95a63325b3bc435d400e1713e06381a3bf696a698c220e2'),
'actual-filecheck.json':(11360,'4329b0b40eed21d196dc970bbaa6338f7fa8d5c7f2ea1c87b19f9d37773475c3')}
class PMC(ctypes.Structure):
 _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(x,ctypes.c_size_t)for x in('pw','w','pp','p','pn','n','pf','ppf','private')]
k=ctypes.WinDLL('kernel32',use_last_error=True);k.GetCurrentProcess.restype=ctypes.c_void_p
p=ctypes.WinDLL('psapi',use_last_error=True)
def guard():
 global peak
 a=PMC();a.cb=ctypes.sizeof(a);assert p.GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()),ctypes.byref(a),a.cb)
 peak=max(peak,a.pw,a.ppf,a.private);assert peak<768*1024*1024
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
 f=ROOT/path;a=f.stat();assert a.st_size<=FILE;r=f.read_bytes();z=f.stat()
 assert (a.st_size,a.st_mtime_ns)==(z.st_size,z.st_mtime_ns)and len(r)==a.st_size
 if q is not None:assert pin(r)==q,path
 reads.append(dict(path=path,**pin(r)));assert sum(x['bytes']for x in reads)<LIMIT;return r
def write(name,obj):
 r=(json.dumps(obj,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode();assert len(r)<=FILE
 with(OUT/name).open('xb')as f:f.write(r)
 return pin(r)
def intake():
 OUT.mkdir(exist_ok=False)
 files={}
 def take(path,q=None):
  if path in files:
   if q:assert {x:files[path][x]for x in('bytes','sha256')}==q
   return
  r=read(path,q);files[path]=dict(**pin(r),text=r.decode('utf-8'))
 take(B+'actual-manifest.json',dict(zip(('bytes','sha256'),EXPECTED['actual-manifest.json'])))
 m=decode(files[B+'actual-manifest.json']['text'].encode())
 assert len(m['source_pins'])==44 and len(m['decoder_expected_witness_pins'])==38
 for path,q in m['source_pins'].items():take(path,q)
 for name,(n,h)in EXPECTED.items():take(B+name,dict(bytes=n,sha256=h))
 # Flat explicit delivery may name post-seal accounting/log receipts not in the manifest.
 d=decode(files[B+'actual-delivery.json']['text'].encode())
 write('intake-schema.json',dict(manifest_keys=list(m),delivery=d,files_count=len(files),source_read_bytes=sum(x['bytes']for x in reads),engine_metadata_pins_not_opened=m['decoder_expected_witness_pins']))
 cp=write('retained-files.json',dict(files=files))
 write('intake-receipt.json',dict(cache=cp,files=len(files),read_bytes=sum(x['bytes']for x in reads),peak_bytes=peak,reads=reads,author_execution=False,target_opened=False,engine_opened=False))
 print(json.dumps(dict(intake='passed',cache=cp,files=len(files),read_bytes=sum(x['bytes']for x in reads),peak_bytes=peak)))
def extend():
 cache=decode(read(O+'retained-files.json',dict(bytes=1905156,sha256='db6377aefefdaf684f1aab405aea37b683473ce9d9d3062b6ec8d2600167f5b5')));files=cache['files']
 d=decode(files[B+'actual-delivery.json']['text'].encode())
 for path,q in d['local_pins'].items():
  if not path.startswith('work/'):path=B+path
  if path in files:assert {k:files[path][k]for k in('bytes','sha256')}==q
  else:
   r=read(path,q);files[path]=dict(**q,text=r.decode('utf-8'))
 cp=write('retained-files-complete.json',dict(files=files))
 write('extension-receipt.json',dict(cache=cp,files=len(files),reads=reads,read_bytes=sum(x['bytes']for x in reads),peak_bytes=peak))
 print(json.dumps(dict(extension='passed',cache=cp,files=len(files),read_bytes=sum(x['bytes']for x in reads),peak_bytes=peak)))
def encoded(raw):
 i=0;rex=0;prefix=[]
 while raw[i]in(0x26,0x2e,0x36,0x3e,0x64,0x65,0x66,0x67,0xf0,0xf2,0xf3)or 0x40<=raw[i]<=0x4f:
  if 0x40<=raw[i]<=0x4f:rex=raw[i]
  else:prefix.append(raw[i])
  i+=1
 op=raw[i:i+2]if raw[i]==15 else raw[i:i+1];return i+len(op),op,rex,prefix
def memory_shape(raw,at,row):
 """Only check retained ModRM/SIB address fields and write direction, no disassembly."""
 i,op,rex,prefix=encoded(raw);mem=row['memory_operands']
 if not mem:return None
 assert len(mem)==1;modrm=raw[i];i+=1;mod=modrm>>6;rm=modrm&7;grp=(modrm>>3)&7;assert mod!=3
 regs=['rax','rcx','rdx','rbx','rsp','rbp','rsi','rdi']+['r'+str(x)for x in range(8,16)]
 index=None;scale=1
 if rm==4:
  sib=raw[i];i+=1;scale=1<<(sib>>6);ind=(sib>>3)&7;base=sib&7
  if ind!=4 or rex&2:index=regs[ind+((rex&2)<<2)]
  if mod==0 and base==5:base=None
  else:base=regs[base+((rex&1)<<3)]
 elif mod==0 and rm==5:base='rip'
 else:base=regs[rm+((rex&1)<<3)]
 if mod==1:disp=struct.unpack('<b',raw[i:i+1])[0]
 elif mod==2 or mod==0 and base in(None,'rip'):disp=struct.unpack('<i',raw[i:i+4])[0]
 else:disp=0
 m=mem[0];assert(m['base'],m['index'],m['scale'],m['displacement'])==(base,index,scale,disp),row['rva']
 assert m['segment']is None
 if base=='rip':assert m['rip_target_rva']==hex(at+len(raw)+disp)
 else:assert m['rip_target_rva']is None
 widths={b'\x88':1,b'\xc6':1,b'\x80':1,b'\xf6':1,b'\x0f\xb6':1,b'\x0f\xb7':2,b'\x0f\x6e':4,b'\x0f\x29':16,b'\x0f\x28':16}
 if op in(b'\x0f\x10',b'\x0f\x11'):width=8 if 0xf2 in prefix else 4 if 0xf3 in prefix else 16
 elif op in widths:width=widths[op]
 else:width=8 if rex&8 else 2 if 0x66 in prefix else 4
 assert m['width_bytes']==width,(row['rva'],op.hex(),width,m)
 dest=op in(b'\x88',b'\x89',b'\xc6',b'\xc7',b'\x0f\x11',b'\x0f\x29')or op in(b'\x80',b'\x81',b'\x83')and grp!=7
 assert op in(b'\x88',b'\x89',b'\xc6',b'\xc7',b'\x0f\x11',b'\x0f\x29',b'\x80',b'\x81',b'\x83',b'\xf6',b'\x8b',b'\x8d',b'\x3b',b'\x0f\xb6',b'\x0f\xb7',b'\x0f\x10',b'\x0f\x28',b'\x0f\x1f'),(row['rva'],op.hex())
 return dict(rva=row['rva'],raw_hex=raw.hex(),opcode=op.hex(),base=base,index=index,scale=scale,disp=disp,width=width,explicit_store=dest,actual_dereference=op not in(b'\x8d',b'\x0f\x1f'))
def audit():
 cp=dict(bytes=1917809,sha256='8aeb4088b8fdfe5468357f2590bfda5eaf31d7817229d005ff64aef0fb0c9841')
 files=decode(read(O+'retained-files-complete.json',cp))['files'];docs={}
 for path,e in files.items():
  assert pin(e['text'].encode())=={k:e[k]for k in('bytes','sha256')}
  if path.endswith('.json')and e['bytes']:docs[path]=decode(e['text'].encode())
 def pn(path):return {k:files[path][k]for k in('bytes','sha256')}
 def obj(name):return docs[B+name]
 m=obj('actual-manifest.json');c=obj('capture.json');s=obj('actual-selected-evidence.json');o=obj('owned-code.json');con=obj('actual-contract.json');d=obj('actual-delivery.json')
 assert len(files)==56 and len(m['source_pins'])==44 and len(m['decoder_expected_witness_pins'])==38
 assert all(pn(path)==q for path,q in m['source_pins'].items())
 assert all(pn(path if path.startswith('work/')else B+path)==q for path,q in d['local_pins'].items())
 assert c['source_pins']==obj('claim.json')['source_pins']==obj('source-manifest.json')['source_pins']
 assert c['decoder_expected_witness_pins']==m['decoder_expected_witness_pins']
 assert len(c['source_pins'])==64 and sum(path.startswith('work/deps/')for path in c['source_pins'])==38
 for path,q in c['source_pins'].items():
  if not path.startswith('work/deps/'):assert pn(path)==q
 assert s['capture']==con['capture_pin']==pn(B+'capture.json')and s['owned']==con['owned_code_pin']==c['owned_code_pin']==pn(B+'owned-code.json')
 assert c['game_sha256']==o['game_sha256']==s['game_sha256']=='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
 raw=bytes.fromhex(o['raw_hex']);begin,end=map(lambda x:int(x,16),o['window']);assert(begin,end,len(raw))==(0x10d23c0,0x10d2bfd,2109)
 assert hashlib.sha256(raw).hexdigest()==o['sha256']and o['bytes']==len(raw)and o['file_offset']==17635264
 a=c['analysis'];rows=s['instructions'];assert rows==a['instructions']and s['edges']==a['edges']and s['terminals']==a['terminals']
 by={int(x['rva'],16):x for x in rows};assert len(rows)==len(by)==418
 at=begin;shapes=[];graph={};branches=[];calls=[];targets=set();opcounts=Counter()
 for r in rows:
  n=int(r['rva'],16);b=bytes.fromhex(r['bytes']);assert n==at and b==raw[n-begin:n-begin+len(b)];at+=len(b)
  i,op,rex,prefix=encoded(b);opcounts[op.hex()]+=1
  shape=memory_shape(b,n,r)
  if shape:shapes.append(shape)
  nextat=n+len(b);mn=r['mnemonic'];g=[]
  if op==b'\xe8':
   assert len(b)==5 and mn=='call';t=nextat+struct.unpack('<i',b[1:])[0];calls.append((n,t));targets.add(t);g=[nextat]
  elif op in(b'\xeb',b'\xe9')or len(op)==1 and 0x70<=op[0]<=0x7f or len(op)==2 and op[0]==15 and 0x80<=op[1]<=0x8f:
   delta=struct.unpack('<b',b[-1:])[0]if len(op)==1 and op!=b'\xe9'else struct.unpack('<i',b[-4:])[0]
   t=nextat+delta;branches.append((n,t));g=[t]if mn=='jmp'else[t,nextat]
  elif op in(b'\xc3',b'\xcc'):assert mn==('ret'if op==b'\xc3'else'int3')
  else:g=[nextat]
  graph[n]=g
 assert at==end and len(calls)==25 and len(targets)==17 and len(branches)==15
 assert len(s['edges'])==40
 for e in s['edges']:
  site=int(e['site'],16);row=by[site];kind=row['mnemonic'];pairs0=calls if kind=='call'else branches
  t=dict(pairs0)[site];assert e['kind']==kind and e['target_rva']==hex(t)and e['target_operand']==hex(t)
  assert e['inside_owned_window']==(begin<=t<end)and e['callee_followed']is False
  assert e['local_branch_target_enqueued']==(kind!='call'and begin<=t<end)
  assert e['fallthrough']==(None if kind=='jmp'else hex(site+len(bytes.fromhex(row['bytes']))))
 seen=set();queue=deque([begin]);parents={}
 while queue:
  n=queue.popleft()
  if n in seen:continue
  assert n in by;n0=by[n];seen.add(n)
  for t in graph[n]:
   assert t in by
   if t not in parents and t!=begin:parents[t]=n
   queue.append(t)
 assert len(seen)==418
 assert [(r['rva'],r['mnemonic'])for r in rows if r['mnemonic']in('ret','int3')]==[('0x10d2bea','ret'),('0x10d2bfc','int3')]
 assert a['local_normal_CFG_closed']is False and a['external_CALL_normal_return_assumed_for_fallthrough']is True and a['dynamic_reachability_verified']is False
 look=a['lookahead_inputs'];assert len(look)==418 and sum(x['bytes']for x in look)==6234
 union=set()
 for x in look:
  n=int(x['rva'],16);assert n in by and x['bytes']==min(15,end-n);union.update(range(n,n+x['bytes']))
 assert union==set(range(begin,end))and a['decoded_unique_bytes']==a['decoder_input_unique_bytes']==2109 and a['decoder_overlap_bytes']==4125 and a['undecoded_owned_intervals']==[]
 stores=[x for x in shapes if x['explicit_store']];store_rows=[by[int(x['rva'],16)]for x in stores]
 flagged=[r for r in rows if any(v['write']for v in r['memory_operands'])]
 omitted=[r for r in store_rows if not any(v['write']for v in r['memory_operands'])]
 assert len(stores)==184 and len(flagged)==168 and len(omitted)==16
 assert store_rows==s['explicit_raw_classified_store_rows']and omitted==s['raw_MOVUPS_destination_access_omissions']
 assert all(encoded(bytes.fromhex(r['bytes']))[1]==b'\x0f\x11'and r['mnemonic']=='movups'for r in omitted)
 counts=dict(Counter(x['base']for x in stores));assert counts==s['store_base_register_counts_not_business_classes']and counts['rdi']==62 and counts['rip']==2
 implicit={x:sum(r['mnemonic']==x for r in rows)for x in('push','call','pop','ret')};assert implicit==s['implicit_stack_sites']==dict(push=5,call=25,pop=5,ret=1)
 assert by[0x10d23f5]==s['receiver_definition']and by[0x10d23f5]['bytes']=='488bf9'
 assert all(not set(r['registers_written'])&{'rdi','edi','di','dil'}for r in rows if 0x10d23f5<int(r['rva'],16)<=0x10d24ea)
 assert s['anchor']==by[0x10d24e3]and by[0x10d24e3]['bytes']=='488d05de83c800'
 assert 0x10d24ea+struct.unpack('<i',bytes.fromhex('de83c800'))[0]==0x1d5a8c8
 assert s['following_store']==by[0x10d24ea]and by[0x10d24ea]['bytes']=='488907'
 path=s['anchor_minimal_path_overapprox_normal_external_return_assumption'];pathnums=[int(r if type(r)is str else r['rva'],16)for r in path]
 assert len(path)==62 and pathnums[0]==begin and pathnums[-1]==0x10d24e3
 assert all(n in by for n in pathnums)and all(y in graph[x]for x,y in zip(pathnums,pathnums[1:]))
 # Selected containing pdata/neighbor arithmetic from retained bytes, not fresh PE metadata.
 pp=c['pdata_requests'];assert len(pp)==20 and len({x['index']for x in pp})==17
 for x in pp:
  b,e,u=struct.unpack('<III',bytes.fromhex(x['raw_hex']));assert b==int(x['begin_rva'],16)and e==int(x['end_exclusive'],16)and u==int(x['unwind_rva_unfollowed'],16)
  assert int(x['rva'],16)==0x2465000+x['index']*12
  assert x['file_offset']==int(x['rva'],16)-0x132000
 assert c['selected']['index']==33731 and int(c['selected']['begin_rva'],16)==begin and int(c['selected']['end_exclusive'],16)==end
 assert int(c['previous']['end_exclusive'],16)<=begin and end<=int(c['next']['begin_rva'],16)
 assert begin<=0x10d24e3 and 0x10d24ea<=end and s['pdata_selected_and_neighbors']==[c['selected'],c['previous'],c['next']]
 assert c['pdata_physical_bytes']==240 and c['pdata_unique_bytes']==204
 assert len(c['sparse_reads'])==21 and all(x['complete']and x['requested_bytes']==x['bytes']for x in c['sparse_reads'])
 assert sum(x['bytes']for x in c['sparse_reads'])==240+2109
 hashes=c['full_PE_authentication_reads'];assert [x['phase']for x in hashes]==['before','after']
 assert all(x['completed']and x['bytes_read']==38462504 and x['sha256']==c['game_sha256']for x in hashes)
 assert sum(x['bytes_read']for x in hashes)+sum(x['bytes']for x in c['sparse_reads'])==c['total_PE_physical_bytes']==76927357
 journal=c['source_file_reads'];assert len(journal)==161 and sum(x['bytes']for x in journal)==c['source_file_read_bytes']==17885120
 assert Counter(x['phase']for x in journal)==Counter(authorization_preflight=14,source_engine_before=71,source_engine_after=76)
 auth=obj('run-authorization.json');assert auth['single_attempt']is True and auth['root_explicit_start_received']is True and auth['authorizes_retry']is False
 assert c['authorization_pin']==obj('claim.json')['authorization_pin']==pn(B+'run-authorization.json')and c['source_manifest']==o['source_manifest']==auth['source_manifest']==pn(B+'source-manifest.json')
 assert c['entry_seed_pin']==auth['entry_seed_pin']==pn(B+'entry-seed.json')and auth['producer_pin']==pn(B+'produce.py')
 assert obj('claim.json')['automatic_retry']is False
 rf=auth['seed_review_path'];assert pn(rf)==auth['seed_review_pin']==c['root_review_pin']
 assert pn(auth['root_review_manifest']['path'])=={k:auth['root_review_manifest'][k]for k in('bytes','sha256')}
 rootrev=docs[rf];assert rootrev['sealed']and rootrev['passed']and rootrev['blocking_findings']==[]
 for g in('source_peer_review','upstream_scan_review'):
  for part,q in auth[g].items():assert pn(q['path'])=={k:q[k]for k in('bytes','sha256')}
  rev=docs[auth[g]['findings']['path']];assert rev['sealed']and rev['passed']and rev['blocking_findings']==[]
  if g=='source_peer_review':
   assert rev['subject_source_manifest']==pn(B+'source-manifest.json')and rev['subject_producer']==pn(B+'produce.py')and rev['subject_entry_seed']==pn(B+'entry-seed.json')
 rootreceipt=docs['work/reports/server-vtable-current-reference-owner-root-authorization-20261016-r2/receipt.json'];assert rootreceipt['before']==rootreceipt['after']
 assert all(pn(path)==q for path,q in rootreceipt['before'].items())and rootreceipt['authorization']==pn(B+'run-authorization.json')
 assert c['normal_target_context_exit']and c['commit_after_target_close_and_final_guards']and c['source_engine_before_after_equal']
 acq=obj('actual-acquisition-receipt.json');assert acq['actual_producer_attempts']==1 and acq['tool_command_exit_code_observed']==0 and acq['all_child_shells_collected']and acq['failure_files']==[]
 assert acq['capture_pin']==pn(B+'capture.json')and acq['owned_code_pin']==pn(B+'owned-code.json')and acq['R1_invoked']is False
 assert obj('actual-seal-run-receipt.json')['exit_code']==0 and obj('actual-seal-run-receipt.json')['producer_reruns']==0 and obj('actual-filecheck-run-receipt.json')['exit_code']==0
 check=obj('actual-filecheck.json');assert check['passed']and check['actual_flat_pins_verified']==44 and check['subject_actual_manifest']==pn(B+'actual-manifest.json')
 assert sum(x['bytes']for x in check['read_events'])==check['explicit_read_bytes']==1713092
 acc=obj('actual-retained-read-accounting.json');assert sum(x['bytes']for x in acc['returned_read_journal'])==acc['measured_retained_read_bytes']==2843186
 da=obj('actual-delivery-read-accounting.json');assert sum(x['bytes']for x in da['delivery_hash_read_events'])==da['delivery_hash_explicit_bytes']==1054924
 assert da['retained_sealer_explicit_bytes_through_manifest']==acc['measured_retained_read_bytes']+pn(B+'actual-retained-read-accounting.json')['bytes']==2862136
 assert 2862136+1713092+1054924==da['retained_measured_sum']==5630152
 assert da['retained_measured_sum']+2097152==da['retained_conservative_upper_bytes']==7727304
 assert 17885120+7727304==da['combined_explicit_upper_bytes']==25612424
 assert da['complete_OS_IO_claimed']is False and da['allowance_not_measured_IO']is True
 # Re-read fixed source text only. Engine metadata is never opened by this audit.
 for path,e in files.items():read(path,{k:e[k]for k in('bytes','sha256')})
 replay=dict(sealed=True,scope='retained_raw_and_conditional_CFG_only',rows=418,owned_unique_bytes=2109,raw_modrm_memory_shapes=shapes,
  explicit_store_count=184,flagged_store_count=168,raw_MOVUPS_missing_flag_sites=[r['rva']for r in omitted],store_bases=counts,implicit_stack_static_sites=implicit,
  calls=[dict(site=hex(n),signed_rel32_target=hex(t))for n,t in calls],branches=[dict(site=hex(n),target=hex(t))for n,t in branches],CFG_reachable_row_count=len(seen),
  terminals=s['terminals'],normal_closed=False,anchor_raw='488d05de83c800',RIP_target='0x1d5a8c8',following_raw='488907',
  receiver_binding='RDI copies incoming RCX at 10d23f5; original receiver identity at store additionally requires unfollowed calls obey normal nonvolatile/frame semantics; contents/lifetime unknown',
  decoder_attempt_inputs_retained=6234,decoder_union=2109,decoder_repeat=4125,pdata_physical=240,pdata_unique=204,target_PE_physical_producer_witness=76927357,
  independent_PE_decoder_engine_native_operations=0)
 rp=write('raw-replay.json',replay)
 prior=decode(read(O+'intake-receipt.json'));ext=decode(read(O+'extension-receipt.json'))
 failed=decode(read(O+'own-schema-failure-r1/failure.json'));failed2=decode(read(O+'own-schema-failure-r2/failure.json'));failure_reads=sum(x['bytes']for x in failed['reads'])+failed2['completed_explicit_read_bytes']
 resources=dict(intake_read_bytes=prior['read_bytes'],extension_read_bytes=ext['read_bytes'],current_audit_reads=sum(x['bytes']for x in reads),failed_audit_read_bytes=failure_reads,manual_cache_inspection_bytes=7658583,
  manual_other_inspection_allowance=524288,planned_own_manifest_check_allowance=4300000,limit=LIMIT,peak_self_bytes=peak,
  disclaimer='Completed explicit file reads plus named manual/planned allowances; not all OS/loader I/O or a hard process-tree limit')
 upper=sum(resources[k]for k in('intake_read_bytes','extension_read_bytes','current_audit_reads','failed_audit_read_bytes','manual_cache_inspection_bytes','manual_other_inspection_allowance','planned_own_manifest_check_allowance'))
 assert upper<LIMIT;resources['conservative_complete_stage_upper_bytes']=upper
 findings=dict(schema='EU4-R72-R2-ACTUAL-INDEPENDENT-REVIEW/1',sealed=True,passed=True,blocking_findings=[],
  scope='Full retained actual raw/CFG/store/conditional dataflow review of sole containing fragment; no new target/decoder/tool run',
  reviewer_role='Nonauthor of R72 producer/actual/sealer; same reviewer previously performed R2 source-peer review. validation_audit authored acquisition; root raw/fullgrant and upstream scan/source reviews remain distinct witnesses.',
  subject_manifest=pn(B+'actual-manifest.json'),subject_actual_manifest=pn(B+'actual-manifest.json'),subject_contract=pn(B+'actual-contract.json'),subject_contract_pin=pn(B+'actual-contract.json'),subject_capture=pn(B+'capture.json'),subject_capture_pin=pn(B+'capture.json'),subject_owned=pn(B+'owned-code.json'),subject_selected_evidence=pn(B+'actual-selected-evidence.json'),raw_replay=rp,
  checks=dict(flat_actual_manifest_pins=44,explicit_delivery_and_manifest_total_files=56,engine38_metadata_only=True,all_selected_rows_exact_raw=True,full_owned_CFG_overapprox_replayed=True,
   all_raw_memory_address_fields_and_write_directions_replayed=True,pdata_containing_neighbor_arithmetic=True,three_reviews_and_root_authorization_bound=True,one_actual_no_R1_retry=True,
   normal_close_before_publish_sourceauthreviews_prepost_retained=True,source_prepost_current_text_pins_equal=True,source_guard_raw_buffer_bound_before_parse_engine_selection=True),
  precision_notes=[
   'Anchor LEA computes module-relative address; its Capstone read flag does not dereference that address. The next instruction writes that address to [RDI]. No constructor/class/mode/layout identity follows.',
   'RDI=entry RCX is conditional on earlier unfollowed calls obeying normal Win64 nonvolatile/frame discipline. No object content/lifetime invariance or world lease is inferred.',
   '418 rows/2109 bytes are complete owned coverage and finite CFG overapproximation, not an observed runtime path. RET and INT3 are both reachable overapproximation terminals; preceding external call is not proven nonreturning.',
   '184 explicit raw memory destination stores include all 16 MOVUPS missing Capstone write flags. Syntactic bases RDI62/RIP2 do not certify allocation extent or classes. PUSH/CALL/POP/RET implicit stack sites are counted separately.',
   'Selected/adjacent pdata records are disjoint; binary search assumes globally ordered table. Whole-table ordering/overlapping aliases and unwind bodies were not inspected.',
   'Producer before/after source, 38 decoder hashes, PE SHA, timing/peak and shell collection are retained witnesses. This audit re-pins only admitted flat text files; it neither opens engine bodies nor independently reruns acquisition.',
   'R2 raw source_manifest buffer pin dominates parse/engine selection; external file coherence/ABA remains unproved. R1 blocker and historical R71 legacy-after-check precision remain unchanged.',
   'Explicit producer source 17885120 plus retained upper 7727304 =25612424; PE 76927357 is separate. Retained 2097152 is an allowance, not measured I/O. Software peak witness does not prove a hard Job/tree limit.'],
  author_resource_witness=dict(source=17885120,retained_measured=5630152,retained_allowance=2097152,retained_upper=7727304,combined_upper=25612424,PE_separate=76927357,producer_peak=27725824),
  independent_resources=resources,operations=dict(author_programs=0,tests=0,PE=0,engine_body=0,decoder=0,game_process=0,Frida=0,native=0,requests=0),
  authority={k:False for k in('constructor_verified','class_layout_verified','class_mode_verified','host_guard_change_authorized','native_ready','callable','reader_adoption_allowed','selected_effect_verified','world_lease','atomic_snapshot','external_ABA_excluded','authorizes_retry','further_actual_authorized')},
  own_schema_failure=dict(preserved=True,reason='Own R1 contract pin key assumption and R2 path string-vs-row assumption; narrow reviewer fixes only; fixed cached pdata section offset arithmetic',author_reruns=0),
  R1_remains_blocked=True,author_frozen_sources_need_change=False,all_shells_collected=True)
 fp=write('findings.json',findings)
 auditpin=pin(read('work/review_r72_actual_r2_20261016.py'))
 local={O+'raw-replay.json':rp,O+'findings.json':fp,'work/review_r72_actual_r2_20261016.py':auditpin,O+'retained-files-complete.json':cp}
 for n in('intake-receipt.json','extension-receipt.json'):local[O+n]=pin(read(O+n))
 for n in('own-schema-failure-r1/review.py','own-schema-failure-r1/failure.json','own-schema-failure-r2/review.py','own-schema-failure-r2/failure.json'):local[O+n]=pin(read(O+n))
 mp=write('manifest.json',dict(sealed=True,passed=True,subject_manifest=pn(B+'actual-manifest.json'),source_pins={path:pn(path)for path in files}|local,
  flat_text_files=56,engine_witness_metadata_not_opened=m['decoder_expected_witness_pins'],independent_stage_upper=upper,native_ready=False,authorizes_actual=False))
 print(json.dumps(dict(passed=True,findings=fp,manifest=mp,raw_replay=rp,upper_bytes=upper,peak_bytes=peak)))
def check():
 m=decode(read(O+'manifest.json'));assert m['passed']and m['sealed']
 for path,q in m['source_pins'].items():read(path,q)
 r=dict(sealed=True,passed=True,checked_pins=len(m['source_pins']),read_bytes=sum(x['bytes']for x in reads),peak_bytes=peak,
  engine_metadata_not_opened=38,author_program_tests_PE_decoder_game_native=0,all_shells_collected=True,authorizes_actual=False)
 z=write('verification.json',r);print(json.dumps(dict(passed=True,verification=z,pins=r['checked_pins'],read_bytes=r['read_bytes'],peak_bytes=peak)))
if __name__=='__main__':
 try:
  if sys.argv[1:] == ['--intake']:intake()
  elif sys.argv[1:]==['--extend']:extend()
  elif sys.argv[1:]==['--audit']:audit()
  elif sys.argv[1:]==['--check']:check()
  else:raise ValueError('expected --intake')
 except BaseException as e:
  if OUT.exists():
   dest=OUT/('own-failure-'+(sys.argv[1].lstrip('-')if len(sys.argv)>1 else'args')+'.json')
   if not dest.exists():write(dest.name,dict(error=type(e).__name__,message=str(e),reads=reads,peak_bytes=peak))
  raise
