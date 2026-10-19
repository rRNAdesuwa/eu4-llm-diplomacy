"""R70 DATA entry-seed review only. No scanner/parser/producer/tests executed."""
from pathlib import Path
import hashlib,json,struct,ctypes,sys
from ctypes import wintypes
ROOT=Path(__file__).resolve().parents[1];B='work/reports/server-vtable-rip-reference-seeds-20261016-r1/';O='work/reports/server-vtable-rip-entry-independent-review-20261016-r1/';OUT=ROOT/O
D='work/reports/server-vtable-rtti-20261016-r1/';V='work/reports/server-vtable-rtti-data-independent-review-20261016-r1/'
A='work/reports/war-peace-api-20261015-r27-truce-literal-anchors/war/anchors.json'
LIMIT=16*1024*1024;MEMORY=768*1024*1024;peak=0;reads=[]
CACHE=dict(bytes=316578,sha256='31018db8e2c437882c2956917bb0de637a5a6f4911e8fedc74bd73136f93fe07')
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
def main():
 cache=decode(read(O+'retained-files.json',CACHE));files=cache['files'];objects={}
 for path,e in files.items():
  raw=bytes.fromhex(e['raw_hex']);assert pin(raw)=={k:e[k]for k in('bytes','sha256')}
  if path.endswith('.json'):objects[path]=decode(raw)
 def pn(path):return {k:files[path][k]for k in('bytes','sha256')}
 m=objects[B+'source-manifest.json'];final=objects[B+'final-manifest.json'];seed=objects[B+'entry-seed.json'];budget=objects[B+'budget.json']
 assert len(m['source_pins'])==14 and len(final['source_pins'])==23
 assert set(m['source_pins'])<=set(final['source_pins'])
 for path,expected in final['source_pins'].items():assert pn(path)==expected
 assert m['actual_authorized']is False and m['tests_authorized']is False and final['actual_authorized']is False and final['tests_run']==0
 cap=objects[D+'capture.json'];contract=objects[D+'data-contract.json'];review=objects[V+'findings.json'];datafinal=objects[D+'data-final-manifest.json'];anchors=objects[A]
 assert review['sealed']is True and review['passed']is True and review['blocking_findings']==[]
 assert review['subject_capture_pin']==pn(D+'capture.json')and review['subject_contract_pin']==pn(D+'data-contract.json')and review['subject_data_final_manifest_pin']==pn(D+'data-final-manifest.json')
 assert seed['upstream_capture_pin']==review['subject_capture_pin']and seed['upstream_contract_pin']==review['subject_contract_pin']and seed['upstream_data_final_manifest_pin']==review['subject_data_final_manifest_pin']
 for path,expected in seed['upstream_DATA_full_review_source_pins'].items():assert pn(path)==expected
 assert contract['subject_capture_pin']==pn(D+'capture.json')and cap['source_pre']==cap['source_post']and cap['source_guard_equal']is True
 targets=seed['target_vtable_rvas'];assert all(type(x)is int and x>0 for x in targets)and targets==[0x1cb8460,0x1d5a8c8]
 assert targets==[q['vtable_rva']for q in cap['chains']]==[iv(x)for x in contract['selected_vtable_rvas']]
 assert len(cap['chains'])==2 and all(x['status']=='unknown'for x in cap['chains'])and review['two_chains_unknown']is True
 assert all(x is False for x in contract['authority'].values())and all(x is False for x in review['authority'].values())
 base=iv(seed['preferred_image_base']);assert base==0x140000000==iv(cap['preferred_image_base'])==iv(anchors['preferred_image_base'])
 optional=next(x for x in anchors['PE_header_reads']if x['label']=='PE32+ optional');optraw=bytes.fromhex(optional['raw_hex'])
 assert optraw[24:32].hex()==seed['cached_preferred_base_raw8_hex']and int.from_bytes(optraw[24:32],'little')==base
 table=next(x for x in anchors['PE_header_reads']if x['label']=='section table');tab=bytes.fromhex(table['raw_hex']);assert len(tab)%40==0
 sections=anchors['sections'];text=[x for x in sections if x['name']=='.text'];assert len(text)==1;section=text[0]
 assert seed['cached_text_section_evidence']==section
 header=bytes.fromhex(section['section_header_raw_hex']);assert len(header)==40 and header==tab[:40]
 name,virtual_size,rva,raw_size,raw_offset,reloc,line,relocs,lines,flags=struct.unpack('<8sIIIIIIHHI',header)
 assert name.rstrip(b'\0')==b'.text'and(rva,raw_offset,raw_size)==(0x1000,0x400,28724736)
 assert(virtual_size,flags)==(28724600,0x60000020)
 assert seed['text_section']==dict(rva=rva,raw_file_offset=raw_offset,raw_size=raw_size)
 assert section['raw_file_range']==[raw_offset,raw_offset+raw_size]
 assert [iv(x)for x in section['raw_mapped_rva_range']]==[rva,rva+raw_size]
 assert raw_offset+raw_size<=seed['game_bytes']==38462504
 assert seed['cached_section_source_pin']==pn(A)
 assert all(x['game_sha256']==seed['game_sha256']for x in(cap,anchors))
 data=[]
 for target,observed in zip(targets,contract['observed']):
  q=observed['selected_read'];b=bytes.fromhex(q['raw_hex']);assert len(b)==q['requested_bytes']==q['returned_bytes']==8 and q['rva']==target-8
  va=int.from_bytes(b,'little');destination=va-base
  assert va==iv(observed['raw_QWORD_preferred_va'])and destination==iv(observed['normalized_target_rva'])
  matches=[s for s in sections if iv(s['rva'])<=destination and destination+24<=iv(s['rva'])+s['raw_size']]
  assert len(matches)==1 and matches[0]['name']=='.text'and observed['hypothetical_target_was_not_read']is True
  assert observed['target_is_a_COL_or_function_proved']is False and observed['raw_RTTI_name']is None and observed['status']=='unknown'
  data.append(dict(target_rva=hex(target),pre_slot_rva=hex(target-8),raw8=q['raw_hex'],preferred_va=hex(va),arithmetic_target_rva=hex(destination),cached_target_section='.text',target_body_not_read=True))
 assert contract['budget']['actual_DATA_requested_and_returned_bytes']==16 and review['DATA_requested_and_returned_bytes']==16
 # Seed range arithmetic only: do not import scanner or exercise its implementation.
 chunk=budget['text_scan_chunk_bytes'];assert chunk==65536
 full,last=divmod(raw_size,chunk);chunks=full+(last!=0);carry=6*(chunks-1)
 assert(chunks,last,carry)==(439,19968,2628)
 assert budget['text_scan_max_chunks']==chunks and budget['text_last_chunk_bytes']==last
 assert budget['physical_text_bytes_complete_scan']==raw_size and budget['in_memory_carry_bytes_complete_scan']==carry
 assert budget['scanner_input_bytes_complete_scan_including_carry']==raw_size+carry==28727364
 authbytes=2*seed['game_bytes'];assert budget['full_PE_SHA_passes']==2 and budget['full_PE_SHA_normal_returned_bytes']==authbytes==76925008
 assert budget['complete_normal_physical_PE_returned_bytes']==authbytes+raw_size==105649744
 assert budget['broader_SHA_plus_input_envelope_not_expected_physical_count']==authbytes+raw_size+carry==105652372
 assert budget['context_metadata_virtualslot_callee_data_header_unwind_followups']==budget['engine_decoder_imports']==0
 protocol=bytes.fromhex(files[B+'PROTOCOL.md']['raw_hex']).decode('ascii')
 assert '(byte2 & c7h) == 05h'in protocol and 'Byte0 is exactly48 or4c, byte1 is8d'in protocol
 assert 'candidateRVA+7+disp'in protocol and 'Signed little-endian disp32'in protocol
 assert seed['instruction_boundary_verified']is False and seed['RTTI_absence_verified']is False and seed['host_guard_change_authorized']is False
 assert seed['existing_instruction_reference_provided_by_selected_sources']is False
 pre=objects[B+'preparation.json'];fc=objects[B+'prepared-filecheck.json'];receipt=objects[B+'source-preparation-receipt.json']
 assert pre['producer_executions']==pre['new_fixture_tests_run']==pre['target_PE_stat_open_hashes']==0
 assert pre['source_before_after_equal']is True and pre['claim_or_actual_authorization_created']is False
 assert fc['sealed']is True and fc['passed']is True and fc['blocking_findings']==[]and fc['subject_source_manifest']==pn(B+'source-manifest.json')
 assert receipt['new_fixture_methods_written']==10 and receipt['new_fixture_methods_executed']==0 and receipt['producer_executions']==0
 assert receipt['prepare_exit_code']==receipt['filecheck_exit_code']==0 and receipt['authorization_or_claim_created']is False
 assert receipt['all_owned_children_and_shells_collected']is True
 assert receipt['preparation_returned_bytes']+receipt['filecheck_returned_bytes']+receipt['current_finalseal_returned_bytes_at_receipt']+receipt['final_pin_output_allowance_bytes']==receipt['stage_explicit_upper_bytes']==439162
 for path,e in files.items():read(path,{k:e[k]for k in('bytes','sha256')})
 knownprior=cache['source_bytes']+cache['prior_initial_inspection_bytes'];inspectionupper=CACHE['bytes']+32768;sealreserve=512*1024
 upper=knownprior+inspectionupper+sum(x['bytes']for x in reads)+sealreserve;assert upper<LIMIT
 proof=write('seed-replay.json',dict(schema='EU4-R70-INDEPENDENT-DATA-SEED-REPLAY/1',passed=True,fixed_targets=[hex(x)for x in targets],DATA_pre_slots=data,
  source_DATA_full_review_bound=True,unknown_live_VA_minus_base_not_replayed_here=True,
  cached_text=dict(rva=rva,file_offset=raw_offset,raw_bytes=raw_size,virtual_bytes=virtual_size,padding_raw_bytes=raw_size-virtual_size,unique_section_mapping=True,header40_exact=header.hex(),preferred_base=hex(base)),
  encoding_plan=dict(REX_allowed=['48','4c'],opcode='8d',ModRM_mask='c7',ModRM_value='05',complete_window_bytes=7,signed_disp32_bytes=[3,6],formula='candidateRVA+7+signextend32(disp)',fixed_targets_only=True,
   actual_instruction_boundary=False,actual_reference=False,all_possible_encodings_covered=False),
  planned_scan_arithmetic=dict(chunk_bytes=chunk,chunks=chunks,last_chunk_bytes=last,physical_selected_text_bytes=raw_size,reused_carry_bytes=carry,in_memory_scanner_bytes=raw_size+carry,
   dual_SHA_bytes=authbytes,physical_total_with_SHA=authbytes+raw_size,broader_input_envelope=authbytes+raw_size+carry),
  implemented_scanner_or_fixture_behavior_accepted=False,actual_authorized=False,tests_authorized=False,source_current_postguard_equal=True))
 ops={k:0 for k in('PE_stat_open','engine_stat_open','decoder','scanner_parser_execution','producer','tests','game_process','Frida','native_game_calls','requests','actual_scan','callee_context_follow')}
 authority={k:False for k in('actual_authorized','tests_authorized','native_ready','callable','host_guard_change_authorized','vtable_compatibility_verified','class_layout_verified','runtime_identity_verified','instruction_boundary_verified','actual_xref_verified','selected_effect_verified','world_lease','atomic_snapshot','authorizes_retry')}
 fp=write('findings.json',dict(schema='EU4-R70-INDEPENDENT-ENTRY-SEED-FINDINGS/1',sealed=True,passed=True,blocking_findings=[],scope='raw_DATA_entry_seed_only',
  subject_source_manifest=pn(B+'source-manifest.json'),subject_entry_seed=pn(B+'entry-seed.json'),subject_final_manifest=pn(B+'final-manifest.json'),seed_replay=proof,
  upstream_DATA_full_review=dict(path=V+'findings.json',**pn(V+'findings.json')),
  checks=dict(source_graph_pins=14,final_delivery_pins=23,total_explicit_retained_files=24,two_DATA_targets_match_exact=True,cached_text_unique_raw_mapping=True,
   complete7B_REX_LEA_RIP_pattern_range_only=True,physical_vs_carry_and_two_SHA_budget_arithmetic_equal=True,all_current_pins_pre_post_equal=True),
  limits=[
   'Only24explicitretainedfiles are read. OriginalunknownliveVA-base arithmetic is inherited sealedreviewwitness, not rerun or re-read here; exactDATAchain subjects establish fixedstaticfilter targets only.',
   'Two vtable[-1] rawQWORDs arithmetically map into cached.text and remainunknown. No COL/TypeDescriptor/name, RTTIabsence, vtableboundary/class/mode/currenthostcompatibility follows.',
   'The 7B profile includes only REX48/4c+8d+ModRMmod00rm101 and signeddisp32. It doesnot establish instructionboundaries, actualxref, constructor/function context or exhaustallpossibleencodings.',
   'Cached.textrawspan includes136paddingbytes beyondvirtualsize. Rawmembership and a bytepatternmatch do not prove execution or source instruction alignment.',
   'Carry2628B is reusedmemory, notadditionaltargetphysicalIO. SHA76925008B is separate. Allnormalcomplete-scan counts are plans, not evidence that anyscan ran.',
   'No scanner/parser/producer/fixtures were imported or executed. Implementationacceptance belongs to the separate sourcepeerreview, not thisDATAentryseed review.',
   'Futurecontext/pdata/callee/vtable-slot/unwind/header/literal followups, currentguardrelaxation and retry are excluded. Thispassedseed is not anactual or test grant.'
  ],resource_witness=dict(source_preparation_upper_bytes=439162,new_fixture_methods_written=10,new_fixture_methods_executed=0,producer_executions=0),
  independent_resources=dict(known_prior_bytes=knownprior,prior_cache_inspection_upper_bytes=inspectionupper,final_cache_and_postguard_bytes=sum(x['bytes']for x in reads),
   own_sealing_reserve_bytes=sealreserve,listed_analysis_upper_bytes=upper,source_limit_bytes=LIMIT,own_peak_bytes=peak,memory_limit_bytes=MEMORY,no_all_OS_loader_IO_claim=True,recursive_closure=False),
  operations=ops,authority=authority,actual_authorized=False,tests_authorized=False,all_shells_collected=True,next_scope_auto_authorized=False))
 report=('R70 raw DATA-entry seed review passed. Fixedtargets1cb8460/1d5a8c8 match the two frozenDATA subjects and passedfullDATA review; rawpre-slot targets remainunknown. '
  'Cached.text mapping and planned439chunks/28,724,736physicalbytes/2,628carry arithmetic agree. No scan, test, instructionboundary, xref, class or currenthostauthority is established.\n').encode('ascii')
 with(OUT/'report.md').open('xb')as f:f.write(report)
 local={O+n:pin((OUT/n).read_bytes())for n in('retained-files.json','seed-replay.json','findings.json','report.md')}
 for path in('work/retain_r70_entry_20261016.py','work/review_r70_entry_20261016.py'):local[path]=pin((ROOT/path).read_bytes())
 mp=write('manifest.json',dict(schema='EU4-R70-INDEPENDENT-ENTRY-SEED-MANIFEST/1',sealed=True,source_pins={path:pn(path)for path in files},local_pins=local,
  source_scope='14source/23deliveryflatunion plusfinalmanifest;24 explicitfiles, no recursiveclosure',findings=fp,operations=ops,authority=authority))
 print(json.dumps(dict(passed=True,findings=fp,seed_replay=proof,manifest=mp,listed_analysis_upper_bytes=upper,peak=peak,all_shells_collected=True)))
