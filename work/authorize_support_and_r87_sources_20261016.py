"""Root exact file-plan reviews and source-build grants; no target execution."""
from pathlib import Path
import hashlib,json,datetime
ROOT=Path(__file__).resolve().parents[1]
journal=[]
total=0
CAP=8388608
MANUAL=1048576
def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def read(name,expected=None):
 global total
 p=ROOT/name
 assert not Path(name).is_absolute() and '..' not in Path(name).parts
 assert p.resolve().is_relative_to(ROOT.resolve())
 size=p.stat().st_size
 assert 0<=size<=4194304 and total+size+1+MANUAL<=CAP
 with p.open('rb') as f:raw=f.read(size+1)
 total+=len(raw);actual=pin(raw)
 assert len(raw)==size
 if expected is not None:assert actual==expected,name
 journal.append({'path':name,**actual})
 return raw
def fixed(name,size,sha):return read(name,{'bytes':size,'sha256':sha})
def triple(name,raw):return {'path':name,**pin(raw)}
def parse(raw):
 def pairs(v):
  out={}
  for k,x in v:assert k not in out;out[k]=x
  return out
 return json.loads(raw,object_pairs_hook=pairs)
def write(path,obj):
 raw=(json.dumps(obj,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode('ascii')
 with path.open('xb') as f:f.write(raw)
 return raw

SUP='work/reports/support-heir-current-verification-plan-20261016-r1/'
NAT='work/reports/war-peace-api-20261016-r87-dual-frontier-source-plan/'
sup_raw=fixed(SUP+'plan.json',23293,'641465b154c02d7749dfb61643833088d8784979935bbbc669306d8b36e78e55')
sup_manifest=fixed(SUP+'manifest.json',8223,'2a13665dc96f940572b53e1ff85648af8d9b765d8baa625a637f058e6b1430c6')
nat_raw=fixed(NAT+'plan.json',18924,'ea0544001037b002e60f27e342d15bc53f6b52cf5e902d07318c9908f9069e99')
nat_manifest=fixed(NAT+'manifest.json',5115,'b175f7fd5b0b63102b71db3319810ca9d8e2c7def087a86520e8c140e90ceccf')
sup,nat=map(parse,(sup_raw,nat_raw))
assert sup['sealed'] is True and sup['authority']['live_authorized'] is False
assert nat['sealed'] is True and nat['actual_authorized'] is False
assert len(sup['source_pins'])==29 and len(nat['source_pins'])==16
fixed_sources={}
for plan in (sup,nat):
 for name,p in plan['source_pins'].items():
  expected={k:p[k] for k in ('bytes','sha256')}
  if name in fixed_sources:assert fixed_sources[name]==expected
  fixed_sources[name]=expected
sources={name:read(name,p) for name,p in sorted(fixed_sources.items())}
extras=[
 ('work/reports/peace-current-pending-v2-text-config-source-authorization-20261016-r1/authorization.json',6172,'58e3ab5f51a73c47e0b1119f9554712c91e34f5289ca228e339cb0f2c9e33d50'),
 ('work/reports/peace-current-pending-v2-live-controller-source-independent-review-20261016-r2/findings.json',5817,'4e38a2083274e8e82825ad63f0e50b7dc7ae3c90858703742341db33e3da31d7'),
 ('work/reports/peace-current-pending-v2-live-controller-source-independent-review-20261016-r2/manifest.json',13944,'c80ea76a7847b55613672b0a7fbf0fd24dc13d91b8a3e4fba868d68737af1086'),
 ('work/reports/peace-current-pending-v2-config-pin-preparation-20261016-r1/preparation.json',674,'aa9d27c365c756163df0a714cde519b3a8f36ee6a4f1a7c960ec427f0160b7ae'),
 ('work/reports/peace-current-pending-v2-live-controller-20261016-r2/receipt.json',421298,'44c1eeab3ca7fe25dc54a3087a208dbebd9bce23f5118e372d16ebc1ee435583')]
extra={name:fixed(name,size,sha) for name,size,sha in extras}
peace_build=parse(extra[extras[0][0]])
source_peer=parse(extra[extras[1][0]])
config_prep=parse(extra[extras[3][0]])
peace_result=parse(extra[extras[4][0]])
assert source_peer['sealed'] is True and source_peer['passed'] is True and source_peer['blocking_findings']==[]
assert peace_result['control_passed'] is True and peace_result['status']=='selected_peace_queue_absent'
selection={'pid':98548,'creation':'01dd5d0e670312c4','actor':'FRA','target':'POL'}
assert {k:peace_result['selection'][k] for k in ('pid','creation','actor')}=={k:selection[k] for k in ('pid','creation','actor')}
config={'path':'local.env','bytes':226,'sha256':'84abda5840824badc9fd5daef7f5faedd61e5c2a01e329843b2bd5a5caeb7658'}
assert config_prep['local_configuration_pin']==config
assert sup['selected_profile']['cli']['sha256']=='8b2eba840c3f6b4927f6fbf1aa04878c931fc548372dc10dd8432863ed68ec01'
assert nat['recommended_window']['rva_begin']=='0xcc266' and nat['recommended_window']['rva_end_exclusive']=='0xcc366'
assert nat['recommended_window']['explicit_decode_seeds']==['0xcc266','0xcc32c']
# Independently replay only the two fixed branch/fallthrough seeds, not any callee.
cap_name=nat['upstream_actual_capture']['path']
cap=parse(sources[cap_name])
rows=cap['analysis']['instructions']
assert rows[17]['bytes']=='0f84cd000000' and rows[19]['bytes']=='482bca'
assert 0xcc259+6+int.from_bytes(bytes.fromhex('cd000000'),'little',signed=True)==0xcc32c
assert 0xcc263+3==0xcc266
before={r['path']:{k:r[k] for k in ('bytes','sha256')} for r in journal}
for name,p in sorted(before.items()):read(name,p)
assert total+MANUAL<=CAP

support_fixed={name:{k:p[k] for k in ('bytes','sha256')} for name,p in sup['source_pins'].items()}
for name in [SUP+'plan.json',SUP+'manifest.json']:
 support_fixed[name]=pin(sup_raw if name.endswith('plan.json') else sup_manifest)
for name in [extras[1][0],extras[2][0],extras[3][0]]:support_fixed[name]=pin(extra[name])
limits=peace_build['future_live_budget_design'].copy()
# The frozen support journal excludes its entry read. Separate the budgets visibly.
for key in list(limits):
 if key.startswith('RPM_'):del limits[key]
limits.update(shared_RPM_calls=4096,shared_RPM_requested_bytes=524288,shared_RPM_single_request=65536,
 entry_PE_source_declared_calls=1,entry_PE_source_declared_requested_bytes=8192,entry_PE_raw_journaled=False)
support_grant={
 'schema':'EU4-SUPPORT-HEIR-CURRENT-CONTROLLER-BUILD/1','sealed':True,'source_build_only':True,'runtime_authorized':False,
 'executor':'/root/diplomacy_static','issued_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'new_source_namespace':'work/reports/support-heir-current-live-controller-20261016-r1',
 'selection':selection,'local_configuration_pin_metadata':config,'fixed_inputs':support_fixed,
 'subject_plan':triple(SUP+'plan.json',sup_raw),'subject_plan_manifest':triple(SUP+'manifest.json',sup_manifest),
 'root_config_preparation':triple(extras[3][0],extra[extras[3][0]]),
 'future_live_budget_design':limits,'build_limits':{'source_explicit':33554432,'retained':8388608,'ordinary_file':4194304,'soft_memory':805306368,'stop_memory':1073741824},
 'authorized_source_changes':[
  'New support-specific controller/child/contract and exact-reviewed adapter composition; retain frozen support CLI21780/canonical5506 and all old dependency/helper sources unchanged.',
  'Reuse original R2 TextConfigAdapter7297/b1d44aff... exact bytes under the new fixed ROOT contract; no real env stat/open/hash/read during source build.',
  'Bind source/production witnesses, raw new once grant before parse, four exact source subjects, PID/creation/FRA-POL/config triple, permanent controller and child claims. A peace grant never substitutes.',
  'Keep ordinary/host/game Meter request reservation and original delegation limits, Job45s/768MiB/8 processes/output2MiB. Do not patch RuntimeCapture/Held or synthesize entry raw data.',
  'Selected current support task state only; retain separate entry8192 source declaration and shared journal/caps. Commit only after original normal-context/heldNone/source guards.'
 ],
 'new_offline_cases':{'maximum':4,'each_runs':1,'only_after_source_freeze':True,'allowed':'New controller result/closure/authorization boundary fakes only, with synthetic captures and contracts. No frozen reader/candidate/main/CLI import, no old15/2/8/6/31 tests, no real config/PE/engine/process. First failure stops; preserve it; no automatic repair/retry. Hard Job and all source/retained budgets apply.'},
 'required_before_live':['Complete non-author source and retained-case review (root may review as non-author; D is author).','A separate exact root once status grant; this build grant is never executable status permission.'],
 'operations_authorized':{'source_files_and_new_bound_fakes':True,'game_process_UI_PE_hostbinary_native_requests_saves_reloads':False,'real_env_operations':False},
 'limits':['Prior peace identity/capture is a selection witness, not future lease; the eventual held process must authenticate freshly.','EntryPE expected8192 is not raw observation; shared counts do not cover every process operation.','Full OS/import/cache/delegated file IO, OS CloseHandle return, ABI/class/lifetime/AI/original effects/final heir/persistence remain unknown.'],
 'all_effect_native_retry_authority':False
}
native_grant={
 'schema':'EU4-R87-DUAL-FRONTIER-SOURCE-BUILD-GRANT/1','sealed':True,'source_build_only':True,'actual_authorized':False,
 'executor':'/root/war_api','issued_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'subject_plan':triple(NAT+'plan.json',nat_raw),'subject_plan_manifest':triple(NAT+'manifest.json',nat_manifest),
 'fixed_inputs':{name:{k:p[k] for k in ('bytes','sha256')} for name,p in nat['source_pins'].items()},
 'new_source_namespace':'work/reports/war-peace-api-20261016-r87-dual-frontier-source',
 'fixed_raw_window':{'begin':'0xcc266','end_exclusive':'0xcc366','bytes':256,'seeds':['0xcc266','0xcc32c']},
 'metadata':{'fixed_indices':list(range(1251,1260)),'records':9,'bytes':108,'hard_records':32,'hard_bytes':384,'cc266_exact_record1253_required':True,'known_raw_anchor_match_required':True,'positive_ordered_nonoverlapping_required':True},
 'explicit_gap_policy_delta':{
  'cc32c_pdata_gap_allowed':True,'cc266_pdata_gap_allowed':False,
  'reason':'CC32C is the independently recomputed direct JE successor of already owned R86 code, not a claimed new function entry. Pdata coverage is diagnostic for this one proven continuation; lack of a containing record must not suppress the exact explicitly authorized raw window.',
  'requirements':['Record missing containment as gap/unknown-function-metadata; never fabricate a function record or promote extent/ABI.','Multiple containment, invalid ordering/anchors/raw mapping or wrong cc266 descriptor still fail closed unknown0code.','No metadata search/fallback/new address/window expansion; the only exception is this exact direct-proven cc32c seed.']},
 'source_limits':{'explicit':33554432,'retained':16777216,'ordinary_file':4194304,'soft_memory':805306368,'stop_memory':1073741824},
 'future_target_limits':{'whole_EXE_hash_streams':2,'whole_EXE_hash_bytes':76925008,'metadata_bytes':108,'code_bytes':256,'recommended_PE_total':76925372,'absolute_PE_upper':76925648,'decoder_unique_bytes':256,'decoder_lookahead_bytes':3840},
 'Job':{'seconds':45,'memory':805306368,'active_and_cumulative_processes':8,'stdout_stderr_acceptance_each':2097152,'target_game_assigned':False},
 'authorized_source_changes':nat['template_delta_required']['new_source_changes'],
 'cfg_requirements':nat['decoder_proposal']['rules'],
 'new_offline_cases':{'maximum':4,'each_runs':1,'only_after_source_freeze':True,'allowed':'New synthetic CFG worklist cases only: dual-seed dedup/interior-target refusal/external frontier/partial-tail, with predefined fake decoder rows. No Capstone/engine/PE/producer main/target/process import or execution. No old tests; preserve first failure and stop, no auto repair/retry. New Job/source/retained caps apply.'},
 'required_before_actual':['R86 complete non-author actual raw/contract review and acceptance.','Complete non-author new CFG/main/metadata/gap-policy/Job source and retained synthetic-case review (root may review as non-author).','Separate exact root once grant and raw seed/range/metadata-policy acceptance; old R86 authorization/claim cannot substitute.'],
 'forbidden':['Target PE stat/open/hash/read, decoder or opaque engine import, producer/launcher main before new actual grant.','Game process/Frida/UI/native/requests/saves/reloads.','Following any callee, RIP data, vtable, header, unwind, out-of-window branch or arbitrary neighbor.'],
 'native_ready':False,'callable':False,'reader_adoption_allowed':False,'world_lease':False,'atomic_snapshot':False,'authorizes_retry':False
}
outputs=[]
for folder,grant in [('work/reports/support-heir-current-controller-source-authorization-20261016-r1',support_grant),('work/reports/war-peace-api-20261016-r87-root-source-authorization',native_grant)]:
 out=ROOT/folder;assert not out.exists();out.mkdir()
 raw=write(out/'authorization.json',grant)
 receipt={'schema':'EU4-ROOT-FIXED-PLAN-SOURCE-DECISION/1','sealed':True,'passed':True,'source_before_after_equal':True,'authorization':triple(folder+'/authorization.json',raw),'read_journal':journal,'resources':{'formal':total,'manual_small_read_allowance':MANUAL,'upper':total+MANUAL,'cap':CAP},'operations':{'subject_import_execute':0,'real_env_PE_engine_process_UI_native_requests_tests':0},'scope':'Source-build only. Exact selected plan inputs and branch arithmetic reviewed; prior peers remain pinned witnesses, not recursive recertification. Runtime/actual source and full raw gates still required.'}
 rr=write(out/'receipt.json',receipt)
 outputs.append({'authorization':triple(folder+'/authorization.json',raw),'receipt':triple(folder+'/receipt.json',rr)})
print(json.dumps({'grants':outputs,'source_upper':total+MANUAL,'actual_runtime_attempts':0},ensure_ascii=True))
