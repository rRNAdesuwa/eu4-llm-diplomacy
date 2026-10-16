"""New offline-only cases; no native/game/Frida operation or old suite imports."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import war_peace_lookup as lookup


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


class Fixture:
    def __init__(self, root, index):
        self.root = Path(root)
        self.directory = self.root / 'candidate'
        self.directory.mkdir()
        self.relative = 'work/reports/synthetic-evidence.json'
        self.source = self.root / self.relative
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(encoded({'fixture': {'not_runtime_evidence': True}}))
        self.index = copy.deepcopy(index)
        self.index['entries'] = [row for row in self.index['entries'] if row['id'] in
                                 ('declare_war.constructor', 'declare_war.body_destructor')]
        for row in self.index['entries']:
            row['evidence'] = [{'path': self.relative, 'json_pointer': '/fixture', **pin(self.source.read_bytes())}]
        self.write()

    def write(self):
        raw = encoded(self.index)
        (self.directory / 'index.json').write_bytes(raw)
        manifest = {'schema': 'EU4-WAR-PEACE-LOOKUP-DATA-MANIFEST/1', 'version': '1.37.5',
                    'game_sha256': lookup.GAME_SHA256, 'scope': 'offline_selected_evidence_only',
                    'index': pin(raw), 'sources': {self.relative: pin(self.source.read_bytes())}}
        manifest_raw = encoded(manifest)
        (self.directory / 'data-manifest.json').write_bytes(manifest_raw)
        self.graph = lookup.SourceGraph(self.root, self.directory, pin(manifest_raw)['sha256'])


class LookupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index, cls.provenance = lookup.SourceGraph().verify(parse=True)

    def assert_unknown(self, result):
        value, code = result
        self.assertEqual(code, 2)
        self.assertEqual(value['status'], 'unknown')
        self.assertEqual(value['entries'], [])
        self.assertNotIn('conditional_address', value)
        for flag in lookup.FALSE_FLAGS:
            self.assertIs(value[flag], False)
        return value

    def test_catalog_families_and_exact_counts(self):
        value, code = lookup.query(lookup.SourceGraph(), 'catalog')
        self.assertEqual(code, 0)
        self.assertEqual(value['count'], 43)
        self.assertEqual(value['provenance']['selected_source_count'], 19)
        self.assertTrue(value['provenance']['source_guard_before_and_after'])
        self.assertEqual([row['id'] for row in value['entries']], sorted(row['id'] for row in value['entries']))
        peace, _ = lookup.query(lookup.SourceGraph(), 'catalog', family='议和')
        self.assertTrue(all('peace' in row['actions'] for row in peace['entries']))

    def test_alias_rva_and_family_lookup(self):
        for name in ('declare_war.constructor', 'DECLAREWAR_CTOR', '宣战构造', '0x00500480'):
            with self.subTest(name=name):
                result, code = lookup.query(lookup.SourceGraph(), 'lookup', selector=name)
                self.assertEqual(code, 0)
                self.assertEqual([r['id'] for r in result['entries']], ['declare_war.constructor'])
        result, code = lookup.query(lookup.SourceGraph(), 'lookup', selector='requestpeace')
        self.assertEqual(code, 0)
        self.assertTrue(all('peace' in r['actions'] for r in result['entries']))

    def test_search_deterministic_and_bounded(self):
        first = lookup.query(lookup.SourceGraph(), 'search', selector='command', limit=3)
        second = lookup.query(lookup.SourceGraph(), 'search', selector='command', limit=3)
        self.assertEqual(first, second)
        self.assertEqual(first[1], 0)
        self.assertEqual(first[0]['count'], 3)
        self.assertGreater(first[0]['total_matches'], 3)
        empty, code = lookup.query(lookup.SourceGraph(), 'search', selector='no_such_endpoint_zz')
        self.assertEqual((code, empty['count']), (0, 0))
        self.assertIs(empty['native_ready'], False)

    def test_exact_uint32_rva_boundaries(self):
        self.assertEqual(lookup.parse_rva('0x0'), 0)
        self.assertEqual(lookup.parse_rva('0xffffffff'), (1 << 32) - 1)
        for value in (True, 0x500480, '500480', '-0x1', '0x100000000', '0x', ' 0x1', '0x1\n'):
            with self.subTest(value=value), self.assertRaises(lookup.LookupFailure):
                lookup.parse_rva(value)

    def test_conditional_base_has_no_authentication(self):
        address = lookup.conditional_va('0x140000000', '0x500480')
        self.assertEqual(address['va'], '0x0000000140500480')
        self.assertEqual(address['meaning'], 'conditional_arithmetic_from_user_supplied_base')
        self.assertIs(address['callable'], False)
        self.assertIs(address['process_authenticated'], False)
        self.assertEqual(lookup.conditional_va('0x10000', '0x0')['va'], '0x0000000000010000')
        self.assertEqual(lookup.conditional_va('0x7ffffffef000', '0xfff')['va'], '0x00007ffffffeffff')
        for base, rva in [(True, '0x0'), ('0x0', '0x0'), ('0xffff', '0x0'), ('0x140000001', '0x0'),
                          ('0x7fffffff0000', '0x0'), ('0x7ffffffef000', '0x1000'),
                          ('0xffffffffffffffff', '0xffffffff'), ('-0x140000000', '0x0')]:
            with self.subTest(base=base, rva=rva), self.assertRaises(lookup.LookupFailure):
                lookup.conditional_va(base, rva)

    def test_unknown_and_unsafe_never_release_addresses(self):
        for selector, base in [('0xffffffff', '0x140000000'), ('0x500481', '0x140000000'),
                               ('500560', None), ('declare_war.constructor', '0xffffffffffffffff')]:
            with self.subTest(selector=selector, base=base):
                self.assert_unknown(lookup.query(lookup.SourceGraph(), 'lookup', selector=selector, base=base))

    def test_scope_separates_rawbody_and_callsites(self):
        real = [r for r in self.index['entries'] if r['stage'] == 'real_rawbody_postcondition']
        self.assertEqual([r['id'] for r in real], ['declare_war.body_destructor'])
        self.assertEqual(real[0]['signature']['status'], 'raw_probe_only')
        self.assertIn('不是合法C++对象', real[0]['unresolved'][0])
        for row in self.index['entries']:
            self.assertTrue(all(row[flag] is False for flag in lookup.FALSE_FLAGS))
        commit = next(r for r in self.index['entries'] if r['id'] == 'declare_war.commit_site')
        self.assertEqual(commit['kind'], 'callsite')
        self.assertEqual(commit['signature']['status'], 'unknown')
        for row in self.index['entries']:
            if row['id'] in ('peace.local_check', 'peace.full_check', 'peace.date_check'):
                self.assertTrue(any(ref['json_pointer'] == '/country_root/alias_arithmetic' for ref in row['evidence']))

    def test_manifest_pin_precedes_json_parse(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(directory, self.index)
            (fixture.directory / 'data-manifest.json').write_bytes(b'not json')
            with mock.patch.object(lookup, '_json', side_effect=AssertionError('must not parse')):
                value = self.assert_unknown(lookup.query(fixture.graph, 'check'))
            self.assertEqual(value['reason'], 'data_manifest_pin_mismatch')

    def test_index_and_source_pin_fail_closed(self):
        for target in ('index', 'source'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                fixture = Fixture(directory, self.index)
                path = fixture.directory / 'index.json' if target == 'index' else fixture.source
                path.write_bytes(b'broken data')
                value = self.assert_unknown(lookup.query(fixture.graph, 'lookup', selector='war_ctor', base='0x140000000'))
                self.assertEqual(value['reason'], 'source_pin_mismatch')

    def test_second_guard_discards_prepared_result(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(directory, self.index)
            verify = fixture.graph.verify
            def changed(*, parse=False):
                if not parse:
                    fixture.source.write_bytes(b'changed after first verified query')
                return verify(parse=parse)
            with mock.patch.object(fixture.graph, 'verify', side_effect=changed):
                value = self.assert_unknown(lookup.query(fixture.graph, 'lookup', selector='war_ctor', base='0x140000000'))
            self.assertEqual(value['reason'], 'source_pin_mismatch')

    def test_even_repinned_fixture_cannot_promote_authority_or_stage(self):
        for mutation in ('flag', 'stage'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                fixture = Fixture(directory, self.index)
                row = next(r for r in fixture.index['entries'] if r['id'] == 'declare_war.constructor')
                if mutation == 'flag':
                    row['native_ready'] = True
                else:
                    row['stage'] = 'real_rawbody_postcondition'
                fixture.write()
                self.assert_unknown(lookup.query(fixture.graph, 'check'))

    def test_path_and_evidence_pointer_boundaries(self):
        for relative in ('../escape.json', 'C:/escape.json', 'work/reports/../escape.json',
                         'work\\reports\\escape.json', 'work/reports//escape.json'):
            with self.subTest(relative=relative), self.assertRaises(lookup.LookupFailure):
                lookup._source_path(lookup.ROOT, relative)
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(directory, self.index)
            fixture.index['entries'][0]['evidence'][0]['json_pointer'] = '/absent'
            fixture.write()
            self.assert_unknown(lookup.query(fixture.graph, 'check'))

    def test_cli_check_and_absence_of_execution_commands(self):
        for arguments, expected in [(['check'], 0), (['execute', '0x500560'], 2),
                                    (['lookup', 'war_ctor', '--pid', '80340'], 2)]:
            with self.subTest(arguments=arguments):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = lookup.main(arguments)
                value = json.loads(output.getvalue())
                self.assertEqual(code, expected)
                self.assertIs(value['callable'], False)
                self.assertEqual(value['requests_published'], 0)
                self.assertEqual(value['native_calls'], 0)
                if code == 0:
                    self.assertEqual(value['stage_counts'], {'static': 42, 'real_rawbody_postcondition': 1})


if __name__ == '__main__':
    unittest.main(verbosity=2)