def check():
 m=decode(read(O+'manifest.json'))
 for path,pn in(m['source_pins']|m['local_pins']).items():read(path,pn)
 f=decode(read(O+'findings.json',m['local_pins'][O+'findings.json']))
 upper=f['independent_resources']['listed_analysis_upper_bytes']+sum(x['bytes']for x in reads);assert upper<LIMIT
 vp=write('verification.json',dict(schema='EU4-R70-INDEPENDENT-ENTRY-VERIFICATION/1',passed=True,checked_pins=len(m['source_pins']|m['local_pins']),all_flat_sources_current_equal=True,
  byte_verification_only=True,conservative_complete_stage_upper_bytes=upper,source_limit_bytes=LIMIT,own_peak_bytes=peak,operations=m['operations'],authority=m['authority'],all_shells_collected=True))
 print(json.dumps(dict(passed=True,verification=vp,checked_pins=len(m['source_pins']|m['local_pins']),conservative_complete_stage_upper_bytes=upper,peak=peak)))
if __name__=='__main__':
 try:check()if sys.argv[1:]==['--check']else main()
 except Exception as exc:
  n='verification-failure.json'if sys.argv[1:]==['--check']else'review-failure.json'
  if not(OUT/n).exists():write(n,dict(type=type(exc).__name__,detail=str(exc),reads=reads,peak=peak,author_sources_unchanged=True,no_PE_or_scanner_or_parser_execution=True))
  raise
