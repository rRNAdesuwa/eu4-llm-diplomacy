"""Bounded offline catalog/set/descriptor review; never runs a game CLI."""
from pathlib import Path
from collections import Counter
import argparse
import ast
import hashlib
import json
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
MAX_FILE=4*1024*1024
MAX_TOTAL=16*1024*1024
INPUTS=(
    'bridge/diplomacy_catalog.json','bridge/diplomacy_api.py','bridge/diplomacy_service.py',
    'bridge/diplomacy_research_capabilities.py','bridge/diplomacy_research_evidence.json',
    'bridge/native_pair_backend.py','bridge/diplomacy_lab_http.py','bridge/diplomacy_lab_http_v17.py',
    'tools/diplomacy.py','work/native/lab_protocol_v17_1375.py',
    'docs/diplomacy-api.md','docs/native-pair-adapter-1375.md',
    'docs/native-subject-interactions-1375.md','docs/native-subject-special-paths-1375.md',
    'docs/native-diplomacy-modes-1375.md',
    'work/reports/native-subject-interactions-1375.json',
    'work/reports/native-subject-special-paths-1375.json','work/reports/native-diplomacy-modes-1375.json',
    'work/candidates/spy-action-contracts-1375/report.json','work/candidates/spy-action-contracts-1375/review.json',
)
MAPPINGS=('native_mapping','native_subject_mapping','native_special_mapping','native_peace_mapping')


def bounded(path,limit=MAX_FILE):
    with path.open('rb') as f:value=f.read(limit+1)
    if len(value)>limit:raise ValueError('Input bound: '+str(path))
    return value


