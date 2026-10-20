"""Run one country-shaped peace batch with controlled incoming responses.

The batch deliberately keeps one observer process, one durable journal, one
before/after control pair, and one final save.  A resume only reads recorded
results and retries an un-dispatched native-fixture preflight; it never
replays a recorded business request.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
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
KINDS = ("combined", "release", "annex", "vassal", "union", "independence")


# Keep this table declarative so the public wire and the incoming fixture are
# built from the same exact clause list.  The actor is always FRA; only the
# normal recipient changes for the vassal/union tests.
SCENARIOS = {
    "combined": {
        "primary_action": "release_nation",
        "outbound_recipient": "ENG",
        "incoming_actor": "ENG",
        "fixture_base": "ENG_PEACE_FRA_COUNTRY_COMBINED",
        "terms": (
            {"action_id": "release_nation", "country": "FLY", "source": "ENG"},
            {"action_id": "full_annexation", "country": "TYR", "beneficiary": "FRA"},
        ),
        "countries": ("FRA", "ENG", "FLY", "TYR"),
        "provinces": ("372", "4379"),
        "pairs": (),
    },
    "release": {
        "primary_action": "release_nation",
        "outbound_recipient": "ENG",
        "incoming_actor": "ENG",
        "fixture_base": "ENG_PEACE_FRA_RELEASE_FLY",
        "terms": (
            {"action_id": "release_nation", "country": "FLY", "source": "ENG"},
        ),
        "countries": ("FRA", "ENG", "FLY"),
        "provinces": (),
        "pairs": (),
    },
    "annex": {
        "primary_action": "full_annexation",
        "outbound_recipient": "ENG",
        "incoming_actor": "ENG",
        "fixture_base": "ENG_PEACE_FRA_ANNEX_TYR",
        "terms": (
            {"action_id": "full_annexation", "country": "TYR", "beneficiary": "FRA"},
        ),
        "countries": ("FRA", "ENG", "TYR"),
        "provinces": ("372", "4379"),
        "pairs": (),
    },
    "vassal": {
        "primary_action": "force_vassalization",
        "outbound_recipient": "LEI",
        "incoming_actor": "LEI",
        "fixture_base": "LEI_PEACE_FRA_FORCE_VASSAL",
        "terms": (
            {"action_id": "force_vassalization", "country": "LEI", "beneficiary": "FRA"},
        ),
        "countries": ("FRA", "LEI"),
        "provinces": (),
        "pairs": (("FRA", "LEI"), ("LEI", "FRA")),
    },
    "union": {
        "primary_action": "form_personal_union",
        "outbound_recipient": "LEI",
        "incoming_actor": "LEI",
        "fixture_base": "LEI_PEACE_FRA_PERSONAL_UNION",
        "terms": (
            {"action_id": "form_personal_union", "country": "LEI", "beneficiary": "FRA"},
        ),
        "countries": ("FRA", "LEI"),
        "provinces": (),
        "pairs": (("FRA", "LEI"), ("LEI", "FRA")),
    },
    "independence": {
        "primary_action": "grant_independence",
        "outbound_recipient": "ENG",
        "incoming_actor": "ENG",
        "fixture_base": "ENG_PEACE_FRA_INDEPENDENCE",
        "terms": (
            {"action_id": "grant_independence"},
        ),
        "countries": ("FRA", "ENG"),
        "provinces": (),
        "pairs": (("ENG", "FRA"), ("FRA", "ENG")),
    },
}


def _scenario(kind: str) -> dict:
    try:
        return SCENARIOS[kind]
    except KeyError as error:
        raise ValueError("UNKNOWN_COUNTRY_KIND") from error


def parameters(war_id: str, direction: str, kind: str = "combined") -> dict:
    """Return an exact country-term context for either demand or offer.

    The normal argument order follows the older batch runner.  Accepting
    ``parameters(war_id, kind, direction)`` as well keeps small offline
    contract callers readable without changing the wire generated here.
    """
    if direction in SCENARIOS and kind in ("demand", "offer"):
        direction, kind = kind, direction
    if direction not in ("demand", "offer"):
        raise ValueError("PEACE_DIRECTION_INVALID")
    scenario = _scenario(kind)
    return {
        "peace_context": {
            "war_id": war_id,
            "direction": direction,
            "terms": [dict(term) for term in scenario["terms"]],
        }
    }


def incoming_terms_match(context: dict, kind: str = "combined") -> bool:
    """Require the complete incoming offer and reject any extra/missing term."""
    if not isinstance(context, dict) or context.get("direction") != "offer":
        return False
    if context.get("complete") is False:
        return False
    rows = context.get("terms")
    if not isinstance(rows, list):
        return False
    expected = parameters("wire-contract", "offer", kind)["peace_context"]["terms"]
    return rows == expected


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_slice(path: Path, start: int) -> bytes:
    length = path.stat().st_size - start
    if not 0 <= length <= 8 * 1024 * 1024:
        raise RuntimeError("BOUNDED_NATIVE_EVENT_SLICE_EXCEEDED")
    with path.open("rb") as stream:
        stream.seek(start)
        return stream.read(length)


def _load_prior_outbound_report(path: Path, kind: str) -> dict:
    """Validate a completed outbound rejection for read-only reuse.

    The new process must rediscover its own war and run its own query.  This
    helper only imports the prior rejection as evidence; it never imports its
    request id into the new journal or polls it again.
    """
    path = path.resolve()
    if not path.is_file():
        raise RuntimeError("PRIOR_OUTBOUND_REPORT_NOT_FOUND")
    if path.stat().st_size > 8 * 1024 * 1024:
        raise RuntimeError("PRIOR_OUTBOUND_REPORT_TOO_LARGE")
    try:
        source = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError("PRIOR_OUTBOUND_REPORT_INVALID_JSON") from error
    scenario = _scenario(kind)
    if source.get("kind") != kind:
        raise RuntimeError("PRIOR_OUTBOUND_KIND_MISMATCH")
    expected_actions = [term["action_id"] for term in scenario["terms"]]
    if source.get("clause_actions") != expected_actions:
        raise RuntimeError("PRIOR_OUTBOUND_CLAUSES_MISMATCH")
    if not isinstance(source.get("prefix"), str) or not source["prefix"]:
        raise RuntimeError("PRIOR_OUTBOUND_PREFIX_MISSING")
    if not isinstance(source.get("session_id"), str) or not source["session_id"]:
        raise RuntimeError("PRIOR_OUTBOUND_SESSION_MISSING")
    outbound = source.get("steps", {}).get("outbound")
    result = outbound.get("result") if isinstance(outbound, dict) else None
    if (not isinstance(outbound, dict) or outbound.get("status") != "rejected"
            or not isinstance(result, dict)
            or result.get("status") != "rejected"
            or result.get("submitted") is not True):
        raise RuntimeError("PRIOR_OUTBOUND_REJECTION_NOT_SUBMITTED")
    if result.get("action_id") != scenario["primary_action"]:
        raise RuntimeError("PRIOR_OUTBOUND_ACTION_MISMATCH")
    request_id = result.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        raise RuntimeError("PRIOR_OUTBOUND_REQUEST_MISSING")

    expected_terms = parameters("wire-contract", "demand", kind)["peace_context"]["terms"]
    contexts = []
    queries = source.get("steps", {}).get("queries")
    if isinstance(queries, list):
        for row in queries:
            if not isinstance(row, dict):
                continue
            query_params = row.get("parameters")
            if isinstance(query_params, dict):
                context = query_params.get("peace_context")
                if isinstance(context, dict):
                    contexts.append(context)
            if (row.get("actor") is not None
                    and row.get("actor") != "FRA"):
                raise RuntimeError("PRIOR_OUTBOUND_ACTOR_MISMATCH")
            if (row.get("recipient") is not None
                    and row.get("recipient") != scenario["outbound_recipient"]):
                raise RuntimeError("PRIOR_OUTBOUND_RECIPIENT_MISMATCH")
    outcome = result.get("result")
    if isinstance(outcome, dict):
        execution_context = outcome.get("execution_context")
        if isinstance(execution_context, dict):
            contexts.append(execution_context)
        result_params = outcome.get("parameters")
        if isinstance(result_params, dict):
            context = result_params.get("peace_context")
            if isinstance(context, dict):
                contexts.append(context)
    if not contexts or any(context.get("terms") != expected_terms for context in contexts):
        raise RuntimeError("PRIOR_OUTBOUND_LOGICAL_TERMS_MISMATCH")
    if isinstance(outcome, dict):
        if (outcome.get("actor") is not None
                and outcome.get("actor") != "FRA"):
            raise RuntimeError("PRIOR_OUTBOUND_ACTOR_MISMATCH")
        if (outcome.get("direction") is not None
                and outcome.get("direction") != "demand"):
            raise RuntimeError("PRIOR_OUTBOUND_DIRECTION_MISMATCH")
    return {
        "path": str(path), "prefix": source["prefix"],
        "session_id": source["session_id"], "request_id": request_id,
        "kind": kind, "status": "rejected", "submitted": True,
        "result": deepcopy(result),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=KINDS, required=True)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--through", choices=STAGES, default="finish")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--prior-outbound-report", type=Path,
                        help="reuse a separately recorded submitted outbound rejection")
    parser.add_argument("--existing-pending-reject", action="store_true",
                        help="inherit one already-pending matching reject fixture")
    parser.add_argument("--fixture-reject")
    parser.add_argument("--fixture-accept")
    parser.add_argument("--save-name")
    args = parser.parse_args()
    scenario = _scenario(args.kind)
    args.fixture_reject = args.fixture_reject or f"TEST_ONLY {scenario['fixture_base']}_PENDING_1"
    args.fixture_accept = args.fixture_accept or f"TEST_ONLY {scenario['fixture_base']}_PENDING_2"
    args.save_name = args.save_name or (
        f"llm_diplomacy_peace_country_{args.kind}_accepted_20261019.eu4")
    prior_outbound = (
        _load_prior_outbound_report(args.prior_outbound_report, args.kind)
        if args.prior_outbound_report is not None else None)

    output = args.output.resolve()
    evidence = output.parent / (output.stem + "-evidence")
    if output.exists():
        if not args.resume:
            raise SystemExit("OUTPUT_ALREADY_EXISTS_USE_RESUME")
        report = json.loads(output.read_text(encoding="utf-8"))
        if report.get("prefix") != args.prefix:
            raise SystemExit("BATCH_PREFIX_MISMATCH")
        if report.get("kind") != args.kind:
            raise SystemExit("RESUME_CLAUSE_SELECTION_MISMATCH")
    else:
        if args.resume:
            raise SystemExit("RESUME_REPORT_MISSING")
        evidence.mkdir(parents=True, exist_ok=False)
        report = {
            "status": "running", "prefix": args.prefix, "kind": args.kind,
            "steps": {}, "save_reload_validation": False, "business_attempts": {},
            "incoming_source": "explicit_operator_native_fixture",
            "clause_actions": [term["action_id"] for term in scenario["terms"]],
            "outbound_actor": "FRA", "outbound_recipient": scenario["outbound_recipient"],
            "incoming_actor": scenario["incoming_actor"], "incoming_recipient": "FRA",
            "fixture_tokens": {"reject": args.fixture_reject, "accept": args.fixture_accept},
            "existing_pending_reject": args.existing_pending_reject,
        }
        if prior_outbound is not None:
            report["prior_outbound_report"] = {
                key: prior_outbound[key]
                for key in ("path", "prefix", "session_id", "request_id", "kind",
                            "status", "submitted")
            }
    if report.get("kind") != args.kind:
        raise SystemExit("RESUME_CLAUSE_SELECTION_MISMATCH")
    if prior_outbound is not None:
        stored_prior = report.get("prior_outbound_report")
        if (stored_prior is not None
                and stored_prior.get("path") != prior_outbound["path"]):
            raise SystemExit("PRIOR_OUTBOUND_REPORT_RESUME_MISMATCH")
        if stored_prior is None:
            report["prior_outbound_report"] = {
                key: prior_outbound[key]
                for key in ("path", "prefix", "session_id", "request_id", "kind",
                            "status", "submitted")
            }
    elif ("outbound" not in report.get("steps", {})
          and isinstance(report.get("prior_outbound_report"), dict)):
        stored_path = report["prior_outbound_report"].get("path")
        if isinstance(stored_path, str):
            prior_outbound = _load_prior_outbound_report(Path(stored_path), args.kind)

    session = ObserverSession(args.installation, game_exe())
    if report.get("session_id", session.session_id) != session.session_id:
        raise SystemExit("SAME_PROCESS_REQUIRED_FOR_RESUME")
    report.update(session_id=session.session_id, installation=str(args.installation.resolve()),
                  pid=session.record["pid"], dll_sha256=session.record["dll_sha256"],
                  status="running")
    report.pop("error", None)
    log = session.directory / "control-probe.jsonl"
    report.setdefault("native_log_start", log.stat().st_size)

    def persist() -> None:
        write(output, report)

    def artifact(name: str, value: object):
        write(evidence / (name + ".json"), value)
        return value

    def command(name: str, argv: list[str]) -> None:
        target = evidence / (name + ".log")
        with target.open("x", encoding="utf-8") as stream:
            code = subprocess.run(argv, cwd=ROOT, stdout=stream,
                                  stderr=subprocess.STDOUT).returncode
        if code:
            raise RuntimeError(f"{name}_EXIT_{code}:{target}")

    def effect_probe(name: str) -> str:
        target = evidence / (name + ".json")
        argv = [sys.executable, "-B", "work/probe_peace_effect_state.py", "--pid",
                str(session.record["pid"]), "--countries", *scenario["countries"]]
        if scenario["provinces"]:
            argv.extend(["--provinces", *scenario["provinces"]])
        for source, subject in scenario["pairs"]:
            argv.extend(["--subject-pair", f"{source}:{subject}"])
        argv.extend(["--expected-date-raw", str(session.health()["date_raw"]),
                     "--output", str(target)])
        command(name, argv)
        return str(target)

    def execute_once(api, key: str, action: str, actor: str, recipient: str,
                     phase: str, params: dict) -> dict:
        rid = args.prefix + "_" + key
        if key not in report["business_attempts"]:
            report["business_attempts"][key] = {
                "request_id": rid, "call_recorded_before_execute": True,
            }
            persist()
            submitted = api.execute_diplomatic_action(
                rid, action, actor, recipient, phase=phase, parameters=params)
            artifact(key + "-submission", submitted)
            report["business_attempts"][key]["submission"] = submitted
            persist()
        final = _poll_result(api, rid)
        artifact(key + "-result", final)
        report["business_attempts"][key]["poll"] = final
        persist()
        return final.get("final", {})

    def require_available(value: dict) -> None:
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
            and report["business_attempts"].get(key, {}).get("poll", {})
            .get("final", {}).get("status") in {"accepted", "rejected"}
        }
        return [row for row in catalog.get("incoming_proposals", [])
                if row.get("family") == "peace"
                and row.get("actor") == scenario["incoming_actor"]
                and row.get("recipient") == "FRA"
                and row.get("observer_status") == "observed_pending"
                and row.get("currently_pending") is not False
                and row.get("proposal_id") not in responded]

    def existing_matching_pending(api):
        """Return exactly one already-pending reject offer, if present."""
        catalog = api.list_diplomatic_actions()
        matches = []
        for row in catalog.get("incoming_proposals", []):
            if (row.get("family") != "peace"
                    or row.get("actor") != scenario["incoming_actor"]
                    or row.get("recipient") != "FRA"
                    or row.get("observer_status") != "observed_pending"
                    or row.get("currently_pending") is False):
                continue
            context = row.get("peace_context")
            if (not isinstance(context, dict)
                    or context.get("war_id") != report.get("war_id")
                    or not incoming_terms_match(context, args.kind)):
                continue
            matches.append(row)
        if len(matches) > 1:
            raise RuntimeError("EXISTING_PENDING_REJECT_NOT_UNIQUE")
        return matches[0] if matches else None

    def fixture(api, decision: str):
        key = "fixture-" + decision
        old = report["steps"].get(key)
        if old:
            return old["proposal"]
        if decision == "reject" and args.existing_pending_reject:
            proposal = existing_matching_pending(api)
            if proposal is None:
                raise RuntimeError("EXISTING_PENDING_REJECT_NOT_FOUND")
            report.setdefault("fixture_attempts", {})[key] = {
                "start": log.stat().st_size,
                "publication": "inherited_pending",
                "publication_attempted": False,
                "source": "current_catalog_existing_pending",
                "proposal_id": proposal.get("proposal_id"),
            }
            report["steps"][key] = {"proposal": proposal,
                                    "inherited_pending": True}
            persist()
            return proposal
        previous = report.get("fixture_attempts", {}).get(key)
        if previous:
            observed = [json.loads(line) for line in
                        read_slice(log, previous["start"]).splitlines()]
            failed_preflight = any(
                row.get("request_id") in {"peace_inbound_fixture", "peace_country_inbound_fixture"}
                and row.get("reason") == "TEST_PEACE_INBOUND_NATIVE_PREFLIGHT_FAILED"
                for row in observed)
            index = 1 if decision == "reject" else 2
            dispatched = any(
                row.get("event") == "native_peace_inbound_fixture_dispatched"
                and row.get("fixture_index") == index for row in observed)
            if failed_preflight and not dispatched:
                report.setdefault("fixture_preflight_failures", []).append(previous)
                del report["fixture_attempts"][key]
                persist()
        if key not in report.get("fixture_attempts", {}):
            offset = log.stat().st_size
            report.setdefault("fixture_attempts", {})[key] = {
                "start": offset, "publication_attempted": True,
            }
            persist()
            wire = args.fixture_reject if decision == "reject" else args.fixture_accept
            publication = session._publish_atomic_request(
                wire + "\n", args.prefix + "_" + key,
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
                            if row.get("request_id") in {"peace_inbound_fixture", "peace_country_inbound_fixture"}
                            and row.get("reason")), None)
            if failure:
                report["fixture_attempts"][key]["native_failure_reason"] = failure
                persist()
                raise RuntimeError("NATIVE_FIXTURE_PREFLIGHT:" + failure)
            time.sleep(0.2)
        artifact(key + "-proposals", proposals)
        if len(proposals) != 1:
            raise RuntimeError("UNIQUE_NATIVE_COUNTRY_PROPOSAL_REQUIRED")
        proposal = proposals[0]
        context = proposal.get("peace_context", {})
        if (context.get("war_id") != report["war_id"]
                or context.get("direction") != "offer"
                or not incoming_terms_match(context, args.kind)):
            raise RuntimeError("INCOMING_FULL_CLAUSE_CONTEXT_MISMATCH")
        report["steps"][key] = {"proposal": proposal}
        persist()
        return proposal

    try:
        health = wait_runtime_ready(session, timeout=25, restore_minimized=True)
        if health.get("status") != "ready":
            raise RuntimeError("SESSION_NOT_READY")
        if "before" not in report:
            control = _control_from_probe(_run_probe(
                PROBE_SPECS[0], session.record["pid"], evidence / "before-control.json"))
            if not _control_is_paused_por(control, health.get("date_raw")):
                raise RuntimeError("PAUSED_POR_CONTEXT_REQUIRED")
            report["before"] = control
            report["before_effect_probe"] = effect_probe("before-effects")
            persist()
        with DurableJournal(evidence / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            recipient = scenario["outbound_recipient"]
            if "queries" not in report["steps"]:
                discovery = artifact(
                    "war-discovery",
                    api.inspect_diplomatic_action("white_peace", "FRA", recipient,
                                                   parameters={}),
                )
                war = _single_discovered_war_id(discovery, "FRA", recipient)
                if war is None:
                    raise RuntimeError("UNIQUE_WAR_REQUIRED")
                report["war_id"] = war
                params = parameters(war, "demand", args.kind)
                inspection = artifact(
                    "country-demand",
                    api.inspect_diplomatic_action(
                        scenario["primary_action"], "FRA", recipient,
                        parameters=params),
                )
                # Resuming an already-submitted outbound offer must not depend
                # on whether another new offer could be sent after loading.
                if prior_outbound is None:
                    require_available(inspection)
                report["steps"]["queries"] = [{
                    "actor": "FRA", "recipient": recipient,
                    "primary_action": scenario["primary_action"],
                    "parameters": params, "inspection": inspection,
                }]
                persist()
            if STAGES.index(args.through) >= 1 and "outbound" not in report["steps"]:
                if prior_outbound is not None:
                    source_meta = {
                        key: prior_outbound[key]
                        for key in ("path", "prefix", "session_id", "request_id",
                                    "kind", "status", "submitted")
                    }
                    report["steps"]["outbound"] = {
                        "status": "rejected", "result": deepcopy(prior_outbound["result"]),
                        "reused": True, "source": source_meta,
                    }
                    report["business_attempts"]["outbound"] = {
                        "reused": True, "submitted": True,
                        "source_report_path": prior_outbound["path"],
                        "source_request_id": prior_outbound["request_id"],
                        "source_session_id": prior_outbound["session_id"],
                    }
                    artifact("outbound-reused-source", {
                        "source": source_meta,
                        "result": prior_outbound["result"],
                    })
                else:
                    final = execute_once(
                        api, "outbound", scenario["primary_action"], "FRA", recipient,
                        "initiate", parameters(report["war_id"], "demand", args.kind))
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
                    inspection = artifact(
                        decision + "-inspection",
                        api.inspect_diplomatic_action(
                            "peace_offer", scenario["incoming_actor"], "FRA",
                            phase=decision, parameters=params),
                    )
                    require_available(inspection)
                final = execute_once(
                    api, decision, "peace_offer", scenario["incoming_actor"], "FRA",
                    decision, params)
                expected_status = "accepted" if decision == "accept" else "rejected"
                if final.get("status") != expected_status:
                    raise RuntimeError("CONTROLLED_RESPONSE_NOT_OBSERVED_" + expected_status.upper())
                if final.get("result", {}).get("pending_removed") is not True:
                    raise RuntimeError("NATIVE_PENDING_REMOVAL_NOT_VERIFIED")
                report["steps"][decision] = {"status": expected_status, "result": final}
                persist()
            if args.through == "finish" and "finish" not in report["steps"]:
                report["after_effect_probe"] = effect_probe("after-effects")
                after = _control_from_probe(_run_probe(
                    PROBE_SPECS[0], session.record["pid"], evidence / "after-control.json"))
                report["after"] = after
                if not _control_is_paused_por(after, session.health().get("date_raw")):
                    raise RuntimeError("BATCH_END_PAUSED_POR_REQUIRED")
                command("save", [sys.executable, "-B", "tools/save_observer_experiment.py",
                                 "--installation", str(args.installation.resolve()),
                                 "--name", args.save_name])
                report["steps"]["finish"] = {"saved_name": args.save_name}
                persist()
        report["status"] = "passed" if args.through == "finish" else "stage_passed"
        report["through"] = args.through
    except Exception as error:
        report.update(status="failed", error=f"{type(error).__name__}:{error}")
    finally:
        raw = read_slice(log, report["native_log_start"])
        (evidence / "native-events-slice.jsonl").write_bytes(raw)
        report["native_event_slice"] = {
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
        }
        persist()
    print(json.dumps({key: report.get(key) for key in
                      ("status", "through", "kind", "war_id", "error")},
                     ensure_ascii=False))
    return 0 if report["status"] in {"passed", "stage_passed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
