"""Answer one pending Peace offer through the public inbound-response API.

The operator is deliberately single-use.  It discovers exactly one opaque
``peace_offer`` proposal from ENG to the controlled FRA country, inspects the
proposal, calls the public response operation once, and polls that same
request id.  It never fabricates a proposal id, retries a request, advances
time, saves the game, or starts a game process.

``--output`` is the report JSON path.  A sibling ``*-evidence`` directory is
created for the four before/after probes, public request records, and the
bounded native-log slice.
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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession  # noqa: E402
from bridge.diplomacy_journal import DurableJournal, UnknownRequestError  # noqa: E402
from work.local_config import game_exe  # noqa: E402
from work.observer_runtime_ready import wait_runtime_ready  # noqa: E402
from work.run_alliance_execution import (  # noqa: E402
    _copy_log_slice,
    _poll_result,
    _sha256_file,
    _write_json,
)
from work.run_peace_authority_test import _snapshot_stability  # noqa: E402
from work.run_royal_marriage_execution import (  # noqa: E402
    _installation_binding,
    _public_probe_records,
    _snapshots_complete,
)
from work.validate_alliance_reload import (  # noqa: E402
    _control_summary,
    _run_snapshots,
)


_ACTION = "peace_offer"
_FAMILY = "peace"
_ACTOR = "ENG"
_RECIPIENT = "FRA"
_PLAYER_SLOT = 189  # POR in the paused observer fixture
_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_PUBLIC_ID_RE = re.compile(r"[0-9a-f]{32}\Z")
_POLL_SECONDS = 20.0
_DISCOVERY_SECONDS = 10.0
_REMOVAL_SECONDS = 5.0
_MAX_LOG_BYTES = 8 * 1024 * 1024
_MAX_LINE_BYTES = 256 * 1024
_RESPONSE_EVENTS = frozenset({
    "native_diplomacy_relation_response_result",
    "native_peace_response_result",
    "native_peace_inbound_response_result",
    "native_alliance_response_result",
})
_HANDLER_EVENTS = frozenset({
    "native_peace_response_entry",
    "native_peace_handler_entry",
    "native_peace_inbound_response_entry",
    "native_diplomacy_inbound_response_entry",
})


class PeaceInboundResponseError(RuntimeError):
    """A bounded operator stop with a stable report code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _public_catalog(value: object) -> dict[str, object]:
    """Return the public catalog without adding private native context."""

    if not isinstance(value, dict):
        return {"status": "unknown", "incoming_proposals": [],
                "incoming_proposals_complete": False}
    proposals = value.get("incoming_proposals")
    if not isinstance(proposals, list):
        proposals = []
    return {
        "incoming_proposals": proposals,
        "incoming_proposals_complete": value.get("incoming_proposals_complete"),
        "action_count": value.get("action_count"),
        "category": value.get("category"),
    }


def _peace_proposals(catalog: object) -> list[dict[str, object]]:
    if not isinstance(catalog, dict):
        return []
    rows = catalog.get("incoming_proposals")
    if not isinstance(rows, list):
        return []
    result: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if (row.get("action_id") == _ACTION
                and row.get("family") == _FAMILY
                and row.get("actor") == _ACTOR
                and row.get("recipient") == _RECIPIENT
                and row.get("decision_country") == _RECIPIENT
                and row.get("observer_status") == "observed_pending"):
            result.append(row)
    return result


def _proposal_contract(proposal: object) -> bool:
    return (
        isinstance(proposal, dict)
        and isinstance(proposal.get("proposal_id"), str)
        and _PUBLIC_ID_RE.fullmatch(proposal["proposal_id"]) is not None
        and proposal.get("action_id") == _ACTION
        and proposal.get("family") == _FAMILY
        and proposal.get("actor") == _ACTOR
        and proposal.get("recipient") == _RECIPIENT
        and proposal.get("decision_country") == _RECIPIENT
        and proposal.get("phase") == "initiate"
        and proposal.get("observer_status") == "observed_pending"
    )


