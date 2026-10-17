"""Validate a Royal business artifact against its observed native source chain.

This is a bounded, read-only validator for an execution artifact containing
``report.json`` and ``native-events-slice.jsonl``.  It associates the actual
submission/result receipt with the independently observed transport -> load ->
clone -> command-entry chain.  A queue flag or a submitted report is never
treated as a business result.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


WORK_DIR = Path(__file__).resolve().parent
if str(WORK_DIR) not in sys.path:
    sys.path.insert(0, str(WORK_DIR))

from validate_alliance_transport import (  # noqa: E402
    HEADER_FIELDS,
    as_int,
    chain_for_transport,
    family_for_action,
    load_events,
    payload_of,
    payload_summary,
    sha256_file,
)


MAX_INPUT_BYTES = 10 * 1024 * 1024
TRANSPORT_EVENT = "native_alliance_transport_completed"
CLONE_EVENT = "native_alliance_wrapper_clone"
ENTRY_EVENT = "native_alliance_command_entry_observed"
SUBMISSION_EVENT = "native_alliance_submission_result"
RESPONSE_EVENT = "native_alliance_response_result"
EXECUTION_EVENT = "native_alliance_execution_result"


def true_value(value: Any) -> bool:
    return value is True


def same_int(left: Any, right: Any) -> bool:
    left_int = as_int(left)
    right_int = as_int(right)
    return left_int is not None and right_int is not None and left_int == right_int


def bounded_size(path: Path) -> int:
    size = path.stat().st_size
    if size > MAX_INPUT_BYTES:
        raise ValueError(f"input exceeds 10 MiB bound: {path} ({size} bytes)")
    return size


def read_json(path: Path) -> dict[str, Any]:
    bounded_size(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def pick_terminal_result(report: dict[str, Any]) -> dict[str, Any] | None:
    """Return the terminal public result, including a poll final for LIT."""

    candidates: list[dict[str, Any]] = []
    poll = report.get("poll")
    if isinstance(poll, dict) and isinstance(poll.get("final"), dict):
        candidates.append(poll["final"])
    for key in ("duplicate", "reopened_result", "execution"):
        value = report.get(key)
        if isinstance(value, dict):
            candidates.append(value)
    terminal_outcomes = {"accepted", "rejected", "executed"}
    for candidate in candidates:
        result = candidate.get("result")
        if not isinstance(result, dict):
            continue
        if result.get("native_outcome") in terminal_outcomes:
            return result
        if candidate.get("game_outcome") in terminal_outcomes:
            return result
    return None


def exact_binding(event: dict[str, Any], *, request_id: str, session_id: str,
                  action_id: str, actor: str, recipient: str, date_raw: int,
                  phase: str) -> bool:
    return (
        str(event.get("request_id")) == request_id
        and str(event.get("session_id")) == session_id
        and event.get("action_id") == action_id
        and event.get("actor") == actor
        and event.get("recipient") == recipient
        and same_int(event.get("date_raw"), date_raw)
        and event.get("phase") == phase
    )


def business_result_checks(action_id: str, expected_outcome: str,
                           result: dict[str, Any] | None) -> dict[str, bool]:
    family = family_for_action(action_id)
    if result is None:
        return {
            "native_event_name_matches_action": False,
            "native_outcome_matches_report": False,
            "native_state_matches_outcome": False,
            "native_variant_matches_action": False,
            "family_is_royal_marriage": False,
            "request_binding_verified": False,
            "response_or_execution_verified": False,
            "royal_marriage_transition": False,
        }
    is_offer = action_id == "offer_royal_marriage"
    expected_event = RESPONSE_EVENT if is_offer else EXECUTION_EVENT
    expected_state = 2 if expected_outcome == "accepted" else 1 if expected_outcome == "rejected" else 0
    event_ok = result.get("event") == expected_event
    variant_ok = (not is_offer) and same_int(result.get("native_variant"), 0)
    transition_ok = (
        (is_offer and result.get("royal_marriage_after") is (expected_outcome == "accepted"))
        or (
            not is_offer
            and result.get("royal_marriage_before") is True
            and result.get("royal_marriage_after") is False
        )
    )
    return {
        "native_event_name_matches_action": event_ok,
        "native_outcome_matches_report": result.get("native_outcome", result.get("outcome")) == expected_outcome,
        "native_state_matches_outcome": same_int(result.get("native_state"), expected_state),
        "native_variant_matches_action": variant_ok if not is_offer else "native_variant" not in result,
        "family_is_royal_marriage": result.get("family") == family == "royal_marriage",
        "request_binding_verified": true_value(result.get("request_binding_verified")),
        "response_or_execution_verified": true_value(
            result.get("response_verified") if is_offer else result.get("execution_verified")
        ),
        "royal_marriage_transition": transition_ok,
    }


def result_summary(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if result is None:
        return None
    fields = (
        "event", "request_id", "session_id", "action_id", "actor", "recipient",
        "phase", "date_raw", "outcome", "native_outcome", "native_state",
        "native_variant", "family", "royal_marriage_before", "royal_marriage_after",
        "response_verified", "execution_verified", "request_binding_verified",
    )
    summary = {field: result.get(field) for field in fields if field in result}
    if "native_outcome" not in summary and "outcome" in result:
        summary["native_outcome"] = result.get("outcome")
    summary.pop("outcome", None)
    return summary


def report_matches_native_result(report_result: dict[str, Any] | None,
                                 native_result: dict[str, Any] | None) -> bool:
    """Compare the public projection with the actual wire receipt.

    The observed Royal response event omits ``royal_marriage_before`` while the
    bridge's public projection supplies the known pre-state.  Compare every
    field present in the native receipt and allow that documented projection
    enrichment; the result identity, outcome, state, family, transition and
    verification flags still have to agree.
    """
    if report_result is None or native_result is None:
        return False
    fields = (
        "event", "request_id", "action_id", "actor", "recipient", "phase",
        "date_raw", "family", "native_state", "native_variant",
        "native_outcome", "royal_marriage_after",
        "response_verified", "execution_verified", "request_binding_verified",
    )
    for field in fields:
        native_value = native_result.get(field)
        if field == "native_outcome" and "native_outcome" not in native_result:
            native_value = native_result.get("outcome")
        if field == "native_outcome":
            public_value = report_result.get("native_outcome", report_result.get("outcome"))
        else:
            public_value = report_result.get(field)
        if field in native_result or (field == "native_outcome" and "outcome" in native_result):
            if public_value != native_value:
                return False
    return True


def submission_summary(submission: dict[str, Any] | None) -> dict[str, Any] | None:
    if submission is None:
        return None
    fields = (
        "event", "request_id", "session_id", "action_id", "actor", "recipient",
        "phase", "date_raw", "submitted", "native_queue_verified", "transport_ring",
        "native_origin", "native_flags", "native_sequence",
    )
    return {field: submission.get(field) for field in fields if field in submission}


def entry_prefix(entry: dict[str, Any]) -> dict[str, Any]:
    return {field: entry.get(field) for field in HEADER_FIELDS if field in entry}


def generation_address_chain(chain: dict[str, Any], raw: dict[str, dict[str, Any]]) -> dict[str, Any]:
    transport = raw["transport"]
    clone = raw["clone"]
    entry = raw["entry"]
    source = transport.get("source") if isinstance(transport.get("source"), dict) else {}
    loaded = transport.get("loaded") if isinstance(transport.get("loaded"), dict) else {}
    clone_source = clone.get("source") if isinstance(clone.get("source"), dict) else {}
    clone_target = clone.get("target") if isinstance(clone.get("target"), dict) else {}
    entry_source = entry.get("source") if isinstance(entry.get("source"), dict) else {}
    return {
        "transport": {
            "source_addr": source.get("addr"),
            "source_action": source.get("action"),
            "outgoing": transport.get("outgoing"),
            "loaded_addr": loaded.get("addr"),
            "loaded_action": loaded.get("action"),
            "peer": transport.get("peer"),
            "peer_owner": transport.get("peer_owner"),
            "peer_input_ring": transport.get("peer_input_ring"),
            "world_dispatcher": transport.get("world_dispatcher"),
            "world_transport": transport.get("world_transport"),
        },
        "clone": {
            "receiver": clone.get("receiver"),
            "receiver_host": clone.get("receiver_host"),
            "receiver_input_ring": clone.get("receiver_input_ring"),
            "world_dispatcher": clone.get("world_dispatcher"),
            "world_transport": clone.get("world_transport"),
            "source_addr": clone_source.get("addr"),
            "source_action": clone_source.get("action"),
            "target_addr": clone_target.get("addr"),
            "target_action": clone_target.get("action"),
            "native_result": clone.get("native_result"),
        },
        "entry": {
            "command": entry.get("command"),
            "action": entry.get("action"),
            "source_payload_addr": entry_source.get("addr"),
            "protocol_sequence": entry.get("protocol_sequence"),
            "callback_sequence": entry.get("callback_sequence"),
            "prefix": entry_prefix(entry),
        },
        "link_checks": {
            "transport_outgoing_source": same_int(transport.get("outgoing"), source.get("addr")),
            "transport_loaded_distinct": (
                source.get("addr") is not None and loaded.get("addr") is not None
                and not same_int(source.get("addr"), loaded.get("addr"))
            ),
            "clone_receiver_peer": same_int(clone.get("receiver"), transport.get("peer")),
            "clone_source_loaded": same_int(clone_source.get("addr"), loaded.get("addr")),
            "clone_native_result_target": same_int(clone.get("native_result"), clone_target.get("addr")),
            "entry_command_target": same_int(entry.get("command"), clone_target.get("addr")),
            "entry_action_target": same_int(entry.get("action"), clone_target.get("action")),
            "entry_source_target_payload": same_int(
                entry_source.get("addr"), payload_of(clone_target).get("addr")
            ),
        },
    }


def chain_payloads(chain: dict[str, Any], raw: dict[str, dict[str, Any]]) -> dict[str, Any]:
    transport = raw["transport"]
    clone = raw["clone"]
    entry = raw["entry"]
    return {
        "transport_source": payload_summary(transport.get("source")),
        "transport_loaded": payload_summary(transport.get("loaded")),
        "clone_source": payload_summary(clone.get("source")),
        "clone_target": payload_summary(clone.get("target")),
        "entry_source": payload_summary(entry.get("source")),
    }


def collect_chains(event_data: dict[str, Any], session_id: str, family: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    transports = sorted(
        (event for event in event_data["transport"] if str(event.get("session_id")) == session_id),
        key=lambda event: as_int(event.get("callback_begin"), -1) or -1,
    )
    clones = list(event_data["clones"])
    entries = list(event_data["entries"])
    used_clone_lines: set[int] = set()
    used_entry_lines: set[int] = set()
    chains: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    for transport in transports:
        available_clones = [item for item in clones if item["_line"] not in used_clone_lines]
        available_entries = [item for item in entries if item["_line"] not in used_entry_lines]
        chain, reason = chain_for_transport(
            transport, available_clones, available_entries, session_id, family
        )
        if chain is None:
            unmatched.append({"transport_line": transport.get("_line"), "reason": reason})
            continue
        used_clone_lines.add(chain["clone"]["line"])
        used_entry_lines.add(chain["entry"]["line"])
        chains.append(chain)
    return chains, unmatched


def validate_artifact(artifact: Path) -> dict[str, Any]:
    report_path = artifact / "report.json"
    events_path = artifact / "native-events-slice.jsonl"
    report_size = bounded_size(report_path)
    events_size = bounded_size(events_path)
    report = read_json(report_path)
    event_data = load_events(events_path)
    action_id = str(report.get("action_id", ""))
    request_id = str(report.get("request_id", ""))
    session = report.get("session") if isinstance(report.get("session"), dict) else {}
    session_id = str(session.get("session_id", ""))
    actor = "FRA"
    recipient = str(report.get("recipient", ""))
    phase = "initiate"
    date_raw = as_int(report.get("expected_date_raw"))
    expected_outcome = str(report.get("expected_outcome", ""))
    family = family_for_action(action_id)
    if family != "royal_marriage":
        raise ValueError(f"not a Royal action: {action_id}")
    if date_raw is None:
        raise ValueError("missing expected_date_raw")

    # load_events intentionally retains only transport/clone/entry records.  The
    # business records are streamed once more, still under the 10 MiB bound, so
    # the validator never materializes unrelated observations.
    submissions = []
    actual_results = []
    business_records: list[dict[str, Any]] = []
    with events_path.open("r", encoding="utf-8") as stream:
        for line_number, raw_line in enumerate(stream, 1):
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            name = event.get("event")
            if name == SUBMISSION_EVENT:
                submissions.append({**event, "_line": line_number})
            elif name in (RESPONSE_EVENT, EXECUTION_EVENT):
                actual_results.append({**event, "_line": line_number})
            if name in (SUBMISSION_EVENT, RESPONSE_EVENT, EXECUTION_EVENT):
                business_records.append(event)

    exact_submissions = [
        event for event in submissions
        if exact_binding(event, request_id=request_id, session_id=session_id,
                         action_id=action_id, actor=actor, recipient=recipient,
                         date_raw=date_raw, phase=phase)
    ]
    exact_results = [
        event for event in actual_results
        if exact_binding(event, request_id=request_id, session_id=session_id,
                         action_id=action_id, actor=actor, recipient=recipient,
                         date_raw=date_raw, phase=phase)
    ]
    submission = exact_submissions[0] if len(exact_submissions) == 1 else None
    native_result = exact_results[0] if len(exact_results) == 1 else None
    terminal_public_result = pick_terminal_result(report)

    chains, unmatched = collect_chains(event_data, session_id, family)
    selected_chain = None
    selected_raw: dict[str, dict[str, Any]] | None = None
    if submission is not None:
        native_sequence = as_int(submission.get("native_sequence"))
        candidates = [
            chain for chain in chains
            if native_sequence is not None
            and same_int(chain["entry"].get("protocol_sequence"), native_sequence)
        ]
        if len(candidates) == 1:
            selected_chain = candidates[0]
            by_line = {
                event["_line"]: event
                for group in (event_data["transport"], event_data["clones"], event_data["entries"])
                for event in group
            }
            selected_raw = {
                "transport": by_line[selected_chain["transport"]["line"]],
                "clone": by_line[selected_chain["clone"]["line"]],
                "entry": by_line[selected_chain["entry"]["line"]],
            }
    result_checks = business_result_checks(action_id, expected_outcome, native_result)
    report_result = terminal_public_result
    report_result_checks = {
        "report_terminal_result_present": report_result is not None,
        "report_result_action_bound": report_result is not None and report_result.get("action_id") == action_id,
        "report_result_request_bound": report_result is not None and report_result.get("request_id") == request_id,
        "report_result_outcome_bound": report_result is not None and report_result.get("native_outcome") == expected_outcome,
        "report_result_matches_native_event": (
            report_matches_native_result(report_result, native_result)
        ),
    }
    chain_checks: dict[str, bool] = {}
    address_chain: dict[str, Any] | None = None
    payloads: dict[str, Any] | None = None
    if selected_chain is not None and selected_raw is not None:
        native_sequence = as_int(submission.get("native_sequence")) if submission else None
        selected_chain_checks = selected_chain.get("checks", {})
        chain_checks = {
            "transport_load_clone_entry_chain": True,
            "full9payload_transport_load_equal": all(
                selected_chain_checks.get(key) is True
                for key in ("full_payload_equal", "clone_source_payload_equal",
                            "clone_target_payload_equal", "entry_source_payload_equal")
            ),
            "headers_transport_load_equal": selected_chain_checks.get("full_header_equal") is True,
            "family_extra60_all_stages": all(
                value is True for key, value in selected_chain_checks.items()
                if "family_extra60" in key or key in ("source_family_extra60_valid", "loaded_family_extra60_valid")
            ),
            "stage_order_transport_clone_entry": all(
                selected_chain_checks.get(key) is True
                for key in ("transport_before_clone", "clone_begin_before_clone_end", "clone_before_entry")
            ),
            "source_protocol_sequence_matches_native_submission": (
                native_sequence is not None
                and same_int(selected_chain["entry"].get("protocol_sequence"), native_sequence)
            ),
        }
        address_chain = generation_address_chain(selected_chain, selected_raw)
        payloads = chain_payloads(selected_chain, selected_raw)
        chain_checks["generation_address_chain"] = all(address_chain["link_checks"].values())
    else:
        chain_checks = {
            "transport_load_clone_entry_chain": False,
            "full9payload_transport_load_equal": False,
            "headers_transport_load_equal": False,
            "family_extra60_all_stages": False,
            "stage_order_transport_clone_entry": False,
            "source_protocol_sequence_matches_native_submission": False,
            "generation_address_chain": False,
        }

    checks = {
        "bounded_input_files": report_size <= MAX_INPUT_BYTES and events_size <= MAX_INPUT_BYTES,
        "jsonl_fully_parsed": not event_data.get("malformed_lines"),
        "session_bound": bool(session_id) and event_data.get("session_ids") == [session_id],
        "report_status_passed": report.get("status") == "passed",
        "action_family_royal_marriage": family == "royal_marriage",
        "submission_receipt_bound": (
            len(exact_submissions) == 1
            and true_value(exact_submissions[0].get("submitted"))
            and true_value(exact_submissions[0].get("native_queue_verified"))
            and true_value(exact_submissions[0].get("transport_ring"))
        ),
        "submission_native_origin_flags_valid": (
            submission is not None
            and same_int(submission.get("native_origin"), 0xFFFF)
            and same_int(submission.get("native_flags"), 0)
            and as_int(submission.get("native_sequence")) is not None
        ),
        "native_result_single_exact_binding": len(exact_results) == 1,
        **result_checks,
        **chain_checks,
        **report_result_checks,
    }
    passed = sum(value is True for value in checks.values())
    failed = len(checks) - passed
    result = {
        "validator": {
            "name": "validate_royal_business_source",
            "version": 1,
            "bounded_input_bytes": MAX_INPUT_BYTES,
            "read_only": True,
        },
        "artifact": str(artifact),
        "inputs": {
            "report": {"path": str(report_path), "bytes": report_size, "sha256": sha256_file(report_path)},
            "native_events": {"path": str(events_path), "bytes": events_size, "sha256": sha256_file(events_path)},
        },
        "request_binding": {
            "request_id": request_id,
            "session_id": session_id,
            "action_id": action_id,
            "family": family,
            "actor": actor,
            "recipient": recipient,
            "phase": phase,
            "date_raw": date_raw,
            "expected_outcome": expected_outcome,
        },
        "native_submission": submission_summary(submission),
        "native_result": result_summary(native_result),
        "report_terminal_result": result_summary(report_result),
        "business_record_counts": {
            "submission_total": len(submissions),
            "submission_exact_binding": len(exact_submissions),
            "actual_result_total": len(actual_results),
            "actual_result_exact_binding": len(exact_results),
        },
        "source_chain": {
            "strict_chain_count": len(chains),
            "unmatched_transports": unmatched,
            "all_strict_chains": chains,
            "selected_chain": selected_chain,
            "selected_generation_address_chain": address_chain,
            "selected_full9_payloads": payloads,
            "selected_entry_prefix": (
                entry_prefix(selected_raw["entry"]) if selected_raw is not None else None
            ),
        },
        "checks": checks,
        "summary": {
            "validation_passed": failed == 0,
            "total_checks": len(checks),
            "passed_checks": passed,
            "failed_checks": failed,
        },
    }
    return result


def markdown_report(result: dict[str, Any]) -> str:
    binding = result["request_binding"]
    summary = result["summary"]
    lines = [
        "# Royal business source validation",
        "",
        f"- Status: **{'passed' if summary['validation_passed'] else 'failed'}**",
        f"- Checks: {summary['passed_checks']}/{summary['total_checks']} passed",
        f"- Artifact: `{result['artifact']}`",
        f"- Request/session/action: `{binding['request_id']}` / `{binding['session_id']}` / `{binding['action_id']}`",
        f"- Family and route: `{binding['family']}`, `{binding['actor']} -> {binding['recipient']}`, phase `{binding['phase']}`, date `{binding['date_raw']}`",
        f"- Expected native outcome: `{binding['expected_outcome']}`",
        "",
        "## Checks",
        "",
        "| Check | Result |",
        "|---|---|",
    ]
    for name, value in result["checks"].items():
        lines.append(f"| `{name}` | {'PASS' if value else 'FAIL'} |")
    source = result["source_chain"]
    selected = source.get("selected_chain")
    lines.extend(["", "## Source chain", ""])
    if selected:
        lines.append(
            f"Selected transport/clone/entry lines: `{selected['transport']['line']}` / "
            f"`{selected['clone']['line']}` / `{selected['entry']['line']}`; "
            f"entry protocol sequence `{selected['entry'].get('protocol_sequence')}`."
        )
        lines.append("The JSON report records the full nine-field payload at transport source/load, clone source/target, and command entry, the header prefix, and the generation address chain.")
    else:
        lines.append("No strict chain was selected.")
    if source.get("unmatched_transports"):
        lines.append(f"Unmatched transports: `{source['unmatched_transports']}`")
    lines.extend(["", "## Native receipt", ""])
    lines.append(f"Submission: `{result['native_submission']}`")
    lines.append(f"Actual native result: `{result['native_result']}`")
    lines.append(f"Terminal public result used for comparison: `{result['report_terminal_result']}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    args = parser.parse_args()
    artifact = args.artifact
    result = validate_artifact(artifact)
    json_path = args.output_json or artifact / "royal-business-source-validation-001.json"
    md_path = args.output_md or artifact / "royal-business-source-validation-001.md"
    for path in (json_path, md_path):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing output: {path}")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(markdown_report(result), encoding="utf-8")
    summary = result["summary"]
    print(json.dumps({"status": "passed" if summary["validation_passed"] else "failed", **summary,
                      "json": str(json_path), "markdown": str(md_path)}, ensure_ascii=False))
    return 0 if summary["validation_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
