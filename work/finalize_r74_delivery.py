"""Freeze R74 sources, verified observations and both runtime build identities."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "work/runtime"
OUTPUT = RUNTIME / "r74-economic-war-delivery-20261020-001"
ECONOMIC = RUNTIME / "diplomacy-observer-20261020-r74-economic-war-d"
WAR = RUNTIME / "diplomacy-observer-20261020-r74-war-f"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    gates = {
        "gift_actual_execution": "r74-gift-execution-20261020-002/report.json",
        "influence_actual_execution": "r74-influence-execution-20261020-001/report.json",
        "economic_queries": "r74-economic-queries-20261020-005/report.json",
        "full_economic_public_projection": "r74-economic-queries-20261020-006/report.json",
        "gift_invalid_execution_reason": "r74-gift-invalid-20261020-001/report.json",
        "influence_invalid_execution_reason": "r74-influence-invalid-20261020-001/report.json",
        "favor_acceptance_and_factor_identity": "r74-favor-acceptance-final-20261020-001.json",
        "economic_persistence": "r74-economic-save-verify-20261020-002/report.json",
        "live_war_query_and_public_projection": "r74-live-war-queries-20261020-003/report.json",
        "war_save_sides_goal_and_control": "r74-live-war-save-verify-20261020-002.json",
        "python_regression": "r74-python-unit-20261020-005/report.json",
    }
    checks = {key: read(RUNTIME / path)["status"] == "passed" for key, path in gates.items()}
    for name in ("r74-gift-execution-20261020-002", "r74-influence-execution-20261020-001"):
        result = read(RUNTIME / name / "report.json")["result"]
        assert result["submitted"] and result["game_outcome"] == "executed", name
        assert all(result["result"][key] is True for key in (
            "execution_verified", "request_binding_verified")), name
    war_report = read(RUNTIME / gates["live_war_query_and_public_projection"])
    assert all(all(case["checks"].values()) for case in war_report["cases"])
    for case in war_report["cases"]:
        score = case["score"]
        expected = -400 if case["actor"] == "FRA" else 400
        assert score["goal"]["cumulative"]["raw"] == expected
        assert ("-0.40" if expected < 0 else "+0.40") in score["tooltip"]["text"]
    economic_build, war_build = read(ECONOMIC / "build-manifest.json"), read(WAR / "build-manifest.json")
    old = {row["name"]: row["sha256"] for row in economic_build["sources"]}
    new = {row["name"]: row["sha256"] for row in war_build["sources"]}
    changed = sorted(name for name in old.keys() | new.keys() if old.get(name) != new.get(name))
    checks["final_build_delta_is_war_score_direction_only"] = changed == ["live-war-score-query.inc"]
    assert all(checks.values()), checks
    OUTPUT.mkdir(exist_ok=False)
    selected = set((ROOT / "bridge").glob("*.py"))
    selected.update((ROOT / "bridge/tests").glob("*.py"))
    selected.update(path for path in (ROOT / "bridge/tests/fixtures").rglob("*") if path.is_file())
    selected.update(ROOT / name for name in ("README.md", "PLAN.md", "HANDOFF.md"))
    selected.update(path for path in (ROOT / "docs").glob("*.md")
                    if any(word in path.name for word in ("外交", "议和", "人情", "赠送", "战争分")))
    selected.update(ROOT / "work" / name for name in (
        "run_r74_economic_queries.py", "run_r74_economic_execution.py", "reproject_r74_economic_queries.py",
        "run_r74_live_war_queries.py", "verify_r74_economic_save.py",
        "verify_r74_live_war_save.py", "finalize_r74_delivery.py"))
    for directory in RUNTIME.glob("r74-*"):
        if directory.is_dir() and directory != OUTPUT:
            selected.update(path for path in directory.rglob("*") if path.is_file()
                            and path.suffix in (".json", ".jsonl", ".txt", ".md", ".c", ".sqlite3", ".log"))
    selected.update(RUNTIME.glob("r74-*.json"))
    for build_directory in (ECONOMIC, WAR):
        selected.update(build_directory / name for name in ("build-manifest.json", "installation.json"))
        selected.add(Path(read(build_directory / "build-manifest.json")["dll"]))
        selected.update(build_directory.glob("save-observer-report-*.json"))
    selected.update(WAR / row["name"] for row in war_build["sources"])
    entries = []
    for source in sorted(selected):
        assert source.is_file() and source.stat().st_size <= 16 * 1024 * 1024, source
        relative = source.relative_to(ROOT)
        destination = OUTPUT / "files" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        with destination.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        entries.append({"source": relative.as_posix(), "archive": destination.relative_to(OUTPUT).as_posix(),
                        "size": destination.stat().st_size, "sha256": digest})
    save_reports = list(ECONOMIC.glob("save-observer-report-*.json"))
    assert len(save_reports) == 1
    manifest = {
        "status": "runtime_acceptance_completed", "checks": checks, "evidence": gates,
        "catalog": {"actions": 47, "diplomatic_actions": 28, "peace_terms": 19},
        "original_priority_scope": {"diplomatic_actions": 19, "peace_terms": 19,
                                    "evidence_policy": "Retain the previously completed R61-R73 delivery records."},
        "economic_runtime": {"build_manifest": str((ECONOMIC / "build-manifest.json").relative_to(ROOT)),
                             "dll_sha256": economic_build["dll_sha256"],
                             "session_id": read(ECONOMIC / "installation.json")["session_id"]},
        "final_war_runtime": {"build_manifest": str((WAR / "build-manifest.json").relative_to(ROOT)),
                              "dll_sha256": war_build["dll_sha256"],
                              "session_id": read(WAR / "installation.json")["session_id"]},
        "native_source_delta": changed, "native_source_count": len(war_build["sources"]),
        "save": read(save_reports[0])["save"], "files": entries,
        "pending_required_items": [], "game_calls": 0, "business_replays": 0,
        "dedicated_save_reload_acceptance": False,
        "goal_completion_basis": "Updated goal items 5-7 accepted; item 8 permits ending this target.",
    }
    write(OUTPUT / "manifest.json", manifest)
    write(RUNTIME / "r74-progress.json", {key: manifest[key] for key in (
        "status", "checks", "pending_required_items", "goal_completion_basis")})
    print(json.dumps({"status": manifest["status"], "files": len(entries),
                      "manifest": str(OUTPUT / "manifest.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