def _inspection_contract(inspection: object, proposal_id: str,
                         decision: str) -> dict[str, bool]:
    """Check the public binding and the Peace-specific war precondition."""

    if not isinstance(inspection, dict):
        return {"object": False, "binding": False, "war_before": False,
                "response_rules": False, "payload": False,
                "preflight_available": False}
    parameters = inspection.get("parameters")
    requested = parameters.get("requested") if isinstance(parameters, dict) else None
    actual = parameters.get("actual") if isinstance(parameters, dict) else None
    legality = inspection.get("legality")
    authorization = inspection.get("authorization")
    return {
        "object": True,
        "binding": (
            inspection.get("action_id") == _ACTION
            and inspection.get("family") == _FAMILY
            and inspection.get("actor") == _ACTOR
            and inspection.get("recipient") == _RECIPIENT
            and inspection.get("phase") == decision
            and isinstance(requested, dict)
            and requested.get("proposal_id") == proposal_id
            and (actual is None or (
                isinstance(actual, dict) and actual.get("proposal_id") == proposal_id))
            and inspection.get("decision_country") == _RECIPIENT
            and inspection.get("decision_country_verified") is True
        ),
        "war_before": inspection.get("war_before") is True,
        "response_rules": (
            isinstance(inspection.get("native_inbound_inspection"), dict)
            and inspection["native_inbound_inspection"].get("response_rules_complete") is True
        ),
        "payload": (
            inspection.get("peace_payload_complete") is True
            and inspection.get("selected_terms_complete") is True
        ),
        "preflight_available": (
            isinstance(legality, dict) and legality.get("status") == "available"
            and isinstance(authorization, dict)
            and authorization.get("status") == "available"
        ),
    }


def _read_events(path: Path) -> list[dict[str, object]]:
    """Read at most one bounded, newline-delimited native-log slice."""

    events: list[dict[str, object]] = []
    if not path.is_file():
        return events
    consumed = 0
    pending = b""
    with path.open("rb") as stream:
        while consumed < _MAX_LOG_BYTES:
            chunk = stream.read(min(64 * 1024, _MAX_LOG_BYTES - consumed))
            if not chunk:
                break
            consumed += len(chunk)
            pending += chunk
            lines = pending.split(b"\n")
            pending = lines.pop()
            for raw in lines:
                if not raw or len(raw) > _MAX_LINE_BYTES:
                    continue
                try:
                    value = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if isinstance(value, dict):
                    events.append(value)
    return events


def _event_matches(event: object, request_id: str, session_id: str,
                   decision: str, *, require_action: bool = True) -> bool:
    if not isinstance(event, dict):
        return False
    if (event.get("request_id") != request_id
            or event.get("session_id") != session_id
            or event.get("phase") != decision):
        return False
    if require_action and event.get("action_id") != _ACTION:
        return False
    if event.get("action_id") not in (None, _ACTION):
        return False
    if event.get("family") not in (None, _FAMILY):
        return False
    if event.get("actor") not in (None, _ACTOR):
        return False
    if event.get("recipient") not in (None, _RECIPIENT):
        return False
    return True


def _bool_from_events(events: list[dict[str, object]], keys: tuple[str, ...]) -> bool | None:
    for event in events:
        for key in keys:
            value = event.get(key)
            if isinstance(value, bool):
                return value
            if key.endswith("_count") and isinstance(value, int) and not isinstance(value, bool):
                return value > 0
    return None


def _payload_complete_from_events(events: list[dict[str, object]]) -> bool | None:
    direct = _bool_from_events(events, (
        "peace_payload_complete", "payload_complete", "native_payload_complete",
        "response_payload_complete", "source_payload_complete", "full_payload",
    ))
    if direct is not None:
        return direct
    for event in events:
        for key in ("peace_payload", "payload", "source_payload", "loaded_payload"):
            payload = event.get(key)
            if isinstance(payload, dict) and isinstance(payload.get("complete"), bool):
                return payload.get("complete")
    return None


