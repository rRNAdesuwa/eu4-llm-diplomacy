"""Unified read-only effects, replies, current relations and current wars."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MANIFEST = ROOT/'bridge/runtime_observer_r3_manifest_1375.json'


def runtime_source_pins():
    from bridge.tag_command_backend import GAME_SHA, read, decode, digest, require
    from tools.eu4_runtime_observer_r2 import runtime_source_pins as r2_pins
    from bridge.relation_state_service import source_pins as relation_pins
    raw = read(MANIFEST, 65536)
    manifest = decode(raw)
    require(manifest['schema'] == 'EU4-RUNTIME-OBSERVER-MANIFEST/3'
        and manifest['game_sha256'] == GAME_SHA, 'Unified R3 identity differs')
    checked = {}
    for relative, expected in manifest['source_pins'].items():
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts,
            'Unified R3 source path bound')
        data = read(ROOT/relative, 4*1024*1024)
        actual = dict(bytes=len(data), sha256=digest(data))
        require(actual == expected, 'Unified R3 source differs: '+relative)
        checked[relative] = actual
    require({'tools/eu4_runtime_observer_r3.py', 'bridge/tests/test_runtime_observer_r3.py',
        'bridge/runtime_observer_manifest_1375.json', 'bridge/relation_state_service_manifest_1375.json'}
        <= set(checked), 'Unified R3 source graph incomplete')
    checked.update(r2_pins())
    checked.update(relation_pins())
    checked[MANIFEST.relative_to(ROOT).as_posix()] = dict(bytes=len(raw), sha256=digest(raw))
    return checked


def catalog(*, effects_enabled=True):
    from bridge.diplomacy_live_observer import live_catalog
    from bridge.relation_state_service import relation_capabilities
    from bridge.war_state_service import war_capabilities
    value = live_catalog() if effects_enabled else dict(profiles=[],
        all120_effect_profiles_complete=False, read_only=True, native_calls=0,
        requests_published=0, saves_written=0)
    value['schema'] = 'EU4-RUNTIME-OBSERVER-CATALOG/3'
    value['current_indexed_relations'] = relation_capabilities()
    value['war_state'] = war_capabilities()
    value['current_state_is_request_completion'] = False
    return value


class CheckedRoutes:
    """Check this composition's graph before and after delegated reads."""
    def __init__(self, observer):
        self.observer = observer

    def _read(self, method, *args):
        from bridge.tag_command_backend import require
        initial = runtime_source_pins()
        value = getattr(self.observer, method)(*args)
        require(runtime_source_pins() == initial, 'Unified sources changed during read')
        return value

    def observe(self, request_id):
        return self._read('observe', request_id)

    def observe_pair(self, *args):
        return self._read('observe_pair', *args)


def compose_server(war, relations, *, port, token, effects=None):
    from bridge.diplomacy_live_observer import make_live_server
    from bridge.relation_state_service import make_relation_server
    from bridge.war_state_service import make_war_server

    def capabilities():
        runtime_source_pins()
        return catalog(effects_enabled=effects is not None)

    base = make_war_server(CheckedRoutes(war), port=port, token=token,
        effect_observer=CheckedRoutes(effects) if effects is not None else None,
        base_factory=make_live_server if effects is not None else None,
        capability_factory=capabilities)
    try:
        server = make_relation_server(CheckedRoutes(relations), base)
        original = server.RequestHandlerClass

        class Handler(original):
            def send_json(self, code, value):
                # Request validation and failed host reads cannot be mistaken
                # for the native engine rejecting a previously sent action.
                if code in (409, 422) and isinstance(value, dict):
                    value = dict(value, status='unknown', automatic_command_retry=False,
                        native_calls=0, requests_published=0)
                return super().send_json(code, value)

        server.RequestHandlerClass = Handler
        return server
    except BaseException:
        base.server_close()
        raise


def main():
    runtime_source_pins()
    if len(sys.argv) > 1 and sys.argv[1] in ('effects', 'war'):
        from tools.eu4_runtime_observer_r2 import main as r2_main
        return r2_main()
    if len(sys.argv) > 1 and sys.argv[1] == 'relations':
        sys.argv.pop(1)
        from tools.observe_relation_runtime import main as relation_main
        return relation_main()
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='operation', required=True)
    sub.add_parser('catalog', help='File-only capability/source inspection')
    for name in ('effects', 'war', 'relations'):
        sub.add_parser(name, help='Forward remaining arguments; use '+name+' --help')
    serve = sub.add_parser('serve')
    serve.add_argument('--session-file', type=Path)
    serve.add_argument('--pid', type=int)
    serve.add_argument('--creation')
    serve.add_argument('--store', type=Path)
    serve.add_argument('--war-store', type=Path)
    serve.add_argument('--relation-store', type=Path)
    serve.add_argument('--allow-tag-host', action='store_true')
    serve.add_argument('--port', type=int, default=8775)
    a = p.parse_args()
    if a.operation == 'catalog':
        value = catalog()
        value['game_process_accessed'] = False
        print(json.dumps(value, ensure_ascii=False))
        return 0
    from bridge.diplomacy_effect_observer import DEFAULT_STORE
    from bridge.diplomacy_live_observer import LiveDiplomacyObserver
    from bridge.relation_state_service import RelationStateObserver
    from bridge.war_state_service import WarStateObserver
    from bridge.tag_command_backend import decode, read, require, validate_identity
    effects = None
    if a.session_file is not None:
        identity = validate_identity(decode(read(a.session_file.resolve(), 32768))['identity'])
        require(a.pid is None or a.pid == identity['pid'], 'Session PID differs')
        require(a.creation is None or a.creation == identity['creation'], 'Session creation differs')
        a.pid, a.creation = identity['pid'], identity['creation']
        effects = LiveDiplomacyObserver(identity, store=a.store or DEFAULT_STORE,
            allow_tag_host=a.allow_tag_host)
    require(a.pid is not None and a.creation is not None, 'Supply an existing session or --pid and --creation')
    war = WarStateObserver(a.pid, a.creation, store=a.war_store, allow_tag_host=a.allow_tag_host)
    relations = RelationStateObserver(a.pid, a.creation, store=a.relation_store,
        allow_tag_host=a.allow_tag_host)
    server = compose_server(war, relations, port=a.port,
        token=os.environ.get('EU4_OBSERVER_TOKEN'), effects=effects)
    print(f'Read-only runtime observer: http://127.0.0.1:{server.server_port}/observer/v1/capabilities', flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(json.dumps(dict(status='unknown', error=str(exc), automatic_command_retry=False,
            native_calls=0, requests_published=0)), file=sys.stderr)
        raise SystemExit(2)
