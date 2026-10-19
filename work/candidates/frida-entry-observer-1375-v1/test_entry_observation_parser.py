"""Offline byte-layout fixtures; never opens a process or invokes the JS hook.

Constants/layout are transcribed from the fixed JS/CONTRACT, independently of
the parser's constants. A dict owns the synthetic bytes at numeric addresses;
those addresses have no connection to a running process.
"""
import copy
import json
import struct
import unittest

import entry_observation_parser as parser


BASE = 0x140000000
Q = 0x100008
OUTER, GAME, SERVER = 0x500000, 0x600000, 0x700000
HOLDER, MAP, PENDING, PREVIOUS = 0x800000, 0x900000, 0xA00000, 0xB00000
SHA = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
PREFIX = '4c89442418555357488d6c24b04881ec50010000488b159d8f2901488bf9440f'
NONCE = '0123456789abcdef0123456789abcdef'


def hx(value):
    return '0x%016x' % value


def raw(value, size=8):
    return struct.pack('<B' if size == 1 else '<Q', value).hex()


def fixture(pending=True, previous=True, attempts=1, prefilter_reads=None,
            pending_vtable=0x1401CB8478, previous_vtable=0x1401CB8490,
            base=BASE, q=Q):
    """Construct evidence from an owned byte layout, not expected parser output."""
    config = dict(schema='EU4-FRIDA-ENTRY-CONFIG/1', pid=80340,
                  creation='01dd5c075fcf8c26', game_sha256=SHA, base=hx(base),
                  expected_prefix_hex=PREFIX, observer_nonce=NONCE, max_attempts=16)
    layout = [
        ('outer', base+0x242BF50, 8, OUTER),
        ('game', base+0x233FE78, 8, GAME),
        ('outer_vtable', OUTER, 8, base+0x1C48BF8),
        ('outer_secondary_vtable', OUTER+0x10, 8, base+0x1C48C80),
        ('current_app', OUTER+0x40, 8, SERVER),
        ('pending_app', OUTER+0x70, 8, PENDING if pending else 0),
        ('previous_app', OUTER+0x78, 8, PREVIOUS if previous else 0),
        ('transition_byte', OUTER+0x48, 1, 0),
        ('retain_previous_byte', OUTER+0x80, 1, 1),
        ('game_vtable', GAME, 8, base+0x1CB00C8),
        ('game_server', GAME+0x1E00, 8, SERVER),
        ('current_vtable', SERVER, 8, base+0x1CB8460),
        ('current_update', base+0x1CB8460+0x20, 8, base+0x8137C0),
        ('server_holder', SERVER+0x330, 8, HOLDER),
        ('map_object', HOLDER+0x360, 8, MAP)]
    if pending:
        layout.append(('pending_vtable', PENDING, 8, pending_vtable))
    if previous:
        layout.append(('previous_vtable', PREVIOUS, 8, previous_vtable))
    stack = [(0, base+0x10A6D61), (0x40, base+0x81582E),
             (0x370, base+0x14C2818), (0x3F0, base+0x14C2E18),
             (0x440, base+0x8781B9), (0x4A8, OUTER)]
    memory = {(address, size): bytes.fromhex(raw(value, size))
              for _, address, size, value in layout}
    memory.update({(q+offset, 8): bytes.fromhex(raw(value)) for offset, value in stack})
    slots = [dict(offset=offset, address=hx(q+offset),
                  raw8_hex=memory[q+offset, 8].hex(),
                  value=hx(struct.unpack('<Q', memory[q+offset, 8])[0]))
             for offset, _ in stack]
    fields, reads = {}, []
    for name, address, size, _ in layout:
        owned = memory[address, size]
        value = struct.unpack('<B' if size == 1 else '<Q', owned)[0]
        fields[name] = value if size == 1 else hx(value)
        reads.append(dict(field=name, address=hx(address), size=size, raw_hex=owned.hex()))
    if not pending:
        fields['pending_vtable'] = None
    if not previous:
        fields['previous_vtable'] = None
    projection = dict(slots=slots, fields=fields, reads=reads)
    optional = int(pending)+int(previous)
    prefilter = 5*attempts if prefilter_reads is None else prefilter_reads
    categories = dict(prefix_before=dict(reads=1, bytes=32),
                      prefilter=dict(reads=prefilter, bytes=8*prefilter),
                      stack=dict(reads=7, bytes=56),
                      world=dict(reads=2*(15+optional), bytes=2*(106+8*optional)),
                      prefix_cleanup=dict(reads=1, bytes=32))
    nbytes = sum(row['bytes'] for row in categories.values())
    payload = dict(schema='EU4-FRIDA-ENTRY-OBSERVATION/1', status='structural_match',
        reason='selected_entry_chain_observed', observer_nonce=NONCE, configured_pid=80340,
        configured_creation=config['creation'], configured_game_sha256=SHA, module_base=hx(base),
        entry_rva=0x10A6EC0, attempts=attempts,
        observation=dict(source='Frida_Interceptor_onEnter_before_original_prologue',
            Q=hx(q), original_rcx=hx(MAP), original_r8=hx(SERVER), thread_id=4412,
            interceptor_depth=0, first=projection, second=copy.deepcopy(projection),
            two_pass_equal=True),
        temporary_code_hook=True, field_game_data_writes=0, native_game_calls=0,
        native_game_objects_constructed=0, pure_RPM=False, native_ready=False,
        native_entry_authenticated=False, creation_authenticated_in_script=False,
        image_sha_verified_in_script=False, lifetime_lease=False, atomic_snapshot=False,
        budgets=dict(scope='all explicit readByteArray requests in this script',
            max_reads=128, max_bytes=8192, max_message_envelope_bytes=16384,
            stack_window_read=False),
        counters=dict(reads=sum(row['reads'] for row in categories.values()),
            requested_bytes=nbytes, exact_bytes=nbytes, categories=categories),
        cleanup=dict(listener_detach_attempted=True, listener_detach_returned=True,
            interceptor_flush_returned=True, original_prefix32_matches=True,
            host_cleanup_still_required=True))
    return payload, config


