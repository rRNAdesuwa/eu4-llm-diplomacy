"""Root grants a new single fixed-prefix source build; no actual PE acquisition."""
from pathlib import Path
import hashlib,json,datetime
ROOT=Path(__file__).resolve().parents[1]
PLAN='work/reports/war-peace-api-20261016-r89-c9d60-source-plan/'
OUT=ROOT/'work/reports/war-peace-api-20261016-r89-root-source-authorization'
assert not OUT.exists()
used=0;journal=[];CAP=8388608;MANUAL=524288
def pin(b):return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def read(n,p):
 global used
 path=ROOT/n;s=path.stat().st_size
 assert 0<s<=4194304 and used+s+1+MANUAL<=CAP
 with path.open('rb') as f:b=f.read(s+1)
 used+=len(b);assert len(b)==s and pin(b)==p,n
 journal.append({'path':n,**pin(b)});return b
def fixed(n,s,h):return read(n,{'bytes':s,'sha256':h})
def triple(n,b):return {'path':n,**pin(b)}
def save(path,o):
 b=(json.dumps(o,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode('ascii')
 with path.open('xb') as f:f.write(b)
 return b
pr=fixed(PLAN+'proposal.json',15747,'5aa951e2818b5525a969a16903707ed66e5ddb78e3524266ecb7b763f9a1237f')
mr=fixed(PLAN+'manifest.json',4689,'89068eefa2db4dcd2d6ceb05cc03b3eccb62416558e52f612ce9d8aaefc25659')
p=json.loads(pr);assert p['sealed'] is True and p['authority']['actual_authorized'] is False
assert len(p['selected_sources'])==14
data={n:read(n,v) for n,v in p['selected_sources'].items()}
owned=json.loads(data['work/reports/war-peace-api-20261016-r87-dual-frontier-source/owned-code.json'])
raw=bytes.fromhex(owned['raw_hex']);assert raw[159:164]==bytes.fromhex('e856daffff')
assert 0xcc30a+int.from_bytes(raw[160:164],'little',signed=True)==0xc9d60
assert 1024+0xc9d60-0x1000==823648
before={x['path']:{k:x[k] for k in ('bytes','sha256')} for x in journal}
for n,v in sorted(before.items()):read(n,v)
assert used+MANUAL<CAP
OUT.mkdir()
fixed_inputs=p['selected_sources'].copy();fixed_inputs[PLAN+'proposal.json']=pin(pr);fixed_inputs[PLAN+'manifest.json']=pin(mr)
grant={'schema':'EU4-R89-C9D60-FIXED-PREFIX-SOURCE-BUILD/1','sealed':True,'source_build_only':True,'actual_authorized':False,
 'executor':'/root/war_api','issued_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'new_source_namespace':'work/reports/war-peace-api-20261016-r89-c9d60-source',
 'subject_proposal':triple(PLAN+'proposal.json',pr),'subject_plan_manifest':triple(PLAN+'manifest.json',mr),'fixed_inputs':fixed_inputs,
 'fixed_raw_window':{'begin':'0xc9d60','end_exclusive':'0xc9e60','bytes':256,'seeds':['0xc9d60']},
 'seed_semantics':{'0xc9d60':'direct_CALL_encoding_target_not_safe_callable_proof'},
 'metadata_policy':{'mode':'bounded_lower_bound_diagnostic_only','maximum_search_records':29,'maximum_selected_previous_next_records':3,'maximum_total_records':32,'maximum_physical_bytes':384,'record_bytes':12,'global_sorted_table_premise_explicit':True,'positive_local_ordered_disjoint_validation_required':True,'cached_raw_mapping_and_table_count_bounds_required':True,'metadata_never_selects_code_extent':True},
 'gap_policy':{'completed_valid_ordered_gap_allowed':True,'contained_nonexact_allowed':True,'must_record_function_metadata_unknown_for_gap':True,'invalid_or_budget_incomplete':'unknown0code','no_metadata_search_retry_or_raw_rewindow':True,'selected_256raw_independent_of_metadata':True,'no_leaf_function_ABI_unwind_global_absence_inference':True},
 'source_limits':{'explicit':33554432,'parent':2097152,'producer':31457280,'retained':16777216,'ordinary_file':4194304,'soft_memory':805306368,'stop_memory':1073741824},
 'future_target_limits':{'whole_EXE_hash_streams':2,'whole_EXE_hash_bytes':76925008,'metadata_records_max':32,'metadata_bytes_max':384,'code_bytes':256,'PE_physical_upper':76925648,'decoder_unique_bytes':256,'decoder_lookahead_upper':3840},
 'Job':{'seconds':45,'memory':805306368,'active_and_cumulative_processes':8,'stdout_stderr_acceptance_each':2097152,'game_process_assigned':False},
 'authorized_source_changes':p['minimal_template_delta'],
 'source_build_sequence':['May prepare new producer/main, diagnostic metadata core and single-seed CFG/Job gates now, preserving nine donor helper text/AST and opaque engine metadata only.',
  'Freeze final upstream actual-review binding only after real R87 complete non-author findings schema is available; do not invent a fullreview pin/pass or silently retain R86-only subjects.',
  'Freeze exact complete new source graph before running any newly permitted synthetic case; all old source/claims/outputs remain unchanged.'],
 'new_offline_cases':{'maximum':4,'each_runs':1,'only_after_final_source_freeze':True,'allowed':'New synthetic metadata/one-seed boundaries only: valid exact/local containment, valid ordered gap-policy, invalid overlap/short metadata, and single-seed/label binding. Use fabricated bytes/records and fake decoder; no Capstone/opaque engine/PE/producer/main/launcher/old cases. First unexpected failure preserved and stops, no automatic repair or retry. Exact owned Job/source/retained caps apply.'},
 'required_before_actual':['Complete R87 actual non-author raw/contract review and exact root acceptance.','Complete non-author new source/retained-case review with exact executable/source subjects.','Separate root raw direct-CALL seed/window/metadata/gap review and exact once grant.'],
 'forbidden':['PE stat/open/hash/read, engine body/Capstone import, actual producer or launch_once execution before separate actual grant.',
 'Two original large cache rereads or new cache/repository searches; use fixed R88 metadata witness only.',
 'Following callee, RIP data, vtable/header/unwind, external branch or raw prefix expansion.',
 'Game process/UI/Frida/native/writes/requests/saves/reloads; original action retry.'],
 'native_ready':False,'callable':False,'reader_adoption_allowed':False,'selected_effect_verified':False,'ownership_transfer_verified':False,'world_lease':False,'atomic_snapshot':False,'authorizes_retry':False}
gr=save(OUT/'authorization.json',grant)
receipt={'schema':'EU4-R89-ROOT-SOURCE-PLAN-REVIEW/1','sealed':True,'passed':True,'blocking_findings':[],
 'subject_proposal':triple(PLAN+'proposal.json',pr),'authorization':triple(OUT.relative_to(ROOT).as_posix()+'/authorization.json',gr),
 'source_before_after_equal':True,'source_returned':used,'manual_allowance':MANUAL,'source_upper':used+MANUAL,'source_cap':CAP,'read_journal':journal,
 'limits':'Exact14 small source/plan inputs and directCALL/mapping arithmetic only. Existing source and R88 negative caches are fixed witnesses, not a repeated full raw/body/cache review. R87 full actual remains pending and actual target is forbidden.'}
rr=save(OUT/'receipt.json',receipt)
print(json.dumps({'authorization':triple(OUT.relative_to(ROOT).as_posix()+'/authorization.json',gr),'receipt':triple(OUT.relative_to(ROOT).as_posix()+'/receipt.json',rr),'source_upper':used+MANUAL},ensure_ascii=True))
