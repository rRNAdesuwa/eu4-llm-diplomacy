"""Verify unified and fresh-native rejection reasons in the paused R66 scene."""
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
from work.run_peace_consequence_queries import (
    _output_paths, _write_json, _copy_bounded_slice, _single_discovered_war_id,
    _has_private_fields,
)
from work.run_peace_concession_queries import _control_from_probe, _control_is_paused_por
from work.validate_alliance_queries import PROBE_SPECS, _run_probe


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output, evidence = _output_paths(args.output)
    session = ObserverSession(args.installation.resolve(strict=True), game_exe())
    report = {"status":"running", "session_id":session.session_id,
              "installation":str(args.installation), "cases":[], "checks":{},
              "business_submission":False, "advance_requested":False,
              "save_requested":False, "restart_requested":False}
    try:
        health = wait_runtime_ready(session, timeout=25, restore_minimized=True)
        date = health["date_raw"]
        before = _control_from_probe(_run_probe(PROBE_SPECS[0], session.record["pid"], evidence/"before.json"))
        report["before"] = before
        assert _control_is_paused_por(before, date), "BASELINE_NOT_PAUSED_POR"
        with DurableJournal(evidence/"journal.sqlite3",session.experiment_id,session.session_id) as journal:
            api = DiplomacyTools(journal,session)
            discovery = api.inspect_diplomatic_action("white_peace","FRA","BUR",parameters={})
            war = _single_discovered_war_id(discovery,"FRA","BUR")
            assert war, "WAR_DISCOVERY_FAILED"
            report["war_id"] = war
            proposals = [
                ("white_cooldown", "white_peace", []),
                ("province_unmatched", "cede_province", [{"action_id":"cede_province","province_ids":[88],"beneficiary":"ORL"}]),
            ]
            for name, action, terms in proposals:
                parameters = {"peace_context":{"war_id":war,"direction":"demand","terms":terms}}
                check = api.inspect_diplomatic_action(action,"FRA","BUR",parameters=parameters)
                # Only negative cases are submitted to the fresh native
                # preflight. The paused baseline cannot change in this batch.
                assert check["legality"]["status"] == "unavailable", "NEGATIVE_CASE_BECAME_AVAILABLE"
                token = output.parent.name[-3:]
                request = f"r66_api_{name}_{token}"
                result = api.execute_diplomatic_action(request,action,"FRA","BUR",parameters=parameters)
                reread = api.get_diplomatic_result(request)
                _write_json(evidence/f"{name}-api.json",result)
                reasons = result.get("result",{}).get("legality_reasons",[])
                api_ok = (result.get("submitted") is False and result==reread
                          and any(row.get("source")=="native_rule" and row.get("text")
                                  and row.get("code")!="NATIVE_LEGALITY_UNAVAILABLE" for row in reasons))
                log = session.directory/"control-probe.jsonl"
                start = log.stat().st_size
                native = session.submit_peace(f"r66_native_{name}_{token}","FRA","BUR","initiate",date,action,parameters)
                _write_json(evidence/f"{name}-native.json",native)
                slice_meta = _copy_bounded_slice(log,start,evidence/f"{name}-native.jsonl")
                native_ok = (native.get("status")=="failed" and native.get("submitted") is False
                             and native.get("binding_complete") is True
                             and native.get("reason",{}).get("source")=="native_rule"
                             and native.get("reason_code") not in (None,"NATIVE_PEACE_PREFLIGHT_FAILED")
                             and native.get("reason",{}).get("text")
                             and not _has_private_fields(native))
                report["cases"].append({"name":name,"action_id":action,"parameters":parameters,
                    "api_reason_verified":bool(api_ok),"native_reason_verified":bool(native_ok),
                    "native_reason_code":native.get("reason_code"),
                    "native_reason":native.get("reason"),"native_slice":slice_meta,
                    "api_submitted":result.get("submitted"),"native_submitted":native.get("submitted")})
                if result.get("submitted") is True or native.get("submitted") is True:
                    report["business_submission"] = True
                    raise RuntimeError("UNEXPECTED_SUBMISSION_NO_REPLAY")
        after = _control_from_probe(_run_probe(PROBE_SPECS[0], session.record["pid"], evidence/"after.json"))
        report["after"] = after
        report["checks"] = {"two_negative_cases":len(report["cases"])==2,
            "all_public_and_native_reasons":all(c["api_reason_verified"] and c["native_reason_verified"] for c in report["cases"]),
            "paused_por_same_date":_control_is_paused_por(after,date) and before["date_raw"]==after["date_raw"],
            "no_business_submission":report["business_submission"] is False}
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type":type(error).__name__,"message":str(error)}
    _write_json(output,report)
    print(json.dumps({"status":report["status"],"report":str(output),"cases":len(report["cases"])},ensure_ascii=False))
    return 0 if report["status"]=="passed" else 1


if __name__=="__main__":
    raise SystemExit(main())
