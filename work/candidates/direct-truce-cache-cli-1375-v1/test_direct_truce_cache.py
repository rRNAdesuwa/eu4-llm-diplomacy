"""New CLI adapter tests only: owned byte fixtures/mocks, no target process."""
import ast
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import direct_truce_cache as cli
ROOT = cli.ROOT
R24_PIN = cli.pin(ROOT / cli.R24)
assert R24_PIN['sha256'] == cli.FIXED[cli.R24]
R24 = cli.exact_compile(cli.R24, R24_PIN)


def selected_observer_functions():
    path = ROOT / 'bridge/diplomacy_effect_observer.py'
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == '9eafecba34e74a6bf1cc3d081b9ce4dee10395cf6bae7da233f915328ec876d1'
    names = {'ptr', 'full_handle', 'BudgetReader', 'country', 'relation'}
    tree = ast.parse(raw, str(path))
    definitions = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names]
    assert {node.name for node in definitions} == names
    namespace = dict(struct=struct, re=re, require=cli.require, COUNTRY_VT=0x1c574a0,
                     LIMITS=dict(calls=4096, bytes=512*1024, single_read=65536, index_entries=256))
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


FUNCTIONS = selected_observer_functions()
BASE, TABLE, ACTOR, TARGET, ALIAS = 0x140000000, 0x30000, 0x40000, 0x50000, 0x80000
AH = (1 << 56) | (8 << 32) | int.from_bytes(b'FRA', 'little')
TH = (1 << 56) | (19 << 32) | int.from_bytes(b'AUV', 'little')
CHOSEN = dict(pid=12345, creation='0000000000000001', actor='FRA', target='AUV')


class Memory:
    def __init__(self, state=False, alias=False):
        self.blocks, self.alias, self.reads = {}, alias, 0
        table = bytearray(1380*8)
        struct.pack_into('<Q', table, 8*8, ACTOR)
        struct.pack_into('<Q', table, 19*8, TARGET)
        self.table = bytes(table)
        self.blocks[TABLE] = self.table
        for address, handle in ((ACTOR, AH), (TARGET, TH), (ALIAS, AH)):
            header = bytearray(0x28)
            struct.pack_into('<QI', header, 0, BASE+0x1c574a0, 357)
            struct.pack_into('<Q', header, 0x20, handle)
            self.blocks[address] = bytes(header)
            relation = bytearray(0x30)
            vector = address + 0x3000
            struct.pack_into('<QI', relation, 0, BASE+0x1c4f5f8, 357)
            struct.pack_into('<QQQQ', relation, 0x10, address, vector, vector+20*0x48, vector+20*0x48)
            self.blocks[address+0x14f8] = bytes(relation)
            row = bytearray(0x48)
            other = TH if handle == AH else AH
            slot = 19 if handle == AH else 8
            struct.pack_into('<QQQ', row, 0, address+0x14f8, handle, other)
            row[0x45] = 1 if state else 0
            self.blocks[vector+slot*0x48] = bytes(row)

    def read(self, address, size):
        self.reads += 1
        if self.alias and address == TABLE + 8*8 and size == 8:
            return struct.pack('<Q', ALIAS)
        for begin, raw in self.blocks.items():
            if begin <= address and address+size <= begin+len(raw):
                return raw[address-begin:address-begin+size]
        raise ValueError('Owned fixture span not present')


class FakeLibraries:
    def __init__(self, state=False, alias=False, fail_guard=0, close_error=False, paused=True, research=False):
        self.memory = Memory(state, alias)
        self.guards = self.enters = self.closes = self.observer_loads = 0
        self.fail_guard, self.close_error = fail_guard, close_error
        self.root = dict(array=hex(TABLE), count=1380, manual_pause=int(paused), date=123)
        self.r24 = R24
        owner = self
        class Runtime:
            def __init__(self, identity, backend):
                owner.selected_identity = copy.deepcopy(identity)
                self.base, self.initial_pins = BASE, {'synthetic': True}
                self.held = types.SimpleNamespace(handle=123, injector=types.SimpleNamespace(GAME=cli.GAME))
                self.modules = [(BASE, str(cli.GAME))]
                if research:
                    self.modules.append((0x90000, 'eu4_tag_command_test.dll'))
            def __enter__(self):
                owner.enters += 1
                return self
            def __exit__(self, *_):
                owner.closes += 1
                self.held.handle = None
                if owner.close_error:
                    raise ValueError('Synthetic context cleanup failure')
        backend = types.SimpleNamespace(manifest={'dll': {'sha256': 'a'*64}}, manifest_sha='b'*64)
        self.module = types.SimpleNamespace(**{name: FUNCTIONS[name] for name in
            ('ptr', 'full_handle', 'BudgetReader', 'country', 'relation')}, COUNTRY_VT=0x1c574a0,
            roots=lambda *_: copy.deepcopy(self.root), HeldRPMPort=lambda _: self.memory,
            pins=lambda: {'synthetic': True}, RuntimeCapture=Runtime, TagCommandBackend=lambda: backend)
        self.host = types.SimpleNamespace(host_sample=lambda *_: {'roots': copy.deepcopy(self.root), 'synthetic': True})
    def guard(self):
        self.guards += 1
        if self.guards == self.fail_guard:
            raise ValueError('Synthetic source changed')
    def observer(self):
        self.observer_loads += 1
        self.guard()
        return self.module
    def evidence(self):
        return {'synthetic': True, 'old_fixed_pid_authority_reused': False}