def _native_response_contract(events: list[dict[str, object]], request_id: str,
                             session_id: str, decision: str) -> dict[str, object]:
    response_events = [
        event for event in events
        if event.get("event") in _RESPONSE_EVENTS
        and _event_matches(event, request_id, session_id, decision)
    ]
    handler_events = [
        event for event in events
        if (event.get("event") in _HANDLER_EVENTS
            or (isinstance(event.get("event"), str)
                and event["event"].startswith("native_peace_")
                and ("response" in event["event"] or "handler" in event["event"])))
        and _event_matches(event, request_id, session_id, decision,
                           require_action=False)
    ]
    response = response_events[0] if response_events else None
    handler_pool = handler_events + response_events
    expected_after = decision == "reject"
    response_contract = (
        isinstance(response, dict)
        and response.get("action_id") == _ACTION
        and response.get("family") == _FAMILY
        and response.get("actor") == _ACTOR
        and response.get("recipient") == _RECIPIENT
        and response.get("response_verified") is True
        and response.get("request_binding_verified") is True
        and response.get("pending_removed") is True
        and response.get("war_before") is True
        and response.get("war_after") is expected_after
    )
    forwarded = _bool_from_events(handler_pool, (
        "handler_forwarded", "native_handler_forwarded", "native_forwarded",
        "forwarded", "call_redirected", "native_forward_count", "forward_count",
    ))
    consumed = _bool_from_events(handler_pool, (
        "handler_consumed", "native_handler_consumed", "response_consumed",
        "pending_consumed", "consumed", "native_consume_count", "consume_count",
    ))
    payload_complete = _payload_complete_from_events(handler_pool)
    return {
        "response_event": response,
        "response_event_count": len(response_events),
        "handler_event_count": len(handler_events),
        "response_event_contract": response_contract,
        "response_verified": isinstance(response, dict)
        and response.get("response_verified") is True,
        "request_binding_verified": isinstance(response, dict)
        and response.get("request_binding_verified") is True,
        "pending_removed": isinstance(response, dict)
        and response.get("pending_removed") is True,
        "war_before": isinstance(response, dict) and response.get("war_before") is True,
        "war_after": (response.get("war_after") if isinstance(response, dict) else None),
        "handler_event_present": bool(handler_events) or any(
            key in response for key in (
                "handler_forwarded", "handler_consumed", "native_forwarded",
                "native_handler_consumed", "payload_complete",
                "peace_payload_complete")
        ) if isinstance(response, dict) else bool(handler_events),
        "handler_forwarded": forwarded is True,
        "handler_consumed": consumed is True,
        "full_payload": payload_complete is True,
        "contract": (
            response_contract and forwarded is True and consumed is True
            and payload_complete is True
        ),
    }


def _find_public_response(final: object) -> dict[str, object] | None:
    """Find the public response projection without treating inspection as result."""

    pending: list[object] = [final]
    seen: set[int] = set()
    while pending:
        value = pending.pop(0)
        if not isinstance(value, dict) or id(value) in seen:
            continue
        seen.add(id(value))
        if (value.get("action_id") == _ACTION
                and ("war_before" in value or "war_after" in value
                     or "pending_removed" in value)):
            return value
        for key in ("result", "response", "native_result"):
            child = value.get(key)
            if isinstance(child, dict):
                pending.append(child)
    return None


