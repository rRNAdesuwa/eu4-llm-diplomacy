"""Author proposal only for offline lookup v6. No candidate/CLI/target execution."""
import ast
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import sys
import traceback
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/reports/war-peace-api-lookup-v6-plan-20261016-r1'
V5='work/candidates/war-peace-api-lookup-1375-v5/'
FIXED={
 V5+'index.json':(185792,'a8b70f547513def34f88c1dd19e73e573c63fe209aeced61f397db8b22556e6c'),
 V5+'data-manifest.json':(14774,'39efa19ba26675647379f6be182b26be727762d5eaf906f0be822b7ca0dba69c'),
 V5+'source-manifest.json':(19355,'1c1b0acd82b7ad100c8e6085deb5e994b92defd8212bf61d2a3a5db2b6cdf27f'),
 V5+'war_peace_lookup.py':(3602,'653530b8d60e789f33786819e43de7d057142de5c75c6841469d2802928a9da6'),
 V5+'query_engine.py':(16583,'ea030ce19461b2e414e0cdbc42f4933551fa9e654f7a7a43db948670b27fa466'),
 V5+'REVIEW_STATUS.md':(1453,'6f84bb3fdb87d6435a86762abf3aa2d74ba0260af094c3dbd4b653303a9218fd'),
 'work/reports/war-peace-api-lookup-v5-independent-review-20261016-r1/findings.json':(5460,'e7dc234280f874769f5965d22fa8ccac416ee9cf3dd4250c1c71e09e3f17531c'),
 'work/reports/war-peace-api-lookup-v5-independent-review-20261016-r1/manifest.json':(99749,'02197b9170d47b53a13ab18802103d5a2cc1a056c340c805a072c5f6945e1eef'),
 'work/reports/war-peace-api-20261016-r75-null-successor-fragment/actual-manifest.json':(16739,'f05a565e8fdb8c2006cd9b2f94e77fef5a86c1c7fbf8d5bcd7e8c91f22c2eab9'),
 'work/reports/war-peace-api-20261016-r75-null-successor-fragment/actual-contract.json':(6999,'b841344c4c286f1cd7d5bfe7c5edea930913a9e9191c5731bb03a6f1b62c19ea'),
 'work/reports/war-peace-api-20261016-r75-null-successor-fragment/actual-selected-evidence.json':(10173,'5ae4eb40dc81a08ff3c328d8d436bfdee72e26b0211d2cbab0fe7fbf317e9efb'),
 'work/reports/war-peace-api-20261016-r75-actual-independent-review-r2/findings.json':(6218,'e3d54d50cd97281872f32b2e3b7648d9b2ca3e1d8735ed010a63be0c7db27e53'),
 'work/reports/war-peace-api-20261016-r75-actual-independent-review-r2/manifest.json':(12383,'6fe456906b3b55738657ac306a3a43722ee45533e38d8864f63be651f1a004f0'),
 'work/reports/war-peace-api-20261016-r77-fragment-composition/manifest.json':(6577,'ae8c40082da1c9a0fab20c36a3b54360fdd554891a972da2c5fe7587446029f4'),
 'work/reports/war-peace-api-20261016-r77-fragment-composition/contract.json':(16978,'93911bd7dcaa02fc6c4c9ab9cb0084a1e06ea070f7517d534176154eef78f53c'),
 'work/reports/war-peace-api-20261016-r77-fragment-composition/raw-composition.json':(88665,'3bc59904e69c2cdbb4002181b7ab143fa0bfcc0f5e296f437e943e198d9afe2f'),
 'work/reports/war-peace-api-20261016-r77-composition-independent-review/findings.json':(20892,'83a284955c31d19cbc4feaf54514d5e617e560a5acb4b99d282557ffa6ed9342'),
 'work/reports/war-peace-api-20261016-r77-composition-independent-review/manifest.json':(11318,'996ed219e20c130e4dda798ba309d68bb74c60d547a3c5bb8e06adaa7f42091a'),
 'work/reports/war-peace-api-20261016-r79-null-selector-callee/actual-manifest.json':(15510,'7ca8e3bc5f0280b5a908ad624e03be91d2be85f2465f7da5ef98fee95b264523'),
 'work/reports/war-peace-api-20261016-r79-null-selector-callee/actual-contract.json':(3281,'52d792d5a5e5ce865adf0eca6959850cf6c8f37cc6df15f6f44354941f8f1fda'),
 'work/reports/war-peace-api-20261016-r79-null-selector-callee/actual-selected-evidence.json':(10307,'ca882c2fbb33c3e76013a5c8e7d4528d3f83783875315b6313b31f141cf2c240'),
 'work/reports/war-peace-api-20261016-r79-actual-independent-review/findings.json':(9030,'8d2277950f717a9d5769bb20c8bb0fe9ce699180247c51dc63b8bccd24fbdf9b'),
 'work/reports/war-peace-api-20261016-r79-actual-independent-review/manifest.json':(11402,'aaca888b33d4cce78f1781448c76526b7a034be82fb0aea152ad1d972e009211'),
}
READS=[];PEAK=0
def need(ok,msg):
 if not ok:raise AssertionError(msg)