@contextlib.contextmanager
def temporary_source_graph(sealed=True):
    with tempfile.TemporaryDirectory(prefix='direct-truce-source-test-') as directory:
        root = Path(directory)
        (root/'static').mkdir()
        for name in ('cli.py', 'r24.py', 'host.py'):
            (root/name).write_text('raise AssertionError("must not compile")\n', encoding='ascii')
        (root/'static/a.txt').write_text('retained source', encoding='ascii')
        static = dict(sealed=True, game_sha256=cli.GAME_SHA, files={'a.txt': cli.pin(root/'static/a.txt')}, sources={})
        (root/'static/manifest.json').write_text(json.dumps(static), encoding='ascii')
        fixed = {name: cli.pin(root/name)['sha256'] for name in ('r24.py', 'host.py', 'static/manifest.json')}
        pins = {name: cli.pin(root/name) for name in ('cli.py', *fixed)}
        path = root/'manifest.json'
        path.write_text(json.dumps(dict(schema='EU4-DIRECT-TRUCE-CACHE-CLI-SOURCE-MANIFEST/1',
            sealed=sealed, game_sha256=cli.GAME_SHA, source_pins=pins)), encoding='ascii')
        with patch.multiple(cli, ROOT=root, R23='static/', REQUIRED={'cli.py'}, FIXED=fixed):
            yield root, path


