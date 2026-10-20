"""Verify the API and fresh native execution preserve an ally refusal reason."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from work.local_config import game_exe
from work.observer_runtime_ready import wait_runtime_ready
from work.run_peace_consequence_queries import _output_paths, _write_json, _copy_bounded_slice


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output, evidence = _output_paths(args.output)
    session = ObserverSession(args.installation.resolve(strict=True), game_exe())
    source = json.loads(args.queries.read_text(encoding="utf-8"))
    assert source["session_id"] == session.session_id and source["status"] == "passed"
    case = next(item for item in source["cases"] if item["name"] == "ally_193_SAV")
    parameters = case["parameters"]
    report = {"status": "running", "session_id": session.session_id,
              "source_queries": str(args.queries), "parameters": parameters,
              "business_submission": False, "checks": {}}
    try:
        date = wait_runtime_ready(session, timeout=25, restore_minimized=True)["date_raw"]
        token = output.parent.name[-3:]
        with DurableJournal(evidence / "journal.sqlite3", session.experiment_id,
                            session.session_id) as journal:
            api = DiplomacyTools(journal, session)
            inspection = api.inspect_diplomatic_action("cede_province", "FRA", "BUR", parameters=parameters)
            assert inspection["legality"]["status"] == "unavailable", "ALLY_REQUEST_NOT_PROHIBITED"
            request = "r67_api_ally_unwilling_" + token
            result = api.execute_diplomatic_action(request, "cede_province", "FRA", "BUR", parameters=parameters)
            reread = api.get_diplomatic_result(request)
            _write_json(evidence / "api-result.json", result)
            log = session.directory / "control-probe.jsonl"
            start = log.stat().st_size
            native = session.submit_peace("r67_native_ally_unwilling_" + token,
                "FRA", "BUR", "initiate", date, "cede_province", parameters)
            _write_json(evidence / "native-result.json", native)
            report["native_slice"] = _copy_bounded_slice(log, start, evidence / "native.jsonl")
            api_reasons = result.get("result", {}).get("legality_reasons", [])
            native_text = native.get("reason", {}).get("text", "")
            report.update(api_reasons=api_reasons, native_reason=native.get("reason"),
                          native_reason_code=native.get("reason_code"))
            report["business_submission"] = result.get("submitted") is True or native.get("submitted") is True
            report["checks"] = {
                "api_ally_unwilling_reason": any("不想要" in item.get("text", "") for item in api_reasons),
                "native_ally_unwilling_reason": "不想要" in native_text,
                "native_coring_reason": "核心化" in native_text,
                "result_reread_equal": result == reread,
                "native_request_binding": native.get("binding_complete") is True,
                "native_rule_source": native.get("reason", {}).get("source") == "native_rule",
                "no_business_submission": not report["business_submission"]}
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except Exception as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
    _write_json(output, report)
    print(json.dumps({"status": report["status"], "report": str(output), "checks": report["checks"]}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