def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def memory():
 global PEAK
 class P(ctypes.Structure):
  _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(n,ctypes.c_size_t)for n in(
   'peak_working','working','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile','private')]
 p=P();p.cb=ctypes.sizeof(p);k=ctypes.WinDLL('kernel32',use_last_error=True);k.GetCurrentProcess.restype=wintypes.HANDLE
 a=ctypes.WinDLL('psapi',use_last_error=True);a.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(P),wintypes.DWORD]
 need(a.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(p),p.cb),'ownmemory')
 PEAK=max(PEAK,p.private,p.peak_pagefile);need(0<PEAK<=768*1024*1024 and PEAK<1024*1024*1024,'ownmemoryguard')
 need(sum(e['bytes']for e in READS)+3*1024*1024<=8*1024*1024,'proposal8MiB includingmanual/seal')
def read(path,want=None,phase='before'):
 need((path.startswith('work/reports/')or path.startswith(V5)or path=='work/plan_lookup_v6_20261016.py')and 'work/deps/'not in path,'admittedflat only')
 need(not path.lower().endswith(('.exe','.dll','.pyd')),'noPEdecoderbody')
 p=ROOT/path;need(p.stat().st_size<=4*1024*1024,'ordinary4MiB');raw=p.read_bytes()
 READS.append({'phase':phase,'path':path,'bytes':len(raw)});memory()
 if want is not None:need(pin(raw)==want,'pin '+path)
 return raw
def save(name,obj):
 raw=(json.dumps(obj,indent=2,ensure_ascii=True)+'\n').encode('utf8')
 with (OUT/name).open('xb')as f:f.write(raw)
 return pin(raw)
def pointer(doc,path):
 need(path.startswith('/'),'nonempty fixedJSONpointer')
 value=doc
 for token in path[1:].split('/'):
  token=token.replace('~1','/').replace('~0','~')
  if isinstance(value,list):value=value[int(token)]
  else:value=value[token]
 return value
def stripped(value):return {k:value[k]for k in('bytes','sha256')}
def canonical(value):return json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode('utf8')

