"""R67 full retained-only review with fixed manual opcode facts; no decoder."""
from pathlib import Path
import hashlib,json,struct,ctypes,sys
from ctypes import wintypes
ROOT=Path(__file__).resolve().parents[1]
B='work/reports/war-peace-api-20261016-r67-entry-helper-register-contract/'
O='work/reports/war-peace-api-20261016-r67-actual-independent-review/'
OUT=ROOT/O;LIMIT=24*1024*1024;MEMORY=768*1024*1024;peak=0;reads=[]
CACHE=dict(bytes=1024275,sha256='e0f6efe069214afd7b2675940564e94837396d822fc4d9bc63dfe4e0d152da1e')
SUPP=dict(bytes=13565,sha256='608b233c2b6459d96293d3c991f58027a62317d4bcb9a4cdb9a2d7901c1225b6')
GAME='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
class PMC(ctypes.Structure):
 _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t)for n in('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
k=ctypes.WinDLL('kernel32',use_last_error=True);p=ctypes.WinDLL('psapi',use_last_error=True);k.GetCurrentProcess.restype=wintypes.HANDLE;p.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(PMC),wintypes.DWORD]
def guard():
 global peak
 x=PMC();x.cb=ctypes.sizeof(x);assert p.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(x),x.cb);peak=max(peak,x.WorkingSetSize,x.PrivateUsage,x.PeakWorkingSetSize,x.PeakPagefileUsage);assert peak<=MEMORY