def passes(payload):
    return (payload['observation']['first'], payload['observation']['second'])


def change_field(payload, name, value):
    """Make a coherent raw/decoded change in both projections."""
    for project in passes(payload):
        project['fields'][name] = value
        for row in project['reads']:
            if row['field'] == name:
                row['raw_hex'] = raw(value if row['size'] == 1 else int(value, 16), row['size'])


def recalculate(payload):
    counters = payload['counters']
    counters['reads'] = sum(row['reads'] for row in counters['categories'].values())
    counters['requested_bytes'] = sum(row['bytes'] for row in counters['categories'].values())
    counters['exact_bytes'] = counters['requested_bytes']


class EntryObservationParserTests(unittest.TestCase):
    def match(self, payload, config):
        result = parser.evaluate(payload, config)
        self.assertEqual(result['status'], 'structural_match', result)
        self.assertIs(result['structural_match'], True)
        self.authority_closed(result)
        return result

    def unknown(self, payload, config):
        result = parser.evaluate(payload, config)
        self.assertEqual(result['status'], 'unknown', result)
        self.assertIs(result['structural_match'], False)
        self.authority_closed(result)
        return result

    def authority_closed(self, result):
        for name in ('requires_host_authentication', 'requires_rea_evidence',
                     'requires_independent_code_restore_verification'):
            self.assertIs(result[name], True)
        for name in ('host_identity_authenticated', 'creation_authenticated', 'image_sha_verified',
                     'code_restore_verified', 'native_ready', 'native_entry_authenticated',
                     'lifetime_lease', 'atomic_snapshot', 'AI_acceptance_verified',
                     'gameplay_effects_verified', 'pure_RPM', 'parser_dereferences_addresses'):
            self.assertIs(result[name], False)

    def test_normal_layout_and_optional_counts(self):
        for pending, previous, counts in ((True, True, (48, 404)), (False, False, (44, 372)),
                                          (True, False, (46, 388)), (False, True, (46, 388))):
            with self.subTest(pending=pending, previous=previous):
                payload, config = fixture(pending, previous)
                result = self.match(payload, config)
                self.assertEqual((result['explicit_reads'], result['explicit_exact_bytes']), counts)
                self.assertEqual(result['explicit_requested_bytes'], counts[1])
                self.assertEqual(result['optional_nonnull_count'], int(pending)+int(previous))

    def test_sixteenth_callback_after_bad_fifth_slot_budget(self):
        result = self.match(*fixture(attempts=16))
        self.assertEqual((result['explicit_reads'], result['explicit_exact_bytes']), (123, 1004))

    def test_each_attempt_prefilter_endpoints(self):
        for attempt in range(1, 17):
            for count in {attempt+4, 5*attempt}:
                with self.subTest(attempt=attempt, count=count):
                    self.match(*fixture(attempts=attempt, prefilter_reads=count))

    def test_optional_vtable_is_raw_uint64_not_object_pointer(self):
        for value in (0, 1, 0xFFFFFFFFFFFFFFFF, 0x8000000000000000):
            with self.subTest(value=value):
                self.match(*fixture(pending_vtable=value, previous_vtable=value))

    def test_transition_bytes_are_not_a_zero_state_requirement(self):
        for value in (0, 1, 127, 255):
            payload, config = fixture()
            change_field(payload, 'transition_byte', value)
            change_field(payload, 'retain_previous_byte', 255-value)
            self.match(payload, config)

    def test_normalized_config_hex_and_zero_nonce(self):
        payload, config = fixture()
        config['base'] = '0X140000000'
        config['observer_nonce'] = payload['observer_nonce'] = '0'*32
        self.match(payload, config)

    def test_config_fields_and_fixed_profile(self):
        changes = {'schema':'wrong', 'pid':True, 'creation':'ABCDEF0123456789',
                   'game_sha256':'0'*64, 'base':hx(BASE+8), 'expected_prefix_hex':'00'*32,
                   'observer_nonce':'0'*31, 'max_attempts':15}
        for key, value in changes.items():
            with self.subTest(key=key):
                payload, config = fixture()
                config[key] = value
                self.unknown(payload, config)
        for key in fixture()[1]:
            payload, config = fixture()
            del config[key]
            self.unknown(payload, config)
        payload, config = fixture()
        config['extra'] = 0
        self.unknown(payload, config)

    def test_config_numeric_and_module_span_boundaries(self):
        for key, values in {'pid':(0, -1, 0x100000000, 80340.0),
                            'max_attempts':(True, 16.0),
                            'base':('0x0', '0x10001', '0x7fffffff0000', '0xfffffffffffff000',
                                    '0x00007ffffdbbd000', 0x140000000)}.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    payload, config = fixture()
                    config[key] = value
                    self.unknown(payload, config)

    def test_config_pid_uint32_endpoints_are_allowed(self):
        for pid in (1, 0xFFFFFFFF):
            payload, config = fixture()
            config['pid'] = payload['configured_pid'] = pid
            self.match(payload, config)

    def test_old_nonce_and_identity_mismatch(self):
        for key, value in {'observer_nonce':'f'*32, 'configured_pid':80341,
                           'configured_creation':'0'*16, 'configured_game_sha256':'0'*64,
                           'module_base':hx(BASE+0x1000), 'entry_rva':0x10A6EC1}.items():
            with self.subTest(key=key):
                payload, config = fixture()
                payload[key] = value
                self.unknown(payload, config)

    def test_observation_source_and_missing_context(self):
        for value in ('Frida_onLeave', 'saved_context', '', True):
            payload, config = fixture()
            payload['observation']['source'] = value
            self.unknown(payload, config)
        for key in fixture()[0]['observation']:
            payload, config = fixture()
            del payload['observation'][key]
            self.unknown(payload, config)

    def test_q_range_alignment_canonical_encoding(self):
        for q in (hx(Q+8), hx(0), hx(0x7FFFFFFEFFF8), hx(0x800000000000),
                  '0x100008', '0X0000000000100008', True):
            payload, config = fixture()
            payload['observation']['Q'] = q
            self.unknown(payload, config)
        self.match(*fixture(q=0x10008))

    def test_thread_and_depth_exact_integer(self):
        for key, values in {'thread_id':(0, -1, 0x100000000, True, 4412.0),
                            'interceptor_depth':(1, -1, False, 0.0)}.items():
            for value in values:
                payload, config = fixture()
                payload['observation'][key] = value
                self.unknown(payload, config)
        for tid in (1, 0xFFFFFFFF):
            payload, config = fixture()
            payload['observation']['thread_id'] = tid
            self.match(payload, config)

    def test_original_register_pointer_semantics(self):
        for key in ('original_rcx', 'original_r8'):
            for value in (hx(0), hx(1), hx(0xFFFFFFFFFFFFFFFF), hx(MAP+1), False):
                payload, config = fixture()
                payload['observation'][key] = value
                self.unknown(payload, config)

    def test_five_return_slots_and_holder_are_independently_checked(self):
        for index in range(6):
            payload, config = fixture()
            for project in passes(payload):
                slot = project['slots'][index]
                changed = int(slot['value'], 16)+8
                slot['value'], slot['raw8_hex'] = hx(changed), raw(changed)
            self.unknown(payload, config)

    def test_owned_slot_actual_source_and_encoding(self):
        for key, value in (('address', hx(Q+8)), ('offset', True), ('offset', 1),
                           ('raw8_hex', '00'*7), ('raw8_hex', 'GG'*8),
                           ('raw8_hex', '00'*8), ('value', hx(BASE+0x10A6D62))):
            payload, config = fixture()
            for project in passes(payload):
                project['slots'][0][key] = value
            self.unknown(payload, config)
        payload, config = fixture()
        for project in passes(payload):
            project['slots'].reverse()
        self.unknown(payload, config)

    def test_no_stack_window_or_extra_slot(self):
        for extra in (True, False):
            payload, config = fixture()
            for project in passes(payload):
                if extra:
                    project['slots'].append(copy.deepcopy(project['slots'][0]))
                else:
                    project['slots'].pop()
            self.unknown(payload, config)

    def test_two_owned_passes_must_match_not_just_flag(self):
        payload, config = fixture()
        payload['observation']['second']['fields']['transition_byte'] = 3
        self.unknown(payload, config)
        for flag in (False, 1, 'true'):
            payload, config = fixture()
            payload['observation']['two_pass_equal'] = flag
            self.unknown(payload, config)

    def test_world_type_and_current_update_checks(self):
        for field in ('outer_vtable', 'outer_secondary_vtable', 'game_vtable',
                      'current_vtable', 'current_update'):
            payload, config = fixture()
            change_field(payload, field, hx(int(payload['observation']['first']['fields'][field], 16)+8))
            self.unknown(payload, config)

    def test_current_game1e00_r8_and_map_rcx_relations(self):
        for field in ('current_app', 'game_server', 'map_object'):
            payload, config = fixture()
            change_field(payload, field, hx(0xC00000))
            self.unknown(payload, config)
        for register in ('original_rcx', 'original_r8'):
            payload, config = fixture()
            payload['observation'][register] = hx(0xC00000)
            self.unknown(payload, config)

    def test_world_root_pointer_types_and_address_bounds(self):
        for field in ('outer', 'game', 'current_app', 'pending_app', 'previous_app',
                      'game_server', 'server_holder'):
            for value in (1, 0xFFFF, 0xFFFFFFFFFFFFFFFF, 0x7FFFFFFEFFF8):
                payload, config = fixture()
                change_field(payload, field, hx(value))
                self.unknown(payload, config)

    def test_world_read_each_actual_field_address(self):
        for index in range(17):
            payload, config = fixture()
            for project in passes(payload):
                row = project['reads'][index]
                row['address'] = hx(int(row['address'], 16)+8)
            self.unknown(payload, config)

    def test_world_read_field_order_size_and_raw(self):
        for key, value in (('field', 'game'), ('size', True), ('size', 8.0),
                           ('size', 7), ('raw_hex', '00'*7), ('raw_hex', '00'*8)):
            payload, config = fixture()
            for project in passes(payload):
                project['reads'][0][key] = value
            self.unknown(payload, config)
        payload, config = fixture()
        for project in passes(payload):
            project['reads'][0], project['reads'][1] = project['reads'][1], project['reads'][0]
        self.unknown(payload, config)

    def test_world_field_and_read_shape_is_exact(self):
        for location in ('fields', 'reads'):
            for extra in (False, True):
                payload, config = fixture()
                for project in passes(payload):
                    target = project[location]
                    if location == 'fields':
                        if extra:
                            target['extra'] = 0
                        else:
                            del target['outer']
                    elif extra:
                        target.append(copy.deepcopy(target[0]))
                    else:
                        target.pop()
                self.unknown(payload, config)

    def test_optional_null_requires_null_diagnostic_and_no_read(self):
        for field in ('pending_vtable', 'previous_vtable'):
            payload, config = fixture(False, False)
            for project in passes(payload):
                project['fields'][field] = hx(0)
            self.unknown(payload, config)
        payload, config = fixture(False, False)
        for project in passes(payload):
            project['reads'].append(dict(field='pending_vtable', address=hx(0), size=8, raw_hex='00'*8))
        self.unknown(payload, config)

    def test_nonnull_optional_requires_owned_diagnostic(self):
        for null_field in (True, False):
            payload, config = fixture()
            for project in passes(payload):
                if null_field:
                    project['fields']['pending_vtable'] = None
                else:
                    project['reads'].pop(-2)
            self.unknown(payload, config)

    def test_world_bytes_reject_boolean_float_and_range(self):
        for field in ('transition_byte', 'retain_previous_byte'):
            for value in (True, False, 0.0, -1, 256):
                payload, config = fixture()
                for project in passes(payload):
                    project['fields'][field] = value
                self.unknown(payload, config)

    def test_attempt_bounds_and_prefilter_boundaries(self):
        for value in (0, -1, 17, True, 1.0):
            payload, config = fixture()
            payload['attempts'] = value
            self.unknown(payload, config)
        for attempt, count in ((1, 4), (1, 6), (16, 19), (16, 81)):
            self.unknown(*fixture(attempts=attempt, prefilter_reads=count))

    def test_category_counts_even_with_consistent_totals(self):
        for category in ('prefix_before', 'prefix_cleanup', 'stack', 'world', 'prefilter'):
            for key in ('reads', 'bytes'):
                payload, config = fixture()
                payload['counters']['categories'][category][key] += 1
                recalculate(payload)
                self.unknown(payload, config)

    def test_counter_totals_short_read_and_strict_scalars(self):
        for key, values in {'reads':(0, 129, 48.0, True),
                            'requested_bytes':(0, 8193, 404.0, True),
                            'exact_bytes':(0, 403, 405, 404.0, True)}.items():
            for value in values:
                payload, config = fixture()
                payload['counters'][key] = value
                self.unknown(payload, config)
        payload, config = fixture()
        payload['counters']['categories']['prefix_before']['reads'] = True
        self.unknown(payload, config)

    def test_budget_contract_exact(self):
        for key, value in {'scope':'some reads', 'max_reads':129, 'max_bytes':8193,
                           'max_message_envelope_bytes':16385, 'stack_window_read':1}.items():
            payload, config = fixture()
            payload['budgets'][key] = value
            self.unknown(payload, config)

    def test_authority_flags_and_zero_fields_are_strict(self):
        for key in ('pure_RPM', 'native_ready', 'native_entry_authenticated',
                    'creation_authenticated_in_script', 'image_sha_verified_in_script',
                    'lifetime_lease', 'atomic_snapshot'):
            for value in (True, 0, 1, None):
                payload, config = fixture()
                payload[key] = value
                self.unknown(payload, config)
        for key in ('field_game_data_writes', 'native_game_calls', 'native_game_objects_constructed'):
            for value in (1, False, 0.0):
                payload, config = fixture()
                payload[key] = value
                self.unknown(payload, config)

    def test_success_needs_all_cleanup_statements_but_never_proves_restore(self):
        for key in fixture()[0]['cleanup']:
            for value in (False, 1, None):
                payload, config = fixture()
                payload['cleanup'][key] = value
                self.unknown(payload, config)
            payload, config = fixture()
            del payload['cleanup'][key]
            self.unknown(payload, config)
        self.assertIs(self.match(*fixture())['code_restore_verified'], False)

    def test_hook_reason_and_status_strict(self):
        for key, value in (('temporary_code_hook', False), ('temporary_code_hook', 1),
                           ('status', 'native_ready'), ('reason', 'some_other_chain')):
            payload, config = fixture()
            payload[key] = value
            self.unknown(payload, config)

    def test_unknown_never_promoted_even_with_valid_projection(self):
        payload, config = fixture()
        payload['status'] = 'unknown'
        payload['reason'] = 'cleanup_not_confirmed'
        result = self.unknown(payload, config)
        self.assertEqual(result['reason'], 'producer_unknown')
        self.assertEqual(result['producer_reason'], 'cleanup_not_confirmed')
        self.assertNotIn('owned_projection_verified', result)

    def test_unknown_setup_failure_null_metadata_and_partial_cleanup(self):
        payload, config = fixture()
        payload.update(status='unknown', reason='invalid_identity_metadata',
                       observer_nonce=None, configured_pid=None, configured_creation=None,
                       module_base=None, attempts=0, observation=None, temporary_code_hook=False)
        payload['cleanup'] = dict(listener_detach_attempted=False, host_cleanup_still_required=True)
        for row in payload['counters']['categories'].values():
            row.update(reads=0, bytes=0)
        recalculate(payload)
        self.assertEqual(self.unknown(payload, config)['reason'], 'producer_unknown')

    def test_unknown_fallback_and_authority_still_closed(self):
        payload, config = fixture()
        payload.update(status='unknown', reason='message_budget_exhausted', observation=None)
        payload['cleanup'] = dict(host_cleanup_still_required=True)
        self.assertEqual(self.unknown(payload, config)['reason'], 'producer_unknown')
        payload['native_ready'] = True
        self.assertEqual(self.unknown(payload, config)['reason'], 'invalid_or_incomplete_evidence')

    def test_message_ascii_depth_node_and_scalar_bounds(self):
        values = ['x'*16385, '\u4e2d', 1 << 100, float('nan'), object(), (1, 2)]
        deep = 0
        for _ in range(12):
            deep = [deep]
        values.extend((deep, [0]*65, [[0]*64 for _ in range(32)]))
        for value in values:
            payload, config = fixture()
            payload['observation'] = value
            self.unknown(payload, config)

    def test_no_mutation_and_json_round_trip(self):
        payload, config = fixture()
        original = copy.deepcopy((payload, config))
        self.match(payload, config)
        self.assertEqual((payload, config), original)
        self.match(json.loads(json.dumps(payload)), json.loads(json.dumps(config)))

    def test_top_level_shape_exact(self):
        for key in fixture()[0]:
            payload, config = fixture()
            del payload[key]
            self.unknown(payload, config)
        payload, config = fixture()
        payload['host_identity_authenticated'] = True
        self.unknown(payload, config)
        for bad in (None, [], 'payload', True):
            self.unknown(bad, config)
            self.unknown(payload, bad)

    def test_wire_bound_counts_real_compact_wrapper_size(self):
        payload, _ = fixture()
        wrapper = json.dumps(dict(type='send', payload=payload), separators=(',', ':'), ensure_ascii=True)
        self.assertEqual(parser.wire_bound(payload, 16384)+len('{"type":"send","payload":}'), len(wrapper))
        self.assertLessEqual(len(wrapper), 16384)


if __name__ == '__main__':
    unittest.main()
