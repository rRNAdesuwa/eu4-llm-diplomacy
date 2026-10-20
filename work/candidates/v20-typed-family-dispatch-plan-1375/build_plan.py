"""Bounded documentation generator. Never imports a game/runtime/API module."""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LIMIT = 4 * 1024 * 1024
INPUTS = (
    'bridge/diplomacy_research_capabilities.py',
    'bridge/diplomacy_research_evidence.json',
    'bridge/diplomacy_catalog.json',
    'bridge/diplomacy_contract_v2_bindings.json',
    'work/native/v17/pair-engine-1375.h',
    'work/native/v17/pair-engine-1375.cpp',
    'work/candidates/v17-batch-action-matrix-1375/plan.json',
    'work/reports/native-diplomacy-1.37.5.json',
    'work/reports/native-pair-cancel-1375.json',
    'work/reports/native-pair-extension-v10-1375.json',
    'work/reports/native-pair-extension-v11-1375.json',
    'work/reports/native-coalition-queue-1375.json',
    'work/candidates/v19-spy-send-core-1375/spy_send_core.h',
    'work/candidates/v19-spy-send-core-1375/spy_send_core.cpp',
    'work/candidates/v19-spy-send-core-1375/review.json',
    'work/candidates/v19-spy-send-context-pins-1375/contract.py',
    'work/candidates/v19-spy-send-context-pins-1375/sender-pins.h',
    'work/candidates/v19-spy-send-context-pins-1375/review.json',
    'work/candidates/v19-spy-restricted-host-r2-1375/review.json',
    'work/review-results/v19-host-r2-native-inventory-20261008a/review.json',
    'work/review-results/v19-spy-send-core-native-inventory-20261008a/review.json',
    'work/candidates/spy-action-contracts-1375/report.json',
    'work/candidates/spy-four-normal-callers-contract-1375/report.json',
    'work/candidates/curry-favors-contract-1375/contract.json',
    'work/candidates/curry-favors-contract-1375/report.json',
    'work/candidates/subject-military-focus-contract-1375/contract.json',
    'work/candidates/subject-toggle-contracts-1375/contract.json',
    'work/candidates/spy-extra-parameter-contracts-1375/report.json',
    'work/candidates/spy-extra-parameter-contracts-1375/facts.json',
    'work/candidates/favor-break-alliance-contract-1375/report.json',
    'work/candidates/favor-exchanges-contract-1375/report.json',
    'work/candidates/war-dynasty-province-contracts-1375/report.json',
    'work/candidates/war-dynasty-province-contracts-r2-1375/review.json',
    'work/candidates/favor-trust-reduce-bindings-1375/report.json',
    'work/candidates/ten-families-typed-contract-r2-1375/contract.json',
    'work/candidates/ten-families-typed-contract-r2-1375/static-binding-index.json',
    'work/candidates/ten-families-typed-contract-r2-1375/formal-api-diff.json',
    'work/candidates/ten-families-typed-contract-r2-1375/review.json',
)

def read(name):
    with (ROOT / name).open('rb') as stream:
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError('Input byte budget exceeded: ' + name)
    return raw

def parsed(name):
    return json.loads(read(name))

def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')

