"""Offline fixed 36-ID batch planning. No imports of live clients or execution."""
import ast,hashlib,json,argparse
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
INPUTS=(
 'work/native/lab_protocol_v17_1375.py','work/native/v17/pair-engine-1375.cpp',
 'work/candidates/fixture-v17-1375/mod/llm_diplomacy_test/events/llmt_fixture.txt',
 'work/candidates/fixture-v17-1375/mod/llm_diplomacy_test/common/defines/zz_llm_diplomacy_test.lua',
 'work/candidates/fixture-v17-1375/mod/llm_diplomacy_test/common/event_modifiers/llm_diplomacy_test.txt',
 'work/runtime/unpacked-1.37.5/base/history/diplomacy/French_alliances.txt',
 'docs/native-test-fixture-1375.md','docs/native-pair-cancel-1375.md',
 'docs/native-pair-extension-v11-1375.md','docs/native-pair-extension-effects-v10-1375.md',
 'work/candidates/directional-experiment-plan-v14-1375/README.md',
 'work/candidates/offered-fleet-ai-response-1375/report.json',
 'work/candidates/ordinary-insult-observer-1375/README.md')
# Order is a topological work-list, never a preallocated live request sequence.
# prerequisites are attempted prior tasks; only current native legality/guards
# may establish whether a relation exists and is valid for cancellation.
ROWS=(
 ('royal_marriage','NAV','reply',[],'Monarchy/religion/native marriage eligibility; NAV vassal does not establish a marriage.'),
 ('offer_alliance','POR','reply',[],'Ordinary independent-country alliance proposal; historical POR setup succeeded but current AI may reject.'),
 ('improve_relations','FOI','persistent_envoy',[],'Fresh native eligibility and free envoy; FOI remains a subject but this is not a dependency cancellation.'),
 ('guarantee','POR','unilateral',[],'Outgoing FRA guarantee only; native power/subject/cooldown checks remain authoritative.'),
 ('give_subsidies','POR','unilateral',[],'FRA payer/POR recipient; fixed 1000 milli monthly and 10 years; budget required.'),
 ('ask_military_access','POR','reply',[],'FRA holder/POR grantor; ordinary explicit protocol object, not conditional war access.'),
 ('offer_military_access','POR','reply',['offer_alliance'],'POR holder/FRA grantor; prior v14 proposal rejected before alliance and later succeeded with alliance; no guarantee.'),
 ('ask_fleet_basing_rights','POR','reply',[],'FRA holder/POR grantor; ports and native request eligibility.'),
 ('offer_fleet_basing_rights','POR','reply',['offer_alliance'],'POR holder/FRA grantor; ordinary AI score is -1000 in the audited path; legal dispatch may remain absent. No automatic accept-control window.'),
 ('request_trade_power','POR','reply',[],'POR supplier/FRA receiver; incoming and outgoing ordinary trade-power records absent; fixed fraction 500, flag 0.'),
 ('cancel_trade_power_transfer','POR','cancel',['request_trade_power'],'Exactly one current direction, full handles and fraction500/flag0. Dispatched positive does not prove it exists.'),
 ('steer_trade','POR','reply',['cancel_trade_power_transfer'],'POR steers toward FRA; keep after trade-power cancellation as a conservative scheduling constraint, not a proved universal engine exclusion.'),
 ('cancel_steer_trade','POR','cancel',['steer_trade'],'Exactly one selected ordinary steering direction, special flag0. Native current object binding required.'),
 ('send_gift','POR','unilateral',[],'Fixed 25.000 gold; actor funds/native eligibility. Batch treasury difference is not an individual gift proof.'),
 ('trade_favors_for_gold','POR','reply',['offer_alliance'],'Current favors, eligibility and native calculated amount; fixture does not grant favors. Legal rejection is expected in many fresh baselines.'),
 ('warn','ENG','unilateral',[],'No existing warning in either direction; native power/war eligibility. ENG chosen to avoid hostile penalties on friendly POR; legality may reject.'),
 ('insult','ENG','unilateral',[],'Fixed ordinary index -1; native eligibility. Only final insulted/trust state census, no per-action effect proof in this cross-date batch.'),
 ('embargo','ENG','unilateral',[],'Outgoing FRA->ENG record byte46 mask02, not dirty04 or reverse embargo.'),
 ('form_coalition','ENG','unilateral',[],'FRA has no current coalition; native AE/rival eligibility remains required. Fixture creates no qualifying AE.'),
 ('build_spy_network','ENG','persistent_envoy',['warn','insult','embargo','form_coalition'],'Start after one-shot ENG proposals; unique active task/full envoy binding. No improve mission to ENG in this plan.'),
 ('support_independence','NAV','reply',[],'Fixed FRA is NAV overlord under fixture: provider==overlord is rejected. This is a guard-coverage row, not a promise of support.'),
 ('stop_improving_relations','FOI','cancel',['improve_relations'],'Existing outgoing improve relation; native relation destructor may leave envoy returning; do not require instant idle.'),
 ('stop_building_spy_network','ENG','cancel',['build_spy_network'],'Unique active spy task with matching target/envoy, node/task not removed; missing is not a successful stop.'),
 ('revoke_guarantee','POR','cancel',['guarantee'],'Existing FRA guarantor/POR guaranteed relation; reverse guarantee cannot substitute.'),
 ('cancel_subsidies','POR','cancel',['give_subsidies'],'Existing FRA payer/POR recipient ordinary 1000/10 object; do not infer cancellation from nominal expiry.'),
 ('cancel_military_access','POR','cancel',['ask_military_access'],'FRA holder/POR grantor; same dual-index ordinary enforce_peace=0 object.'),
 ('revoke_military_access','POR','cancel',['offer_military_access'],'POR holder/FRA grantor; distinct direction from cancel_military_access.'),
 ('cancel_fleet_basing_rights','POR','cancel',['ask_fleet_basing_rights'],'FRA holder/POR grantor; explicit ordinary enforce_peace=0 object.'),
 ('revoke_fleet_basing_rights','POR','cancel',['offer_fleet_basing_rights'],'POR holder/FRA grantor; likely guard rejection if ordinary AI never accepted prior offer. No absent->absent effect.'),
 ('leave_coalition','ENG','cancel',['form_coalition'],'FRA coalition target full handle and unique active target membership required; missing initial eligibility cannot be repaired by a false-mode submit.'),
 ('cancel_independence_support','NAV','cancel',['support_independence'],'Same supported independent-provider/third-party-dependent scope required as positive; own NAV vassal remains unsupported.'),
 ('break_marriage','NAV','cancel',['royal_marriage'],'Existing royal marriage/native eligibility; cancel before ending NAV dependency; marriage/stability side effects not isolated by batch census.'),
 ('cancel_vassalization','NAV','cancel',[],'Fixture-established NAV vassal/client_vassal with target.overlord==FRA; never FOI appanage. Fresh type and direction are mandatory.'),
 ('dissolve_alliance','POR','cancel',['offer_alliance','offer_military_access','trade_favors_for_gold','cancel_military_access','revoke_military_access','cancel_fleet_basing_rights','revoke_fleet_basing_rights'],'Existing symmetric alliance; keep after friendly setup and access removals.'),
 ('revoke_embargo','ENG','cancel',['embargo'],'Only FRA outgoing embargo bit02 currently set; no successful cancellation from missing bit.'),
 ('offer_vassalization','POR','reply',['dissolve_alliance'],'No demonstrated suitable fresh target: NAV already our vassal and FOI appanage; POR/ENG native size/opinion/truce gates may reject. Last because an accepted new dependency changes later eligibility.')
)
PAIR_MAP={
 'offer_vassalization':'cancel_vassalization','royal_marriage':'break_marriage','improve_relations':'stop_improving_relations',
 'guarantee':'revoke_guarantee','build_spy_network':'stop_building_spy_network','offer_alliance':'dissolve_alliance',
 'ask_military_access':'cancel_military_access','offer_military_access':'revoke_military_access',
 'ask_fleet_basing_rights':'cancel_fleet_basing_rights','offer_fleet_basing_rights':'revoke_fleet_basing_rights',
 'embargo':'revoke_embargo','give_subsidies':'cancel_subsidies','form_coalition':'leave_coalition',
 'support_independence':'cancel_independence_support','request_trade_power':'cancel_trade_power_transfer','steer_trade':'cancel_steer_trade'}

