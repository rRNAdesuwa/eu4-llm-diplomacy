"""Checked unified runtime entry point; preserve the frozen first wrapper."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MANIFEST = ROOT/'bridge/runtime_observer_manifest_1375.json'


def runtime_source_pins():
    from bridge.tag_command_backend import GAME_SHA, read, decode, digest, require
    from bridge.war_state_service import source_pins
    from bridge.diplomacy_live_observer import live_source_pins
    raw = read(MANIFEST, 65536)
    manifest = decode(raw)
    require(manifest['schema'] == 'EU4-RUNTIME-OBSERVER-MANIFEST/2'
        and manifest['game_sha256'] == GAME_SHA, 'Unified runtime identity differs')
    checked = {}
    for relative, expected in manifest['source_pins'].items():
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts,
            'Unified source path bound')
        data = read(ROOT/relative, 4*1024*1024)
        actual = dict(bytes=len(data), sha256=digest(data))
        require(actual == expected, 'Unified runtime source differs: '+relative)
        checked[relative] = actual
    require({'tools/eu4_runtime_observer_r2.py', 'bridge/tests/test_runtime_observer_guard.py',
        'bridge/war_state_service_manifest_1375.json', 'bridge/diplomacy_live_observer_manifest_1375.json'}
        <= set(checked), 'Unified source graph incomplete')
    checked.update(source_pins())
    checked.update(live_source_pins())
    checked[MANIFEST.relative_to(ROOT).as_posix()] = dict(bytes=len(raw), sha256=digest(raw))
    return checked


def main():
    # This must precede even specialist forwarding or argument mutation.
    runtime_source_pins()
    from tools.eu4_runtime_observer import main as frozen_main
    return frozen_main()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(json.dumps(dict(status='unknown', error=str(exc), automatic_command_retry=False,
            native_calls=0, requests_published=0)), file=sys.stderr)
        raise SystemExit(2)
