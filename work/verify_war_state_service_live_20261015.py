"""Real loopback GET acceptance on held PID80340; close all listeners."""
from datetime import datetime, timezone
import http.client
import json
from pathlib import Path
import secrets
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.war_state_service import WarStateObserver, make_war_server, source_pins
from bridge.tag_command_backend import digest, require


def main():
    directory = ROOT/'work/reports/runtime-observer-20261015-r1'
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory/'live-http-verification.json'
    require(not destination.exists(), 'Exclusive report required')
    token = secrets.token_urlsafe(32)
    initial = source_pins()
    observer = WarStateObserver(80340, '01dd5c075fcf8c26', store=directory/'captures')
    server = make_war_server(observer, port=0, token=token)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, kwargs=dict(poll_interval=0.05))
    thread.start()
    rows = []
    try:
        for method, path, authorized, expected, state in (
            ('GET', '/observer/v1/capabilities', True, 200, None),
            ('GET', '/observer/v1/wars/ENG/AMG', True, 200, 'opponents'),
            ('GET', '/observer/v1/wars/FRA/ENG', True, 200, 'not_currently_opponents'),
            ('GET', '/observer/v1/wars/ENG/AMG', False, 403, None),
            ('POST', '/observer/v1/wars/ENG/AMG', True, 405, None),
            ('GET', '/observer/v1/effects/not-configured', True, 404, None)):
            client = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
            try:
                headers = {'Authorization': 'Bearer '+token} if authorized else {}
                client.request(method, path, headers=headers)
                response = client.getresponse()
                raw = response.read()
                require(response.status == expected and response.getheader('Cache-Control') == 'no-store',
                    'HTTP status/cache contract differs')
                value = json.loads(raw)
                if state is not None:
                    require(value['status'] == 'observed' and value['pair_state'] == state
                        and value['two_pass_equal'] is True, 'Current war projection differs')
                    require(value['global_war_count'] == 4 and not value['peace_completion_verified']
                        and not value['runtime_effect_verified'], 'Evidence boundary differs')
                    record = value['record']
                    full = Path(record['path']).read_bytes()
                    require(len(full) == record['bytes'] and digest(full) == record['sha256'],
                        'Complete journal identity differs')
                rows.append(dict(method=method, path=path, authorized=authorized,
                    http_status=response.status, response=value))
            finally:
                client.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
    require(not thread.is_alive() and server.socket.fileno() == -1, 'Listener/thread remains')
    require(source_pins() == initial, 'Sources changed during live HTTP acceptance')
    producer = Path(__file__).read_bytes()
    result = dict(schema='EU4-RUNTIME-OBSERVER-LIVE-HTTP/1',
        verified_utc=datetime.now(timezone.utc).isoformat(), pid=80340,
        creation='01dd5c075fcf8c26', source_pins=initial,
        producer=dict(path=Path(__file__).relative_to(ROOT).as_posix(),
            bytes=len(producer), sha256=digest(producer)),
        cases=rows, listener_closed=True, server_thread_joined=True,
        native_calls=0, memory_written=False, requests_published=0, saves_written=0, reloads=0,
        offline_new_host_tests=dict(count=19, passed=True,
            command='python -B -m unittest bridge.tests.test_war_state_service -v',
            execution_seconds=0.393, evidence='Root tool execution before this live acceptance; not rerun here'),
        active_knowledge_effect_tested=False, new_war_peace_API_effect_tested=False)
    with destination.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(dict(output=str(destination), bytes=destination.stat().st_size,
        sha256=digest(destination.read_bytes()), source_pins=len(initial),
        cases=[dict(method=x['method'], path=x['path'], status=x['http_status'],
            pair_state=x['response'].get('pair_state'), duration_ms=x['response'].get('duration_ms')) for x in rows],
        listener_closed=True, server_thread_joined=True)))


if __name__ == '__main__':
    main()
