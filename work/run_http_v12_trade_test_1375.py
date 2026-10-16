"""One fixed v12 HTTP submit, then read-only completion and idempotency checks."""
from __future__ import annotations
from http.client import HTTPConnection
import json
from pathlib import Path
import secrets
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge import diplomacy_lab_http_v12 as http
from work.native import lab_protocol_v12_1375 as lab


def main():
    output = lab.OUTPUT / 'trade-power-http-submit-17676.json'
    body = {'protocol': lab.PROTOCOL, 'pid': 17676, 'creation': '01dd56989186135c',
            'sequence': 3, 'mode': 'submit', 'action': 'request_trade_power',
            'actor': 'FRA', 'target': 'POR', 'ttl_ms': 5000}
    # Exclusive audit reservation precedes every possible publication.
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        report = {'purpose': 'one_fixed_v12_http_trade_submit', 'request': body,
                  'automatic_retry': False, 'token_written_to_disk': False,
                  'ai_acceptance_verified': False, 'effect_verified': False,
                  'steps': [], 'server_closed': False, 'server_thread_joined': False}
        server = thread = None
        exit_code = 2
        try:
            service = http.ResearchService(http.V12ResearchRuntime(body['pid'], body['creation']))
            token = secrets.token_hex(32)
            server = http.make_server(service, host='127.0.0.1', port=8769, token=token)
            thread = threading.Thread(target=server.serve_forever,
                                      kwargs={'poll_interval': 0.05}, daemon=True)
            thread.start()

            def call(method, route, data=None):
                client = HTTPConnection('127.0.0.1', 8769, timeout=5)
                try:
                    client.request(method, route,
                        body=None if data is None else json.dumps(data, separators=(',', ':')),
                        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
                    response = client.getresponse()
                    raw = response.read(2 * 1024 * 1024 + 1)
                    lab.require(len(raw) <= 2 * 1024 * 1024, 'Oversized HTTP response')
                    value = json.loads(raw)
                    report['steps'].append({'method': method, 'route': route,
                                            'http_status': response.status, 'response': value})
                    return response.status, value
                finally:
                    client.close()

            status, ready = call('GET', http.PREFIX + '/status')
            lab.require(status == 200 and ready['pair_publication_ready'] is True
                        and ready['last_sequence'] == 2, 'Session is not ready for the exact next sequence')
            status, published = call('POST', http.PREFIX + '/pair', body)
            lab.require(status == 202 and published.get('request_written') is True,
                        'Publication not verified; query evidence, never resend')
            deadline = time.monotonic() + 3
            completed = None
            while time.monotonic() < deadline:
                status, queried = call('GET', http.PREFIX + '/requests/3')
                lab.require(status == 200, 'Read-only completion query failed')
                if queried['state'] == 'native_completed':
                    completed = queried
                    break
                lab.require(queried['state'] == 'queued', 'Unknown result; do not resend')
                time.sleep(0.1)
            lab.require(completed is not None, 'Completion not yet observed; no retry')
            core = completed['native']['records'][-1]
            lab.require(core['status'] == 2 and core['reason'] == 0
                and core['submit_entered'] is True and core['submit_returned'] is True
                and core['caller_container_consumed'] is True
                and core['ownership_uncertain'] is False and core['freeze_session'] is False
                and core['exception'] == 0, 'Native dispatch did not satisfy the reviewed ownership contract')
            # This identical POST may only read the permanently bound intent.
            status, replay = call('POST', http.PREFIX + '/pair', body)
            lab.require(status == 200 and replay['replayed'] is True
                and replay['request_written'] is False and replay['state'] == 'native_completed',
                'Read-only idempotency replay was not verified')
            report['native_dispatch_verified'] = True
            exit_code = 0
        except Exception as error:
            report['error'] = {'type': type(error).__name__, 'message': str(error)}
        finally:
            if server is not None:
                if thread is not None and thread.is_alive():
                    server.shutdown()
                    thread.join(2)
                server.server_close()
                report['server_closed'] = server.fileno() == -1
                report['server_thread_joined'] = thread is None or not thread.is_alive()
            report['exit_code'] = exit_code
            json.dump(report, stream, indent=2)
            stream.write('\n')
    print(json.dumps({'output': str(output), 'exit_code': exit_code,
        'error': report.get('error'), 'native_dispatch_verified': report.get('native_dispatch_verified', False),
        'http_statuses': [step['http_status'] for step in report['steps']],
        'server_closed': report['server_closed'], 'server_thread_joined': report['server_thread_joined']}))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
