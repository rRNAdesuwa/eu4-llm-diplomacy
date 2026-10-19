"""Only new pure FFI-profile/parser/job-receipt tests; no fixture/WinAPI/REA/Frida."""
import copy
import hashlib
import json
import unittest

from evidence import extract, semantic_id, strict_json
from protocol import require_clean_job

PID, NONCE = 31415, 'ab'*16
SCRIPT, SHA = 'D:\\owned-ffi\\rendered-smoke.js', 'bc'*32
SESSION, SCRIPT_ID = '11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222'


def document():
    payload = dict(schema='REA-OWNED-FFI-OBSERVATION/1', pid=PID, platform='windows',
        arch='x64', pointer_size=8, nonce=NONCE, lstrlenA=3, GetCurrentProcessId=PID)
    result = dict(session_id=SESSION, device_id='local', state='running',
        target='python.exe (pid 31415)', pid=PID, mode='attach',
        scripts=[dict(script_id=SCRIPT_ID, name='rea-'+SCRIPT_ID)],
        messages=[dict(script_id=SCRIPT_ID, type='send', payload=payload)],
        messages_truncated=False, source_kind='file', source_path=SCRIPT,
        source_sha256=SHA, cleanup_error=None)
    evidence = dict(evidence_id='', subject=None, provider=dict(id='frida', name='Frida', version=None),
        analysis_profile=None, predicate_type='rea.frida.instrumentation-observation',
        operation='instrument_with_frida',
        parameters=dict(session_id=SESSION, device_id='local', mode='attach', pid=PID),
        raw_result=None, normalized_result=result, confidence='observed', authority='external-service',
        environment=None, limitations=['Artifact identity is unavailable for this observation.',
            'The target operating system and architecture were not reported by this observation.'],
        relationship_coverage=None, locations=[], evidence_links=[])
    return dict(ok=True, data=dict(evidence=evidence, cleanup_error=None),
                meta=dict(command='instrument-with-frida', duration='1500ms'))


def encode(value, rehash=True):
    if rehash:
        evidence = value['data']['evidence']
        evidence['evidence_id'] = semantic_id(evidence)
    return json.dumps(value, separators=(',', ':')).encode('ascii')


def parse(raw):
    return extract(raw, pid=PID, nonce=NONCE, script_path=SCRIPT, script_sha256=SHA)


def payload(value):
    return value['data']['evidence']['normalized_result']['messages'][0]['payload']


class FFIContractTests(unittest.TestCase):
    def test_complete_ffi_observation_and_metadata_only_schema_refusal(self):
        value = document()
        self.assertEqual(parse(encode(value))['payload'], payload(value))
        payload(value).pop('lstrlenA')
        payload(value).pop('GetCurrentProcessId')
        payload(value)['schema'] = 'REA-OWNED-FIXTURE-SMOKE/1'
        with self.assertRaises(ValueError):
            parse(encode(value))

    def test_each_return_scalar_is_exact_and_bound_to_held_expected_pid(self):
        for key, wrong in [('lstrlenA', 0), ('lstrlenA', True), ('lstrlenA', '3'),
            ('GetCurrentProcessId', PID+1), ('GetCurrentProcessId', True),
            ('GetCurrentProcessId', 1 << 40), ('pid', True), ('pointer_size', True),
            ('nonce', 'cd'*16), ('native_ready', True)]:
            with self.subTest(key=key, wrong=wrong):
                value = document(); payload(value)[key] = wrong
                with self.assertRaises(ValueError):
                    parse(encode(value))

    def test_unique_send_cleanup_and_exact_render_hash_are_required_for_ffi_success(self):
        for mode in ('outer_cleanup','inner_cleanup','duplicate','error','binary','truncated','source','target'):
            value = document(); result = value['data']['evidence']['normalized_result']
            if mode == 'outer_cleanup': value['data']['cleanup_error'] = 'failed'
            elif mode == 'inner_cleanup': result['cleanup_error'] = 'failed'
            elif mode == 'duplicate': result['messages'] *= 2
            elif mode == 'error': result['messages'][0]['type'] = 'error'
            elif mode == 'binary': result['messages'][0]['data_base64'] = ''
            elif mode == 'truncated': result['messages_truncated'] = True
            elif mode == 'source': result['source_sha256'] = 'ff'*32
            elif mode == 'target': result['target'] = 'eu4.exe (pid 31415)'
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                parse(encode(value))

    def test_semantic_hash_binds_new_returns_and_duplicate_raw_key_cannot_hide_return(self):
        value = document(); encode(value)
        payload(value)['lstrlenA'] = 4
        with self.assertRaises(ValueError): parse(encode(value, rehash=False))
        raw = encode(document())
        bad = raw.replace(b'"lstrlenA":3', b'"lstrlenA":0,"lstrlenA":3')
        with self.assertRaises(ValueError): parse(bad)
        with self.assertRaises(ValueError): strict_json(b'{"lstrlenA":3.0}')
        # A correct payload still needs REA's exact semantic ID, not an arbitrary digest.
        value = document(); encode(value)
        value['data']['evidence']['evidence_id'] = 'ev_'+'00'*32
        with self.assertRaises(ValueError): parse(encode(value, rehash=False))

    def test_job_cumulative_one_through_eight_with_active_zero_only(self):
        state = dict(error=None, exit_code=0, direct_child_collected=True,
            job_active_processes_final=0, completed_command_descendants_terminated=False,
            job_total_processes=1, peak_job_commit=1024)
        for count in range(1,9):
            require_clean_job(dict(state, job_total_processes=count))
        for key, wrong in [('job_total_processes',0),('job_total_processes',9),
            ('job_total_processes',True),('job_total_processes',1.0),
            ('job_active_processes_final',1),('job_active_processes_final',False),
            ('direct_child_collected',1),('completed_command_descendants_terminated',0),
            ('completed_command_descendants_terminated',True),('exit_code',False),
            ('peak_job_commit',768*1024*1024+1),('error','failed')]:
            with self.subTest(key=key, wrong=wrong), self.assertRaises(ValueError):
                require_clean_job(dict(state, **{key:wrong}))


if __name__ == '__main__':
    unittest.main(verbosity=2)
