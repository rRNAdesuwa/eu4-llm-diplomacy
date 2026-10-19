import copy
import json
import unittest
from model import (ContractError, GPRS, SITES, STAGES, FAULTS, MAX_PACKET,
                   validate, decode_packet, compare_recorder, correlate_return,
                   exception_requirement)


def sample(site='entry', avx=False):
    base = 0x140000000
    g = {name: (i + 1) * 0x1010101010101 for i, name in enumerate(GPRS)}
    g['rsp'] = 0x700008 if site == 'entry' else 0x700010
    stack = (base + SITES['continuation']).to_bytes(8, 'little') + bytes(range(56))
    return {'schema': 'synthetic_c02_state_v1', 'site': site, 'module_base': base,
            'thread': 7, 'span': 2, 'parent': 1, 'generation': 1,
            'rip': base + SITES[site], 'gpr': g, 'rflags': 0x202, 'stack_top': stack.hex(),
            'xstate': {'profile': 'synthetic_avx' if avx else 'synthetic_legacy_sse',
                       'enabled': ['x87', 'sse'] + (['avx_upper'] if avx else []),
                       'x87': {'control': 0x37f, 'status': 0, 'tag': 0xffff, 'opcode': 0,
                               'ip': 0, 'dp': 0, 'st': [bytes([i] * 10).hex() for i in range(8)]},
                       'sse': {'mxcsr': 0x1f80, 'xmm': [bytes([i] * 16).hex() for i in range(16)]},
                       'avx_upper': [bytes([i + 16] * 16).hex() for i in range(16)] if avx else None},
            'thread_observables': {'last_error': 123, 'errno': -1}}


def scalar_paths(v, path=()):
    if type(v) is dict:
        for k, child in v.items():
            yield from scalar_paths(child, path + (k,))
    elif type(v) is list:
        for k, child in enumerate(v):
            yield from scalar_paths(child, path + (k,))
    elif type(v) is int:
        yield path, v


def set_path(v, path, value):
    for k in path[:-1]:
        v = v[k]
    v[path[-1]] = value