def blob(path):
 with path.open('rb') as f:b=f.read(4*1024*1024+1)
 if len(b)>4*1024*1024:raise ValueError('Input over 4MiB')
 return b
def descriptor(b):return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def fixed_protocol():
 tree=ast.parse(blob(ROOT/INPUTS[0]).decode());found={}
 for n in tree.body:
  if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name):
   if n.targets[0].id=='ACTIONS':found['actions']=set(ast.literal_eval(n.value.args[0]))
   if n.targets[0].id=='FIXED_RESEARCH_PARAMETERS':found['parameters']=ast.literal_eval(n.value)
 return found

def validate(plan,protocol):
 if type(plan) is not dict or plan['actual_run_authorized'] is not False:raise ValueError('Offline only')
 rows=plan['rows'];seen=set()
 if len(rows)!=36:raise ValueError('Exactly 36')
 for position,row in enumerate(rows,1):
  if type(row['order']) is not int or row['order']!=position:raise ValueError('Strict order')
  if row['action'] in seen or row['action'] not in protocol['actions']:raise ValueError('Exact action IDs')
  if row['actor']!='FRA' or row['target'] not in ('ENG','POR','NAV','FOI'):raise ValueError('Fixed actor/target')
  if not set(row['after_attempts'])<=seen:raise ValueError('Dependency must precede attempt')
  if row['effect_verified'] is not False or row['retry_unknown'] is not False:raise ValueError('No effect promotion or unknown retry')
  if json.dumps(row['fixed_parameters'],sort_keys=True)!=json.dumps(protocol['parameters'].get(row['action'],{}),sort_keys=True):raise ValueError('Fixed parameters')
  if row['action'] in ('support_independence','cancel_independence_support') and row['submit_policy']!='guard_survey_only':raise ValueError('Own subject scope')
  seen.add(row['action'])
 if seen!=protocol['actions']:raise ValueError('Coverage')
 by={r['action']:r for r in rows}
 if by['improve_relations']['target']==by['build_spy_network']['target']:raise ValueError('Conservative persistent-mission exclusion')
 if by['cancel_vassalization']['target']!='NAV' or 'offer_vassalization' in by['cancel_vassalization']['after_attempts']:raise ValueError('Baseline NAV, not own positive POR')
 if plan['observations']['actual_default']!=['initial','final'] or plan['observations']['per_action_effect_verified'] is not False:raise ValueError('Final census contract')
 if plan['scheduler']['same_target_requirement']!='current_raw_date > last_native_target_threshold':raise ValueError('Strict native cooldown')
 if plan['scheduler']['max_inflight_requests']!=1 or type(plan['scheduler']['max_inflight_requests']) is not int:raise ValueError('Single native mailbox slot')
 return True

