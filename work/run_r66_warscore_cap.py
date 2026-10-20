"""Verify the native 100% peace-cost guard without submitting a treaty."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from bridge.diplomacy import DiplomacyTools,ObserverSession
from bridge.diplomacy_journal import DurableJournal
from work.local_config import game_exe
from work.observer_runtime_ready import wait_runtime_ready
from work.run_peace_consequence_queries import _output_paths,_write_json,_copy_bounded_slice,_single_discovered_war_id
from work.run_peace_concession_queries import _control_from_probe,_control_is_paused_por
from work.validate_alliance_queries import PROBE_SPECS,_run_probe


def cap_texts(value:object) -> list[str]:
    found=[]
    if isinstance(value,dict):
        for key,item in value.items():
            if (isinstance(item,str) and (key=="text" or key.endswith("_text"))
                    and "100" in item and ("战争分" in item or "war score" in item.lower())):
                found.append(item)
            elif isinstance(item,(dict,list)):
                found.extend(cap_texts(item))
    elif isinstance(value,list):
        for item in value:
            found.extend(cap_texts(item))
    return list(dict.fromkeys(found))


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    output,evidence=_output_paths(args.output)
    session=ObserverSession(args.installation.resolve(strict=True),game_exe())
    report={"status":"running","session_id":session.session_id,
            "business_submission":False,"advance_requested":False,"save_requested":False,
            "restart_requested":False,"checks":{}}
    try:
        health=wait_runtime_ready(session,timeout=25,restore_minimized=True)
        date=health["date_raw"]
        before=_control_from_probe(_run_probe(PROBE_SPECS[0],session.record["pid"],evidence/"before.json"))
        report["before"]=before
        assert _control_is_paused_por(before,date),"BASELINE_NOT_PAUSED_POR"
        with DurableJournal(evidence/"journal.sqlite3",session.experiment_id,session.session_id) as journal:
            api=DiplomacyTools(journal,session)
            discovery=api.inspect_diplomatic_action("white_peace","FRA","BUR",parameters={})
            war=_single_discovered_war_id(discovery,"FRA","BUR")
            assert war,"WAR_DISCOVERY_FAILED"
            empty={"peace_context":{"war_id":war,"direction":"demand","terms":[]}}
            baseline=api.inspect_diplomatic_action("white_peace","FRA","BUR",parameters=empty)
            _write_json(evidence/"white-baseline.json",baseline)
            candidates=api.inspect_diplomatic_action("cede_province","FRA","BUR",parameters=empty)
            _write_json(evidence/"candidates.json",candidates)
            rows=candidates.get("parameters",{}).get("candidates",[])
            ids=list(dict.fromkeys(r["province_id"] for r in rows
                if r.get("beneficiary")=="FRA" and isinstance(r.get("province_id"),int)))[:16]
            assert len(ids)==16,"SIXTEEN_NATIVE_CANDIDATES_REQUIRED"
            one_parameters={"peace_context":{"war_id":war,"direction":"demand","terms":[
                {"action_id":"cede_province","province_ids":ids[:1],"beneficiary":"FRA"}]}}
            one=api.inspect_diplomatic_action("cede_province","FRA","BUR",parameters=one_parameters)
            _write_json(evidence/"single-province-positive.json",one)
            assert one.get("legality",{}).get("status")=="available","SINGLE_PROVINCE_NOT_AVAILABLE"
            parameters={"peace_context":{"war_id":war,"direction":"demand","terms":[
                {"action_id":"cede_province","province_ids":ids,"beneficiary":"FRA"}]}}
            _write_json(evidence/"input.json",parameters)
            log=session.directory/"control-probe.jsonl"
            start=log.stat().st_size
            inspection=api.inspect_diplomatic_action("cede_province","FRA","BUR",parameters=parameters)
            _write_json(evidence/"inspection.json",inspection)
            report["query_native_slice"]=_copy_bounded_slice(log,start,evidence/"query-native.jsonl")
            assert inspection.get("legality",{}).get("status")=="unavailable","OVER_CAP_PROPOSAL_NOT_PROHIBITED"
            assert cap_texts(inspection),"NATIVE_100_PERCENT_REASON_NOT_OBSERVED"
            api_result=api.execute_diplomatic_action("r66_api_overcap_"+output.parent.name[-3:],"cede_province","FRA","BUR",parameters=parameters)
            _write_json(evidence/"api-result.json",api_result)
            start=log.stat().st_size
            native=session.submit_peace("r66_native_overcap_"+output.parent.name[-3:],"FRA","BUR","initiate",date,"cede_province",parameters)
            _write_json(evidence/"native-result.json",native)
            report["execution_native_slice"]=_copy_bounded_slice(log,start,evidence/"execution-native.jsonl")
            report.update(war_id=war,parameters=parameters,white_baseline_legality=baseline.get("legality"),
                single_province_legality=one.get("legality"),
                inspection_cap_texts=cap_texts(inspection),api_cap_texts=cap_texts(api_result),
                native_cap_texts=cap_texts(native),native_reason=native.get("reason"),
                native_reason_code=native.get("reason_code"),native_status=native.get("status"),
                api_submitted=api_result.get("submitted"),native_submitted=native.get("submitted"))
            report["business_submission"]=api_result.get("submitted") is True or native.get("submitted") is True
        after=_control_from_probe(_run_probe(PROBE_SPECS[0],session.record["pid"],evidence/"after.json"))
        report["after"]=after
        report["checks"]={"sixteen_native_provinces":len(ids)==16,
            "single_province_available":one.get("legality",{}).get("status")=="available",
            "query_reports_100_percent_guard":bool(report["inspection_cap_texts"]),
            "unified_execution_reports_100_percent_guard":bool(report["api_cap_texts"]),
            "fresh_native_execution_reports_100_percent_guard":bool(report["native_cap_texts"]),
            "native_prohibition_bound":native.get("binding_complete") is True and native.get("reason",{}).get("source")=="native_rule",
            "no_business_submission":report["business_submission"] is False,
            "paused_por_same_date":_control_is_paused_por(after,date) and before["date_raw"]==after["date_raw"]}
        report["status"]="passed" if all(report["checks"].values()) else "failed"
    except Exception as error:
        report["status"]="failed"
        report["error"]={"type":type(error).__name__,"message":str(error)}
    _write_json(output,report)
    print(json.dumps({"status":report["status"],"report":str(output),"checks":report["checks"]},ensure_ascii=False))
    return 0 if report["status"]=="passed" else 1


if __name__=="__main__":
    raise SystemExit(main())