def _public_response_contract(final: object, decision: str,
                              proposal_id: str) -> dict[str, bool]:
    response = _find_public_response(final)
    expected_after = decision == "reject"
    return {
        "object": isinstance(response, dict),
        "action_and_family": isinstance(response, dict)
        and response.get("action_id") == _ACTION
        and response.get("family") == _FAMILY,
        "proposal_id_bound": isinstance(response, dict)
        and response.get("proposal_id", proposal_id) == proposal_id,
        "war_before": isinstance(response, dict) and response.get("war_before") is True,
        "war_after": isinstance(response, dict)
        and response.get("war_after") is expected_after,
        "pending_removed": isinstance(response, dict)
        and response.get("pending_removed") is True,
        "response_verified": isinstance(response, dict)
        and response.get("response_verified") is True
        and response.get("request_binding_verified") is True,
    }


def _war_pair_summary(probes: object) -> dict[str, object]:
    """Extract the reviewed FRA/ENG pair state from the war probe schema.

    ``probe_war_pair.py`` identifies FRA and ENG by their reviewed country
    slots (122 and 46) and exposes the semantic ``pair_at_war`` boolean for
    each side.  No pointer, opaque war reference, or API text is interpreted
    here.
    """

    if not isinstance(probes, dict):
        return {"complete": False, "fra_pair_at_war": None,
                "eng_pair_at_war": None, "pair_at_war": None}
    entry = probes.get("war_state")
    snapshot = entry.get("snapshot") if isinstance(entry, dict) else None
    countries = snapshot.get("countries") if isinstance(snapshot, dict) else None
    if not isinstance(countries, list):
        return {"complete": False, "fra_pair_at_war": None,
                "eng_pair_at_war": None, "pair_at_war": None}
    by_slot: dict[int, dict[str, object]] = {}
    for country in countries:
        if not isinstance(country, dict):
            continue
        slot = country.get("slot")
        if isinstance(slot, int) and not isinstance(slot, bool):
            by_slot[slot] = country
    fra = by_slot.get(122)
    eng = by_slot.get(46)
    fra_value = fra.get("pair_at_war") if isinstance(fra, dict) else None
    eng_value = eng.get("pair_at_war") if isinstance(eng, dict) else None
    complete = type(fra_value) is bool and type(eng_value) is bool
    return {
        "complete": complete,
        "fra_pair_at_war": fra_value,
        "eng_pair_at_war": eng_value,
        "pair_at_war": (fra_value is True and eng_value is True)
        if complete else None,
        "both_pair_at_peace": snapshot.get("both_pair_at_peace")
        if isinstance(snapshot, dict) else None,
    }


def _wait_for_catalog(api: DiplomacyTools, seconds: float) -> dict[str, object]:
    deadline = time.monotonic() + seconds
    catalog: dict[str, object] = {}
    while time.monotonic() < deadline:
        value = api.list_diplomatic_actions(recipient=_RECIPIENT)
        catalog = _public_catalog(value)
        if not _peace_proposals(catalog):
            break
        time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))
    return catalog


