"""R69 actual-result review; original source design is not claimed independent."""
from pathlib import Path
import hashlib,json,struct,ctypes,sys
from ctypes import wintypes
ROOT=Path(__file__).resolve().parents[1];B='work/reports/war-peace-api-20261016-r69-generator-divisor-source/';O='work/reports/war-peace-api-20261016-r69-actual-independent-review/';OUT=ROOT/O
LIMIT=24*1024*1024;MEMORY=768*1024*1024;peak=0;reads=[]
CACHE=dict(bytes=3832367,sha256='4ad79d31ee58332426a06bd3ef173db053668156af3d5bb5b795454cb3618c2c')
# Exact Win32 PROCESS_MEMORY_COUNTERS_EX layout; own process only.
class MemoryCounters(ctypes.Structure):
 _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t)for n in('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
k=ctypes.WinDLL('kernel32',use_last_error=True);p=ctypes.WinDLL('psapi',use_last_error=True);k.GetCurrentProcess.restype=wintypes.HANDLE;p.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(MemoryCounters),wintypes.DWORD]
def guard():
 global peak
 x=MemoryCounters();x.cb=ctypes.sizeof(x);assert p.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(x),x.cb);peak=max(peak,x.WorkingSetSize,x.PrivateUsage,x.PeakWorkingSetSize,x.PeakPagefileUsage);assert peak<=MEMORY
def pin(r):return dict(bytes=len(r),sha256=hashlib.sha256(r).hexdigest())
def pairs(items):
 d={}
 for k,v in items:assert k not in d;d[k]=v
 return d
