"""Archive the accepted R64 force-query source and immutable evidence links."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "work/runtime/r64-python-docs-delivery-20261019-001"
BUILD = "work/runtime/diplomacy-query-20261019-r64-forces-a/build-manifest.json"
TESTS = "work/runtime/r64-final-python-unit-20261019-001/report.json"
QUERIES = [
    "work/runtime/r64-force-query-batch-20261019-001/report.json",
    "work/runtime/r64-force-query-milan-20261019-002/report.json",
]
GROUPS = "work/runtime/r64-force-save-groups-20261019-001/report.json"
SOURCES = [
    "bridge/diplomacy.py", "bridge/diplomacy_catalog.py", "bridge/declarewar_forces.py",
    "bridge/tests/test_declarewar_forces.py",
    "bridge/tests/test_declare_war_forces_integration.py",
    "bridge/tests/test_declare_war_forces_r64_real.py",
    "bridge/tests/fixtures/declare_war_r64_forces_real.json",
    "work/probe_r64_force_terms.py", "work/inspect_r64_force_save.py",
    "work/prepare_r64_force_scene.py", "work/run_declarewar_force_queries.py",
    "work/verify_r64_force_save_groups.py", "work/finalize_r64_force_delivery.py",
    "docs/history/R64宣战双方兵力与后备人力.md", "docs/宣战接口与运行验收.md",
    "docs/外交能力矩阵.md", "docs/外交系统说明.md", "docs/外交开发推进复盘.md",
    "docs/外交运行工作流.md", "PLAN.md", "HANDOFF.md",
    "work/临时prompt/外交系统开发goal.md",
]


def read(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8-sig"))


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            value.update(block)
    return value.hexdigest()


def main() -> int:
    if OUTPUT.exists():
        raise FileExistsError("R64_DELIVERY_ALREADY_EXISTS")
    build, tests, groups = read(BUILD), read(TESTS), read(GROUPS)
    queries = [read(path) for path in QUERIES]
    if any(report["status"] != "passed" for report in [tests, groups, *queries]):
        raise ValueError("R64_REQUIRED_REPORT_FAILED")
    mismatches = [source["name"] for source in build["sources"]
                  if digest(ROOT / "work/native" / source["name"]) != source["sha256"]]
    if mismatches:
        raise ValueError(f"INSTALLED_NATIVE_SOURCE_CHANGED: {mismatches}")
    scene = read("work/runtime/r64-force-scene-20261019-001/report.json")
    progress = {
        "status": "r64_force_query_runtime_accepted", "goal_status": "active",
        "common_diplomatic_execution_paths": "19/19", "common_peace_execution_paths": "19/19",
        "pid": 36144, "session_id": "36144-1dd5fb060362044",
        "date": "1455.9.10", "date_raw": 56551848, "player": "POR",
        "native_build_manifest": BUILD, "native_source_count": len(build["sources"]),
        "native_dll_sha256": build["dll_sha256"], "query_runtime_verified": True,
        "query_reports": QUERIES, "query_case_count": sum(len(q["cases"]) for q in queries),
        "query_check_count": sum(q["summary"]["check_count"] for q in queries),
        "query_scopes_complete": all(c["public_result"]["forces"]["complete"]
                                     for q in queries for c in q["cases"]),
        "save_fields_report": GROUPS, "save_countries": len(groups["country_union"]),
        "save_case_sides": groups["case_side_count"],
        "save_side_checks": [groups["case_side_checks_passed"], groups["case_side_checks_total"]],
        "save_global_checks": [groups["checks_passed"], groups["checks_total"]],
        "unit_definition_proof": "work/runtime/r64-force-unit-definition-20261019-001/report.json",
        "scene": scene["destination"], "scene_sha256": scene["destination_sha256"],
        "tests_report": TESTS, "passed_tests": tests["passed_tests"],
        "passed_subtests": tests["passed_subtests"],
        "delivery_manifest": str(OUTPUT.relative_to(ROOT) / "manifest.json"),
        "execution_in_this_batch": 0, "date_advanced": False,
        "new_save_requested": False, "dedicated_reload_test": False,
        "execution_evidence_reused": "work/runtime/r63-participants-execution-20261019-001/report.json",
        "next": ["structured_justified_peace_terms", "peace_ae_oe_adm_dip_coalition_preview",
                 "remaining_phases", "fair_information", "persistent_model_loop"],
    }
    OUTPUT.mkdir(parents=True)
    files = []
    for relative in SOURCES:
        source, target = ROOT / relative, OUTPUT / "source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        files.append({"path": relative, "sha256": digest(source), "bytes": source.stat().st_size})
    manifest = {"status": "archived", "stage": "R64", "progress": progress,
                "native_sources_verified_against_installed_build": True,
                "sources": files}
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "work/runtime/r64-progress.json").write_text(json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "archived", "source_count": len(files),
                      "native_source_count": len(build["sources"]), "progress": progress}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
