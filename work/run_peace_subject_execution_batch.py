"""Run subject terms, ducats and reparations with both controlled responses.

One process, one journal, one before/after control pair and one final save.
Resume reads existing request results; it never resubmits a recorded business
attempt. Incoming proposals are explicit operator fixtures, with native gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from work.local_config import game_exe
from work.observer_runtime_ready import wait_runtime_ready
from work.run_peace_concession_queries import _control_from_probe, _control_is_paused_por
from work.run_peace_empty_offer_queries import _has_private_fields, _single_discovered_war_id
from work.run_peace_outbound_execution import _poll_result
from work.validate_alliance_queries import PROBE_SPECS, _run_probe

STAGES = ("queries", "outbound", "reject", "accept", "finish")


def parameters(war_id: str, direction: str, transfer_country: str | None = None) -> dict:
    terms = [
        {"action_id": "demand_ducats", "amount": "1.0", "payer": "ENG", "claimant": "FRA"},
        {"action_id": "war_reparations", "payer": "ENG", "claimant": "FRA"},
        {"action_id": "release_subject", "country": "TYR"},
    ]
    if transfer_country:
        terms.append({"action_id": "transfer_subject", "country": transfer_country})
    return {"peace_context": {"war_id": war_id, "direction": direction, "terms": terms}}


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_slice(path: Path, start: int) -> bytes:
    length = path.stat().st_size - start
    if not 0 <= length <= 8 * 1024 * 1024:
        raise RuntimeError("BOUNDED_NATIVE_EVENT_SLICE_EXCEEDED")
    with path.open("rb") as stream:
        stream.seek(start)
        return stream.read(length)


def incoming_terms_match(context: dict, transfer_country: str | None = None) -> bool:
    """Compare the complete incoming offer with every selected clause."""
    rows = context.get("terms")
    if not isinstance(rows, list) or len(rows) != (4 if transfer_country else 3):
        return False
    by_action = {row.get("action_id"): row for row in rows if isinstance(row, dict)}
    expected = {"demand_ducats", "war_reparations", "release_subject"}
    if transfer_country:
        expected.add("transfer_subject")
    if set(by_action) != expected:
        return False
    money = by_action["demand_ducats"]
    if money.get("amount_raw") != 1000 or money.get("scale") != 1000:
        return False
    rep = by_action["war_reparations"]
    if rep.get("payer") != "ENG" or rep.get("claimant") != "FRA":
        return False
    subject = by_action["release_subject"]
    if subject.get("countries", [subject.get("country")]) != ["TYR"]:
        return False
    if transfer_country:
        transfer = by_action["transfer_subject"]
        if transfer.get("countries", [transfer.get("country")]) != [transfer_country]:
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--through", choices=STAGES, default="finish")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--fixture-reject")
    parser.add_argument("--fixture-accept")
    parser.add_argument("--transfer-country", choices=("LEI",))
    parser.add_argument("--save-name", default="llm_diplomacy_peace_subject_release_accepted_20261019_r60.eu4")
    args = parser.parse_args()
    fixture_kind = "COMBINED" if args.transfer_country else "RELEASE"
    args.fixture_reject = args.fixture_reject or f"TEST_ONLY ENG_PEACE_FRA_SUBJECT_{fixture_kind}_PENDING_1"
    args.fixture_accept = args.fixture_accept or f"TEST_ONLY ENG_PEACE_FRA_SUBJECT_{fixture_kind}_PENDING_2"
    output = args.output.resolve()
    evidence = output.parent / (output.stem + "-evidence")
    if output.exists():
        if not args.resume:
            raise SystemExit("OUTPUT_ALREADY_EXISTS_USE_RESUME")
        report = json.loads(output.read_text(encoding="utf-8"))
        if report["prefix"] != args.prefix:
            raise SystemExit("BATCH_PREFIX_MISMATCH")
    else:
        if args.resume:
            raise SystemExit("RESUME_REPORT_MISSING")
        evidence.mkdir(parents=True, exist_ok=False)
        report = {"status": "running", "prefix": args.prefix, "steps": {},
                  "transfer_country": args.transfer_country,
                  "save_reload_validation": False, "business_attempts": {},
                  "incoming_source": "explicit_operator_native_fixture",
                  "clause_actions": ["demand_ducats", "war_reparations", "release_subject"]}
        if args.transfer_country:
            report["clause_actions"].append("transfer_subject")
    if report.get("transfer_country") != args.transfer_country:
        raise SystemExit("RESUME_CLAUSE_SELECTION_MISMATCH")
    session = ObserverSession(args.installation, game_exe())
    if report.get("session_id", session.session_id) != session.session_id:
        raise SystemExit("SAME_PROCESS_REQUIRED_FOR_RESUME")
    report.update(session_id=session.session_id, installation=str(args.installation.resolve()),
                  pid=session.record["pid"], dll_sha256=session.record["dll_sha256"],
                  status="running")
    report.pop("error", None)
    log = session.directory / "control-probe.jsonl"
    report.setdefault("native_log_start", log.stat().st_size)

    def persist():
        write(output, report)

    def artifact(name, value):
        write(evidence / (name + ".json"), value)
        return value

    def command(name, argv):
        target = evidence / (name + ".log")
        with target.open("x", encoding="utf-8") as stream:
            code = subprocess.run(argv, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT).returncode
        if code:
            raise RuntimeError(f"{name}_EXIT_{code}:{target}")

    def effect_probe(name):
        target = evidence / (name + ".json")
        argv = [sys.executable, "-B", "work/probe_peace_effect_state.py", "--pid",
                      str(session.record["pid"]), "--countries", "FRA", "ENG", "TYR",
                      "--subject-pair", "ENG:TYR", "--subject-pair", "FRA:TYR",
                      "--reparations-payer", "ENG",
                      "--reparations-claimant", "FRA", "--expected-date-raw", str(session.health()["date_raw"]),
                      "--output", str(target)]
        if args.transfer_country:
            argv.extend(["--subject-pair", "ENG:" + args.transfer_country,
                         "--subject-pair", "FRA:" + args.transfer_country])
        command(name, argv)
        return str(target)

    def execute_once(api, key, action, actor, recipient, phase, params):
        rid = args.prefix + "_" + key
        if key not in report["business_attempts"]:
            report["business_attempts"][key] = {"request_id": rid, "call_recorded_before_execute": True}
            persist()
            submitted = api.execute_diplomatic_action(rid, action, actor, recipient,
                                                      phase=phase, parameters=params)
            artifact(key + "-submission", submitted)
            report["business_attempts"][key]["submission"] = submitted
            persist()
        final = _poll_result(api, rid)
        artifact(key + "-result", final)
        report["business_attempts"][key]["poll"] = final
        persist()
        return final.get("final", {})

    def require_available(value):
        if value.get("legality", {}).get("status") != "available":
            raise RuntimeError("NATIVE_LEGALITY_NOT_AVAILABLE")
        if _has_private_fields(value):
            raise RuntimeError("PRIVATE_FIELDS_IN_PUBLIC_INSPECTION")

    def pending(api):
        catalog = api.list_diplomatic_actions()
        responded = {
            report["steps"]["fixture-" + key]["proposal"]["proposal_id"]
            for key in ("reject", "accept")
            if "fixture-" + key in report["steps"]
            and report["business_attempts"].get(key, {}).get("poll", {}).get(
                "final", {}).get("status") in {"accepted", "rejected"}}
        return [row for row in catalog.get("incoming_proposals", [])
                if row.get("family") == "peace" and row.get("actor") == "ENG"
                and row.get("recipient") == "FRA"
                and row.get("observer_status") == "observed_pending"
                and row.get("currently_pending") is not False
                and row.get("proposal_id") not in responded]

    def fixture(api, decision):
        key = "fixture-" + decision
        old = report["steps"].get(key)
        if old:
            return old["proposal"]
        previous = report.get("fixture_attempts", {}).get(key)
        if previous:
            observed = [json.loads(line) for line in read_slice(log, previous["start"]).splitlines()]
            failed_preflight = any(
                row.get("request_id") == "peace_inbound_fixture"
                and row.get("reason") == "TEST_PEACE_INBOUND_NATIVE_PREFLIGHT_FAILED"
                for row in observed)
            index = 1 if decision == "reject" else 2
            dispatched = any(row.get("event") == "native_peace_inbound_fixture_dispatched"
                             and row.get("fixture_index") == index for row in observed)
            if failed_preflight and not dispatched:
                report.setdefault("fixture_preflight_failures", []).append(previous)
                del report["fixture_attempts"][key]
                persist()
        if key not in report.get("fixture_attempts", {}):
            offset = log.stat().st_size
            report.setdefault("fixture_attempts", {})[key] = {"start": offset, "publication_attempted": True}
            persist()
            wire = args.fixture_reject if decision == "reject" else args.fixture_accept
            publication = session._publish_atomic_request(wire + "\n", args.prefix + "_" + key,
                                                          "diplomacy-authority-test.req")
            report["fixture_attempts"][key]["publication"] = publication
            persist()
            if publication != "published":
                raise RuntimeError("FIXTURE_NOT_PUBLISHED")
        deadline = time.monotonic() + 20
        proposals = []
        while time.monotonic() < deadline:
            proposals = pending(api)
            if proposals:
                break
            observed = [json.loads(line) for line in read_slice(
                log, report["fixture_attempts"][key]["start"]).splitlines()]
            failure = next((row.get("reason") for row in observed
                            if row.get("request_id") == "peace_inbound_fixture"
                            and row.get("reason")), None)
            if failure:
                report["fixture_attempts"][key]["native_failure_reason"] = failure
                persist()
                raise RuntimeError("NATIVE_FIXTURE_PREFLIGHT:" + failure)
            time.sleep(0.2)
        artifact(key + "-proposals", proposals)
        if len(proposals) != 1:
            raise RuntimeError("UNIQUE_NATIVE_SUBJECT_PROPOSAL_REQUIRED")
        proposal = proposals[0]
        context = proposal.get("peace_context", {})
        if (context.get("war_id") != report["war_id"]
                or context.get("direction") != "offer"
                or not incoming_terms_match(context, args.transfer_country)):
            raise RuntimeError("INCOMING_FULL_CLAUSE_CONTEXT_MISMATCH")
        report["steps"][key] = {"proposal": proposal}
        persist()
        return proposal

    try:
        health = wait_runtime_ready(session, timeout=25, restore_minimized=True)
        if health.get("status") != "ready":
            raise RuntimeError("SESSION_NOT_READY")
        if "before" not in report:
            control = _control_from_probe(_run_probe(PROBE_SPECS[0], session.record["pid"], evidence / "before-control.json"))
            if not _control_is_paused_por(control, health.get("date_raw")):
                raise RuntimeError("PAUSED_POR_CONTEXT_REQUIRED")
            report["before"] = control
            report["before_effect_probe"] = effect_probe("before-effects")
            persist()
        with DurableJournal(evidence / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            if "queries" not in report["steps"]:
                discovery = artifact("war-discovery", api.inspect_diplomatic_action("white_peace", "FRA", "ENG", parameters={}))
                war = _single_discovered_war_id(discovery, "FRA", "ENG")
                if war is None:
                    raise RuntimeError("UNIQUE_WAR_REQUIRED")
                report["war_id"] = war
                rows = []
                for actor, recipient, direction in (("FRA", "ENG", "demand"),):
                    params = parameters(war, direction, args.transfer_country)
                    cached = evidence / ("combined-" + direction + ".json")
                    if cached.exists():
                        # A projection correction can reuse the original native
                        # observation; execution still checks the current offer.
                        inspection = json.loads(cached.read_text(encoding="utf-8"))
                    else:
                        inspection = artifact("combined-" + direction, api.inspect_diplomatic_action("release_subject", actor, recipient, parameters=params))
                    require_available(inspection)
                    rows.append({"actor": actor, "recipient": recipient, "parameters": params,
                                 "inspection": inspection})
                report["steps"]["queries"] = rows
                persist()
            if STAGES.index(args.through) >= 1 and "outbound" not in report["steps"]:
                final = execute_once(api, "outbound", "release_subject", "FRA", "ENG", "initiate", parameters(report["war_id"], "demand", args.transfer_country))
                if final.get("status") != "rejected":
                    raise RuntimeError("OUTBOUND_NOT_OBSERVED_REJECTED")
                report["steps"]["outbound"] = {"status": "rejected", "result": final}
                persist()
            for decision in ("reject", "accept"):
                if STAGES.index(args.through) < STAGES.index(decision) or decision in report["steps"]:
                    continue
                proposal = fixture(api, decision)
                params = {"proposal_id": proposal["proposal_id"]}
                if decision not in report["business_attempts"]:
                    inspection = artifact(decision + "-inspection", api.inspect_diplomatic_action(
                        "peace_offer", "ENG", "FRA", phase=decision, parameters=params))
                    require_available(inspection)
                final = execute_once(api, decision, "peace_offer", "ENG", "FRA", decision, params)
                expected_status = "accepted" if decision == "accept" else "rejected"
                if final.get("status") != expected_status:
                    raise RuntimeError("CONTROLLED_RESPONSE_NOT_OBSERVED_" + expected_status.upper())
                if final.get("result", {}).get("pending_removed") is not True:
                    raise RuntimeError("NATIVE_PENDING_REMOVAL_NOT_VERIFIED")
                report["steps"][decision] = {"status": expected_status, "result": final}
                persist()
            if args.through == "finish" and "finish" not in report["steps"]:
                report["after_effect_probe"] = effect_probe("after-effects")
                after = _control_from_probe(_run_probe(PROBE_SPECS[0], session.record["pid"], evidence / "after-control.json"))
                report["after"] = after
                if not _control_is_paused_por(after, session.health().get("date_raw")):
                    raise RuntimeError("BATCH_END_PAUSED_POR_REQUIRED")
                command("save", [sys.executable, "-B", "tools/save_observer_experiment.py", "--installation",
                                 str(args.installation.resolve()), "--name", args.save_name])
                report["steps"]["finish"] = {"saved_name": args.save_name}
                persist()
        report["status"] = "passed" if args.through == "finish" else "stage_passed"
        report["through"] = args.through
    except Exception as error:
        report.update(status="failed", error=f"{type(error).__name__}:{error}")
    finally:
        raw = read_slice(log, report["native_log_start"])
        (evidence / "native-events-slice.jsonl").write_bytes(raw)
        report["native_event_slice"] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        persist()
    print(json.dumps({key: report.get(key) for key in ("status", "through", "war_id", "error")}, ensure_ascii=False))
    return 0 if report["status"] in {"passed", "stage_passed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