def descriptor(raw):
    return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def summarize():
    files={name:bounded(ROOT/name) for name in INPUTS}
    assert sum(map(len,files.values()))<=MAX_TOTAL
    # Imports define classes/constants only. Never construct an API, open a DB,
    # inspect a process, invoke a CLI, or call build/capability discovery.
    sys.path.insert(0,str(ROOT))
    from bridge import diplomacy_research_capabilities as discovery
    from bridge.diplomacy_api import DiplomacyAPI
    catalog=json.loads(files[INPUTS[0]])
    actions={a['action_id']:a for a in catalog['actions']}
    assert len(actions)==len(catalog['actions'])==274
    lab_tree=ast.parse(files['work/native/lab_protocol_v17_1375.py'])
    literal=next(n.value for n in lab_tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ACTIONS' for t in n.targets))
    assert isinstance(literal,ast.Call) and isinstance(literal.func,ast.Name) and literal.func.id=='frozenset'
    research=frozenset(ast.literal_eval(literal.args[0]))
    assert research==discovery.V12_ACTIONS and len(research)==36
    bindings=discovery.V12_CATALOG_BINDINGS
    covered=frozenset(x for values in bindings.values() for x in values)
    assert len(covered)==37 and covered<=actions.keys()
    remaining=actions.keys()-covered
    native={n for n,a in actions.items() if any(a.get(k) for k in MAPPINGS)}
    assert len(native)==270 and len(remaining)==237
    # Execute the actual no-backend readiness method with an explicit constant
    # build; the no-backend branch performs no DB or backend call.
    api=object.__new__(DiplomacyAPI);api.backend=None
    statuses={n:api._readiness(a,{'sha256':discovery.LOCAL_SHA256,'status':'static_analysis_only'}) for n,a in actions.items()}
    blockers=Counter(b['code'] for s in statuses.values() for b in s['blockers'])
    assert all(s['execution_allowed'] is False for s in statuses.values())
    history=json.loads(files['bridge/diplomacy_research_evidence.json'])
    effects=sorted({identifier for r in history['observations'] if r['claims'].get('observed_state_change') is True
        for identifier in bindings.get(r['action_id'],[r['action_id']]) if identifier in actions})
    assert len(effects)==28 and history['production_whitelist']==[]
    recommendations=json.loads(bounded(HERE/'recommendations.json',65536))
    ids=[n for r in recommendations['recommendations'] for n in r['action_ids']]
    assert len(ids)==len(set(ids))==6 and set(ids)<=remaining
    assert not set(ids)&set(recommendations['excluded_already_researched_spy_ids'])
    for n in ids:
        assert actions[n]['parameter_status']=='specified' and actions[n]['execution']['status']=='unimplemented'
        assert actions[n]['parameters']['additionalProperties'] is False
    for n in ('subject.scutage','subject.divert_trade','subject.embargo_rivals'):
        assert actions[n]['parameters']['properties']['enabled']=={'type':'boolean'}
    assert actions['subject.set_military_focus']['native_special_mapping']['enum_mappings']['focus']==dict(no_focus=0,aggressive=1,supportive=2,passive=3,defensive=4,siege=5)
    for n in ids:
        for k in MAPPINGS:
            reference=actions[n].get(k,{}).get('source_report')
            if reference:
                assert descriptor(files[reference['path']])['sha256'].upper()==reference['sha256'].upper()
    rows=[]
    for n in sorted(remaining):
        a=actions[n]
        rows.append({'action_id':n,'surface':a['surface'],'parameter_status':a['parameter_status'],
            'static_mapping_fields':[k for k in MAPPINGS if a.get(k)],
            'execution_allowed':False,'blocker_codes':[b['code'] for b in statuses[n]['blockers']]})
    return {'schema_version':1,'purpose':'bounded_remaining_diplomacy_interface_scope_review',
        'process_access':False,'game_cli_invoked':False,'native_code_added':False,'production_registered':False,
        'current_game_sha256':discovery.LOCAL_SHA256,'input_hashes':{n:descriptor(b) for n,b in files.items()},
        'total_input_bytes':sum(map(len,files.values())),'limits':{'per_file_bytes':MAX_FILE,'total_bytes':MAX_TOTAL},
        'counts':{'catalog':len(actions),'static_union':len(native),'research_entrypoints':len(research),
            'catalog_bindings':len(covered),'raw_name_intersection':len(actions.keys()&research),
            'raw_name_difference':len(actions.keys()-research),'semantic_remaining':len(remaining),
            'remaining_mapped':len(remaining&native),'remaining_unmapped':len(remaining-native),
            'historical_effect_actions_from_index':len(effects),'production_execution':0},
        'alias_bindings':{k:v for k,v in bindings.items() if v!=[k]},
        'alias_limit':'A discovery binding does not prove both cancellation roles or effects.',
        'all_mapping_counts':{k:sum(bool(a.get(k)) for a in actions.values()) for k in MAPPINGS},
        'remaining_mapping_counts':{k:sum(bool(actions[n].get(k)) for n in remaining) for k in MAPPINGS},
        'remaining_surface_counts':dict(sorted(Counter(actions[n]['surface'] for n in remaining).items())),
        'remaining_parameter_counts':dict(sorted(Counter(actions[n]['parameter_status'] for n in remaining).items())),
        'all_production_blocker_counts':dict(sorted(blockers.items())),
        'unmapped_action_ids':sorted(actions.keys()-native),'research_action_ids':sorted(research),
        'remaining':rows,'recommendations':recommendations,
        'selected_catalog_contracts':{n:{k:v for k,v in actions[n].items() if k in ('parameters','parameter_status','execution',*MAPPINGS)} for n in ids},
        'interface_contract':{
            'production_routes':{'GET':['/v1/capabilities','/v1/actions/{action_id}','/v1/requests/{request_id}','/v1/requests/{request_id}/events'],
                'POST':['/v1/preview','/v1/requests','/v1/requests/{request_id}/reconcile']},
            'production_preview':'contract_only; no native legality/AI acceptance/envoy query',
            'production_submit':'all 274 currently unsupported; reason durably recorded, no backend registered',
            'reconcile':'read-only evidence reconciliation, not resend; unknown holds persist',
            'research_routes':{'GET':['/research/v17/capabilities','/research/v17/status','/research/v17/requests/{sequence}'],'POST':['/research/v17/pair']},
            'research_protocol':'EU4LAB/3','research_purpose':'restricted_pair_lab_1375_v17',
            'research_pair_scope':'36 fixed IDs; strict typed 13-field wire; bound process/session; actor FRA for submit; fixed scalar parameters',
            'not_exposed_over_http':['fixture','speed','stage','load','reset','accept_on','accept_off','production_submit'],
            'semantic_boundaries':['schema specified is not verified native argument binding','static mapped is not executable','legality allowed is not AI acceptance','native ownership returned is not observed effect','initial/final batch census is not per-action effect proof']},
        'historical_index_limit':'Only pinned index metadata was read; its 876 referenced artifacts and large saves were not re-audited or promoted in this study.',
        'completeness_limit':'274 is the current reconciled catalog, not proof that all EU4 behaviors or every script-defined action are enumerated.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True);group.add_argument('--create',action='store_true');group.add_argument('--check',action='store_true')
    args=parser.parse_args();value=summarize();path=HERE/'report.json'
    raw=(json.dumps(value,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode('ascii')
    assert len(raw)<=512*1024
    if args.check:assert bounded(path,512*1024)==raw,'Report or pinned inputs changed'
    else:
        with path.open('xb') as f:f.write(raw)
    print(json.dumps({'counts':value['counts'],'report':descriptor(raw),'input_bytes':value['total_input_bytes'],'process_access':False}))


if __name__=='__main__':main()
