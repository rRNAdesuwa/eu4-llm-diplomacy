"""R68 retained-only conditional frame review; raw slices/arithmetic, no decoder."""
from pathlib import Path
import hashlib,json,ctypes,sys
from ctypes import wintypes
ROOT=Path(__file__).resolve().parents[1];B='work/reports/war-peace-api-20261016-r68-fixed-frame-projection/';O='work/reports/war-peace-api-20261016-r68-independent-review/';OUT=ROOT/O
LIMIT=24*1024*1024;MEMORY=768*1024*1024;peak=0;reads=[]
CACHE=dict(bytes=1128905,sha256='dc612d08781b29621cc5868b6791cec45da12a3c2421becd4b7ed6e957aa2dfe')
class PMC(ctypes.Structure):
 _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t)for n in('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
k=ctypes.WinDLL('kernel32',use_last_error=True);p=ctypes.WinDLL('psapi',use_last_error=True);k.GetCurrentProcess.restype=wintypes.HANDLE;p.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(PMC),wintypes.DWORD]
def guard():
 global peak
 x=PMC();x.cb=ctypes.sizeof(x);assert p.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(x),x.cb);peak=max(peak,x.WorkingSetSize,x.PrivateUsage,x.PeakWorkingSetSize,x.PeakPagefileUsage);assert peak<=MEMORY
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
def rel(row):
 b=bytes.fromhex(row['bytes']);n=1 if b[0]in range(0x70,0x80)or b[0]==0xeb else 2 if b[:1]==b'\x0f'else 1
 return iv(row['rva'])+len(b)+int.from_bytes(b[n:],'little',signed=True)
