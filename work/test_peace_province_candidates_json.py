"""Compile the native province serializer fixture and parse its three JSON cases."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work" / "native" / "test-peace-province-candidates-json.cpp"


def main() -> int:
    compiler = shutil.which("g++")
    if compiler is None:
        raise SystemExit("g++ is required for the native JSON roundtrip fixture")
    with tempfile.TemporaryDirectory(prefix="peace-province-json-") as directory:
        executable = Path(directory) / "peace-province-json.exe"
        subprocess.run([
            compiler, "-std=c++17", "-O0", str(SOURCE), "-o", str(executable),
        ], cwd=ROOT, check=True)
        completed = subprocess.run(
            [str(executable)], cwd=ROOT, check=True, text=True,
            capture_output=True,
        )
    cases: dict[str, dict] = {}
    for line in completed.stdout.splitlines():
        name, separator, payload = line.partition("\t")
        if not separator:
            raise AssertionError(f"malformed fixture output: {line!r}")
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise AssertionError(f"fixture case is not an object: {name}")
        if name in cases:
            raise AssertionError(f"duplicate fixture case: {name}")
        cases[name] = value

    if set(cases) != {"empty", "missing", "selected"}:
        raise AssertionError(f"unexpected fixture cases: {sorted(cases)}")

    empty = cases["empty"]
    assert empty["requested_province_ids"] == []
    assert empty["selected_province_ids"] == []
    assert empty["requested_beneficiary"] is None
    assert empty["selected_beneficiary"] is None

    missing = cases["missing"]
    assert missing["requested_province_ids"] == [2147483647]
    assert missing["selected_province_ids"] == []
    assert missing["requested_beneficiary"] == "FRA"
    assert missing["reason_code"] == "NATIVE_PEACE_PROVINCE_CANDIDATE_ABSENT"

    selected = cases["selected"]
    assert selected["requested_province_ids"] == [177]
    assert selected["selected_province_ids"] == [177]
    assert selected["requested_beneficiary"] == "FRA"
    assert selected["selected_beneficiary"] == "FRA"
    assert selected["selection_delta_raw"] == 5
    print("peace_province_json_roundtrip:passed cases=3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
