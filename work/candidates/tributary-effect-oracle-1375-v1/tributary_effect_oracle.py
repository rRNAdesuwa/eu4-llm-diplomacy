"""Pure JSON-shaped candidate comparison; never authenticates or reads its inputs."""
import re

GAME_SHA256 = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
SNAPSHOT_SCHEMA = 'EU4-TRIBUTARY-CANDIDATE-SNAPSHOT/1'
RECEIPT_SCHEMA = 'EU4-TRIBUTARY-CANDIDATE-RECEIPT/1'
SENTINEL = 0x2D2D2D
DEPENDENCY_VTABLE_RVA = 0x1C81758
PROFILES = (
    ('establish_tributary', 'target', 'actor', None, 'tributary_state'),
    ('ask_to_be_tributary', 'actor', 'target', None, 'tributary_state'),
    ('convert_tributary_to_vassal', 'target', 'actor', 'tributary_state', 'vassal'),
)
FALSE_FLAGS = ('inputs_authenticated', 'selected_effect_verified', 'native_action_mapping_verified',
               'native_ready', 'callable', 'AI_acceptance_verified', 'persistence_verified',
               'exclusive_causality_verified', 'world_lease', 'retry_authorized', 'dispatch_authorized')
LIMITATIONS = (
    'A match is only a candidate dependency-state pattern in supplied data.',
    'JSON identity, audit and capture claims do not authenticate an installation or original request.',
    'Action direction/key mapping remains the reviewed candidate inference, not a native commit proof.',
    'A future host must replay raw typed reads and real installation/request audit with source guards.',
    'No rejection, AI-pending state, lifetime, complete side effects, persistence or retry permission follows.',
)


def _result(action, status, reason):
    return dict(schema='EU4-TRIBUTARY-CANDIDATE-RESULT/1', action=action if type(action) is str else None,
                status=status, reason=reason, candidate_pattern_match=status == 'candidate_pattern_match',
                accounting_scope='this_pure_function_only', native_calls=0, requests_published=0, limitations=list(LIMITATIONS),
                **{key: False for key in FALSE_FLAGS})


def catalog():
    return dict(schema='EU4-TRIBUTARY-CANDIDATE-CATALOG/1', game_sha256=GAME_SHA256,
                profiles=[dict(action=a, subject_role=s, overlord_role=l, before_type=b, after_type=e,
                               mapping_grade='candidate_inference', native_action_mapping_verified=False)
                          for a, s, l, b, e in PROFILES],
                count=3, limitations=list(LIMITATIONS), **{key: False for key in FALSE_FLAGS})


def _require(value, reason):
    if not value:
        raise ValueError(reason)


def _dict(value, keys, reason):
    _require(type(value) is dict and len(value) == len(keys) and set(value) == set(keys), reason)
    return value


def _hex(value, width, reason):
    _require(type(value) is str and re.fullmatch('[0-9a-f]{'+str(width)+'}', value)
             and int(value, 16) != 0, reason)
    return value


def _uint(value, bits, reason):
    _require(type(value) is int and 0 <= value < (1 << bits), reason)
    return value


def _address(value):
    if type(value) is str and re.fullmatch(r'0x[0-9a-fA-F]{1,16}', value):
        value = int(value, 16)
    _require(type(value) is int and 0x10000 <= value < 2**47, 'invalid_object_address')
    return value


def _handle(value, count, tag=None, allow_sentinel=False):
    if type(value) is str and re.fullmatch(r'0x[0-9a-fA-F]{1,16}', value):
        value = int(value, 16)
    _uint(value, 64, 'invalid_full_handle')
    if allow_sentinel and value == SENTINEL:
        return value
    slot = (value >> 32) & 0xffff
    name = (value & 0xffffff).to_bytes(3, 'little')
    _require(value >> 56 != 0 and (value >> 48) & 255 == 0 and (value >> 24) & 255 == 0
             and 0 < slot < min(count, 32768) and re.fullmatch(rb'[A-Z0-9]{3}', name), 'invalid_ordinary_handle')
    _require(tag is None or name == tag.encode('ascii'), 'full_handle_tag_mismatch')
    return value


def _identity(value):
    v = _dict(value, ('pid', 'creation', 'session', 'dll_sha256', 'manifest_sha256'), 'identity_fields')
    _uint(v['pid'], 32, 'pid_not_dword')
    _require(v['pid'] != 0, 'zero_pid')
    for key, width in (('creation', 16), ('session', 32), ('dll_sha256', 64), ('manifest_sha256', 64)):
        _hex(v[key], width, 'invalid_identity_'+key)
    return tuple(v[k] for k in ('pid', 'creation', 'session', 'dll_sha256', 'manifest_sha256'))


