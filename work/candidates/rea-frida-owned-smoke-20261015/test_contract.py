"""Future pure parser tests. Does not start a fixture, child, Frida, REA or game."""
import copy
import hashlib
import json
import unittest

from evidence import extract, semantic_id, strict_json

PID, NONCE = 31415, 'ab'*16
SCRIPT = 'D:\\owned-fixture\\rendered-smoke.js'
SOURCE = b'const config = "owned-fixture";\n'
SHA = hashlib.sha256(SOURCE).hexdigest()
SESSION = '11111111-1111-4111-8111-111111111111'
SCRIPT_ID = '22222222-2222-4222-8222-222222222222'


def document():
    # A complete selected REA field layout, not a shortened mock envelope.
    normalized = dict(session_id=SESSION, device_id='local', state='running',
        target='python.exe (pid 31415)', pid=PID, mode='attach',
        scripts=[dict(script_id=SCRIPT_ID, name='rea-'+SCRIPT_ID)],
        messages=[dict(script_id=SCRIPT_ID, type='send', payload=dict(
            schema='REA-OWNED-FIXTURE-SMOKE/1', pid=PID, platform='windows',
            arch='x64', pointer_size=8, nonce=NONCE))],
        messages_truncated=False, source_kind='file', source_path=SCRIPT,
        source_sha256=SHA, cleanup_error=None)
    evidence = dict(evidence_id='', subject=None,
        provider=dict(id='frida', name='Frida', version=None), analysis_profile=None,
        predicate_type='rea.frida.instrumentation-observation', operation='instrument_with_frida',
        parameters=dict(session_id=SESSION, device_id='local', mode='attach', pid=PID),
        raw_result=None, normalized_result=normalized, confidence='observed', authority='external-service',
        environment=None, limitations=['Artifact identity is unavailable for this observation.',
            'The target operating system and architecture were not reported by this observation.'],
        relationship_coverage=None, locations=[], evidence_links=[])
    evidence['evidence_id'] = semantic_id(evidence)
    return dict(ok=True, data=dict(evidence=evidence, cleanup_error=None),
                meta=dict(command='instrument-with-frida', duration='1500ms'))


def encoded(value, recompute=True):
    value = copy.deepcopy(value)
    if recompute:
        evidence = value['data']['evidence']
        evidence['evidence_id'] = semantic_id(evidence)
    return json.dumps(value, separators=(',', ':')).encode('ascii')


def parse(raw):
    return extract(raw, pid=PID, nonce=NONCE, script_path=SCRIPT, script_sha256=SHA)


class ContractTests(unittest.TestCase):
    def test_complete_selected_envelope(self):
        result = parse(encoded(document()))
        self.assertEqual(result['session_id'], SESSION)
        self.assertEqual(result['payload']['nonce'], NONCE)

    def test_error_messages_are_failure_even_with_ok_and_exit_success(self):
        for message in (dict(script_id=SCRIPT_ID, type='error', description='Script failed'),
                        dict(script_id=SCRIPT_ID, type='log', payload='diagnostic')):
            value = document()
            value['data']['evidence']['normalized_result']['messages'] = [message]
            with self.assertRaises(ValueError):
                parse(encoded(value))

    def test_all_binary_truncation_and_redaction_fields_refused(self):
        for key, bad in [('data_base64', ''), ('data_bytes', 0), ('data_truncated', False),
            ('data_redacted', False), ('type_truncated', False), ('payload_truncated', False),
            ('description_truncated', False), ('stack_truncated', False), ('description', ''), ('stack', '')]:
            with self.subTest(key=key):
                value = document()
                value['data']['evidence']['normalized_result']['messages'][0][key] = bad
                with self.assertRaises(ValueError):
                    parse(encoded(value))

    def test_global_truncation_or_two_messages_refused(self):
        for mode in ('truncated', 'duplicate', 'zero'):
            value = document()
            result = value['data']['evidence']['normalized_result']
            if mode == 'truncated':
                result['messages_truncated'] = True
            elif mode == 'duplicate':
                result['messages'] *= 2
            else:
                result['messages'] = []
            with self.assertRaises(ValueError):
                parse(encoded(value))

    def test_both_cleanup_error_fields_independently_required(self):
        for outer in (False, True):
            value = document()
            container = value['data'] if outer else value['data']['evidence']['normalized_result']
            container['cleanup_error'] = 'detach failed'
            with self.assertRaises(ValueError):
                parse(encoded(value))

    def test_session_pid_script_source_and_payload_binding(self):
        paths = [(['parameters', 'pid'], PID+1), (['parameters', 'pid'], True),
            (['normalized_result', 'pid'], PID+1), (['normalized_result', 'pid'], True),
            (['normalized_result', 'device_id'], 'remote'),
            (['normalized_result', 'state'], 'detached'),
            (['normalized_result', 'target'], 'eu4.exe (pid 31415)'),
            (['normalized_result', 'source_sha256'], '0'*64),
            (['normalized_result', 'source_path'], 'D:\\other.js'),
            (['normalized_result', 'session_id'], SCRIPT_ID),
            (['normalized_result', 'messages', 0, 'script_id'], SESSION),
            (['normalized_result', 'messages', 0, 'payload', 'nonce'], 'cd'*16),
            (['normalized_result', 'messages', 0, 'payload', 'pid'], PID+1),
            (['normalized_result', 'messages', 0, 'payload', 'pointer_size'], True),
            (['normalized_result', 'messages', 0, 'payload'], 'not an object')]
        for path, bad in paths:
            with self.subTest(path=path):
                value = document()
                parent = value['data']['evidence']
                for part in path[:-1]:
                    parent = parent[part]
                parent[path[-1]] = bad
                with self.assertRaises(ValueError):
                    parse(encoded(value))

    def test_evidence_id_cannot_be_forged_by_wrong_projection(self):
        value = document()
        evidence = value['data']['evidence']
        wrong = {key: item for key, item in evidence.items() if key != 'evidence_id'}
        evidence['evidence_id'] = 'ev_'+hashlib.sha256(json.dumps(wrong,
            sort_keys=True, separators=(',', ':')).encode('ascii')).hexdigest()
        with self.assertRaises(ValueError):
            parse(encoded(value, recompute=False))

    def test_reject_duplicate_keys_every_level_and_trailing_or_nonutf8(self):
        raw = encoded(document())
        cases = [raw.replace(b'"ok":true', b'"ok":false,"ok":true', 1),
            raw.replace(b'"nonce":"'+NONCE.encode()+b'"',
                        b'"nonce":"'+NONCE.encode()+b'","nonce":"'+NONCE.encode()+b'"'),
            raw+b'{}', b'\xff'+raw, b'\xef\xbb\xbf'+raw,
            raw.decode('ascii').encode('utf-16'), b'{"x":NaN}', b'{"x":Infinity}']
        for bad in cases:
            with self.assertRaises(ValueError):
                parse(bad)

    def test_bounds_bool_float_and_unexpected_metadata(self):
        for raw in (b'{}'+b' '*65536, b'{"x":1.0}', b'{"x":9007199254740992}',
                    b'['*40+b'0'+b']'*40):
            with self.assertRaises(ValueError):
                strict_json(raw)
        value = document()
        value['meta']['extra'] = 'not selected'
        with self.assertRaises(ValueError):
            parse(encoded(value))


if __name__ == '__main__':
    unittest.main()
