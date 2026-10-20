"""Archive the accepted R63 source and reference its immutable runtime evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "work/runtime/r63-python-docs-delivery-20261019-001"
BUILD = "work/runtime/diplomacy-query-20261019-r63-participants-b/build-manifest.json"
TESTS = "work/runtime/r63-final-python-unit-20261019-001/report.json"
QUERY = "work/runtime/r63-participants-query-batch-b-20261019-003/report.json"
EXECUTION = "work/runtime/r63-participants-execution-20261019-001/report.json"
SAVE_FIELDS = "work/runtime/r63-participants-save-fields-20261019-001/report.json"

SOURCES = [
    "bridge/diplomacy.py", "bridge/diplomacy_catalog.py",
    "bridge/declarewar_selection.py", "bridge/declarewar_participants.py",
    "bridge/declarewar_details.py", "bridge/native_text.py",
    "bridge/tests/test_declarewar_selection.py",
    "bridge/tests/test_declarewar_participants.py",
    "bridge/tests/test_declare_war_participants_integration.py",
    "bridge/tests/test_declare_war_participants_r63_real.py",
    "bridge/tests/test_declare_war_participants_r63_batch_b_real.py",
    "bridge/tests/test_declare_war_execution_r63_real.py",
    "bridge/tests/test_declare_war_tools.py",
    "bridge/tests/fixtures/declare_war_r63_participants_real.json",
    "bridge/tests/fixtures/declare_war_r63_participants_b_real.json",
    "bridge/tests/fixtures/declare_war_r63_execution_real.json",
    "work/native/test-declarewar-selection.cpp",
    "work/run_declarewar_participants_queries.py",
    "work/run_declarewar_participants_execution.py",
    "work/run_declare_war_execution.py", "work/prepare_r63_ally_scene.py",
    "work/inspect_r63_participant_save.py", "work/probe_r63_country_database.py",
    "work/finalize_r63_participant_delivery.py",
    "docs/history/R63宣战参战方案与因素.md",
    "docs/宣战接口与运行验收.md", "docs/外交能力矩阵.md",
    "docs/外交系统说明.md", "docs/外交开发推进复盘.md",
    "docs/外交运行工作流.md", "PLAN.md", "HANDOFF.md",
    "work/临时prompt/外交系统开发goal.md",
]


def read(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def main() -> int:
    if OUTPUT.exists():
        raise FileExistsError("R63_DELIVERY_ALREADY_EXISTS")
    build = read(BUILD)
    tests = read(TESTS)
    if tests["status"] != "passed" or read(QUERY)["status"] != "passed" \
            or read(EXECUTION)["status"] != "passed":
        raise RuntimeError("R63_REQUIRED_RUNTIME_REPORT_FAILED")
    source_mismatches = [item["name"] for item in build["sources"]
                         if digest(ROOT / "work/native" / item["name"]) != item["sha256"]]
    if source_mismatches:
        raise RuntimeError(f"INSTALLED_NATIVE_SOURCE_CHANGED: {source_mismatches}")
    progress = {
        "status": "r63_participant_runtime_accepted", "goal_status": "active",
        "common_diplomatic_execution_paths": "19/19", "common_peace_execution_paths": "19/19",
        "session_id": "40828-1dd5fa887f32179", "pid": 40828,
        "player": "POR", "date": "1455.9.10", "date_raw": 56551848,
        "query_cases_passed": 27, "execution_request": "r63_declare_BUR_SAV_HSA_001",
        "execution_report": EXECUTION, "query_report": QUERY,
        "save_fields_report": SAVE_FIELDS, "save_fields_passed": "14/14",
        "save_name": "llm_diplomacy_declarewar_SAV_HSA_20261019_r63.eu4",
        "save_sha256": "e03b9cfedd8b1400e31b6299af434a77d9dba226b997c64452da46e94555b251",
        "native_build_manifest": BUILD, "native_source_count": len(build["sources"]),
        "native_dll_sha256": build["dll_sha256"], "tests_report": TESTS,
        "passed_tests": tests["passed_tests"], "passed_subtests": tests["passed_subtests"],
        "delivery_manifest": str(OUTPUT.relative_to(ROOT) / "manifest.json"),
        "next": ["deployed_forces", "manpower", "structured_justified_peace_terms",
                 "peace_ae_oe_adm_dip_coalition_preview", "remaining_phases",
                 "fair_information", "persistent_model_loop"],
    }
    (ROOT / "work/runtime/r63-progress.json").write_text(
        json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUTPUT.mkdir(parents=True)
    entries = []
    for relative in SOURCES:
        source = ROOT / relative
        target = OUTPUT / "source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        entries.append({"path": relative, "bytes": source.stat().st_size,
                        "sha256": digest(target)})
    manifest = {
        "stage": "R63", "status": "accepted", "goal_status": "active",
        "files": entries, "file_count": len(entries),
        "source_bytes": sum(item["bytes"] for item in entries),
        "native_source_binding_verified": True, "native_build_manifest": BUILD,
        "native_dll_sha256": build["dll_sha256"],
        "evidence": {"query": QUERY, "execution": EXECUTION, "save_fields": SAVE_FIELDS,
                     "tests": TESTS, "progress": "work/runtime/r63-progress.json",
                     "advance": "work/runtime/r63-advance-reconciliation-20261019-001/report.json"},
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "accepted", "files": len(entries),
                      "native_sources": len(build["sources"]),
                      "manifest": str(OUTPUT / "manifest.json")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