def main():
 OUT.mkdir(exist_ok=False)
 raw={path:read(path,{'bytes':v[0],'sha256':v[1]})for path,v in FIXED.items()}
 pins={path:pin(v)for path,v in raw.items()}
 docs={path:json.loads(v)for path,v in raw.items()if path.endswith('.json')}
 index=docs[V5+'index.json'];data=docs[V5+'data-manifest.json']
 need(len(index['entries'])==59 and len(data['sources'])==74,'v5current59/74')
 need(data['index']==pins[V5+'index.json'],'olddataindexpin')
 accepted=docs['work/reports/war-peace-api-lookup-v5-independent-review-20261016-r1/findings.json']
 need(accepted['sealed']is True and accepted['passed']is True and accepted['blocking_findings']==[],'v5acceptedfull')
 for key,name in [('subject_data_manifest','data-manifest.json'),('subject_index','index.json'),('subject_query_engine','query_engine.py'),('subject_source_manifest','source-manifest.json'),('subject_wrapper','war_peace_lookup.py')]:
  need(accepted[key]==pins[V5+name],'v5acceptedcore '+key)
 families={};groups={}
 for report in ('R75','R77','R79'):
  needle={'R75':'r75-','R77':'r77-','R79':'r79-'}[report]
  selected=[path for path in FIXED if needle in path]
  need(len(selected)==5,'exact5directJSON '+report)
  groups[report]=selected
  reviewpath=next(path for path in selected if path.endswith('/findings.json'))
  review=docs[reviewpath];need(review['sealed']is True and review['passed']is True and review['blocking_findings']==[],report+'fullaccepted')
  families[report]={'status':'accepted_full_file_review','source_count':5,'sources':selected,'full_review_pin':pins[reviewpath]}
 r75=groups['R75'];r77=groups['R77'];r79=groups['R79']
 r75review=docs[next(p for p in r75 if p.endswith('/findings.json'))]
 need(r75review['subject_actual_manifest']==pins[r75[0]] and r75review['subject_contract_pin']==pins[r75[1]],'R75subjectbindings')
 r77review=docs[next(p for p in r77 if p.endswith('/findings.json'))]
 need(r77review['subject_manifest']==pins[r77[0]]and r77review['subject_contract']==pins[r77[1]]and r77review['subject_raw_composition']==pins[r77[2]],'R77subjectbindings')
 r79review=docs[next(p for p in r79 if p.endswith('/findings.json'))]
 need(stripped(r79review['subject_actual_manifest'])==pins[r79[0]]and stripped(r79review['subject_contract_pin'])==pins[r79[1]]
  and stripped(r79review['subject_selected_pin'])==pins[r79[2]],'R79subjectbindings')
 need(docs[r79[1]]['owned_code_pin']is None and docs[r79[1]]['analysis']is None and docs[r79[1]]['decoder_loaded']is False,'R79onlyunknownmetadatafence')
 refspec={
  r75[0]:['/capture_pin','/contract_pin','/owned_code_pin'],
  r75[1]:['/return_register_contract','/stack_contract','/inherited_state','/unknowns','/local_selected_CFG'],
  r75[2]:['/raw_code','/analysis/instructions','/metadata'],
  r75[3]:['/passed','/subject_actual_manifest','/subject_contract_pin','/precision_notes'],r75[4]:['/source_pins'],
  r77[0]:['/source_pins','/files'],r77[1]:['/conditional_cases','/normal_conditions','/epilogue_stack_contracts','/unresolved','/historical_delta','/source_review_precision'],
  r77[2]:['/fragments','/epilogue_projections','/RET_sites','/signed_edge_replay'],
  r77[3]:['/passed','/subject_manifest','/subject_contract','/subject_raw_composition','/precision_notes'],r77[4]:['/source_pins'],
  r79[0]:['/owned_code_pin','/analysis','/decoder_loaded','/capture_pin','/contract_pin'],
  r79[1]:['/status','/selected_metadata','/next_metadata','/metadata_gap','/callee_formals_field_access_direct_writes_return_register_effects','/D_header_contents_or_callee_sideeffect_freedom'],
  r79[2]:['/selected','/next','/pdata_requests','/new_code_bytes','/analysis','/decoder_loaded'],
  r79[3]:['/passed','/subject_actual_manifest','/subject_contract_pin','/subject_selected_pin','/result','/limits'],r79[4]:['/source_pins'],
 }
 refs=[];resolved=[]
 for path,paths in refspec.items():
  for ptr in paths:
   value=pointer(docs[path],ptr)
   refs.append({'path':path,'json_pointer':ptr,**pins[path]})
   resolved.append({'path':path,'json_pointer':ptr,'value_type':type(value).__name__,'canonical_value_sha256':hashlib.sha256(canonical(value)).hexdigest()})
 need(len(set(ref['path']for ref in refs))==15,'all15directsourcesused')
 original={row['id']:row for row in index['entries']}
 generator=original['peace.generator_divisor_source'];old58={key:row for key,row in original.items()if key!='peace.generator_divisor_source'}
 need(len(old58)==58 and generator['rva']=='0x993570'and any('NULL target993658 unread' in x for x in generator['unresolved']),'historicalv5NULLunknown frozen')
 need(all(path not in data['sources']for path in refspec),'new15no old74duplicates')
 engine=raw[V5+'query_engine.py'].decode('utf8');wrapper=raw[V5+'war_peace_lookup.py'].decode('utf8')
 need('1 <= len(sources) <= 96' in engine and 'MAX_FILE = 4 * 1024 * 1024' in engine,'acceptedengine96+4M')
 need('for ref in refs:' in engine and "refs = row.get('evidence')" in engine and "used_sources == set(manifest['sources'])" in engine,'refs must attachrow.evidence')
 need('entries = copy.deepcopy(matches)' in engine and "'ea030ce19461b2e414e0cdbc42f4933551fa9e654f7a7a43db948670b27fa466'" in wrapper,'lookupshowswhole row/exactsameengine')
 old_source_bytes=sum(p['bytes']for p in data['sources'].values());added_bytes=sum(pins[path]['bytes']for path in refspec)
 r80_allowance=1024*1024;index_allowance=512*1024;data_allowance=64*1024
 perpass=old_source_bytes+added_bytes+r80_allowance+index_allowance+data_allowance
 perquery=2*perpass+3*16583+16*1024
 batch=4*perquery+8*1024*1024
 need(batch<=64*1024*1024 and perpass<=32*1024*1024,'explicitconditional fourquerybudget')
 inventory={
  'schema':'EU4-LOOKUP-V6-PLANNED-SOURCE-INVENTORY/1','sealed':True,'author_proposal_only':True,
  'old74_JSON_source_pins_unchanged':data['sources'],'old_source_bytes_metadata_sum':old_source_bytes,
  'new15_accepted_JSON_pins':{path:pins[path]for path in refspec},'new15_bytes':added_bytes,
  'report_groups':families,'current_direct_source_count_if_integrated':89,
  'future_R80_five_roles':[{'role':role,'path':None,'bytes':None,'sha256':None,'json_pointers':None,'status':'not_final_not_read_not_guessed'}
    for role in('author_actual_manifest','author_machine_contract','one_retained_JSON_carrying_owned_raw_and_rows','full_independent_findings','full_independent_manifest')],
  'future_count_after_exact5_R80_sources':94,'accepted_engine_source_cap':96,'cap_expansion_allowed':False,
  'if_R80_needs_sixth_source':'Stop and revise proposal explicitly before build; do not silently use headroom or expand engine.',
  'old74_bodies_read_or_reaudited_by_this_proposal':False,'recursive_closure_claimed':False}
 inventory_pin=save('source-inventory.json',inventory)
 ref_pin=save('reference-plan.json',{'schema':'EU4-LOOKUP-V6-FIXED-REFERENCE-PLAN/1','sealed':True,'references':refs,
  'resolved':resolved,'reference_count':len(refs),'source_count':15,'future_R80_refs':'Unresolved; derive actual schema and fixed pointers only after final/full accepted package.',
  'all_current_new_sources_referenced_in_generator_evidence_required':True})
 oldmap_pin=save('old-entry-preservation.json',{'schema':'EU4-LOOKUP-V6-OLD-ENTRY-PRESERVATION-PLAN/1','sealed':True,
  'v5_index_pin':pins[V5+'index.json'],'old58_canonical_rows':{key:{'rva':row['rva'],'canonical_sha256':hashlib.sha256(canonical(row)).hexdigest()}for key,row in old58.items()},
  'generator_base_row_canonical_sha256':hashlib.sha256(canonical(generator)).hexdigest(),'generator_base_field_names':list(generator),
  'generator_only_allowed_append_fields':['later_checked_context','historical_base_scope'],
  'generator_only_allowed_existing_field_append':'evidence; original evidence must remain an exact prefix',
  'generator_original_fields_must_equal_v5_except_evidence_append':True,'old_later_conditional_context_unchanged':True,
  'historical_NULL_unread_unresolved_text_preserved':True,'v5_files_modified':False})
 plan={
  'schema':'EU4-WAR-PEACE-LOOKUP-V6-SOURCE-SCOPE-PROPOSAL/1','sealed':True,'stage':'author_planning_not_candidate_build_or_source_ready',
  'author_role':'War authored lookupv5 and R79 source+actual; this is author planning. Root fullv5 review and Val fullR79 review are independent accepted witnesses. Fullv6 needs non-author source/data review.',
  'baseline':{'entries':59,'direct_JSON_sources':74,'index_pin':pins[V5+'index.json'],'data_manifest_pin':pins[V5+'data-manifest.json'],
   'source_manifest_pin':pins[V5+'source-manifest.json'],'wrapper_pin':pins[V5+'war_peace_lookup.py'],'engine_pin':pins[V5+'query_engine.py']},
  'planned_scope':{'old58_rows':'strict dataequal including all fields and evidence','existing_generator_id':'peace.generator_divisor_source',
   'existing_generator_rva':'0x993570','append_only_fields':['later_checked_context','historical_base_scope'],
   'evidence_append_only':'Attach all15new accepted sources through exactrefs. Keep original evidence an exact prefix. No top-level-only unreferenced supplement.',
   'base_fields_to_preserve':'summary/title/signature/unresolved/aliases/actions/ownership/flags/call_sites/oldlater_conditional_context and all other v5fields remainexact.',
   'historical_base_scope':'Explicit revision5/indexpin/cutoff. OldNULLunread sentence is a historical base claim; later_checked_context supplements that condition without overwriting v5.',
   'later_checked_context':[
    {'report':'R75','facts':'Selected16B NULL epilogue copies currentR14 toRAX before5POP+RET/48B stackreads. JE-entryRAX0 is not finalRAX.',
     'conditions':'Prior normally balanced97bd30 return, valid saved/control stack and explicit nonvolatile/alias premises.',
     'unknown':'FinalD/header/units/typed formals/lifetime/effect; no independent callable fragment.'},
    {'report':'R77','facts':'Conditional retainedR69/R71/R73/R75 composition; selected local returns and aliases are conditioned on normal unfollowed calls.',
     'conditions':'Use exact conditional_cases/normal_conditions/epilogue_stack_contracts; no unconditional wholefunction/prototype claim.',
     'unknown':'All followups/aliases/D/header/value meanings/ownership and runtime effects remain limited by preserved unresolved fields.'},
    {'report':'R79','facts':'Accepted bounded exact-entry metadata lookup returnedunknown0code:20records240B/17unique204, selected19063 ends97bd21,next19064 starts97bda0.',
     'conditions':'Only metadatafence and explicit ownedpin=null/analysis=null/decoderfalse. KnownCALL97bd30 lies in a pdata gap.',
     'unknown':'No targetcode/formals/sideeffects/returns proof, no function-absence conclusion, no independent97bd30 endpoint fromR79.'}],
   'new_entry_after_R80_full_only':{'tentative_id':'peace.generator_selector_callee','rva':'0x97bd30','kind':'function',
    'scope_kind':'known_direct_CALL_entry_bounded_prefix_not_whole_function','class_business_name_verified':False,
    'whole_function_closed':False,'complete_prototype':'unknown','units_lifetime_effect_verified':False,
    'details':'Fill only observed finalR80 machine contract. kind=function identifies known machine entry; does not assert legitimate callable Win64/C++ API.'},
   'planned_final_entry_count':60,'planned_final_JSON_sources':94,'R72_R74_type_diagnostics_or_R65_unapproved_scopes_included':False},
  'engine_wrapper_plan':{'engine_file_to_reuse':V5+'query_engine.py','engine_sha256':pins[V5+'query_engine.py']['sha256'],
   'engine_bytes_unchanged':True,'engine96cap_unchanged':True,'copy_or_new_engine_fork_planned':False,
   'wrapper_allowed_delta':['DATA_SHA new frozen data hash','tool_revision5to6 in result metadata','help revision5to6','BASE path only if needed, prefer existingv5 exactpath'],
   'wrapper_logic_AST_unchanged':['base_bytes','engine','Parser','query invocation/error/flag behavior'],
   'DATA_revision_is_not_current_process_authentication':True},
  'dependencies':{'R75':'full accepted exact5JSON pinned','R77':'full accepted exact5JSON pinned','R79':'ValfullPASS update pinned; unknownmetadatafence only',
   'R80':'Only rootplanned64B prefix atknownCALL97bd30; no mutableR80 path/schema/content read. No actual or full review yet.',
   'R80_required_before_candidate':'Explicit rootsingle scope actual, final raw/contract package, passed non-author full review, then resolve5roles paths/hash/pointers before source/data freeze.'},
  'future_verification_plan':{
   'first_queries_max':4,'first_queries':['check','catalog','lookup 0x993570','lookup 0x97bd30'],
   'each_once_only':True,'execute_now':False,'query_command_root':'future newv6 wrapper only after separate build scope authorization',
   'source_checks':['old58rows exact canonical equality','generator basefields exact exceptevidenceappend/new2keys','old74pins exactunchanged',
    '94directJSON allreferenced with valid fixedpointers','engineea030 exactunchanged','wrappernarrowASTdelta only','allauthorityfalse and R79unknown not newentry'],
   'no_new_parser_guard_fixtures_or_old_tests_required':'Parser/engineguards unchanged. Keep failedv5fixture history and its limited refusal witnesses unchanged; do not rerun them.',
   'publication_gate':'Full non-author v6 source/data/receipts review; no publictool directory or ZIP before root separately publishes.'},
  'future_budgets':{'build_plus_seal_bytes':32*1024*1024,'first_four_query_batch_bytes':64*1024*1024,'ordinary_file_bytes':4*1024*1024,
   'own_memory_software_bytes':768*1024*1024,'one_GiB_stop':True,'known74_source_metadata_bytes':old_source_bytes,'new15_source_bytes':added_bytes,
   'conditional_R80_five_total_allowance':r80_allowance,'conditional_new_index_allowance':index_allowance,'conditional_new_data_manifest_allowance':data_allowance,
   'conditional_perpass_bytes':perpass,'conditional_perquery_including_two_passes_three_enginepins_and_wrapper_allowance':perquery,
   'controller_source_receipt_allowance':8*1024*1024,'conditional_fourquery_plus_controller_upper':batch,
   'not_universal_OS_IO_bound':True,'if_future_sizes_exceed_assumptions':'Recompute and stop before build/querybudget overrun; no silent enginecap or resource limit expansion.',
   'accepted_engine32MiB_semantics':'successful graph acceptance check; an unknown/refused pass can read one next perfile-bounded source before aggregate rejection.'},
  'source_inventory_pin':inventory_pin,'reference_plan_pin':ref_pin,'old_entry_preservation_pin':oldmap_pin,
  'authority':{key:False for key in('candidate_built','queries_executed','tests_executed','native_ready','callable','sender_authorized','selected_effect_verified',
    'gameplay_effect_verified','process_authenticated','reader_adoption_allowed','world_lease','atomic_snapshot','authorizes_retry','actual_authorized')},
  'plan_is_not_full_v6_review_or_permission':True,'old_files_modified':False,'v6_candidate_created':False}
 plan_pin=save('plan.json',plan)
 for path,want in pins.items():read(path,want,'after')
 resources=save('resources.json',{'schema':'EU4-LOOKUP-V6-PROPOSAL-RESOURCES/1','sealed':True,'read_events':READS,
  'explicit_read_bytes':sum(x['bytes']for x in READS),'manual_prior_inspection_allowance':1024*1024,'ownseal_and_pincheck_reserve':2*1024*1024,
  'conservative_upper':sum(x['bytes']for x in READS)+3*1024*1024,'limit':8*1024*1024,'ordinary4MiB':True,'self_peak_private':PEAK,
  'source_prepost_pins_equal':True,'flat_files':len(pins),'recursive_closure':False,'old74bodies_read':False,
  'PE_engine_decoder_body_game_native_queries_tests_accesses':0,'Python_query_engine_source_read_only':True,'all_shells_collected':True})
 manifest_pins=dict(pins);manifest_pins['work/plan_lookup_v6_20261016.py']=pin(Path(__file__).read_bytes())
 for name,want in [('plan.json',plan_pin),('source-inventory.json',inventory_pin),('reference-plan.json',ref_pin),('old-entry-preservation.json',oldmap_pin),('resources.json',resources)]:
  manifest_pins[(OUT/name).relative_to(ROOT).as_posix()]=want
 mp=save('manifest.json',{'schema':'EU4-LOOKUP-V6-PROPOSAL-MANIFEST/1','sealed':True,'author_proposal_only':True,'source_pins':manifest_pins,
  'pin_count':len(manifest_pins),'candidate_built':False,'queries_executed':False,'native_ready':False,'actual_authorized':False})
 print(json.dumps({'plan':plan_pin,'manifest':mp,'reference_plan':ref_pin,'new_current_sources':15,'future_total_sources':94,
  'conditional_fourquery_budget':batch,'read_bytes':sum(x['bytes']for x in READS),'peak':PEAK}))
def check():
 path=(OUT/'manifest.json').relative_to(ROOT).as_posix();raw=read(path,phase='proposal_pincheck');m=json.loads(raw)
 for p,w in m['source_pins'].items():read(p,w,'proposal_pincheck')
 need(len(m['source_pins'])==m['pin_count'],'proposalpincount')
 vp=save('verification.json',{'schema':'EU4-LOOKUP-V6-PROPOSAL-VERIFICATION/1','file_only':True,'passed':True,'manifest_pin':pin(raw),
  'pins':m['pin_count'],'v6_built':False,'queries_or_tests':0,'PE_game_native_accesses':0})
 print(json.dumps({'passed':True,'verification':vp,'pins':m['pin_count']}))
if __name__=='__main__':
 try:
  if sys.argv[1:]==['--check']:check()
  else:need(sys.argv[1:]==[],'proposalonly');main()
 except BaseException:
  if OUT.exists():
   with (OUT/'failure.txt').open('x',encoding='utf8')as f:f.write(traceback.format_exc())
  raise
