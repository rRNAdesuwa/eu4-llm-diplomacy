"""Only new R2 pure-fake/byte tests; no fixture, REA or Frida execution.

The controller Popen is mocked. Existing parser/JS/job suites are not rerun.
"""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import controller
import evidence
import launch_smoke
import protocol


def complete_cli_document(duration):
    # Independent complete wire layout; use the actual semantic content hash
    # so a duration rejection cannot be explained by an unrelated bad ID.
    pid, nonce = 31415, 'ab'*16
    session, script_id = '11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222'
    script_path, sha = 'D:\\owned\\rendered-smoke.js', 'bc'*32
    observation = dict(
        evidence_id='', subject=None, provider=dict(id='frida', name='Frida', version=None),
        analysis_profile=None, predicate_type='rea.frida.instrumentation-observation',
        operation='instrument_with_frida',
        parameters=dict(session_id=session, device_id='local', mode='attach', pid=pid),
        raw_result=None,
        normalized_result=dict(session_id=session, device_id='local', state='running',
            target='python.exe (pid 31415)', pid=pid, mode='attach',
            scripts=[dict(script_id=script_id, name='rea-'+script_id)],
            messages=[dict(script_id=script_id, type='send', payload=dict(
                schema='REA-OWNED-FIXTURE-SMOKE/1', pid=pid, platform='windows', arch='x64',
                pointer_size=8, nonce=nonce))], messages_truncated=False,
            source_kind='file', source_path=script_path, source_sha256=sha, cleanup_error=None),
        confidence='observed', authority='external-service', environment=None,
        limitations=['Artifact identity is unavailable for this observation.',
            'The target operating system and architecture were not reported by this observation.'],
        relationship_coverage=None, locations=[], evidence_links=[])
    semantic = {key: value for key, value in observation.items()
                if key not in ('evidence_id', 'relationship_coverage')}
    observation['evidence_id'] = 'ev_'+hashlib.sha256(json.dumps(semantic,
        sort_keys=True, separators=(',', ':')).encode('ascii')).hexdigest()
    raw = json.dumps(dict(ok=True, data=dict(evidence=observation, cleanup_error=None),
        meta=dict(command='instrument-with-frida', duration=duration)), separators=(',', ':')).encode('ascii')
    return raw, dict(pid=pid, nonce=nonce, script_path=script_path, script_sha256=sha)


class ClosedHandle:
    def __init__(self):
        self.closed = 0

    def Close(self):
        self.closed += 1


class CollectedFakeProcess:
    def __init__(self):
        self._handle = ClosedHandle()
        self.waits = 0

    def poll(self):
        return 0

    def wait(self, timeout):
        self.waits += 1
        return 0

    def terminate(self):
        raise AssertionError('Successful fake must not be terminated')


class NewProfileTests(unittest.TestCase):
    def test_actual_controller_cli_receipt_roundtrips_through_launcher_bytes(self):
        fake = CollectedFakeProcess()
        with tempfile.TemporaryDirectory(prefix='rea-owned-pure-r2-') as temporary:
            with patch.object(controller.subprocess, 'Popen', return_value=fake) as spawn:
                with patch.object(controller.time, 'monotonic', side_effect=[10.0, 10.01, 10.125]):
                    cli = controller.run_cli(['pure-fake-never-started'], Path(temporary))
            self.assertEqual(spawn.call_count, 1)
            self.assertEqual(fake._handle.closed, 1)
            self.assertEqual(fake.waits, 2)
            self.assertEqual(cli['elapsed_ms'], 125)
            self.assertIs(type(cli['elapsed_ms']), int)
            self.assertNotIn('seconds', cli)
            self.assertIsNone(cli['error'])
            self.assertEqual(cli['exit_code'], 0)
            controller_receipt = dict(schema='REA-OWNED-SMOKE-CONTROLLER/1', cli=cli,
                source_postcheck=True, fixture_cleanup=dict(collected=True, exit_code=0),
                nonce='ab'*16, native_ready=False, lease=False)
            encoded = json.dumps(controller_receipt).encode('ascii')
            self.assertEqual(launch_smoke.strict_json(encoded), controller_receipt)
            broken = copy.deepcopy(controller_receipt)
            broken['cli']['seconds'] = 0.125
            with self.assertRaises(ValueError):
                launch_smoke.strict_json(json.dumps(broken).encode('ascii'))

    def test_normal_unicode_source_strings_accept_only_opt_in(self):
        raw = json.dumps(dict(name='synthetic-package', authors=['\u4f5c\u8005', 'A\u00e9']),
                         ensure_ascii=False).encode('utf-8')
        decoded = evidence.strict_json(raw, ascii_strings=False)
        self.assertEqual(decoded['name'], 'synthetic-package')
        self.assertTrue(any(not value.isascii() for value in decoded['authors']))
        with self.assertRaises(ValueError):
            evidence.strict_json(raw)  # Evidence profile remains ASCII.
        with self.assertRaises(ValueError):
            evidence.strict_json(b'{"source":"\\ud800"}', ascii_strings=False)

    def test_source_opt_in_keeps_duplicate_nonfinite_utf8_and_bounds(self):
        cases = [b'{"x":1,"x":2}', b'{"o":{"x":1,"x":2}}', b'{"x":NaN}',
            b'{"x":Infinity}', b'\xff{}', b'\xef\xbb\xbf{}', b'{}{}',
            b'['*40+b'0'+b']'*40, b'{}'+b' '*65536]
        for bad in cases:
            with self.subTest(kind=bad[:12]), self.assertRaises(ValueError):
                evidence.strict_json(bad, ascii_strings=False)

    def test_exact_pinned_package_is_valid_utf8_without_author_output(self):
        raw = protocol.read_bound(protocol.REA/'node_modules/frida/package.json')
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
            '7efb59d2050b7b6304e1617f463c4eb7b2f7cb7e3e80e677976825a76ee31e8d')
        package = evidence.strict_json(raw, ascii_strings=False)
        self.assertEqual(package['version'], '17.23.2')
        self.assertEqual(protocol.strict_json(raw, ascii_strings=False), package)

    def test_native_cli_duration_digits_ms_accepts_selected_positive_cases(self):
        for duration in ('0ms', '1ms', '1500ms', '45678ms'):
            raw, expected = complete_cli_document(duration)
            self.assertEqual(evidence.extract(raw, **expected)['payload']['pid'], 31415)

    def test_native_cli_duration_rejects_unemitted_formats(self):
        for duration in ('', '1.5s', '1.5ms', '-1ms', '+1ms', '01ms', '1e3ms',
                         'NaNms', '1ms\n', ' 1ms', '1000', 1500, True, '9'*17+'ms'):
            with self.subTest(duration=duration):
                raw, expected = complete_cli_document(duration)
                with self.assertRaises(ValueError):
                    evidence.extract(raw, **expected)

    def test_utf8_source_opt_in_does_not_relax_evidence_extract(self):
        raw, expected = complete_cli_document('1500ms')
        document = json.loads(raw)
        document['meta']['duration'] = '\u4e00ms'
        encoded = json.dumps(document, ensure_ascii=False).encode('utf-8')
        with self.assertRaises(ValueError):
            evidence.extract(encoded, **expected)


if __name__ == '__main__':
    unittest.main(verbosity=2)
