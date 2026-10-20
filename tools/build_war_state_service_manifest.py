"""Seal only the new war host; frozen decoder/dependency manifests stay intact."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ('bridge/war_state_service.py', 'tools/observe_war_runtime.py',
    'tools/eu4_runtime_observer.py', 'bridge/tests/test_war_state_service.py',
    'tools/build_war_state_service_manifest.py',
    'bridge/diplomacy_live_observer_manifest_1375.json',
    'work/reports/war-peace-api-20261015-r7-r2/observer/manifest.json')


def main():
    pins = {}
    for name in FILES:
        raw = (ROOT/name).read_bytes()
        pins[name] = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    value = dict(schema='EU4-WAR-STATE-HOST-MANIFEST/1',
        game_sha256='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a',
        read_only=True, native_calls=0, source_pins=pins)
    dest = ROOT/'bridge/war_state_service_manifest_1375.json'
    with dest.open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2)
    print(json.dumps(dict(path=str(dest), bytes=dest.stat().st_size,
        sha256=hashlib.sha256(dest.read_bytes()).hexdigest())))


if __name__ == '__main__':
    main()
