"""V3 offline types and real loopback HTTP/CLI integration; no game access."""
from copy import deepcopy
import contextlib
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import queue
import re
import sqlite3
import subprocess
import sys
import threading
import unittest
from unittest.mock import Mock, patch

from bridge.diplomacy_api import APIError, DiplomacyAPI
from bridge import diplomacy_contract_v2 as v2
from bridge import diplomacy_contract_v3 as v3
from bridge.diplomacy_service import make_server
from bridge.tests.test_diplomacy_contract_v2 import sample, connection
from tools import diplomacy as cli
from tools import serve_diplomacy as serve

ROOT = Path(__file__).resolve().parents[2]
TEN_EXAMPLES = ROOT / 'work/candidates/ten-families-typed-contract-r2-1375/request-examples.json'


def examples():
    result = {}
    for row in json.loads(TEN_EXAMPLES.read_bytes())['requests']:
        result[row['action_id']] = {'protocol': v3.PROTOCOL, 'request_id': row['request_id'],
                                     'action': row['action_id'], 'parameters': row['parameters']}
    return result


@contextlib.contextmanager
def server_context(token=None):
    server = make_server(None, port=0, token=token)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02})
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
        if thread.is_alive():
            raise AssertionError('uncollected HTTP thread')


class ContractV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = DiplomacyAPI.contract(version=3)
        cls.old = DiplomacyAPI.contract(version=2)

    def test_factory_versions_and_274_existing_v2_shapes_preserved(self):
        for version in (True, 3.0, '3', 1, 4, None):
            with self.subTest(version=version), self.assertRaises(APIError):
                DiplomacyAPI.contract(version)
        summary = self.c.describe()
        self.assertEqual(summary['catalog_actions'], 274)
        self.assertEqual(summary['production_executable_actions'], 0)
        self.assertEqual(summary['typed_binding_extensions'], self.old.describe()['typed_binding_extensions'] + 10)
        changed = []
        for row in summary['actions']:
            name = row['action']
            if self.c.describe(name)['parameters'] != self.old.describe(name)['parameters']:
                changed.append(name)
            if name not in self.c._ten:
                self.assertEqual(self.c.describe(name)['binding'], self.old.describe(name)['binding'])
        self.assertEqual(set(changed), set(v3.TEN_MIGRATIONS))
        self.assertEqual(self.old.describe()['protocol'], v2.PROTOCOL)

    def test_all274_database_free_unsupported_and_canonical_snapshot(self):
        ten = examples()
        with (patch.object(sqlite3, 'connect', side_effect=AssertionError('SQLite')),
              patch.object(DiplomacyAPI, '__init__', side_effect=AssertionError('V1 init')),
              patch.object(subprocess, 'Popen', side_effect=AssertionError('native process'))):
            c = DiplomacyAPI.contract(version=3)
            for row in c.describe()['actions']:
                name = row['action']
                payload = ten.get(name, {'protocol': v3.PROTOCOL, 'request_id': 'same-id', 'action': name,
                                         'parameters': sample(c.describe(name)['parameters'])})
                result = c.request(payload)
                self.assertEqual(result['status'], 'unsupported')
                self.assertEqual(result['protocol'], v3.PROTOCOL)
                self.assertEqual(result['parameters'], payload['parameters'])
                self.assertEqual(result['idempotency_scope'], 'not_reserved_contract_only')
                for field in ('request_written', 'queued', 'native_called', 'production_supported',
                              'runtime_binding_verified', 'live_identity_resolved', 'execution_verified', 'effect_verified'):
                    self.assertIs(result[field], False)
                raw = result['canonical_request'].encode('ascii')
                self.assertEqual(hashlib.sha256(raw).hexdigest(), result['request_sha256'])

    def test_four_migrations_reject_legacy_fields_and_integer_aliases(self):
        legacy = {'sell_province': {'province_id': 183, 'price': 100},
                  'enforce_peace': {'war_id': 'war1', 'defender': 'POR'},
                  'threaten_war': {'province_id': 183},
                  'trade_favors_for_trust': {'favors': 10}}
        for name, extra in legacy.items():
            payload = examples()[name]
            payload['parameters'] = {'actor': 'FRA', 'target': 'ENG', **extra}
            with self.subTest(action=name), self.assertRaises(APIError):
                self.c.request(payload)
            old = {**payload, 'protocol': v2.PROTOCOL}
            self.assertEqual(self.old.request(old)['status'], 'unsupported')
        for field, values in (('price_integer', (True, 100.0, -1, 2147484)),
                              ('province_id', (True, 183.0, 0, 2147483648))):
            for value in values:
                payload = examples()['sell_province']
                payload['parameters'][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(APIError):
                    self.c.request(payload)
        payload = examples()['sell_province']
        payload['parameters'].update(price_integer=2147483, province_id=2147483647)
        self.assertEqual(self.c.request(payload)['parameters']['price_integer'], 2147483)

    def test_cross_field_identity_and_explicit_taker_constraints(self):
        for name, payload in examples().items():
            payload['parameters']['target'] = payload['parameters']['actor']
            with self.subTest(action=name), self.assertRaises(APIError):
                self.c.validate(payload)
        for name, field in (('reduce_relations_favor', 'third_country'), ('enforce_peace', 'opposing_country')):
            for value in ('FRA', 'ENG', 0x0100008800524f50, 'por', 'ＰＯＲ'):
                payload = examples()[name]
                payload['parameters'][field] = value
                with self.subTest(action=name, value=value), self.assertRaises(APIError):
                    self.c.request(payload)
        payload = examples()['threaten_war']
        payload['parameters']['taker_country'] = 'POR'
        with self.assertRaises(APIError):
            self.c.request(payload)

    def test_ten_public_metadata_and_inputs_exclude_native_addresses_and_controls(self):
        forbidden = {'pointer', 'rva', 'full_handle', 'native_token', 'native_cancel', 'cancel', 'state', 'envoy_id'}
        def walk(value):
            if type(value) is dict:
                self.assertFalse(forbidden & set(value))
                for child in value.values():
                    walk(child)
            elif type(value) is list:
                for child in value:
                    walk(child)
            elif type(value) is str:
                self.assertIsNone(re.search(r'\b0x[0-9a-fA-F]+', value))
        for name, payload in examples().items():
            walk(self.c.describe(name)['binding'])
            walk(self.c.request(payload)['symbolic_binding'])
            for field in forbidden | {'amount', 'favors', 'runtime_verified', 'loaded_cost'}:
                bad = deepcopy(payload)
                bad['parameters'][field] = 1
                with self.subTest(action=name, field=field), self.assertRaises(APIError):
                    self.c.request(bad)
        trust = self.c.describe('trade_favors_for_trust')['binding']
        self.assertIsNone(trust['current_values'])
        self.assertFalse(trust['stock_value_fallback'])
        self.assertFalse(trust['cached_values_are_runtime_proof'])
        self.assertFalse(self.c.describe('reduce_relations_favor')['binding']['live_TAG_resolution_implemented'])

    def test_wire_unknown_keys_strict_subclasses_and_mutation_detachment(self):
        class IntLike(int):
            pass
        payload = examples()['sell_province']
        payload['parameters']['price_integer'] = IntLike(100)
        with self.assertRaises(APIError):
            self.c.request(payload)
        for raw in (b'{"action":"a","action":"b"}', b'{"x":NaN}', b'\xff'):
            with self.subTest(raw=raw), self.assertRaises(APIError):
                self.c.decode(raw)
        with self.assertRaises(APIError):
            self.c.decode(b' ' * 16385)
        payload = examples()['trade_favors_for_trust']
        for extra in ({'native_evidence': {}}, {'contract': 'TenFamiliesDraft/2'}, {'runtime_verified': True}):
            with self.subTest(extra=extra), self.assertRaises(APIError):
                self.c.validate({**payload, **extra})
        first = self.c.request(payload)
        payload['parameters']['target'] = 'POR'
        second = self.c.request(payload)
        self.assertNotEqual(first['request_sha256'], second['request_sha256'])
        self.assertEqual(first['parameters']['target'], 'ENG')
        self.assertEqual(first['idempotency_scope'], second['idempotency_scope'])

    def test_fixed_pins_reject_source_tamper_and_report_is_not_runtime_authority(self):
        original = v3.read_bounded
        def altered(path, limit):
            raw = original(path, limit)
            return raw + b' ' if path.name == 'contract.json' else raw
        with patch.object(v3, 'read_bounded', side_effect=altered), self.assertRaises(APIError):
            DiplomacyAPI.contract(version=3)
        description = self.c.describe('trade_favors_for_trust')
        self.assertFalse(description['native_binding_complete'])
        self.assertFalse(description['readiness']['runtime_binding_verified'])
        self.assertFalse(description['readiness']['native_ready'])
        self.assertIsNone(description['readiness']['legality'])


class HttpV3Tests(unittest.TestCase):
    def test_real_http_v3_drafts_no_sqlite_and_v2_remains_distinct(self):
        with patch.object(sqlite3, 'connect', side_effect=AssertionError('SQLite')), \
             patch.object(DiplomacyAPI, '__init__', side_effect=AssertionError('V1 init')), server_context() as server:
            self.assertEqual(connection(server, 'GET', '/v3/actions')[1]['catalog_actions'], 274)
            payload = examples()['trade_favors_for_trust']
            self.assertEqual(connection(server, 'POST', '/v3/validate', payload)[0], 200)
            status, result = connection(server, 'POST', '/v3/requests', payload)
            self.assertEqual(status, 501)
            self.assertEqual(result['protocol'], v3.PROTOCOL)
            self.assertFalse(result['request_written'])
            self.assertEqual(connection(server, 'POST', '/v2/requests', payload)[0], 400)
            old = {**payload, 'protocol': v2.PROTOCOL, 'parameters': {'actor': 'FRA', 'target': 'ENG', 'favors': 10}}
            self.assertEqual(connection(server, 'POST', '/v2/requests', old)[0], 501)
            self.assertEqual(connection(server, 'GET', '/v1/capabilities')[0], 404)
            for path in ('/v3/submit', '/v3/preview', '/v3/requests/id/reconcile'):
                self.assertEqual(connection(server, 'POST', path, {})[0], 404)

    def test_real_http_retains_budget_duplicate_origin_host_bearer_boundaries(self):
        with server_context(token='test-token') as server:
            headers = {'Authorization': 'Bearer test-token'}
            self.assertEqual(connection(server, 'GET', '/v3/actions')[0], 401)
            self.assertEqual(connection(server, 'GET', '/v3/actions', headers={**headers, 'Origin': 'https://invalid.test'})[0], 403)
            self.assertEqual(connection(server, 'GET', '/v3/actions', headers={**headers, 'Host': 'invalid.test'})[0], 403)
            for raw, expected in ((b' ' * 16385, 413), (b'{"a":1,"a":2}', 400), (b'\xff', 400)):
                self.assertEqual(connection(server, 'POST', '/v3/requests', raw=raw, headers=headers)[0], expected)
            payload = examples()['sell_province']
            payload['parameters']['price_integer'] = True
            self.assertEqual(connection(server, 'POST', '/v3/requests', payload, headers=headers)[0], 422)


class CliV3Tests(unittest.TestCase):
    def call(self, args, body=''):
        out, err = io.StringIO(), io.StringIO()
        with patch('sys.stdin', io.StringIO(body)), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(args)
        return code, json.loads(out.getvalue() or err.getvalue())

    def test_local_cli_avoids_v1_config_database_and_rejects_executable_options(self):
        with patch.object(cli, 'get_path', side_effect=AssertionError('config')), \
             patch.object(sqlite3, 'connect', side_effect=AssertionError('SQLite')), \
             patch.object(DiplomacyAPI, '__init__', side_effect=AssertionError('V1 init')):
            payload = json.dumps(examples()['trade_favors_for_trust'])
            self.assertEqual(self.call(['--api-version', '3', 'validate', '-'], payload)[0], 0)
            code, result = self.call(['--api-version', '3', 'request', '-'], payload)
            self.assertEqual(code, 2)
            self.assertEqual(result['status'], 'unsupported')
            self.assertEqual(self.call(['--api-version', '3', '--queue-db', 'forbidden.db', 'request', '-'], payload)[1]['error']['code'], 'version_option')
            self.assertEqual(self.call(['--api-version', '3', 'submit', 'missing.json'])[1]['error']['code'], 'version_command')
            self.assertEqual(self.call(['--api-version', '3', 'request', '-'], ' ' * 16385)[1]['error']['code'], 'request_budget')

    def test_actual_cli_subprocess_local_and_http_501_exit2(self):
        environment = dict(os.environ)
        environment.pop('EU4_DIPLOMACY_TOKEN', None)
        environment['NO_PROXY'] = '127.0.0.1,localhost'
        command = [sys.executable, '-B', str(ROOT / 'tools/diplomacy.py'), '--api-version', '3']
        body = json.dumps(examples()['reduce_relations_favor'])
        for url in (None, 'http'):
            with server_context() as server:
                extra = [] if url is None else ['--url', f'http://127.0.0.1:{server.server_port}']
                result = subprocess.run(command + extra + ['request', '-'], input=body, text=True,
                                        encoding='utf8', capture_output=True, cwd=ROOT, env=environment, timeout=15)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(json.loads(result.stdout)['status'], 'unsupported')

    def test_actual_v3_serve_subprocess_and_forbidden_remote_startup(self):
        environment = dict(os.environ)
        environment.pop('EU4_DIPLOMACY_TOKEN', None)
        child = subprocess.Popen([sys.executable, '-B', str(ROOT / 'tools/serve_diplomacy.py'),
                                  '--api-version', '3', '--port', '0'], cwd=ROOT, env=environment,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf8')
        lines = queue.Queue()
        def reader():
            lines.put(child.stdout.readline())
            lines.put(child.stdout.readline())
        thread = threading.Thread(target=reader)
        thread.start()
        try:
            first = lines.get(timeout=10)
            second = lines.get(timeout=10)
            self.assertIn('/v3/actions', first)
            self.assertIn('V3: unsupported', second)
            port = int(re.search(r':(\d+)/v3/actions', first).group(1))
            fake = Mock(server_port=port)
            self.assertEqual(connection(fake, 'POST', '/v3/requests', examples()['trade_favors_for_trust'])[0], 501)
            self.assertEqual(connection(fake, 'GET', '/v1/capabilities')[0], 404)
        finally:
            child.terminate()
            child.communicate(timeout=5)
            thread.join(3)
            self.assertFalse(thread.is_alive())
        with patch('sys.argv', ['serve', '--api-version', '3', '--allow-remote']), \
             patch.object(serve, 'make_server', side_effect=AssertionError('server creation')), \
             patch.object(DiplomacyAPI, '__init__', side_effect=AssertionError('V1 init')), \
             contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            serve.main()


if __name__ == '__main__':
    unittest.main()