def pin(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def pairs(items):
 d={}
 for k,v in items:assert k not in d;d[k]=v
 return d
def decode(raw):return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
def read(path,pn=None):
 assert 'eu4.exe'not in path.lower()and not path.startswith('work/deps/')
 guard();f=ROOT/path;a=f.stat();assert a.st_size<=4*1024*1024
 raw=f.read_bytes();z=f.stat();assert len(raw)==a.st_size and(a.st_size,a.st_mtime_ns)==(z.st_size,z.st_mtime_ns)
 actual=pin(raw)
 if pn is not None:assert actual==pn,(path,actual,pn)
 reads.append(dict(path=path,**actual));guard();return raw
def write(n,o):
 raw=(json.dumps(o,indent=2,ensure_ascii=True)+'\n').encode('ascii');assert len(raw)<4*1024*1024
 with(OUT/n).open('xb')as f:f.write(raw)
 return pin(raw)
def iv(n):return int(n,16)if isinstance(n,str)else n
def relative(path):
 s=str(path).replace('\\','/');pre=ROOT.as_posix()+'/'
 return s[len(pre):]if s.startswith(pre)else s
SPEC='''
4883ec10 sub
4c891424 mov
4c895c2408 mov
4d33db xor
4c8d542418 lea
4c2bd0 sub
4d0f42d3 cmovb
654c8b1c2510000000 mov
4d3bd3 cmp
7316 jae
664181e200f0 and
4d8d9b00f0ffff lea
41c60300 mov
4d3bd3 cmp
75f0 jne
4c8b1424 mov
4c8b5c2408 mov
4883c410 add
c3 ret
'''
STORE={0x1a337f4:('rsp',0,None,8),0x1a337f8:('rsp',8,None,8),0x1a33827:('r11',0,None,1)}
READ={0x1a3380c:(None,16,'gs',8),0x1a33830:('rsp',0,None,8),0x1a33834:('rsp',8,None,8)}
BRANCH={0x1a33818:0x1a33830,0x1a3382e:0x1a33820}
def main():
 cache=decode(read(O+'retained-files.json',CACHE));supp=decode(read(O+'retained-delivery.json',SUPP));files=cache['files']|supp['files'];objects={}
 for path,e in files.items():
  rr=bytes.fromhex(e['raw_hex']);assert pin(rr)=={k:e[k]for k in('bytes','sha256')}
  if path.endswith('.json'):objects[path]=decode(rr)
 def obj(n):return objects[B+n]
 def pn(path):return {k:files[path][k]for k in('bytes','sha256')}
 m=obj('manifest.json');c=obj('capture.json');s=obj('selected-evidence.json');o=obj('owned-code.json');contract=obj('contract.json')
 assert len(m['source_pins'])==m['actual_file_pin_count']==37 and len(m['decoder_expected_witness_pins'])==38
 assert m['source_pins']=={path:pn(path)for path in m['source_pins']} and m['decoder_files_reopened_by_sealer']is False
 assert c['game_sha256']==o['game_sha256']==s['game_sha256']==GAME and c['game_bytes']==38462504
 raw=bytes.fromhex(o['raw_hex']);assert len(raw)==o['bytes']==78 and o['full_extent_owned']is True
 assert o['window']==['0x1a337f0','0x1a3383e']and hashlib.sha256(raw).hexdigest()==o['sha256']==s['raw_sha256']
 assert bytes.fromhex(s['raw_hex'])==raw
 rows=c['analysis']['instructions'];assert rows==s['instructions']and len(rows)==19
 spec=[line.split()for line in SPEC.splitlines()if line.strip()];assert len(spec)==19
 cursor=0x1a337f0;replay=[];succ={};rowmap={}
 for row,(hx,mn)in zip(rows,spec):
  at=iv(row['rva']);b=bytes.fromhex(hx);assert at==cursor and(row['bytes'],row['mnemonic'])==(hx,mn)
  assert raw[at-0x1a337f0:at-0x1a337f0+len(b)]==b
  mem=[]if mn=='lea'else row['memory_operands'];r=READ.get(at);w=STORE.get(at)
  assert sum(q['read']is True for q in mem)==bool(r)and sum(q['write']is True for q in mem)==bool(w)
  for expected,field in((r,'read'),(w,'write')):
   if expected:
    q=next(q for q in mem if q[field]);assert(q['base'],q['displacement'],q['segment'],q['width_bytes'])==expected
    assert q['index']is None and q['rip_target_rva']is None
  after=at+len(b)
  if at in BRANCH:
   target=after+int.from_bytes(b[1:],'little',signed=True);assert target==BRANCH[at]and row['immediates']==[target]
  succ[at]=[]if mn=='ret'else[after,BRANCH[at]]if at in BRANCH else[after]
  replay.append(dict(rva=hex(at),raw_hex=hx,mnemonic=mn,owned_equal=True,read=r,store=w,successors=[hex(n)for n in succ[at]]))
  rowmap[at]=row;cursor=after
 assert cursor==0x1a3383e and b''.join(bytes.fromhex(x[0])for x in spec)==raw
 todo=[0x1a337f0];seen=set()
 while todo:
  at=todo.pop()
  if at in seen:continue
  assert at in rowmap;seen.add(at);todo.extend(succ[at])
 assert len(seen)==19
 assert c['analysis']['edges']==s['edges']and len(s['edges'])==2
 for e in s['edges']:
  at=iv(e['site']);assert iv(e['target_rva'])==BRANCH[at]and e['inside_owned_window']is True
  assert e['local_branch_target_enqueued']is True and e['callee_followed']is False
  assert iv(e['fallthrough'])==at+2
 assert c['analysis']['terminals']==s['terminals']==[dict(kind='normal_ret',rva='0x1a3383d')]
 assert c['analysis']['local_normal_CFG_closed']is True and c['analysis']['undecoded_owned_intervals']==[]
 assert c['analysis']['dynamic_reachability_verified']is False
 look=c['analysis']['lookahead_inputs'];assert len(look)==19 and look==s['lookahead_inputs']
 for x,row in zip(look,rows):assert iv(x['rva'])==iv(row['rva'])and x['bytes']==min(15,0x1a3383e-iv(row['rva']))
 assert sum(x['bytes']for x in look)==255 and c['analysis']['decoder_overlap_bytes']==177
 # Byte width/ModRM facts independent of retained decoder regaccess annotations.
 assert bytes.fromhex(rowmap[0x1a3381a]['bytes'])[:2]==b'\x66\x41'and rowmap[0x1a3381a]['immediates']==[0xf000]
 assert rowmap[0x1a33820]['memory_operands'][0]['displacement']==-0x1000
 assert rowmap[0x1a33827]['immediates']==[0]
 forbidden={'rax','eax','ax','al','ah','rcx','ecx','cx','cl','ch','rdx','edx','dx','dl','dh','r8','r8d','r8w','r8b','r9','r9d','r9w','r9b'}
 assert not any(forbidden&set(row['registers_written'])for row in rows)
 assert not any(any(n.startswith(('xmm','ymm','zmm'))for n in row['registers_read']+row['registers_written'])for row in rows)
 assert all(row['mnemonic']not in('call','std','cld','popf','popfq','iret','iretq')for row in rows)
 assert [row['mnemonic']for row in rows if row['mnemonic']=='ret']==['ret']
 # All scalar flags after restore come from the final ADD RSP,10. DF is untouched.
 assert rowmap[0x1a33839]['bytes']=='4883c410'and rowmap[0x1a3383d]['bytes']=='c3'
 # Retained Pdata and cached mapping arithmetic, without opening the PE.
 anchors=objects['work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json'];sections=anchors['sections']
 def offset(rva,n):
  matches=[q for q in sections if iv(q['rva'])<=rva and rva+n<=iv(q['rva'])+q['raw_size']];assert len(matches)==1
  q=matches[0];return q['raw_file_offset']+rva-iv(q['rva'])
 pd=next(q for q in sections if q['name']=='.pdata');requests=c['pdata_requests'];assert len(requests)==19
 lo,hi=0,pd['virtual_size']//12
 for q in requests:
  rr=bytes.fromhex(q['raw_hex']);assert len(rr)==12
  assert struct.unpack('<III',rr)==tuple(iv(q[k])for k in('begin_rva','end_exclusive','unwind_rva'))
  assert iv(q['rva'])==iv(pd['rva'])+q['index']*12 and q['file_offset']==offset(iv(q['rva']),12)
  if q['reason']=='binary_search':
   assert q['index']==(lo+hi)//2
   if iv(q['begin_rva'])<=0x1a337f0:lo=q['index']+1
   else:hi=q['index']
 assert lo==hi==63540
 assert c['selected']['index']==63539 and c['selected']['raw_hex']=='f037a3013e38a301c821fa01'
 assert iv(c['selected']['begin_rva'])==0x1a337f0 and iv(c['selected']['end_exclusive'])==0x1a3383e and c['exact_pdata_begin']is True
 assert iv(c['previous']['end_exclusive'])<=0x1a337f0 and 0x1a3383e<=iv(c['next']['begin_rva'])
 assert c['pdata_physical_bytes']==228 and c['pdata_unique_bytes']==len({q['index']for q in requests})*12==204
 sparse=c['sparse_reads'];assert len(sparse)==20 and sum(q['bytes']for q in sparse)==306
 assert sparse[-1]['kind']=='single_entry_code'and sparse[-1]['bytes']==78 and sparse[-1]['file_offset']==o['file_offset']==offset(0x1a337f0,78)
 assert c['full_PE_authentication_reads']==[dict(phase=phase,bytes_read=38462504,completed=True,sha256=GAME)for phase in('before','after')]
 assert c['total_PE_physical_bytes']==76925008+306==76925314
 # Three independent gates and one-shot author capture receipts.
 auth=obj('run-authorization.json');acq=obj('acquisition-receipt.json');claim=obj('claim.json');rootclaim=obj('root-invocation-claim.json');base=obj('source-manifest.json')
 assert auth['source_manifest']==pn(B+'source-manifest.json')and auth['producer_pin']==pn(B+'produce.py')and auth['entry_seed_pin']==pn(B+'entry-seed.json')
 assert auth['root_explicit_start_received']is True and auth['automatic_retry']is False
 assert c['source_manifest']==claim['source_manifest']==auth['source_manifest']
 assert c['source_pins']==claim['source_pins']==base['source_pins']
 assert c['authorization_pin']==claim['authorization_pin']==rootclaim['authorization']==pn(B+'run-authorization.json')
 assert c['decoder_expected_pins']==base['decoder_expected_witness_pins']==m['decoder_expected_witness_pins']
 reviews={auth['seed_review_path']:auth['seed_review_pin']}
 rm=auth['root_review_manifest'];reviews[rm['path']]={k:rm[k]for k in('bytes','sha256')}
 for group in('upstream_body_review','source_peer_review'):
  for value in auth[group].values():reviews[value['path']]={k:value[k]for k in('bytes','sha256')}
 for path,pinexpected in reviews.items():assert pn(path)==pinexpected
 for path in(auth['seed_review_path'],auth['upstream_body_review']['findings']['path'],auth['source_peer_review']['findings']['path']):
  q=objects[path];assert q['sealed']is True and q['passed']is True and q['blocking_findings']==[]
 peer=objects[auth['source_peer_review']['findings']['path']]
 assert peer['subject_source_manifest']==pn(B+'source-manifest.json')and peer['subject_producer']==pn(B+'produce.py')and peer['subject_entry_seed']==pn(B+'entry-seed.json')
 assert acq['review_pins']==rootclaim['review_pins']==reviews
 assert acq['exit_code']==0 and acq['direct_owned_child_collected']is True and acq['failure_files']==[]and acq['all_admission_pins_prepost_equal']is True
 assert acq['stdout']==pn(B+'producer.stdout.json')and acq['stderr']==pn(B+'producer.stderr.txt')and files[B+'producer.stderr.txt']['bytes']==0
 assert obj('producer.stdout.json')['capture_pin']==pn(B+'capture.json')
 journal=c['source_file_reads'];assert sum(x['bytes']for x in journal)==c['source_file_read_bytes']==16786447 and c['source_engine_before_after_equal']is True
 for phase in('source_engine_before','source_engine_after'):
  q=[x for x in journal if x['phase']==phase and x['operation']=='streaming_engine_pin']
  assert len(q)==38 and {relative(x['path']):x['bytes']for x in q}=={p:v['bytes']for p,v in m['decoder_expected_witness_pins'].items()}
 source=bytes.fromhex(files[B+'produce.py']['raw_hex']).decode('ascii');maintext=source[source.index('def main():'):]
 assert maintext.index("for label in ('upstream_body_review','source_peer_review')")<maintext.index('base,pins=source_guard()')<maintext.index("save('claim.json'")<maintext.index("stream=(ROOT.parent/'eu4.exe').open('rb')")
 assert maintext.index("authenticate('after')")<maintext.index('_,postpins=source_guard()')<maintext.index('finally:')<maintext.index('stream.close()')<maintext.index("save('capture.json',value)")
 assert "open('x'"in source and 'sys.argv[1:]==[]'in source
 # Source/retained budgets are witness claims backed by exact event sums.
 delivery=obj('delivery-receipt.json');last=obj('actual-delivery-manifest.json');fc=obj('filecheck.json')
 for path,expected in last['source_pins'].items():assert pn(path)==expected
 for name,expected in delivery['outputs'].items():assert pn(B+name)==expected
 assert fc['subject_manifest']==pn(B+'manifest.json')and fc['passed']is True and fc['file_pins_verified']==37
 assert sum(q['bytes']for q in m['retained_seal_read_events'])==m['retained_seal_returned_bytes']==562161
 assert sum(q['bytes']for q in fc['read_events'])==fc['returned_bytes']==589733
 assert sum(q['bytes']for q in delivery['retained_read_events'])==delivery['this_delivery_returned_bytes_at_receipt']==190031
 assert 16786447+pn(B+'capture.json')['bytes']==16867855==delivery['producer_source_returned_bytes_including_postcapture_pin']
 retained=562161+589733+1048576+190031+65536
 assert retained==delivery['retained_stage_explicit_upper_bytes']==2456037
 assert 16867855+retained==delivery['combined_producer_retained_stage_explicit_upper_bytes']==19323892
 assert delivery['producer_exit_code']==delivery['sealer_exit_code']==delivery['filecheck_exit_code']==0 and delivery['all_owned_children_and_shells_collected']is True
 assert all(x is False for x in contract['authority'].values())
 # Independently hash only45 listed text/retained files; no engine or PE body.
 for path,e in files.items():read(path,{k:e[k]for k in('bytes','sha256')})
 known_prior=cache['source_bytes']+cache['prior_schema_inspection_bytes']+supp['source_bytes']
 inspection_upper=CACHE['bytes']+65536
 own_seal_reserve=2*1024*1024
 upper=known_prior+inspection_upper+sum(x['bytes']for x in reads)+own_seal_reserve;assert upper<LIMIT
 model=dict(
  entry='LetS=entryRSP,N=entryRAX. LocalRSP=S-16; saveentryR10 atS-16,entryR11 atS-8.',
  candidate='R11=0; R10=(S+8)mod64; SUBR10,N; ifunsignedborrow CMOVB selects0, else subtractionresult.',
  GS='B=u64(GSbase+0x10). Neither GSfieldname nor validstack/worldmapping is proved.',
  branch='If unsignedcandidate>=B skiploop; otherwise AND16 R10W,f000 => L=candidate&fffffffffffff000.',
  loop='EachstepR11=submod64(R11,4096); storeBYTE[R11]=0; compare64L,R11; JNEstep. One staticsite, zeroorloopdependent dynamicstores.',
  conditional_termination='IfB is4096aligned, candidate<B, validnormalstores and noasync/codechanges, L<=candidate<B and (B-L)/4096 finite no-wrap steps. ArbitraryB/permissions/faults remainunknown.',
  concrete_preservation='NoRCX/RDX/RAX/R8/R9/XMMwrites in thisbody; under normal execution those registers retain entryvalues. This follows explicitinstructions, notordinaryvolatileABI.',
  R10_R11='Reloadsavedqwords; equalentryvaluesonlyifthosebyteswere notaliased/clobbered. GSderivedstoretargetsavedstack/returnslot/H/Talias notexcluded.',
  RSP='BeforeRET RSP=S modulo64 bySUB16/ADD16; normalRET consumesreturnqword and yields S+8. Actualnormalreturn/controltarget/validmemory isnotproved.',
  flags='FinalADD64(S-16,16) produces final arithmeticflags; incomingarithmeticflags notpreserved. DFnotwritten byanyselectedinstruction, so inheritedDF onnormalnonasyncpath.',
  R66='Fixedcaller EAX1040 ->helper N1040; normalreturn preservesRAX1040/RCXH/RDXT and balancesCALLstack. SubsequentcallerSUBallocates1040 concretely; freshH/Treads stillrequired and contentsnotprovedunchanged.')
 rp=write('raw-replay.json',dict(schema='EU4-R67-INDEPENDENT-ACTUAL-RAW/1',passed=True,rows=replay,
  full_owned_bytes=78,rows_count=19,edges=s['edges'],terminals=s['terminals'],explicit_store_sites=3,stack_store_sites=2,GS_derived_store_sites=1,explicit_read_sites=3,
  LEA_dereference_excluded=True,implicit_RET_stack_read_separate=True,CALL_sites=0,CFG_closed_local_normal_only=True,
  pdata=dict(physical_records=19,unique_records=17,physical_bytes=228,unique_bytes=204,selected=c['selected'],previous=c['previous'],next=c['next'],binary_search_replayed=True),
  lookahead=dict(attempts=19,cumulative_input_bytes=255,unique_input_bytes=78,overlap_bytes=177),model=model,
  source_postguard_equal=True,no_new_PE_or_decoder=True))
 authority={key:False for key in contract['authority']}
 ops={key:0 for key in('PE_stat_open','engine_stat_open','decoder','author_producer_or_driver','tests','game_process','Frida','native_game_calls','requests','callee_expansion','RTTI_scope','new_actual')}
 fp=write('findings.json',dict(schema='EU4-R67-INDEPENDENT-ACTUAL-FINDINGS/1',sealed=True,passed=True,blocking_findings=[],
  subject_manifest=pn(B+'manifest.json'),subject_contract=pn(B+'contract.json'),subject_capture=pn(B+'capture.json'),
  author_frozen_source_needs_change=False,raw_replay=rp,checks=dict(actual_source_pins=37,explicit_additional_finalpins=len(files)-38,
   engine_metadata_witness_pins_unopened=38,owned_bytes=78,rows=19,CALL_sites=0,conditional_branches=2,RET_sites=1,explicit_store_sites=3,
   stack_store_sites=2,GS_derived_store_sites=1,explicit_read_sites=3,raw_width_CFG_metadata_replayed=True,three_review_gates_auth_claim_bound=True,source_postguard_equal=True),
  machine_contract=model,precision_notes=[
   'Registerpreservation and balancedRSP follow the complete concrete normal instructions. They do not prove normalreturn/faultfreedom or immutableH/Tdata.',
   'The GSderivedBYTEwrite can alias borrowedobjects, savedR10/R11qwords orreturnslot; no processstackownership/type is established. R10/R11restore is conditionalonuncorrupted savedbytes.',
   'AND R10W,f000 preservesupper48bits and clearslow12; it is not DWORDzeroextension. BranchJAEstaysunsigned64; loopLEAdisplacement is signed-4096 with modulo64addressarithmetic.',
   'ConditionalnormalR66crosswalk may now fill postRAX1040/RCXH/RDXTregistervalues andCALLbalance; older frozenR66unknown remains historical. This doesnotremove freshH/Treads, nativeguards or lifetimeconditions.',
   'No helper/CRT/businessname, safeexecution, selectedAPIeffect, amountunit, recipient, conservation, sort or lifetime authority follows.',
   'Source/PE/decoder/resource identities are retained producerwitnesses; no enginebody orPE was independentlyopened. 503865800ns is producerlaunch-to-collectedexit, notnativecalllatency.',
   'Retainedupper2456037 includes1048576 manual/wrapperprepallowance and65536 finaldeliveryallowance, not exactallOS/interpreter/loaderIO.'
  ],resource_witness=dict(source_journal_at_capture=16786447,post_capture_pin_bytes=81408,producer_source_bytes=16867855,
   retained_explicit_upper=2456037,combined_explicit_upper=19323892,PE_separate_bytes=76925314,
   producer_elapsed_ns=acq['elapsed_ns'],producer_peak_bytes=c['peak_committed_bytes_observed'],hard_Job_installed=False),
  independent_resources=dict(known_prior_listed_bytes=known_prior,prior_inspection_upper_bytes=inspection_upper,
   final_cache_and_source_postguard_bytes=sum(x['bytes']for x in reads),own_sealing_reserve_bytes=own_seal_reserve,
   listed_analysis_upper_bytes=upper,source_limit_bytes=LIMIT,own_peak_bytes=peak,memory_limit_bytes=MEMORY,
   no_all_OS_loader_IO_claim=True,recursive_closure=False),
  operations=ops,authority=authority,self_diagnostics=dict(review_failures=0,finaldelivery_filenames_fixed_from_directory_metadata_before_first_intake=True),
  all_shells_collected=True,next_scope_auto_authorized=False))
 report=('R67 complete retained-file review passed. All19rows/78bytes and unsigned64branches agree. '
  'Normal concrete instructions preserveRCX/RDX/RAX and balanceRSP; fixedR66postRAX1040 is therefore conditional machinefact. '
  'GSderivedloopBYTEwrites retainH/T/savedframe/returnslotalias andfault/terminationunknowns. '
  'No helpername, contentpreservation, nativepermission, lifetime or effect is established.\n').encode('ascii')
 with(OUT/'report.md').open('xb')as f:f.write(report)
 names=('retained-files.json','retained-delivery.json','raw-replay.json','findings.json','report.md')
 local={O+n:pin((OUT/n).read_bytes())for n in names}
 for path in('work/retain_r67_actual_review_20261016.py','work/review_r67_actual_20261016.py'):local[path]=pin((ROOT/path).read_bytes())
 mp=write('manifest.json',dict(schema='EU4-R67-INDEPENDENT-ACTUAL-MANIFEST/1',sealed=True,source_pins={path:pn(path)for path in files},local_pins=local,
  source_scope='37actual+subjectmanifest+7explicit finaldelivery/check files;45flat files, no recursiveclosure',engine_metadata_unopened=38,findings=fp,operations=ops,authority=authority))
 print(json.dumps(dict(passed=True,findings=fp,raw_replay=rp,manifest=mp,listed_analysis_upper_bytes=upper,peak=peak,all_shells_collected=True)))
def check():
 m=decode(read(O+'manifest.json'))
 for path,pn in(m['source_pins']|m['local_pins']).items():read(path,pn)
 f=decode(read(O+'findings.json',m['local_pins'][O+'findings.json']))
 upper=f['independent_resources']['listed_analysis_upper_bytes']+sum(x['bytes']for x in reads);assert upper<LIMIT
 vp=write('verification.json',dict(schema='EU4-R67-INDEPENDENT-ACTUAL-VERIFICATION/1',passed=True,checked_pins=len(m['source_pins']|m['local_pins']),
  all_flat_sources_current_equal=True,byte_verification_only=True,conservative_complete_stage_upper_bytes=upper,source_limit_bytes=LIMIT,
  own_peak_bytes=peak,operations=m['operations'],authority=m['authority'],all_shells_collected=True))
 print(json.dumps(dict(passed=True,verification=vp,checked_pins=len(m['source_pins']|m['local_pins']),conservative_complete_stage_upper_bytes=upper,peak=peak)))
if __name__=='__main__':
 try:check()if sys.argv[1:]==['--check']else main()
 except Exception as exc:
  n='verification-failure.json'if sys.argv[1:]==['--check']else'review-failure.json'
  if not(OUT/n).exists():write(n,dict(type=type(exc).__name__,detail=str(exc),reads=reads,peak=peak,author_sources_unchanged=True,no_PE_or_program_replay=True))
  raise
