"""Finite copied-data war graph comparison. No imports, I/O or runtime access."""

VIEW_SCHEMA = 'EU4-WAR-GRAPH-COPIED-VIEW/1'
RESULT_SCHEMA = 'EU4-WAR-GRAPH-DATA-PATTERN/1'
LIMITS = {'global_wars': 64, 'side_members': 64,
          'member_occurrences': 8192, 'unique_countries': 1379,
          'country_count': 1380}
AUTHORITY_FIELDS = (
    'input_authenticated', 'current_runtime_state_verified',
    'original_request_causality_verified', 'request_dispatch_verified',
    'effect_verified', 'AI_acceptance_verified', 'terms_verified',
    'war_creation_verified', 'war_retirement_verified', 'peace_completion_verified',
    'native_ready', 'sender_authorized', 'actual_native_predicate_evaluated',
    'world_epoch_proven', 'atomic_snapshot', 'lifetime_lease',
    'persistence_verified', 'same_address_continuity_verified', 'authorizes_retry')
_VIEW_KEYS = ('schema', 'identity', 'world', 'actor', 'target',
              'complete_current_global_scan', 'global_war_count', 'wars')
_WORLD_KEYS = ('game_address', 'database_address', 'country_table_address',
               'now_raw', 'country_count')
_COUNTRY_KEYS = ('address', 'handle', 'tag', 'slot')
_WAR_KEYS = ('current_war_address', 'vtable_rva', 'marker', 'started_raw_date',
             'primary_attacker_handle', 'primary_defender_handle',
             'goal_pointer_raw', 'attackers', 'defenders', 'raw_outcome')


class _Invalid(ValueError):
    pass


def _need(condition, reason):
    if not condition:
        raise _Invalid(reason)


def _keys(value, keys):
    _need(type(value) is dict, 'expected_exact_dict')
    _need(len(value) == len(keys), 'unexpected_or_missing_keys')
    _need(all(type(k) is str and len(k) <= 64 for k in value), 'invalid_key_type')
    _need(set(value) == set(keys), 'unexpected_or_missing_keys')


def _integer(value, low, high):
    _need(type(value) is int and low <= value <= high, 'integer_type_or_bound')
    return value


def _hex(value):
    _need(type(value) is str and 3 <= len(value) <= 18, 'hex_type_or_length')
    _need(value[:2] == '0x' and value[2] != '0'
          and all(c in '0123456789abcdef' for c in value[2:]), 'noncanonical_hex')
    return int(value[2:], 16)


def _pointer(value, size):
    n = _hex(value)
    _need(0x10000 <= n < n + size <= 2**47 and n % 8 == 0, 'pointer_shape')
    return n


def _handle(value):
    n = _hex(value)
    _need(0 < n < 2**64 and n >> 56 != 0 and (n >> 48) & 255 == 0
          and (n >> 24) & 255 == 0, 'ordinary_handle_encoding')
    slot = (n >> 32) & 0xffff
    _need(0 < slot < LIMITS['country_count'], 'ordinary_handle_slot')
    raw = (n & 0xffffff).to_bytes(3, 'little')
    _need(all(48 <= b <= 57 or 65 <= b <= 90 for b in raw), 'ordinary_handle_tag')
    return n, slot, raw.decode('ascii')


def _country(value, registry):
    _keys(value, _COUNTRY_KEYS)
    handle, slot, tag = _handle(value['handle'])
    _need(type(value['tag']) is str and value['tag'] == tag, 'country_tag_differs')
    _need(type(value['slot']) is int and value['slot'] == slot, 'country_slot_differs')
    address = _pointer(value['address'], 0x28)
    normalized = (address, handle, tag, slot)
    if handle in registry['handles']:
        _need(registry['handles'][handle] == normalized, 'country_identity_rebound')
    _need(slot not in registry['slots'] or registry['slots'][slot] == handle, 'country_slot_alias')
    _need(address not in registry['addresses'] or registry['addresses'][address] == handle, 'country_address_alias')
    registry['handles'][handle] = normalized
    registry['slots'][slot] = handle
    registry['addresses'][address] = handle
    _need(len(registry['handles']) <= LIMITS['unique_countries'], 'country_identity_budget')
    return normalized


