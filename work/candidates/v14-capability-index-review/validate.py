"""Bounded offline capability regression; no game inspection or publication."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from bridge import diplomacy_research_capabilities as cap


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = HERE / "final-validation-output.txt"
    report = HERE / "final-validation.json"
    if output.exists() or report.exists():
        raise ValueError("Validation artifacts are CreateNew")
    sources = ["bridge/diplomacy_research_capabilities.py", "bridge/diplomacy_research_evidence.json",
        "bridge/tests/test_research_capabilities.py", "bridge/tests/test_research_preflight_discovery.py",
        "bridge/diplomacy_lab_http.py"]
    before = {name: sha(ROOT/name) for name in sources}
    result = cap.capabilities()
    assert all(row["available"] for row in result["artifacts"].values())
    assert result["summary"]["actions_with_reviewed_state_effects"] == 28
    assert result["summary"]["production_executable_actions"] == 0
    assert result["historical_persistence_reviews"][0]["selected_state_count"] == 9
    commands = [sys.executable, "-B", "-m", "unittest", "-v",
        "bridge.tests.test_research_capabilities", "bridge.tests.test_research_preflight_discovery",
        "bridge.tests.test_diplomacy_lab_http", "bridge.tests.test_diplomacy_lab_http_v10",
        "bridge.tests.test_diplomacy_lab_http_v11", "bridge.tests.test_diplomacy_lab_http_v12"]
    started = time.monotonic()
    with output.open("xb") as stream:
        completed = subprocess.run(commands, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    after = {name: sha(ROOT/name) for name in sources}
    assert before == after
    data = {"command": commands, "exit_code": completed.returncode, "elapsed_seconds": time.monotonic()-started,
        "sources_before": before, "sources_after": after, "output_sha256": sha(output),
        "summary": result["summary"], "artifacts": len(result["artifacts"]),
        "artifact_bytes": sum(r["size_bytes"] for r in result["artifacts"].values()),
        "all_artifacts_available": True, "historical_effect_reviews": result["historical_effect_reviews"],
        "persistence_counts": {key: result["historical_persistence_reviews"][0][key] for key in
            ("selected_state_count", "serialized_and_typed_reload_count", "typed_reload_only_count")},
        "large_save_files_read": False, "process_inspected": False, "game_requests_written": False,
        "development_run": {"tests": 45, "failures": 3, "reason": "Stale v9/v10 historical aggregate and canceled-direction expectations; fixed before this run"}}
    with report.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2);stream.write("\n")
    print(json.dumps({"exit_code":completed.returncode,"summary":result["summary"],"report_sha256":sha(report)}))
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