def describe_inputs():
    result = []
    total = 0
    for name in INPUTS:
        raw = read(name)
        total += len(raw)
        if total > 32 * 1024 * 1024:
            raise ValueError('Aggregate input byte budget exceeded')
        result.append({'path': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    return result

def slot_key(value):
    return int(value, 16)

def base_registry():
    cpp = read('work/native/v17/pair-engine-1375.cpp').decode('utf-8')
    block = cpp.split('constexpr Action kActions[] = {', 1)[1].split('\n};', 1)[0]
    items = re.findall(r'\{(0x[0-9a-f]+), (0x[0-9a-f]+), (0x[0-9a-f]+), (0x[0-9a-f]+), (0x[0-9a-f]+), (0x[0-9a-f]+), (0x[0-9a-f]+), (0x[0-9a-f]+), (0x[0-9a-f]+), (0x[0-9a-f]+),', block)
    names = re.findall(r'"([a-z_]+)"', cpp.split('constexpr const char* kNames[] = {', 1)[1].split('};', 1)[0])
    modes = re.findall(r'\{(\d+), (true|false)\}', cpp.split('constexpr ModeMapping kModes[] = {', 1)[1].split('};', 1)[0])
    if len(items) != 20 or len(names) != 36 or len(modes) != 36:
        raise ValueError('Frozen research table changed')
    inventory = parsed('work/reports/native-diplomacy-1.37.5.json')['native_actions']['actions']
    native = {a['token_id']: a for a in inventory}
    registry = []
    for index, row in enumerate(items):
        token, size, vt, clone, dtor, getter, local, envoy_pred, favor_pred, setter = row
        entry = native[int(token, 16)]
        slots = entry['slots']
        if int(vt, 16) != int(entry['vtable_rva'], 16) or int(clone, 16) != int(slots['0xb0'], 16):
            raise ValueError('Research/inventory identity conflict')
        mapped = [{'protocol_id': name, 'catalog_ids': catalog_ids(name), 'native_value': value == 'true'}
                  for name, (family, value) in zip(names, modes) if int(family) == index]
        registry.append({
            'family': entry['name'], 'token': token, 'size_bytes': int(size, 16), 'vtable_rva': vt,
            'modes': mapped, 'object_kind': 'owned_action_then_0x58_command',
            'action_wrapper_rva': slots['0x40'], 'clone_rva': clone, 'destructor_rva': dtor,
            'family_local_0x80_rva': slots['0x80'], 'family_full_0x88_rva': slots['0x88'],
            'mode_setter_rva': setter, 'command_gate_rva': '0x4e8630',
            'v17_preview_used': 'generic_0x4e9d00_not_family_full_0x88',
            'full_preview_evidence': 'static_slot_mapping_only_unless_supplemented_by_specific_caller',
            'profile_action': 'adapt_existing_owned_cpp_with_new_family_full_preview_preflight',
            'native_ready': False, 'production_ready': False,
            'initial_state': 2 if token == '0x2de0' else 0,
            'extra_and_cancel_contract': notes(index),
        })
    return registry, names

def catalog_ids(name):
    return {'request_trade_power': ['transfer_trade_power'],
            'cancel_independence_support': ['cancel_offered_independence_support', 'cancel_requested_independence_support']}.get(name, [name])

def notes(index):
    return {
        0: ['value=false cancels only a current exact vassal/client_vassal dependency; appanage/union excluded', 'target.overlord must equal actor full handle; positive offer is a proposal, not forced vassal creation'],
        1: ['0x68 object has EngineString32 +0x40 and force byte +0x60', 'factory/clone require empty SSO string and force=false; preview original may hold bounded string; clone resets instead of copying it', 'use 0x4ed5b0 destructor; never overwrite/free its String32 from the host'],
        2: ['both modes retain envoy=-1; cancellation relation destructor recalls its mission', 'native false mode is not spy envoy binding'],
        3: ['false requires exact paired guarantee relation, actor guarantor and target beneficiary'],
        4: ['false invokes 0x586330 setter after full identities', 'stop mode needs unique live envoy/mission/task graph and signed nonnegative int32 envoy_id, privately resolved and rechecked; never accept it publicly'],
        5: ['false requires one shared active alliance object in both indices, not a prior dispatched positive receipt'],
        6: ['actor is rights holder; target provider; false revokes actor-held right'],
        7: ['actor is provider; target holder; false expels target-held right'],
        8: ['actor is fleet rights holder; target provider; false cancels actor-held right'],
        9: ['actor is fleet provider; target holder; false expels target-held right; a refused offer creates nothing to revoke'],
        10: ['false requires actor-to-target outgoing embargo bit; inverse direction is different'],
        11: ['+0x40 int32 monthly milli currency=1000; +0x44 int32 duration YEARS=10 in old research', 'false binds exact active subsidy object with those parameters; arbitrary amounts/years need a new versioned profile'],
        12: ['true only; requires no existing warning in either indexed direction; no undo invented'],
        13: ['+0x40 signed definition index fixed -1 ordinary insult; scornful index registry unsupported'],
        14: ['factory/default/normal AI initialized state=2, unlike other families; false only leaves exact current target coalition', 'membership linked-list identity/count/flags must be privately rechecked'],
        15: ['two catalog cancellation aliases share one protocol ID; actor-dependent and actor-provider branches are distinct runtime qualifications', 'requires exactly one dependent, independent supporter different from its overlord, and exact vassal/client_vassal definition; self-overlord NAV fixture is invalid'],
        16: ['+0x40 int32 fraction=500; +0x44 byte flag=0', 'true receives from target; false requires exactly one unambiguous existing direction and 500/flag0'],
        17: ['false requires one unambiguous existing direction and ordinary flag0; do not infer from proposal order'],
        18: ['+0x40 int32 amount=25000 milli currency; true only; arbitrary caller amount outside current research'],
        19: ['no amount extra; native calculates transfer dynamically; true only; favor/opinion/resource prerequisites remain native'],
    }[index]

def supplement():
    typed = parsed('work/candidates/ten-families-typed-contract-r2-1375/contract.json')['actions']
    binding = parsed('work/candidates/ten-families-typed-contract-r2-1375/static-binding-index.json')['actions']
    result = []
    for name, record in typed.items():
        result.append({'group': name, 'actions': [name], 'kind': 'owned_pair_action',
            'public_parameters': record['parameters'], 'constraints': record['constraints'],
            'descriptor': binding[name]['native_descriptor'],
            'normal_full_preview_caller_closed': record['normal_full_preview_caller_closed'],
            'profile_action': 'trace_normal_full_preview_path_before_live_profile' if name == 'threaten_war' else 'implement_typed_owned_profile_and_private_resolver',
            'extra_rule': extra_rule(name), 'evidence': record['evidence'],
            'native_ready': False, 'production_ready': False})
    result += [
        {'group': 'spy5', 'actions': ['corrupt_officials', 'sabotage_reputation', 'sow_discontent', 'slander_merchants', 'sabotage_recruitment'],
         'kind': 'owned_pair_action', 'profile_action': 'reuse_exact_v19_profile_implementation_only',
         'extra_rule': '0x40 true/state0/envoy-1; five individually evidenced normal callers; fixed FRA/ENG and same-date host cannot silently accept new targets or batches',
         'normal_full_preview_caller_closed': True, 'native_ready': False, 'production_ready': False},
        {'group': 'curry', 'actions': ['curry_favors', 'stop_currying_favors'], 'kind': 'owned_pair_action',
         'profile_action': 'implement_new_0x40_pair_profile_from_sealed_contract',
         'descriptor': {'token': '0x3acc', 'size_bytes': 64, 'vtable_rva': '0x1c7aef8', 'clone_rva': '0x5ae2b0', 'family_full_0x88_rva': '0x5ae110'},
         'extra_rule': 'both modes envoy=-1; exact outgoing relation/mission graph for stop; full +88 separate from generic and command gate',
         'normal_full_preview_caller_closed': True, 'native_ready': False, 'production_ready': False},
        {'group': 'subject_focus', 'actions': ['subject.set_military_focus'], 'kind': 'already_command_0x60',
         'profile_action': 'new_command_profile_not_pair_wrapper',
         'descriptor': {'token': '0x3017', 'size_bytes': 96, 'vtable_rva': '0x1c54678', 'constructor_rva': '0x2b2850', 'gate_rva': '0x2b2b30', 'clone_rva': '0x2b2a70', 'destructor_rva': '0x98940'},
         'extra_rule': '+50 full subject handle/+58 focus DWORD; clone(source,owned temporary String32*) consumes argument, not NULL; no-focus=0 is a mode, not undo; native gate lacks overlord authority',
         'normal_full_preview_caller_closed': None, 'native_ready': False, 'production_ready': False},
        {'group': 'subject_toggles', 'actions': ['subject.embargo_rivals', 'subject.scutage', 'subject.divert_trade'], 'kind': 'borrowed_singleton_owned_command_0xa0',
         'profile_action': 'new_command_profile_not_pair_wrapper',
         'descriptor': {'command_token': '0x31d8', 'size_bytes': 160, 'vtable_rva': '0x1c3a650', 'constructor_rva': '0xaf3860', 'gate_rva': '0xaf3e20', 'clone_rva': '0xaf3b70', 'destructor_rva': '0xa7180'},
         'extra_rule': 'desired enabled strict bool; already_desired=no constructor; +90 cancel snapshots current +78 family mask and overlord high byte; +98 borrowed singleton never free; clone consumes temporary String32 and deep-copies +70; GUI raw-pointer 14ca2d0 is NOT container submit 14ca210',
         'normal_full_preview_caller_closed': None, 'native_ready': False, 'production_ready': False},
        {'group': 'steal_maps', 'actions': ['steal_maps'], 'kind': 'owned_pair_action_selected_region',
         'profile_action': 'private_region_registry_resolver_before_live_profile',
         'extra_rule': 'region_index int32 nonnegative; +40 DWORD, -1 factory default not a selected region; false is not undo',
         'normal_full_preview_caller_closed': True, 'native_ready': False, 'production_ready': False},
        {'group': 'support_rebels', 'actions': ['support_rebels', 'stop_supporting_rebels'], 'kind': 'owned_pair_action_borrowed_faction',
         'profile_action': 'caller_tracing_and_borrowed_lifetime_required',
         'extra_rule': 'two public faction uint32 identities require exact target-vector/type/supporter resolution; +40 is borrowed pointer, cloned but never freed; selected normal owning caller unclosed; false full preview rejects and effect selects first matching supporter, so stop remains unsupported',
         'normal_full_preview_caller_closed': False, 'native_ready': False, 'production_ready': False},
        {'group': 'scripted_modernization', 'actions': ['steal_modern_ideas'], 'kind': 'owned_pair_action_borrowed_definition',
         'profile_action': 'definition_resolver_lifetime_and_specific_script_profile_required',
         'extra_rule': 'only stock named Russian modernization action token0x3662; not generic technology theft; +40 borrowed definition; lazy registry getter is not read-only',
         'normal_full_preview_caller_closed': False, 'native_ready': False, 'production_ready': False},
        {'group': 'favor_break_alliance', 'actions': ['break_alliance_favor'], 'kind': 'owned_pair_action',
         'profile_action': 'pin_factory_token_dispatch_then_three_country_profile',
         'descriptor': {'token': '0x3bcb', 'size_bytes': 72, 'vtable_rva': '0x1c3e438', 'clone_rva': '0x7ca3e0', 'family_full_0x88_rva': '0x7ca480'},
         'extra_rule': '+40 full third-country value; distinct ordinary0x3375; normal AI full88/owned queue closed but factory arithmetic dispatch and complete accepting multi-relation side-effects not closed; no false/cancel/state2',
         'normal_full_preview_caller_closed': True, 'native_ready': False, 'production_ready': False},
    ]
    return result

def extra_rule(name):
    if name == 'claim_throne': return '0x40; true/state0/envoy-1; no reply-state bypass; one-direction mask1 claim observation only'
    if name == 'sell_province': return '+40 int32 INTEGER gold 0..2147483; +44 province int32>0; accepted effect multiplies by1000; private loaded province registry/owner resolver missing'
    if name == 'enforce_peace': return '+40 QWORD opposing country, not war_id; rejection may join war; requires separate war-scope fixture and observer'
    if name == 'threaten_war': return '+40 DWORD province; +44 UNALIGNED QWORD taker==actor; normal caller uses local80 before wrapper/bfe50, not proven full88; refusal may declare war'
    if name == 'reduce_relations_favor': return '+40 full third-country from normal GUI; GUI local80 mutable text vs AI full88 NULL; distinct three identities/private resolver required'
    if name == 'trade_favors_for_trust': return 'factory current signed32 global233db7c*1000 at+40, global233db80 at+44; read current authenticated values, no stock10/5 or caller amount; source secondary factory date must not be silently rewritten'
    return 'no free amount extra; normal AI writes source primary date only, clone dates both source primary then wrapper secondary current; native resource amount/permission remains dynamic'

def documents():
    registry, ids = base_registry()
    catalog = parsed('bridge/diplomacy_catalog.json')['actions']
    catalog_set = {v['action_id'] for v in catalog}
    binding_map = {name: catalog_ids(name) for name in sorted(ids)}
    bindings = {n for names in binding_map.values() for n in names}
    if len(bindings) != 37 or not bindings <= catalog_set:
        raise ValueError('Expected 36 protocol IDs / 37 catalog bindings')
    # Validate the source aliases without importing a mutable API module.
    cap = read('bridge/diplomacy_research_capabilities.py').decode('utf-8')
    expected_alias = {
        'request_trade_power': ['transfer_trade_power'],
        'cancel_independence_support': ['cancel_offered_independence_support', 'cancel_requested_independence_support'],
    }
    found = {}
    for node in ast.parse(cap).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id == 'V12_CATALOG_BINDINGS':
                found[ast.literal_eval(target.slice)] = ast.literal_eval(node.value)
    if found != expected_alias: raise ValueError('Discovery alias contract changed')
    plan = {
        'schema_version': 1, 'purpose': 'typed_family_dispatch_design_only_1375',
        'game_sha256': '9AD3EFE1AF169F40EE577F9DAE5DEBBC87AF6FB8B5450FB345EBF110DC4D771A',
        'new_decode_bytes': 0, 'production_ready': False, 'native_ready': False,
        'runtime_calls_made': False, 'profile_implementation_created': False,
        'world_epoch_verified': False, 'strict_single_player_verified': False,
        'historical_effects_promoted': False,
        'counts': {'catalog_total': len(catalog), 'catalog_static_mapped': sum(any(v.get(k) for k in ('native_mapping','native_subject_mapping','native_special_mapping','native_peace_mapping')) for v in catalog),
                   'lab_protocol_ids': len(ids), 'lab_native_families': len(registry), 'catalog_lab_bindings': len(bindings),
                   'formal_v2_typed_extensions': len(parsed('bridge/diplomacy_contract_v2_bindings.json')['actions']), 'separate_ten_family_draft': 10},
        'catalog_bindings': binding_map,
        'requested_role_cancel_not_independently_runtime_qualified': ['cancel_requested_independence_support', 'cancel_offered_independence_support'],
        'remaining_without_lab_binding': sorted(catalog_set - bindings),
        'private_chain': ['resolve authenticated current country/province/definition handles', 'fixed profile factory/default check', 'only owned exact field writes and explicit native setter', 'family full+88(NULL,false), separately logged', '4e9930 wrapper creates independent clone and 0x58 command', '4e8630 command gate, separately logged', 'destroy independent original normally', 'durable unique dispatch intent', 'exact context/owned graph readback and last fresh owner barrier', '14ca210(context,command**) with irreversible ownership relinquishment', 'normal ALtrue+slotNULL means dispatched only', 'independent later owner health before next item'],
        'chain_exclusions': ['already-command subject families use different constructor/clone/gate and are never passed to 4e9930', 'family full88 is not action generic80/4e9d00 or command40', 'no execute/transport direct call/consumer/queue drain', 'no public pointer/RVA/token/state/envoy/force/value/ready or source path', 'no application-level retry after native entry or ownership uncertainty'],
        'public_contract': {
            'shape': ['protocol_version', 'request_id', 'action', 'parameters'],
            'protocol_status': 'future_version_selection_required_not_registered',
            'tag': 'exact string /^[A-Z0-9]{3}$/; actor must resolve to current/effective player; syntactic validity never proves country existence',
            'province_id': 'exact integer 1..2147483647; bounded loaded registry membership, identity and full owner handles must be resolved privately; no bool coercion',
            'unknown_keys': 'reject; do not silently translate V1/V2 conflicting price/war/trust fields',
            'parameters_binding': 'copy fixed schema per profile; same request_id plus canonical public payload persistent conflict rule only in future authenticated research service',
            'private_resolution': ['hash+PE+PIDcreation+session+actual owner thread and paused state', 'DB118/124 bounds, full country20 handle and generation, unique TAG match, full current/effective player', 'snapshot before/after root/date/identity and immediate owner-call final guard', 'private references cannot survive unproven reload/epoch change; two-pass equality is not an engine lifetime lock'],
            'v17_fixed_extras_remain_fixed': {'subsidy_milli': 1000, 'subsidy_years': 10, 'gift_milli': 25000, 'trade_fraction_milli': 500, 'ordinary_insult_index': -1},
        },
        'minimum_37_binding_gaps': [
            {'id': 'R1', 'work': 'Build a versioned private profile registry from exact20 families/36 modes, preserve field widths/clone/default differences, no mutable formal API runtime import.'},
            {'id': 'R2', 'work': 'Replace five-tag constant resolver with bounded authenticated TAG→current fullhandle resolution, retaining actor authority; add province/borrowed-definition resolvers only per proven family.'},
            {'id': 'R3', 'work': 'Authenticate per-profile lifecycle/full88/command preflights and independent later owner health in the new Host; old generic-only preview is not new full-preview success.'},
            {'id': 'R4', 'work': 'Bind cancellation current relations/tasks and dynamic envoy inside the owner call; separate offered/requested independence roles instead of claiming37 runnable directions.'},
            {'id': 'R5', 'work': 'Provide separate research protocol/consumer and durable request_id ledger linked to process/session/profile payload; descriptor/unsupported V2 request is not queued.'},
            {'id': 'R6', 'work': 'Keep legality, dispatched, reply and observed state separate; native false gate is valid refusal, unknown freezes current item and is never retried.'},
            {'id': 'R7', 'work': 'Use initial/final aggregate observations only for batch selected-state coverage; retain intermediate positive unobserved when cancellations erase it.'},
            {'id': 'R8', 'work': 'Production additionally requires true lifetime/epoch invalidation and strict SP provenance; the restricted research host does not establish either.'},
        ],
        'batch_groups': [
            {'id': 'A_pair_core', 'priority': 1, 'scope': 'marriage, improvement, guarantee, spy-network, vassal proposal/cancel plus curry',
             'fixture': 'new disposable reviewed world; independent POR for proposals, ENG spy, FOI improvement; NAV current true vassal only for cancel. Targets are planned roles, not observed live facts.',
             'order': 'fixed positives and later qualified cancellations with owner-health and needed supervised date advance. Preexisting guarantee/marriage/dependency graphs must not be inferred from returned submit.',
             'observation': 'one initial plus one final group; no per-item effect sampling; ended tasks/removed relations cannot prove intermediate creation', 'individual_effect_verified': False},
            {'id': 'B_rights_trade_resources', 'priority': 2, 'scope': 'existing otherpair directional rights, alliance, embargo, fixed subsidies/trade/gift and no-extra favors',
             'fixture': 'reviewed bilateral identities, resource/favor availability; rights holder/provider separate; trade transfer and steer not assumed compatible; leave failed permission as known rejection.',
             'order': 'fresh legal check per item, strict-next sequences without rejection holes; cleanup only if live matching relation; no accept-all or arbitrary amount expansion',
             'observation': 'initial/final only; cross-date state census is not same-day per-action delta/cost attribution', 'individual_effect_verified': False},
            {'id': 'C_subject_separate_command', 'priority': 3, 'scope': 'military focus six enum values and three desired-state toggles',
             'fixture': 'exact direct subject dependency/definition and current flags; both focus permission bytes and enum entitlement; scutage target not at war; embargo enabling requires actual actor rivals.',
             'order': 'separate command-profile no-send phases first; then finite desired transitions with already_desired no-native result. No borrowed singleton free or implicit reset.',
             'observation': 'initial/final only; final focus proves selected final state, not all six interim settings; toggle side effects may survive off', 'individual_effect_verified': False},
            {'id': 'D_deferred_parameterized', 'priority': 4, 'scope': 'WAR4, three-country favors, selected map/faction/scripted actions',
             'fixture': 'do not combine warfare-triggering refusals with peaceful batch; independent province/war/third-country and borrowed-lifetime fixtures required',
             'order': 'resolve specific blockers before dispatch; threaten full-preview caller, support-rebels owning caller and borrowed lifetime, scripted registry selection, favor-break factory dispatch remain finite tracing gaps',
             'observation': 'initial/final aggregate observers for province/war/third-country state required; request return never substitutes', 'individual_effect_verified': False},
        ],
        'runtime_authority': 'none; source descriptions and historical evidence are not a live authorization or production whitelist',
    }
    return {'plan.json': plan, 'abi-registry.json': {'schema_version': 1, 'research_families': registry, 'supplemental_groups': supplement(), 'production_ready': False, 'runtime_verified': False}}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--check', action='store_true'); args = ap.parse_args()
    pins = describe_inputs()
    result = documents()
    result['input-pins.json'] = {'schema_version': 1, 'role': 'audit_source_snapshot_not_future_runtime_dependency', 'inputs': pins,
        'limits': {'input_count': 64, 'single_input_bytes': LIMIT, 'total_input_bytes': 32*1024*1024}}
    for name, value in result.items():
        raw = canonical(value); path = HERE / name
        if args.check:
            if path.read_bytes() != raw: raise ValueError('Candidate differs: ' + name)
        else:
            with path.open('xb') as stream: stream.write(raw)
    if pins != describe_inputs(): raise ValueError('Inputs changed during generation/check')
    print(json.dumps({'check': args.check, 'source_count': len(pins), 'source_bytes': sum(x['bytes'] for x in pins),
                      'counts': result['plan.json']['counts'], 'new_decode_bytes': 0, 'process_accessed': False}))

if __name__ == '__main__': main()
