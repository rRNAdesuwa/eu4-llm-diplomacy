"""Actual loopback routing and negative evidence semantics; no game access."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from bridge.war_state_service import (WarStateObserver, compact_capture,
    make_war_server, tags)

TOKEN = 'observer-test-token-0123456789'


class FakeWar:
    def __init__(self):
        self.calls = []
        self.fail = False

    def observe_pair(self, actor, target):
        self.calls.append((actor, target))
        if self.fail:
            raise RuntimeError('Target changed during read')
        return dict(status='observed', pair_state='opponents', native_calls=0,
                    requests_published=0, runtime_effect_verified=False)


class FakeEffects:
    def __init__(self):
        self.calls = []

    def observe(self, request_id):
        self.calls.append(request_id)
        return dict(request_id=request_id, effect=dict(status='unknown'), requests_published=0)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.war, self.effects = FakeWar(), FakeEffects()
        self.server = make_war_server(self.war, port=0, token=TOKEN, effect_observer=self.effects)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs=dict(poll_interval=0.01))
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.assertFalse(self.thread.is_alive())

    def request(self, method='GET', path='/observer/v1/wars/ENG/AMG', headers=None, body=None):
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        values = {'Authorization': 'Bearer '+TOKEN} if headers is None else headers
        try:
            c.request(method, path, body=body, headers=values)
            r = c.getresponse()
            raw = r.read()
            self.assertEqual(r.getheader('Cache-Control'), 'no-store')
            return r.status, json.loads(raw)
        finally:
            c.close()

    def test_current_pair_route(self):
        code, value = self.request()
        self.assertEqual(code, 200)
        self.assertEqual(value['pair_state'], 'opponents')
        self.assertFalse(value['runtime_effect_verified'])
        self.assertEqual(self.war.calls, [('ENG', 'AMG')])
        self.assertEqual(self.effects.calls, [])

    def test_effect_route_delegates(self):
        code, value = self.request(path='/observer/v1/effects/original-id')
        self.assertEqual((code, value['request_id']), (200, 'original-id'))
        self.assertEqual(self.effects.calls, ['original-id'])
        self.assertEqual(self.war.calls, [])

    def test_no_token_no_read(self):
        self.assertEqual(self.request(headers={})[0], 403)
        self.assertEqual(self.war.calls, [])

    def test_wrong_token_no_read(self):
        self.assertEqual(self.request(headers={'Authorization': 'Bearer wrong'})[0], 403)
        self.assertEqual(self.war.calls, [])

    def test_origin_no_read(self):
        self.assertEqual(self.request(headers={'Authorization': 'Bearer '+TOKEN,
            'Origin': 'http://localhost'})[0], 403)
        self.assertEqual(self.war.calls, [])

    def test_foreign_host_no_read(self):
        self.assertEqual(self.request(headers={'Authorization': 'Bearer '+TOKEN,
            'Host': 'example.org'})[0], 403)
        self.assertEqual(self.war.calls, [])

    def test_same_country_refused(self):
        self.assertEqual(self.request(path='/observer/v1/wars/FRA/FRA')[0], 422)
        self.assertEqual(self.war.calls, [])

    def test_query_refused(self):
        self.assertEqual(self.request(path='/observer/v1/wars/ENG/AMG?retry=1')[0], 422)
        self.assertEqual(self.war.calls, [])

    def test_encoded_country_refused(self):
        self.assertEqual(self.request(path='/observer/v1/wars/%45NG/AMG')[0], 422)
        self.assertEqual(self.war.calls, [])

    def test_lowercase_country_refused(self):
        self.assertEqual(self.request(path='/observer/v1/wars/eng/AMG')[0], 422)
        self.assertEqual(self.war.calls, [])

    def test_extra_segment_refused(self):
        self.assertEqual(self.request(path='/observer/v1/wars/ENG/AMG/retry')[0], 422)
        self.assertEqual(self.war.calls, [])

    def test_read_failure_stays_unknown(self):
        self.war.fail = True
        code, value = self.request()
        self.assertEqual(code, 409)
        self.assertEqual(value['status'], 'unknown')
        self.assertFalse(value['automatic_command_retry'])
        self.assertEqual(len(self.war.calls), 1)

    def test_post_refuses_without_observation(self):
        code, value = self.request('POST', body='{"action":"declare_war"}')
        self.assertEqual(code, 405)
        self.assertEqual(value['requests_published'], 0)
        self.assertEqual(self.war.calls, [])
        self.assertEqual(self.effects.calls, [])

    def test_bad_auth_post_refuses(self):
        self.assertEqual(self.request('POST', headers={})[0], 403)
        self.assertEqual(self.war.calls, [])

    def test_combined_capabilities_preserve_effect_boundary(self):
        def catalog():
            return dict(profiles=['selected_effect'], all120_effect_profiles_complete=False)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.server = make_war_server(self.war, port=0, token=TOKEN,
            effect_observer=self.effects, capability_factory=catalog)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs=dict(poll_interval=0.01))
        self.thread.start()
        code, value = self.request(path='/observer/v1/capabilities')
        self.assertEqual(code, 200)
        self.assertEqual(value['profiles'], ['selected_effect'])
        self.assertFalse(value['all120_effect_profiles_complete'])
        self.assertFalse(value['war_state']['peace_API_completion_verified'])
        self.assertEqual(self.war.calls, [])


class EvidenceTests(unittest.TestCase):
    def test_invalid_tag_rejects_before_process_open(self):
        observer = object.__new__(WarStateObserver)
        with patch('bridge.war_state_service.RuntimeCapture') as opener:
            with self.assertRaises((ValueError, RuntimeError)):
                observer.capture_pair('FRA', '../')
            opener.assert_not_called()

    def test_boolean_tag_not_accepted(self):
        with self.assertRaises((ValueError, RuntimeError)):
            tags(True, 'ENG')

    def test_projection_keeps_completion_unproven(self):
        capture = dict(status='observed', identity={}, captured_utc='fixed',
            identity_purpose='nonce', two_pass_equal=True, duration_ms=1,
            total_rpm_budget=dict(calls=1, bytes=8), limitations=[],
            projection=dict(pair_state='not_currently_opponents', global_war_count=0))
        value = compact_capture(capture)
        self.assertEqual(value['pair_state'], 'not_currently_opponents')
        for key in ('peace_completion_verified', 'war_retired_proven', 'runtime_effect_verified',
                    'world_epoch_proven', 'request_causality_verified'):
            self.assertFalse(value[key])

    def test_unknown_projection_cannot_become_absence(self):
        capture = dict(status='unknown', identity={}, captured_utc='fixed',
            identity_purpose='nonce', duration_ms=1, total_rpm_budget={},
            limitations=[], failure='unsupported world')
        value = compact_capture(capture)
        self.assertEqual(value['status'], 'unknown')
        self.assertIsNone(value['pair_state'])
        self.assertFalse(value['two_pass_equal'])


if __name__ == '__main__':
    unittest.main()
