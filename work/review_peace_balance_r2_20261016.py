"""Independent five-business-source R2 retained crosswalk audit; no target/tool run."""
import ctypes,hashlib,json,re,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
B='work/reports/peace-balance-field-crosswalk-20261016-r2/'
R1='work/reports/peace-balance-field-crosswalk-20261016-r1/'
O='work/reports/peace-balance-field-crosswalk-independent-20261016-r2/'
OUT=ROOT/O;LIMIT=12*1024*1024;FILE=4*1024*1024;MEM=768*1024*1024
CACHE=dict(bytes=858013,sha256='04214eab91f04febeb25e7713c56fb30ebe1defd00e60e0a96ddf15f8fb2a0c1')
AP='work/reports/diplomacy-corrective-20261014/runtime-file-audit.json'
NP='work/reports/native-pair29-favor-effects-1375.json'
WR='work/reports/peace-balance-field-crosswalk-independent-review-20261016-r1/'
WITNESS={WR+'findings.json':dict(bytes=6145,sha256='380397c058e3fdbc77ec537f8766766550bc4df10dd25fcde9a72e6539b924ae'),
 WR+'manifest.json':dict(bytes=5330,sha256='f55ff73a29b7dc10135cd6672bb44e921797815021ab251e49cd70b1560f1490')}
GAME='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
reads=[];peak=0
class PMC(ctypes.Structure):
 _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(x,ctypes.c_size_t)for x in('pw','w','pp','p','pn','n','pf','ppf','private')]