def decode(r):return json.loads(r,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
def read(path,pn=None):
 assert 'eu4.exe'not in path.lower()and not path.startswith('work/deps/')
 guard();f=ROOT/path;a=f.stat();assert a.st_size<=4*1024*1024
 r=f.read_bytes();z=f.stat();assert len(r)==a.st_size and(a.st_size,a.st_mtime_ns)==(z.st_size,z.st_mtime_ns)
 actual=pin(r)
 if pn is not None:assert actual==pn,(path,actual,pn)
 reads.append(dict(path=path,**actual));guard();return r
def write(n,x):
 r=(json.dumps(x,indent=2,ensure_ascii=True)+'\n').encode('ascii');assert len(r)<4*1024*1024
 with(OUT/n).open('xb')as f:f.write(r)
 return pin(r)
def iv(n):return int(n,16)if isinstance(n,str)else n
def relative(path):
 s=str(path).replace('\\','/');prefix=ROOT.as_posix()+'/'
 return s[len(prefix):]if s.startswith(prefix)else s
SPEC='''
4055 push
56 push
4154 push
4155 push
4156 push
4883ec30 sub
33f6 xor
498be8 mov
8932 mov
4c8bf2 mov
4c8be9 mov
e8a187feff call
4c8be0 mov
4885c0 test
0f84bd000000 je
4d8b4578 mov
4d2b4570 sub
49c1f803 sar
'''
def main():
 cache=decode(read(O+'retained-files.json',CACHE));files=cache['files'];objects={}
 for path,e in files.items():
  rr=bytes.fromhex(e['raw_hex']);assert pin(rr)=={k:e[k]for k in('bytes','sha256')}
  if path.endswith('.json'):
   if not rr:assert path==B+'seal.stdout.json'
   else:objects[path]=decode(rr)
 def obj(n):return objects[B+n]
 def pn(path):return {k:files[path][k]for k in('bytes','sha256')}
 m=obj('manifest.json');c=obj('capture.json');o=obj('owned-code.json');s=obj('selected-evidence.json');contract=obj('contract.json');final=obj('actual-delivery-manifest.json')
 assert len(m['source_pins'])==45 and len(m['decoder_expected_witness_pins'])==38 and m['decoder_files_opened_in_retained_stage']is False
 for path,expected in m['source_pins'].items():assert pn(path)==expected
 for path,expected in final['source_pins'].items():assert pn(path)==expected
 raw=bytes.fromhex(o['raw_hex']);assert len(raw)==o['bytes']==55 and o['window']==['0x993570','0x9935a7']and o['full_extent_owned']is True
 assert hashlib.sha256(raw).hexdigest()==o['sha256']==s['raw_sha256']and bytes.fromhex(s['raw_hex'])==raw
 rows=c['analysis']['instructions'];assert rows==s['instructions']and len(rows)==18
 spec=[x.split()for x in SPEC.splitlines()if x.strip()];assert len(spec)==18
 cursor=0x993570;replay=[];rowmap={}
 for row,(hx,mn)in zip(rows,spec):
  at=iv(row['rva']);b=bytes.fromhex(hx);assert at==cursor and(row['bytes'],row['mnemonic'])==(hx,mn)
  assert raw[at-0x993570:at-0x993570+len(b)]==b
  mem=row['memory_operands'];writes=[q for q in mem if q['write']];loads=[q for q in mem if q['read']]
  if at==0x993582:
   assert len(writes)==1 and(writes[0]['base'],writes[0]['displacement'],writes[0]['width_bytes'])==('rdx',0,4)and not loads
  elif at in(0x99359b,0x99359f):
   assert not writes and len(loads)==1 and(loads[0]['base'],loads[0]['displacement'],loads[0]['width_bytes'])==('r13',0x78 if at==0x99359b else 0x70,8)
  else:assert not writes and not loads
  for q in mem:assert q['index']is None and q['rip_target_rva']is None and q['segment']is None
  replay.append(dict(rva=hex(at),raw_hex=hx,mnemonic=mn,raw_equal=True,explicit_reads=loads,explicit_stores=writes));rowmap[at]=row;cursor=at+len(b)
 assert cursor==0x9935a7 and b''.join(bytes.fromhex(x[0])for x in spec)==raw
 call=bytes.fromhex(rowmap[0x99358a]['bytes']);assert 0x99358a+5+int.from_bytes(call[1:],'little',signed=True)==0x97bd30
 je=bytes.fromhex(rowmap[0x993595]['bytes']);assert 0x993595+6+int.from_bytes(je[2:],'little',signed=True)==0x993658
 assert c['analysis']['edges']==s['edges']and len(s['edges'])==2
 assert c['analysis']['terminals']==s['terminals']==[dict(kind='external_or_indirect_branch',rva='0x993595',target='0x993658'),dict(kind='window_fallthrough',rva='0x9935a7')]
 assert c['analysis']['local_normal_CFG_closed']is False and s['whole_normal_function_CFG_closed']is False
 assert c['analysis']['undecoded_owned_intervals']==[]and all(r['mnemonic']not in('ret','retf')for r in rows)
 assert c['next']['begin_rva']=='0x9935a7'and c['next']['end_exclusive']=='0x993643'
 assert c['analysis']['lookahead_inputs']==s['lookahead_inputs']
 for q,row in zip(s['lookahead_inputs'],rows):assert iv(q['rva'])==iv(row['rva'])and q['bytes']==min(15,0x9935a7-iv(row['rva']))
 assert sum(q['bytes']for q in s['lookahead_inputs'])==249 and s['decoder_overlap_bytes']==194
 # Pdata/cachedsections arithmetic uses retained rawmetadata only.
 anchors=objects['work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json'];sections=anchors['sections'];pd=next(q for q in sections if q['name']=='.pdata')
 def offset(rva,n):
  match=[q for q in sections if iv(q['rva'])<=rva and rva+n<=iv(q['rva'])+q['raw_size']];assert len(match)==1
  q=match[0];return q['raw_file_offset']+rva-iv(q['rva'])
 requests=c['pdata_requests'];assert len(requests)==20
 lo,hi=0,pd['virtual_size']//12
 for q in requests:
  assert struct.unpack('<III',bytes.fromhex(q['raw_hex']))==tuple(iv(q[k])for k in('begin_rva','end_exclusive','unwind_rva'))
  assert iv(q['rva'])==iv(pd['rva'])+12*q['index']and q['file_offset']==offset(iv(q['rva']),12)
  if q['reason']=='binary_search':
   assert q['index']==(lo+hi)//2
   if iv(q['begin_rva'])<=0x993570:lo=q['index']+1
   else:hi=q['index']
 assert lo==hi==19161 and c['selected']['index']==19160 and c['selected']['raw_hex']=='70359900a7359900f8dce701'
 assert c['exact_pdata_begin']is True and c['pdata_physical_bytes']==240 and c['pdata_unique_bytes']==len({q['index']for q in requests})*12==204
 sparse=c['sparse_reads'];assert len(sparse)==21 and sum(q['bytes']for q in sparse)==295 and sparse[-1]['kind']=='single_entry_code'and sparse[-1]['bytes']==55
 assert sparse[-1]['file_offset']==o['file_offset']==offset(0x993570,55)
 assert c['total_PE_physical_bytes']==76925008+240+55==76925303
 assert sum(q['bytes_read']for q in c['full_PE_authentication_reads'])==76925008 and all(q['completed']is True and q['sha256']==c['game_sha256']for q in c['full_PE_authentication_reads'])
 # Actual root/third-party reviews, independent of original source authorship.
 auth=obj('run-authorization.json');acq=obj('acquisition-receipt.json');base=obj('source-manifest.json');claim=obj('claim.json');rootclaim=obj('root-invocation-claim.json')
 assert auth['source_manifest']==pn(B+'source-manifest.json')and auth['producer_pin']==pn(B+'produce.py')and auth['entry_seed_pin']==pn(B+'entry-seed.json')
 assert auth['root_explicit_start_received']is True and auth['single_attempt']is True and auth['authorizes_retry']is False
 assert c['source_manifest']==claim['source_manifest']==auth['source_manifest']and c['source_pins']==claim['source_pins']==base['source_pins']
 assert c['authorization_pin']==claim['authorization_pin']==rootclaim['authorization']==pn(B+'run-authorization.json')
 reviews={auth['seed_review_path']:auth['seed_review_pin']};q=auth['root_review_manifest'];reviews[q['path']]={k:q[k]for k in('bytes','sha256')}
 for group in('upstream_body_review','source_peer_review'):
  for q in auth[group].values():reviews[q['path']]={k:q[k]for k in('bytes','sha256')}
 for path,expected in reviews.items():assert pn(path)==expected
 for path in(auth['seed_review_path'],auth['upstream_body_review']['findings']['path'],auth['source_peer_review']['findings']['path']):
  q=objects[path];assert q['sealed']is True and q['passed']is True and q['blocking_findings']==[]
 peer=objects[auth['source_peer_review']['findings']['path']]
 assert peer['subject_source_manifest']==pn(B+'source-manifest.json')and peer['subject_producer']==pn(B+'produce.py')and peer['subject_entry_seed']==pn(B+'entry-seed.json')
 assert acq['review_pins']==rootclaim['review_pins']==reviews and acq['exit_code']==0 and acq['direct_owned_child_collected']is True and acq['failure_files']==[]
 assert acq['all_admission_pins_prepost_equal']is True and acq['stdout']==pn(B+'producer.stdout.json')and acq['stderr']==pn(B+'producer.stderr.txt')
 assert files[B+'producer.stderr.txt']['bytes']==0 and obj('producer.stdout.json')['capture_pin']==pn(B+'capture.json')
 assert c['decoder_expected_pins']==m['decoder_expected_witness_pins']==base['decoder_expected_witness_pins']and c['source_engine_before_after_equal']is True
 journal=c['source_file_reads'];assert sum(q['bytes']for q in journal)==c['source_file_read_bytes']==19579065
 for phase in('source_engine_before','source_engine_after'):
  q=[x for x in journal if x['phase']==phase and x['operation']=='streaming_engine_pin'];assert len(q)==38
  assert {relative(x['path']):x['bytes']for x in q}=={p:v['bytes']for p,v in m['decoder_expected_witness_pins'].items()}
 producer=bytes.fromhex(files[B+'produce.py']['raw_hex']).decode('ascii');maintext=producer[producer.index('def main():'):]
 assert maintext.index("for label in ('upstream_body_review','source_peer_review')")<maintext.index('base,pins=source_guard()')<maintext.index("save('claim.json'")<maintext.index("stream=(ROOT.parent/'eu4.exe').open('rb')")
 assert maintext.index("authenticate('after')")<maintext.index('_,postpins=source_guard()')<maintext.index('finally:')<maintext.index('stream.close()')<maintext.index("save('capture.json',value)")
 # Failed first retained seal is not a second actual. Compare preserved rawpins.
 fail=obj('retained-seal-failure-r1.json');delivery=obj('actual-delivery-receipt.json');fc=obj('filecheck.json')
 assert fail['producer_reexecuted']is False and fail['derived_count_is_not_instrumented_firstpass_IO']is True
 assert fail['first_completed_content_read_bytes_derived_from_reached_source_path_and_pins']==1808772
 assert fail['conservative_failed_seal_IO_allowance_bytes']==3145728>1808772
 assert fail['original_failed_sealer_pin']==pn(B+'seal_actual.py')
 for name,expected in fail['original_outputs_and_existing_report_pins'].items():assert pn(B+name)==expected
 r2=bytes.fromhex(files[B+'seal_actual_r2.py']['raw_hex']).decode('ascii')
 assert "assert read(HERE/name)==payload"in r2 and "name in('selected-evidence.json','contract.json')"in r2 and 'actual-report.md'in r2
 assert 'FileExistsError'in bytes.fromhex(files[B+'seal.stderr.txt']['raw_hex']).decode('ascii')and files[B+'seal-r2.stderr.txt']['bytes']==0
 assert final['actual_executions']==1 and final['retained_seal_executions']==2 and delivery['actual_not_reexecuted']is True
 assert delivery['producer_exit_code']==0 and delivery['first_retained_seal_exit_code']==1 and delivery['second_independent_retained_seal_exit_code']==delivery['filecheck_exit_code']==0
 assert delivery['old_preparation_report_not_modified']is True and delivery['actual_report_filename']=='actual-report.md'
 for name,expected in delivery['outputs'].items():assert pn(B+name)==expected
 assert fc['subject_manifest']==pn(B+'manifest.json')and fc['passed']is True and fc['normal_RET_count']==0
 assert sum(q['bytes']for q in m['retained_seal_read_events'])==m['retained_seal_returned_bytes']==2015035
 assert sum(q['bytes']for q in fc['read_events'])==fc['returned_bytes']==1981873
 later=sum(q['bytes']for q in delivery['final_delivery_read_events'])
 assert 2015035+1981873+1048576+3145728+later+65536==delivery['retained_stage_explicit_upper_bytes']==8493434
 assert 19579065+pn(B+'capture.json')['bytes']==19661300==delivery['producer_source_returned_bytes_including_postcapture_pin']
 assert 19661300+8493434==delivery['combined_producer_retained_stage_explicit_upper_bytes']==28154734
 assert delivery['direct_owned_child_and_all_shells_collected']is True and all(x is False for x in contract['authority'].values())
 for path,e in files.items():read(path,{k:e[k]for k in('bytes','sha256')})
 # R1 read this cache once before rejecting a pinned empty sealer log. Small
 # direct metadata/source inspection is covered by256KiB. Own sealing hashes
 # include one3.83MiBcache reread and small outputs, hence4MiB explicit reserve.
 upper=cache['source_bytes']+cache['prior_initial_inspection_bytes']+256*1024+CACHE['bytes']+sum(x['bytes']for x in reads)+4*1024*1024;assert upper<LIMIT
 model=dict(pre_CALL='FivePUSH+SUB30hex =>S-58hex; XOR ESI clearsfullRSI; RBP=entryR8; DWORD[entryRDX]=0; R14=entryRDX; R13=entryRCX. RCX/RDX/R8forwardedunchangedto97bd30.',
  zero_write='Exactly4bytesbeforeexternalCALL; neither finalDnorRAXreturn norpositive/nonzero result.',
  CALL='99358a->97bd30 bodyunfollowed. Normalreturn/volatile/nonvolatile/alias/outwrite/borrowretention unknown; conditionalordinaryABIR13preservation isnot recoveredbodyfact.',
  null_branch='postCALLRAX copiedtoR12; TEST64; RAX0 JE993658outsideowned andbeyondnextmetadataend993643.',
  nonnull='freshQWORD[postCALLR13+78] minusfreshQWORD[postCALLR13+70]mod64; SAR64R8,3 thenfallthrough9935a7outsideowned. No element/count/type/unit semantics.',
  header='entryR8pointer savedRBP/forwardedR8 only; noheaderdereference in55B. Its output andcomplete layout remainunknown.',
  frame='ConditionalR62 Q62: S=Q62-90hex; out=Q62+20=S+b0; header=Q62-50=S+40; precallRSP=S-58, calleeentryS-60. No epilogue/normalreturn owned.',
  flags='Pre97bd30XOR ESI definesarithmeticflags/DFunknown; externalcallunknown; TEST64selectsbranch; lastSAR3changesflags. No finalflags/RETcontract.')
 rp=write('raw-replay.json',dict(schema='EU4-R69-INDEPENDENT-ACTUAL-RAW/1',passed=True,rows=replay,owned_bytes=55,rows_count=18,
  edges=s['edges'],terminals=s['terminals'],explicit_stores=1,store_width=4,explicit_reads=2,read_widths=[8,8],implicit_pushes=5,implicit_CALL_stores=1,
  RET_count=0,local_normal_CFG_closed=False,exact_pdata_complete_not_whole_function=True,selected=c['selected'],next_metadata=c['next'],
  metadata=dict(requests=20,physical_bytes=240,unique_bytes=204),decoder_witness=dict(input_bytes=249,unique_bytes=55,overlap_bytes=194,new_decode=0),machine_model=model,
  first_failed_seal_partialpins_exact=True,R2bytecompare_reuses_partial=True,all_sources_current_postguard_equal=True))
 ops={k:0 for k in('PE_stat_open','engine_stat_open','decoder','author_producer_driver_sealer','tests','game_process','Frida','native_game_calls','requests','callee_or_continuation_follow','R71_scope')}
 authority={k:False for k in contract['authority']}
 fp=write('findings.json',dict(schema='EU4-R69-ACTUAL-RESULT-REVIEW/1',sealed=True,passed=True,blocking_findings=[],
  subject_manifest=pn(B+'manifest.json'),subject_contract=pn(B+'contract.json'),subject_capture=pn(B+'capture.json'),raw_replay=rp,
  reviewer_role=dict(original_source_preparer=True,actual_and_retained_package_author='validation_audit',independent_source_peer='diplomacy_static',
   independent_source_peer_pin=auth['source_peer_review']['findings'],scope='Currentselectedactualraw/metadata/retainedpackage review; notindependentredesignorengineauthentication'),
  author_frozen_source_needs_change=False,checks=dict(actual_file_pins=45,additional_finalpins=len(files)-46,engine_witness_metadata_only=38,
   rows=18,bytes=55,RET_count=0,external_JE='0x993658',window_fallthrough='0x9935a7',local_CFG_closed=False,
   raw_widths_metadata_and_three_gate_bindings_equal=True,normalclose_afterguards_beforecapture=True,R1failure_preserved_R2noactualretry=True,source_current_postguard_equal=True),
  machine_contract=model,precision_notes=[
   'Fullselectedpdata ownership55B is not wholefunction or returnclosure. Both localexits leaveownedbytes; no continuation or97bd30body was read.',
   'DWORDout0 occursbeforeCALL. Externalcall/aliases/continuations may change it; finalD, Dpositive/nonzero, headeroutput andRAXapplicationreturn remainunknown.',
   'R13 capturesentryRCX at993587. postCALLR13 accesses are concrete, but originalWidentity after97bd30 requires a separatecalleecontract or explicitordinarynormalABIpremise; pointeecontents never follow from registeridentity.',
   'The reviewer preparedoriginalsource; D fullsourcepeer0ea57356/c1420c3d remains the independent source gate. Thisphase audits Valsactual/retainedrawoutput, not an independentlyredesignedproducer or newlyauthenticatedengine.',
   'R1sealer failed exclusively at preexistingreport.md. Originalsource/log/report andpartialcontract/selected pins are retained; R2comparesexactbytes before reuse and writesactual-report.md. Oneactual only.',
   'Firstfailedseal1,808,772B is path-and-pinderived, not an instrumentedfirstpassledger. Conservative3MiBallowance remains inretainedupper; no allOS/loaderIO claim.',
   '498,531,000ns and22,675,456B are producerwitnesses, not native latency or treewidepeak. PE/engine identifications remain retainedwitness; allpermissions/effects/leasefalse.'
  ],resource_witness=dict(source_journal_at_capture=19579065,final_capture_pin_read_bytes=82235,producer_source_total=19661300,
   retained_explicit_upper=8493434,combined_explicit_upper=28154734,first_failed_seal_derived_not_instrumented=1808772,failed_seal_allowance=3145728,
   PE_separate_bytes=76925303,producer_elapsed_ns=acq['elapsed_ns'],producer_peak_bytes=c['peak_committed_bytes_observed'],hard_Job_installed=False),
  independent_resources=dict(retained_intake_bytes=cache['source_bytes'],initial_schema_bytes=cache['prior_initial_inspection_bytes'],smallinspection_allowance=256*1024,prior_failed_cache_read_bytes=CACHE['bytes'],
   final_cache_and_sourcepostguard_bytes=sum(x['bytes']for x in reads),own_sealing_reserve=4*1024*1024,listed_analysis_upper_bytes=upper,source_limit_bytes=LIMIT,
   own_peak_bytes=peak,memory_limit_bytes=MEMORY,no_all_OS_loader_IO_claim=True,recursive_closure=False),
  operations=ops,authority=authority,self_diagnostics=dict(review_failures=1,reason='R1 attempted to parse the exact pinned empty failed-sealer stdout log as JSON. R2 exempts only that known empty log; all actual JSON remains strict. R1 source and failure are preserved; author sources and actual capture unchanged.'),all_shells_collected=True,next_scope_auto_authorized=False))
 report=('R69 actual-result raw/retained review passed. 18rows55B exactly matchselectedpdata, but JE993658 andfallthrough9935a7 leaveownedrange; noRET/localclosure. '
  'PreCALLDWORDout0 is notfinalD. PostcalleeR13/content/header andnormalreturn remainunknown. '
  'Revieweroriginalsourceauthorship isdisclosed; Dindependent sourcepeer andValsactual package remain separate. NoPE/engine/producer/game/native execution.\n').encode('ascii')
 with(OUT/'report.md').open('xb')as f:f.write(report)
 local={O+n:pin((OUT/n).read_bytes())for n in('retained-files.json','raw-replay.json','findings.json','report.md','review-failure.json','reviewer-r1-preimage.py','reviewer-r1-preimage.json')}
 for path in('work/retain_r69_actual_review_20261016.py','work/review_r69_actual_20261016.py'):local[path]=pin((ROOT/path).read_bytes())
 mp=write('manifest.json',dict(schema='EU4-R69-ACTUAL-REVIEW-MANIFEST/1',sealed=True,source_pins={path:pn(path)for path in files},local_pins=local,
  source_scope='45actual+rootmanifest+7finaldelivery/checkfiles;53explicitflatfiles, noengineclosure',findings=fp,operations=ops,authority=authority))
 print(json.dumps(dict(passed=True,findings=fp,raw_replay=rp,manifest=mp,listed_analysis_upper_bytes=upper,peak=peak,all_shells_collected=True)))
def check():
 m=decode(read(O+'manifest.json'))
 for path,pn in(m['source_pins']|m['local_pins']).items():read(path,pn)
 f=decode(read(O+'findings.json',m['local_pins'][O+'findings.json']))
 upper=f['independent_resources']['listed_analysis_upper_bytes']+sum(x['bytes']for x in reads);assert upper<LIMIT
 vp=write('verification.json',dict(schema='EU4-R69-ACTUAL-REVIEW-VERIFICATION/1',passed=True,checked_pins=len(m['source_pins']|m['local_pins']),
  all_flat_sources_current_equal=True,byte_verification_only=True,conservative_complete_stage_upper_bytes=upper,source_limit_bytes=LIMIT,
  own_peak_bytes=peak,operations=m['operations'],authority=m['authority'],all_shells_collected=True))
 print(json.dumps(dict(passed=True,verification=vp,checked_pins=len(m['source_pins']|m['local_pins']),conservative_complete_stage_upper_bytes=upper,peak=peak)))
if __name__=='__main__':
 try:check()if sys.argv[1:]==['--check']else main()
 except Exception as exc:
  n='verification-failure.json'if sys.argv[1:]==['--check']else'review-r2-failure.json'
  if not(OUT/n).exists():write(n,dict(type=type(exc).__name__,detail=str(exc),reads=reads,peak=peak,author_sources_unchanged=True,no_PE_engine_or_author_program_execution=True))
  raise
