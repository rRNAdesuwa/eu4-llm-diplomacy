"""Build/check the file-only, fixed-build observer provenance manifest."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy_effect_observer import EVIDENCE_FILES, SOURCE_MANIFEST
from bridge.diplomacy_effect_profiles import profile_catalog
from bridge.tag_command_backend import DEFAULT_MANIFEST, GAME_SHA, digest, read, require


def build():
    names = set(EVIDENCE_FILES) | {
        "bridge/diplomacy_effect_observer.py", "bridge/diplomacy_effect_profiles.py",
        "bridge/diplomacy_observer_service.py", "tools/observe_diplomacy.py",
        "tools/build_effect_observer_manifest.py"}
    expected = {}
    for row in profile_catalog():
        for name, pin in row["source_pins"].items():
            simple = {k: pin[k] for k in ("bytes", "sha256")}
            require(name not in expected or expected[name] == simple, "Conflicting profile evidence")
            expected[name] = simple
            names.add(name)
    sources = {name: {"bytes": len(raw := read(ROOT/name, 2*1024*1024)), "sha256": digest(raw)}
               for name in sorted(names)}
    require(all(sources[name] == pin for name, pin in expected.items()), "Fixed profile evidence changed")
    return {"schema": "EU4DIPLOMACY-OBSERVER-MANIFEST/1", "game_sha256": GAME_SHA,
        "native_manifest_sha256": digest(read(DEFAULT_MANIFEST, 1024*1024)),
        "source_pins": sources, "read_only": True, "native_calls": 0,
        "all120_effect_profiles_complete": False, "atomic_snapshot_claimed": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    value = build()
    if args.check:
        require(json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8")) == value, "Observer manifest differs")
    else:
        with SOURCE_MANIFEST.open("x", encoding="utf-8") as f:
            json.dump(value, f, sort_keys=True, indent=2)
            f.write("\n")
    print(json.dumps({"source_pins": len(value["source_pins"]), "check": args.check,
        "manifest_sha256": digest(SOURCE_MANIFEST.read_bytes()), "game_accessed": False}))


if __name__ == "__main__":
    main()