def _output_paths(output: Path) -> tuple[Path, Path]:
    report_path = output.expanduser().resolve()
    if report_path.exists():
        raise PeaceInboundResponseError("OUTPUT_EXISTS", str(report_path))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    artifact = report_path.parent / f"{report_path.stem}-evidence"
    if artifact.exists():
        raise PeaceInboundResponseError("EVIDENCE_DIRECTORY_EXISTS", str(artifact))
    artifact.mkdir()
    return report_path, artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--decision", choices=("accept", "reject"), required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="unique report JSON path; sibling evidence directory is created")
    args = parser.parse_args(argv)
    if _REQUEST_ID_RE.fullmatch(args.request_id) is None:
        parser.error("request-id must contain only ASCII letters, digits, '_' or '-' (1..64)")

    try:
        output, artifact = _output_paths(args.output)
    except PeaceInboundResponseError as error:
        parser.error(f"{error.code}: {error.message}")
    installation = args.installation.expanduser().resolve(strict=True)
    log = installation.parent / "control-probe.jsonl"
    report: dict[str, object] = {
        "validator": Path(__file__).name,
        "version": 1,
        "status": "running",
        "mode": "public_peace_inbound_response",
        "installation_path": str(installation),
        "output": str(output),
        "artifact": str(artifact),
        "action_id": _ACTION,
        "family": _FAMILY,
        "actor": _ACTOR,
        "recipient": _RECIPIENT,
        "decision": args.decision,
        "request_id": args.request_id,
        "execute_call_count": 0,
        "request_publish_count": 0,
        "checks": {},
    }
    session: ObserverSession | None = None
    log_start: int | None = None
    before: dict[str, object] | None = None
    after: dict[str, object] | None = None
    before_catalog: dict[str, object] | None = None
    after_catalog: dict[str, object] | None = None
    proposal: dict[str, object] | None = None
    inspection: dict[str, object] | None = None
    execution: dict[str, object] | None = None
    final: dict[str, object] | None = None
    try:
        session = ObserverSession(installation, game_exe())
        report["installation"] = _sha256_file(installation)
        manifest = installation.parent / "build-manifest.json"
        if manifest.is_file():
            report["manifest"] = _sha256_file(manifest)
        report["session"] = {
            "experiment_id": session.experiment_id,
            "session_id": session.session_id,
            "pid": session.record.get("pid"),
            "dll_sha256": session.record.get("dll_sha256"),
        }
        report.update(_installation_binding(installation))
        log_start = log.stat().st_size
        report["log_start_offset"] = log_start
        health = wait_runtime_ready(session, restore_minimized=True)
        before = _run_snapshots(session, artifact / "before-probes")
        before_control = _control_summary(before["control_state"]["snapshot"])
        report["before"] = {
            "health": health,
            "control": before_control,
            "probes": _public_probe_records(before),
        }
        if (health.get("status") != "ready"
                or not _snapshots_complete(before)
                or before_control.get("player_slot") != _PLAYER_SLOT
                or before_control.get("paused_flag") != 1
                or health.get("date_raw") != before_control.get("date_raw")):
            raise PeaceInboundResponseError(
                "BASELINE_NOT_READY_POR_PAUSED",
                "before probes did not prove a paused POR session at one date")
        if "native_inbound_peace_response" not in session.installation_capabilities():
            raise PeaceInboundResponseError(
                "INBOUND_PEACE_RESPONSE_CAPABILITY_MISSING",
                "installation does not advertise the Peace inbound-response adapter")

        journal_path = artifact / "diplomacy.sqlite3"
        with DurableJournal(journal_path, session.experiment_id, session.session_id,
                            global_request_ids=True) as journal:
            try:
                journal.lookup_request(args.request_id)
            except UnknownRequestError:
                report["request_id_unique"] = True
            else:
                raise PeaceInboundResponseError(
                    "REQUEST_ID_NOT_UNIQUE", args.request_id)
            api = DiplomacyTools(journal, session)
            before_catalog = _public_catalog(
                api.list_diplomatic_actions(recipient=_RECIPIENT))
            _write_json(artifact / "before-proposals.json", before_catalog)
            deadline = time.monotonic() + _DISCOVERY_SECONDS
            matches: list[dict[str, object]] = []
            while time.monotonic() < deadline:
                catalog = _public_catalog(
                    api.list_diplomatic_actions(recipient=_RECIPIENT))
                matches = _peace_proposals(catalog)
                if matches:
                    break
                time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))
            if len(matches) != 1 or not _proposal_contract(matches[0]):
                raise PeaceInboundResponseError(
                    "UNIQUE_PEACE_PROPOSAL_NOT_FOUND",
                    f"expected one valid ENG->FRA peace_offer, found {len(matches)}")
            proposal = matches[0]
            proposal_id = proposal["proposal_id"]
            report["proposal"] = proposal
            parameters = {"proposal_id": proposal_id}
            inspection = api.inspect_diplomatic_action(
                _ACTION, _ACTOR, _RECIPIENT, phase=args.decision,
                parameters=parameters)
            _write_json(artifact / "inspection.json", inspection)
            report["inspection"] = inspection
            inspection_checks = _inspection_contract(
                inspection, proposal_id, args.decision)
            report["inspection_checks"] = inspection_checks
            if not all(inspection_checks.values()):
                raise PeaceInboundResponseError(
                    "PEACE_INSPECTION_CONTRACT_INCOMPLETE",
                    json.dumps(inspection_checks, sort_keys=True))
            execution = api.execute_diplomatic_action(
                args.request_id, _ACTION, _ACTOR, _RECIPIENT,
                phase=args.decision, parameters=parameters)
            report["execute_call_count"] = 1
            report["request_publish_count"] = 1 if execution.get("submitted") is True else 0
            _write_json(artifact / "execution.json", execution)
            report["execution"] = execution
            if execution.get("submitted") is True:
                poll = _poll_result(api, args.request_id)
            else:
                poll = {"calls": 1, "status_history": [execution.get("status")],
                        "terminal": False,
                        "final": api.get_diplomatic_result(args.request_id)}
            report["poll"] = poll
            final = poll.get("final") if isinstance(poll, dict) else None
            if not isinstance(final, dict):
                final = api.get_diplomatic_result(args.request_id)
            _write_json(artifact / "result.json", final)
            report["result"] = final
            report["public_response"] = _find_public_response(final)
        with DurableJournal(journal_path, session.experiment_id, session.session_id,
                            global_request_ids=True) as reopened:
            persisted = DiplomacyTools(reopened, session).get_diplomatic_result(
                args.request_id)
        report["persisted"] = persisted
        # Re-open a proper journal for the removal observation so the SQLite
        # connection is always closed deterministically.
        with DurableJournal(journal_path, session.experiment_id, session.session_id,
                            global_request_ids=True) as after_journal:
            after_catalog = _wait_for_catalog(
                DiplomacyTools(after_journal, session), _REMOVAL_SECONDS)
        _write_json(artifact / "after-proposals.json", after_catalog)
        report["after_proposals"] = after_catalog
        report["after_pending_matches"] = _peace_proposals(after_catalog)
        after = _run_snapshots(session, artifact / "after-probes")
        after_control = _control_summary(after["control_state"]["snapshot"])
        report["after"] = {
            "health": session.health(),
            "control": after_control,
            "probes": _public_probe_records(after),
        }
    except PeaceInboundResponseError as error:
        report["status"] = "failed"
        report["error"] = {"code": error.code, "message": error.message}
    except Exception as error:  # keep a reviewable artifact for bridge failures
        report["status"] = "failed"
        report["error"] = {
            "code": "UNEXPECTED_OPERATOR_ERROR",
            "type": type(error).__name__,
            "message": str(error),
        }
    finally:
        if log_start is not None:
            report["native_events"] = _copy_log_slice(
                log, log_start, artifact / "native-events-slice.jsonl")
            native_path = artifact / "native-events-slice.jsonl"
            events = _read_events(native_path)
            session_id = session.session_id if session is not None else ""
            native = _native_response_contract(
                events, args.request_id, session_id, args.decision)
            report["native_response"] = native
        else:
            report["native_events"] = {
                "status": "not_started",
                "path": str(artifact / "native-events-slice.jsonl"),
                "bytes": 0,
            }
            native = {"contract": False, "response_event_count": 0,
                      "handler_event_count": 0}
            report["native_response"] = native

        before_control = report.get("before", {}).get("control") \
            if isinstance(report.get("before"), dict) else None
        after_control = report.get("after", {}).get("control") \
            if isinstance(report.get("after"), dict) else None
        public = report.get("public_response")
        public_checks = _public_response_contract(
            report.get("result"), args.decision,
            proposal.get("proposal_id") if isinstance(proposal, dict)
            else "")
        report["public_response_checks"] = public_checks
        expected_outcome = "accepted" if args.decision == "accept" else "rejected"
        final_value = report.get("result")
        final_status = final_value.get("status") if isinstance(final_value, dict) else None
        final_game_outcome = (
            final_value.get("game_outcome") if isinstance(final_value, dict) else None)
        stability = _snapshot_stability(before, after) if before and after else {}
        report["snapshot_stability"] = stability
        report["war_state_transition"] = {
            "before": _war_pair_summary(before),
            "after": _war_pair_summary(after),
            "expected_pair_at_war_after": args.decision == "reject",
        }
        # Diplomat queues and ordinary alliance rows are recorded for review;
        # an accepted Peace response may legitimately change them, so neither
        # is converted into a no-delta assertion here.
        report["allowed_probe_deltas"] = {
            "alliance_state_unchanged": stability.get("alliance_state_unchanged"),
            "diplomats_unchanged": stability.get("diplomats_unchanged"),
            "war_state_unchanged": stability.get("war_state_unchanged"),
        }
        war_before_probe = report["war_state_transition"]["before"]
        war_after_probe = report["war_state_transition"]["after"]
        report["checks"] = {
            "request_id_unique": report.get("request_id_unique") is True,
            "before_four_probes_complete": before is not None and _snapshots_complete(before),
            "after_four_probes_complete": after is not None and _snapshots_complete(after),
            "inspection_contract": all(report.get("inspection_checks", {}).values())
            if isinstance(report.get("inspection_checks"), dict) else False,
            "war_before": native.get("war_before") is True
            or public_checks.get("war_before") is True,
            "decision_outcome": final_status == expected_outcome
            and final_game_outcome == expected_outcome,
            "war_after": native.get("war_after") == (args.decision == "reject")
            or public_checks.get("war_after") is True,
            "war_state_transition": (
                isinstance(war_before_probe, dict)
                and isinstance(war_after_probe, dict)
                and war_before_probe.get("complete") is True
                and war_after_probe.get("complete") is True
                and war_before_probe.get("pair_at_war") is True
                and war_after_probe.get("pair_at_war")
                is (args.decision == "reject")
            ),
            # The native response is authoritative for queue removal.  The
            # public catalog is a bounded observer cursor and may retain a
            # previously seen opaque row, so keep that observation separate.
            "pending_removed": native.get("pending_removed") is True,
            "request_bound": native.get("request_binding_verified") is True
            and public_checks.get("response_verified") is True,
            "native_response_verified": native.get("response_verified") is True,
            "native_handler_forwarded": native.get("handler_forwarded") is True,
            "native_handler_consumed": native.get("handler_consumed") is True,
            "native_full_payload": native.get("full_payload") is True,
            "native_response_contract": native.get("contract") is True,
            "native_event_slice_complete": (
                isinstance(report.get("native_events"), dict)
                and report.get("native_events", {}).get("status") == "ok"
                and report.get("native_events", {}).get("complete") is True),
            "execute_once": report.get("execute_call_count") == 1,
            "poll_same_request": (
                isinstance(report.get("poll"), dict)
                and report.get("poll", {}).get("calls", 0) >= 1
                and report.get("request_id") == args.request_id),
            "por_paused_same_date": (
                isinstance(before_control, dict) and isinstance(after_control, dict)
                and before_control == after_control
                and before_control.get("player_slot") == _PLAYER_SLOT
                and before_control.get("paused_flag") == 1),
            # The current public catalog deliberately reports a bounded
            # observation as ``incoming_proposals_complete: false``.  The
            # removal claim is therefore bound to the native pending event
            # plus the successfully read public catalog, rather than treating
            # that bounded-catalog marker as a full-world enumeration claim.
            "public_pending_catalog_read": isinstance(after_catalog, dict),
        }
        if report.get("status") == "running":
            report["status"] = "passed" if all(report["checks"].values()) else "failed"
        _write_json(output, report)

    print(json.dumps({
        "status": report["status"],
        "report": str(output),
        "artifact": str(artifact),
        "request_id": args.request_id,
        "execute_call_count": report.get("execute_call_count"),
    }, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