k=ctypes.WinDLL('kernel32',use_last_error=True);k.GetCurrentProcess.restype=ctypes.c_void_p;p=ctypes.WinDLL('psapi',use_last_error=True)
def guard():
 global peak
 a=PMC();a.cb=ctypes.sizeof(a);assert p.GetProcessMemoryInfo(ctypes.c_void_p(k.GetCurrentProcess()),ctypes.byref(a),a.cb)
 peak=max(peak,a.pw,a.ppf,a.private);assert peak<MEM
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
def write(name,obj):
 r=(json.dumps(obj,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode();assert len(r)<=FILE
 with(OUT/name).open('xb')as f:f.write(r)
 return pin(r)
def pointer(v,s):
 assert s.startswith('/')
 for token in s.split('/')[1:]:
  token=token.replace('~1','/').replace('~0','~');v=v[int(token)]if type(v)is list else v[token]
 return v
def main():
 cache=decode(read(O+'retained-files.json',CACHE));files=cache['files'];docs={}
 for path,e in files.items():
  r=e['text'].encode('utf-8');assert pin(r)=={x:e[x]for x in('bytes','sha256')}
  if path.endswith('.json'):docs[path]=decode(r)
 for path,q in WITNESS.items():
  r=read(path,q);files[path]=dict(**q,text=r.decode('utf-8'));docs[path]=decode(r)
 def pn(path):return {x:files[path][x]for x in('bytes','sha256')}
 def obj(n):return docs[B+n]
 m=obj('manifest.json');c=obj('crosswalk.json');s=obj('selected-evidence.json');v=obj('verification.json');delivery=obj('delivery.json')
 assert len(m['source_pins'])==m['source_count']==5 and len(m['pins'])==11 and len(files)==16
 assert set(m['source_pins'])=={R1+'manifest.json',R1+'crosswalk.json',R1+'selected-evidence.json',AP,NP}
 assert m['pins']==m['source_pins']|m['local_source_pins']|m['output_pins']and len(m['local_source_pins'])==len(m['output_pins'])==3
 assert all(pn(path)==q for path,q in m['pins'].items())and all(pn(B+name)==q for name,q in delivery['pins'].items())
 assert s['source_pins']==m['source_pins']and c['selected_evidence_pin']==pn(B+'selected-evidence.json')
 assert all(c['base_r1_pins'][name]==pn(R1+name)for name in('manifest.json','crosswalk.json','selected-evidence.json'))
 assert c['new_source_pins']=={AP:pn(AP),NP:pn(NP)}and m['new_source_count']==2
 base=docs[R1+'crosswalk.json'];be=docs[R1+'selected-evidence.json'];bm=docs[R1+'manifest.json']
 accepted=docs[WR+'findings.json'];assert accepted['sealed']is True and accepted['passed']is True and accepted['blocking_findings']==[]
 assert accepted['subject_manifest']==pn(R1+'manifest.json')and accepted['subject_crosswalk']==pn(R1+'crosswalk.json')and accepted['subject_selected_evidence']==pn(R1+'selected-evidence.json')
 assert docs[WR+'manifest.json']['subject_manifest']==pn(R1+'manifest.json')
 assert bm['output_pins'][R1+'crosswalk.json']==pn(R1+'crosswalk.json')and bm['output_pins'][R1+'selected-evidence.json']==pn(R1+'selected-evidence.json')
 assert s['r1_conditional_bridge']==base['conditional_crosswalk']and s['r1_contract_fields']==be['R60_audited_contract_fields']
 assert s['r1_conditional_bridge']['unconditional_runtime_identity']is False and s['r1_conditional_bridge']['unit_conversion_factor']is None
 assert s['r1_conditional_bridge']['final_settlement_delta_formula']is None
 refs=base['unit_and_provenance']['frozen_profile_upstream_references_not_opened'];assert set(refs)=={AP,NP}
 assert all({x:refs[path][x]for x in('bytes','sha256')}==pn(path)for path in refs)
 # Retained request/session association, not a replay/authentication of raw event files.
 audit=docs[AP];native=docs[NP];assert audit['game_sha256']==native['game_sha256']==c['game_sha256']==GAME
 assert audit['source_pins'][NP]==pn(NP)
 assert [i for i,a in enumerate(audit['actions'])if a['command']['action']=='trade_favors_for_gold']==[0]
 action=audit['actions'][0];expected_command=dict(action='trade_favors_for_gold',actor='FRA',target='SCO',request_id='tag31-corrective-20261014-1-trade_favors_for_gold')
 assert action['command']==expected_command and action['sequence']==1 and action['state']=='dispatched'and action['selected_effect_observed']is True
 assert action['strict_clean_rejection']is False and action['retry_forbidden']is True and action['current_legality_proven_for_a_future_attempt']is False
 identity=audit['identity'];assert identity['pid']==19876 and identity['creation']=='01dd5b2fd032fd53'and identity['session']=='3ea93e5210cf4f96aaefc00ac3e97535'
 sel=s['selected_audit'];assert sel['identity']==identity and sel['action']==action and sel['action_pointer']=='/actions/0'
 for key in('schema','game_sha256','audit_sha256','same_date_raw','same_player_handle','all_ownership_closed','limitations'):assert sel[key]==audit[key]
 assert sel['original_command_keys']==sorted(action['command'])and sel['selected_effect_keys']==sorted(action['selected_effect'])
 assert sel['new_runtime_replay']is False and sel['raw_event_request_baseline_files_opened']is False
 effect=action['selected_effect'];assert effect['field']=='treasury_milli'
 FRA=effect['FRA_after']-effect['FRA_before'];SCO=effect['SCO_after']-effect['SCO_before']
 assert(effect['FRA_before'],effect['FRA_after'],effect['SCO_before'],effect['SCO_after'])==(901548905,902006641,99317142,98859406)
 assert FRA==effect['FRA_delta']==457736 and SCO==effect['SCO_delta']==-457736
 before=effect['FRA_before']+effect['SCO_before'];after=effect['FRA_after']+effect['SCO_after'];assert before==after==1000866047
 assert effect['selected_two_country_total_before']==effect['selected_two_country_total_after']==before and effect['selected_two_country_total_conserved']is True
 assert s['arithmetic_replay']==dict(FRA_delta=FRA,SCO_delta=SCO,before_total=before,after_total=after)
 obs=c['observations'];assert obs[0]['raw_before_after']==effect and obs[0]['amount_in_command']is False and obs[0]['displayed_currency_in_receipt']is False
 assert obs[0]['both_complete_country_handles_in_gold_action']is False
 assert set(action['command'])=={'action','actor','request_id','target'}
 assert not any(x in action['command']for x in('amount','display','actor_handle','target_handle'))
 assert audit['saved_state_verified']is False and audit['cold_reload_verified']is False and action['saved_state_verified']is False
 # 74 selected rows are exact copies of the fixed 820-row text directory, not new disassembly.
 assert native['vtable_effects']['gold']==s['selected_gold_index_metadata']['value']=='0x4f40a0'
 assert s['selected_gold_index_metadata']['raw_vtable_slots_replayed']is False
 rows=native['functions']['0x4f40a0']['instructions'];assert len(rows)==s['gold_body_retained_rows_total']==820
 by={int(r['rva'],16):r for r in rows};indices=sorted(set(range(0,11))|set(range(275,297))|set(range(489,530)))
 assert len(indices)==len(s['selected_rows'])==74
 rawbytes=0
 for i,selected in zip(indices,s['selected_rows'],strict=True):
  original=rows[i];assert selected==dict(json_pointer='/functions/0x4f40a0/instructions/'+str(i),index=i,**original)
  assert pointer(native,selected['json_pointer'])==original;rawbytes+=len(bytes.fromhex(original['bytes']))
 for interval in(range(0,11),range(275,297),range(489,530)):
  vals=list(interval)
  for prev,nxt in zip(vals,vals[1:]):assert int(rows[prev]['rva'],16)+len(bytes.fromhex(rows[prev]['bytes']))==int(rows[nxt]['rva'],16)
 # Independent raw width and relative-call replay for the three amount uses.
 expected_calls={0x4f4560:0x4f3fe0,0x4f4599:0x1703850,0x4f4957:0xc9cc0,0x4f4976:0xa658d0,0x4f49ad:0x3387f0,0x4f49e4:0x338540}
 rawcalls=[]
 for at,target in expected_calls.items():
  rr=bytes.fromhex(by[at]['bytes']);assert rr[0]==0xe8 and len(rr)==5
  delta=int.from_bytes(rr[1:],'little',signed=True);assert at+5+delta==target
  rawcalls.append(dict(site=hex(at),raw=rr.hex(),signed_rel32=delta,target=hex(target),followed=False))
 assert s['raw_arithmetic'][:6]==rawcalls
 imul=bytes.fromhex(by[0x4f495c]['bytes']);assert imul.hex()=='690d8aaae401e8030000'
 disp=struct.unpack('<i',imul[2:6])[0];imm=struct.unpack('<i',imul[6:10])[0]
 assert 0x4f495c+10+disp==0x233f3f0 and imm==1000 and imul[1]==0x0d
 assert s['raw_arithmetic'][6]==dict(site='0x4f495c',raw=imul.hex(),RIP_source='0x233f3f0',operand_width_bits=32,signed_immediate=1000,destination='ECX',module_value_read=False)
 assert s['thousand_operand_rows_in_this_gold_body']==[dict(index=503,**{k:by[0x4f495c][k]for k in('rva','bytes','instruction')})]
 assert [(i,r['rva'])for i,r in enumerate(rows)if '0x3e8'in r['instruction']]==[(503,'0x4f495c')]
 expected_raw={0x4f40bc:'4c8be9',0x4f4556:'488d95a0000000',0x4f455d:'498bcd',0x4f4565:'8b9da0000000',
  0x4f456b:'899da0000000',0x4f458e:'488d95a0000000',0x4f4595:'488d4d20',0x4f4966:'898da0000000',
  0x4f496c:'488d95a0000000',0x4f4973:'488bc8',0x4f4995:'899da0000000',0x4f49cc:'899da0000000',
  0x4f499b:'4533c9',0x4f499e:'4c8d85a0000000',0x4f49a5:'418d5111',0x4f49d2:'4533c9',0x4f49d5:'4c8d85a0000000',0x4f49dc:'418d510a'}
 assert all(by[at]['bytes']==raw for at,raw in expected_raw.items())
 # DB globals are reloaded; only signed16 slots are extracted, not full handles.
 rip=[]
 for at in(0x4f492b,0x4f497f,0x4f49b6):
  rr=bytes.fromhex(by[at]['bytes']);assert rr[:3]==bytes.fromhex('488b05')and len(rr)==7
  target=at+7+struct.unpack('<i',rr[3:])[0];assert target==0x233d8d0;rip.append(dict(site=hex(at),raw=rr.hex(),RIP_global=hex(target)))
 for at in(0x4f493a,0x4f498e,0x4f49c5):assert by[at]['bytes']=='488b8018010000'
 for at in(0x4f4936,0x4f498a,0x4f49c1):assert by[at]['bytes']=='480fbfc9'
 assert by[0x4f497b]['bytes']=='498b4d20'and by[0x4f49b2]['bytes']=='498b4d10'
 assert by[0x4f4986]['bytes']==by[0x4f49bd]['bytes']=='48c1e920'
 # There is no explicit local EBX assignment between selected load and wrappers
 # in retained text. This does not recover any external callee's preservation.
 bxtext=[dict(index=i,**r)for i,r in enumerate(rows)if re.search(r'\b(?:rbx|ebx|bx|bl|bh)\b',r['instruction'])and 278<=i<=529]
 assert [x['index']for x in bxtext]==[278,279,513,524]
 assert all(x['bytes']=='899da0000000'for x in bxtext[1:])
 assert s['limited_helper_body_absence']['explicit_function_keys']==list(native['functions'])
 assert set(native['functions'])=={'0x4f40a0','0x4f6790','0x4f8af0','0x4fd220','0x4feaf0'}
 assert s['limited_helper_body_absence']['absent_selected_helpers']==['0x4f3fe0','0x1703850','0xa658d0']and s['limited_helper_body_absence']['no_global_absence_claim']is True
 assert c['answer']['raw_to_display_scale']is None and c['answer']['peace_component30_or_BD4_scale']is None
 assert c['source_scope']==dict(base_files=3,new_files=2,recursive_closure=False,gold_rows_total=820,selected_row_count=74,new_decoding=0,
  scan_boundary='Only selected old JSON gold instruction text for0x3e8; no binary or repository scan.')
 assert c['unchanged']==dict(r1_files_modified=False,accepted_effects=48,persistence=44,repair_candidates=42,stable_profiles=15,new_runtime_profiles=0,new_native_or_request_calls=0)
 for j in(m,c,s,v,delivery):assert all(x is False for x in j['authority'].values())
 for o in obs:
  assert o['source']in(AP,NP);pointer(docs[o['source']],o['json_pointer'])
 assert v['passed']is True and v['sealed']is True and v['manifest_pin']==pn(B+'manifest.json')and v['flat_pin_count']==11
 assert len(v['source_file_reads'])==25
 for e in v['source_file_reads']:assert e['bytes']==pn(e['path'])['bytes']
 before={e['path']:e['bytes']for e in v['source_file_reads']if e['phase']in('base_before','new_source_before')}
 after={e['path']:e['bytes']for e in v['source_file_reads']if e['phase']=='source_after'}
 assert before==after=={path:q['bytes']for path,q in m['source_pins'].items()}
 assert sum(x['bytes']for x in v['source_file_reads'])==v['measured_file_bytes']==2108707
 assert v['combined_upper']==2108707+4194304==6303011==delivery['read_upper']<LIMIT
 assert v['hard_Job']is False and v['peak_committed_self_observed']==13344768
 for path,e in files.items():read(path,{x:e[x]for x in('bytes','sha256')})
 upper=cache['source_bytes']+3*CACHE['bytes']+sum(q['bytes']for q in WITNESS.values())+512*1024+sum(x['bytes']for x in reads)+1024*1024;assert upper<LIMIT
 ops={x:0 for x in('PE_stat_open','engine_stat_open','decoder','author_builder_or_old_program_execution','CLI','tests','runtime_query','game_process','native_calls','requests','new_upstream_business_source','callee_body_or_literal_follow','raw_request_event_baseline_reopen')}
 authority={x:False for x in c['authority']};authority.update(inputs_authenticated=False,raw_request_runtime_reauthenticated=False,new_native_or_effect_authorized=False)
 model=dict(historical_request='Exact frozen audit action0/requestID/sequence1 and PID19876/creation/session retained. Only that audited JSON is replayed; no raw request/event/baseline authentication, current PID/epoch or new dispatch.',
  raw_effect='FRA901548905->902006641 +457736; SCO99317142->98859406 -457736; selectedsum1000866047 conserved. Raw signed32 field labeltreasury_milli does not establish displayunit, EBXruntimevalue, completeworldconservation or fresh causalproof.',
  fresh_EBX='4f3fe0 receives currentR13 and &RBP+A0; 4f4565 reads freshDWORDlocalA0 intoEBX. Callee body absent here, so initialization/formula/unit unknown. RAX is not the scalar input.',
  multiply='IMUL32 ECX,DWORD[module233f3f0],1000 ->localA0 ->a658d0 withRCX=postc9cc0RAX andRDX=&A0. At4f4995 localA0 is overwritten byEBX before3387f0, and4f49cc repeatsEBX before338540. This product is not the syntactic wrapperDWORD input.',
  wrappers='Currentaction+20/+10 QWORDs yield signed16highslots, freshDB233d8d0/table118 receiver loads. R8=&localA0,R9D0,EDX17/10. Slots do not authenticate fullcountryhandles/roles; normalnonvolatile and root/object premises remainconditional.',
  formatter='1703850 receives address ofEBXcopy and distinctlocalbuffer; nearbybyte scan/copy shape is a formattercandidateonly. No callee/literal/displaytext or /1000proof.',
  peace='AcceptedR1 conditionalrawBB0 correspondence and separateBD4 field retained; no favorEBX-to-peacecomponent30/BD4 mapping, numericunits, fullsettlement or neweffect.')
 replay=write('retained-replay.json',dict(schema='EU4-BALANCE-R2-INDEPENDENT-REPLAY/1',sealed=True,passed=True,
  business_sources_exactly_five=True,source_business_pins=m['source_pins'],optional_R1_review_witness_pins=WITNESS,
  historical_command=expected_command,historical_identity=identity,raw_effect=effect,selected_rows=74,selected_raw_bytes=rawbytes,
  selected_indices=indices,raw_calls=rawcalls,IMUL=dict(site='0x4f495c',raw=imul.hex(),operand_bits=32,source_global='0x233f3f0',immediate=1000,destination='ECX'),
  fresh_DB_RIP_references=rip,explicit_EBX_text_mentions=bxtext,no_callee_or_new_source_read=True,machine_contract=model,sourcepins_current_prepost_equal=True))
 findings=write('findings.json',dict(schema='EU4-BALANCE-CROSSWALK-R2-INDEPENDENT-REVIEW/1',sealed=True,passed=True,blocking_findings=[],
  subject_manifest=pn(B+'manifest.json'),subject_crosswalk=pn(B+'crosswalk.json'),subject_selected_evidence=pn(B+'selected-evidence.json'),
  subject_verification=pn(B+'verification.json'),subject_delivery=pn(B+'delivery.json'),retained_replay=replay,
  reviewer_role=dict(R1_and_R2_author='diplomacy_static',R1_full_independent_reviewer='validation_audit',R2_reviewer_is_not_author=True,
   R1_review_metadata_only=WITNESS,R60_is_accepted_contract_witness_not_raw_replayed_here=True),
  checks=dict(author_flat_pins=11,business_source_count=5,old_base_sources=3,new_business_sources=2,explicit_review_witness_files=2,current_flat_files=16,
   retained_original_request_session_exact=True,selected_raw_delta_and_conservation=True,amount_or_display_calibration_present=False,both_gold_action_fullhandles_present=False,
   selected74rows_exact=True,selected_raw_bytes=rawbytes,selected6CALLsignedrel32_exact=True,IMUL32_RIP_and1000_exact=True,
   EBX_local_overwrites_before_both_wrappers=True,fresh_DB_signed16_slot_paths_exact=True,R1_conditional_bridge_unchanged=True,
   formatter_and_amount_source_bodies_unfollowed=True,all_current_flat_prepost_equal=True,no_author_change_required=True),
  machine_contract=model,precision_notes=[
   'This review uses exactly the five business-source files listed by R2: three R1 files and two additional retained JSONs. Only Val R1findings/manifest were additionally read as explicitly permitted metadata witnesses; none of their upstream graph or original R1 eight sources were opened.',
   'Historical audit contains exact requestID/action/roles/sequence and PID/creation/session. The actual request/events/baseline and two complete countryhandles were not reopened. This is a retained audit association, not new runtime identity, atomicity or causal reauthentication.',
   'Raw FRA/SCO deltas are exactly+457736/-457736 with selectedsum conserved. No command amount/display amount or two full handles exist in that gold-action record. Historical selectedeffect is not counted again, no dispatch/retry is allowed, and no EBX=457736 equality is asserted.',
   '4f4565 readsDWORDlocalA0 after4f3fe0. The body is absent only from this selected five-function directory; callee initialization/formula/unit remains unknown. Numeric action labels do not supply this missing contract.',
   'The sole visible0x3e8 text operand in the retained goldbody is IMUL32 of a moduleDWORD intoECX. That product is passed to anotherhelper and overwritten withEBX before the two resourcewrappers. Its unrelated provenance cannot establish gold/peace/display units.',
   'Explicit localEBX copies and signed16slot receiver paths are machine facts when reached. Continuation reachability, normalcallee/nonvolatile preservation, fullhandles/currentDB/root/object equality, aliases and pointed-copy mutation remain necessary conditions. No fullfunction/pure or finalsettlement result follows.',
   '1703850 is only a formattercandidate edge with a localbuffer and followingbyte-shaped operations. No formatterbody/literal/text/unit conversion was followed or inferred.',
   'R1 BB0 rawfield correspondence remains conditional, BD4 remains a separateDWORD. R60 is acceptedcontractwitness here, not a new raw replay. FavorEBX has no closed mapping to peacecomponent30 orBD4 or completepeacepayment.',
   'The additional read of ValR1reviewmetadata does not raise new business-source count beyondfive. Author explicitread2,108,707 plus4MiB manualallowance6,303,011 is boundedselected accounting, not allOS/loaderIO; peak13,344,768B is authorprocess witness only.',
   '48accepted/44persistence/42repair/15stableprofiles remain unchanged; newruntimeprofile/effect/native/request counts are zero. All execution/payment/unit/direction/lease/atomic/persistence/retry permissions remainfalse.',
   'Own reviewR1 compared the selected four-field thousand-operand projection against the entire source row, whose additional RIP metadata was deliberately omitted by that projection. ExactR1source/failure preserved; R2 compares the precise four retained fields while all74 fullselected rows still match the original. No author/source/business changes or oldprogram rerun; failedcache and two witness reads charged.'
  ],author_resource_witness=dict(measured_file_bytes=2108707,manual_allowance=4194304,combined_upper=6303011,stage_limit=LIMIT,
   author_peak_bytes=13344768,hard_Job=False,all_OS_IO_claim=False),
  independent_resources=dict(intake_source_bytes=cache['source_bytes'],prior_two_cache_inspection_bytes=2*CACHE['bytes'],prior_failed_review_bytes=CACHE['bytes']+sum(q['bytes']for q in WITNESS.values()),manual_smallinspection_allowance=512*1024,
   current_cache_witness_and_postguard_bytes=sum(x['bytes']for x in reads),own_sealing_reserve=1024*1024,listed_analysis_upper_bytes=upper,
   stage_limit=LIMIT,ordinary_file_limit=FILE,own_peak_bytes=peak,memory_limit=MEM),
  operations=ops,authority=authority,author_files_modified=False,all_shells_collected=True,next_scope_auto_authorized=False))
 report=b'Peace balance R2 retained audit passed:five business sources/11authorpins plus two permitted R1review metadata witnesses. Exact historicalrequest/session and rawFRA/SCO deltas conserve selectedsum. FreshDWORD->EBX->two wrappercopy paths do not establish units; moduleIMUL1000 goes to anotherhelper and is overwritten. Amount/display/fullhandles/formatter/peaceunit bridge remainunknown. NoPE/decoder/program/tests/game/native/request operations.\n'
 with(OUT/'report.md').open('xb')as z:z.write(report)
 local={O+n:pin((OUT/n).read_bytes())for n in('retained-files.json','retained-replay.json','findings.json','report.md','reviewer-r1-source.py','review-failure.json')}
 for path in('work/retain_peace_balance_r2_review_20261016.py','work/review_peace_balance_r2_20261016.py'):local[path]=pin((ROOT/path).read_bytes())
 mp=write('manifest.json',dict(schema='EU4-BALANCE-CROSSWALK-R2-INDEPENDENT-MANIFEST/1',sealed=True,source_pins={path:pn(path)for path in files},
  business_source_pins=m['source_pins'],accepted_R1_review_witness_pins=WITNESS,local_pins=local,findings=findings,operations=ops,authority=authority))
 print(json.dumps(dict(passed=True,findings=findings,manifest=mp,replay=replay,analysis_upper=upper,peak=peak,all_shells_collected=True)))
def check():
 m=decode(read(O+'manifest.json'))
 for path,q in(m['source_pins']|m['local_pins']).items():read(path,q)
 f=decode(read(O+'findings.json',m['local_pins'][O+'findings.json']))
 upper=f['independent_resources']['listed_analysis_upper_bytes']+sum(x['bytes']for x in reads);assert upper<LIMIT
 vp=write('verification.json',dict(schema='EU4-BALANCE-R2-INDEPENDENT-VERIFICATION/1',sealed=True,passed=True,pins_checked=len(m['source_pins']|m['local_pins']),
  business_sources=5,R1_review_witnesses=2,sourcepins_current_equal=True,complete_stage_upper_bytes=upper,stage_limit=LIMIT,own_peak_bytes=peak,
  operations=m['operations'],authority=m['authority'],all_shells_collected=True))
 print(json.dumps(dict(passed=True,verification=vp,pins=len(m['source_pins']|m['local_pins']),complete_upper=upper,peak=peak)))
if __name__=='__main__':
 try:check()if sys.argv[1:]==['--check']else main()
 except BaseException as exc:
  n='verification-failure.json'if sys.argv[1:]==['--check']else'review-r2-failure.json'
  if not(OUT/n).exists():write(n,dict(type=type(exc).__name__,detail=str(exc),reads=reads,peak=peak,author_sources_unchanged=True,no_author_program_PE_decoder_game_native_or_sixth_business_source=True))
  raise