def generate():
 proto=fixed_protocol();rows=[];last={}
 for order,(action,target,mechanism,after,note) in enumerate(ROWS,1):
  policy='guard_survey_only' if action in ('support_independence','cancel_independence_support') else 'fresh_legality_then_submit_if_allowed'
  rows.append({'order':order,'action':action,'actor':'FRA','target':target,'mechanism':mechanism,
   'after_attempts':list(dict.fromkeys(after+([last[target]] if target in last else []))),'prior_same_target_action':last.get(target),'submit_policy':policy,
   'fixed_parameters':proto['parameters'].get(action,{}),'preconditions_and_limits':note,
   'allowed_rejection_is_coverage':True,'effect_verified':False,'retry_unknown':False})
  last[target]=action
 plan={'schema_version':1,'purpose':'offline_v17_fixed36_batch_test_matrix','actual_run_authorized':False,
  'protocol':'EU4LAB/3','families':20,'action_ids':36,'paired_families':16,'positive_only':['warn','insult','send_gift','trade_favors_for_gold'],
  'rows':rows,'pairs':PAIR_MAP,
  'scheduler':{'max_inflight_requests':1,'unallocated_live_sequences':True,'absolute_raw_dates_supplied':False,
   'same_target_requirement':'current_raw_date > last_native_target_threshold','cooldown_define_zero_is_not_same_day_permission':True,
   'cross_target_dispatch_before_shared_date_advance':True,'date_advance':'Only existing exact-process supervised bounded speed then healthy paused state; no active acceptance window.',
   'native_rejection':'Record completed legality/guard rejection; continue independent rows. Do not infer specific rejection cause from reason17 alone.',
   'ownership_unknown':'Permanently stop remaining batch; never retry or compensating cancel.',
   'fresh_law_each_row':True,'law_and_submit_same_paused_date':True,'status_log_ownership_check_each_request':True,
   'per_step_effect_observer':False,'automatic_acceptance_control':False,'automatic_fixture_toggle':False},
  'observations':{'actual_default':['initial','final'],'optional_positive_boundary_used_this_run':False,
   'semantics':'cross_date_selected_state_census','per_action_effect_verified':False,
   'legacy_same_date_comparison_allowed_for_cross_date_batch':False,'positive_cancellation_erases_positive_evidence':True,
   'mission_quantity':'100 added diplomats are a pool, not 100 distinct authorized targets or bypassed country cooldowns.',
   'final_scope':'Typed full identity plus selected final relations/tasks/insulted/trust/economy where supported; missing is not native rejection.',
   'normal_ai_acceptance_verified':False,'request_causality_verified':False,'whole_world_unchanged':False},
  'target_constraints':{
   'POR':'Independent-friendly candidate for most proposals; v14 ordinary offered fleet rejected, offered military worked only later after alliance. Current legality and AI response not inherited.',
   'ENG':'Hostile/unilateral and spy target candidate; native war/power/coalition gates may reject. No improve job to this same target.',
   'NAV':'Fixture vassal of FRA; suitable current-type checked cancellation baseline, not fresh positive vassalization or independent third-party support.',
   'FOI':'Source history is FRA appanage; only improve candidate here. Appanage is not recognized as ordinary vassal by current cancellation/support core.'},
  'unmet_scope_rows':['support_independence','cancel_independence_support'],
  'qualification_unknown_rows':['form_coalition','leave_coalition','trade_favors_for_gold','offer_vassalization'],
  'natural_ai_negative_candidate':['offer_fleet_basing_rights'],
  'ordering_notes':['Orders are topological recommendations, not request sequence IDs; each law and submit consumes separate canonical live sequence.',
   'Trade-power cancel precedes steering solely to maximize compatibility in this constrained test; not a newly claimed native exclusion.',
   'Vassal positive POR and cancellation NAV intentionally exercise different prerequisites; never call this a positive/cancel round trip.',
   'Independent rows on other targets may run before a shared supervised date advance; do not wait for used diplomats to return when free ones exist.',
   'Fixture on is not repeated. Fixture off stays outside batch until persistent missions are stopped and final census captured.']}
 validate(plan,proto)
 inputs={name:descriptor(blob(ROOT/name)) for name in INPUTS}
 if sum(d['bytes'] for d in inputs.values())>12*1024*1024:raise ValueError('Total source budget')
 return plan,{'schema_version':1,'files':inputs,'no_process_access':True}
def main():
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');args=p.parse_args()
 for name,value in zip(('plan.json','input-pins.json'),generate()):
  data=(json.dumps(value,sort_keys=True,ensure_ascii=False,indent=2)+'\n').encode()
  path=HERE/name
  if args.check:
   if blob(path)!=data:raise ValueError('Changed '+name)
  else:
   with path.open('xb') as f:f.write(data)
 print(json.dumps({'checked':True,'actions':36,'observations':['initial','final'],'effect_verified':False,'game_accessed':False}))
if __name__=='__main__':main()
