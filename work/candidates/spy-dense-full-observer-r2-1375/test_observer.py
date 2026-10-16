"""Sparse graph integration and mocked held-process failure cleanup only."""
import importlib.util
import copy
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch
import observer as full

SPY, DENSE = full.dependencies()
spec = importlib.util.spec_from_file_location('_fixed_spy_fixture', full.ROOT / 'work/candidates/spy-modifier-observer-1375/test_observer.py')
sys.modules['observer'] = SPY
MOCK = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MOCK)
sys.modules['observer'] = full


def fixture(family='corrupt_officials'):
    f = MOCK.Fixture(family)
    contract = DENSE.report()
    for fact in contract['facts'].values():
        for row in fact['evidence']:
            f.m.put(f.BASE + int(row['rva'], 16), bytes.fromhex(row['bytes']))
    f.m.q(f.BASE + 0x1c427b8, f.BASE + 0x8e6190)
    a = f.ACTOR + 0x28d0
    f.m.i(f.ACTOR + 0x28c8, 2)
    f.m.q(a, f.BASE + 0x1c42770)
    f.m.i(a + 8, 0x165)
    f.m.b(a + 0x10, 1)
    f.m.q(a + 0x50, f.BASE + 0x1c37fa0)
    f.m.i(a + 0x60, 694)
    f.m.i(a + 0x64, 694)
    f.m.put(f.AGG + DENSE.SELECTED * 8, struct.pack('<ii', DENSE.SELECTED, -750))
    return f