class DirectTruceCLITests(unittest.TestCase):
    def test_selection_strict_parameters_before_library_loading(self):
        self.assertEqual(cli.selection(**CHOSEN), CHOSEN)
        values = [('pid', True), ('pid', 0), ('pid', -1), ('pid', 1<<32), ('pid', '12345'),
                  ('creation', '0'*16), ('creation', 'A'*16), ('creation', '1'*15), ('creation', 1),
                  ('actor', 'fra'), ('target', 'AU'), ('actor', 'FRA\x00'), ('target', 'FRA')]
        for key, value in values:
            with self.subTest(key=key, value=value):
                selected = {**CHOSEN, key: value}
                with patch.object(cli, 'Libraries', side_effect=AssertionError('must not load')):
                    result = cli.run('status', selected, library_factory=lambda: self.fail('library called'))
                self.assertEqual(cli.result_code(result), 2)
                self.assertIsNone(result['direct_pair_cache_flag_set'])

    def test_positive_table_slot_mapping_is_required(self):
        lib = FakeLibraries()
        r = lib.module.BudgetReader(R24.AlignedPort(lib.memory))
        self.assertEqual(cli.selected_handles(r, lib.module, lib.root, lib.memory.table, 'FRA', 'AUV'), {'FRA': AH, 'AUV': TH})
        for wrong_slot in (0, 7):
            table = bytearray(lib.memory.table)
            struct.pack_into('<Q', table, 8*8, 0)
            struct.pack_into('<Q', table, wrong_slot*8, ACTOR)
            with self.subTest(slot=wrong_slot), self.assertRaisesRegex(ValueError, 'slot disagree'):
                cli.selected_handles(r, lib.module, lib.root, bytes(table), 'FRA', 'AUV')

    def test_true_and_false_are_observations_not_effect_success(self):
        for state in (False, True):
            with self.subTest(state=state):
                lib = FakeLibraries(state=state)
                result = cli.run('status', CHOSEN, library_factory=lambda: lib)
                self.assertEqual(cli.result_code(result), 0, result['errors'])
                self.assertIs(result['direct_pair_cache_flag_set'], state)
                self.assertEqual(result['direction'], 'FRA->AUV')
                self.assertEqual((lib.enters, lib.closes), (1, 1))
                self.assertEqual(lib.selected_identity['pid'], CHOSEN['pid'])
                self.assertEqual(lib.selected_identity['creation'], CHOSEN['creation'])
                self.assertNotEqual(lib.selected_identity['pid'], 80340)
                self.assertRegex(lib.selected_identity['session'], '^[0-9a-f]{32}$')
                for key in ('selected_effect_verified', 'peace_completion_verified', 'request_effect_verified', 'native_ready'):
                    self.assertIs(result[key], False)
                self.assertEqual(result['requests_published'], 0)

    def test_adopted_r24_table_a_to_b_guard_rejects_equal_two_pass_alias(self):
        lib = FakeLibraries(state=True, alias=True)
        result = cli.run('status', CHOSEN, library_factory=lambda: lib)
        self.assertEqual(len(result['samples']), 2)
        self.assertEqual(result['samples'][0], result['samples'][1])
        self.assertEqual(result['samples'][0]['directional_pairs'][0]['actor']['address'], hex(ALIAS))
        self.assertIn('table and sampled address differ', result['errors'][0]['message'])
        self.assertEqual(cli.result_code(result), 2)
        self.assertIsNone(result['direct_pair_cache_flag_set'])
        self.assertEqual(lib.closes, 1)

    def test_source_change_rejected_before_any_library_compilation(self):
        with temporary_source_graph() as (root, path):
            cli.verify_sources(path)
            (root/'static/a.txt').write_text('changed source', encoding='ascii')
            original = cli.verify_sources
            with patch.object(cli, 'verify_sources', side_effect=lambda: original(path)), \
                 patch.object(cli, 'exact_compile', side_effect=AssertionError('must not compile')) as compile_mock:
                with self.assertRaisesRegex(ValueError, 'Selected source changed'):
                    cli.Libraries()
                compile_mock.assert_not_called()

    def test_unsealed_manifest_rejected_before_library_compilation(self):
        with temporary_source_graph(sealed=False) as (_, path):
            original = cli.verify_sources
            with patch.object(cli, 'verify_sources', side_effect=lambda: original(path)), \
                 patch.object(cli, 'exact_compile', side_effect=AssertionError('must not compile')) as compile_mock:
                with self.assertRaisesRegex(ValueError, 'sealed source manifest required'):
                    cli.Libraries()
                compile_mock.assert_not_called()

    def test_source_guard_change_before_open_and_after_passes_prevents_commit(self):
        for point in (2, 3, 4):
            with self.subTest(guard=point):
                lib = FakeLibraries(state=True, fail_guard=point)
                result = cli.run('status', CHOSEN, library_factory=lambda: lib)
                self.assertEqual(cli.result_code(result), 2)
                self.assertIsNone(result['direct_pair_cache_flag_set'])
                self.assertIs(result['commit_after_context_exit'], False)
                self.assertEqual(lib.enters, 0 if point == 2 else 1)
                self.assertEqual(lib.enters, lib.closes)

    def test_context_cleanup_exception_cannot_commit_a_good_sample(self):
        lib = FakeLibraries(state=True, close_error=True)
        result = cli.run('status', CHOSEN, library_factory=lambda: lib)
        self.assertIs(result['selected_two_pass_equal'], True)
        self.assertIs(result['normal_context_exit'], False)
        self.assertIs(result['commit_after_context_exit'], False)
        self.assertIsNone(result['direct_pair_cache_flag_set'])
        self.assertEqual(cli.result_code(result), 2)

    def test_paused_guard_and_research_module_refusal_precede_selected_reads(self):
        for options in ({'paused': False}, {'research': True}):
            with self.subTest(options=options):
                lib = FakeLibraries(**options)
                result = cli.run('status', CHOSEN, library_factory=lambda: lib)
                self.assertEqual(cli.result_code(result), 2)
                self.assertEqual(lib.memory.reads, 0)
                self.assertEqual((lib.enters, lib.closes), (1, 1))

    def test_catalog_and_check_do_not_load_observer_or_open_process(self):
        for operation in ('catalog', 'check'):
            with self.subTest(operation=operation):
                lib = FakeLibraries()
                result = cli.run(operation, library_factory=lambda: lib)
                self.assertEqual(cli.result_code(result), 0)
                self.assertEqual((lib.observer_loads, lib.enters, lib.memory.reads), (0, 0, 0))
                self.assertIsNone(result['direct_pair_cache_flag_set'])
                self.assertIs(result['selected_effect_verified'], False)

    def test_exit_zero_requires_strict_boolean_and_postcommit_flags(self):
        result = cli.run('status', CHOSEN, library_factory=FakeLibraries)
        self.assertEqual(cli.result_code(result), 0)
        for value in (0, 1, None, 'false'):
            self.assertEqual(cli.result_code({**result, 'direct_pair_cache_flag_set': value}), 2)
        for key in ('selected_two_pass_equal', 'normal_context_exit', 'held_handle_cleared', 'commit_after_context_exit'):
            self.assertEqual(cli.result_code({**result, key: 1}), 2)
        self.assertEqual(cli.result_code({**result, 'status': 'unknown'}), 2)

    def test_cli_missing_identity_is_json_unknown_without_runtime(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli.main(['status', '--actor', 'FRA', '--target', 'AUV'])
        result = json.loads(output.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(result['status'], 'unknown')
        self.assertIsNone(result['direct_pair_cache_flag_set'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