def _side(value, registry):
    _need(type(value) is list and 1 <= len(value) <= LIMITS['side_members'], 'side_type_or_bound')
    registry['occurrences'] += len(value)
    _need(registry['occurrences'] <= LIMITS['member_occurrences'], 'member_occurrence_budget')
    rows = [_country(item, registry) for item in value]
    handles = tuple(item[1] for item in rows)
    _need(len(set(handles)) == len(handles), 'duplicate_side_member')
    return handles


def _view(value, actor_handle, target_handle):
    _keys(value, _VIEW_KEYS)
    _need(type(value['schema']) is str and value['schema'] == VIEW_SCHEMA, 'view_schema')
    _keys(value['identity'], ('pid', 'creation'))
    pid = _integer(value['identity']['pid'], 1, 0xffffffff)
    creation = value['identity']['creation']
    _need(type(creation) is str and len(creation) == 16
          and all(c in '0123456789abcdef' for c in creation)
          and int(creation, 16) != 0, 'creation_shape')
    _keys(value['world'], _WORLD_KEYS)
    raw_world = value['world']
    world_addresses = tuple(_pointer(raw_world[key], 8) for key in _WORLD_KEYS[:3])
    now = _integer(raw_world['now_raw'], 1, 0x7fffffff)
    _need(type(raw_world['country_count']) is int
          and raw_world['country_count'] == LIMITS['country_count'], 'country_count_profile')
    _need(value['complete_current_global_scan'] is True, 'incomplete_global_view')
    count = _integer(value['global_war_count'], 0, LIMITS['global_wars'])
    raw_wars = value['wars']
    _need(type(raw_wars) is list and len(raw_wars) == count, 'global_list_count')
    registry = {'handles': {}, 'slots': {}, 'addresses': {}, 'occurrences': 0}
    actor = _country(value['actor'], registry)
    target = _country(value['target'], registry)
    _need(actor[1] == actor_handle and target[1] == target_handle, 'selected_handle_binding')
    wars = {}
    order = []
    for raw in raw_wars:
        _keys(raw, _WAR_KEYS)
        address = _pointer(raw['current_war_address'], 0x218)
        _need(address not in wars, 'duplicate_global_address')
        _need(type(raw['vtable_rva']) is str and raw['vtable_rva'] == '0x1d1f768', 'war_type_profile')
        _need(type(raw['marker']) is int and raw['marker'] == 357, 'war_raw_marker_profile')
        started = _integer(raw['started_raw_date'], 1, now)
        attackers = _side(raw['attackers'], registry)
        defenders = _side(raw['defenders'], registry)
        _need(not set(attackers) & set(defenders), 'overlapping_sides')
        primary_a = _handle(raw['primary_attacker_handle'])[0]
        primary_d = _handle(raw['primary_defender_handle'])[0]
        _need(primary_a in attackers and primary_d in defenders, 'primary_not_in_side')
        goal = _pointer(raw['goal_pointer_raw'], 1)
        outcome = _integer(raw['raw_outcome'], 0, 0xffffffff)
        wars[address] = {'started_raw_date': started, 'primary_attacker_handle': primary_a,
                         'primary_defender_handle': primary_d, 'goal_pointer_raw': goal,
                         'raw_outcome': outcome, 'attackers': attackers, 'defenders': defenders}
        order.append(address)
    _need(not set(wars) & set(registry['addresses']), 'war_country_address_alias')
    return {'identity': (pid, creation), 'world_addresses': world_addresses, 'now_raw': now,
            'actor': actor, 'target': target, 'wars': wars, 'order': tuple(order),
            'countries': registry['handles'], 'country_slots': registry['slots']}


def _opposing(view, actor, target):
    return {address for address, w in view['wars'].items()
            if (actor in w['attackers'] and target in w['defenders'])
            or (actor in w['defenders'] and target in w['attackers'])}


def _hexes(values):
    return [hex(v) for v in sorted(values)]


