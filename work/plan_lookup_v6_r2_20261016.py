"""Author proposal R2 only. Reads explicitly frozen file inputs; no CLI/candidate build."""
import ctypes
import hashlib
import json
from pathlib import Path
import sys
import traceback

ROOT=Path(__file__).resolve().parent.parent
OLD='work/reports/war-peace-api-lookup-v6-plan-20261016-r1/'
OUT=ROOT/'work/reports/war-peace-api-lookup-v6-plan-20261016-r2'
R80='work/reports/war-peace-api-20261016-r80-unregistered-call-prefix/'
R80REVIEW='work/reports/war-peace-api-20261016-r80-actual-independent-review-r3/'
LIMIT=8*1024*1024; CAP=4*1024*1024; MANUAL=1024*1024; TAIL=2*1024*1024
J=[]; C={}; P={}
AUTH={k:False for k in ('candidate_built','queries_executed','tests_executed','native_ready','callable','sender_authorized','selected_effect_verified','gameplay_effect_verified','process_authenticated','reader_adoption_allowed','world_lease','atomic_snapshot','authorizes_retry','actual_authorized')}
HARD={
 OLD+'plan.json':(8375,'2ee490e3ac1c0780666b3edf13e8aef3b959dceabd6aa8419e76ded27e410051'),
 OLD+'manifest.json':(5938,'47d6c6829378d736f39eda39c0092d01c334ca1b045848b1f793d8b61cb27628'),
 OLD+'source-inventory.json':(21390,'6b6a1e7dfba718879b36c02a2899e7b77916e5d0ae4c0760ac35991722ca3671'),
 OLD+'reference-plan.json':(31783,'9bd94d0d00c1b3c4a2dad636f8b7ba46c16e5ce9923275b8960f76d95806d9a3'),
 OLD+'old-entry-preservation.json':(10536,'a1617297a9d5733bd311a5171bbda175d5ba85a9e98a93afc342886698cafd5f'),
 R80+'actual-manifest.json':(17047,'4537f650656dab1ce8c9511f65ebe5211adc81c4f10c8a1daf8b0b47db62dc18'),
 R80+'actual-contract.json':(5247,'b73969a9eabc1c874998f38e29ea0911b050755b290c0188e9725a6563abe73c'),
 R80+'actual-selected-evidence.json':(15924,'6bd48ab81e3a493f7115d81585a6f3f4c02f926662b33b6b0cf5b2c485cb794a'),
 R80REVIEW+'findings.json':(9252,'81bb504dd809001a9a1549f094e9b9889013808607d16be7e176748ae61d7e18'),
 R80REVIEW+'manifest.json':(15918,'91ed106282413b91fbc5d34a2cd096c7f41f1569a2df4ab0bf33ffa0c571a9c4'),
}


def need(v,m):
    if not v:raise AssertionError(m)


def memory():
    class PMC(ctypes.Structure):
        _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong),('PeakWorkingSetSize',ctypes.c_size_t),('WorkingSetSize',ctypes.c_size_t),('QuotaPeakPagedPoolUsage',ctypes.c_size_t),('QuotaPagedPoolUsage',ctypes.c_size_t),('QuotaPeakNonPagedPoolUsage',ctypes.c_size_t),('QuotaNonPagedPoolUsage',ctypes.c_size_t),('PagefileUsage',ctypes.c_size_t),('PeakPagefileUsage',ctypes.c_size_t),('PrivateUsage',ctypes.c_size_t)]
    p=PMC();p.cb=ctypes.sizeof(p)
    k=ctypes.WinDLL('kernel32');k.GetCurrentProcess.restype=ctypes.c_void_p
    a=ctypes.WinDLL('psapi');a.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong]
    need(a.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(p),p.cb),'self query')
    need(p.PrivateUsage<768*1024**2 and p.PeakPagefileUsage<1024**3,'own memory limit')
    return {'private_bytes':p.PrivateUsage,'peak_pagefile_bytes':p.PeakPagefileUsage}


