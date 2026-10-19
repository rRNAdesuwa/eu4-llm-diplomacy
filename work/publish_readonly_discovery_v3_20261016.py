"""Publish reviewed discovery metadata and refresh current docs; no tool execution."""
from pathlib import Path
import copy
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/reports/readonly-discovery-publication-20261016-r1'
PINS = {}
TOTAL = 0


def pin(b):
    return dict(bytes=len(b), sha256=hashlib.sha256(b).hexdigest())


def read(p, expected=None):
    global TOTAL
    path = (ROOT / p).resolve()
    assert path.is_relative_to(ROOT) and 0 <= path.stat().st_size <= 4194304
    b = path.read_bytes()
    TOTAL += len(b)
    assert TOTAL < 16 * 1024 * 1024
    actual = pin(b)
    assert expected is None or actual == expected, p
    assert p not in PINS or PINS[p] == actual, p
    PINS[p] = actual
    return b


def load(p, expected=None):
    return json.loads(read(p, expected))


def save(p, o):
    b = (json.dumps(o, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode()
    with p.open('xb') as f:
        f.write(b)
    return pin(b)


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    oldpath = 'docs/runtime-capability-map-1375-v2.json'
    old = load(oldpath, dict(bytes=9158, sha256='593fed58a53cd7215bbadded1470ae93c4589211fd59f51088a0e01d574fd962'))
    prefix = 'work/candidates/war-peace-api-lookup-1375-v3/'
    lookup_manifest = load(prefix + 'source-manifest.json', dict(bytes=12934, sha256='7b8b9323d20190c1c7f4b966c9520d10a4136a8f5c6be3c8957621b4b98fe6d1'))
    lookup_data = load(prefix + 'data-manifest.json', dict(bytes=8733, sha256='8f849152e150b3f3918b10bb427cfa39457e4774db83c4dac42f82da04c3c212'))
    lr = 'work/reports/war-peace-api-lookup-v3-independent-review-20261016-r1/'
    lookup_review = load(lr + 'findings.json', dict(bytes=2248, sha256='b257809613c5145807509c928da05ddb7ceb7e086350710bc4853324820bc406'))
    load(lr + 'manifest.json', dict(bytes=16772, sha256='9d43a041fc03951bde0b7bec3a700960c2bd083d244cc8d7c9527e2ecf8af9e3'))
    assert lookup_review['sealed'] is lookup_review['passed'] is True and lookup_review['blocking_findings'] == []
    cli = prefix + 'war_peace_lookup.py'
    read(cli, lookup_review['subject_cli_pin'])
    pending = 'work/candidates/peace-current-pending-observer-1375-v1/'
    pm = load(pending + 'source-manifest.json', dict(bytes=7055, sha256='55c2b33910e95f942c769358752810ff294e7667d99d63c01fd334adae2ff28d'))
    assert pm['sealed'] is pm['runtime_capture_authorized'] is True
    pc = 'work/reports/peace-current-pending-observer-production-check-20261016-r1/'
    check = load(pc + 'receipt.json', dict(bytes=4667, sha256='750ae9df59e3f8d6fbb231f3c13e262582c9161d5504bcf1daa86e07c8cb530a'))
    cm = load(pc + 'manifest.json', dict(bytes=3283, sha256='c1f27b3999f7250eb7d85167ff86bb30b2225234e1ca33ed21a38bbf0e7cac62'))
    load(pc + 'verification.json', dict(bytes=1044, sha256='eb0dfbbec8e07b6f5f00838bd03027d0a8287350e71f0446f31f935c730431b0'))
    assert cm['sealed'] is cm['passed'] is True
    for group in ('local_pins', 'captured_source_pins'):
        for path, expected in cm[group].items():
            read(path, expected)
    assert check['passed'] is True and check['failure'] is None and check['source_unchanged'] is True
    assert check['source_before'] == check['source_after']
    assert check['check_invocations'] == 1 and check['tests_run'] == check['catalog_runs'] == check['actual_status_captures'] == 0
    job = check['job']
    assert job['exit_code'] == 0 and job['error'] is None and job['direct_child_collected'] is True
    assert job['job_active_processes_final'] == 0 and job['job_total_processes'] == 2
    answer = load(pc + 'stdout.txt', cm['local_pins'][pc + 'stdout.txt'])
    assert answer['status'] == 'files_verified' and answer['errors'] == [] and answer['selected_queue_presence'] is None
    assert answer['source_graph']['candidate']['sealed'] is answer['source_graph']['candidate']['runtime_capture_authorized'] is True
    assert all(v is False for v in check['observations']['authority'].values())
    for key in ('independent_source_review', 'production_review'):
        rp = pm[key]
        v = load(rp['path'], {k: rp[k] for k in ('bytes', 'sha256')})
        assert v['sealed'] is v['passed'] is True and v['blocking_findings'] == []
        assert v['subject_cli_pin'] == pm['source_pins'][pending + 'peace_current_pending.py']
        assert v['subject_source_graph_sha256'] == pm['source_graph_sha256']
    result = copy.deepcopy(old)
    result.update(schema='EU4-READONLY-TOOL-DISCOVERY/3',
        previous_discovery=dict(path=oldpath, **PINS[oldpath]),
        accepted_entry_count=5, pending_active_world_reader_count=2,
        discovery_build_scope='Exact previous map, changed file-lookup entry, new pending-reader owner and reviewed source/production/check receipts; no deep closure or process authentication.')
    li = next(i for i, t in enumerate(result['tools']) if t['id'] == 'war_peace_static_contract_lookup_v2')
    result['tools'][li] = dict(id='war_peace_static_contract_lookup_v3', entry=cli,
        entry_pin=PINS[cli], manifest=prefix + 'data-manifest.json', manifest_pin=PINS[prefix + 'data-manifest.json'],
        source_manifest=prefix + 'source-manifest.json', source_manifest_pin=PINS[prefix + 'source-manifest.json'],
        guide=prefix + 'REVIEW_STATUS.md', scope='54 retained endpoints / 44 selected JSON sources; file-only catalog/search/lookup/check',
        request_effect_profile_count=0, endpoint_count=54, process_access=False, war_peace_executor_ready=False,
        source_graph_scope='44 JSON sources + index; frozen Python query-engine guard separate. Original50 entries unchanged; R63 excluded.',
        manifest_direct_pin_count=45, source_manifest_direct_pin_count=65,
        independent_review=dict(path=lr + 'findings.json', **PINS[lr + 'findings.json']),
        previous_file_lookup=dict(entry=old['tools'][li]['entry'], entry_pin=old['tools'][li]['entry_pin']),
        permission_authority='Exact data-manifest/index/evidence and frozen Python engine guards; discovery map does not authorize execution.',
        game_functions_invoked_by_observer=False, publishes_diplomacy_requests=False)
    result['tools'].append(dict(id='peace_current_pending_queue_pending_active_world',
        entry=pending + 'peace_current_pending.py', entry_pin=pm['source_pins'][pending + 'peace_current_pending.py'],
        manifest=pending + 'source-manifest.json', manifest_pin=PINS[pending + 'source-manifest.json'],
        guide=pending + 'REVIEW_STATUS.md', manifest_direct_pin_count=32, additional_runtime_review_gates=2,
        scope='Current selected actor->target inbox peace presence/absence or unknown, rawID/state/endpoints; no request correlation.',
        maturity='source_and_production_reviewed_31_first_fakes_and_production_file_check_passed_live_pending',
        request_effect_profile_count=0, real_world_queue_decoder_verified=False, real_capture_scope='No genuine live status sample yet.',
        queue_profile=dict(iteration_byte=0, tombstones_allowed=False, max_nodes=128, action_prefix_bytes=64, foreign_vtable_bytes=8),
        attempt_budget=dict(reads=4096, bytes=524288, single_read=65536, entry_PE8192_included=True),
        loaded_code_bytes_per_pass=735, source_graph_sha256=pm['source_graph_sha256'],
        independent_source_review=pm['independent_source_review'], production_review=pm['production_review'],
        first_production_check=dict(path=pc + 'receipt.json', **PINS[pc + 'receipt.json']),
        original_request_effect_verified=False, acceptance_verified=False, peace_completed=False,
        persistence_verified=False, world_lease=False, atomic_snapshot=False,
        permission_authority='Exact owner source graph and independently bound source/production reviews plus fresh runtime guards; never this map.',
        game_functions_invoked_by_observer=False, publishes_diplomacy_requests=False))
    assert len(result['tools']) == 7 and len({t['id'] for t in result['tools']}) == 7
    assert all(result['tools'][i] == old['tools'][i] for i in range(6) if i != li)
    assert result['historical_effect_signals'] == 48 and result['historical_persistence_aggregate'] == 44
    assert result['remaining_repair_candidates'] == 42 and result['all120_effects_complete'] is False
    newpath = 'docs/runtime-capability-map-1375-v3.json'
    output_pin = save(ROOT / newpath, result)
    assert load(newpath, output_pin) == result
    for path, expected in list(PINS.items()):
        read(path, expected)
    manifest = save(OUT / 'manifest.json', dict(schema='EU4-READONLY-DISCOVERY-V3-PUBLICATION/1',
        sealed=True, passed=True, source_pins=PINS, output=dict(path=newpath, **output_pin),
        accepted_entries=5, pending_active_world_readers=2, total_entries=7,
        changed_only='Replace file lookup v2 with accepted v3 and append live-pending peace queue reader. Other five entries unchanged.',
        current_process_authenticated=False, deep_closure_rehashed=False,
        selected_source_file_reads=TOTAL, operations=dict(PE=0, game_process=0, decoder=0, native=0, CLI_or_tests=0)))
    print(json.dumps(dict(passed=True, output=output_pin, manifest=manifest, source_reads=TOTAL), ensure_ascii=True))


if __name__ == '__main__':
    main()
