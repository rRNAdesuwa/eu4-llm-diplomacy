"""Compile the TAG command host with bounded offline tests; never injects it."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import struct

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "bridge/native/tag_command_1375"


def pin(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", default="build-1")
    args = parser.parse_args()
    assert args.attempt.replace("-", "").isalnum() and args.attempt.isascii()
    output = HERE / args.attempt
    output.mkdir(exist_ok=False)
    paths = [p for p in (HERE / "src").rglob("*") if p.is_file()]
    paths += [HERE / "build_test.cmd", HERE / "origin-pins.json", Path(__file__).resolve(),
              ROOT / "tools/prepare_tag_command_bridge.py"]
    sources = {p.relative_to(ROOT).as_posix(): pin(p) for p in paths}
    helper = ROOT / "work/candidates/v21-core-pair-nosend-1375/validate.py"
    spec = importlib.util.spec_from_file_location("_tag_command_bounded_build", helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = ROOT
    module.HERE = HERE
    build = module.run_build(output)
    sources_same = all(pin(ROOT / name) == expected for name, expected in sources.items())
    test = output / "build/test.stdout"
    passed = build["exit_code"] == 0 and sources_same
    validation = {"passed": passed, "build": build, "sources_same": sources_same,
                  "tests": test.read_text() if test.exists() else "", "game_accessed": False}
    validation_path = output / "validation.json"
    validation_path.write_text(json.dumps(validation, indent=2)+"\n")
    if not passed:
        print(json.dumps(validation))
        return 1
    dll = output / "build/eu4_tag_command_1375_v30.dll"
    raw = dll.read_bytes()
    nt = struct.unpack_from("<I", raw, 60)[0]
    assert raw[nt:nt+4] == b"PE\0\0"
    manifest = {
        "schema": "EU4TAGBUILD/1", "purpose": "tag_command_1375_v30", "DLL": dll.name,
        "dll": pin(dll), "PE_timestamp": struct.unpack_from("<I", raw, nt+8)[0],
        "SizeOfImage": struct.unpack_from("<I", raw, nt+80)[0],
        "game_sha256": "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a",
        "source_pins": sources, "validation": pin(validation_path),
        "experimental": True, "arbitrary_actor_runtime_verified": False,
        "production_ready": False, "no_send": False,
    }
    manifest_path = dll.parent / "build.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n")
    print(json.dumps({"passed": True, "build": build, "tests": validation["tests"],
                      "manifest": str(manifest_path), "manifest_sha256": pin(manifest_path)["sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
