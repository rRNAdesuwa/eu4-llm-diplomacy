"""Bounded standalone deadline tests against build-6 sources; no game access."""
import argparse
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from bridge.tag_command_backend import TagCommandBackend, digest, encode, read, write_new


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--attempt", required=True)
    args = p.parse_args()
    assert args.attempt.isascii() and args.attempt.replace("-", "").isalnum()
    backend = TagCommandBackend()
    files = [HERE / "guard_boundary.cpp", HERE / "build_test.cmd", Path(__file__).resolve()]
    sources = {str(f.relative_to(ROOT)): digest(read(f, 65536)) for f in files}
    output = HERE / args.attempt
    output.mkdir(exist_ok=False)
    spec = importlib.util.spec_from_file_location("_bounded_ttl_build", ROOT / "work/candidates/v21-core-pair-nosend-1375/validate.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.ROOT, helper.HERE = ROOT, HERE
    build = helper.run_build(output)
    backend.verify()
    same = all(digest(read(ROOT / f, 65536)) == sha for f, sha in sources.items())
    test_output = output / "build/test.stdout"
    tests = read(test_output, 8192).decode("ascii") if test_output.exists() else ""
    passed = build["exit_code"] == 0 and same and "batch_ttl_boundary_cases=9 native_calls=0 game_access=0" in tests
    report = dict(passed=passed, build=build, tests=tests, source_pins=sources, sources_same=same,
                  compiled_manifest_sha256=backend.manifest_sha, game_accessed=False,
                  game_native_called=False, DLL_built=False)
    write_new(output / "validation.json", encode(report))
    print(__import__("json").dumps(report))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
