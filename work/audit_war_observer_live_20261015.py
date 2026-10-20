"""Independently check retained live war projections; never opens a process."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'work/reports/war-peace-api-20261015-r7-r2/observer'


def load(path, bound=2*1024*1024):
    assert path.stat().st_size <= bound, path
    return json.loads(path.read_bytes())


def pin(path):
    raw = path.read_bytes()
    return dict(path=str(path.relative_to(ROOT)).replace('\\', '/'),
                bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def verify_capture(name, expected):
    path = REPORT / name
    data = load(path)
    assert data['schema'] == 'EU4-WAR-PAIR-CAPTURE/2'
    assert data['status'] == 'observed' and data['two_pass_equal'] is True
    graph = data['projection']
    assert len(data['passes']) == 2 and all(x == graph for x in data['passes'])
    assert data['identity']['pid'] == 80340 and data['identity']['creation'] == '01dd5c075fcf8c26'
    for field in ('native_calls', 'requests_published', 'saves_written', 'reloads'):
        assert data[field] == 0
    for field in ('memory_written', 'native_session_installed', 'world_epoch_proven',
                  'world_lifetime_lease_proven', 'runtime_effect_verified'):
        assert data[field] is False
    assert data['process_identity_authenticated_by_host'] is True
    assert graph['complete_current_global_scan'] is True
    assert graph['global_war_count'] == len(graph['wars']) == 4
    assert graph['physical_pair_indexes'] == len(graph['relation_indexes']) == 2
    assert graph['pair_state'] == expected
    ah, th = graph['actor']['handle'], graph['target']['handle']
    selected = []
    for war in graph['wars']:
        assert war['vtable_rva'] == '0x1d1f768' and war['marker'] == 357
        assert war['outcome_is_retirement'] is False
        a = {m['handle'] for m in war['attackers']}
        t = {m['handle'] for m in war['defenders']}
        assert a and t and not a.intersection(t)
        assert len(a) == len(war['attackers']) and len(t) == len(war['defenders'])
        assert war['primary_attacker_handle'] in a and war['primary_defender_handle'] in t
        opp = (ah in a and th in t) or (ah in t and th in a)
        assert war['selected_pair_opponents'] == opp
        if opp:
            selected.append(war)
    assert len(selected) == (1 if expected == 'opponents' else 0)
    for index, owner, other in zip(graph['relation_indexes'],
                                   (graph['actor'], graph['target']),
                                   (graph['target'], graph['actor'])):
        assert index['owner_handle'] == owner['handle']
        assert index['data_field'] == index['country_data_alias']
        assert index['independent_physical_indexes'] == 1
        assert 0 <= index['count'] <= index['capacity'] <= 64
        assert index['count'] == len(index['entries'])
        assert len({x['other_slot'] for x in index['entries']}) == index['count']
        matches = [x for x in index['entries'] if x['other_slot'] == other['slot']]
        assert bool(matches) == index['target_match'] == bool(selected)
        assert index['relation_byte46_is_war_membership'] is False
        assert index['native_war_membership_predicate_rva'] == '0xa68a00'
        if selected:
            assert matches[0]['current_war_address'] == selected[0]['current_war_address']
            assert index['relation_byte46_raw'] == 0
    if selected:
        assert len(selected[0]['attackers']) + len(selected[0]['defenders']) == 41
    for field in ('war_retired_proven', 'peace_terms_verified', 'peace_completion_verified',
                  'request_causality_verified', 'queue_removal_is_completion'):
        assert graph[field] is False
    for relative, expected_pin in data['source_pins'].items():
        actual = pin(ROOT / relative)
        assert actual['bytes'] == expected_pin['bytes'] and actual['sha256'] == expected_pin['sha256']
    host = pin(ROOT / 'tools/observe_war_state_r2.py')
    assert {k: host[k] for k in ('bytes', 'sha256')} == data['host_source_pin']
    return dict(path=pin(path)['path'], pair_state=expected,
                selected_members=41 if selected else 0, global_wars=4,
                two_pass_equal=True, duration_ms=data['duration_ms'])


def main():
    rows = [verify_capture('live-80340-ENG-AMG.json', 'opponents'),
            verify_capture('live-80340-FRA-ENG.json', 'not_currently_opponents')]
    paths = {Path(__file__), ROOT/'tools/observe_war_state_r2.py', REPORT/'manifest.json'}
    for name in ('live-80340-ENG-AMG.json', 'live-80340-FRA-ENG.json'):
        p = REPORT/name
        paths.add(p)
        paths.update(ROOT/x for x in load(p)['source_pins'])
    result = dict(schema='EU4-WAR-OBSERVER-LIVE-FILE-AUDIT/1',
                  audited_utc=datetime.now(timezone.utc).isoformat(), checks_passed=True,
                  process_accessed=False, native_calls=0, requests_published=0,
                  captures=rows, input_pins=[pin(p) for p in sorted(paths)],
                  limitations=['Retained decoded live projections checked; no raw RAM replay.',
                               'Current membership does not prove declaration or peace API completion.',
                               'No world lifetime lease or atomic snapshot is established.'])
    dest = REPORT/'independent-live-file-audit.json'
    with dest.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(dict(checks_passed=True, input_pins=len(result['input_pins']),
                          captures=rows, output=str(dest))))


if __name__ == '__main__':
    main()