def evaluate_graph_change(before, after, actor_handle, target_handle):
    """Compare bounded copied views. Valid output is ONLY a data pattern."""
    result = {'schema': RESULT_SCHEMA, 'status': 'unknown', 'selected_pair': None,
              'pattern': None, 'failure': None,
              'authority': {name: False for name in AUTHORITY_FIELDS},
              'ambiguities': ['Equal process/root metadata does not exclude reload or ABA.',
                              'Same address never proves continuous identity of one war.',
                              'Copied views and completeness claims are not authenticated.',
                              'No request, effect, acceptance, terms or persistence is evaluated.']}
    stage = 'selection'
    try:
        ah = _handle(actor_handle)[0]
        th = _handle(target_handle)[0]
        _need(ah != th, 'selected_pair_same_handle')
        stage = 'before'
        a = _view(before, ah, th)
        stage = 'after'
        b = _view(after, ah, th)
        stage = 'comparison'
        _need(a['identity'] == b['identity'], 'process_identity_metadata_changed')
        _need(a['world_addresses'] == b['world_addresses'], 'world_address_metadata_changed')
        _need(a['actor'] == b['actor'] and a['target'] == b['target'], 'selected_country_identity_changed')
        _need(a['now_raw'] <= b['now_raw'], 'raw_date_order_reversed')
        for h in a['countries'].keys() & b['countries'].keys():
            _need(a['countries'][h] == b['countries'][h], 'shared_country_identity_changed')
        for slot in a['country_slots'].keys() & b['country_slots'].keys():
            _need(a['country_slots'][slot] == b['country_slots'][slot], 'shared_country_slot_generation_changed')
        left, right = set(a['wars']), set(b['wars'])
        same_changes = []
        unchanged = []
        payload = ('started_raw_date', 'primary_attacker_handle', 'primary_defender_handle',
                   'goal_pointer_raw', 'raw_outcome')
        for address in sorted(left & right):
            x, y = a['wars'][address], b['wars'][address]
            fields = [name for name in payload if x[name] != y[name]]
            members = {}
            order_changed = {}
            for side in ('attackers', 'defenders'):
                old, new = set(x[side]), set(y[side])
                members[side] = {'handles_added_in_view': _hexes(new-old),
                                 'handles_removed_in_view': _hexes(old-new)}
                order_changed[side] = x[side] != y[side]
            if fields or any(order_changed.values()):
                same_changes.append({'address': hex(address), 'changed_raw_payload_fields': fields,
                                     'members': members, 'side_order_changed': order_changed,
                                     'comparison_is_same_address_pattern_only': True,
                                     'continuous_object_identity_verified': False})
            else:
                unchanged.append(address)
        old_pair, new_pair = _opposing(a, ah, th), _opposing(b, ah, th)
        result.update(status='observed_data_pattern', selected_pair={'actor_handle': hex(ah), 'target_handle': hex(th)},
                      pattern={'global_addresses_added_in_view': _hexes(right-left),
                               'global_addresses_removed_in_view': _hexes(left-right),
                               'global_order_changed': a['order'] != b['order'],
                               'same_address_changes': same_changes,
                               'same_addresses_unchanged_in_copied_fields': _hexes(unchanged),
                               'selected_pair_opposing_addresses_before': _hexes(old_pair),
                               'selected_pair_opposing_addresses_after': _hexes(new_pair),
                               'selected_pair_opposing_addresses_added_in_view': _hexes(new_pair-old_pair),
                               'selected_pair_opposing_addresses_removed_in_view': _hexes(old_pair-new_pair),
                               'raw_date_before': a['now_raw'], 'raw_date_after': b['now_raw'],
                               'multiple_opposing_addresses_in_copied_data': len(old_pair)>1 or len(new_pair)>1,
                               'runtime_reader_multiple_opposing_supported': False})
    except _Invalid as exc:
        result['failure'] = {'stage': stage, 'reason': exc.args[0]}
    except (ValueError, TypeError, OverflowError):
        result['failure'] = {'stage': stage, 'reason': 'malformed_copied_value'}
    return result


def catalog():
    """Finite protocol metadata, never an execution capability grant."""
    return {'schema': 'EU4-WAR-GRAPH-DATA-ORACLE-CATALOG/1',
            'functions': ['evaluate_graph_change', 'catalog'], 'input_schema': VIEW_SCHEMA,
            'statuses': ['observed_data_pattern', 'unknown'], 'limits': dict(LIMITS),
            'strict_keys': {'view': list(_VIEW_KEYS), 'world': list(_WORLD_KEYS),
                            'country': list(_COUNTRY_KEYS), 'war': list(_WAR_KEYS)},
            'accepts_runtime_capture_receipts': False, 'runtime_adapter_implemented': False,
            'copied_schema_supports_multiple_opposing_addresses': True,
            'frozen_war_r2_strictly_rejects_multiple_opposing_addresses': True,
            'caller_metadata_can_authenticate_inputs': False,
            'authority': {name: False for name in AUTHORITY_FIELDS}}