def main():
 cache=decode(read(O+'retained-files.json',CACHE));files=cache['files'];objects={}
 for path,e in files.items():
  raw=bytes.fromhex(e['raw_hex']);assert pin(raw)=={k:e[k]for k in('bytes','sha256')}
  if path.endswith('.json'):objects[path]=decode(raw)
 def obj(n):return objects[B+n]
 def pn(path):return {k:files[path][k]for k in('bytes','sha256')}
 m=obj('manifest.json');proj=obj('projection.json');rc=obj('raw-crosscheck.json');final=obj('final-manifest.json')
 assert len(m['source_pins'])==20 and len(m['local_pins'])==12 and m['recursive_closure']is False
 assert m['source_pins']==obj('source-pins.json')['pins']
 assert obj('source-pins.json')['recursive_closure']is False and obj('source-pins.json')['source_prepost_equal']is True
 for path,expected in(m['source_pins']|m['local_pins']).items():assert pn(path)==expected
 for path,expected in final['pins'].items():assert pn(path)==expected
 assert all(x is False for x in proj['authority'].values())and all(x==0 for x in proj['operations'].values())
 assert final['authority']==m['authority']==proj['authority']and final['operations']==m['operations']==proj['operations']
 groups=rc['all_owned_row_byte_comparisons'];assert len(groups)==3
 rowmaps={};rawreplay=[];totalrows=totalbytes=0
 for g in groups:
  selected=objects[g['source']];owned=objects[g['owned']];raw=bytes.fromhex(owned['raw_hex']);start=iv(owned['window'][0]);end=iv(owned['window'][1])
  rows=selected['instructions'];assert len(rows)==g['rows']and len(raw)==g['retained_bytes']==end-start
  assert hashlib.sha256(raw).hexdigest()==g['raw_sha256']==owned['sha256']and owned['window']==g['window']
  cursor=start;entries=[]
  for row in rows:
   at=iv(row['rva']);b=bytes.fromhex(row['bytes']);assert at==cursor and raw[at-start:at-start+len(b)]==b
   entries.append(dict(rva=row['rva'],bytes=row['bytes'],raw_slice_equal=True));cursor+=len(b)
  assert cursor==end
  rowmaps[g['source']]={iv(r['rva']):r for r in rows};rawreplay.append(dict(source=g['source'],owned=g['owned'],rows=len(rows),bytes=len(raw),entries=entries))
  totalrows+=len(rows);totalbytes+=len(raw)
 assert totalrows==243 and totalbytes==952
 merged={at:r for d in rowmaps.values()for at,r in d.items()}
 for row in rc['selected_projection_rows']:
  actual=rowmaps[row['source']][iv(row['rva'])]
  assert all(row[k]==actual[k]for k in('rva','bytes','mnemonic','operands'))
 for rr in rc['relative_operand_arithmetic']:
  row=merged[iv(rr['site'])];assert row['bytes']==rr['raw_hex']and rel(row)==iv(rr['target'])
  assert rel(row)-(iv(row['rva'])+len(bytes.fromhex(row['bytes'])))==rr['signed_displacement']
  assert rr['target_body_followed_this_task']is False
 # Conditional symbolic frame follows concrete savedpush/MOV/SUB/LEA bytes.
 R62=rowmaps['work/reports/war-peace-api-20261016-r62-gold-recipient-generator/selected-evidence.json']
 R66=rowmaps['work/reports/war-peace-api-20261016-r66-generated-record-postprocess/selected-native.json']
 R67=rowmaps['work/reports/war-peace-api-20261016-r67-entry-helper-register-contract/selected-evidence.json']
 pushaddresses=[0x9844da,0x9844db,0x9844dc,0x9844dd,0x9844df,0x9844e1,0x9844e3]
 assert [R62[x]['bytes']for x in pushaddresses]==['55','56','57','4154','4155','4156','4157']
 assert R62[0x9844e5]['bytes']=='4883ec50'and R62[0x9844e9]['bytes']=='4c8bf2'
 assert R62[0x9846ca]['bytes']=='488d9424a0000000'and R62[0x9846d2]['bytes']=='498bce'and R62[0x9846d5]['bytes']=='e826080100'
 assert R66[0x994f0f]['bytes']=='57'and R66[0x994f10]['bytes']=='b840100000'and R66[0x994f1a]['bytes']=='482be0'
 assert R67[0x1a337f0]['bytes']=='4883ec10'and R67[0x1a33839]['bytes']=='4883c410'and R67[0x1a3383d]['bytes']=='c3'
 imm=int.from_bytes(bytes.fromhex(R66[0x994f10]['bytes'])[1:],'little');assert imm==0x1040
 prehelper=-8;S=prehelper-8;F=prehelper-imm;F62=-8*len(pushaddresses)-0x50;Q_from_Q62=F62-8
 expected={
  'R66_entry_return_QWORD':0,'saved_RBX':8,'saved_RBP':16,'saved_RSI':24,'saved_RDI':-8,
  'helper_entry_S_and_return_QWORD':S,'helper_saved_R10':S-16,'helper_saved_R11':S-8,'post_helper_RSP':prehelper,
  'steady_F':F,'local30':F+0x30,'local38':F+0x38,'worker_arg5_QWORD':F+0x20,'worker_arg6_low_BYTE':F+0x28,
  'worker_entry_RSP':F-8,'epilogue_R11':F+0x1040,'after_R66_normal_RET_RSP':8,
  'R62_current_T_borrowed_address':F62+0xa0-Q_from_Q62}
 assert expected==rc['symbolic_integer_offsets']
 assert {x['name']:x['offset_from_Q']for x in proj['address_table']}==expected
 for x in proj['address_table']:
  value=x['offset_from_Q'];formatted='Q'+('-0x'+format(-value,'x')if value<0 else'+0x'+format(value,'x'));assert x['address']==formatted
 assert rc['R62_to_R66']==dict(F62_minus_Q62=F62,Q_minus_Q62=Q_from_Q62,F_minus_Q62=Q_from_Q62+F)
 assert(F62,Q_from_Q62,F,S)==(-0x88,-0x90,-0x1048,-0x10)
 # R67candidate(S+8)-N is F on nonborrow path, not a proof that GS writes are safe.
 assert S+8-imm==F
 assert R67[0x1a33800]['bytes']=='4c8d542418'and R67[0x1a33805]['bytes']=='4c2bd0'and R67[0x1a33808]['bytes']=='4d0f42d3'
 assert R67[0x1a3380c]['bytes']=='654c8b1c2510000000'and R67[0x1a3381a]['bytes']=='664181e200f0'and R67[0x1a33827]['bytes']=='41c60300'
 # Machine argument locations use Win64 CALL returnslot displacement; semantic
 # signature and upper7bytes of arg6 remain deliberately unknown.
 for at,hx in {0x994f6e:'885c2428',0x994f72:'488b442438',0x994f77:'4889442420',0x994f7c:'4c8b4c2430',0x994f81:'4c8bc7',0x994f84:'488bd5',0x994f87:'488bce',0x994f8a:'e8813e0000',0x994fa5:'4c8d9c2440100000',0x994fad:'498b5b10',0x994fb1:'498b6b18',0x994fb5:'498b7320',0x994fb9:'498be3',0x994fbc:'5f',0x994fbd:'c3'}.items():assert R66[at]['bytes']==hx
 assert F+0x20==(F-8)+0x28 and F+0x28==(F-8)+0x30
 assert(F+0x1040+0x10,F+0x1040+0x18,F+0x1040+0x20)==(8,16,24)
 assert F+0x1040==-8 and Q_from_Q62+8==F62
 assert proj['machine_argument_locations'][4]['at_worker_entry']=='QWORD[RSP+0x28]'and proj['machine_argument_locations'][5]['at_worker_entry']=='BYTE[RSP+0x30]'
 # Local CFG walk reuses retained mnemonicannotations and rawrel arithmetic;
 # no instruction decode or externalcallee follow. Selected bypass is local.
 def reachable_from(start):
  seen=set();todo=[start]
  while todo:
   at=todo.pop()
   if at in seen:continue
   assert at in R62;seen.add(at);row=R62[at];mn=row['mnemonic'];nextat=at+len(bytes.fromhex(row['bytes']))
   if mn in('ret','int3'):continue
   if mn=='jmp':todo.append(rel(row))
   elif mn.startswith('j'):todo.extend([nextat,rel(row)])
   else:todo.append(nextat)
  return seen
 simple=reachable_from(0x98472d);dnonpositive=reachable_from(0x9846e4)
 assert 0x9846d5 not in simple|dnonpositive
 assert R62[0x984513]['bytes']=='0f8414020000'and rel(R62[0x984513])==0x98472d
 assert R62[0x98455b]['bytes']=='0f8e83010000'and rel(R62[0x98455b])==0x9846e4
 for label,ref in proj['upstream_full_reviews_passed'].items():
  assert pn(ref['path'])=={k:ref[k]for k in('bytes','sha256')};v=objects[ref['path']]
  assert v['sealed']is True and v['passed']is True and v['blocking_findings']==[]
  prefix={'R62':'work/reports/war-peace-api-20261016-r62-gold-recipient-generator/','R66':'work/reports/war-peace-api-20261016-r66-generated-record-postprocess/','R67':'work/reports/war-peace-api-20261016-r67-entry-helper-register-contract/'}[label]
  assert v['subject_manifest']==pn(prefix+'manifest.json')
  if 'subject_contract'in v:assert v['subject_contract']==pn(prefix+'contract.json')
  assert all(x is False for x in v['authority'].values())
 assert len(proj['hypotheses'])==5 and proj['historical_sources_modified']is False and proj['new_scope_auto_authorized']is False
 assert 'fresh' in proj['GS_alias'] or 'alias' in proj['GS_alias']
 # Listed source/retained account arithmetic is witness-only; no old script run.
 ac=obj('read-accounting.json');ver=obj('verification.json');delivery=obj('delivery.json')
 assert sum(x['bytes']for x in ac['events'])==ac['source_returned_bytes']==931664
 assert ac['source_returned_bytes']+ac['manual_prior_allowance']==ac['combined_source_upper']==5125968
 assert sum(x['bytes']for x in m['sealing_read_events'])==m['sealing_read_bytes']==533056
 assert sum(x['bytes']for x in ver['check_read_events'])==ver['check_read_bytes']==545265
 assert m['sealing_read_bytes']+ver['check_read_bytes']==delivery['seal_and_check_bytes']==1078321
 assert delivery['seal_and_check_bytes']+delivery['delivery_pin_read_bytes']==delivery['combined_seal_check_delivery_bytes']==1155756
 for name,expectedpin in delivery['artifact_pins'].items():assert pn(B+name)==expectedpin
 for name in('build-tool-result.json','check-tool-result.json'):
  v=obj(name);assert v['exit_code']==0 and v['direct_shell_collected']is True
 assert delivery['all_shells_collected']is True and delivery['no_further_scope_auto_authorized']is True
 for path,e in files.items():read(path,{k:e[k]for k in('bytes','sha256')})
 knownprior=cache['source_bytes']+cache['prior_initial_inspection_bytes'];inspection_upper=3*CACHE['bytes']+65536;sealreserve=2*1024*1024
 upper=knownprior+inspection_upper+sum(x['bytes']for x in reads)+sealreserve;assert upper<LIMIT
 rp=write('raw-projection-replay.json',dict(schema='EU4-R68-INDEPENDENT-RAW-PROJECTION/1',passed=True,
  group_raw_slice_comparisons=rawreplay,total_rows=243,total_retained_bytes=952,selected_projection_rows=len(rc['selected_projection_rows']),
  relative_operand_count=len(rc['relative_operand_arithmetic']),raw_relative_operands_verified=True,
  independently_derived_offsets=expected,R62_to_R66=rc['R62_to_R66'],
  local_bypass=dict(simple_path_selected_start='0x98472d',D_nonpositive_start='0x9846e4',postprocess_CALL_not_reached=True),
  all_three_full_review_subjects_bound=True,no_new_decode_or_callee_follow=True,all_sources_pre_post_equal=True))
 ops={k:0 for k in proj['operations']};authority={k:False for k in proj['authority']}
 fp=write('findings.json',dict(schema='EU4-R68-INDEPENDENT-PROJECTION-FINDINGS/1',sealed=True,passed=True,blocking_findings=[],
  subject_manifest=pn(B+'manifest.json'),subject_projection=pn(B+'projection.json'),subject_raw_crosscheck=pn(B+'raw-crosscheck.json'),subject_final_manifest=pn(B+'final-manifest.json'),
  author_frozen_source_needs_change=False,raw_projection_replay=rp,
  checks=dict(flat_upstream_sources=20,author_local_pins=12,explicit_final_delivery_additions=5,retained_instruction_rows=243,retained_code_bytes=952,
   all_raw_slices_equal=True,symbolic_offset_fields=18,relative_operands=14,three_upstream_fullreview_subjects_exact=True,source_postguard_equal=True),
  conditional_result=dict(F='Q-0x1048',S='Q-0x10',local30='Q-0x1018',local38='Q-0x1010',arg5='Q-0x1028',arg6_lowBYTE='Q-0x1020',
   home_reads=['Q+0x8','Q+0x10','Q+0x18'],R62_Q_to_R66_Q='Q=Q62-0x90',T_borrowed_address='Q+0xa8',
   actual_GS_bound_or_memory_contents_or_lifetime_proved=False),
  precision_notes=[
   'Address identities are conditional modulo64 arithmetic; validnormalstack/returnslots and relevantnonwrap/canonicalmappings remain separate hypotheses.',
   'R67 concrete normalregisterpreservation permits the fixed1040subtraction. Its GSderivedwrites do not prove H/T, savedhomes/helperqwords orreturnslots unchanged.',
   'R62T is currentborrowedaddressQ62+18hex=Q+a8hex, not unchangedpositivevalue. It differs from the Dout-shapedA8cell used by R69sourceprep; that later scope was not read or audited here.',
   'Machine fifthQWORD and sixthlowBYTE locations are demonstrated; six fullQWORDformalarguments, sixthupper7bytes, ownership and worker semantics are not recovered.',
   'SimpleAL0 and D<=0 paths bypass994f00 only in the selected localnormalCFG. Unfollowed externalcalls may have unknown effects/reentry; no transitivebypass guarantee.',
   'Othercallees still require normalreturn/balancedstack/nonvolatilepremises; preservedregisteridentities never imply pointeecontents oratomicity.',
   'Sourceupper5125968 includes4MiBpriorallowance; seal/check/delivery1155756 is separate. These retainedwitnesses are not allOS/loaderIO or newlyexecutedproducer evidence.'
  ],resource_witness=dict(source_upper_bytes=5125968,separate_seal_check_delivery_bytes=1155756,combined_explicit_upper_bytes=6281724,
   author_peak_committed_bytes=ac['self_committed_peak'],hard_Job_installed=False,scope='Retained author arithmetic/budget witnesses only'),
  independent_resources=dict(known_prior_bytes=knownprior,prior_cache_inspection_upper_bytes=inspection_upper,final_cache_and_postguard_bytes=sum(x['bytes']for x in reads),
   own_sealing_reserve_bytes=sealreserve,listed_analysis_upper_bytes=upper,source_limit_bytes=LIMIT,own_peak_bytes=peak,memory_limit_bytes=MEMORY,no_all_OS_loader_IO_claim=True),
  operations=ops,authority=authority,self_diagnostics=dict(review_failures=2,
   first_reviewer_error='R1 assumedsource-pins.json baremapping; actualschema haspinswrapper. ExactR1source/failurepreserved; R2onlyschemapointer/accountingadaptation.',
   second_reviewer_error='R2 selectedpaths by/r62- instead of exactfrozennamespace. ExactR2source/failurepreserved; R3usesexplicitthreefixedsourcekeys and accountingupdate only.',
   authored_sources_unchanged=True,PE_decoder_producer_rerun=False),all_shells_collected=True,next_scope_auto_authorized=False))
 report=('R68 retained-only independent review passed. 243rows/952retainedbytes,14relativeoperands and18symbolicoffsets agree. '
  'FixednormalR67contract establishes the conditionalR66frame F=Q-1048hex; R62mappingQ=Q62-90hex andT=Q+a8hex is consistent. '
  'FreshH/T, GS/data/returnslot aliases, allothercallee effects, runtime/safeexecution/lease and businessmeaning remainunknown.\n').encode('ascii')
 with(OUT/'report.md').open('xb')as f:f.write(report)
 local={O+n:pin((OUT/n).read_bytes())for n in('retained-files.json','raw-projection-replay.json','findings.json','report.md','review-failure.json','reviewer-r1-preimage.py','reviewer-r1-preimage.json','review-r2-failure.json','reviewer-r2-preimage.py','reviewer-r2-preimage.json')}
 for path in('work/retain_r68_review_20261016.py','work/review_r68_projection_20261016.py'):local[path]=pin((ROOT/path).read_bytes())
 mp=write('manifest.json',dict(schema='EU4-R68-INDEPENDENT-REVIEW-MANIFEST/1',sealed=True,source_pins={path:pn(path)for path in files},local_pins=local,
  source_scope='20flatupstream+12authorlocal+authorrootmanifest+4finalmetadata files;37explicit files, norecursion',findings=fp,operations=ops,authority=authority))
 print(json.dumps(dict(passed=True,findings=fp,raw_replay=rp,manifest=mp,listed_analysis_upper_bytes=upper,peak=peak,all_shells_collected=True)))
