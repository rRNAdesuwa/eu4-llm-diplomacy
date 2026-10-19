"""Seal the public entry after review, preserving all older source versions."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ('tools/eu4_observer.py', 'bridge/tests/test_eu4_observer_entry.py',
    'tools/build_eu4_observer_manifest.py', 'bridge/runtime_observer_r3_manifest_1375.json')


def main():
    pins = {}
    for name in FILES:
        raw = (ROOT/name).read_bytes()
        pins[name] = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    value = dict(schema='EU4-OBSERVER-ENTRY-MANIFEST/1',
        game_sha256='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a',
        read_only=True, native_calls=0, source_pins=pins)
    dest = ROOT/'bridge/eu4_observer_manifest_1375.json'
    with dest.open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2)
    print(json.dumps(dict(path=str(dest), bytes=dest.stat().st_size,
        sha256=hashlib.sha256(dest.read_bytes()).hexdigest())))


if __name__ == '__main__':
    main()
