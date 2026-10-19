"""Public read-only EU4 observer entry with guaranteed service cleanup."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MANIFEST = ROOT/'bridge/eu4_observer_manifest_1375.json'


def source_pins():
    from bridge.tag_command_backend import GAME_SHA, read, decode, digest, require
    from tools.eu4_runtime_observer_r3 import runtime_source_pins
    raw = read(MANIFEST, 65536)
    data = decode(raw)
    require(data['schema'] == 'EU4-OBSERVER-ENTRY-MANIFEST/1'
        and data['game_sha256'] == GAME_SHA, 'Public observer identity differs')
    result = {}
    for relative, expected in data['source_pins'].items():
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts,
            'Public observer source path bound')
        value = read(ROOT/relative, 4*1024*1024)
        actual = dict(bytes=len(value), sha256=digest(value))
        require(actual == expected, 'Public observer source differs: '+relative)
        result[relative] = actual
    require({'tools/eu4_observer.py', 'bridge/tests/test_eu4_observer_entry.py',
        'bridge/runtime_observer_r3_manifest_1375.json'} <= set(result), 'Public observer graph incomplete')
    result.update(runtime_source_pins())
    result[MANIFEST.relative_to(ROOT).as_posix()] = dict(bytes=len(raw), sha256=digest(raw))
    return result


def main():
    source_pins()
    from tools.eu4_runtime_observer_r3 import main as specialist, compose_server
    if len(sys.argv) < 2 or sys.argv[1] != 'serve':
        return specialist()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['serve'])
    parser.add_argument('--session-file', type=Path)
    parser.add_argument('--pid', type=int)
    parser.add_argument('--creation')
    parser.add_argument('--store', type=Path)
    parser.add_argument('--war-store', type=Path)
    parser.add_argument('--relation-store', type=Path)
    parser.add_argument('--allow-tag-host', action='store_true')
    parser.add_argument('--port', type=int, default=8775)
    args = parser.parse_args()
    from bridge.diplomacy_effect_observer import DEFAULT_STORE
    from bridge.diplomacy_live_observer import LiveDiplomacyObserver
    from bridge.relation_state_service import RelationStateObserver
    from bridge.war_state_service import WarStateObserver
    from bridge.tag_command_backend import decode, read, require, validate_identity
    effects = None
    if args.session_file is not None:
        identity = validate_identity(decode(read(args.session_file.resolve(), 32768))['identity'])
        require(args.pid is None or args.pid == identity['pid'], 'Session PID differs')
        require(args.creation is None or args.creation == identity['creation'], 'Session creation differs')
        args.pid, args.creation = identity['pid'], identity['creation']
        effects = LiveDiplomacyObserver(identity, store=args.store or DEFAULT_STORE,
            allow_tag_host=args.allow_tag_host)
    require(args.pid is not None and args.creation is not None, 'Supply an existing session or --pid and --creation')
    war = WarStateObserver(args.pid, args.creation, store=args.war_store, allow_tag_host=args.allow_tag_host)
    relations = RelationStateObserver(args.pid, args.creation, store=args.relation_store,
        allow_tag_host=args.allow_tag_host)
    server = compose_server(war, relations, port=args.port,
        token=os.environ.get('EU4_OBSERVER_TOKEN'), effects=effects)
    try:
        print(f'Read-only EU4 observer: http://127.0.0.1:{server.server_port}/observer/v1/capabilities', flush=True)
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