def _command(value, action):
    v = _dict(value, ('request_id', 'action', 'actor', 'target'), 'command_fields')
    _require(type(v['request_id']) is str and re.fullmatch(r'[A-Za-z0-9_.:-]{1,96}', v['request_id']), 'invalid_request_id')
    _require(type(v['action']) is str and v['action'] == action, 'command_action_mismatch')
    _require(all(type(v[k]) is str and re.fullmatch(r'[A-Z0-9]{3}', v[k]) for k in ('actor', 'target')), 'invalid_tag')
    _require(v['actor'] != v['target'], 'same_actor_target')
    return tuple(v[k] for k in ('request_id', 'action', 'actor', 'target'))


def _index(value, count, selected_slot):
    _require(type(value) is list and len(value) <= 256, 'index_bound')
    slots = set()
    selected = None
    for entry in value:
        e = _dict(entry, ('slot', 'object_address'), 'index_entry_fields')
        slot = e['slot']
        _require(type(slot) is int and 0 < slot < min(count, 32768) and slot not in slots, 'invalid_or_duplicate_index_slot')
        slots.add(slot)
        address = _address(e['object_address'])
        if slot == selected_slot:
            selected = address
    return selected


def _snapshot(value, action, phase):
    keys = ('schema', 'game_sha256', 'identity', 'command', 'phase', 'country_count', 'pair',
            'dependency_indexes', 'dependency_object', 'capture_claims')
    if phase == 'before':
        keys += ('baseline_claims',)
    v = _dict(value, keys, 'snapshot_fields')
    _require(v['schema'] == SNAPSHOT_SCHEMA and v['game_sha256'] == GAME_SHA256 and v['phase'] == phase, 'snapshot_schema_target_phase')
    identity = _identity(v['identity'])
    command = _command(v['command'], action)
    count = v['country_count']
    _require(type(count) is int and 1 < count <= 32768, 'country_count_bound')
    claims = _dict(v['capture_claims'], ('two_pass_equal', 'typed_countries_and_roots', 'complete_active_indexes'), 'capture_claim_fields')
    _require(all(x is True for x in claims.values()), 'incomplete_capture_claims')
    if phase == 'before':
        claims = _dict(v['baseline_claims'], ('immutable', 'before_publication', 'intent_absent_before', 'intent_absent_after',
                                             'publisher_lock_absent_before', 'publisher_lock_absent_after',
                                             'intent_absent_before_commit', 'publisher_lock_absent_before_commit'), 'baseline_claim_fields')
        _require(all(x is True for x in claims.values()), 'unproven_baseline_claims')
    p = _dict(v['pair'], ('actor_tag', 'target_tag', 'actor_handle', 'target_handle',
                         'actor_overlord_handle', 'target_overlord_handle', 'dependency_present', 'dependency_type'), 'pair_fields')
    _require(p['actor_tag'] == command[2] and p['target_tag'] == command[3], 'pair_command_tag_mismatch')
    actor = _handle(p['actor_handle'], count, command[2])
    target = _handle(p['target_handle'], count, command[3])
    _require(actor != target and ((actor >> 32) & 0xffff) != ((target >> 32) & 0xffff), 'pair_identity_collision')
    lords = {side: _handle(p[side+'_overlord_handle'], count, allow_sentinel=True) for side in ('actor', 'target')}
    present = p['dependency_present']
    _require(type(present) is bool, 'dependency_present_not_bool')
    typ = p['dependency_type']
    _require(typ is None or (type(typ) is str and re.fullmatch(r'[a-z][a-z0-9_]{0,63}', typ)), 'invalid_dependency_type')
    indexes = _dict(v['dependency_indexes'], ('actor', 'target'), 'bilateral_index_fields')
    left = _index(indexes['actor'], count, (target >> 32) & 0xffff)
    right = _index(indexes['target'], count, (actor >> 32) & 0xffff)
    _require(left == right, 'bilateral_selected_object_mismatch')
    obj = v['dependency_object']
    if not present:
        _require(left is None and typ is None and obj is None, 'inconsistent_typed_absence')
    else:
        o = _dict(obj, ('address', 'vtable_rva', 'removed_byte_28', 'endpoints', 'type_key'), 'dependency_object_fields')
        _require(left is not None and _address(o['address']) == left, 'object_not_bilaterally_indexed')
        _require(type(o['vtable_rva']) is int and o['vtable_rva'] == DEPENDENCY_VTABLE_RVA, 'dependency_type_mismatch')
        _require(type(o['removed_byte_28']) is int and o['removed_byte_28'] == 0, 'dependency_removed_or_malformed')
        _require(type(o['endpoints']) is list and len(o['endpoints']) == 2, 'endpoint_shape')
        endpoints = [_handle(h, count) for h in o['endpoints']]
        _require(set(endpoints) == {actor, target}, 'dependency_full_endpoints_mismatch')
        _require(typ is not None and o['type_key'] == typ, 'definition_key_projection_mismatch')
    return dict(identity=identity, command=command, actor=actor, target=target, lords=lords,
                present=present, typ=typ, count=count)