def digest(b):return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}


def normal(n):
    p=(ROOT/n).resolve();need(p.is_relative_to(ROOT),'project local')
    r=p.relative_to(ROOT).as_posix()
    need(not r.startswith('work/deps/') and p.name.lower()!='eu4.exe','no native engine or PE')
    return r


def read(n,phase,expected=None):
    n=normal(n);p=ROOT/n;size=p.stat().st_size
    need(size<=CAP and sum(e['bytes'] for e in J)+size+MANUAL+TAIL<=LIMIT,'preread cap/8MiB')
    memory();b=p.read_bytes();d=digest(b);J.append({'path':n,'phase':phase,**d})
    need(len(b)==size,'size stable')
    if expected is not None:need(d=={k:expected[k] for k in ('bytes','sha256')},'exact pin '+n)
    return b


def admit(n,expected):
    n=normal(n);expected={k:expected[k] for k in ('bytes','sha256')}
    if n in P:need(P[n]==expected,'pin consistency')
    else:C[n]=read(n,'before',expected);P[n]=expected


def obj(n):return json.loads(C[normal(n)])
def canon(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
def triple(n):return {'path':normal(n),**P[normal(n)]}


def save(n,x):
    b=(json.dumps(x,ensure_ascii=True,indent=2)+'\n').encode()
    with (OUT/n).open('xb') as f:f.write(b)
    return digest(b)


def pointer(d,p):
    need(p.startswith('/'),'absolute pointer')
    for key in p.split('/')[1:]:
        key=key.replace('~1','/').replace('~0','~')
        d=d[int(key)] if isinstance(d,list) else d[key]
    return d


def main():
    OUT.mkdir(exist_ok=False);before=memory()
    for n,(length,sha) in HARD.items():admit(n,{'bytes':length,'sha256':sha})
    oldplan=obj(OLD+'plan.json');oldmanifest=obj(OLD+'manifest.json');oldinventory=obj(OLD+'source-inventory.json');oldrefs=obj(OLD+'reference-plan.json');oldproof=obj(OLD+'old-entry-preservation.json')
    # Only selected v5 query files, no old74 JSON bodies or recursive history graph.
    v5pins={n:p for n,p in oldmanifest['source_pins'].items() if n.startswith('work/candidates/war-peace-api-lookup-1375-v5/')}
    needed_pins=(oldplan['baseline'][k] for k in ('index_pin','data_manifest_pin','source_manifest_pin','wrapper_pin','engine_pin'))
    selected=[]
    for expected in needed_pins:
        matches=[n for n,p in v5pins.items() if p==expected]
        need(len(matches)==1,'explicit v5 five query files');admit(matches[0],expected);selected.append(matches[0])
    index_name,data_name,source_name,wrapper_name,engine_name=selected
    v5index=obj(index_name);v5data=obj(data_name)
    need(len(v5index['entries'])==59,'v5 59entries')
    need(len(oldinventory['old74_JSON_source_pins_unchanged'])==74,'74 old sources')
    # R1 retained pointer map fixes exact10 R75/R77 sources. R79 five are dropped only from R2 planned direct list.
    group10={n:p for n,p in oldinventory['new15_accepted_JSON_pins'].items() if '20261016-r79-' not in n}
    need(len(group10)==10,'R75/R77 exactly10')
    for n,p in group10.items():admit(n,p)
    r80five={n:{'bytes':length,'sha256':sha} for n,(length,sha) in HARD.items() if n.startswith(R80) or n.startswith(R80REVIEW)}
    need(len(r80five)==5,'R80 five sources')
    new15=group10|r80five;need(len(new15)==15,'new15 distinct')
    all89=oldinventory['old74_JSON_source_pins_unchanged']|new15
    need(len(all89)==89 and set(oldinventory['old74_JSON_source_pins_unchanged']).isdisjoint(new15),'74+15=89 distinct')
    # Reuse unchanged row equality map, independently compare current frozen v5 rows now.
    generator=next(e for e in v5index['entries'] if e['rva']=='0x993570')
    byid={e['id']:e for e in v5index['entries']}
    need(canon(generator)==oldproof['generator_base_row_canonical_sha256'],'v5 generator exact base')
    for key,expected in oldproof['old58_canonical_rows'].items():need(key in byid and canon(byid[key])==expected['canonical_sha256'],'old58 canonical base equality')
    need(len(byid)==59,'unique existing IDs')
    need('0x97bd30' not in [e['rva'] for e in v5index['entries']],'new callee entry not duplicated')
    # Old data format may store source mapping as a dict; compare raw74 pin mapping rather than infer nested witnesses.
    need(isinstance(v5data['sources'],dict) and v5data['sources']==oldinventory['old74_JSON_source_pins_unchanged'],'exact old74 data manifest pins')
    need(sum(p['bytes'] for p in v5data['sources'].values())==2321371,'old74 metadata byte sum')
    need(P[engine_name]=={'bytes':16583,'sha256':'ea030ce19461b2e414e0cdbc42f4933551fa9e654f7a7a43db948670b27fa466'},'accepted v5 Python query engine same bytes')
    rf=obj(R80REVIEW+'findings.json');rc=obj(R80+'actual-contract.json');rs=obj(R80+'actual-selected-evidence.json')
    need(rf['sealed'] and rf['passed'] and rf['blocking_findings']==[],'accepted R80 full review')
    for key,name in [('subject_actual_manifest','actual-manifest.json'),('subject_contract_pin','actual-contract.json'),('subject_selected_pin','actual-selected-evidence.json')]:need(rf[key]==triple(R80+name),'R80 full exact subject')
    need(rf['result']['partial_owned_bytes']==2 and rf['result']['whole_function_closed'] is False,'R80 prefix boundary')

    refs=[dict(x) for x in oldrefs['references'] if x['path'] in group10]
    mapping={R80+'actual-manifest.json':['/files','/authority','/decoder_witness_only_not_rehashed_by_sealer'],
      R80+'actual-contract.json':['/observations','/conditional_projection','/unknowns','/resources','/authority'],
      R80+'actual-selected-evidence.json':['/all13_raw_reviewed_rows','/partial','/old_CALL','/RIP_arithmetic','/semantic_memory_reads'],
      R80REVIEW+'findings.json':['/passed','/subject_actual_manifest','/subject_capture_pin','/subject_contract_pin','/subject_owned_pin','/subject_selected_pin','/limits','/authority'],
      R80REVIEW+'manifest.json':['/files','/subject_actual_manifest','/engine_metadata_only']}
    for n,ps in mapping.items():
        for p in ps:refs.append({'path':n,'json_pointer':p,**P[n]})
    resolved=[]
    for e in refs:
        need(P[e['path']]=={k:e[k] for k in ('bytes','sha256')},'reference selected source pin')
        value=pointer(obj(e['path']),e['json_pointer'])
        resolved.append({'path':e['path'],'json_pointer':e['json_pointer'],'value_type':type(value).__name__,'canonical_value_sha256':canon(value)})
    need(set(e['path'] for e in refs)==set(new15),'all15 direct sources used by evidence; no unused supplement')
    own=Path(__file__).relative_to(ROOT).as_posix();ownraw=read(own,'own_source_before');P[own]=digest(ownraw);C[own]=ownraw

    future=[{'role':role,'path':None,'bytes':None,'sha256':None,'json_pointers':None,'status':'future_R81_not_final_not_read_not_guessed'} for role in ('author_actual_manifest','author_contract','author_selected_evidence','independent_full_findings','independent_full_manifest')]
    inventory={'schema':'EU4-LOOKUP-V6-R2-SOURCE-INVENTORY/1','sealed':True,'author_proposal_only':True,
      'old74_JSON_source_pins_unchanged':oldinventory['old74_JSON_source_pins_unchanged'],'old74_metadata_bytes':2321371,
      'R75_R77_exact10_sources':group10,'R80_exact5_sources':r80five,'current_new15_sources':new15,'new15_bytes':sum(x['bytes'] for x in new15.values()),
      'current_direct_source_count':89,'future_R81_five_roles':future,'future_direct_source_count_if_exact5_added':94,'accepted_engine_source_limit':96,'engine_cap_expansion_allowed':False,
      'dropped_only_from_unbuilt_R2_plan':{'R79_direct_JSON_sources':sorted(n for n in oldinventory['new15_accepted_JSON_pins'] if n not in group10),'R79_separate_generator_context':True,
       'historical_R79_files_modified':False,'reason':'R80/R81 accepted contracts and full-review pins inherit metadata-fence witness. They do not directly re-audit the R79 graph.'},
      'no_recursive_history_or_old74_body_authentication_claim':True,'R72_R74_R65_excluded':True,
      'if_future_R81_needs_extra_source':'Stop and explicitly revise selected source list; no silent engine fork/cap expansion or unreferenced supplement.'}
    save('source-inventory.json',inventory)
    save('reference-plan.json',{'schema':'EU4-LOOKUP-V6-R2-EXACT-POINTER-PLAN/1','sealed':True,'references':refs,'resolved':resolved,'reference_count':len(refs),'current_new_source_count':15,
      'R75_R77_consumers':'Only generator copied row later_checked_context and evidence append','R80_consumer':'Future new97bd30 entry after R81 actual/full acceptance','future_R81_refs':'Not guessed; fix exact raw/contract/full-review pointers from final R81 schema after acceptance.',
      'all94_direct_sources_must_be_referenced_in_entry_evidence':True,'no_unreferenced_top_level_supplement':True})
    preservation=dict(oldproof)
    preservation.update(schema='EU4-LOOKUP-V6-R2-OLD-ENTRY-PRESERVATION/1',planned_later_checked_context_sources=['R75','R77'],R79_context_appended=False,
      historical_base_scope='Original generator fields, summary, signature, unresolved and later_conditional_context remain the v5 historical base. New later_checked_context limits selected old unresolved claims under its own assumptions.',
      new_entry={'rva':'0x97bd30','entry_evidence':'R69 retained direct CALL as inherited by R80 accepted contract/full review','scope':'known CALL entry; selected prefix with later R81 suffix context only after accepted actual/full review',
       'requires_before_build':['R81 fixed actual final package','R81 independent full review passed with exact subject pins','root separate v6 build scope authorization'],
       'must_not_infer':['whole function extent/closure from cached gap or local RET','independent callable Win64 API from suffix','formal C++ signature/type/class','return semantics before tail evidence','D/header final contents or disjoint aliases','units/currency/recipient/settlement/effect/lifetime'],
       'R80_historical_contract_unchanged':True,'future_R81_fact_fields':None})
    save('old-entry-preservation.json',preservation)
    known_new=sum(p['bytes'] for p in new15.values())
    future_R81=1048576;index_allowance=524288;data_allowance=65536
    perpass=2321371+known_new+future_R81+index_allowance+data_allowance
    perquery=2*perpass+3*16583+16384
    queryupper=4*perquery+8388608
    need(queryupper<64*1024**2,'conditional future query upper64M')
    budgets={'build_plus_seal_bytes':32*1024**2,'first_four_query_batch_bytes':64*1024**2,'ordinary_file_bytes':CAP,'software_memory_bytes':768*1024**2,'one_GiB_stop':True,
      'old74_metadata_source_bytes':2321371,'new15_known_bytes':known_new,'conditional_R81_five_source_total_allowance':future_R81,'conditional_new_index_allowance':index_allowance,'conditional_new_data_allowance':data_allowance,
      'conditional_perpass_bytes':perpass,'conditional_perquery_two_passes_three_query_engine_pins_wrapper_allowance':perquery,'controller_allowance':8388608,'conditional_fourquery_plus_controller_upper':queryupper,
      'not_universal_OS_loader_IO_bound':True,'query_engine_is_python_lookup_source_not_Capstone_decoder':True,
      'future_unknown_file_sizes_exceed_allowance':'Recompute and stop before batch/budget exceedance; do not silently expand.',
      'accepted_query_engine_aggregate32MiB':'Successful graph acceptance; a refusal may charge one next perfile-bounded source before checking aggregate. No guard hardening planned.'}
    plan={'schema':'EU4-WAR-PEACE-LOOKUP-V6-SOURCE-SCOPE-PROPOSAL/2','sealed':True,'stage':'author_planning_not_candidate_build_source_ready_or_query_authorization',
      'supersedes_unbuilt_scope_only':triple(OLD+'plan.json'),'R1_artifacts_modified':False,
      'author_role':'war_api authored lookupv5 and R79 actual/source, reviewed R78 and R80 full. This R2 is author planning, not non-author v6 review. Independent v6 source/engine/data/receipt review remains required.',
      'baseline':oldplan['baseline'],'planned_scope':{'result_entry_count_if_ready':60,'old58_rows':'strict dataequal, all fields/evidence intact','generator_existing_fields':'strict v5 equality except exact evidence prefix plus append','generator_new_keys':['later_checked_context','historical_base_scope'],
       'generator_contexts_only':['R75 selected NULL successor return contract','R77 conditional caller fragment composition'],
       'original_generator_later_conditional_context_and_unresolved':'unchanged, historical scope; no rewriting v5 NULL-unread text','R79_direct_context':'removed from this unbuilt R2 plan only; all R79 history remains frozen',
       'new97bd30_entry':'Wait for R81 full acceptance; combine R80 selected prefix with later suffix context, without wholefunction/formal/type/unit/effect claims.',
       'R80_selected_current_facts':{'complete_rows':13,'complete_bytes':62,'partial_owned_bytes':2,'QWORD_loads':8,'RET_seen':False,'known_function_extent':False},
       'sources_current89_future94':'old74+R75/R77ten+R80five+R81futurefive=94<=96; no engine expansion',
       'R79_metadata_fence_provenance':'Only inherited R80/R81 accepted contract/full witness; no direct R79 selected JSON reauthentication or separate97bd30 duplicate entry.'},
      'engine_wrapper_plan':oldplan['engine_wrapper_plan'],'dependencies':{'R75_R77':'accepted exact10JSONs reused as fixed independent witnesses, not full recursive re-review','R80':'accepted full review81bb504d pinned exact five JSON roles','R81':'No final/actual/full schema or facts assumed; five future roles null and mutable files not read','v6_build':'Not authorized by this proposal','v6_publication':'Requires non-author full v6 source/data/first receipts acceptance and root publication'},
      'future_verification_plan':{'first_queries_max':4,'first_queries':['check','catalog','lookup 0x993570','lookup 0x97bd30'],'each_once_only':True,'execute_now':False,
       'source_checks':['old58 strict equality','generator oldfields exact except evidence append and new2keys','old74 direct JSON pins unchanged','94 refs fixed valid used pointers','accepted ea030 query engine exactbytes and96cap unchanged','wrapper metadata-only ASTdelta','allauthority false; no fragment standalone entry'],
       'no_old_suite_parser_fixture_query_reruns':True,'must_preserve_new_failures_and_successful_queries_not_repeat':True},
      'future_budgets':budgets,'authority':AUTH,'old_files_modified':False,'v6_candidate_created':False}
    save('plan.json',plan)
    for n,p in list(P.items()):read(n,'after',p)
    after=memory();charged=sum(e['bytes'] for e in J)
    need(charged+MANUAL+TAIL<=LIMIT,'proposal own upper')
    save('resources.json',{'schema':'EU4-LOOKUP-V6-R2-PROPOSAL-RESOURCES/1','flat_input_files':len(P)-1,'source_pin_before_after_equal':True,'completed_read_events':J,'completed_read_bytes':charged,'manual_inspection_allowance_bytes':MANUAL,'seal_and_filecheck_reserve_bytes':TAIL,'upper_bytes':charged+MANUAL+TAIL,'own_limit_bytes':LIMIT,'ordinary_limit_bytes':CAP,'self_before':before,'self_after':after,
      'manual_scope':'Initial focused R1 schema/selected v5 metadata inspection only; no recursive74old JSON closure. The Python lookup engine source is read/hash only, no Capstone/native decoder.',
      'no_PE_engine_decoder_game_native_tests_queries_or_candidate_build':True,'all_shells_collected':True})
    report='v6 author proposal R2: wait for R81 actual/full review before building.\n\nKeep v5 old58 rows and original generator fields unchanged. Append only R75/R77 context/evidence plus historical_base_scope. Remove R79 direct context/five planned sources only from the unbuilt proposal, preserving every historical artifact. New97bd30 entry will use five accepted R80 and five future R81 roles; no suffix is an independent API and no wholefunction, formal/type, units, finalD or effect is inferred.\n\nOld74+new10(R75/R77)+fiveR80+futurefiveR81=94<=unchanged96 cap. Exact source pointers are resolved for current15 new sources; future R81 paths/SHA/pointers remain null. Future queries: check/catalog/lookup993570/lookup97bd30, each once only after separately authorized build. No candidate, query or runtime was created/run.\n'
    with (OUT/'report.md').open('x',encoding='utf-8',newline='\n') as f:f.write(report)
    pins=dict(P)
    for n in ('plan.json','source-inventory.json','reference-plan.json','old-entry-preservation.json','resources.json','report.md'):
        name=(OUT/n).relative_to(ROOT).as_posix();pins[name]=digest(read(name,'own_output_seal'))
    save('manifest.json',{'schema':'EU4-LOOKUP-V6-R2-PROPOSAL-MANIFEST/1','sealed':True,'author_proposal_only':True,'source_pins':pins,'pin_count':len(pins),'candidate_built':False,'queries_executed':False,'native_ready':False,'actual_authorized':False})
    print(json.dumps({'status':'sealed_author_proposal_only','plan':digest((OUT/'plan.json').read_bytes()),'manifest':digest((OUT/'manifest.json').read_bytes()),'current_new_source_count':15,'future_sources':94,'own_upper_bytes':charged+MANUAL+TAIL,'future_fourquery_conditional_upper':queryupper}))


def check():
    b=read((OUT/'manifest.json').relative_to(ROOT).as_posix(),'first_proposal_filecheck_manifest');d=json.loads(b)
    need(d['author_proposal_only'] and d['pin_count']==len(d['source_pins']),'own proposal manifest')
    for n,p in d['source_pins'].items():read(n,'first_proposal_filecheck',p)
    v={'schema':'EU4-LOOKUP-V6-R2-PROPOSAL-FILECHECK/1','passed':True,'subject_manifest':digest(b),'pin_count':len(d['source_pins']),'read_bytes':sum(e['bytes'] for e in J),'author_program_query_tests_PE_decoder_game_operations':0,'all_shells_collected':True}
    save('verification.json',v);print(json.dumps(v))


if __name__=='__main__':
    try:
        if sys.argv[1:]==['--check']:check()
        else:need(sys.argv[1:]==[],'proposal only or own check');main()
    except BaseException:
        if OUT.exists():
            with (OUT/'failure.json').open('x',encoding='utf-8') as f:json.dump({'traceback':traceback.format_exc(),'read_events':J,'read_bytes':sum(e['bytes'] for e in J),'no_author_query_or_runtime_retry':True},f,indent=2)
        raise