class IntegrationTests(unittest.TestCase):
    def test_raw_cross_envelope_substitution_rejected(self):
        # These reproduce the four independent-review counterexamples using
        # actual sparse reads, not replaced observer return dictionaries.
        for which in ('data', 'count', 'transform_root', 'transform'):
            with self.subTest(which=which):
                f = fixture()
                a, other, seen = f.ACTOR + 0x28d0, 0x64000000, 0
                f.m.put(other + DENSE.SELECTED * 8,
                        struct.pack('<ii', DENSE.SELECTED, -900))
                f.m.q(other + 0xe4a0, 0)

                def hook(address, size):
                    nonlocal seen
                    if address != f.ACTOR + 0x28c8:
                        return
                    seen += 1
                    if seen not in (3, 5):
                        return
                    middle = seen == 3
                    if which == 'data':
                        f.m.q(a + 0x58, other if middle else f.AGG)
                    elif which == 'count':
                        f.m.i(a + 0x64, 693 if middle else 694)
                    elif which == 'transform_root':
                        f.m.q(f.BASE + 0x2358080, other if middle else f.TRANSROOT)
                    else:
                        f.m.q(f.TRANSROOT + 0xe4a0, 0x75000000 if middle else 0)

                f.m.hook = hook
                with self.assertRaisesRegex(ValueError, 'Cross-envelope cost field differs'):
                    full.capture(f.m, f.BASE)

    def test_unsupported_branches_only_bind_observed_fields(self):
        changes = {
            'cache_zero': lambda f: f.m.i(f.ACTOR + 0x28c8, 0),
            'cache_lazy': lambda f: f.m.i(f.ACTOR + 0x28c8, 1),
            'cache_unknown': lambda f: f.m.i(f.ACTOR + 0x28c8, -1),
            'root_null': lambda f: f.m.q(f.BASE + 0x2358080, 0),
            'transform': lambda f: f.m.q(f.TRANSROOT + 0xe4a0, 0x75000000),
            'aggregate_vtable': lambda f: f.m.q(f.ACTOR + 0x28d0, f.BASE + 0x1c48000),
            'marker': lambda f: f.m.i(f.ACTOR + 0x28d0 + 8, 0),
            'vector_vtable': lambda f: f.m.q(f.ACTOR + 0x28d0 + 0x50, f.BASE + 0x1c48000),
            'empty_vector': lambda f: f.m.i(f.ACTOR + 0x28d0 + 0x64, 0),
            'capacity': lambda f: f.m.i(f.ACTOR + 0x28d0 + 0x60, 693),
            'selected_id': lambda f: f.m.put(f.AGG + DENSE.SELECTED * 8, struct.pack('<ii', 123, -750)),
        }
        for name, change in changes.items():
            with self.subTest(branch=name):
                f = fixture()
                change(f)
                x = full.capture(f.m, f.BASE)
                self.assertIsNone(x['dense']['final_milli_candidate'])
                fields = x['cost_binding']['observed_common_fields']
                self.assertEqual(fields[:2], ['base_milli', 'cache_state'])
                if name.startswith('cache_'):
                    self.assertEqual(len(fields), 2)
                elif name == 'root_null':
                    self.assertEqual(len(fields), 3)
                elif name == 'transform':
                    self.assertEqual(len(fields), 4)
                self.assertFalse(x['actual_cost_verified'])
                self.assertFalse(x['cost_binding']['same_address_value_aba_excluded'])

    def test_binding_strict_scalar_types_and_missing_full_aggregate(self):
        x = full.capture(fixture().m, MOCK.Fixture.BASE)
        old = x['before']['snapshot']['cost']
        local = x['dense']['before']
        for key in ('base_milli', 'cache_state', 'transform_root', 'transform'):
            for convert in (bool, float):
                with self.subTest(key=key, convert=convert):
                    bad = copy.deepcopy(local)
                    bad[key] = convert(bad[key])
                    with self.assertRaises(ValueError):
                        full.bind_cost(old, bad)
        for key in ('address', 'dense', 'data', 'count'):
            for convert in (bool, float):
                with self.subTest(key=key, convert=convert):
                    bad = copy.deepcopy(local)
                    bad['aggregate'][key] = convert(bad['aggregate'][key])
                    with self.assertRaises(ValueError):
                        full.bind_cost(old, bad)
        bad = copy.deepcopy(old)
        bad['aggregate'] = None
        with self.assertRaises(ValueError):
            full.bind_cost(bad, local)

    def test_five_raw_graphs_preserve_unsupported_old_cost_and_new_projection(self):
        for family in SPY.contract()['families']:
            with self.subTest(family=family):
                f = fixture(family)
                result = full.capture(f.m, f.BASE, family=family)
                self.assertTrue(result['full_envelope_equal'])
                self.assertEqual(result['before']['snapshot']['cost']['status'], 'unsupported_dense_storage')
                self.assertIsNone(result['before']['snapshot']['cost']['final_milli_candidate'])
                self.assertEqual(result['dense']['final_milli_candidate'], 6250)
                self.assertFalse(result['actual_cost_verified'])
                self.assertFalse(result['production_ready'])

    def test_kernel_equal_but_changed_full_world_or_network_is_rejected(self):
        for which in ('date', 'network'):
            with self.subTest(which=which):
                f = fixture()
                seen = 0

                def hook(address, size):
                    nonlocal seen
                    if address == f.ACTOR + 0x28d0 + 0x50:
                        seen += 1
                        if seen == 2:
                            if which == 'date':
                                f.m.i(f.GAME + 0x1dd0, 56456977)
                            else:
                                f.m.put(f.record + 0x18, struct.pack('<h', 9999))

                f.m.hook = hook
                with self.assertRaises(ValueError):
                    full.capture(f.m, f.BASE)

    def test_shared_budget_and_exact_reader_type(self):
        class Reader:
            def read(self, address, size):
                return bytearray(size)

        budget = full.BudgetReader(Reader())
        with self.assertRaises(ValueError):
            budget.read(0x20000000, 4)
        for bytes_used, calls in ((full.MAX_BYTES, 0), (0, full.MAX_CALLS)):
            budget.bytes, budget.calls = bytes_used, calls
            with self.assertRaises(ValueError):
                budget.read(0x20000000, 4)

    def test_process_failures_close_mock_handle(self):
        sys.path.insert(0, str(full.ROOT))
        from work import probe_diplomacy_current as legacy
        c = SPY.contract()
        signature = dict(timestamp=c['pe']['timestamp'], size=c['pe']['image_size'])
        real_sha = full.sha
        exe = full.ROOT.parent / 'eu4.exe'

        class Reader:
            base, bytes_read = MOCK.Fixture.BASE, 0
            closed = False

            def close(self):
                self.closed = True

        for first_fails in (True, False):
            reader = Reader()
            held = ValueError('held mismatch') if first_fails else [dict(pid=123), dict(pid=124)]
            with patch.object(full, 'dependencies', return_value=(SPY, DENSE)), \
                 patch.object(full, 'sha', side_effect=lambda p: SPY.EXE_SHA if Path(p).resolve() == exe.resolve() else real_sha(p)), \
                 patch.object(legacy, 'verified_executable', return_value=(None, signature)), \
                 patch.object(legacy, 'ProcessReader', return_value=reader), \
                 patch.object(SPY, 'held_identity', side_effect=held), \
                 patch.object(full, 'capture', return_value=dict(profile='mock')):
                with self.assertRaises(ValueError):
                    full.sample_process(pid=123, creation='0000000000000001', executable=exe)
            self.assertTrue(reader.closed)


if __name__ == '__main__':
    unittest.main()
