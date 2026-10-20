"""R68 staged runtime acceptance; each stage writes evidence before proceeding."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from work.local_config import game_exe
from work.observer_runtime_ready import wait_runtime_ready
from work.run_alliance_inbound_response import control_snapshot
from work.run_peace_consequence_queries import _write_json, _copy_bounded_slice
from work.run_peace_empty_offer_queries import _single_discovered_war_id
from work.validate_alliance_queries import PROBE_SPECS, _run_probe

NO_CB = {"casus_belli": "no_casus_belli", "war_goal": {
    "province_id": -1, "beneficiary": "FRA"}, "call_allies": [],
    "promise_land_to": [], "co_belligerents": []}
CASES = (
    ("offer_alliance", "LIT"), ("dissolve_alliance", "SAV"),
    ("improve_relations", "MOR"), ("stop_improving_relations", "MLO"),
    ("offer_royal_marriage", "SAV"), ("break_royal_ties", "SAV"),
    ("build_spy_network", "MOR"), ("stop_building_spy_network", "BUR"),
    ("proclaim_guarantee", "MOR"), ("revoke_guarantee", "MOR"),
    ("ask_military_access", "MLO"), ("cancel_military_access", "MLO"),
    ("send_insult", "MOR"), ("scornful_insult", "MOR"),
    ("set_rival", "MOR"), ("remove_rival", "ENG"),
    ("offer_vassalization", "MLO"), ("cancel_vassalization", "ORL"),
    ("declare_war", "MOR"))


def brief(value):
    return {"status": value.get("status"), "submitted": value.get("submitted"),
            "reason_code": value.get("reason_code"), "resources": value.get("resources"),
            "legality": value.get("legality"), "result": value.get("result")}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--installation", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--stage", choices=("baseline", "occupy", "zero", "recall", "recovered"), required=True)
    args = p.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    evidence = root / args.stage
    evidence.mkdir(exist_ok=False)
    session = ObserverSession(args.installation.resolve(strict=True), game_exe())
    report = {"status": "running", "session_id": session.session_id,
              "installation": str(args.installation.resolve()), "stage": args.stage,
              "checks": {}, "cases": []}
    log = session.directory / "control-probe.jsonl"
    token = root.name[-3:]
    start = log.stat().st_size
    def save():
        _write_json(evidence / "report.json", report)
    save()
    try:
        health = wait_runtime_ready(session, timeout=25, restore_minimized=True)
        report["health"] = health
        control = control_snapshot(int(session.record["pid"]), evidence / "control.json")
        report["control"] = control
        assert health.get("status") == "ready" and control.get("paused_flag") == 1 and control.get("player_slot") == 189, "PAUSED_POR_READY_REQUIRED"
        date = control["date_raw"]
        with DurableJournal(root / "journal.sqlite3", session.experiment_id, session.session_id,
                            global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            def inspect(name, action, recipient, parameters=None):
                offset = log.stat().st_size
                value = api.inspect_diplomatic_action(action, "FRA", recipient, parameters=parameters or {})
                _write_json(evidence / (name + "-inspection.json"), value)
                raw = _copy_bounded_slice(log, offset, evidence / (name + "-native.jsonl"))
                row = {"name": name, "action_id": action, "recipient": recipient,
                       "parameters": parameters or {}, "inspection": brief(value), "native_slice": raw}
                report["cases"].append(row)
                save()
                return value
            def execute(name, action, recipient, parameters=None):
                request = "r68_" + name + "_" + token
                report["execution_started"] = {"request_id": request, "action_id": action, "recipient": recipient}
                save()
                value = api.execute_diplomatic_action(request, action, "FRA", recipient, parameters=parameters or {})
                _write_json(evidence / (name + "-execute.json"), value)
                # Poll the same journal request; never reissue an operation.
                deadline = time.monotonic() + 20
                while value.get("status") in ("pending", "submitted", "queued", "executing") and time.monotonic() < deadline:
                    time.sleep(.2)
                    value = api.get_diplomatic_result(request)
                _write_json(evidence / (name + "-result.json"), value)
                report.setdefault("executions", []).append({"request_id": request, "result": value})
                save()
                return value
            def probe():
                value = _run_probe(next(s for s in PROBE_SPECS if s.name == "diplomats"), int(session.record["pid"]), evidence / "diplomats.json")
                report["diplomat_probe"] = value
                save()
            if args.stage == "baseline":
                value = inspect("improve_MLO", "improve_relations", "MLO")
                inspect("declare_MOR", "declare_war", "MOR", NO_CB)
                probe()
                report["checks"]["one_available_diplomat"] = value.get("resources", {}).get("diplomats", {}).get("available_count") == 1
            elif args.stage == "occupy":
                value = inspect("improve_MLO_before", "improve_relations", "MLO")
                assert value["legality"]["status"] == "available", "IMPROVE_MLO_NOT_AVAILABLE"
                assert value["resources"]["diplomats"]["available_count"] == 1, "EXPECTED_ONE_FREE"
                result = execute("start_improve_MLO", "improve_relations", "MLO")
                after = inspect("improve_MOR_after", "improve_relations", "MOR")
                report["checks"] = {"start_executed": result.get("status") == "executed",
                    "zero_free": after.get("resources", {}).get("diplomats", {}).get("available_count") == 0}
                probe()
            elif args.stage == "zero":
                for action, recipient in CASES:
                    value = inspect(action, action, recipient, NO_CB if action == "declare_war" else {})
                    report["checks"][action + "_query_consumed"] = not any(
                        r.get("source") == "runtime_error" for r in value["legality"].get("reasons", []))
                    resource = value.get("resources", {}).get("diplomats")
                    if resource:
                        report["checks"][action + "_count_zero"] = resource.get("available_count") == 0
                        if resource.get("native_requirement") is True:
                            report["checks"][action + "_explicit_unavailable"] = value["legality"]["status"] == "unavailable" and any(r.get("code") == "NATIVE_DIPLOMAT_UNAVAILABLE" for r in value["legality"].get("reasons", []))
                        elif action.startswith("stop_"):
                            report["checks"][action + "_recall_allowed"] = value["legality"]["status"] == "available"
                discovery = inspect("peace_discovery", "white_peace", "BUR")
                war = _single_discovered_war_id(discovery, "FRA", "BUR")
                assert war, "WAR_REQUIRED"
                peace = {"peace_context": {"war_id": war, "direction": "demand", "terms": []}}
                report["peace_parameters"] = peace
                value = inspect("peace_selected", "white_peace", "BUR", peace)
                resource = value.get("resources", {}).get("diplomats", {})
                report["checks"]["peace_zero_explicit"] = resource.get("available_count") == 0 and any(r.get("code") == "NATIVE_DIPLOMAT_UNAVAILABLE" for r in value["legality"].get("reasons", []))
                for name, action, recipient, parameters in (("blocked_insult", "send_insult", "MOR", {}), ("blocked_declare", "declare_war", "MOR", NO_CB), ("blocked_peace", "white_peace", "BUR", peace)):
                    result = execute(name, action, recipient, parameters)
                    reasons = result.get("result", {}).get("legality_reasons", [])
                    report["checks"][name + "_api_reason"] = any(r.get("code") == "NATIVE_DIPLOMAT_UNAVAILABLE" for r in reasons) and result.get("submitted") is not True
                    report["checks"][name + "_reread"] = result == api.get_diplomatic_result("r68_" + name + "_" + token)
                    req = "r68_native_" + name + "_" + token
                    offset = log.stat().st_size
                    if action == "send_insult":
                        native = session.submit_send_insult(req, "FRA", recipient, "initiate", date)
                    elif action == "declare_war":
                        native = session.submit_declare_war(req, "FRA", recipient, "initiate", date, parameters)
                    else:
                        native = session.submit_peace(req, "FRA", recipient, "initiate", date, action, parameters)
                    _write_json(evidence / (name + "-fresh-native.json"), native)
                    _copy_bounded_slice(log, offset, evidence / (name + "-fresh-native.jsonl"))
                    report.setdefault("native_rejections", []).append({"action_id": action, "result": native})
                    report["checks"][name + "_native_reason"] = native.get("reason_code") == "NATIVE_DIPLOMAT_UNAVAILABLE" and native.get("submitted") is False and native.get("binding_complete") is True
                    save()
                probe()
            elif args.stage == "recall":
                before = inspect("stop_MLO_before", "stop_improving_relations", "MLO")
                assert before["resources"]["diplomats"]["available_count"] == 0, "EXPECTED_ZERO_FREE"
                assert before["resources"]["diplomats"]["native_requirement"] is False, "RECALL_REQUIRES_NO_DIPLOMAT"
                assert before["legality"]["status"] == "available", "RECALL_NOT_AVAILABLE"
                result = execute("stop_improve_MLO", "stop_improving_relations", "MLO")
                report["checks"]["recall_executed_at_zero"] = result.get("status") == "executed"
                probe()
            else:
                for action, recipient in (("improve_relations", "MOR"), ("declare_war", "MOR")):
                    value = inspect(action, action, recipient, NO_CB if action == "declare_war" else {})
                    resource = value.get("resources", {}).get("diplomats", {})
                    report["checks"][action + "_free_returned"] = resource.get("available_count", 0) > 0
                    report["checks"][action + "_zero_reason_cleared"] = not any(r.get("code") == "NATIVE_DIPLOMAT_UNAVAILABLE" for r in value["legality"].get("reasons", []))
                probe()
        report["status"] = "passed" if report["checks"] and all(report["checks"].values()) else "failed"
    except Exception as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
    report["native_slice"] = _copy_bounded_slice(log, start, evidence / "stage-native.jsonl")
    save()
    print(json.dumps({k: v for k, v in report.items() if k in ("status", "checks", "error", "stage")}, ensure_ascii=False))
    print(json.dumps({"case_count": len(report["cases"]), "executions": [
        {"request_id": row["request_id"], "status": row["result"].get("status")}
        for row in report.get("executions", [])]}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