class ModelTests(unittest.TestCase):
    def test_two_synthetic_profiles_never_authorize(self):
        for site in SITES:
            for avx in (False, True):
                v = sample(site, avx)
                out = compare_recorder(v, decode_packet(json.dumps(v).encode('ascii')))
                self.assertTrue(out['synthetic_modeled_equality'])
                self.assertFalse(out['hook_supported'])
                self.assertFalse(out['machine_capture_verified'])
                self.assertFalse(out['native_execution_authorized'])

    def test_all_integer_aliases_rejected(self):
        v = sample(avx=True)
        for path, value in scalar_paths(v):
            for alias in (bool(value), float(value)):
                with self.subTest(path=path, alias=alias), self.assertRaises(ContractError):
                    altered = copy.deepcopy(v)
                    set_path(altered, path, alias)
                    validate(altered)

    def test_every_gpr_even_volatile_must_survive_recorder(self):
        for name in GPRS:
            with self.subTest(name=name), self.assertRaises(ContractError):
                v = sample(); after = copy.deepcopy(v)
                after['gpr'][name] ^= 0x100
                compare_recorder(v, after)

    def test_all_flags_and_mxcsr_bits_compared_without_claiming_restorability(self):
        for field, width in (('rflags', 64), ('mxcsr', 32)):
            for bit in range(width):
                with self.subTest(field=field, bit=bit), self.assertRaises(ContractError):
                    v = sample(); after = copy.deepcopy(v)
                    if field == 'rflags': after[field] ^= 1 << bit
                    else: after['xstate']['sse'][field] ^= 1 << bit
                    compare_recorder(v, after)

    def test_xmm_and_upper_halves_all_registers(self):
        for group in ('xmm', 'avx_upper'):
            for index in range(16):
                with self.subTest(group=group, index=index), self.assertRaises(ContractError):
                    v = sample(avx=True); after = copy.deepcopy(v)
                    values = after['xstate']['sse']['xmm'] if group == 'xmm' else after['xstate']['avx_upper']
                    values[index] = 'ff' * 16
                    compare_recorder(v, after)

    def test_x87_and_thread_observables_preserved(self):
        for path, value in [(('xstate', 'x87', 'control'), 0), (('xstate', 'x87', 'status'), 1),
                            (('xstate', 'x87', 'tag'), 0), (('xstate', 'x87', 'opcode'), 1),
                            (('xstate', 'x87', 'ip'), 1), (('xstate', 'x87', 'dp'), 1),
                            (('thread_observables', 'last_error'), 0), (('thread_observables', 'errno'), 0)]:
            with self.subTest(path=path), self.assertRaises(ContractError):
                v = sample(); after = copy.deepcopy(v); set_path(after, path, value)
                compare_recorder(v, after)
        for index in range(8):
            with self.subTest(index=index), self.assertRaises(ContractError):
                v = sample(); after = copy.deepcopy(v); after['xstate']['x87']['st'][index] = 'ff' * 10
                compare_recorder(v, after)

    def test_stack_return_and_home_area_canaries(self):
        for index in range(64):
            with self.subTest(index=index), self.assertRaises(ContractError):
                v = sample(); after = copy.deepcopy(v)
                raw = bytearray.fromhex(after['stack_top']); raw[index] ^= 1
                after['stack_top'] = raw.hex(); compare_recorder(v, after)

    def test_unknown_missing_or_torn_extended_state(self):
        mutations = [('profile', 'actual_host'), ('enabled', ['x87', 'sse', 'avx512']),
                     ('enabled', ['sse']), ('enabled', ['x87', 'sse', 'sse']), ('avx_upper', [])]
        for k, val in mutations:
            with self.subTest(k=k, val=val), self.assertRaises(ContractError):
                v = sample(); v['xstate'][k] = val; validate(v)
        for field in ('xmm',):
            v = sample(); v['xstate']['sse'][field][0] = '00' * 15
            with self.assertRaises(ContractError): validate(v)

    def test_missing_extra_duplicate_and_oversize_packets(self):
        v = sample()
        for k in v:
            bad = copy.deepcopy(v); del bad[k]
            with self.subTest(k=k), self.assertRaises(ContractError): validate(bad)
        for path in ((), ('gpr',), ('xstate',), ('xstate', 'x87'), ('thread_observables',)):
            bad = copy.deepcopy(v); obj = bad
            for k in path: obj = obj[k]
            obj['unexpected'] = 0
            with self.subTest(path=path), self.assertRaises(ContractError): validate(bad)
        for raw in (b'{"x":1,"x":1}', b' ' * (MAX_PACKET + 1), b'NaN', b'[]', b'\xff'):
            with self.assertRaises(ContractError): decode_packet(raw)

    def test_pair_only_known_normal_return_constraints(self):
        entry, ret = sample(), sample('continuation')
        ret['gpr']['rax'] = entry['gpr']['rcx']
        # The native function may alter volatile registers/flags; don't confuse that with recorder loss.
        ret['gpr']['rdx'] = 0; ret['rflags'] = 0x246
        self.assertTrue(correlate_return(entry, ret)['synthetic_normal_return_correlated'])
        for path, value in [(('thread',), 8), (('span',), 3), (('parent',), 0), (('generation',), 2),
                            (('gpr', 'rax'), 0), (('gpr', 'rsp'), 0x700020)]:
            with self.subTest(path=path), self.assertRaises(ContractError):
                bad = copy.deepcopy(ret); set_path(bad, path, value); correlate_return(entry, bad)
        with self.assertRaises(ContractError): compare_recorder(entry, ret)

    def test_original_prefix_effects_are_not_same_pc_transparency(self):
        entry = sample(); after = copy.deepcopy(entry)
        after['gpr']['rsp'] -= 0x28; after['rip'] += 15
        with self.assertRaises(ContractError): compare_recorder(entry, after)

    def test_exceptions_never_provide_automatic_resume_or_cleanup(self):
        for stage in STAGES:
            for fault in FAULTS:
                result = exception_requirement(stage, fault)
                self.assertTrue(result['required_terminal_revocation'])
                self.assertFalse(result['automatic_recovery_allowed'])
                self.assertFalse(result['engine_cleanup_by_observer_allowed'])
                self.assertFalse(result['normal_return_event_allowed'])
                self.assertFalse(result['installed_exception_policy_verified'])
                self.assertEqual(result['original_engine_exception_must_propagate'], fault == 'engine_exception')
        for stage, fault in ((False, 'ring_loss'), ('entry_save', 1), ('new_stage', 'ring_loss')):
            with self.assertRaises(ContractError): exception_requirement(stage, fault)


if __name__ == '__main__':
    unittest.main()
