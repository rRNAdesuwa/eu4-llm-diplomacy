"""Exact-build read-only v11 state observations; no process access on import.

sample opens QUERY_INFORMATION | VM_READ. compare is entirely offline.
Insult effects remain unsupported; no request causality or AI acceptance claims.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work import probe_diplomacy_relations_v7_1375 as core

base = core.base
require, integer, address = base.require, base.integer, base.address
PROFILE = '1375_pair_extension_observation_v11_1'
EVIDENCE_SHA256 = 'aa93b84c2ae1af3652134b49c80453aabfb4a51006e4ec20b9c6c7196eb1888a'
EXTENSION_SHA256 = 'ac4559379e218aaf1fa8ffc1dd7dc6b8332ed5b7bf681c4b66bfc59349944344'
HANDLES, TARGETS = core.HANDLES, core.TARGETS
RELATIONS = {
    'warningaction': (0x1B8, 0x1C4, 0x1B8, 0x1C4, 0x1C7FCA0, 'forward'),
    'support_independence_action': (0x170, 0x17C, 0x170, 0x17C, 0x1C80570, 'pair'),
    # Default FRA receives/benefits: FRA index is receiver; target is supplier.
    'transfer_trade_power': (0x248, 0x254, 0x230, 0x23C, 0x1C571F0, 'reverse'),
    'steer_trade': (0x278, 0x284, 0x260, 0x26C, 0x1C7D498, 'reverse'),
}
TRADE = frozenset(('transfer_trade_power', 'steer_trade'))
ECONOMIC = frozenset(('giftaction', 'trade_favors_for_gold'))
ACTIONS = tuple(RELATIONS) + ('form_coalition', 'giftaction', 'trade_favors_for_gold', 'insultaction')
UNSUPPORTED = {'insultaction': 'Ordinary insult opinion-modifier/CB identity is not closed; no synthetic relation is inferred.'}
MAX_COALITION_NODES = 1024
LIMITATIONS = [
    'Two identical bounded passes are not atomic; transient state or ABA address reuse can escape observation.',
    'Full handles, roots, player and dates do not establish a reliable same-process world epoch.',
    'Trade flow is explicit. Proposal actor receives in true mode; cancellation requires the selected existing direction.',
    'Support relation fields preserve proposal order, not a fixed supporter/dependent order; no provider authority is inferred.',
    'Economic comparisons require same date and exact expected scalar deltas, but unrelated transfers can produce the same difference.',
    'Observed state transition is not request causality, AI acceptance, execution capability or whole-world invariance.',
    'Missing, unsupported, unreadable or unstable state never implies rejection.',
    'On-disk full executable hash and loaded PE identity do not hash every in-memory code byte.',
]


def flow_for(action, flow):
    require(action in ACTIONS, 'Unsupported family')
    if action in TRADE:
        flow = flow or 'target_to_actor'
        require(flow in ('target_to_actor', 'actor_to_target'), 'Invalid trade flow')
        return flow
    require(flow is None, 'Trade direction only applies to trade families')
    return None


def offsets(action, flow):
    a, ac, b, bc, vt, direction = RELATIONS[action]
    if action in TRADE and flow == 'actor_to_target':
        return b, bc, a, ac, vt, 'forward'
    return a, ac, b, bc, vt, direction


def full_handle(value):
    require(isinstance(value, str) and value.startswith('0x') and 3 <= len(value) <= 18, 'Invalid full handle encoding')
    return integer(int(value, 16), 0, (1 << 64)-1)


def relation_snapshot(reader, identity, target, action, flow):
    actor, recipient = identity['pair']['FRA'], identity['pair'][target]
    aoff, acount, boff, bcount, vt, _ = offsets(action, flow)
    left = base.index_snapshot(reader, actor, recipient, aoff, acount)
    right = base.index_snapshot(reader, recipient, actor, boff, bcount)
    a = core.validate_index(left, recipient, (aoff, acount))
    b = core.validate_index(right, actor, (boff, bcount))
    require(len(a) <= 1 and a == b, 'Selected relation indexes disagree')
    obj = None
    if a:
        location = address(a[0])
        header = reader.read(location, 0x30)
        require(struct.unpack_from('<Q', header)[0] == address(identity['module_base']) + vt, 'Wrong relation vtable')
        obj = {'address': a[0], 'vtable': hex(struct.unpack_from('<Q', header)[0]),
               'type_marker': struct.unpack_from('<I', header, 8)[0],
               'first_handle': hex(struct.unpack_from('<Q', header, 0x10)[0]),
               'second_handle': hex(struct.unpack_from('<Q', header, 0x18)[0]),
               'started_raw_date': struct.unpack_from('<i', header, 0x20)[0], 'removed': header[0x28]}
        if action == 'transfer_trade_power':
            obj['fraction_milli'] = reader.integer(location + 0x40)
            obj['extra_flag'] = reader.read(location + 0x44, 1)[0]
        elif action == 'steer_trade':
            obj['extra_flag'] = reader.read(location + 0x40, 1)[0]
    return {'left': left, 'right': right, 'object': obj}


def coalition_snapshot(reader, identity, target):
    actor, recipient = identity['pair']['FRA'], identity['pair'][target]
    actor_target = reader.qword(address(actor['address']) + 0x18F8)
    head, tail, count, iterating = struct.unpack('<QQIB', reader.read(address(recipient['address']) + 0x1910, 21))
    require(count <= MAX_COALITION_NODES, 'Coalition list exceeds bound')
    nodes, seen, current = [], set(), head
    for _ in range(count):
        base.pointer(current)
        require(current not in seen, 'Coalition list cycle')
        seen.add(current)
        raw = reader.read(current, 0x20)
        handle, previous, following = struct.unpack_from('<QQQ', raw)
        removed = raw[0x18]
        require(removed in (0, 1), 'Invalid coalition removal flag')
        member = None
        current_target = None
        if not removed:
            slot = (handle >> 32) & 0xFFFF
            require(slot < base.MAX_SLOTS, 'Coalition member slot exceeds bound')
            member = base.country_identity(reader, address(identity['country_array']), slot, handle)
            require(member is not None, 'Coalition member country is absent')
            current_target = hex(reader.qword(address(member['address']) + 0x18F8))
        nodes.append({'address': hex(current), 'member_handle': hex(handle), 'previous': hex(previous),
                      'next': hex(following), 'removed': removed, 'member': member, 'current_target': current_target})
        current = following
    require(current == 0, 'Coalition list does not end at declared count')
    return {'actor_coalition_target': hex(actor_target), 'head': hex(head), 'tail': hex(tail),
            'count': count, 'iterating': iterating, 'nodes': nodes}


def economic_snapshot(reader, identity, target):
    result = {'treasury_milli': {}, 'favors_records': {}}
    for tag, other in (('FRA', target), (target, 'FRA')):
        country = identity['pair'][tag]
        result['treasury_milli'][tag] = reader.integer(address(country['address']) + 0xBB0)
        records = base.pointer(reader.qword(address(country['address']) + 0x1510))
        location = records + identity['pair'][other]['slot'] * 0x48
        data = reader.read(location, 0x24)
        require(struct.unpack_from('<Q', data, 0x10)[0] == HANDLES[other], 'Economic relation counterpart mismatch')
        result['favors_records'][tag] = {'records': hex(records), 'record': hex(location),
            'counterpart_handle': hex(struct.unpack_from('<Q', data, 0x10)[0]),
            'favors_milli': struct.unpack_from('<i', data, 0x20)[0]}
    return result


def sample_once(reader, module_base, target, action, trade_direction=None):
    flow = flow_for(action, trade_direction)
    require(action not in UNSUPPORTED, UNSUPPORTED.get(action, 'Unsupported'))
    identity = core.read_identity(reader, module_base, target)
    result = {**identity, 'target': target, 'action': action, 'trade_direction': flow}
    if action in RELATIONS:
        result['relation'] = relation_snapshot(reader, identity, target, action, flow)
    elif action == 'form_coalition':
        result['coalition'] = coalition_snapshot(reader, identity, target)
    else:
        result['economic'] = economic_snapshot(reader, identity, target)
    require(core.read_identity(reader, module_base, target) == identity, 'Date/world/country identity changed during sampling')
    return result


def relation_state(sample):
    action, target, flow = sample['action'], sample['target'], sample['trade_direction']
    aoff, acount, boff, bcount, vt, direction = offsets(action, flow)
    data = sample['relation']
    left = core.validate_index(data['left'], sample['pair'][target], (aoff, acount))
    right = core.validate_index(data['right'], sample['pair']['FRA'], (boff, bcount))
    obj = data['object']
    if left == right == []:
        require(obj is None, 'Absent indexes cannot claim object')
        return {'state': 'absent', 'object': None}
    require(len(left) == len(right) == 1 and left == right and isinstance(obj, dict), 'Relation indexes disagree')
    require(obj['address'] == left[0] and address(obj['vtable']) == address(sample['module_base'])+vt, 'Object/vtable mismatch')
    require(type(obj['type_marker']) is int and obj['type_marker'] == 0x165, 'Wrong relation type marker')
    require(type(obj['removed']) is int and obj['removed'] == 0, 'Indexed relation marked removed')
    integer(obj['started_raw_date'], 1, sample['current_raw_date'])
    forward = (hex(HANDLES['FRA']), hex(HANDLES[target]))
    actual = (obj['first_handle'], obj['second_handle'])
    require(actual in (forward, forward[::-1]), 'Relation full handles differ')
    expected = forward[::-1] if direction == 'reverse' else forward
    state = 'active'
    if direction != 'pair' and actual != expected:
        require(action == 'warningaction', 'Trade index direction disagrees with object')
        state = 'reverse_relation'
    if action in TRADE:
        if integer(obj['extra_flag'], 0, 1):
            state = 'special_variant'
        if action == 'transfer_trade_power':
            amount = integer(obj['fraction_milli'], -0x80000000, 0x7FFFFFFF)
            if not 0 < amount <= 1000:
                state = 'unsupported_fraction'
    return {'state': state, 'object': obj, 'object_order': 'FRA_first' if actual == forward else 'target_first',
            'provider_role_inferred': False}


def coalition_state(sample):
    target, data = sample['target'], sample['coalition']
    count = integer(data['count'], 0, MAX_COALITION_NODES)
    integer(data['iterating'], 0, 255)
    head = address(data['head'], nullable=count == 0)
    tail = address(data['tail'], nullable=count == 0)
    nodes = data['nodes']
    require(isinstance(nodes, list) and len(nodes) == count, 'Coalition count mismatch')
    require(count or (head == tail == 0), 'Empty coalition has linked nodes')
    previous, following, addresses, handles, selected = 0, head, set(), set(), []
    for node in nodes:
        location = address(node['address'])
        require(location == following and location not in addresses, 'Coalition cycle/link mismatch')
        addresses.add(location)
        require(address(node['previous'], nullable=True) == previous, 'Coalition previous link mismatch')
        following = address(node['next'], nullable=True)
        previous = location
        removed = integer(node['removed'], 0, 1)
        handle = full_handle(node['member_handle'])
        if removed:
            require(node['member'] is None and node['current_target'] is None, 'Removed coalition node was dereferenced')
            continue
        base.validated_identity(node['member'], handle)
        require(handle not in handles, 'Duplicate active coalition member')
        handles.add(handle)
        require(node['current_target'] == hex(HANDLES[target]), 'Member coalition target contradicts list')
        if (handle >> 32) & 0xFFFF == sample['pair']['FRA']['slot']:
            require(handle == HANDLES['FRA'], 'Selected member generation differs')
            selected.append(node['address'])
    require(following == 0 and previous == tail, 'Coalition tail/count mismatch')
    current = full_handle(data['actor_coalition_target'])
    if (current >> 32) & 0xFFFF == sample['pair'][target]['slot']:
        require(current == HANDLES[target], 'Coalition target full handle mismatch')
    active = current == HANDLES[target]
    require(active == (len(selected) == 1), 'Actor coalition target and member list disagree')
    return {'state': 'active' if active else 'absent', 'selected_nodes': selected,
            'actor_coalition_target': data['actor_coalition_target'], 'object': None}


def economic_state(sample):
    data, target = sample['economic'], sample['target']
    require(set(data['treasury_milli']) == {'FRA', target} and set(data['favors_records']) == {'FRA', target}, 'Economic pair keys differ')
    for tag, other in (('FRA', target), (target, 'FRA')):
        integer(data['treasury_milli'][tag], -1000000000, 1000000000)
        record = data['favors_records'][tag]
        require(address(record['record']) == address(record['records']) + sample['pair'][other]['slot']*0x48
                and record['counterpart_handle'] == hex(HANDLES[other]), 'Favors record identity mismatch')
        integer(record['favors_milli'], 0, 100000)
    return {'state': 'economic_scalars', **data, 'object': None}


def inspect_state(sample):
    target, action = sample['target'], sample['action']
    require(target in TARGETS and action in ACTIONS and action not in UNSUPPORTED, 'Unsupported pair/family')
    require(flow_for(action, sample['trade_direction']) == sample['trade_direction'], 'Flow metadata differs')
    for key in ('module_base', 'database', 'game', 'country_array'):
        address(sample[key])
    integer(sample['current_raw_date'], 1, 0x7FFFFFFF)
    base.validated_identity(sample['player'])
    for tag in ('FRA', target):
        base.validated_identity(sample['pair'][tag], HANDLES[tag])
    state = relation_state(sample) if action in RELATIONS else coalition_state(sample) if action == 'form_coalition' else economic_state(sample)
    return {**state, 'rejection_observed': False}


def capture(reader, module_base, target, action, trade_direction=None):
    result = {'status': 'unknown', 'passes': [], 'state': None, 'errors': [], 'atomic_snapshot': False}
    if action in UNSUPPORTED:
        return {**result, 'status': 'unsupported', 'reason': UNSUPPORTED[action]}
    try:
        for _ in range(2):
            value = sample_once(reader, module_base, target, action, trade_direction)
            result['passes'].append(value)
            inspect_state(value)
        require(result['passes'][0] == result['passes'][1], 'Repeated samples differ')
        result.update(state=inspect_state(result['passes'][1]), status='consistent_bounded_observation')
    except (base.ProbeError, KeyError, TypeError, ValueError, UnicodeError, struct.error) as exc:
        result['errors'].append(str(exc))
    return result


def sample_process(pid, executable, target, action, trade_direction=None):
    flow = flow_for(action, trade_direction)
    if action in UNSUPPORTED:
        return {'schema_version': 1, 'profile': PROFILE, 'kind': 'pair_extension_v11_snapshot', 'read_only': True,
                'action': action, 'actor': 'FRA', 'target': target, 'observation': capture(None, 0, target, action),
                'process_opened': False, 'execution_verified': False, 'limitations': LIMITATIONS}
    build, signature = base.verified_executable(executable)
    reader = base.ProcessReader(pid, executable, signature)
    try:
        source = base.process_identity(reader, pid)
        started = base.timestamp()
        observation = capture(reader, reader.base, target, action, flow)
        finished = base.timestamp()
        require(base.process_identity(reader, pid) == source, 'Process identity changed')
        return {'schema_version': 1, 'kind': 'pair_extension_v11_snapshot', 'profile': PROFILE,
                'static_effect_evidence_sha256': EVIDENCE_SHA256, 'static_extension_evidence_sha256': EXTENSION_SHA256,
                'read_only': True, 'capture_started_at': started, 'capture_finished_at': finished,
                'build': build, 'source': source, 'action': action, 'actor': 'FRA', 'target': target, 'trade_direction': flow,
                'observation': observation, 'execution_verified': False, 'request_causality_verified': False,
                'read_budget': {'bytes_read': reader.bytes_read, 'maximum_total': base.MAX_TOTAL_READ,
                    'maximum_single': base.MAX_READ, 'maximum_relation_entries': base.MAX_RELATION_ENTRIES,
                    'maximum_coalition_nodes': MAX_COALITION_NODES, 'passes': 2}, 'limitations': LIMITATIONS}
    finally:
        reader.close()


def validated_report(report):
    require(type(report['schema_version']) is int and report['schema_version'] == 1 and report['profile'] == PROFILE
            and report['kind'] == 'pair_extension_v11_snapshot' and report['read_only'] is True
            and report['static_effect_evidence_sha256'] == EVIDENCE_SHA256
            and report['static_extension_evidence_sha256'] == EXTENSION_SHA256, 'Unsupported observation profile/evidence')
    require(report['build']['sha256'].upper() == base.LOCAL_SHA256, 'Wrong build')
    require(report['actor'] == 'FRA' and report['target'] in TARGETS and report['action'] in ACTIONS, 'Wrong pair/family')
    source = report['source']
    require(source['kind'] == 'live_process' and source['access_rights'] == 'QUERY_INFORMATION | VM_READ', 'Not a read-only process snapshot')
    integer(source['pid'], 1)
    integer(source['process_creation_filetime'], 1, (1 << 64)-1)
    require(type(source['process_exit_filetime']) is int and source['process_exit_filetime'] == 0, 'Exited process')
    address(source['module_base'])
    times = [base.datetime.fromisoformat(report[k]) for k in ('capture_started_at', 'capture_finished_at')]
    require(all(x.tzinfo is not None for x in times) and times[0] <= times[1], 'Invalid capture interval')
    obs = report['observation']
    require(obs['status'] == 'consistent_bounded_observation' and obs['errors'] == [], 'Incomplete/unstable observation')
    passes = obs['passes']
    require(isinstance(passes, list) and len(passes) == 2 and passes[0] == passes[1], 'Two complete identical passes required')
    sample = passes[0]
    require(all(sample[k] == report[k] for k in ('target', 'action', 'trade_direction')) and sample['module_base'] == source['module_base'], 'Report/sample identity differs')
    state = inspect_state(sample)
    require(state == obs['state'], 'Stored state differs from raw fields')
    return sample, state, times


def compare_reports(before, after, direction='positive', expected_amount_milli=None, expected_favors_milli=None, expected_fraction_milli=None):
    result = {'schema_version': 1, 'kind': 'pair_extension_v11_comparison', 'profile': PROFILE,
              'status': 'unknown', 'direction': direction, 'observed_effect': False, 'execution_verified': False,
              'request_causality_verified': False, 'ai_acceptance_verified': False, 'rejection_observed': False,
              'whole_world_unchanged_verified': False, 'errors': [], 'limitations': LIMITATIONS}
    try:
        require(direction in ('positive', 'cancel'), 'Unsupported comparison direction')
        if before.get('action') in UNSUPPORTED or after.get('action') in UNSUPPORTED:
            result.update(status='unsupported', reason=UNSUPPORTED['insultaction'])
            return result
        prior, old, old_times = validated_report(before)
        current, new, new_times = validated_report(after)
        action, target = before['action'], before['target']
        require(before['source'] == after['source'], 'Process/creation/base changed')
        require(all(before[k] == after[k] for k in ('action', 'target', 'trade_direction')), 'Different family/pair/flow')
        require(old_times[1] <= new_times[0] and old_times[0] < new_times[1], 'Capture intervals overlap/reverse')
        require(all(prior[k] == current[k] for k in ('pair', 'player', 'database', 'game', 'country_array')), 'World/country identity changed')
        require(current['current_raw_date'] >= prior['current_raw_date'], 'Date moved backwards')
        require(not (direction == 'cancel' and action in ('warningaction', *ECONOMIC)), 'This family has no supported cancel comparison')
        require(not (direction == 'positive' and action in TRADE and before['trade_direction'] != 'target_to_actor'),
                'Positive native proposal requests target-to-actor flow; reverse flow is observation/cancel only')
        if expected_fraction_milli is not None:
            require(action == 'transfer_trade_power', 'Expected fraction applies only to trade-power transfer')
            integer(expected_fraction_milli, 1, 1000)
            selected = new if direction == 'positive' else old
            require(selected['state'] == 'active' and selected['object']['fraction_milli'] == expected_fraction_milli,
                    'Trade-power fraction differs from expectation')
            result['expected_fraction_milli'] = expected_fraction_milli
        result.update(source=after['source'], action=action, actor='FRA', target=target, trade_direction=before['trade_direction'],
                      raw_dates={'before': prior['current_raw_date'], 'after': current['current_raw_date']}, before_state=old, after_state=new)
        if action in ECONOMIC:
            amount = integer(expected_amount_milli, 1, 1000000000)
            require(prior['current_raw_date'] == current['current_raw_date'], 'Economic comparisons require same raw date')
            deltas = {tag: new['treasury_milli'][tag]-old['treasury_milli'][tag] for tag in ('FRA', target)}
            favors = {tag: new['favors_records'][tag]['favors_milli']-old['favors_records'][tag]['favors_milli'] for tag in ('FRA', target)}
            result.update(treasury_delta_milli=deltas, favors_record_delta_milli=favors, expected_amount_milli=amount)
            if action == 'giftaction':
                require(expected_favors_milli is None, 'Gift has no expected favors cost')
                matched = deltas == {'FRA': -amount, target: amount} and all(v == 0 for v in favors.values())
            else:
                cost = integer(expected_favors_milli, 1, 100000)
                result['expected_favors_milli'] = cost
                matched = deltas == {'FRA': amount, target: -amount} and favors == {'FRA': 0, target: -cost}
            if matched:
                result.update(status='observed_effect', observed_effect=True, transition='exact_selected_economic_delta')
        else:
            require(expected_amount_milli is None and expected_favors_milli is None, 'Economic expectations only apply to economic families')
            if direction == 'positive' and old['state'] == 'absent' and new['state'] == 'active':
                if action in RELATIONS:
                    require(new['object']['started_raw_date'] >= prior['current_raw_date'], 'New relation predates baseline')
                result.update(status='observed_effect', observed_effect=True, transition='added_selected_state')
            elif direction == 'cancel' and old['state'] == 'active' and new['state'] == 'absent':
                result.update(status='observed_effect', observed_effect=True, transition='removed_selected_state')
    except (base.ProbeError, KeyError, TypeError, ValueError) as exc:
        result['errors'].append(str(exc))
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='mode', required=True)
    s = sub.add_parser('sample')
    s.add_argument('--pid', type=int, required=True); s.add_argument('--exe', type=Path)
    s.add_argument('--target', choices=TARGETS, required=True); s.add_argument('--action', choices=ACTIONS, required=True)
    s.add_argument('--trade-direction', choices=('target_to_actor', 'actor_to_target'))
    s.add_argument('--output', type=Path, required=True)
    c = sub.add_parser('compare')
    c.add_argument('--before', type=Path, required=True); c.add_argument('--after', type=Path, required=True)
    c.add_argument('--direction', choices=('positive', 'cancel'), required=True)
    c.add_argument('--expected-amount-milli', type=int); c.add_argument('--expected-favors-milli', type=int)
    c.add_argument('--expected-fraction-milli', type=int)
    c.add_argument('--output', type=Path, required=True)
    a = p.parse_args(argv)
    try:
        require(not a.output.exists(), 'Output exists; choose a new evidence filename')
        if a.mode == 'sample':
            executable = a.exe or base.game_exe()
            result = sample_process(a.pid, executable, a.target, a.action, a.trade_direction)
            base.write_report(a.output, result, (executable,))
            okay = result['observation']['status'] == 'consistent_bounded_observation'
        else:
            before, bh = base.read_report(a.before); after, ah = base.read_report(a.after)
            result = compare_reports(before, after, a.direction, a.expected_amount_milli, a.expected_favors_milli, a.expected_fraction_milli)
            result['inputs'] = {'before_sha256': bh, 'after_sha256': ah}
            base.write_report(a.output, result, (a.before, a.after))
            okay = result['observed_effect']
        print(json.dumps({'output': str(a.output), 'status': result.get('status', result.get('observation', {}).get('status')),
                          'observed_effect': result.get('observed_effect', False), 'execution_verified': False}))
        return 0 if okay else 2
    except (base.ProbeError, base.EvidenceError, OSError, ValueError, RuntimeError) as exc:
        print(f'V11 observer: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