def check():
 m=decode(read(O+'manifest.json'))
 for path,pn in(m['source_pins']|m['local_pins']).items():read(path,pn)
 f=decode(read(O+'findings.json',m['local_pins'][O+'findings.json']))
 upper=f['independent_resources']['listed_analysis_upper_bytes']+sum(x['bytes']for x in reads);assert upper<LIMIT
 vp=write('verification.json',dict(schema='EU4-R68-INDEPENDENT-VERIFICATION/1',passed=True,checked_pins=len(m['source_pins']|m['local_pins']),all_flat_sources_current_equal=True,
  byte_verification_only=True,conservative_complete_stage_upper_bytes=upper,source_limit_bytes=LIMIT,own_peak_bytes=peak,operations=m['operations'],authority=m['authority'],all_shells_collected=True))
 print(json.dumps(dict(passed=True,verification=vp,checked_pins=len(m['source_pins']|m['local_pins']),conservative_complete_stage_upper_bytes=upper,peak=peak)))
if __name__=='__main__':
 try:check()if sys.argv[1:]==['--check']else main()
 except Exception as exc:
  n='verification-failure.json'if sys.argv[1:]==['--check']else'review-r3-failure.json'
  if not(OUT/n).exists():write(n,dict(type=type(exc).__name__,detail=str(exc),reads=reads,peak=peak,author_sources_unchanged=True,no_PE_or_decoder_or_author_program=True))
  raise
