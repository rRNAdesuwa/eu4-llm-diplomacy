"""Answer one native pending relation proposal through the four public tools.

Use an independently loaded, paused POR test campaign with a fresh r22 observer.
This script does not start, install, advance or save the game.  The optional
legacy TEST_ONLY source sends SAV's native proposal.  Support Independence and
Military Access and Vassalization tests may select another three-letter source
actor; the fixture still does not choose FRA's response.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from work.local_config import game_exe
from work.observer_runtime_ready import wait_runtime_ready
from work.run_alliance_execution import (
    ExperimentStop, _copy_log_slice, _dissolve_selector_check, _poll_result,
    _sha256_file, _stable_result, _write_json,
)
from work.validate_alliance_queries import PROBE_SPECS, _run_probe


def control_snapshot(pid: int, path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    spec = next(spec for spec in PROBE_SPECS if spec.name == "control_state")
    result = _run_probe(spec, pid, path)
    if result.get("snapshot_completeness", {}).get("complete") is not True:
        raise ExperimentStop("CONTROL_SNAPSHOT_INCOMPLETE", str(path))
    return result["snapshot"]


def _support_response_event(log_path: Path, start: int, request_id: str,
                           actor: str, decision: str,
                           action_id: str = "support_independence",
                           family: str = "support_independence") -> dict | None:
    """Read one bounded raw relation response event from the native log.

    The public bridge result intentionally exposes the stable response fields;
    pending_removed is additionally verified here against the native event so
    the operator does not infer queue removal from the public status alone.
    """

    if start < 0 or not log_path.is_file():
        return None
    maximum = 8 * 1024 * 1024
    consumed = 0
    pending = b""
    try:
        with log_path.open("rb") as stream:
            stream.seek(start)
            while consumed < maximum:
                chunk = stream.read(min(64 * 1024, maximum - consumed))
                if not chunk:
                    break
                consumed += len(chunk)
                pending += chunk
                complete_end = pending.rfind(b"\n")
                if complete_end < 0:
                    continue
                complete = pending[:complete_end + 1]
                pending = pending[complete_end + 1:]
                for raw_line in complete.splitlines():
                    try:
                        event = json.loads(raw_line.decode("utf-8"))
                    except (UnicodeDecodeError, ValueError):
                        continue
                    if not isinstance(event, dict):
                        continue
                    if all(event.get(field) == expected for field, expected in (
                            ("event", "native_diplomacy_relation_response_result"),
                            ("request_id", request_id),
                            ("action_id", action_id),
                            ("actor", actor), ("recipient", "FRA"),
                            ("phase", decision),
                            ("family", family))):
                        return event
    except OSError:
        return None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", required=True, type=Path)
    parser.add_argument("--decision", required=True, choices=("accept", "reject"))
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--actor", default="SAV")
    parser.add_argument("--action-id", choices=(
        "offer_alliance", "offer_royal_marriage", "support_independence",
        "ask_military_access", "offer_vassalization"),
                        default="offer_alliance")
    parser.add_argument("--generate-test-proposal", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", args.request_id):
        parser.error("Invalid request ID")
    if not re.fullmatch(r"[A-Z0-9]{3}", args.actor) or args.actor == "FRA":
        parser.error("Invalid original proposal actor")
    if args.generate_test_proposal and args.action_id not in (
            "support_independence", "ask_military_access", "offer_vassalization") \
            and args.actor != "SAV":
        parser.error("The native TEST_ONLY source supports SAV only")
    installation = args.installation.resolve(strict=True)
    directory = installation.parent
    artifact = directory / ("inbound-response-" + uuid.uuid4().hex)
    artifact.mkdir()
    log = directory / "control-probe.jsonl"
    log_start = None
    report = {"status": "unknown", "decision": args.decision,
              "request_id": args.request_id, "actor": args.actor, "action_id": args.action_id,
              "family": "military_access" if args.action_id == "ask_military_access"
              else "support_independence" if args.action_id == "support_independence"
              else "vassalization" if args.action_id == "offer_vassalization"
              else "royal_marriage" if args.action_id == "offer_royal_marriage" else "alliance",
              "test_source": args.generate_test_proposal, "checks": {}}
    try:
        session = ObserverSession(installation, game_exe())
        report["installation"] = _sha256_file(installation)
        report["manifest"] = _sha256_file(directory / "build-manifest.json")
        report["session_id"] = session.session_id
        log_start = log.stat().st_size
        health = wait_runtime_ready(session, restore_minimized=True)
        before = control_snapshot(int(session.record["pid"]), artifact / "before-control.json")
        report["before"] = {"health": health, "control": before}
        if (health.get("status") != "ready" or before.get("player_slot") != 189
                or before.get("paused_flag") != 1
                or health.get("date_raw") != before.get("date_raw")):
            raise ExperimentStop("BASELINE_NOT_READY_POR_PAUSED", "Control snapshot")
        marriage=args.action_id == "offer_royal_marriage"
        support=args.action_id == "support_independence"
        military=args.action_id == "ask_military_access"
        vassalization=args.action_id == "offer_vassalization"
        capability=("native_inbound_military_access_response" if military
                    else "native_inbound_support_independence_response" if support
                    else "native_inbound_vassalization_response" if vassalization
                    else "native_inbound_royal_marriage_response" if marriage
                    else "native_inbound_alliance_response")
        if capability not in session.installation_capabilities():
            raise ExperimentStop("INBOUND_RESPONSE_CAPABILITY_MISSING", "Installation ACK")
        journal_path = artifact / "diplomacy.sqlite3"
        with DurableJournal(journal_path, session.experiment_id, session.session_id,
                            global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            if args.generate_test_proposal:
                # Exclusive creation prevents an accidental second fixture send.
                with (directory / "alliance-inbound-test.req").open("xb") as request:
                    if support:
                        request.write(f"TEST_ONLY SUPPORT_TO_FRA {args.actor}\n".encode("ascii"))
                    elif military:
                        request.write(f"TEST_ONLY MILITARY_ACCESS_TO_FRA {args.actor}\n".encode("ascii"))
                    elif vassalization:
                        request.write(f"TEST_ONLY VASSALIZATION_TO_FRA {args.actor}\n".encode("ascii"))
                    else:
                        request.write(b"TEST_ONLY SAV_ROYAL_TO_FRA\n" if marriage
                                      else b"TEST_ONLY SAV_TO_FRA\n")
            deadline = time.monotonic() + 10
            proposals = []
            while time.monotonic() < deadline:
                catalog = api.list_diplomatic_actions(recipient="FRA")
                proposals = [item for item in catalog.get("incoming_proposals", [])
                             if item.get("actor") == args.actor
                             and item.get("action_id") == args.action_id]
                if proposals:
                    break
                time.sleep(0.2)
            if len(proposals) != 1:
                raise ExperimentStop("UNIQUE_INBOUND_PROPOSAL_NOT_FOUND", str(len(proposals)))
            proposal = proposals[0]
            report["proposal"] = proposal
            parameters = {"proposal_id": proposal["proposal_id"]}
            inspection = api.inspect_diplomatic_action(
                args.action_id, args.actor, "FRA", args.decision, parameters)
            report["inspection"] = inspection
            if support or military or vassalization:
                inspection_parameters = inspection.get("parameters") \
                    if isinstance(inspection, dict) else None
                requested_parameters = inspection_parameters.get("requested") \
                    if isinstance(inspection_parameters, dict) else {}
                report["public_request_check"] = {
                    "phase": isinstance(inspection, dict)
                    and inspection.get("phase") == args.decision,
                    "action_id": isinstance(inspection, dict)
                    and inspection.get("action_id") == args.action_id,
                    "actor": isinstance(inspection, dict)
                    and inspection.get("actor") == args.actor,
                    "recipient": isinstance(inspection, dict)
                    and inspection.get("recipient") == "FRA",
                    "proposal_id": isinstance(requested_parameters, dict)
                    and requested_parameters.get("proposal_id") == proposal.get("proposal_id"),
                }
            execution = api.execute_diplomatic_action(
                args.request_id, args.action_id, args.actor, "FRA", args.decision,
                parameters=parameters)
            report["execution"] = execution
            poll = _poll_result(api, args.request_id) if execution.get("submitted") is True else {
                "final": api.get_diplomatic_result(args.request_id), "terminal": False}
            report["poll"] = poll
            final = poll["final"]
            expected = "accepted" if args.decision == "accept" else "rejected"
            selector_action = (
                "cancel_military_access" if military
                else "revoke_support_independence" if support
                else "cancel_vassalization" if vassalization
                else "break_royal_ties" if marriage else "dissolve_alliance"
            )
            selector_actor, selector_recipient = (
                (args.actor, "FRA") if military else ("FRA", args.actor)
            )
            selector = api.inspect_diplomatic_action(
                selector_action, selector_actor, selector_recipient
            )
            report["selector"] = selector
            if support or military or vassalization:
                relationship = selector.get("relationship_state") \
                    if isinstance(selector, dict) else None
                relation_key = (
                    "military_access_active" if military
                    else "support_independence_active" if support
                    else "vassal_active"
                )
                active = relationship.get(relation_key) \
                    if isinstance(relationship, dict) else None
                complete = relationship.get("complete") is True \
                    if isinstance(relationship, dict) else False
                report["selector_check"] = {
                    "source": "relationship_state",
                    relation_key: active,
                    "complete": complete,
                    "consistent": (
                        complete and active is (args.decision == "accept")
                    ),
                }
                if vassalization:
                    actor_is_overlord = selector.get("actor_is_overlord") \
                        if isinstance(selector, dict) else None
                    actor_is_subject = selector.get("actor_is_subject") \
                        if isinstance(selector, dict) else None
                    subject_type = selector.get("subject_type") \
                        if isinstance(selector, dict) else None
                    roles_expected = (
                        actor_is_overlord is False
                        and actor_is_subject is True
                        and subject_type == "vassal"
                        if args.decision == "accept"
                        else actor_is_overlord is False
                        and actor_is_subject is False
                        and subject_type is None
                    )
                    report["selector_check"].update({
                        "query_actor": selector_actor,
                        "query_recipient": selector_recipient,
                        "expected_overlord": args.actor,
                        "expected_subject": "FRA",
                        "actor_is_overlord": actor_is_overlord,
                        "actor_is_subject": actor_is_subject,
                        "subject_type": subject_type,
                        "roles_and_type_consistent": roles_expected,
                        "consistent": (
                            report["selector_check"]["consistent"]
                            and roles_expected
                        ),
                    })
            elif marriage:
                from work.run_royal_marriage_execution import _break_selector_relation
                relation = _break_selector_relation(selector)
                report["selector_check"] = {**relation, "consistent":
                    relation.get("selector_consistent") is True
                    and relation.get("royal_marriage") is (args.decision == "accept")}
            else:
                report["selector_check"] = _dissolve_selector_check(selector, expected)
            if support or military or vassalization:
                response_action = args.action_id
                response_family = (
                    "military_access" if military
                    else "support_independence" if support
                    else "vassalization"
                )
                relation_before_key = (
                    "military_access_before" if military
                    else "support_independence_before" if support
                    else "vassalization_before"
                )
                relation_after_key = (
                    "military_access_after" if military
                    else "support_independence_after" if support
                    else "vassalization_after"
                )
                raw_event = _support_response_event(
                    log, log_start if log_start is not None else -1,
                    args.request_id, args.actor, args.decision,
                    response_action, response_family)
                public = final.get("result") if isinstance(final, dict) else None
                expected_state = 2 if args.decision == "accept" else 1
                expected_after = args.decision == "accept"
                report["native_response_event"] = raw_event
                report["native_response_check"] = {
                    "event_present": isinstance(raw_event, dict),
                    "event_contract": isinstance(raw_event, dict) and all(
                        raw_event.get(field) == value for field, value in (
                            ("event", "native_diplomacy_relation_response_result"),
                            ("request_id", args.request_id),
                            ("action_id", response_action),
                            ("actor", args.actor), ("recipient", "FRA"),
                            ("phase", args.decision),
                            ("family", response_family),
                        )),
                    "pending_removed": isinstance(raw_event, dict)
                    and raw_event.get("pending_removed") is True,
                    "native_variant_state": isinstance(raw_event, dict)
                    and isinstance(raw_event.get("native_variant"), int)
                    and not isinstance(raw_event.get("native_variant"), bool)
                    and raw_event.get("native_variant") == 1
                    and isinstance(raw_event.get("native_state"), int)
                    and not isinstance(raw_event.get("native_state"), bool)
                    and raw_event.get("native_state") == expected_state,
                    "relation_before_after": isinstance(raw_event, dict)
                    and raw_event.get(relation_before_key) is False
                    and raw_event.get(relation_after_key) is expected_after,
                }
                public_pending_removed = (
                    public.get("pending_removed") is True
                    if isinstance(public, dict) and "pending_removed" in public else None
                )
                report["public_response_check"] = {
                    "event": isinstance(public, dict)
                    and public.get("event") == "native_diplomacy_relation_response_result",
                    "phase": isinstance(public, dict)
                    and public.get("phase") == args.decision,
                    "proposal_id_bound": all(report.get("public_request_check", {}).values()),
                    "family": isinstance(public, dict)
                    and public.get("family") == response_family,
                    "native_variant_state": isinstance(public, dict)
                    and isinstance(public.get("native_variant"), int)
                    and not isinstance(public.get("native_variant"), bool)
                    and public.get("native_variant") == 1
                    and isinstance(public.get("native_state"), int)
                    and not isinstance(public.get("native_state"), bool)
                    and public.get("native_state") == expected_state,
                    "relation_before_after": isinstance(public, dict)
                    and public.get(relation_before_key) is False
                    and public.get(relation_after_key) is expected_after,
                    "response_verified": isinstance(public, dict)
                    and public.get("response_verified") is True
                    and public.get("request_binding_verified") is True,
                    "pending_removed_if_public": public_pending_removed in (None, True),
                }
        with DurableJournal(journal_path, session.experiment_id, session.session_id,
                            global_request_ids=True) as journal:
            persisted = DiplomacyTools(journal, session).get_diplomatic_result(args.request_id)
        after = control_snapshot(int(session.record["pid"]), artifact / "after-control.json")
        after_health = session.health()
        report["after"] = {"control": after, "health": after_health}
        report["persisted"] = persisted
        report["checks"] = {
            "submitted": execution.get("submitted") is True,
            "actual_response": final.get("status") == expected and final.get("game_outcome") == expected,
            "native_relationship_matches_decision": report["selector_check"].get("consistent") is True,
            "journal_survives_reopen": _stable_result(final) == _stable_result(persisted),
            "player_por_paused_same_date": after.get("player_slot") == 189
                and after.get("paused_flag") == 1 and after.get("date_raw") == before.get("date_raw"),
            "health_ready": after_health.get("status") == "ready",
            "support_native_response_verified": (
                all(report.get("native_response_check", {}).values())
                and all(report.get("public_response_check", {}).values())
                if support else True
            ),
            "military_native_response_verified": (
                all(report.get("native_response_check", {}).values())
                and all(report.get("public_response_check", {}).values())
                if military else True
            ),
            "vassalization_native_response_verified": (
                all(report.get("native_response_check", {}).values())
                and all(report.get("public_response_check", {}).values())
                if vassalization else True
            ),
        }
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        if log_start is not None:
            report["native_events"] = _copy_log_slice(log, log_start, artifact / "native-events.jsonl")
        _write_json(artifact / "report.json", report)
    print(json.dumps({"status": report["status"], "artifact": str(artifact)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
