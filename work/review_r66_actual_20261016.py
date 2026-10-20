"""Independent retained-only R66 review: manual opcode facts, no decoder import."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import hashlib
import json
import struct
import sys

ROOT=Path(__file__).resolve().parents[1]
B='work/reports/war-peace-api-20261016-r66-generated-record-postprocess/'
O='work/reports/war-peace-api-20261016-r66-independent-review/'
OUT=ROOT/O
LIMIT=24*1024*1024;MEMORY=768*1024*1024
GAME='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
CACHE_PIN=dict(bytes=1268988,sha256='bbb490b749a10062464b246bcacd34db303f1efa0dbdc5e2176b6bbd273fd972')
SUPPLEMENT_PIN=dict(bytes=23731,sha256='d1afb4e42533eb3b96a2db685c0f289dca303157e30451047423c33a5eb496bf')
ACCOUNTING_PIN=dict(bytes=22982,sha256='ebf3cc6c4deb215ad314826700fab98a07aa731734ba412845c5c82707820cec')
reads=[];peak=0
class PMC(ctypes.Structure):
 _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
k=ctypes.WinDLL('kernel32',use_last_error=True);p=ctypes.WinDLL('psapi',use_last_error=True)
k.GetCurrentProcess.restype=wintypes.HANDLE;p.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(PMC),wintypes.DWORD]
def guard():
 global peak
 x=PMC();x.cb=ctypes.sizeof(x);assert p.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(x),x.cb)
 peak=max(peak,x.WorkingSetSize,x.PrivateUsage,x.PeakWorkingSetSize,x.PeakPagefileUsage);assert peak<=MEMORY
def pin(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def pairs(items):
 d={}
 for k,v in items:assert k not in d;d[k]=v
 return d
def decode(raw):return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
def read(path,pn=None):
 assert 'eu4.exe' not in path.lower() and not path.startswith('work/deps/')
 guard();f=ROOT/path;a=f.stat();assert a.st_size<=4*1024*1024
 raw=f.read_bytes();z=f.stat();assert len(raw)==a.st_size and(a.st_size,a.st_mtime_ns)==(z.st_size,z.st_mtime_ns)
 actual=pin(raw)
 if pn is not None:assert actual==pn,(path,actual,pn)
 reads.append(dict(path=path,**actual));guard();return raw
def write(name,obj):
 raw=(json.dumps(obj,ensure_ascii=True,indent=2)+'\n').encode('ascii');assert len(raw)<4*1024*1024
 with (OUT/name).open('xb') as f:f.write(raw)
 return pin(raw)
def iv(n):return int(n,16) if isinstance(n,str) else n
def rel(site,raw):return site+len(raw)+int.from_bytes(raw[1:],'little',signed=True)
def relative(path):
 s=str(path).replace('\\','/');prefix=ROOT.as_posix()+'/'
 return s[len(prefix):] if s.startswith(prefix) else s
def false_authority(d):assert d and all(x is False for x in d.values())

# Each row was independently classified from the retained bytes. This is a
# fixed50-row review profile, not an x64 decoder or a delivered-producer replay.
SPEC='''
48895c2408 mov
48896c2410 mov
4889742418 mov
57 push
b840100000 mov
e8d6e80901 call
482be0 sub
0fb61a movzx
488b6908 mov
488b31 mov
488bfd mov
482bfe sub
48c1ff02 sar
48b8abaaaaaaaaaaaaaa movabs
480faff8 imul
4883ff20 cmp
7f0d jg
488bd5 mov
488bce mov
e8003e0000 call
eb53 jmp
488bc7 mov
4899 cqo
482bc2 sub
48d1f8 sar
488bd7 mov
482bd0 sub
488d4c2430 lea
e84354adff call
90 nop
885c2428 mov
488b442438 mov
4889442420 mov
4c8b4c2430 mov
4c8bc7 mov
488bd5 mov
488bce mov
e8813e0000 call
90 nop
48817c243855010000 cmp
760a jbe
488b4c2430 mov
e87b8adc00 call
4c8d9c2440100000 lea
498b5b10 mov
498b6b18 mov
498b7320 mov
498be3 mov
5f pop
c3 ret
'''
STORE={0x994f00:('rsp',8,8),0x994f05:('rsp',16,8),0x994f0a:('rsp',24,8),0x994f6e:('rsp',40,1),0x994f77:('rsp',32,8)}
READ={0x994f1d:('rdx',0,1),0x994f20:('rcx',8,8),0x994f24:('rcx',0,8),0x994f72:('rsp',56,8),0x994f7c:('rsp',48,8),0x994f90:('rsp',56,8),0x994f9b:('rsp',48,8),0x994fad:('r11',16,8),0x994fb1:('r11',24,8),0x994fb5:('r11',32,8)}
CALL={0x994f15:0x1a337f0,0x994f4b:0x998d50,0x994f68:0x46a3b0,0x994f8a:0x998e10,0x994fa0:0x175da20}
BRANCH={0x994f43:0x994f52,0x994f50:0x994fa5,0x994f99:0x994fa5}

def main():
 cache=decode(read(O+'retained-files.json',CACHE_PIN));supp=decode(read(O+'retained-supplement.json',SUPPLEMENT_PIN));acc=decode(read(O+'retained-accounting.json',ACCOUNTING_PIN))
 files=cache['files']|supp['files']|acc['files'];objects={}
 for path,e in files.items():
  raw=bytes.fromhex(e['raw_hex']);assert pin(raw)=={k:e[k] for k in ('bytes','sha256')}
  if path.endswith('.json'):objects[path]=decode(raw)
 def obj(name):return objects[B+name]
 def pn(path):return {k:files[path][k] for k in ('bytes','sha256')}
 m=obj('manifest.json');c=obj('capture.json');owned=obj('owned-code.json');s=obj('selected-native.json');contract=obj('contract.json')
 assert len(m['source_pins'])==41 and len(m['decoder_expected_witness_pins'])==38
 assert m['source_pins']=={path:pn(path) for path in m['source_pins']}
 assert m['engine_files_opened_during_retained_seal']==0 and m['recursive_closure_claim'] is False
 assert c['game_sha256']==owned['game_sha256']==GAME and c['game_bytes']==38462504
 assert owned['window']==['0x994f00','0x994fbe'] and owned['bytes']==190 and owned['full_extent_owned'] is True
 raw=bytes.fromhex(owned['raw_hex']);assert len(raw)==190 and hashlib.sha256(raw).hexdigest()==owned['sha256']==s['owned_raw_sha256']
 rows=c['analysis']['instructions'];assert rows==s['instructions'] and len(rows)==50
 specs=[line.split() for line in SPEC.splitlines() if line.strip()];assert len(specs)==50
 cursor=0x994f00;replay=[];successors={};rowmap={}
 for row,(hx,mnemonic) in zip(rows,specs):
  at=iv(row['rva']);b=bytes.fromhex(hx);assert at==cursor and row['bytes']==hx and row['mnemonic']==mnemonic
  assert raw[at-0x994f00:at-0x994f00+len(b)]==b
  mem=[q for q in row['memory_operands'] if mnemonic!='lea']
  expected_read=READ.get(at);expected_store=STORE.get(at)
  assert sum(q['read'] is True for q in mem)==(1 if expected_read else 0)
  assert sum(q['write'] is True for q in mem)==(1 if expected_store else 0)
  for expected,field in ((expected_read,'read'),(expected_store,'write')):
   if expected:
    q=next(q for q in mem if q[field]);assert(q['base'],q['displacement'],q['width_bytes'])==expected
    assert q['index'] is None and q['segment'] is None and q['rip_target_rva'] is None
  if at in CALL|BRANCH:
   target=rel(at,b);assert target==(CALL|BRANCH)[at] and row['immediates']==[target]
  nextat=at+len(b)
  successors[at]=[] if mnemonic=='ret' else [BRANCH[at]] if mnemonic=='jmp' else [nextat,BRANCH[at]] if at in BRANCH else [nextat]
  replay.append(dict(rva=hex(at),raw_hex=hx,mnemonic=mnemonic,owned_bytes_equal=True,
   explicit_read=expected_read,explicit_store=expected_store,successors=[hex(n) for n in successors[at]],
   CALL_target=hex(CALL[at]) if at in CALL else None,CALL_effect='unfollowed_normal_return_assumed' if at in CALL else None))
  rowmap[at]=row;cursor=nextat
 assert cursor==0x994fbe and b''.join(bytes.fromhex(x[0]) for x in specs)==raw
 reached=set();todo=[0x994f00]
 while todo:
  at=todo.pop()
  if at in reached:continue
  assert at in rowmap;reached.add(at);todo.extend(successors[at])
 assert len(reached)==50
 edges=c['analysis']['edges'];assert edges==s['edges'] and len(edges)==8
 for e in edges:
  at=iv(e['site']);assert iv(e['target_rva'])==(CALL|BRANCH)[at]
  assert e['inside_owned_window'] is (at in BRANCH)
  assert e['callee_followed'] is False
  assert e['local_branch_target_enqueued'] is (at in BRANCH)
  expected_next=None if rowmap[at]['mnemonic']=='jmp' else at+len(bytes.fromhex(rowmap[at]['bytes']))
  assert e['fallthrough']==(hex(expected_next) if expected_next is not None else None)
 assert c['analysis']['terminals']==s['terminals']==[dict(kind='normal_ret',rva='0x994fbd')]
 assert c['analysis']['undecoded_owned_intervals']==[] and c['analysis']['decoded_unique_bytes']==190
 assert c['analysis']['local_normal_CFG_closed'] is True and c['analysis']['dynamic_reachability_verified'] is False
 look=c['analysis']['lookahead_inputs'];assert len(look)==50
 for inp,row in zip(look,rows):assert iv(inp['rva'])==iv(row['rva']) and inp['bytes']==min(15,0x994fbe-iv(row['rva']))
 assert sum(x['bytes'] for x in look)==705 and c['analysis']['decoder_overlap_bytes']==515
 assert {iv(x['rva']) for x in s['explicit_store_sites']}==set(STORE)
 assert {iv(x['rva']) for x in s['explicit_read_sites']}==set(READ)
 assert s['access_count']==dict(explicit_stores=5,stack_stores=5,explicit_reads=10,H_or_record_or_borrowed_RDX_direct_stores=0)
 # Retained cached section arithmetic; no PE/headers opened.
 anchors=objects['work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json'];sections=anchors['sections']
 def offset(rva,n):
  found=[z for z in sections if iv(z['rva'])<=rva and rva+n<=iv(z['rva'])+z['raw_size']];assert len(found)==1
  z=found[0];return z['raw_file_offset']+rva-iv(z['rva'])
 pd=next(z for z in sections if z['name']=='.pdata');requests=c['pdata_requests'];assert len(requests)==19
 for q in requests:
  rr=bytes.fromhex(q['raw_hex']);a,z,u=struct.unpack('<III',rr);assert len(rr)==12
  assert (a,z,u)==tuple(iv(q[k]) for k in ('begin_rva','end_exclusive','unwind_rva'))
  assert iv(q['rva'])==iv(pd['rva'])+12*q['index'] and q['file_offset']==offset(iv(q['rva']),12)
 lo,hi=0,pd['virtual_size']//12
 for q in requests:
  if q['reason']!='binary_search':continue
  mid=(lo+hi)//2;assert q['index']==mid
  if iv(q['begin_rva'])<=0x994f00:lo=mid+1
  else:hi=mid
 assert lo==hi==19196
 for key,index in [('selected',lo-1),('previous',lo-2),('next',lo)]:assert c[key]['index']==index
 assert c['selected']['raw_hex']=='004f9900be4f9900d4dfe701' and c['exact_pdata_begin'] is True
 assert iv(c['selected']['end_exclusive'])-iv(c['selected']['begin_rva'])==190
 assert iv(c['previous']['end_exclusive'])<=0x994f00 and 0x994fbe<=iv(c['next']['begin_rva'])
 assert c['pdata_physical_bytes']==228 and c['pdata_unique_bytes']==len({q['index'] for q in requests})*12==192
 assert len(c['sparse_reads'])==20 and c['sparse_reads'][-1]['kind']=='single_entry_code'
 assert c['sparse_reads'][-1]['bytes']==190 and c['sparse_reads'][-1]['file_offset']==owned['file_offset']==offset(0x994f00,190)
 assert sum(x['bytes'] for x in c['sparse_reads'])==418
 assert c['full_PE_authentication_reads']==[dict(phase=phase,bytes_read=38462504,completed=True,sha256=GAME) for phase in ('before','after')]
 assert c['total_PE_physical_bytes']==2*38462504+418==76925426
 # Entry provenance and all three independent reviews remain separate gates.
 seed=obj('entry-seed.json');up=objects['work/reports/war-peace-api-20261016-r62-gold-recipient-generator/owned-code.json']
 ub=bytes.fromhex(up['raw_hex']);begin=iv(up['window'][0]);site=0x9846d5;cb=ub[site-begin:site-begin+5]
 assert cb.hex()==seed['raw_call']=='e826080100' and rel(site,cb)==0x994f00
 assert seed['minimal_CALL_prefix_raw_rows']==objects['work/reports/war-peace-api-20261016-r62-gold-recipient-generator/capture.json']['analysis']['instructions'][125:128]
 auth=obj('run-authorization.json');acq=obj('acquisition-receipt.json');claim=obj('claim.json');rootclaim=obj('root-invocation-claim.json');base=obj('source-manifest.json')
 assert auth['root_explicit_start_received'] is True and auth['automatic_retry'] is False
 assert auth['source_manifest']==pn(B+'source-manifest.json') and auth['producer_pin']==pn(B+'produce.py') and auth['entry_seed_pin']==pn(B+'entry-seed.json')
 assert c['source_manifest']==claim['source_manifest']==auth['source_manifest']
 assert c['source_pins']==claim['source_pins']==base['source_pins']
 assert c['authorization_pin']==claim['authorization_pin']==rootclaim['authorization']==pn(B+'run-authorization.json')
 assert m['decoder_expected_witness_pins']==base['decoder_expected_witness_pins']==c['decoder_expected_pins']
 reviews={auth['seed_review_path']:auth['seed_review_pin']}
 for group in ('upstream_body_review','source_peer_review'):
  for part,decl in auth[group].items():reviews[decl['path']]={k:decl[k] for k in ('bytes','sha256')}
 rm=auth['root_review_manifest'];reviews[rm['path']]={k:rm[k] for k in ('bytes','sha256')}
 for path,expected in reviews.items():assert pn(path)==expected
 for path in [auth['seed_review_path'],auth['upstream_body_review']['findings']['path'],auth['source_peer_review']['findings']['path']]:
  v=objects[path];assert v['sealed'] is True and v['passed'] is True and v['blocking_findings']==[]
 peer=objects[auth['source_peer_review']['findings']['path']]
 assert peer['subject_source_manifest']==pn(B+'source-manifest.json') and peer['subject_producer']==pn(B+'produce.py') and peer['subject_entry_seed']==pn(B+'entry-seed.json')
 assert acq['review_pins']==rootclaim['review_pins']==reviews
 assert acq['exit_code']==0 and acq['direct_owned_child_collected'] is True and acq['failure_files']==[]
 assert acq['all_admission_pins_prepost_equal'] is True and acq['exit_and_file_success'] is True
 assert acq['stdout']==pn(B+'producer.stdout.json') and acq['stderr']==pn(B+'producer.stderr.txt')
 assert files[B+'producer.stderr.txt']['bytes']==0
 stdout=obj('producer.stdout.json');assert stdout['capture_pin']==pn(B+'capture.json')
 assert c['source_engine_before_after_equal'] is True
 journal=c['source_file_reads'];assert sum(x['bytes'] for x in journal)==c['source_file_read_bytes']==16973248
 for phase in ('source_engine_before','source_engine_after'):
  er=[x for x in journal if x['phase']==phase and x['operation']=='streaming_engine_pin']
  assert len(er)==38 and {relative(x['path']):x['bytes'] for x in er}=={p:v['bytes'] for p,v in m['decoder_expected_witness_pins'].items()}
 assert sum(x['bytes'] for x in acq['wrapper_file_reads'])==acq['wrapper_explicit_file_bytes']==230231
 producer=bytes.fromhex(files[B+'produce.py']['raw_hex']).decode('ascii')
 maintext=producer[producer.index('def main():'):]
 assert maintext.index('for label in (\'upstream_body_review\',\'source_peer_review\')')<maintext.index("base,pins=source_guard()")<maintext.index("save('claim.json'")<maintext.index("stream=(ROOT.parent/'eu4.exe').open('rb')")
 assert maintext.index("authenticate('after')")<maintext.index('_,postpins=source_guard()')<maintext.index('finally:')<maintext.index('stream.close()')<maintext.index("save('capture.json',value)")
 assert "open('x'" in producer and "sys.argv[1:]==[]" in producer
 # Resource tables are replayed as retained witnesses, not new PE/engine proof.
 delivery=obj('delivery-manifest.json');fc=obj('filecheck.json');sa=obj('seal-read-accounting.json')
 for name,expected in delivery['pins'].items():assert pn(B+name)==expected
 assert fc['source_manifest_pin']==pn(B+'manifest.json') and fc['passed'] is True
 assert sum(x['bytes'] for x in sa['seal_events'])==sa['seal_script_explicit_bytes']==745181
 assert sa['seal_script_explicit_bytes']+sa['prior_inspection_bytes']+sa['wrapper_explicit_bytes']==sa['retained_explicit_bytes_before_filecheck']==1188470
 assert sum(x['bytes'] for x in fc['file_read_events'])==fc['filecheck_explicit_bytes']==638857
 assert sa['retained_explicit_bytes_before_filecheck']+fc['filecheck_explicit_bytes']+sa['manual_console_preflight_source_read_allowance']==fc['retained_explicit_upper_before_delivery']==2077327
 assert sum(x['bytes'] for x in delivery['delivery_read_events'])==delivery['delivery_explicit_file_bytes']==193775
 assert fc['retained_explicit_upper_before_delivery']+delivery['delivery_explicit_file_bytes']==delivery['retained_explicit_upper_including_delivery_and_manual_allowance']==2271102
 assert c['source_file_read_bytes']+pn(B+'capture.json')['bytes']==17079777==delivery['producer_source_engine_IO_including_final_stdout_capture_pin']
 assert 17079777+2271102==delivery['combined_explicit_upper']==19350879
 assert delivery['actual_executions']==1 and delivery['actual_exit_code']==0 and delivery['failure_files']==[]
 assert delivery['all_owned_children_shells_collected'] is True
 for name in ('seal-execution.json','filecheck-actual-execution.json'):
  ex=obj(name);assert ex['exit_code']==0 and ex['owned_child_collected'] is True
 for flag in ('native_ready','callable','reader_adoption_allowed','selected_effect_verified','world_lease','atomic_snapshot','authorizes_retry'):assert c[flag] is False
 false_authority(contract['authority'])
 # Only known flat source files get a final independent hash. Engine38 stays
 # metadata-only, including its entries in capture/base/claim dictionaries.
 for path,e in files.items():read(path,{k:e[k] for k in ('bytes','sha256')})
 known_prior=cache['source_bytes']+cache['initial_schema_read_upper_bytes']+supp['source_bytes']+acc['source_bytes']
 prior_inspection_upper=4*CACHE_PIN['bytes']+SUPPLEMENT_PIN['bytes']+65536
 own_sealing_reserve=2*1024*1024
 current=sum(x['bytes'] for x in reads)
 analysis_upper=known_prior+prior_inspection_upper+current+own_sealing_reserve
 assert analysis_upper<LIMIT
 raw_review=dict(schema='EU4-R66-INDEPENDENT-RAW-REPLAY/1',passed=True,rows=replay,
  rows50_raw190_complete=True,syntax_CFG_rows_covered=50,edges=edges,terminals=c['analysis']['terminals'],
  explicit_store_sites=s['explicit_store_sites'],explicit_read_sites=s['explicit_read_sites'],
  implicit_stack_separate=True,LEA_not_dereference=True,
  pdata=dict(records=19,physical_bytes=228,unique_records=16,unique_bytes=192,selected=c['selected'],previous=c['previous'],next=c['next'],binary_search_replayed=True,cached_mapping_only=True),
  decoder=dict(author_lookahead_attempts=50,author_input_bytes=705,author_unique_bytes=190,author_overlap_bytes=515,new_decode_or_engine_access=0),
  first_call=dict(EAX_pre_call='0x1040',site='0x994f15',target='0x1a337f0',post_RAX_RCX_RDX_contract='unknown',post_RSP_SUB_uses='post-call RAX; not assumed0x1040'),
  dataflow=dict(byte_load='u8[post-callRDX] zeroextendsEBX; not fullDWORD or BOOL',begin_end='post-callRCX QWORD0/8',
   N='low64(SAR64(submod64(end,begin),2)*0xaaaaaaaaaaaaaaab); /12 only under suitable nonnegative exact12B-span premise',
   small='signedN<=32 includes negative malformed; RCXbegin/RDXend ->998d50; no explicit BL flag setup',
   large='signedN>32; CQO/SUB/SAR gives floorN/2 then N-floorN/2; 46a3b0(&local30,ceilN/2)',
   worker='998e10(begin,end,N,freshlocal30; arg5freshlocal38; arg6lowBYTE savedBL; upper7 uninitialized locally)',
   cleanup='freshlocal38 unsigned>0x155; freshlocal30 ->175da20; actual free/ownership unknown',
   return_paths={'small':'RAX from998d50 ifnormalreturn','large_skipcleanup':'RAX from998e10 ifnormalreturn','large_cleanup':'RAX from175da20 ifnormalreturn'},
   stack='steadyQ-8-postRAX undernormalfirstCALLstack; epiloguebalancesentryonlywhenpostRAX==0x1040; actualhomecontents stillcallee/aliasdependent'),
  arithmetic_verification='RawSAR2/low64IMUL and signedJG; CQO/SUB/SAR on positiveN provesceilN/2; unsignedJBE immediate341. No general memory validity, range or amount meaning inferred.',
  delivered_contract_consistent=True,all_external_callees_unfollowed=True,all_flat_source_postguard_equal=True)
 rp=write('raw-replay.json',raw_review)
 authority={k:False for k in contract['authority']}
 operations={k:0 for k in ('PE','engine','decoder','author_programs','tests','game_process','Frida','native_game_calls','requests','saves','extra_callee_follow')}
 findings=dict(schema='EU4-R66-INDEPENDENT-FINDINGS/1',sealed=True,passed=True,blocking_findings=[],
  subject_manifest=pn(B+'manifest.json'),subject_contract=pn(B+'contract.json'),subject_capture=pn(B+'capture.json'),
  author_frozen_source_needs_change=False,raw_replay=rp,
  checks=dict(actual_source_pins=41,additional_delivery_accounting_pins=len(files)-42,engine_metadata_witness_pins_unopened=38,
   full_rows=50,full_owned_bytes=190,CALL_sites=5,branch_sites=3,recorded_edges=8,RET_sites=1,INT3_sites=0,
   explicit_stores=5,syntactic_stack_stores=5,explicit_reads=10,all_raw_bytes_CFG_access_widths_replayed=True,
   three_review_gate_auth_claim_bound=True,source_current_postguard_equal=True,source_and_decoder_only_producer_witness=True),
  machine_contract=raw_review['dataflow'],
  precision_notes=[
   'The firstcallee is not followed. RAX/RCX/RDX are volatile under ordinary Win64ABI; MOV EAX1040 does not establish returnedRAX1040, current H/Treceiver or balanced frame.',
   'Five explicit memory stores are syntactically stack based. This is neither a purity proof nor unconditional assurance that malformed postcallee stack addresses cannot alias other memory; implicitPUSH/CALL/POP/RET accesses are separate.',
   'Only BYTE[postRDX] is consumed. EntryRDX DWORD address binding depends on firstcallee preservation; no amount, BOOL, units or originalTunchanged assumption.',
   'Nonvolatile ABI preserves saved register values under conforming normalcalls, not H/record/localtemp contents. Temporary30/38 is not initialized in thisbody before46a3b0; calleeoutwrite/ownership remainsunknown.',
   'Return provenance can be tightened conditionally: finalRAX is exactly the last normalreturn of998d50,998e10 or175da20 on its respective localpath; no uniform application value or completion follows.',
   'Complete local normal CFG is conditional on normal externalcall returns and valid stack/memory. No sort/conservation/currency/recipient/settlement/persistence/lease/readiness is established.',
   'Producer17,079,777 and retainedupper2,271,102 contain selected-source accounting/manual allowance, not allOS/interpreter/loader IO. PE76,925,426 is separately reported authorwitness.',
   'The acquisition duration580,747,200ns covers producerlaunch-to-collectedexit including source/engine/dualEXEhash; not a native runtime latency. Softwarepeak23,101,440B is authorwitness with no hardJob.'
  ],
  resource_witness=dict(producer_source_IO_including_capture_pin=17079777,retained_explicit_upper=2271102,combined_explicit_upper=19350879,
   PE_physical_bytes=76925426,pdata_physical_bytes=228,pdata_unique_bytes=192,code_unique_bytes=190,
   producer_elapsed_ns=acq['elapsed_ns'],producer_peak_committed_bytes=c['peak_committed_bytes_observed'],hard_Job_installed=False,
   scope='Retained producer/accounting witnesses only; no independent PE/engine/runtime access'),
  independent_resources=dict(known_prior_listed_bytes=known_prior,prior_inspection_upper_bytes=prior_inspection_upper,
   final_cache_and_postguard_bytes=current,own_sealing_reserve_bytes=own_sealing_reserve,
   listed_analysis_upper_bytes=analysis_upper,source_limit_bytes=LIMIT,own_peak_bytes=peak,memory_limit_bytes=MEMORY,
   source_budget_not_all_OS_or_loader_IO=True,recursive_closure=False),
  operations=operations,authority=authority,self_diagnostics=dict(review_failures=0,additional_file_names_resolved_before_read=True),
  all_shells_collected=True,next_scope_auto_authorized=False)
 fp=write('findings.json',findings)
 report=('R66 full independent retained-file review passed with no blocking discrepancy. '
  'All50 rows/190 bytes,8 CFG edges,5 calls,3 branches,5 syntactic stackstores and10 explicit reads agree. '
  'The firsthelper preservation/return/frame contract remains unknown; five stackstores do not establish purity. '
  'No record mutation, ordering, business unit, recipient, settlement, lifetime, readiness or permission is inferred. '
  'Only52 flat files were retained including delivery/accounting;38 engine witness files stayed unopened.\n').encode('ascii')
 with (OUT/'report.md').open('xb') as f:f.write(report)
 ownnames=('retained-files.json','retained-supplement.json','retained-accounting.json','raw-replay.json','findings.json','report.md')
 local={O+n:pin((OUT/n).read_bytes()) for n in ownnames}
 for path in ('work/retain_r66_review_20261016.py','work/review_r66_actual_20261016.py'):local[path]=pin((ROOT/path).read_bytes())
 mp=write('manifest.json',dict(schema='EU4-R66-INDEPENDENT-MANIFEST/1',sealed=True,source_pins={path:pn(path) for path in files},
  local_pins=local,source_count=len(files),source_scope='41actual authorpins + subjectmanifest +10 explicit finaldelivery/accounting files; no recursion',
  engine_witness_count_unopened=38,findings=fp,operations=operations,authority=authority))
 print(json.dumps(dict(passed=True,findings=fp,raw_replay=rp,manifest=mp,listed_analysis_upper_bytes=analysis_upper,peak=peak,all_shells_collected=True)))

def check():
 m=decode(read(O+'manifest.json'))
 for path,pn in (m['source_pins']|m['local_pins']).items():read(path,pn)
 f=decode(read(O+'findings.json',m['local_pins'][O+'findings.json']))
 upper=f['independent_resources']['listed_analysis_upper_bytes']+sum(x['bytes'] for x in reads)
 assert upper<LIMIT
 vp=write('verification.json',dict(schema='EU4-R66-INDEPENDENT-VERIFICATION/1',passed=True,
  checked_pins=len(m['source_pins']|m['local_pins']),all_flat_sources_equal=True,byte_verification_only=True,
  check_listed_bytes=sum(x['bytes'] for x in reads),conservative_full_review_upper_bytes=upper,source_limit_bytes=LIMIT,
  own_peak_bytes=peak,all_shells_collected=True,operations=m['operations'],authority=m['authority']))
 print(json.dumps(dict(passed=True,verification=vp,checked_pins=len(m['source_pins']|m['local_pins']),conservative_full_review_upper_bytes=upper,peak=peak)))

if __name__=='__main__':
 try:check() if sys.argv[1:]==['--check'] else main()
 except Exception as exc:
  name='verification-failure.json' if sys.argv[1:]==['--check'] else 'review-failure.json'
  if not (OUT/name).exists():write(name,dict(type=type(exc).__name__,detail=str(exc),reads=reads,peak=peak,author_sources_unchanged=True,no_PE_or_program_replay=True))
  raise