def _receipt(value, action, before):
    v = _dict(value, ('schema', 'game_sha256', 'identity', 'command', 'binding', 'sequence', 'state',
                      'native_result', 'audit_claims'), 'receipt_fields')
    _require(v['schema'] == RECEIPT_SCHEMA and v['game_sha256'] == GAME_SHA256, 'receipt_schema_target')
    _require(_identity(v['identity']) == before['identity'] and _command(v['command'], action) == before['command'], 'receipt_identity_request_mismatch')
    _require(type(v['sequence']) is int and 1 <= v['sequence'] <= 128, 'receipt_sequence_bound')
    _require(v['state'] == 'dispatched', 'receipt_not_complete_dispatch')
    binding = _dict(v['binding'], ('actor_handle', 'target_handle'), 'binding_fields')
    _require(_handle(binding['actor_handle'], before['count'], before['command'][2]) == before['actor']
             and _handle(binding['target_handle'], before['count'], before['command'][3]) == before['target'], 'receipt_full_binding_mismatch')
    n = _dict(v['native_result'], ('status', 'submitted', 'slot_consumed', 'ownership_closed',
                                  'owned_live', 'quarantined', 'adapter_fault', 'submit_exception'), 'native_receipt_fields')
    _require(type(n['status']) is int and n['status'] == 4, 'native_status_not_dispatched')
    _require(all(n[k] is True for k in ('submitted', 'slot_consumed', 'ownership_closed')), 'incomplete_dispatch_flags')
    _require(all(type(n[k]) is int and n[k] == 0 for k in ('owned_live', 'quarantined', 'adapter_fault', 'submit_exception')), 'dispatch_not_closed')
    a = _dict(v['audit_claims'], ('installation_record_verified', 'original_request_audit_complete', 'native_dispatch_audit_complete',
                                 'identity', 'request_id', 'audit_sha256'), 'audit_claim_fields')
    _require(all(a[k] is True for k in ('installation_record_verified', 'original_request_audit_complete', 'native_dispatch_audit_complete')), 'incomplete_audit_claims')
    _require(_identity(a['identity']) == before['identity'] and a['request_id'] == before['command'][0], 'audit_session_request_mismatch')
    _hex(a['audit_sha256'], 64, 'audit_digest_invalid')


def evaluate(action, before, after, receipt):
    """Compare untrusted data only. No input flag can elevate output authority."""
    if type(action) is not str or action not in {row[0] for row in PROFILES}:
        return _result(action, 'unknown', 'unsupported_action')
    try:
        b, a = _snapshot(before, action, 'before'), _snapshot(after, action, 'after')
        _require(b['identity'] == a['identity'] and b['command'] == a['command'], 'capture_session_request_mismatch')
        _require((b['actor'], b['target']) == (a['actor'], a['target']), 'capture_full_handle_changed')
        _receipt(receipt, action, b)
        _, subject, lord, old_key, new_key = next(row for row in PROFILES if row[0] == action)
        expected_lord = b[lord]
        if old_key is None:
            baseline_ok = b['present'] is False and b['typ'] is None and b['lords'][subject] == SENTINEL
        else:
            baseline_ok = b['present'] is True and b['typ'] == old_key and b['lords'][subject] == expected_lord
        _require(baseline_ok, 'baseline_not_selected_transition_origin')
        matched = a['present'] is True and a['typ'] == new_key and a['lords'][subject] == expected_lord
        result = _result(action, 'candidate_pattern_match' if matched else 'pattern_not_matched',
                         'candidate_dependency_transition_only' if matched else 'valid_data_selected_postcondition_not_matched')
        result['candidate_transition'] = dict(subject_role=subject, overlord_role=lord,
                                              before_type=b['typ'], after_type=a['typ'])
        return result
    except (ValueError, TypeError, KeyError, OverflowError, UnicodeError):
        return _result(action, 'unknown', 'incomplete_inconsistent_or_invalid_candidate_inputs')
