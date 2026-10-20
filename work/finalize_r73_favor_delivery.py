"""Archive the R73 runtime evidence and the matching Python source batch."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "work/runtime"
OUTPUT = RUNTIME / "r73-favor-delivery-20261020-001"
BUILD = RUNTIME / "diplomacy-observer-20261020-r73-trust-men-b"
BUSINESS = (
    "r73-trust-outbound-20261020-001", "r73-trust-inbound-reject-20261020-001",
    "r73-men-inbound-reject-20261020-001", "r73-men-outbound-20261020-002",
    "r73-trust-inbound-accept-20261020-001", "r73-men-inbound-accept-20261020-001",
)
DOCS = (
    "docs/人情外交接口.md", "docs/外交能力矩阵.md", "docs/外交系统说明.md",
    "docs/外交接口开发方案.md", "docs/外交开发推进复盘.md", "PLAN.md", "HANDOFF.md",
)
SOURCES = (
    "bridge/diplomacy.py", "bridge/diplomacy_catalog.py", "bridge/favor_resources.py",
    "work/run_r73_favor_queries.py", "work/reproject_r73_favor_queries.py",
    "work/run_r73_favor_execution.py", "work/run_r73_favor_inbound_fixture.py",
    "work/capture_r73_final_resources.py", "work/verify_r73_favor_save.py",
    "work/finalize_r73_favor_delivery.py",
)


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    for name in BUSINESS:
        report = read(RUNTIME / name / "report.json")
        assert report["status"] == "passed", name
        result = report["result"]
        proof = result["result"]
        assert result["submitted"] is True and result["game_outcome"] in ("accepted", "rejected")
        assert all(proof[key] is True for key in (
            "execution_verified", "request_binding_verified", "response_verified"))
        assert proof["favor_trade"]["complete"] and proof["favor_trade"]["verified"]
    checks = {
        "six_actual_response_paths": True,
        "final_save_fields": read(RUNTIME / "r73-final-save-fields-20261020-002.json")["status"] == "passed",
        "final_public_query_reprojection": read(RUNTIME / "r73-favor-queries-20261020-004/report.json")["status"] == "passed",
        "python_regression": read(RUNTIME / "r73-final-python-unit-20261020-001/report.json")["status"] == "passed",
    }
    assert all(checks.values()), checks
    OUTPUT.mkdir(exist_ok=False)
    selected = {ROOT / name for name in DOCS + SOURCES}
    contract_dir = RUNTIME / "r74-gift-influence-contract-20261020-001"
    selected.update(contract_dir / name for name in (
        "trust-save-contract.md", "trust-save-writer.txt", "trust-save-contract-scan.json"))
    selected.update((ROOT / "bridge/tests").glob("test_favor_resources*.py"))
    selected.update((ROOT / "bridge/tests").glob("test_r73*.py"))
    selected.update((ROOT / "bridge/tests/fixtures").glob("r73*.json"))
    for directory in RUNTIME.glob("r73-*"):
        if directory.is_dir() and directory != OUTPUT:
            selected.update(path for path in directory.rglob("*")
                            if path.is_file() and path.suffix in (".json", ".jsonl", ".txt", ".md", ".sqlite3"))
    selected.update(RUNTIME.glob("r73-*.json"))
    selected.update(BUILD / name for name in ("build-manifest.json", "installation.json"))
    save_reports = sorted(BUILD.glob("save-observer-report-*.json"))
    assert len(save_reports) == 1
    selected.add(save_reports[0])
    for directory in BUILD.glob("advance-context-*"):
        selected.add(directory / "report.json")
    entries = []
    for source in sorted(selected):
        if not source.is_file() or source.stat().st_size > 16 * 1024 * 1024:
            raise ValueError(f"Missing or oversized batch file: {source}")
        relative = source.relative_to(ROOT)
        destination = OUTPUT / "files" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        payload = destination.read_bytes()
        entries.append({"source": relative.as_posix(), "archive": destination.relative_to(OUTPUT).as_posix(),
                        "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
    installation = read(BUILD / "installation.json")
    build = read(BUILD / "build-manifest.json")
    manifest = {
        "status": "execution_and_persistence_passed", "checks": checks,
        "session_id": installation["session_id"], "dll_sha256": build["dll_sha256"],
        "native_build_manifest": str((BUILD / "build-manifest.json").relative_to(ROOT)),
        "native_source_count": len(build["sources"]),
        "native_source_policy": "Use the immutable source files retained beside the build manifest.",
        "save": read(save_reports[0])["save"], "files": entries,
        "pending": ["Trust/Men native acceptance preview and factors; combine with the next related native build."],
        "game_calls": 0, "business_replays": 0, "goal_status": "active",
    }
    write(OUTPUT / "manifest.json", manifest)
    write(RUNTIME / "r73-progress.json", {key: manifest[key] for key in
          ("status", "session_id", "dll_sha256", "checks", "pending", "goal_status")})
    print(json.dumps({"status": manifest["status"], "files": len(entries),
                      "manifest": str(OUTPUT / "manifest.json")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
