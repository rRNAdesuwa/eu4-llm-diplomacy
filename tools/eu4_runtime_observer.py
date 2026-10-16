"""One read-only entry point for diplomacy effects, replies and current wars."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    # Forward verbatim so the frozen specialist CLIs retain their exact flags.
    if len(sys.argv) > 1 and sys.argv[1] in ('effects', 'war'):
        operation = sys.argv.pop(1)
        if operation == 'effects':
            from tools.observe_diplomacy_live import main as specialist
        else:
            from tools.observe_war_runtime import main as specialist
        return specialist()
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='operation', required=True)
    sub.add_parser('catalog', help='File-only capabilities and checked source identities')
    for name in ('effects', 'war'):
        sub.add_parser(name, help='Forward remaining arguments; use '+name+' --help')
    serve = sub.add_parser('serve', help='Authenticated loopback HTTP; token from EU4_OBSERVER_TOKEN')
    serve.add_argument('--session-file', type=Path,
        help='Existing TAG identity for request-correlated effects; otherwise current-war routes only')
    serve.add_argument('--pid', type=int)
    serve.add_argument('--creation')
    serve.add_argument('--store', type=Path)
    serve.add_argument('--war-store', type=Path)
    serve.add_argument('--allow-tag-host', action='store_true')
    serve.add_argument('--port', type=int, default=8775)
    a = p.parse_args()
    from bridge.diplomacy_live_observer import LiveDiplomacyObserver, live_catalog, make_live_server
    from bridge.diplomacy_effect_observer import DEFAULT_STORE
    from bridge.war_state_service import WarStateObserver, make_war_server, source_pins, war_capabilities
    from bridge.tag_command_backend import decode, read, require, validate_identity
    if a.operation == 'catalog':
        value = live_catalog()
        value['war_state'] = war_capabilities()
        value['war_source_pins_verified'] = len(source_pins())
        value['game_process_accessed'] = False
        print(json.dumps(value, ensure_ascii=False))
        return 0
    effects = None
    if a.session_file is not None:
        identity = validate_identity(decode(read(a.session_file.resolve(), 32768))['identity'])
        require(a.pid is None or a.pid == identity['pid'], 'Session PID differs')
        require(a.creation is None or a.creation == identity['creation'], 'Session creation differs')
        a.pid, a.creation = identity['pid'], identity['creation']
        effects = LiveDiplomacyObserver(identity, store=a.store or DEFAULT_STORE,
            allow_tag_host=a.allow_tag_host)
    require(a.pid is not None and a.creation is not None, 'Supply an existing session or --pid and --creation')
    source_pins()
    war = WarStateObserver(a.pid, a.creation, store=a.war_store, allow_tag_host=a.allow_tag_host)
    server = make_war_server(war, port=a.port, token=os.environ.get('EU4_OBSERVER_TOKEN'),
        effect_observer=effects, base_factory=make_live_server if effects else None,
        capability_factory=live_catalog if effects else None)
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
