"""Real composed HTTP relation/war reads; no dispatcher or game mutation."""
from datetime import datetime, timezone
import http.client
import json
from pathlib import Path
import secrets
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.eu4_runtime_observer_r3 import compose_server, runtime_source_pins
from bridge.relation_state_service import RelationStateObserver
from bridge.war_state_service import WarStateObserver
from bridge.tag_command_backend import digest, require


def main():
    directory = ROOT/'work/reports/runtime-observer-20261015-r3'
    directory.mkdir(exist_ok=False)
    destination = directory/'live-http-verification.json'
    initial = runtime_source_pins()
    token = secrets.token_urlsafe(32)
    war = WarStateObserver(80340, '01dd5c075fcf8c26', store=directory/'captures/wars')
    relations = RelationStateObserver(80340, '01dd5c075fcf8c26', store=directory/'captures/relations')
    server = compose_server(war, relations, port=0, token=token)
    thread = threading.Thread(target=server.serve_forever, kwargs=dict(poll_interval=0.05))
    thread.start()
    cases = []
    requests = [
        ('GET', '/observer/v1/capabilities', True, 200, None),
        ('GET', '/observer/v1/relations/offer_alliance/FRA/POR', True, 200, 'current_relation_observed'),
        ('GET', '/observer/v1/relations/offer_alliance/POR/FRA', True, 200, 'current_relation_observed'),
        ('GET', '/observer/v1/relations/royal_marriage/ORL/BRI', True, 200, 'current_relation_observed'),
        ('GET', '/observer/v1/relations/guarantee/FRA/SAV', True, 200, 'current_relation_observed'),
        ('GET', '/observer/v1/relations/guarantee/SAV/FRA', True, 200, 'reverse_relation_observed'),
        ('GET', '/observer/v1/relations/offer_alliance/FRA/ENG', True, 200, 'pair_absent_observed'),
        ('GET', '/observer/v1/wars/ENG/AMG', True, 200, 'opponents'),
        ('GET', '/observer/v1/wars/FRA/ENG', True, 200, 'not_currently_opponents'),
        ('GET', '/observer/v1/relations/guarantee/FRA/SAV', False, 403, None),
        ('POST', '/observer/v1/relations/guarantee/FRA/SAV', True, 405, None),
        ('GET', '/observer/v1/effects/not-configured', True, 404, None),
        ('GET', '/observer/v1/relations/guarantee/FRA/SAV?retry=1', True, 422, 'unknown')]
    try:
        for method, path, authorized, expected_code, state in requests:
            client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=15)
            try:
                client.request(method, path, headers={'Authorization': 'Bearer '+token} if authorized else {})
                response = client.getresponse()
                raw = response.read()
                require(response.status == expected_code and len(raw) <= 256*1024
                    and response.getheader('Cache-Control') == 'no-store', 'HTTP contract differs')
                value = json.loads(raw)
                if path == '/observer/v1/capabilities':
                    require(value['profiles'] == [] and not value['current_state_is_request_completion']
                        and len(value['current_indexed_relations']['actions']) == 3,
                        'Sessionless capability declaration differs')
                if state is not None:
                    observed = value.get('pair_state', value.get('status'))
                    require(observed == state, 'Observed relation/war/error state differs')
                    if expected_code == 200:
                        require(value['two_pass_equal'] is True and not value['runtime_effect_verified'],
                            'Current state was upgraded to a new API effect')
                        record = value['record']
                        full = Path(record['path']).read_bytes()
                        require(len(full) == record['bytes'] and digest(full) == record['sha256'],
                            'Complete capture record differs')
                        if state == 'reverse_relation_observed':
                            require(value['requested_direction_matches'] is False, 'Reverse guarantee was treated as forward')
                    else:
                        require(value['automatic_command_retry'] is False, 'Invalid query became a retry instruction')
                cases.append(dict(method=method, path=path, authorized=authorized,
                    http_status=response.status, response_bytes=len(raw), response=value))
            finally:
                client.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
    require(not thread.is_alive() and server.socket.fileno() == -1, 'Server remains active')
    require(runtime_source_pins() == initial, 'Composition source changed during real HTTP verification')
    result = dict(schema='EU4-RUNTIME-COMPOSED-LIVE-HTTP/3',
        verified_utc=datetime.now(timezone.utc).isoformat(), pid=80340, creation='01dd5c075fcf8c26',
        source_pins=initial, cases=cases, listener_closed=True, server_thread_joined=True,
        native_calls=0, memory_written=False, requests_published=0, saves_written=0, reloads=0,
        new_API_effect_tested=False, exact_external_request_id_causality_verified=False,
        composed_factory='tools.eu4_runtime_observer_r3.compose_server',
        public_entry_process_launched=False,
        new_composition_tests=dict(count=13, passed=True, execution_seconds=0.633,
            evidence='Root tool execution before this live acceptance; not rerun here'),
        producer=dict(path=Path(__file__).relative_to(ROOT).as_posix(), sha256=digest(Path(__file__).read_bytes())))
    with destination.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(dict(output=str(destination), sha256=digest(destination.read_bytes()), source_pins=len(initial),
        cases=[dict(method=x['method'], path=x['path'], http_status=x['http_status'],
            state=x['response'].get('pair_state', x['response'].get('status')),
            duration_ms=x['response'].get('duration_ms')) for x in cases],
        listener_closed=True, server_thread_joined=True)))


if __name__ == '__main__':
    main()
