"""Build a file-only discovery map; it grants no process or action authority."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'docs/runtime-capability-map-1375.json'
TOOLS=[
 dict(id='original_effects_and_current_relations_wars',entry='tools/eu4_observer.py',
    manifest='bridge/eu4_observer_manifest_1375.json',manifest_sha='23c6831a861425c5f3012b583c93c6c1ccf7d10c769f9a23389474d389c9b361',
    guide='docs/runtime-observer-1375.md',scope='15 original-request effect profiles; current alliance, marriage, guarantee and complete current war graph',
    request_effect_profile_count=15,original_receipt_and_prebaseline_required_for_effects=True,request_causality_from_current_state_alone=False),
 dict(id='integration_current_task',entry='work/candidates/integration-task-observer-1375-v1/integration_task_observer.py',
    manifest='work/candidates/integration-task-observer-1375-v1/source-manifest.json',manifest_sha='4b17a5862dbe4461497c6d187d6cb9dc0efb16a489fbb7048f6658ca5794cb9e',
    guide='work/candidates/integration-task-observer-1375-v1/STATUS.md',scope='selected current task presence, selected index absence, or unknown',
    request_effect_profile_count=0,action_labels_for_reference=['integrate_union','cancel_integration'],
    real_capture_scope='FRA-ORL and DAN-NOR selected-index absence only; no active taskbody sample',integration_completion_verified=False),
 dict(id='linked_truce_conditional_projection_v2',entry='work/candidates/linked-truce-projection-1375-v2/linked_truce_projection.py',
    manifest='work/candidates/linked-truce-projection-1375-v2/source-manifest.json',manifest_sha='15a221ec3eb1d63f1598a9c5305d2cbfd50b7e2c8492fbb10ce695b27b28ee93',
    guide='work/candidates/linked-truce-projection-1375-v2/STATUS.md',scope='four selected external normal-return path projections; other paths unknown',
    request_effect_profile_count=0,path_count=4,actual_native_predicate_evaluated=False,complete_truce_or_expiry_verified=False,
    real_capture_scope='v1 A/B paths retained; v2 new D POR-ORL once, false; C covered offline only'),
 dict(id='directional_truce_cache',entry='work/candidates/direct-truce-cache-cli-1375-v1/direct_truce_cache.py',
    manifest='work/candidates/direct-truce-cache-cli-1375-v1/source-manifest.json',manifest_sha='47cfc947bac30cf47eaf9aa09b46bc423a0cefb49168930b03af4be6a2b47bb8',
    guide='work/candidates/direct-truce-cache-cli-1375-v1/STATUS.md',scope='current directional pair byte45 mask1 only',
    request_effect_profile_count=0,complete_truce_or_expiry_verified=False),
 dict(id='war_peace_static_contract_lookup_v2',entry='work/candidates/war-peace-api-lookup-1375-v2/war_peace_lookup.py',
    manifest='work/candidates/war-peace-api-lookup-1375-v2/source-manifest.json',manifest_sha='7c72ee48d57a753526c4731b894e751255eb8267fdc83b086820305770ef6bc6',
    guide='work/candidates/war-peace-api-lookup-1375-v2/STATUS.md',scope='50 static endpoints: catalog/search/lookup of frozen contracts only',
    request_effect_profile_count=0,endpoint_count=50,process_access=False,war_peace_executor_ready=False)
]


def read(path):
    with path.open('rb') as stream:raw=stream.read(256*1024+1)
    assert 0<len(raw)<=256*1024
    return raw


def pin(path):
    raw=read(path);return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def main():
    assert not OUTPUT.exists(), 'Discovery map already exists; preserve before revising'
    rows=[];before={}
    for item in TOOLS:
        manifest=ROOT/item['manifest'];raw=read(manifest);mpin=pin(manifest)
        assert mpin['sha256']==item['manifest_sha']
        value=json.loads(raw);selected=value.get('source_pins',value.get('files'))
        assert isinstance(selected,dict)
        epin=pin(ROOT/item['entry'])
        assert epin==selected[item['entry']], 'Entry must be owned by the exact manifest'
        before[item['manifest']]=mpin;before[item['entry']]=epin
        assert (ROOT/item['guide']).is_file()
        row={k:v for k,v in item.items() if k!='manifest_sha'}
        row.update(entry_pin=epin,manifest_pin=mpin,manifest_direct_pin_count=len(selected),
            permission_authority='exact owner manifest and runtime source gate, never this discovery map',
            game_functions_invoked_by_observer=False,publishes_diplomacy_requests=False)
        rows.append(row)
    assert all(pin(ROOT/n)==p for n,p in before.items())
    result=dict(schema='EU4-READONLY-TOOL-DISCOVERY/1',game_sha256='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a',
        purpose='file-only tool selection; descriptive metadata does not authorize execution',
        authoritative_for_permissions=False,current_process_authenticated=False,source_closures_rehashed=False,
        historical_effect_signals=48,historical_persistence_aggregate=44,remaining_repair_candidates=42,
        all120_effects_complete=False,tools=rows,
        rules=['Current state and successful reads do not establish original-request effects',
            'Effects require the genuine original receipt, pre-send baseline and selected runtime object change',
            'Save and cold reload test persistence separately',
            'Unsupported layout, stale identity, changed sources or inconsistent reads remain unknown; no automatic retry',
            'Fresh real process identity and manual pause are required by runtime readers; the game need not be foreground'],
        build_operations=dict(process_accesses=0,PE_opens=0,native_game_calls=0,CLI_or_tests_run=0,requests_published=0))
    with OUTPUT.open('x',encoding='utf-8',newline='\n') as stream:stream.write(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(dict(status='built',tools=len(rows),output=pin(OUTPUT))))


if __name__=='__main__':main()
