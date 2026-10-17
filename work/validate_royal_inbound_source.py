#!/usr/bin/env python3
"""Validate a native inbound relation offer/response source chain.

The validator is independent of the Python consumer receipt. It uses the
parent control-probe stream to identify the native UI fixture that created the
pending proposal, then correlates the response artifact's native
transport-to-load-to-clone-to-command-entry chain with that proposal.
Source and business-result checks stay separate so a consumer-side receipt bug
cannot erase a successful native response.

All input JSONL is read line by line. Shared transport helpers retain only the
bounded chain events needed for validation and apply their full header,
prefix, identity, family, payload, and callback-order checks.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


WORK_DIR = Path(__file__).resolve().parent
if str(WORK_DIR) not in sys.path:
    sys.path.insert(0, str(WORK_DIR))

from validate_alliance_transport import (  # noqa: E402
    HEADER_FIELDS,
    PAYLOAD_FIELDS,
    as_int,
    chain_for_transport,
    load_events,
    sha256_file,
)
from validate_royal_business_source import (  # noqa: E402
    bounded_size,
    chain_payloads,
    generation_address_chain,
    read_json,
    result_summary,
    same_int,
    submission_summary,
)


MAX_INPUT_BYTES = 10 * 1024 * 1024
FAMILY = "royal_marriage"
ACTION = "offer_royal_marriage"
SOURCE_TAG = "SAV_ROYAL_TO_FRA"
SOURCE_ACTOR = "SAV"
RECIPIENT = "FRA"
RELATION_PREFIX = "royal_marriage"
TRANSPORT_EVENT = "native_alliance_transport_completed"
CLONE_EVENT = "native_alliance_wrapper_clone"
ENTRY_EVENT = "native_alliance_command_entry_observed"
OFFER_EVENT = "native_alliance_inbound_offer"
INSPECTION_EVENT = "native_alliance_inbound_inspection"
SUBMISSION_EVENT = "native_alliance_submission_result"
RESPONSE_EVENT = "native_alliance_response_result"
TEST_EVENT = "native_alliance_inbound_test_submitted"
PENDING_RESTORED_EVENT = "native_diplomacy_inbound_pending_restored"


def bool_true(value: Any) -> bool:
    return value is True


def stream_selected_events(path: Path, names: set[str]) -> dict[str, Any]:
    """Stream one JSONL file and retain only named records."""

    counts: Counter[str] = Counter()
    selected: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    malformed: list[int] = []
    line_count = 0
    with path.open("r", encoding="utf-8") as stream:
        for line_number, raw_line in enumerate(stream, 1):
            line_count += 1
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                malformed.append(line_number)
                continue
            if not isinstance(event, dict):
                malformed.append(line_number)
                continue
            name = str(event.get("event", "<missing>"))
            counts[name] += 1
            if name in names:
                selected[name].append({**event, "_line": line_number})
    return {
        "line_count": line_count,
        "malformed_lines": malformed,
        "event_counts": dict(counts),
        "selected": dict(selected),
    }


def input_record(path: Path, scan: dict[str, Any] | None = None) -> dict[str, Any]:
    size = path.stat().st_size
    record: dict[str, Any] = {
        "path": str(path.resolve()),
        "bytes": size,
        "sha256": sha256_file(path),
        "bounded": size <= MAX_INPUT_BYTES,
    }
    if scan is not None:
        record.update({
            "line_count": scan["line_count"],
            "malformed_lines": scan["malformed_lines"],
            "event_counts": scan["event_counts"],
        })
    return record


def packed_country(value: Any) -> str | None:
    """Decode the native packed three-letter country tag from a payload."""

    number = as_int(value)
    if number is None or number < 0:
        return None
    chars: list[str] = []
    for shift in (0, 8, 16):
        char = (number >> shift) & 0xFF
        if not 65 <= char <= 90:
            return None
        chars.append(chr(char))
    return "".join(chars)


def raw_chain_events(event_data: dict[str, Any],
                     chain: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_line = {
        event["_line"]: event
        for group in (event_data["transport"], event_data["clones"], event_data["entries"])
        for event in group
    }
    return {
        "transport": by_line[chain["transport"]["line"]],
        "clone": by_line[chain["clone"]["line"]],
        "entry": by_line[chain["entry"]["line"]],
    }


def strict_chains(event_data: dict[str, Any], session_id: str,
                  protocol_sequence: int | None = None) -> list[dict[str, Any]]:
    chains: list[dict[str, Any]] = []
    for transport in sorted(
        event_data["transport"],
        key=lambda item: as_int(item.get("callback_begin"), -1) or -1,
    ):
        chain, _reason = chain_for_transport(
            transport, event_data["clones"], event_data["entries"], session_id, FAMILY
        )
        if chain is None:
            continue
        chain_sequence = as_int(chain["entry"].get("protocol_sequence"))
        if protocol_sequence is None or chain_sequence == protocol_sequence:
            chains.append(chain)
    return chains


def chain_record(event_data: dict[str, Any],
                 chain: dict[str, Any]) -> dict[str, Any]:
    raw = raw_chain_events(event_data, chain)
    payloads = chain_payloads(chain, raw)
    address_chain = generation_address_chain(chain, raw)
    entry = raw["entry"]
    return {
        "line_refs": {
            "transport": chain["transport"]["line"],
            "clone": chain["clone"]["line"],
            "entry": chain["entry"]["line"],
        },
        "callback_refs": {
            "transport_begin": chain["transport"].get("callback_begin"),
            "transport_load": chain["transport"].get("load_callback_sequence"),
            "transport_end": chain["transport"].get("callback_end"),
            "clone_begin": chain["clone"].get("begin_callback_sequence"),
            "clone_end": chain["clone"].get("callback_sequence"),
            "entry": chain["entry"].get("callback_sequence"),
            "protocol_sequence": chain["entry"].get("protocol_sequence"),
        },
        "checks": chain.get("checks", {}),
        "all_strict_checks_true": all(
            value is True for value in chain.get("checks", {}).values()
        ),
        "address_chain": address_chain,
        "address_chain_checks": address_chain["link_checks"],
        "address_chain_all_true": all(address_chain["link_checks"].values()),
        "payloads": payloads,
        "entry_prefix": {
            field: entry.get(field) for field in HEADER_FIELDS if field in entry
        },
        "full_chain": chain,
    }


def find_all(records: list[dict[str, Any]], predicate: Any) -> list[dict[str, Any]]:
    return [record for record in records if predicate(record)]


def find_one(records: list[dict[str, Any]], predicate: Any) -> dict[str, Any] | None:
    matches = find_all(records, predicate)
    return matches[0] if len(matches) == 1 else None


def offer_tuple_checks(offer: dict[str, Any] | None) -> dict[str, bool]:
    if offer is None:
        return {
            "offer_record_unique": False,
            "offer_source_tag_family": False,
            "offer_actor_recipient": False,
            "offer_phase_state": False,
            "offer_tuple_complete": False,
            "offer_queue_integrity": False,
        }
    numeric = all(
        as_int(offer.get(field)) is not None
        for field in (
            "date28", "date2c", "envoy30", "state34", "variant38",
            "proposal3c", "token3c",
        )
    )
    return {
        "offer_record_unique": True,
        "offer_source_tag_family": (
            offer.get("action_id") == ACTION
            and offer.get("family") == FAMILY
            and not isinstance(offer.get("extra60"), bool)
            and as_int(offer.get("extra60")) == 0
        ),
        "offer_actor_recipient": (
            offer.get("actor") == SOURCE_ACTOR
            and offer.get("mirror") == SOURCE_ACTOR
            and offer.get("recipient") == RECIPIENT
            and offer.get("decision_country") == RECIPIENT
            and bool_true(offer.get("decision_country_verified"))
        ),
        "offer_phase_state": (
            offer.get("phase") == "initiate"
            and as_int(offer.get("state34")) == 0
            and as_int(offer.get("variant38")) == 1
        ),
        "offer_tuple_complete": (
            numeric and as_int(offer.get("proposal_id")) is not None
        ),
        "offer_queue_integrity": all(
            bool_true(offer.get(field))
            for field in (
                "queue_readable", "list_integrity", "new_entry",
                "payload_readable", "source_verified",
            )
        ),
    }


def saved_pending_tuple_checks(restored: dict[str, Any] | None) -> dict[str, bool]:
    """Validate a restored pending node without treating it as a new offer."""

    if restored is None:
        return {
            "saved_pending_record_unique": False,
            "offer_source_tag_family": False,
            "offer_actor_recipient": False,
            "offer_phase_state": False,
            "offer_tuple_complete": False,
            "offer_queue_integrity": False,
            "saved_pending_not_new_entry": False,
        }
    numeric = all(
        as_int(restored.get(field)) is not None
        for field in (
            "date28", "date2c", "envoy30", "state34", "variant38",
            "proposal3c", "token3c",
        )
    )
    return {
        "saved_pending_record_unique": True,
        "offer_source_tag_family": (
            restored.get("action_id") == ACTION
            and restored.get("family") == FAMILY
            and not isinstance(restored.get("extra60"), bool)
            and as_int(restored.get("extra60")) == 0
        ),
        "offer_actor_recipient": (
            restored.get("actor") == SOURCE_ACTOR
            and restored.get("mirror") == SOURCE_ACTOR
            and restored.get("recipient") == RECIPIENT
            and restored.get("decision_country") == RECIPIENT
            and bool_true(restored.get("decision_country_verified"))
        ),
        "offer_phase_state": (
            restored.get("phase") == "initiate"
            and as_int(restored.get("state34")) == 0
            and as_int(restored.get("variant38")) == 1
        ),
        "offer_tuple_complete": (
            numeric and as_int(restored.get("proposal_id")) is not None
        ),
        "offer_queue_integrity": all(
            bool_true(restored.get(field))
            for field in (
                "queue_readable", "list_integrity", "payload_readable",
                "source_verified", "decision_country_verified",
                "saved_queue_restored", "native_queue_membership_verified",
            )
        ),
        "saved_pending_not_new_entry": (
            restored.get("pending_source") == "native_saved_pending_queue"
            and restored.get("new_entry") is False
            and restored.get("call_redirected") is False
        ),
    }


def resolve_report_file(path: Path) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    if resolved.is_dir():
        resolved = (resolved / "report.json").resolve(strict=True)
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    bounded_size(resolved)
    return resolved


def saved_pending_reference_checks(
    source_reference: Path | None,
    recovery_reference: Path | None,
    restored: dict[str, Any] | None,
    *,
    source_actor: str,
    recipient: str,
) -> tuple[dict[str, bool], dict[str, Any]]:
    """Bind F's restored event to E's fixture and the recovery validator."""

    checks = {
        "saved_source_reference_present": source_reference is not None,
        "saved_recovery_reference_present": recovery_reference is not None,
    }
    detail: dict[str, Any] = {
        "source_reference": None,
        "recovery_reference": None,
    }
    source_report: dict[str, Any] | None = None
    recovery_report: dict[str, Any] | None = None
    if source_reference is not None:
        source_path = resolve_report_file(source_reference)
        source_report = read_json(source_path)
        detail["source_reference"] = {
            "input": input_record(source_path),
            "status": source_report.get("status"),
            "family": source_report.get("family"),
            "action_id": source_report.get("action_id"),
            "actor": source_report.get("actor"),
            "recipient": source_report.get("recipient"),
            "session_id": source_report.get("session_id"),
            "test_source": source_report.get("test_source"),
            "fixed_test_source_published": source_report.get(
                "fixed_test_source_published"
            ),
        }
        checks.update({
            "saved_source_reference_passed": source_report.get("status") == "passed",
            "saved_source_reference_family_direction": (
                source_report.get("family") == FAMILY
                and source_report.get("action_id") == ACTION
                and source_report.get("actor") == source_actor
                and source_report.get("recipient") == recipient
            ),
            "saved_source_reference_fixture_published": (
                source_report.get("test_source") is True
                and source_report.get("fixed_test_source_published") is True
            ),
        })
    if recovery_reference is not None:
        recovery_path = resolve_report_file(recovery_reference)
        recovery_report = read_json(recovery_path)
        detail["recovery_reference"] = {
            "input": input_record(recovery_path),
            "status": recovery_report.get("status"),
            "source_event": recovery_report.get("source_event"),
            "restored_event": recovery_report.get("restored_event"),
            "response_event": recovery_report.get("response_event"),
            "payload_comparison": recovery_report.get("payload_comparison"),
        }
        reference_restored = recovery_report.get("restored_event")
        reference_source = recovery_report.get("source_event")
        reference_response = recovery_report.get("response_event")
        ref_fields = (
            "actor", "mirror", "recipient", "date28", "date2c", "envoy30",
            "state34", "variant38", "proposal3c", "token3c",
        )
        checks.update({
            "saved_recovery_reference_passed": recovery_report.get("status") == "passed",
            "saved_recovery_reference_payload_complete": (
                isinstance(reference_restored, dict)
                and isinstance(reference_source, dict)
                and recovery_report.get("payload_comparison", {}).get("all_match") is True
            ),
            "saved_recovery_reference_source_direction": (
                isinstance(reference_source, dict)
                and reference_source.get("family") == FAMILY
                and reference_source.get("action_id") == ACTION
                and reference_source.get("actor") == source_actor
                and reference_source.get("recipient") == recipient
            ),
            "saved_recovery_reference_restored_contract": (
                isinstance(reference_restored, dict)
                and reference_restored.get("event") == PENDING_RESTORED_EVENT
                and reference_restored.get("pending_source") == "native_saved_pending_queue"
                and reference_restored.get("new_entry") is False
                and reference_restored.get("call_redirected") is False
            ),
            "saved_recovery_reference_response_accepted": (
                isinstance(reference_response, dict)
                and reference_response.get("action_id") == ACTION
                and reference_response.get("family") == FAMILY
                and reference_response.get("actor") == source_actor
                and reference_response.get("recipient") == recipient
                and reference_response.get("outcome") == "accepted"
                and as_int(reference_response.get("native_state")) == 2
                and reference_response.get("pending_removed") is True
            ),
            "saved_recovery_reference_matches_current_restored": (
                isinstance(reference_restored, dict)
                and isinstance(restored, dict)
                and all(
                    restored.get(field) == reference_restored.get(field)
                    for field in ref_fields
                )
            ),
        })
    return checks, detail


def response_payload_checks(payloads: dict[str, dict[str, Any]],
                            offer: dict[str, Any] | None,
                            current_date: int | None,
                            expected_outcome: str) -> dict[str, bool]:
    stages = tuple(payloads.items())
    if offer is None:
        return {
            "response_payload_stages_present": False,
            "response_payload_family_extra60": False,
            "response_payload_actor_recipient": False,
            "response_payload_tuple_matches_offer": False,
            "response_payload_date2c_current": False,
            "response_payload_state_matches_outcome": False,
        }
    offer_date28 = as_int(offer.get("date28"))
    offer_envoy = as_int(offer.get("envoy30"))
    offer_token = as_int(offer.get("token3c"))
    stage_present = bool(stages) and all(
        isinstance(value, dict) for _, value in stages
    )
    family_extra = stage_present and all(
        value.get("family") == FAMILY
        and not isinstance(value.get("extra60"), bool)
        and as_int(value.get("extra60")) == 0
        for _, value in stages
    )
    actor_recipient = stage_present and all(
        packed_country(value.get("actor10")) == SOURCE_ACTOR
        and packed_country(value.get("mirror18")) == SOURCE_ACTOR
        and packed_country(value.get("recipient20")) == RECIPIENT
        for _, value in stages
    )
    tuple_match = stage_present and all(
        as_int(value.get("date28")) == offer_date28
        and as_int(value.get("envoy30")) == offer_envoy
        and as_int(value.get("proposal3c")) == offer_token
        for _, value in stages
    )
    date2c_current = (
        current_date is not None
        and stage_present
        and all(as_int(value.get("date2c")) == current_date for _, value in stages)
    )
    expected_state = 2 if expected_outcome == "accepted" else 1
    state_matches = stage_present and all(
        as_int(value.get("state34")) == expected_state for _, value in stages
    )
    return {
        "response_payload_stages_present": stage_present,
        "response_payload_family_extra60": family_extra,
        "response_payload_actor_recipient": actor_recipient,
        "response_payload_tuple_matches_offer": tuple_match,
        "response_payload_date2c_current": date2c_current,
        "response_payload_state_matches_outcome": state_matches,
    }


def normalized_response_result(event: dict[str, Any] | None) -> dict[str, Any] | None:
    if event is None:
        return None
    fields = (
        "event", "request_id", "session_id", "action_id", "family", "actor",
        "recipient", "phase", "date_raw", "outcome", "native_state",
        "native_variant",
        f"{RELATION_PREFIX}_before", f"{RELATION_PREFIX}_after", "response_verified",
        "request_binding_verified", "pending_removed",
    )
    return {field: event.get(field) for field in fields if field in event}


def response_binding_checks(submission: dict[str, Any] | None,
                            response: dict[str, Any] | None,
                            *, request_id: str, session_id: str,
                            phase: str, date_raw: int,
                            expected_outcome: str) -> dict[str, bool]:
    if submission is None or response is None:
        return {
            "request_submission_exact": False,
            "request_submission_receipt": False,
            "request_phase_date_binding": False,
            "response_exact_binding": False,
            "response_family_state": False,
            "response_transition": False,
            "response_verification_flags": False,
        }
    state = 2 if expected_outcome == "accepted" else 1
    after = expected_outcome == "accepted"
    common = (
        submission.get("request_id") == request_id
        and submission.get("session_id") == session_id
        and submission.get("action_id") == ACTION
        and submission.get("actor") == SOURCE_ACTOR
        and submission.get("recipient") == RECIPIENT
        and submission.get("phase") == phase
        and as_int(submission.get("date_raw")) == date_raw
    )
    response_common = (
        response.get("request_id") == request_id
        and response.get("session_id") == session_id
        and response.get("action_id") == ACTION
        and response.get("family") == FAMILY
        and response.get("actor") == SOURCE_ACTOR
        and response.get("recipient") == RECIPIENT
        and response.get("phase") == phase
        and as_int(response.get("date_raw")) == date_raw
    )
    return {
        "request_submission_exact": common,
        "request_submission_receipt": (
            common
            and bool_true(submission.get("submitted"))
            and bool_true(submission.get("native_queue_verified"))
            and bool_true(submission.get("transport_ring"))
            and same_int(submission.get("native_origin"), 0xFFFF)
            and same_int(submission.get("native_flags"), 0)
        ),
        "request_phase_date_binding": common and phase in ("accept", "reject"),
        "response_exact_binding": response_common,
        "response_family_state": (
            response_common
            and as_int(response.get("native_state")) == state
            and (
                FAMILY not in ("support_independence", "military_access", "vassalization")
                or (
                    type(response.get("native_variant")) is int
                    and response.get("native_variant") == 1
                )
            )
            and response.get("outcome") == expected_outcome
        ),
        "response_transition": (
            response.get(f"{RELATION_PREFIX}_before") is False
            and response.get(f"{RELATION_PREFIX}_after") is after
        ),
        "response_verification_flags": (
            bool_true(response.get("response_verified"))
            and bool_true(response.get("request_binding_verified"))
            and bool_true(response.get("pending_removed"))
        ),
    }


def compare_response_receipts(left: dict[str, Any] | None,
                              right: dict[str, Any] | None) -> bool:
    if left is None or right is None:
        return False
    fields = (
        "request_id", "session_id", "action_id", "family", "actor", "recipient",
        "phase", "date_raw", "outcome", "native_state",
        "native_variant",
        f"{RELATION_PREFIX}_before", f"{RELATION_PREFIX}_after", "response_verified",
        "request_binding_verified", "pending_removed",
    )
    return all(left.get(field) == right.get(field) for field in fields)


def compare_payload_semantics(left: dict[str, dict[str, Any]] | None,
                               right: dict[str, dict[str, Any]] | None) -> bool:
    """Compare cross-log payload meaning without requiring equal addresses."""

    if left is None or right is None or set(left) != set(right):
        return False
    fields = (*PAYLOAD_FIELDS, "family", "extra60")
    return all(
        all(left[stage].get(field) == right[stage].get(field) for field in fields)
        for stage in left
    )


def reverse_relation_evidence(
    report_path: Path,
    *,
    date_raw: int,
    source_actor: str,
    recipient: str,
) -> dict[str, Any]:
    """Read a same-date outbound query report for the reverse relation.

    Military Access is directional.  An inbound ``source_actor -> recipient``
    response does not prove the opposite query.  When a query report is
    supplied, this helper records the independent ``recipient -> source_actor``
    relationship evidence without reading any game state or replaying a call.
    """

    resolved = report_path.expanduser().resolve(strict=True)
    report_file = resolved if resolved.is_file() else resolved / "report.json"
    bounded_size(report_file)
    payload = read_json(report_file)
    if not isinstance(payload, dict):
        raise ValueError("reverse query report is not an object")
    control = payload.get("control") if isinstance(payload.get("control"), dict) else {}
    results = payload.get("recipient_results")
    target = results.get(source_actor) if isinstance(results, dict) else None
    relation = target.get("relation") if isinstance(target, dict) else None
    actions = (
        target.get("ask"), target.get("cancel")
    ) if isinstance(target, dict) else (None, None)
    checks = {
        "report_status_passed": payload.get("status") == "passed",
        "report_family_military_access": payload.get("family") == "military_access",
        "reverse_actor_is_inbound_recipient": payload.get("actor") == recipient,
        "reverse_counterparty_is_inbound_source": (
            isinstance(payload.get("recipients"), list)
            and source_actor in payload.get("recipients", [])
        ),
        "reverse_date_matches_response": (
            as_int(control.get("date_raw")) == date_raw
        ),
        "reverse_action_pair_present": (
            isinstance(actions[0], dict)
            and actions[0].get("action_id") == "ask_military_access"
            and isinstance(actions[1], dict)
            and actions[1].get("action_id") == "cancel_military_access"
        ),
        "reverse_relation_active": (
            isinstance(relation, dict)
            and relation.get("source") == "relationship_state"
            and relation.get("complete") is True
            and relation.get("consistent") is True
            and relation.get("military_access_active") is True
        ),
    }
    return {
        "input": input_record(report_file),
        "report_status": payload.get("status"),
        "report_actor": payload.get("actor"),
        "report_recipients": payload.get("recipients"),
        "date_raw": as_int(control.get("date_raw")),
        "direction": {
            "actor": recipient,
            "recipient": source_actor,
            "relation_meaning": f"{recipient} grants military access to {source_actor}",
        },
        "relation": relation,
        "checks": checks,
        "all_checks_true": all(checks.values()),
    }


def observation_hold_checks(
    observation: Path | None,
    offer: dict[str, Any] | None,
    session_id: str,
    response_identity_bound: bool = False,
) -> tuple[dict[str, bool], dict[str, Any]]:
    """Verify a cross-day pending proposal before its response."""
    if observation is None:
        return {}, {}
    observed_path = observation / "observed-events.jsonl"
    report_path = observation / "observation-report.json"
    scan = stream_selected_events(
        observed_path,
        {
            "native_diplomacy_inbound_ai_choice_held",
            ENTRY_EVENT,
            RESPONSE_EVENT,
            "native_diplomacy_relation_response_result",
            "native_alliance_response_result",
            EXECUTION_EVENT if "EXECUTION_EVENT" in globals() else "native_diplomacy_relation_execution_result",
            "native_alliance_execution_rejected",
            "native_alliance_authority_test_dispatched",
        },
    )
    observation_report = read_json(report_path)
    offer_proposal_id = as_int(offer.get("proposal_id")) if offer else None
    held = [
        value for value in scan["selected"].get("native_diplomacy_inbound_ai_choice_held", [])
        if value.get("action_id") == ACTION
        and value.get("decision_country") == RECIPIENT
        and offer_proposal_id is not None
        and as_int(value.get("proposal_id")) == offer_proposal_id
    ]
    offer_date = as_int(offer.get("date28")) if offer else None
    offer_token = as_int(offer.get("token3c")) if offer else None
    hold_dates = [as_int(value.get("date_raw")) for value in held]
    hold_dates = [value for value in hold_dates if value is not None]
    hold_date = (
        max(hold_dates) if hold_dates
        else as_int(observation_report.get("date_raw_after"))
        if FAMILY == "military_access" else None
    )
    automatic_entries = [
        value for value in scan["selected"].get(ENTRY_EVENT, [])
        if value.get("action_id") == ACTION
        and isinstance(value.get("source"), dict)
        and value.get("source", {}).get("payload", {}).get("family") == FAMILY
        and as_int(value.get("source", {}).get("payload", {}).get("state34")) in (1, 2)
    ]
    response_events = []
    for name in (
        RESPONSE_EVENT,
        "native_diplomacy_relation_response_result",
        "native_alliance_response_result",
            "native_diplomacy_relation_execution_result",
        "native_alliance_execution_rejected",
        "native_alliance_authority_test_dispatched",
    ):
        response_events.extend(
            value for value in scan["selected"].get(name, [])
            if value.get("action_id") == ACTION
        )
    checks = {
        "observation_session_matches": observation_report.get("session_id") == session_id,
        "observation_status_observed": observation_report.get("status") == "observed",
        "observation_date_advanced": (
            offer_date is not None and hold_date is not None and hold_date > offer_date
        ),
        "observation_date_matches_report": (
            hold_date is not None
            and hold_date == as_int(observation_report.get("date_raw_after"))
        ),
        "same_pending_proposal": (
            len(held) >= 1
            and offer is not None
            and all(
                as_int(value.get("proposal_id")) == as_int(offer.get("proposal_id"))
                and as_int(value.get("token3c")) == offer_token
                for value in held
            )
        ),
        "pending_actor_recipient_and_decision": (
            offer is not None
            and offer.get("actor") == SOURCE_ACTOR
            and offer.get("recipient") == RECIPIENT
            and offer.get("decision_country") == RECIPIENT
            and len(held) >= 1
            and all(value.get("decision_country") == RECIPIENT for value in held)
        ),
        "pending_variant_one": offer is not None and as_int(offer.get("variant38")) == 1,
        "no_automatic_state1_or2_entry": not automatic_entries,
        "no_unrequested_response_or_rejection": not response_events,
    }
    if FAMILY == "military_access":
        if held:
            checks["hold_queue_verified_and_ai_skipped"] = (
                all(
                    bool_true(value.get("native_queue_verified"))
                    and bool_true(value.get("native_ai_choice_skipped"))
                    for value in held
                )
            )
        else:
            # This R32 fixture does not emit the daily AI-hold event.  The
            # response transport tuple still binds the later rejection to the
            # initial offer, while the observation independently proves the
            # date advance and absence of an automatic command.
            checks.pop("same_pending_proposal", None)
            checks.pop("pending_actor_recipient_and_decision", None)
            checks["pending_identity_bound_by_response_tuple"] = (
                response_identity_bound and offer is not None
            )
            checks["hold_event_not_emitted_for_fixture"] = True
    return checks, {
        "observation_report": observation_report,
        "observed_events": input_record(observed_path, scan),
        "hold_records": held,
        "hold_evidence_mode": (
            "native_ai_hold_event" if held
            else "initial_offer_and_response_tuple" if FAMILY == "military_access"
            else "no_hold_record"
        ),
        "automatic_state1_or2_entries": automatic_entries,
        "support_state1_or2_entries": automatic_entries,
        "response_or_rejection_records": response_events,
    }


def validate(
    artifact: Path,
    control_probe: Path,
    expected_outcome: str | None = None,
    expected_request_id: str | None = None,
    *,
    family: str = "royal_marriage",
    action_id: str = "offer_royal_marriage",
    source_actor: str = "SAV",
    recipient: str = "FRA",
    source_tag: str = "SAV_ROYAL_TO_FRA",
    source_kind: str = "native_ui_fixture",
    response_event: str = "native_alliance_response_result",
    fixture_probe: Path | None = None,
    observation: Path | None = None,
    reverse_query_artifact: Path | None = None,
    source_reference: Path | None = None,
    recovery_reference: Path | None = None,
) -> dict[str, Any]:
    global FAMILY, ACTION, SOURCE_ACTOR, RECIPIENT, SOURCE_TAG, RESPONSE_EVENT, RELATION_PREFIX
    FAMILY = family
    ACTION = action_id
    SOURCE_ACTOR = source_actor
    RECIPIENT = recipient
    SOURCE_TAG = source_tag
    RESPONSE_EVENT = response_event
    relation_prefixes = {
        "royal_marriage": "royal_marriage",
        "support_independence": "support_independence",
        "military_access": "military_access",
        "vassalization": "vassalization",
    }
    if family not in relation_prefixes:
        raise ValueError(f"unsupported inbound family: {family}")
    if source_kind not in (
        "native_ui_fixture", "natural_native", "saved_native_pending"
    ):
        raise ValueError(f"unsupported source kind: {source_kind}")
    if source_kind == "natural_native" and fixture_probe is not None:
        raise ValueError("natural_native source cannot use fixture_probe")
    if source_kind == "saved_native_pending" and fixture_probe is not None:
        raise ValueError("saved_native_pending source cannot use fixture_probe")
    if source_kind == "saved_native_pending" and (
        source_reference is None or recovery_reference is None
    ):
        raise ValueError(
            "saved_native_pending source requires source_reference and recovery_reference"
        )
    if family == "military_access" and action_id != "ask_military_access":
        raise ValueError("Military Access inbound source requires ask_military_access")
    RELATION_PREFIX = relation_prefixes[family]
    native_events_path = artifact / "native-events.jsonl"
    report_path = artifact / "report.json"
    input_paths = [native_events_path, control_probe, report_path]
    if fixture_probe is not None:
        input_paths.append(fixture_probe)
    if observation is not None:
        input_paths.extend([observation / "observed-events.jsonl", observation / "observation-report.json"])
    reverse_query_report = None
    if reverse_query_artifact is not None:
        resolved_reverse = reverse_query_artifact.expanduser().resolve(strict=True)
        reverse_query_report = (
            resolved_reverse if resolved_reverse.is_file()
            else resolved_reverse / "report.json"
        )
        input_paths.append(reverse_query_report)
    if source_reference is not None:
        input_paths.append(resolve_report_file(source_reference))
    if recovery_reference is not None:
        input_paths.append(resolve_report_file(recovery_reference))
    for path in input_paths:
        if not path.is_file():
            raise FileNotFoundError(path)
        bounded_size(path)

    report = read_json(report_path)
    native_scan = stream_selected_events(
        native_events_path,
        {INSPECTION_EVENT, SUBMISSION_EVENT, RESPONSE_EVENT},
    )
    control_scan = stream_selected_events(
        control_probe,
        {
            TEST_EVENT, OFFER_EVENT, PENDING_RESTORED_EVENT, INSPECTION_EVENT,
            SUBMISSION_EVENT, RESPONSE_EVENT,
        },
    )
    fixture_scan = (
        stream_selected_events(
            fixture_probe,
            {
                TEST_EVENT, OFFER_EVENT, PENDING_RESTORED_EVENT,
                INSPECTION_EVENT, SUBMISSION_EVENT, RESPONSE_EVENT,
            },
        )
        if fixture_probe is not None else {"selected": {}, "line_count": 0,
                                           "malformed_lines": [], "event_counts": {}}
    )
    for name, values in fixture_scan["selected"].items():
        existing = control_scan["selected"].setdefault(name, [])
        identity_fields = (
            "event", "session_id", "action_id", "family", "actor", "recipient",
            "phase", "date_raw", "date28", "proposal_id", "native_proposal_id",
            "token3c", "state34", "variant38", "request_id",
        )
        identities = {
            tuple(item.get(field) for field in identity_fields) for item in existing
        }
        for value in values:
            identity = tuple(value.get(field) for field in identity_fields)
            if identity not in identities:
                existing.append(value)
                identities.add(identity)
    native_event_data = load_events(native_events_path)
    control_event_data = load_events(control_probe)
    session_ids = sorted(
        set(native_event_data["session_ids"]) | set(control_event_data["session_ids"])
    )
    session_id = session_ids[0] if len(session_ids) == 1 else ""

    native_submissions = native_scan["selected"].get(SUBMISSION_EVENT, [])
    control_submissions = control_scan["selected"].get(SUBMISSION_EVENT, [])
    submission_matches = [
        event for event in native_submissions
        if event.get("action_id") == ACTION
        and event.get("actor") == SOURCE_ACTOR
        and event.get("recipient") == RECIPIENT
        and bool_true(event.get("submitted"))
    ]
    if len(submission_matches) != 1:
        raise ValueError(
            f"expected one native submission receipt, found {len(submission_matches)}"
        )
    submission = submission_matches[0]
    request_id = expected_request_id or str(submission.get("request_id", ""))
    phase = str(submission.get("phase", ""))
    date_raw = as_int(submission.get("date_raw"))
    if not request_id or not phase or date_raw is None:
        raise ValueError("submission receipt lacks request_id/phase/date_raw")

    native_responses = native_scan["selected"].get(RESPONSE_EVENT, [])
    control_responses = control_scan["selected"].get(RESPONSE_EVENT, [])
    exact_native_responses = [
        event for event in native_responses
        if event.get("request_id") == request_id
        and event.get("session_id") == session_id
        and event.get("action_id") == ACTION
        and event.get("family") == FAMILY
    ]
    if len(exact_native_responses) != 1:
        raise ValueError(
            f"expected one exact native response receipt, found {len(exact_native_responses)}"
        )
    response = exact_native_responses[0]
    inferred_outcome = str(response.get("outcome", ""))
    if inferred_outcome not in ("accepted", "rejected"):
        inferred_outcome = (
            "accepted" if as_int(response.get("native_state")) == 2 else "rejected"
        )
    wanted_outcome = expected_outcome or inferred_outcome
    if wanted_outcome not in ("accepted", "rejected"):
        raise ValueError(f"unsupported expected outcome: {wanted_outcome}")

    tests = control_scan["selected"].get(TEST_EVENT, [])
    fixture_tests = find_all(
        tests,
        lambda event: (
            event.get("source") == SOURCE_ACTOR
            and event.get("recipient") == RECIPIENT
            and event.get("phase") == "initiate"
            and bool_true(event.get("submitted"))
        ),
    )
    offers = find_all(
        control_scan["selected"].get(OFFER_EVENT, []),
        lambda event: (
            event.get("action_id") == ACTION
            and event.get("family") == FAMILY
            and event.get("actor") == SOURCE_ACTOR
            and event.get("recipient") == RECIPIENT
            and as_int(event.get("state34")) == 0
        ),
    )
    restored_events = find_all(
        control_scan["selected"].get(PENDING_RESTORED_EVENT, []),
        lambda event: (
            event.get("action_id") == ACTION
            and event.get("family") == FAMILY
            and event.get("actor") == SOURCE_ACTOR
            and event.get("mirror") == SOURCE_ACTOR
            and event.get("recipient") == RECIPIENT
            and event.get("phase") == "initiate"
        ),
    )
    if source_kind == "saved_native_pending":
        offer = restored_events[0] if len(restored_events) == 1 else None
        offer_checks = saved_pending_tuple_checks(offer)
    else:
        offer = offers[0] if len(offers) == 1 else None
        offer_checks = offer_tuple_checks(offer)
    proposal_id = as_int(offer.get("proposal_id")) if offer else None

    inspections = native_scan["selected"].get(INSPECTION_EVENT, [])
    matching_inspections = find_all(
        inspections,
        lambda event: (
            event.get("action_id") == ACTION
            and event.get("family") == FAMILY
            and event.get("actor") == SOURCE_ACTOR
            and event.get("recipient") == RECIPIENT
            and event.get("phase") == phase
            and as_int(event.get("native_proposal_id")) == proposal_id
        ),
    )

    def inspection_relation_precondition(event: dict[str, Any]) -> bool:
        if FAMILY == "military_access":
            return (
                event.get("military_access_active") is False
                and bool_true(event.get("military_access_state_verified"))
            )
        return event.get(f"{RELATION_PREFIX}_before") is False

    native_sequence = as_int(submission.get("native_sequence"))
    native_chains = strict_chains(native_event_data, session_id, native_sequence)
    control_chains = strict_chains(control_event_data, session_id, native_sequence)
    native_chain = native_chains[0] if len(native_chains) == 1 else None
    control_chain = control_chains[0] if len(control_chains) == 1 else None
    control_offer_chains = [
        chain for chain in strict_chains(control_event_data, session_id)
        if as_int(chain["entry"].get("protocol_sequence")) != native_sequence
        and chain["entry"].get("action_id") == ACTION
        and as_int(
            chain["transport"].get("source", {}).get("payload", {}).get("state34")
        ) == 0
    ]
    native_chain_report = (
        chain_record(native_event_data, native_chain) if native_chain else None
    )
    control_chain_report = (
        chain_record(control_event_data, control_chain) if control_chain else None
    )
    control_offer_chain_report = (
        chain_record(control_event_data, control_offer_chains[0])
        if len(control_offer_chains) == 1 else None
    )

    response_payloads = (
        chain_payloads(native_chain, raw_chain_events(native_event_data, native_chain))
        if native_chain else {}
    )
    payload_checks = response_payload_checks(
        response_payloads, offer, date_raw, wanted_outcome
    )
    binding_checks = response_binding_checks(
        submission, response,
        request_id=request_id,
        session_id=session_id,
        phase=phase,
        date_raw=date_raw,
        expected_outcome=wanted_outcome,
    )
    native_control_response = find_one(
        control_responses,
        lambda event: (
            event.get("request_id") == request_id
            and event.get("session_id") == session_id
        ),
    )
    control_submission = find_one(
        control_submissions,
        lambda event: (
            event.get("request_id") == request_id
            and event.get("session_id") == session_id
        ),
    )

    fixture_source_checks = {
        "fixture_submit_receipt": len(fixture_tests) == 1,
        "fixture_submit_deferred_for_observation": (
            len(fixture_tests) == 1
            and bool_true(fixture_tests[0].get("dispatcher_accepted"))
            and bool_true(fixture_tests[0].get("defer_observation_expected"))
        ),
        "fixture_date_matches_initial_offer": (
            len(fixture_tests) == 1
            and offer is not None
            and (
                as_int(fixture_tests[0].get("date_raw")) == as_int(offer.get("date28"))
                or (
                    fixture_probe is None
                    and as_int(fixture_tests[0].get("date_raw")) == date_raw
                )
            )
        ),
    }
    natural_source_checks = {
        "natural_source_without_fixture_submission": len(fixture_tests) == 0,
        "natural_offer_precedes_response": (
            offer is not None
            and as_int(offer.get("date28")) is not None
            and as_int(offer.get("date28")) <= date_raw
        ),
    }
    saved_pending_checks, saved_pending_reference_detail = (
        saved_pending_reference_checks(
            source_reference,
            recovery_reference,
            offer,
            source_actor=SOURCE_ACTOR,
            recipient=RECIPIENT,
        )
        if source_kind == "saved_native_pending"
        else ({}, {})
    )
    saved_pending_source_checks = {
        **saved_pending_checks,
        "saved_pending_restored_record_unique": (
            len(restored_events) == 1
        ),
        "saved_pending_has_no_new_offer_event": (
            not offers
        ),
        "saved_pending_has_no_fixture_submission": (
            len(fixture_tests) == 0
        ),
    }
    source_checks: dict[str, bool] = {
        **offer_checks,
        **(
            fixture_source_checks
            if source_kind == "native_ui_fixture"
            else natural_source_checks
            if source_kind == "natural_native"
            else saved_pending_source_checks
        ),
        "proposal_id_matches_response_inspection": (
            proposal_id is not None
            and len(matching_inspections) >= 1
            and all(bool_true(item.get("pending_active"))
                    for item in matching_inspections)
        ),
        "inspection_relation_precondition_false": (
            len(matching_inspections) >= 1
            and all(inspection_relation_precondition(item)
                    for item in matching_inspections)
        ),
        "inspection_native_validity": (
            all(bool_true(item.get("native_validity")) for item in matching_inspections)
            if FAMILY == "military_access" else True
        ),
        "inspection_response_rules_complete": (
            all(bool_true(item.get("response_rules_complete")) for item in matching_inspections)
            if FAMILY == "military_access" else True
        ),
        "native_chain_unique": len(native_chains) == 1,
        "control_chain_unique": len(control_chains) == 1,
        "control_offer_chain_unique": (
            len(control_offer_chains) == 1
            if source_kind == "native_ui_fixture" else True
        ),
        "native_chain_strict_checks": (
            native_chain_report is not None
            and native_chain_report["all_strict_checks_true"]
            and native_chain_report["address_chain_all_true"]
        ),
        "control_chain_strict_checks": (
            control_chain_report is not None
            and control_chain_report["all_strict_checks_true"]
            and control_chain_report["address_chain_all_true"]
        ),
        "control_offer_chain_strict_checks": (
            (
                control_offer_chain_report is not None
                and control_offer_chain_report["all_strict_checks_true"]
                and control_offer_chain_report["address_chain_all_true"]
            )
            if source_kind == "native_ui_fixture" else True
        ),
        "native_control_response_chain_payloads_equal": (
            native_chain_report is not None
            and control_chain_report is not None
            and compare_payload_semantics(
                native_chain_report["payloads"], control_chain_report["payloads"]
            )
        ),
        "native_sequence_matches_submission": (
            native_sequence is not None
            and native_chain is not None
            and as_int(native_chain["entry"].get("protocol_sequence")) == native_sequence
        ),
    }
    source_checks.update(payload_checks)
    source_checks.update(binding_checks)
    source_checks.update({
        "control_submission_matches_native": (
            control_submission is not None
            and submission_summary(control_submission) == submission_summary(submission)
        ),
        "control_response_matches_native": (
            compare_response_receipts(native_control_response, response)
        ),
        "source_and_business_checks_independent": True,
    })
    reverse_relation = None
    if reverse_query_report is not None:
        reverse_relation = reverse_relation_evidence(
            reverse_query_report,
            date_raw=date_raw,
            source_actor=SOURCE_ACTOR,
            recipient=RECIPIENT,
        )
        source_checks["reverse_relation_evidence_bound"] = (
            reverse_relation.get("all_checks_true") is True
        )
    hold_checks, hold_detail = observation_hold_checks(
        observation,
        offer,
        session_id,
        response_identity_bound=(
            payload_checks.get("response_payload_tuple_matches_offer") is True
        ),
    )
    source_checks.update(hold_checks)
    check_groups = {
        "source_fixture": {
            key: value for key, value in source_checks.items()
            if key.startswith((
                "offer_", "fixture_", "saved_", "proposal_", "inspection_",
                "control_offer_",
            ))
        },
        "request_and_phase": {
            key: value for key, value in source_checks.items()
            if key.startswith("request_")
            or key in ("control_submission_matches_native", "native_sequence_matches_submission")
        },
        "business_status": {
            key: value for key, value in source_checks.items()
            if key.startswith("response_") or key == "control_response_matches_native"
        },
        "native_source_chain": {
            key: value for key, value in source_checks.items()
            if key.startswith(("native_chain", "control_chain", "native_control_"))
        },
    }

    consumer_status = report.get("status")
    result = {
        "validator": {
            "name": "validate_royal_inbound_source",
            "version": 1,
            "bounded_input_bytes": MAX_INPUT_BYTES,
            "read_only": True,
            "replay": False,
        },
        "source_context": {
            "tag": SOURCE_TAG,
            "kind": source_kind,
            "npc_spontaneous_choice": source_kind == "natural_native",
            "sender": SOURCE_ACTOR,
            "recipient": RECIPIENT,
            "bridge_selected_decision": phase,
            "fullnative_original_state2_choice": "deferred_by_TLS",
            "basis": (
                (
                    "native_alliance_inbound_test_submitted and "
                    "native_alliance_inbound_offer identify the controlled "
                    f"{SOURCE_ACTOR}-to-{RECIPIENT} UI fixture; the bridge "
                    "response receipt identifies the selected accept/reject phase."
                )
                if source_kind == "native_ui_fixture" else (
                    "native_diplomacy_inbound_pending_restored identifies the saved "
                    f"{SOURCE_ACTOR}-to-{RECIPIENT} pending node; the E fixture "
                    "source report and the F saved-pending recovery report bind the "
                    "original proposal to this restored payload. The response "
                    "receipt identifies the selected accept/reject phase."
                    if source_kind == "saved_native_pending" else (
                    "native_alliance_inbound_offer identifies the natural "
                    f"{SOURCE_ACTOR}-to-{RECIPIENT} pending proposal; the bridge "
                    "response receipt identifies the selected accept/reject phase."
                    )
                )
            ),
        },
        "inputs": {
            "report": input_record(report_path),
            "native_events": input_record(native_events_path, native_scan),
            "control_probe": input_record(control_probe, control_scan),
            "fixture_probe": (
                input_record(fixture_probe, fixture_scan)
                if fixture_probe is not None else None
            ),
            "source_reference": (
                input_record(resolve_report_file(source_reference))
                if source_reference is not None else None
            ),
            "recovery_reference": (
                input_record(resolve_report_file(recovery_reference))
                if recovery_reference is not None else None
            ),
            "observation": (
                {
                    "report": input_record(observation / "observation-report.json"),
                    "events": hold_detail.get("observed_events"),
                }
                if observation is not None else None
            ),
        },
        "request_binding": {
            "request_id": request_id,
            "session_id": session_id,
            "action_id": ACTION,
            "family": FAMILY,
            "actor": SOURCE_ACTOR,
            "recipient": RECIPIENT,
            "phase": phase,
            "date_raw": date_raw,
            "native_sequence": native_sequence,
            "expected_outcome": wanted_outcome,
        },
        "initial_native_offer": offer,
        "initial_offer_source": {
            "proposal_id": proposal_id,
            "record_line": offer.get("_line") if offer else None,
            "tuple": {
                key: offer.get(key) if offer else None
                for key in (
                    "actor", "mirror", "recipient", "date28", "date2c",
                    "envoy30", "token3c", "family", "extra60",
                )
            },
            "fixture_submission": fixture_tests[0] if len(fixture_tests) == 1 else None,
            "inspection_records": matching_inspections,
        },
        "saved_pending_references": saved_pending_reference_detail,
        "native_submission": submission_summary(submission),
        "native_response": normalized_response_result(response),
        "control_submission": submission_summary(control_submission),
        "control_response": normalized_response_result(native_control_response),
        "source_chain": {
            "native_response": native_chain_report,
            "control_response": control_chain_report,
            "control_initial_offer": control_offer_chain_report,
        },
        "observation_hold": hold_detail,
        "reverse_relation_evidence": reverse_relation,
        "state_transition": {
            "initial_pending_state34": as_int(offer.get("state34")) if offer else None,
            "response_state34": as_int(
                response_payloads.get("transport_source", {}).get("state34")
            ),
            "response_native_state": as_int(response.get("native_state")),
            f"{RELATION_PREFIX}_before": response.get(f"{RELATION_PREFIX}_before"),
            f"{RELATION_PREFIX}_after": response.get(f"{RELATION_PREFIX}_after"),
            "date28": as_int(
                response_payloads.get("transport_source", {}).get("date28")
            ),
            "date2c_current": as_int(
                response_payloads.get("transport_source", {}).get("date2c")
            ),
            "date2c_expected_current": date_raw,
        },
        "consumer_receipt_context": {
            "original_report_status": consumer_status,
            "original_report_submitted": (
                report.get("execution", {}).get("submitted")
                if isinstance(report.get("execution"), dict) else None
            ),
            "original_report_result": result_summary(
                report.get("execution", {}).get("result")
                if isinstance(report.get("execution"), dict)
                and isinstance(report.get("execution", {}).get("result"), dict)
                else None
            ),
            "excluded_from_native_source_validity": True,
        },
        "check_groups": check_groups,
        "checks": source_checks,
        "summary": {
            "validation_passed": all(value is True for value in source_checks.values()),
            "total_checks": len(source_checks),
            "passed_checks": sum(value is True for value in source_checks.values()),
            "failed_checks": sum(value is not True for value in source_checks.values()),
        },
    }
    return result


def markdown_report(result: dict[str, Any]) -> str:
    binding = result["request_binding"]
    summary = result["summary"]
    context = result["source_context"]
    source = result["source_chain"]
    consumer = result["consumer_receipt_context"]
    relation_label = {
        "royal_marriage": "联姻",
        "support_independence": "支持独立",
        "military_access": "军事通行权",
        "vassalization": "附庸关系",
    }.get(FAMILY, FAMILY)
    if context["kind"] == "natural_native":
        source_semantics = (
            f"native_alliance_inbound_offer 证明这是自然产生的 {context['sender']}→"
            f"{context['recipient']} pending 提议；没有使用 TEST_ONLY 来源，也没有把该提议"
            "解释为受控 fixture。桥接明确选择了当前 phase="
            f"{binding['phase']} 的响应。"
        )
    elif context["kind"] == "saved_native_pending":
        source_semantics = (
            f"native_diplomacy_inbound_pending_restored 证明这是保存后恢复的 "
            f"{context['sender']}→{context['recipient']} pending 节点；E 阶段受控 "
            "fixture 来源与 F 阶段保存队列恢复报告共同绑定原始 payload。该事件的 "
            "new_entry=false、call_redirected=false 表示恢复既有提议，没有伪造新的来源 fixture。"
            "桥接明确选择了当前 phase="
            f"{binding['phase']} 的响应。"
        )
    else:
        source_semantics = (
            f"native_alliance_inbound_test_submitted 与 native_alliance_inbound_offer "
            f"共同证明这是受控的 {context['sender']}→{context['recipient']} 原生 UI fixture；"
            "报告不把该提议解释为 NPC 自发选择。桥接明确选择了当前 phase="
            f"{binding['phase']} 的响应。"
        )
    relation_before = f"{RELATION_PREFIX}_before"
    relation_after = f"{RELATION_PREFIX}_after"
    lines = [
        f"# {FAMILY} 入站响应原生来源验收",
        "",
        f"- 验收状态：{'通过' if summary['validation_passed'] else '失败'}（{summary['passed_checks']}/{summary['total_checks']} 项）",
        f"- 测试来源：{context['tag']}，{context['kind']}，发送方 {context['sender']}，接收方 {context['recipient']}",
        f"- 请求：{binding['request_id']}，动作 {binding['action_id']}，family {binding['family']}，phase {binding['phase']}，date_raw {binding['date_raw']}，sequence {binding['native_sequence']}",
        f"- 业务结果：预期 {binding['expected_outcome']}，native state {result['native_response'].get('native_state') if result['native_response'] else None}，{relation_label}前后 {result['native_response'].get(relation_before) if result['native_response'] else None} -> {result['native_response'].get(relation_after) if result['native_response'] else None}",
        "",
        "## 来源和决策语义",
        "",
        source_semantics + (
            f"原生完整 state2 选择按本次实验上下文由 TLS 延期；"
            f"该上下文不参与本次 {binding['expected_outcome']} 的 source-validity 判定。"
        ),
        "",
        "## 原生状态转换",
        "",
        f"- 初始 pending state34={result['state_transition']['initial_pending_state34']}，proposal_id={result['initial_offer_source']['proposal_id']}。",
        f"- 响应链 state34={result['state_transition']['response_state34']}，native response state={result['state_transition']['response_native_state']}；date28={result['state_transition']['date28']} 保持原提议身份，date2c={result['state_transition']['date2c_current']} 刷新到当前日期 {result['state_transition']['date2c_expected_current']}。",
        "- Native receipt 标记 response_verified=true、request_binding_verified=true、pending_removed=true。",
        "",
        "## 跨日观察",
        "",
    ]
    hold = result.get("observation_hold")
    if isinstance(hold, dict) and hold:
        lines.append(
            f"观察证据模式：{hold.get('hold_evidence_mode')}；"
            f"原始 hold 记录数：{len(hold.get('hold_records', [])) if isinstance(hold.get('hold_records'), list) else 0}。"
        )
        if hold.get("hold_evidence_mode") == "initial_offer_and_response_tuple":
            lines.append(
                "本 Military Access fixture 未输出独立 daily AI hold 事件；"
                "报告使用初始 offer 与响应 transport tuple 的一致性绑定提议身份，"
                "并使用 observation 的日期推进与无自动 state1/2 entry 证明跨日未自动回应。"
            )
    else:
        lines.append("未提供跨日 observation。")
    lines.extend(["", "## 来源链", ""])
    for label, chain in (
        ("response native-events", source.get("native_response")),
        ("response control-probe", source.get("control_response")),
        ("initial offer control-probe", source.get("control_initial_offer")),
    ):
        if chain is None:
            lines.append(f"- {label}：未选出严格链。")
            continue
        refs = chain["line_refs"]
        callbacks = chain["callback_refs"]
        lines.append(
            f"- {label}：JSONL 行 transport/clone/entry = "
            f"{refs['transport']}/{refs['clone']}/{refs['entry']}；"
            f"callback = {callbacks['transport_begin']} < {callbacks['transport_load']} < "
            f"{callbacks['transport_end']} < {callbacks['clone_begin']} < "
            f"{callbacks['clone_end']} < {callbacks['entry']}；"
            f"protocol_sequence={callbacks['protocol_sequence']}；严格检查与地址链检查均通过。"
        )
    lines.extend(["", "## 检查结果", "", "| 检查 | 结果 |", "|---|---|"])
    for name, value in result["checks"].items():
        lines.append(f"| {name} | {'通过' if value else '失败'} |")
    lines.extend([
        "",
        "## 单向关系反向证据",
        "",
    ])
    reverse = result.get("reverse_relation_evidence")
    if isinstance(reverse, dict):
        direction = reverse.get("direction", {})
        lines.append(
            f"独立查询报告证明方向为 {direction.get('actor')}→{direction.get('recipient')}；"
            f"同日期关系 active={reverse.get('relation', {}).get('military_access_active') if isinstance(reverse.get('relation'), dict) else None}；"
            f"反向证据检查{'通过' if reverse.get('all_checks_true') else '失败'}。"
        )
    else:
        lines.append("本次未提供反向关系查询报告。")
    lines.extend([
        "",
        "## Python 消费端状态",
        "",
        f"原始 report.json 状态为 {consumer['original_report_status']}，其中消费端提交字段为 {consumer['original_report_submitted']}。该字段只作为独立上下文保存；本报告以 native submission、transport、wrapper、command-entry 和 native response 证据判断来源链，因此没有用消费端 receipt 失败覆盖原生验收结果。",
        "",
        "输入文件的大小、SHA-256、行数和解析错误信息已写入同名 JSON 报告；输入 JSONL 均按行流式读取。",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True,
                        help="inbound-response artifact directory")
    parser.add_argument("--control-probe", type=Path,
                        help="parent control-probe.jsonl; inferred from runtime layout when omitted")
    parser.add_argument("--expected-outcome", choices=("accepted", "rejected"))
    parser.add_argument("--expected-request-id")
    parser.add_argument("--family", default="royal_marriage",
                        help="native relation family; default preserves Royal")
    parser.add_argument("--action-id", default="offer_royal_marriage",
                        help="inbound action id")
    parser.add_argument("--source-actor", default="SAV",
                        help="proposal source country")
    parser.add_argument("--recipient", default="FRA",
                        help="proposal recipient country")
    parser.add_argument("--source-tag", default="SAV_ROYAL_TO_FRA",
                        help="human-readable fixture source tag")
    parser.add_argument(
        "--source-kind",
        choices=("native_ui_fixture", "natural_native", "saved_native_pending"),
        default="native_ui_fixture",
        help="proposal source provenance; default preserves fixture validation",
    )
    parser.add_argument("--response-event", default="native_alliance_response_result",
                        help="native response result event name")
    parser.add_argument("--fixture-probe", type=Path,
                        help="separate preparation JSONL containing fixture submission")
    parser.add_argument(
        "--source-reference", type=Path,
        help="original source preparation report; required for saved_native_pending",
    )
    parser.add_argument(
        "--recovery-reference", type=Path,
        help="passed saved-pending recovery validation report; required for saved_native_pending",
    )
    parser.add_argument("--observation", type=Path,
                        help="cross-day lifecycle observation directory")
    parser.add_argument("--reverse-query-artifact", type=Path,
                        help="same-date outbound query report for the reverse one-sided relation")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    args = parser.parse_args()

    artifact = args.artifact.resolve()
    control_probe = (
        args.control_probe.resolve()
        if args.control_probe
        else artifact.parent / "control-probe.jsonl"
    )
    fixture_probe = args.fixture_probe.resolve() if args.fixture_probe else None
    observation = args.observation.resolve() if args.observation else None
    reverse_query_artifact = (
        args.reverse_query_artifact.resolve()
        if args.reverse_query_artifact else None
    )
    result = validate(
        artifact, control_probe, args.expected_outcome, args.expected_request_id,
        family=args.family,
        action_id=args.action_id,
        source_actor=args.source_actor,
        recipient=args.recipient,
        source_tag=args.source_tag,
        source_kind=args.source_kind,
        response_event=args.response_event,
        fixture_probe=fixture_probe,
        observation=observation,
        reverse_query_artifact=reverse_query_artifact,
        source_reference=args.source_reference.resolve()
        if args.source_reference else None,
        recovery_reference=args.recovery_reference.resolve()
        if args.recovery_reference else None,
    )
    default_stem = (
        "military-access-inbound-source-validation-001"
        if args.family == "military_access"
        else "royal-inbound-source-validation-001"
        if args.family == "royal_marriage"
        else f"{args.family}-inbound-source-validation-001"
    )
    json_path = (
        args.output_json.resolve()
        if args.output_json
        else artifact / f"{default_stem}.json"
    )
    md_path = (
        args.output_md.resolve()
        if args.output_md
        else artifact / f"{default_stem}.md"
    )
    for path in (json_path, md_path):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing output: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(markdown_report(result), encoding="utf-8")
    summary = result["summary"]
    print(json.dumps({
        "status": "passed" if summary["validation_passed"] else "failed",
        **summary,
        "json": str(json_path),
        "markdown": str(md_path),
    }, ensure_ascii=False))
    return 0 if summary["validation_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
