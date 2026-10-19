"""Offline decoder for a proposed, untrusted RO query envelope.

No process reader, native call, thread API, hooks or execution authorization.
Pointers are data; no supplied pointer is ever dereferenced by this module.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
MAX_FILE = 1024 * 1024
EXE_SHA = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
CONTRACT_SHA = '1a34f841be89574e5b9cba1aaf7edae3ea87bcf499cc954e4796e4ef70121c37'
PTR = re.compile(r'0x[1-9a-f][0-9a-f]*\Z')
HANDLE = re.compile(r'0x[0-9a-f]{16}\Z')
CREATION = re.compile(r'[0-9a-f]{16}\Z')
GOAL_METHODS = {'0x58': '0x9b120', '0x70': '0xd9f0b0', '0x78': '0x8f440'}


def require(test, reason):
    if not test: raise ValueError(reason)


def exact(value, keys, name):
    require(type(value) is dict and set(value) == set(keys.split()), name + ': exact keys required')
    return value


def integer(value, low, high, name):
    require(type(value) is int and low <= value <= high, name + ': bounded exact integer required')
    return value


def pointer(value, name, nullable=False):
    if value is None and nullable: return None
    require(type(value) is str and PTR.fullmatch(value), name + ': canonical pointer string required')
    number = int(value, 16)
    require(0x10000 <= number < 0x800000000000 and number % 8 == 0, name + ': pointer range/alignment')
    return number


def rva(value, image_size, name):
    require(type(value) is str and PTR.fullmatch(value), name + ': canonical RVA required')
    require(0 < int(value, 16) < image_size, name + ': RVA outside exact module')


def handle(value, count):
    require(type(value) is str and HANDLE.fullmatch(value), 'Full handle must be 16-hex string')
    number = int(value, 16)
    slot = (number >> 32) & 0xffff
    require(slot < 0x8000 and slot < count, 'Signed country slot outside observed database')
    tag = (number & 0xffffff).to_bytes(3, 'little')
    require(all(65 <= c <= 90 for c in tag), 'Country handle TAG must be three uppercase ASCII bytes')
    require(number >> 48 != 0, 'No bare TAG/slot handles')
    return slot, tag.decode('ascii')


def strict_json(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_FILE, 'Envelope byte budget')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    def forbidden(_): raise ValueError('Float/NaN/Infinity JSON values forbidden')
    try: return json.loads(raw, object_pairs_hook=pairs, parse_float=forbidden, parse_constant=forbidden)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error: raise ValueError('Malformed bounded JSON') from error


def variant(value):
    exact(value, 'pointer raw_type storage_byte', 'Boolean variant')
    pointer(value['pointer'], 'Variant', True)
    if value['pointer'] is None:
        require(value['raw_type'] is None and value['storage_byte'] is None, 'Null variant cannot have storage')
        return 'null_variant_native_default_branch_not_reproduced'
    raw_type = integer(value['raw_type'], -(2**31), 2**31-1, 'Variant type')
    integer(value['storage_byte'], 0, 255, 'Variant byte')
    if raw_type not in (0, -1): return 'unreviewed_variant_type'
    if value['storage_byte'] not in (0, 1): return 'noncanonical_bool_storage'
    return None


def condition_vector(value, owner, offset, image_size, objects):
    exact(value, 'owner container_offset data count entries', 'Condition vector')
    require(value['owner'] == owner and value['container_offset'] == offset, 'Condition vector owner/offset differs')
    pointer(owner, 'Condition owner')
    count = integer(value['count'], 0, 64, 'Signed condition count (conservative ceiling 64)')
    pointer(value['data'], 'Conditions data', count == 0)
    require(type(value['entries']) is list and len(value['entries']) == count, 'Condition vector must be complete')
    for entry in value['entries']:
        exact(entry, 'object vtable_rva method30_rva', 'Condition instance')
        pointer(entry['object'], 'Condition instance')
        rva(entry['vtable_rva'], image_size, 'Condition vtable')
        rva(entry['method30_rva'], image_size, 'Condition virtual30')
        prior = objects.setdefault(entry['object'], (entry['vtable_rva'], entry['method30_rva']))
        require(prior == (entry['vtable_rva'], entry['method30_rva']), 'Aliased condition has conflicting identity')


def side(value, count):
    exact(value, 'begin end handles', 'War side')
    require(type(value['handles']) is list and 1 <= len(value['handles']) <= 64, 'Nonempty bounded war side required')
    begin, end = pointer(value['begin'], 'Side begin'), pointer(value['end'], 'Side end')
    require(end - begin == 8 * len(value['handles']), 'Side pointer/length mismatch')
    for member in value['handles']: handle(member, count)
    require(len(set(value['handles'])) == len(value['handles']), 'Duplicate full war member')
    return value['handles']


def snapshot(value, binding, image_size):
    exact(value, 'roots countries relations war caches dependency tls paused_observed', 'Snapshot')
    require(type(value['paused_observed']) is bool, 'Paused is exact bool diagnostic only')
    roots = exact(value['roots'], 'game database country_array country_count raw_date', 'Roots')
    for name in ('game', 'database', 'country_array'): pointer(roots[name], name)
    count = integer(roots['country_count'], 1, 4096, 'Country count')
    integer(roots['raw_date'], 1, 2**31-1, 'Raw date')
    for member in (binding['actor_handle'], binding['recipient_handle']): handle(member, count)
    taker, giver = ((binding['actor_handle'], binding['recipient_handle']) if binding['direction'] == 'demand'
                    else (binding['recipient_handle'], binding['actor_handle']))
    war = exact(value['war'], 'pointer vtable_rva side_a side_b goal', 'Borrowed war')
    pointer(war['pointer'], 'War'); rva(war['vtable_rva'], image_size, 'War vtable inventory only')
    a, b = side(war['side_a'], count), side(war['side_b'], count)
    require(not set(a) & set(b), 'War sides overlap')
    require((taker in a and giver in b) or (taker in b and giver in a), 'Negotiating countries must be opposite sides')
    members = a + b
    slots = [handle(member, count)[0] for member in members]
    require(len(set(slots)) == len(slots), 'Stale handles alias the same slot')
    countries = value['countries']
    require(type(countries) is list and len(countries) == len(members), 'Complete side-member country inventory required')
    seen, addresses, gaps = set(), set(), []
    for country in countries:
        exact(country, 'handle slot tag pointer government', 'Country')
        slot, tag = handle(country['handle'], count)
        integer(country['slot'], 0, count-1, 'Country slot')
        require(country['slot'] == slot and country['tag'] == tag, 'Full country handle/slot/TAG mismatch')
        require(country['handle'] not in seen, 'Duplicate country inventory')
        seen.add(country['handle']); pointer(country['pointer'], 'Country')
        require(country['pointer'] not in addresses, 'Country object alias'); addresses.add(country['pointer'])
        government = exact(country['government'], 'instance definition variant_170 variant_110', 'Government')
        pointer(government['instance'], 'Government instance', True)
        pointer(government['definition'], 'Government definition', True)
        if government['instance'] is None:
            require(all(government[k] is None for k in ('definition', 'variant_170', 'variant_110')), 'Absent instance has fabricated fields')
            gaps.append('government_missing_requires_fallback:' + tag)
        else:
            for field in ('variant_170', 'variant_110'):
                gap = variant(government[field])
                if gap: gaps.append(gap + ':' + tag + ':' + field)
    require(seen == set(members), 'Country inventory does not match complete war sides')
    require(type(value['relations']) is list and len(value['relations']) == 2, 'Both directed indexes required')
    owners = set()
    for relation in value['relations']:
        exact(relation, 'owner_handle counterpart_handle root data count entries', 'War relation index')
        pair = (relation['owner_handle'], relation['counterpart_handle'])
        require(pair in ((taker, giver), (giver, taker)) and pair not in owners, 'Wrong/duplicate index direction')
        owners.add(pair)
        pointer(relation['root'], 'Relation root'); pointer(relation['data'], 'War index data')
        n = integer(relation['count'], 1, 64, 'Signed index count')
        require(type(relation['entries']) is list and len(relation['entries']) == n, 'War index truncated')
        keys, matches = set(), []
        for entry in relation['entries']:
            exact(entry, 'country_slot war_pointer', 'War index record')
            key = integer(entry['country_slot'], 0, count-1, 'Index key is country slot, not war ID')
            require(key not in keys, 'Ambiguous duplicate war index key'); keys.add(key)
            pointer(entry['war_pointer'], 'Borrowed indexed war')
            if key == handle(relation['counterpart_handle'], count)[0]: matches.append(entry['war_pointer'])
        require(matches == [war['pointer']], 'Reciprocal indexed war mismatch')
    caches = exact(value['caches'], 'nogovernment secondary goal_fallback dependency_registry', 'Globals')
    for name, address in caches.items(): pointer(address, name, True)
    objects = {}
    goal = value['war']['goal']
    require(type(goal) is dict, 'Goal object required')
    selected = None
    if goal.get('kind') == 'unrecognized':
        exact(goal, 'kind pointer vtable_rva', 'Unrecognized goal')
        pointer(goal['pointer'], 'Goal', True)
        if goal['pointer'] is None: require(goal['vtable_rva'] is None, 'Null goal has vtable')
        else: rva(goal['vtable_rva'], image_size, 'Unrecognized goal vtable')
        gaps.append('goal_dynamic_class_unreviewed')
    else:
        exact(goal, 'kind pointer vtable_rva methods definition province_index province province_marker game_provinces_begin game_provinces_end game_province_blocks province_block_field_address province_block_pointer conditions', 'Take-colony goal')
        require(goal['kind'] == 'take_colony' and goal['vtable_rva'] == '0x1d1fd90' and goal['methods'] == GOAL_METHODS, 'Goal pinned method family mismatch')
        pointer(goal['pointer'], 'Goal'); pointer(goal['definition'], 'Goal definition')
        index = integer(goal['province_index'], -(2**31), 2**31-1, 'Goal province index')
        begin = pointer(goal['game_provinces_begin'], 'Game province vector begin')
        end = pointer(goal['game_provinces_end'], 'Game province vector end')
        require(0 <= end-begin <= 32768*8 and (end-begin) % 8 == 0, 'Province vector bounds')
        blocks = pointer(goal['game_province_blocks'], 'Game province blocks')
        pointer(goal['province'], 'Goal province', True); pointer(goal['province_block_pointer'], 'Province block binding', True)
        if 0 <= index < (end-begin)//8:
            field = pointer(goal['province_block_field_address'], 'Province block field')
            require(field == blocks + index * 0x2e10 + 0x560, 'Province block address formula differs')
        else:
            require(goal['province_block_field_address'] is None and goal['province_block_pointer'] is None,
                    'Out-of-range index must not supply a dereferenced province block')
        marker = integer(goal['province_marker'], 0, 2**32-1, 'Province marker')
        valid70 = 0 <= index < (end-begin)//8 and goal['province'] is not None and marker != 0 and goal['province_block_pointer'] == goal['province']
        if not valid70:
            require(goal['conditions'] is None, 'Fallback resolution cannot reuse original definition conditions')
            gaps.append('effective_goal_is_fallback_virtual_family_unreviewed')
        else:
            exact(goal['conditions'], '0x50 0x140 0x288 0x378', 'Four condition vectors')
            for offset, vector in goal['conditions'].items(): condition_vector(vector, goal['definition'], offset, image_size, objects)
            selected = ['0x50', '0x140'] if taker in a else ['0x288', '0x378']
    dependency = exact(value['dependency'], 'definition conditions', 'Registry dependency definition')
    pointer(dependency['definition'], 'Dependency definition', True)
    if dependency['definition'] is None:
        require(dependency['conditions'] is None, 'Absent definition has conditions')
        gaps.append('dependency_definition_missing')
    else:
        require(caches['dependency_registry'] is not None, 'Definition without registry')
        condition_vector(dependency['conditions'], dependency['definition'], '0x40', image_size, objects)
    tls = exact(value['tls'], 'thread_id gate_a gate_b gs58_array slot0_pointer module_index indexed_pointer slot0_initialized_byte slot0_gate_byte indexed_initialized_byte', 'TLS metadata')
    integer(tls['thread_id'], 1, 2**32-1, 'Subject thread')
    integer(tls['gate_a'], 0, 255, '233ff94 byte'); integer(tls['gate_b'], 0, 255, '233fed6 byte')
    integer(tls['module_index'], 0, 4095, 'Initializer TLS index')
    active = tls['gate_a'] == 0 or tls['gate_b'] != 0
    for field in ('gs58_array', 'slot0_pointer', 'indexed_pointer'): pointer(tls[field], field, True)
    for field in ('slot0_initialized_byte', 'slot0_gate_byte', 'indexed_initialized_byte'):
        if tls[field] is not None: integer(tls[field], 0, 255, field)
    fields = ('gs58_array', 'slot0_pointer', 'indexed_pointer', 'slot0_initialized_byte', 'slot0_gate_byte', 'indexed_initialized_byte')
    have_tls = all(tls[field] is not None for field in fields)
    require(have_tls or all(tls[field] is None for field in fields), 'Partial TLS provenance/storage group')
    if active and not have_tls: gaps.append('required_tls_observation_missing')
    if have_tls:
        require(tls['gs58_array'] is not None, 'TLS blocks without source array')
        if tls['module_index'] == 0:
            require(tls['slot0_pointer'] == tls['indexed_pointer'] and tls['slot0_initialized_byte'] == tls['indexed_initialized_byte'], 'Index zero aliases conflict')
        else: gaps.append('caller_index_zero_differs_from_initializer_index')
        if active and tls['slot0_initialized_byte'] == 0: gaps.append('native_tls_initializer_would_run')
        if active and tls['slot0_gate_byte'] == 0: gaps.append('native_tls_gate_skips_candidates')
    if objects: gaps.append('concrete_condition_virtual30_bodies_unreviewed')
    return {'taker_handle': taker, 'giver_handle': giver, 'borrowed_war': war['pointer'],
        'taker_side': 'A' if taker in a else 'B', 'selected_province_condition_offsets': selected,
        'condition_instance_count': len(objects), 'condition_instances': dict(sorted(objects.items())),
        'tls_branch_would_be_entered': active, 'gaps': sorted(set(gaps))}


def parse(raw, contract):
    require(type(contract) is bytes and 0 < len(contract) <= MAX_FILE, 'Contract byte budget')
    document = strict_json(raw)
    exact(document, 'schema_version purpose source_kind exe_sha256 static_contract_sha256 identity binding passes', 'Envelope')
    require(type(document['schema_version']) is int and document['schema_version'] == 1, 'Schema version')
    require(document['purpose'] == 'peace_preconditions_offline_queries_v1' and document['source_kind'] in ('synthetic', 'external_capture_unverified'), 'Offline query purpose/source')
    require(document['exe_sha256'] == EXE_SHA, 'Wrong exact EXE')
    require(document['static_contract_sha256'] == CONTRACT_SHA == hashlib.sha256(contract).hexdigest(), 'Static evidence binding differs')
    static = strict_json(contract)
    require(static['exe_sha256'] == EXE_SHA and static['purpose'] == 'peace_constructor_readonly_query_contract', 'Wrong static contract')
    identity = exact(document['identity'], 'pid creation_filetime module_base image_size image_timestamp', 'Identity')
    integer(identity['pid'], 1, 2**32-1, 'PID')
    require(type(identity['creation_filetime']) is str and CREATION.fullmatch(identity['creation_filetime']) and int(identity['creation_filetime'],16)>0, 'Creation identity')
    pointer(identity['module_base'], 'Module base')
    require(type(identity['image_size']) is int and identity['image_size'] == static['pe']['image_size'], 'Image size')
    require(type(identity['image_timestamp']) is int and identity['image_timestamp'] == static['pe']['timestamp'], 'Image timestamp')
    binding = exact(document['binding'], 'actor_handle recipient_handle direction', 'Direction binding')
    require(binding['direction'] in ('demand', 'concede') and binding['actor_handle'] != binding['recipient_handle'], 'Direction / distinct pair')
    require(type(document['passes']) is list and len(document['passes']) == 2, 'Exactly two bounded observations')
    results, previous_end, snapshots = [], -1, []
    for index, capture in enumerate(document['passes']):
        exact(capture, 'sequence started_tick ended_tick snapshot', 'Capture pass')
        integer(capture['sequence'], index, index, 'Capture sequence')
        start = integer(capture['started_tick'], previous_end+1, 2**64-1, 'Ordered start tick')
        previous_end = integer(capture['ended_tick'], start, 2**64-1, 'Ordered end tick')
        snapshots.append(capture['snapshot']); results.append(snapshot(capture['snapshot'], binding, identity['image_size']))
    require(snapshots[0] == snapshots[1], 'Observed fields changed between passes')
    return {'schema_version': 1, 'purpose': 'peace_readonly_preconditions_observation_only',
        'source_kind': document['source_kind'], 'input_sha256': hashlib.sha256(raw).hexdigest(),
        'static_contract_sha256': document['static_contract_sha256'], 'identity_recorded': identity,
        'structural_query_validation_passed': True, 'selected_fields_equal_two_pass': True,
        'observation': results[0], 'parameter_constructor_authorized': False, 'parameter_selftest_ready': False,
        'source_authenticity_verified': False, 'process_identity_independently_verified': False,
        'world_epoch_verified': False, 'object_lifetime_verified': False, 'engine_thread_provenance_verified': False,
        'tls_source_authenticated': False, 'condition_purity_verified': False, 'constructor_purity_verified': False,
        'runtime_verified': False, 'execution_verified': False, 'production_ready': False,
        'unconditional_unknowns': ['No producer/held process handle or native thread witness is implemented.',
            'Pause and equal observations do not exclude intervening destruction, ABA reuse, migration or reentrant callbacks.',
            'Borrowed war ownership, participant dependency selection and complete auxiliary/candidate call graph remain unclosed.',
            'Conditions are inventory only; empty lists do not prove the full constructor pure.',
            'Known cache/TLS observations do not authorize lazy initialization, condition evaluation, offer construction or submission.']}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('input', type=Path); args = parser.parse_args()
    with args.input.open('rb') as stream: raw = stream.read(MAX_FILE + 1)
    with (HERE/'static-contract.json').open('rb') as stream: contract = stream.read(MAX_FILE + 1)
    print(json.dumps(parse(raw, contract), indent=2))


if __name__ == '__main__': main()
