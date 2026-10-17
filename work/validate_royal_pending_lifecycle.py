"""Validate the natural Royal inbound pending lifecycle without running EU4.

The validator reads one bounded observation slice and the original JSONL control
probe from the same runtime directory.  It proves that a real PRO -> FRA Royal
Marriage proposal entered the native pending list, then requires daily native
AI-choice holds while the game advances and remains paused for POR.  It never
starts a process, installs a DLL, submits a request, advances time, or rewrites
the source logs.  A response artifact is optional and is checked only when the
operator supplies one.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Iterator, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from work.validate_alliance_lifecycle import (  # noqa: E402
    InputError,
    _bounded_json,
    _jsonl,
    _stream_sha256,
)


ACTION = "offer_royal_marriage"
FAMILY = "royal_marriage"
ACTOR = "PRO"
RECIPIENT = "FRA"
DECISION_COUNTRY = "FRA"
MAX_METADATA_BYTES = 4 * 1024 * 1024
MAX_EVENTS = 250_000
MAX_SELECTED = 512
MAX_LINE_BYTES = 256 * 1024


class ValidationInputError(ValueError):
    """An input artifact is missing or has an invalid bounded schema."""


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text, 0)
        except ValueError:
            return None
    return None


def _true(value: Any) -> bool:
    return value is True


def _read_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValidationInputError(f"{label}_missing:{path}")
    value = _bounded_json(path, MAX_METADATA_BYTES)
    if not isinstance(value, dict):
        raise ValidationInputError(f"{label}_not_object:{path}")
    return value


def _native_tag(value: Any) -> str | None:
    """Decode the three ASCII tag bytes in a packed native country handle."""

    if isinstance(value, str):
        text = value.strip().upper()
        if len(text) == 3 and text.isascii() and text.isalpha():
            return text
        try:
            value = int(text, 0)
        except ValueError:
            return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    raw = int(value).to_bytes(8, "little", signed=False)
    tag = raw[:3].decode("ascii", errors="ignore")
    return tag if len(tag) == 3 and tag.isalpha() else None


def _shape_tag(shape: Mapping[str, Any], field: str, expected: str) -> bool:
    value = shape.get(field)
    if value is None:
        return False
    return _native_tag(value) == expected


def _shape_is_full_royal(shape: Any, *, expected_state: int | None = None) -> bool:
    if not isinstance(shape, Mapping):
        return False
    if shape.get("family") != FAMILY or _int(shape.get("extra60")) != 0:
        return False
    required = (
        "addr", "readable", "matched", "handles_canonical", "tracked",
        "vtable_rva", "discriminator", "actor10", "mirror18", "recipient20",
        "date28", "date2c", "envoy30", "state34", "variant38", "proposal3c",
    )
    if any(key not in shape for key in required):
        return False
    if not all(_true(shape.get(key)) for key in ("readable", "matched", "handles_canonical")):
        return False
    if expected_state is not None and _int(shape.get("state34")) != expected_state:
        return False
    return _shape_tag(shape, "actor10", ACTOR) and _shape_tag(shape, "recipient20", RECIPIENT)


@dataclass
class LogScan:
    path: Path
    bytes: int = 0
    scanned_bytes: int = 0
    end_offset: int | None = None
    lines: int = 0
    parsed: int = 0
    malformed_lines: int = 0
    event_counts: Counter[str] = field(default_factory=Counter)
    session_mismatches: int = 0
    offers: list[tuple[int, dict[str, Any]]] = field(default_factory=list)
    holds: list[tuple[int, dict[str, Any]]] = field(default_factory=list)
    command_entries: list[tuple[int, dict[str, Any]]] = field(default_factory=list)
    rejected: list[tuple[int, dict[str, Any]]] = field(default_factory=list)
    lifecycle_clones: list[tuple[int, dict[str, Any]]] = field(default_factory=list)
    fixture_events: list[tuple[int, dict[str, Any]]] = field(default_factory=list)
    advance_begin: list[tuple[int, dict[str, Any]]] = field(default_factory=list)
    advance_complete: list[tuple[int, dict[str, Any]]] = field(default_factory=list)
    health: list[tuple[int, dict[str, Any]]] = field(default_factory=list)

    def select(self, target: list[tuple[int, dict[str, Any]]],
               line: int, event: dict[str, Any]) -> None:
        if len(target) < MAX_SELECTED:
            target.append((line, event))


def _iter_jsonl_until(path: Path, end_offset: int | None) -> Iterator[tuple[int, dict[str, Any] | None, str | None]]:
    """Stream complete JSONL records before an optional exclusive byte bound."""

    if end_offset is None:
        yield from _jsonl(path, MAX_EVENTS * 1024)
        return
    try:
        size = path.stat().st_size
    except OSError as error:
        raise ValidationInputError(f"jsonl_stat:{path}:{error}") from error
    if end_offset < 0 or end_offset > size:
        raise ValidationInputError(
            f"jsonl_end_offset_invalid:{path}:{end_offset}:{size}")
    if size > MAX_EVENTS * 1024:
        raise ValidationInputError(f"jsonl_exceeds_bound:{path}")
    try:
        with path.open("rb") as stream:
            for line_number in range(1, MAX_EVENTS + 1):
                line_start = stream.tell()
                if line_start >= end_offset:
                    break
                raw = stream.readline()
                if not raw:
                    break
                # The offset is defined at a log-record boundary.  Never
                # parse a record that would cross an explicitly supplied
                # response start, even if a truncated file contains bytes
                # after the boundary.
                if line_start + len(raw) > end_offset:
                    break
                if len(raw) > MAX_LINE_BYTES:
                    yield line_number, None, "line_too_large"
                    continue
                try:
                    value = json.loads(raw.decode("utf-8-sig" if line_number == 1 else "utf-8"))
                except (UnicodeError, json.JSONDecodeError):
                    yield line_number, None, "invalid_json"
                    continue
                if not isinstance(value, dict):
                    yield line_number, None, "non_object"
                    continue
                yield line_number, value, None
    except OSError as error:
        raise ValidationInputError(f"jsonl_read:{path}:{error}") from error


def _scan_jsonl(path: Path, session_id: str,
                end_offset: int | None = None) -> LogScan:
    if not path.is_file():
        raise ValidationInputError(f"jsonl_missing:{path}")
    try:
        size = path.stat().st_size
    except OSError as error:
        raise ValidationInputError(f"jsonl_stat:{path}:{error}") from error
    if end_offset is not None and (end_offset < 0 or end_offset > size):
        raise ValidationInputError(f"jsonl_end_offset_invalid:{path}:{end_offset}:{size}")
    result = LogScan(
        path=path,
        bytes=size,
        scanned_bytes=min(size, end_offset) if end_offset is not None else size,
        end_offset=end_offset,
    )
    for line, event, parse_error in _iter_jsonl_until(path, end_offset):
        result.lines += 1
        if parse_error is not None or event is None:
            result.malformed_lines += 1
            continue
        result.parsed += 1
        name = event.get("event")
        if not isinstance(name, str):
            continue
        result.event_counts[name] += 1
        event_session = event.get("session_id")
        if event_session is not None and event_session != session_id:
            result.session_mismatches += 1

        lowered = name.lower()
        if "inbound_test" in lowered or "fixture" in lowered:
            result.select(result.fixture_events, line, event)
        if name == "native_alliance_inbound_offer":
            result.select(result.offers, line, event)
        elif name == "native_diplomacy_inbound_ai_choice_held":
            result.select(result.holds, line, event)
        elif name == "native_alliance_command_entry_observed":
            if event.get("action_id") == ACTION:
                result.select(result.command_entries, line, event)
        elif name == "native_alliance_execution_rejected":
            result.select(result.rejected, line, event)
        elif name == "native_alliance_lifecycle" and event.get("kind") == "clone":
            source = event.get("source")
            target = event.get("target")
            if _shape_is_full_royal(source) or _shape_is_full_royal(target):
                result.select(result.lifecycle_clones, line, event)
        elif name == "control_advance_begin":
            result.select(result.advance_begin, line, event)
        elif name == "control_advance_complete":
            result.select(result.advance_complete, line, event)
        elif name == "diplomacy_observer_health":
            result.select(result.health, line, event)
        if result.lines > MAX_EVENTS:
            raise ValidationInputError(f"jsonl_event_limit_exceeded:{path}")
    return result


def _matching_offer(event: Mapping[str, Any], session_id: str) -> bool:
    return (
        event.get("session_id") == session_id
        and event.get("event") == "native_alliance_inbound_offer"
        and event.get("action_id") == ACTION
        and event.get("family") == FAMILY
        and event.get("actor") == ACTOR
        and event.get("mirror") == ACTOR
        and event.get("recipient") == RECIPIENT
    )


def _offer_checks(offer: Mapping[str, Any] | None) -> dict[str, bool]:
    if offer is None:
        return {
            "natural_offer_exact_pro_to_fra": False,
            "offer_native_pending_source": False,
            "pending_new_node_and_payload_readable": False,
            "pending_full_family": False,
            "pending_extra60_zero": False,
            "pending_token_legal": False,
            "pending_state0_variant1": False,
        }
    proposal_id = _int(offer.get("proposal_id"))
    token = _int(offer.get("token3c"))
    proposal_token = _int(offer.get("proposal3c"))
    return {
        "natural_offer_exact_pro_to_fra": (
            offer.get("action_id") == ACTION and offer.get("family") == FAMILY
            and offer.get("actor") == ACTOR and offer.get("mirror") == ACTOR
            and offer.get("recipient") == RECIPIENT
        ),
        "offer_native_pending_source": (
            offer.get("pending_source") == "native_executor_pending_block"
            and _true(offer.get("source_verified"))
            and _true(offer.get("call_redirected"))
            and offer.get("business_result") == "pending_observed"
        ),
        "pending_new_node_and_payload_readable": (
            _true(offer.get("new_entry"))
            and _true(offer.get("queue_readable"))
            and _true(offer.get("list_integrity"))
            and _true(offer.get("payload_readable"))
        ),
        "pending_full_family": offer.get("family") == FAMILY and "family" in offer,
        "pending_extra60_zero": "extra60" in offer and _int(offer.get("extra60")) == 0,
        "pending_token_legal": (
            proposal_id is not None and proposal_id > 0
            and token is not None and token > 0
            and proposal_token is not None and proposal_token == token
        ),
        "pending_state0_variant1": (
            offer.get("phase") == "initiate"
            and _int(offer.get("state34")) == 0
            and _int(offer.get("variant38")) == 1
        ),
    }


def _clone_matches_offer(event: Mapping[str, Any], offer: Mapping[str, Any]) -> bool:
    source = event.get("source")
    target = event.get("target")
    if not (_shape_is_full_royal(source) and _shape_is_full_royal(target)):
        return False
    offer_date = _int(offer.get("date28"))
    source_date = _int(source.get("date28")) if isinstance(source, Mapping) else None
    target_date = _int(target.get("date28")) if isinstance(target, Mapping) else None
    source_addr = source.get("addr") if isinstance(source, Mapping) else None
    target_addr = target.get("addr") if isinstance(target, Mapping) else None
    return (
        offer_date is not None and source_date == offer_date and target_date == offer_date
        and source_addr is not None and target_addr is not None and source_addr != target_addr
        and _true(target.get("tracked"))
    )


def _command_matches_pending_offer(event: Mapping[str, Any],
                                   offer: Mapping[str, Any]) -> bool:
    """Bind a later native command entry to the exact pending payload."""

    source = event.get("source")
    if not _shape_is_full_royal(source, expected_state=_int(event.get("state_raw"))):
        return False
    if not isinstance(source, Mapping):
        return False
    if _int(source.get("date28")) != _int(offer.get("date28")):
        return False
    if _int(source.get("extra60")) != _int(offer.get("extra60")):
        return False
    # Native command entries expose the stable payload token as proposal3c;
    # newer observers may additionally expose token3c or proposal_id.
    stable_proposal = _int(offer.get("proposal3c"))
    stable_token = _int(offer.get("token3c"))
    source_proposal = _int(source.get("proposal3c"))
    source_token = _int(source.get("token3c"))
    event_proposal = _int(event.get("proposal_id"))
    if stable_proposal is not None and source_proposal != stable_proposal:
        return False
    if source_token is not None and source_token != stable_token:
        return False
    if event_proposal is not None and event_proposal != _int(offer.get("proposal_id")):
        return False
    return source_proposal is not None or source_token is not None or event_proposal is not None


def _public_event(line: int, event: Mapping[str, Any]) -> dict[str, Any]:
    return {"line": line, **dict(event)}


def _hold_event_key(event: Mapping[str, Any]) -> tuple[Any, ...]:
    """Identify one native hold without depending on its source slice."""

    return (
        event.get("session_id"), event.get("action_id"),
        _int(event.get("proposal_id")), _int(event.get("token3c")),
        _int(event.get("date_raw")), _int(event.get("hold_count")),
    )


def _merge_hold_events(observed: LogScan, control: LogScan,
                       offer: Mapping[str, Any] | None,
                       session_id: str) -> list[tuple[int, dict[str, Any]]]:
    """Merge overlapping observation/control slices without double counting."""

    if offer is None:
        return []
    proposal_id = _int(offer.get("proposal_id"))
    token = _int(offer.get("token3c"))
    merged: list[tuple[int, dict[str, Any]]] = []
    seen: set[tuple[Any, ...]] = set()
    # Prefer the observation slice when both sources contain the same record;
    # control then supplies any records emitted after that slice ended.
    for source in (observed.holds, control.holds):
        for line, event in source:
            if not (
                event.get("session_id") == session_id
                and event.get("action_id") == ACTION
                and event.get("decision_country") == DECISION_COUNTRY
                and _int(event.get("proposal_id")) == proposal_id
                and _int(event.get("token3c")) == token
            ):
                continue
            key = _hold_event_key(event)
            if key in seen:
                continue
            seen.add(key)
            merged.append((line, event))
    return merged


def _response_records(value: Any, limit: int = 100_000) -> Iterator[Mapping[str, Any]]:
    count = 0
    stack = [value]
    while stack and count < limit:
        current = stack.pop()
        if isinstance(current, Mapping):
            count += 1
            yield current
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def _response_native_records(report_path: Path, report: Mapping[str, Any]) -> tuple[list[Mapping[str, Any]], dict[str, Any]]:
    """Read the bounded native-events sidecar referenced by a response report."""

    metadata = report.get("native_events")
    if not isinstance(metadata, Mapping):
        return [], {"present": False, "readable": False, "reason": "native_events_metadata_missing"}
    declared = metadata.get("path")
    if not isinstance(declared, str) or not declared:
        return [], {"present": True, "readable": False, "reason": "native_events_path_missing"}
    native_path = Path(declared).expanduser()
    if not native_path.is_file():
        native_path = report_path.parent / Path(declared).name
    if not native_path.is_file():
        return [], {"present": True, "readable": False,
                    "path": str(native_path), "reason": "native_events_file_missing"}
    selected: list[Mapping[str, Any]] = []
    parsed = 0
    malformed = 0
    try:
        for _, event, parse_error in _jsonl(native_path, 16 * 1024 * 1024):
            if parse_error is not None or event is None:
                malformed += 1
                continue
            parsed += 1
            if len(selected) < MAX_SELECTED:
                selected.append(event)
    except (InputError, OSError, ValueError) as error:
        return [], {"present": True, "readable": False,
                    "path": str(native_path), "reason": str(error)}
    return selected, {
        "present": True,
        "readable": malformed == 0,
        "path": str(native_path),
        "parsed": parsed,
        "malformed": malformed,
        "sha256": metadata.get("sha256"),
        "start_offset": _int(metadata.get("start_offset")),
        "end_offset": _int(metadata.get("end_offset")),
        "complete": metadata.get("complete"),
    }


def _public_proposal_is_exact(report: Mapping[str, Any],
                              offer: Mapping[str, Any] | None) -> tuple[bool, dict[str, Any]]:
    """Bind the public opaque proposal id to the native pending identity."""

    proposal = report.get("proposal")
    inspection = report.get("inspection")
    observed = inspection.get("observed_inbound_proposal") if isinstance(inspection, Mapping) else None
    parameters = inspection.get("parameters") if isinstance(inspection, Mapping) else None
    actual = parameters.get("actual") if isinstance(parameters, Mapping) else None
    public_id = proposal.get("proposal_id") if isinstance(proposal, Mapping) else None
    fields = ("action_id", "family", "actor", "recipient")
    exact = (
        isinstance(proposal, Mapping)
        and isinstance(public_id, str) and bool(public_id)
        and all(proposal.get(field) == expected for field, expected in (
            ("action_id", ACTION), ("family", FAMILY),
            ("actor", ACTOR), ("recipient", RECIPIENT)))
        and isinstance(observed, Mapping)
        and all(observed.get(field) == proposal.get(field) for field in fields)
        and observed.get("proposal_id") == public_id
        and isinstance(actual, Mapping)
        and actual.get("proposal_id") == public_id
    )
    native_id = _int(offer.get("proposal_id")) if isinstance(offer, Mapping) else None
    return exact, {
        "public_proposal_id": public_id,
        "native_pending_proposal_id": native_id,
        "observed_public_proposal_id": observed.get("proposal_id") if isinstance(observed, Mapping) else None,
        "inspection_actual_proposal_id": actual.get("proposal_id") if isinstance(actual, Mapping) else None,
    }


def _response_checks(path: Path, offer: Mapping[str, Any] | None,
                     session_id: str) -> dict[str, Any]:
    try:
        report = _read_object(path, "response_artifact")
    except (InputError, ValidationInputError) as error:
        return {
            "supplied": True,
            "path": str(path),
            "readable": False,
            "error": str(error),
            "checks": {"response_artifact_readable": False},
        }
    records = list(_response_records(report))
    native_records, native_metadata = _response_native_records(path, report)
    records.extend(native_records)
    public_proposal_exact, proposal_binding = _public_proposal_is_exact(report, offer)
    exact_proposal = [
        item for item in records
        if item.get("action_id") == ACTION
        and item.get("family") == FAMILY
        and item.get("actor") == ACTOR
        and item.get("recipient") == RECIPIENT
    ]
    pending_active = [
        item for item in records
        if _true(item.get("pending_active"))
        and item.get("action_id") == ACTION
        and item.get("family") == FAMILY
    ]
    native_validity = [
        item for item in records
        if item.get("action_id") == ACTION
        and item.get("family") == FAMILY
        and any(item.get(key) is True for key in
                ("native_validity", "native_result", "native_valid"))
    ]
    request_ids = {
        str(item.get("request_id")) for item in records
        if isinstance(item.get("request_id"), (str, int)) and str(item.get("request_id"))
    }
    terminal = [
        item for item in records
        if item.get("outcome") in {"accepted", "rejected"}
        or item.get("native_outcome") in {"accepted", "rejected"}
        # The execution wrapper exposes the terminal business result as
        # top-level ``status``/``game_outcome`` while the native receipt uses
        # ``outcome``.  Accept both representations from the same artifact.
        or item.get("status") in {"accepted", "rejected"}
        or item.get("game_outcome") in {"accepted", "rejected"}
    ]
    relation = [item for item in records if isinstance(item.get("royal_marriage_after"), bool)]
    native_proposal_ids = {
        _int(item.get("native_proposal_id")) for item in records
        if _int(item.get("native_proposal_id")) is not None
    }
    native_id_matches = (
        offer is not None
        and _int(offer.get("proposal_id")) is not None
        and _int(offer.get("proposal_id")) in native_proposal_ids
    )
    poll = report.get("poll")
    persisted = report.get("persisted")
    checks = {
        "response_artifact_readable": True,
        "public_proposal_exact_pro_to_fra": public_proposal_exact and bool(exact_proposal),
        "native_proposal_id_matches_pending": native_id_matches,
        "query_pending_active_present": bool(pending_active),
        "query_native_validity_present": bool(native_validity),
        "poll_final_present": isinstance(poll, Mapping) and isinstance(poll.get("final"), Mapping),
        "persisted_result_present": isinstance(persisted, Mapping),
        "unique_request_id": len(request_ids) == 1,
        "accepted_or_rejected_result": bool(terminal),
        "pending_removed_reported": any(_true(item.get("pending_removed")) for item in records),
        "royal_relation_result_reported": bool(relation),
        "response_session_binding": any(item.get("session_id") == session_id for item in records),
    }
    return {
        "supplied": True,
        "path": str(path),
        "readable": True,
        "native_events": native_metadata,
        "proposal_binding": proposal_binding,
        "native_proposal_ids": sorted(native_proposal_ids),
        "request_ids": sorted(request_ids),
        "terminal_results": len(terminal),
        "exact_proposal_records": len(exact_proposal),
        "pending_active_records": len(pending_active),
        "checks": checks,
    }


def _find_response_file(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.is_dir():
        resolved = resolved / "report.json"
    return resolved


def _control_log_bound(control_path: Path, response_artifact: Path | None) -> tuple[int | None, dict[str, Any]]:
    """Return the exclusive control-log bound for this validation run.

    A response artifact records the byte offset captured immediately before
    that request started.  Everything before that offset belongs to the
    pending observation; the response's own later records must not be judged
    as automatic AI responses.  With no response artifact, the current EOF is
    the intended bound.
    """

    try:
        size = control_path.stat().st_size
    except OSError as error:
        raise ValidationInputError(f"control_probe_stat:{control_path}:{error}") from error
    if response_artifact is None:
        return None, {
            "mode": "eof",
            "exclusive_end_offset": None,
            "file_size": size,
        }
    response_path = _find_response_file(response_artifact)
    response_report = _read_object(response_path, "response_artifact")
    offset = _int(response_report.get("log_start_offset"))
    bound_source = "log_start_offset"
    native_events_meta: dict[str, Any] = {}
    if offset is None:
        # Inbound-response reports bind their copied native-events slice with
        # native_events.start_offset rather than the outbound execution
        # report's top-level log_start_offset.
        candidate = response_report.get("native_events")
        if isinstance(candidate, Mapping):
            offset = _int(candidate.get("start_offset"))
            bound_source = "native_events.start_offset"
            native_events_meta = {
                key: candidate.get(key)
                for key in ("path", "start_offset", "end_offset", "sha256", "complete")
                if key in candidate
            }
    if offset is None or offset < 0 or offset > size:
        raise ValidationInputError(
            f"response_log_start_offset_invalid:{response_path}:{offset}:{size}")
    return offset, {
        "mode": f"response_{bound_source}_exclusive",
        "source": str(response_path),
        "offset_field": bound_source,
        "exclusive_end_offset": offset,
        "file_size": size,
        "native_events": native_events_meta,
    }


def _fresh_default_outputs(observation: Path) -> tuple[Path, Path]:
    base = observation.parent / "royal-pending-lifecycle-validation-001"
    candidate = base
    suffix = 1
    while candidate.exists():
        suffix += 1
        candidate = observation.parent / f"royal-pending-lifecycle-validation-{suffix:03d}"
    candidate.mkdir(parents=True)
    return candidate / "report.json", candidate / "report.md"


def _write_exclusive(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(value)


def _markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    checks = report["checks"]
    offer = report.get("natural_offer") or {}
    offer_event = offer.get("selected") if isinstance(offer, Mapping) else None
    offer_source = offer.get("selected_source") if isinstance(offer, Mapping) else None
    offer_source_text = {
        "observation_slice": "观察切片",
        "control_probe": "控制原日志",
    }.get(offer_source, "日志")
    hold = report.get("hold_evidence") or {}
    forbidden = report.get("forbidden_during_pending") or {}
    advance = report.get("advance_and_pause") or {}
    lines = [
        "# Royal 外来联姻 pending 生命周期验收",
        "",
        f"- 验收状态：**{'通过' if report.get('status') == 'passed' else '失败'}**",
        f"- 必要检查：{summary['passed_checks']}/{summary['total_checks']} 通过",
        f"- 观察目录：`{report['inputs']['observation']}`",
        f"- 控制原日志：`{report['inputs']['control_probe']}`",
        f"- 控制日志边界：`{report['control_log_bound'].get('mode')}`，"
        f"exclusive_end_offset=`{report['control_log_bound'].get('exclusive_end_offset')}`",
        f"- 会话：`{report['session_id']}`",
        "",
        "## 自然来源与 pending 节点",
        "",
    ]
    if isinstance(offer_event, Mapping):
        lines.append(
            f"{offer_source_text}第 `{offer_event.get('line')}` 行记录了 `{offer_event.get('actor')}` → "
            f"`{offer_event.get('recipient')}` 的 `{offer_event.get('action_id')}`，"
            f"proposal_id=`{offer_event.get('proposal_id')}`，date28=`{offer_event.get('date28')}`，"
            f"state34=`{offer_event.get('state34')}`，token3c=`{offer_event.get('token3c')}`。"
        )
    else:
        lines.append("观察切片没有找到满足 PRO → FRA Royal 条件的自然 pending 提议。")
    lines.append(
        f"自然来源候选数：观察切片 `{offer.get('observation_count')}`，"
        f"原始控制日志 `{offer.get('control_count')}`；测试 fixture 事件数 `{offer.get('fixture_event_count')}`。"
    )
    lines.extend(["", "## 跨日 hold 证据", ""])
    lines.append(
        f"匹配 hold 事件 `{hold.get('matched_count')}` 条，"
        f"不同 date_raw `{hold.get('distinct_date_count')}` 个："
        f"`{', '.join(str(x) for x in hold.get('distinct_dates', []))}`。"
    )
    lines.append(
        f"要求至少 `{report['minimum_hold_days']}` 个不同日期；"
        f"native_queue_verified 与 native_ai_choice_skipped 全部为 true："
        f"`{hold.get('all_native_flags_true')}`。"
    )
    lines.extend(["", "## hold 阶段禁止事件", ""])
    lines.append(
        f"匹配 PRO → FRA、state 1/2 command entry `{forbidden.get('command_count')}` 条；"
        f"UNAUTHORIZED_FRA_ROYAL_RESPONSE `{forbidden.get('unauthorized_count')}` 条。"
    )
    lines.extend(["", "## 推进与暂停", ""])
    lines.append(
        f"目标日期 `{advance.get('target_raw')}`，实际日期 `{advance.get('date_raw')}`，"
        f"达到目标 `{advance.get('reached')}`；玩家 `{advance.get('player')}`，暂停 `{advance.get('paused')}`。"
    )
    lines.extend(["", "## 检查结果", "", "| 检查 | 结果 |", "|---|---|"])
    for name, value in checks.items():
        lines.append(f"| `{name}` | {'通过' if value else '失败'} |")
    optional = report.get("response_checks")
    if isinstance(optional, Mapping) and optional.get("supplied"):
        lines.extend(["", "## 可选 response artifact", ""])
        for name, value in (optional.get("checks") or {}).items():
            lines.append(f"| `{name}` | {'通过' if value else '失败'} |")
    failures = summary.get("failed_check_names", [])
    if failures:
        lines.extend(["", "## 失败原因", ""])
        for name in failures:
            lines.append(f"- `{name}` 未满足验收条件。")
    return "\n".join(lines) + "\n"


def validate(installation: Path, observation: Path, response_artifact: Path | None,
             minimum_hold_days: int) -> dict[str, Any]:
    installation = installation.expanduser().resolve()
    observation = observation.expanduser().resolve()
    installation_record = _read_object(installation, "installation")
    observation_report_path = observation / "observation-report.json"
    observation_report = _read_object(observation_report_path, "observation_report")
    observed_path = observation / "observed-events.jsonl"
    control_path = installation.parent / "control-probe.jsonl"
    session_id = installation_record.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValidationInputError("installation_session_id_missing")

    observed = _scan_jsonl(observed_path, session_id)
    control_end_offset, control_bound = _control_log_bound(control_path, response_artifact)
    control = _scan_jsonl(control_path, session_id, control_end_offset)
    observation_sha256, observation_hash_error = _stream_sha256(observed_path)
    offers_observed = [
        (line, event) for line, event in observed.offers
        if _matching_offer(event, session_id)
    ]
    offers_control = [
        (line, event) for line, event in control.offers
        if _matching_offer(event, session_id)
    ]
    # The observation slice is the authoritative source for the detailed
    # native pending payload.  Fall back to the bounded control log if a
    # future slice contains only the progress report but not the offer line.
    offer_line, offer = (
        offers_observed[0] if len(offers_observed) == 1
        else offers_control[0] if len(offers_control) == 1
        else (None, None)
    )
    control_offer_line = offers_control[0][0] if len(offers_control) == 1 else None
    offer_checks = _offer_checks(offer)
    clone_matches: list[tuple[int, dict[str, Any]]] = []
    clone_seen: set[tuple[Any, ...]] = set()
    for line, event in observed.lifecycle_clones + control.lifecycle_clones:
        if (
            offer is None
            or event.get("session_id") != session_id
            or not _clone_matches_offer(event, offer)
        ):
            continue
        source = event.get("source")
        target = event.get("target")
        key = (
            event.get("sequence"),
            source.get("addr") if isinstance(source, Mapping) else None,
            target.get("addr") if isinstance(target, Mapping) else None,
        )
        if key in clone_seen:
            continue
        clone_seen.add(key)
        clone_matches.append((line, event))
    if offer is not None:
        offer_checks["pending_full_family_clone_seen"] = bool(clone_matches)
    else:
        offer_checks["pending_full_family_clone_seen"] = False

    holds = _merge_hold_events(observed, control, offer, session_id)
    hold_dates = sorted({_int(event.get("date_raw")) for _, event in holds
                         if _int(event.get("date_raw")) is not None})
    hold_flags = bool(holds) and all(
        _true(event.get("native_queue_verified"))
        and _true(event.get("native_ai_choice_skipped"))
        for _, event in holds
    )
    forbidden_entries = [
        (line, event) for line, event in control.command_entries
        if control_offer_line is not None and line > control_offer_line
        and event.get("session_id") == session_id
        and event.get("actor_field") == ACTOR
        and event.get("recipient_field") == RECIPIENT
        and _int(event.get("state_raw")) in {1, 2}
        and offer is not None and _command_matches_pending_offer(event, offer)
    ]
    unauthorized = [
        (line, event) for line, event in control.rejected
        if control_offer_line is not None and line > control_offer_line
        and event.get("session_id") == session_id
        and event.get("reason") == "UNAUTHORIZED_FRA_ROYAL_RESPONSE"
    ]
    completion = observation_report.get("completion")
    if not isinstance(completion, Mapping):
        completion = {}
    health = [event for _, event in observed.health
              if event.get("session_id") in (None, session_id)]
    last_health = health[-1] if health else {}
    target_raw = _int(completion.get("target_raw"))
    date_raw = _int(completion.get("date_raw"))
    checks: dict[str, bool] = {
        "installation_and_observation_same_session": (
            observation_report.get("session_id") == session_id
            and all(event.get("session_id") in (None, session_id)
                    for _, event in observed.offers + observed.holds
                    + observed.command_entries + observed.rejected)
        ),
        "observation_log_hash_bound": (
            observation_hash_error is None
            and observation_report.get("events_sha256") == observation_sha256
        ),
        # The observation slice can begin after the natural offer.  A unique
        # exact offer in the bounded original control log is equally valid,
        # provided the slice itself contains no conflicting offer.
        "natural_offer_unique_in_observation": (
            len(offers_observed) == 1
            or (len(offers_observed) == 0 and len(offers_control) == 1)
        ),
        "natural_offer_cross_checked_in_control_log": len(offers_control) == 1,
        "no_test_fixture_submission": (
            not observed.fixture_events and not control.fixture_events
            and observation_report.get("business_submission") is False
            and observation_report.get("own_diplomatic_request") is False
        ),
        "pending_lifecycle_full_family_clone": bool(clone_matches),
        **offer_checks,
        "hold_minimum_distinct_dates": len(hold_dates) >= minimum_hold_days,
        "hold_native_queue_and_ai_skip_flags": hold_flags,
        "hold_events_same_session_proposal_token": (
            bool(holds) and all(event.get("session_id") == session_id for _, event in holds)
        ),
        "no_pro_to_fra_state1_state2_command_entry_during_pending": not forbidden_entries,
        "no_unauthorized_fra_royal_response": not unauthorized,
        "advance_reached_target_date": (
            _true(completion.get("reached"))
            and target_raw is not None and date_raw == target_raw
            and any(event.get("event") == "control_advance_complete"
                    and _true(event.get("reached"))
                    and _int(event.get("date_raw")) == target_raw
                    for _, event in observed.advance_complete)
        ),
        "por_paused_after_advance": (
            _true(observation_report.get("paused_after"))
            and _true(completion.get("paused_command_success"))
            and last_health.get("player") == "POR"
        ),
    }
    response_checks: dict[str, Any] = {
        "supplied": False,
        "checks": {},
    }
    if response_artifact is not None:
        response_checks = _response_checks(_find_response_file(response_artifact), offer, session_id)
        checks.update({f"response_{name}": value
                       for name, value in response_checks.get("checks", {}).items()})

    event_counts = {
        "observation": dict(sorted(observed.event_counts.items())),
        "control_probe": dict(sorted(control.event_counts.items())),
    }
    selected_offer = _public_event(offer_line, offer) if offer_line is not None and offer else None
    report: dict[str, Any] = {
        "report_version": 1,
        "validator": "validate_royal_pending_lifecycle.py",
        "offline_only": True,
        "native_methods_invoked": False,
        "game_started": False,
        "status": "passed" if all(checks.values()) else "failed",
        "installation": str(installation),
        "session_id": session_id,
        "minimum_hold_days": minimum_hold_days,
        "inputs": {
            "observation": str(observation),
            "observation_report": str(observation_report_path),
            "observed_events": str(observed_path),
            "control_probe": str(control_path),
            "response_artifact": str(response_artifact) if response_artifact else None,
        },
        "streaming": {
            "observation": {
                "bytes": observed.bytes, "lines": observed.lines,
                "scanned_bytes": observed.scanned_bytes,
                "parsed": observed.parsed, "malformed_lines": observed.malformed_lines,
                "sha256": observation_sha256, "sha256_error": observation_hash_error,
            },
            "control_probe": {
                "bytes": control.bytes, "lines": control.lines,
                "scanned_bytes": control.scanned_bytes,
                "end_offset": control.end_offset,
                "parsed": control.parsed, "malformed_lines": control.malformed_lines,
            },
        },
        "control_log_bound": control_bound,
        "event_counts": event_counts,
        "natural_offer": {
            "observation_count": len(offers_observed),
            "control_count": len(offers_control),
            "fixture_event_count": len(observed.fixture_events) + len(control.fixture_events),
            "selected_source": (
                "observation_slice" if len(offers_observed) == 1
                else "control_probe" if len(offers_control) == 1 else None
            ),
            "selected": selected_offer,
            "clone_matches": [_public_event(line, event) for line, event in clone_matches[:16]],
        },
        "hold_evidence": {
            "matched_count": len(holds),
            "distinct_dates": hold_dates,
            "distinct_date_count": len(hold_dates),
            "all_native_flags_true": hold_flags,
            "selected": [_public_event(line, event) for line, event in holds[:16]],
        },
        "forbidden_during_pending": {
            "command_count": len(forbidden_entries),
            "command_entries": [_public_event(line, event) for line, event in forbidden_entries[:16]],
            "unauthorized_count": len(unauthorized),
            "unauthorized_entries": [_public_event(line, event) for line, event in unauthorized[:16]],
        },
        "advance_and_pause": {
            "target_raw": target_raw,
            "date_raw": date_raw,
            "reached": _true(completion.get("reached")),
            "paused": _true(observation_report.get("paused_after")),
            "paused_command_success": _true(completion.get("paused_command_success")),
            "player": last_health.get("player"),
            "last_health_date_raw": _int(last_health.get("date_raw")),
        },
        "checks": checks,
        "response_checks": response_checks,
    }
    failed = [name for name, passed in checks.items() if not passed]
    passed_count = len(checks) - len(failed)
    report["summary"] = {
        "validation_passed": not failed,
        "total_checks": len(checks),
        "passed_checks": passed_count,
        "failed_checks": len(failed),
        "failed_check_names": failed,
    }
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", required=True, type=Path,
                        help="runtime installation.json")
    parser.add_argument("--observation", required=True, type=Path,
                        help="lifecycle observation directory")
    parser.add_argument("--response-artifact", type=Path,
                        help="optional response artifact directory or report.json")
    parser.add_argument("--minimum-hold-days", type=int, default=3,
                        help="required distinct hold dates; default: 3")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.minimum_hold_days < 1:
        parser.error("--minimum-hold-days must be >= 1")
    try:
        if args.output_json is None and args.output_md is None:
            json_path, md_path = _fresh_default_outputs(args.observation.expanduser().resolve())
        else:
            json_path = args.output_json or args.output_md.with_suffix(".json")
            md_path = args.output_md or args.output_json.with_suffix(".md")
            if json_path.exists() or md_path.exists():
                raise ValidationInputError("refusing_to_overwrite_output")
        report = validate(args.installation, args.observation, args.response_artifact,
                          args.minimum_hold_days)
        _write_exclusive(json_path, json.dumps(report, ensure_ascii=False, indent=2,
                                               sort_keys=True) + "\n")
        _write_exclusive(md_path, _markdown(report))
    except (InputError, ValidationInputError, OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps({
        "status": report["status"],
        "summary": report["summary"],
        "json": str(json_path),
        "markdown": str(md_path),
    }, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
