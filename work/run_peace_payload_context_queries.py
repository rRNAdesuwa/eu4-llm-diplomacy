"""Run read-only peace payload-context inspections for one paused batch.

The operator discovers the shared FRA--ENG war, then inspects a white-peace
payload and a 10.0-ducat payload through the unified query interface.  It
checks the public native-war-context projection, including both participant
tag lists, without assigning either side an attacker/defender role.  The
attacker/defender arrays from the R37 save are kept as an independent fixture
comparison only; they are not used as a native role proof.

No offer is submitted, time is advanced, and no save is written.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from work.local_config import game_exe
from work.observer_runtime_ready import wait_runtime_ready
from work.run_alliance_execution import _copy_log_slice, _write_json
from work.run_improve_relations_execution import _new_artifact
from work.run_peace_money_offer_queries import _money_parameters
from work.run_royal_marriage_execution import (
    _installation_binding, _public_probe_records, _snapshots_complete,
)
from work.validate_alliance_reload import _control_summary, _run_snapshots
import work.run_peace_factor_identifiers as factor_operator


WAR_ACTOR = "FRA"
WAR_RECIPIENT = "ENG"
MONEY_AMOUNT = "10.0"
MONEY_ACTION = "demand_ducats"
TAG_RE = re.compile(r"[A-Z]{3}\Z")
PAYLOAD_EVENT = "native_peace_payload_term_private"
PAYLOAD_SCHEMA = "native_peace_serialized_fields_v1"
GOLD_TYPE_ID = 0x2D2B
PAYLOAD_LOGICAL_FIELDS = (
    "type_id", "bucket", "field10", "field18", "field22", "extra30",
    "nested_present", "nested_id", "gold_raw", "flag40",
    "definition_name_size", "definition_name_hex", "selected",
    "selected_index", "complete",
)

# These are the two participant sets recorded by the independent R37 save
# comparison.  Their only use here is a bounded, role-neutral set comparison.
R37_ATTACKERS = frozenset(("FRA", "AMG", "AUV", "BOU", "FOI", "ORL"))
R37_DEFENDERS = frozenset(("ENG", "TYR", "SWE", "UTR"))
R37_SAVE_REFERENCE = (
    "work/runtime/r37-declarewar-save-pair-20261016-002/report.json"
)


def _integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _native_war_context(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    context = value.get("native_war_context")
    return context if isinstance(context, dict) else None


def _native_war_context_contract(
        value: object, actor: str = WAR_ACTOR,
        recipient: str = WAR_RECIPIENT) -> bool:
    """Validate the public participant projection without inferring roles."""

    context = _native_war_context(value)
    if context is None:
        return False
    if context.get("war_context_resolved") is not True:
        return False
    side_a = context.get("side_a_members")
    side_b = context.get("side_b_members")
    if (not isinstance(side_a, list) or not isinstance(side_b, list)
            or not _integer(context.get("side_a_count"))
            or not _integer(context.get("side_b_count"))
            or context.get("side_a_count") != len(side_a)
            or context.get("side_b_count") != len(side_b)
            or not side_a or not side_b):
        return False
    if any(not isinstance(tag, str) or TAG_RE.fullmatch(tag) is None
           for tag in side_a + side_b):
        return False
    if (len(side_a) != len(set(side_a))
            or len(side_b) != len(set(side_b))
            or set(side_a).intersection(side_b)):
        return False
    if context.get("participant_lists_complete") is not True:
        return False
    if ("members_capture_complete" in context
            and context.get("members_capture_complete") is not True):
        return False
    actor_side = context.get("actor_side")
    recipient_side = context.get("recipient_side")
    selected_side = context.get("selected_side")
    if (actor_side not in ("side_a", "side_b")
            or recipient_side not in ("side_a", "side_b")
            or selected_side not in ("side_a", "side_b")
            or actor_side == recipient_side
            or selected_side != actor_side):
        return False
    if context.get("actor_side_verified") is not True:
        return False
    if context.get("recipient_side_verified") is not True:
        return False
    if context.get("actor_recipient_opposite") is not True:
        return False
    members_for_actor = side_a if actor_side == "side_a" else side_b
    members_for_recipient = side_a if recipient_side == "side_a" else side_b
    if actor not in members_for_actor or recipient not in members_for_recipient:
        return False
    if context.get("offer_identity_verified") is not True:
        return False
    if context.get("offer_vectors_readable") is not True:
        return False
    if context.get("primary_offer_mapping_verified") is not True:
        return False
    for field in (
            "derived_offer_mapping_verified",
            "offer_vector_mapping_verified",
            "roles_verified", "leaders_verified", "context_complete"):
        if not isinstance(context.get(field), bool):
            return False
    if context.get("roles_verified") is not False:
        return False
    if context.get("leaders_verified") is not False:
        return False
    if context.get("context_complete") is not False:
        return False
    return True


def _context_signature(value: object) -> tuple[Any, ...] | None:
    context = _native_war_context(value)
    if context is None:
        return None
    side_a = context.get("side_a_members")
    side_b = context.get("side_b_members")
    if not isinstance(side_a, list) or not isinstance(side_b, list):
        return None
    return (
        frozenset(side_a), frozenset(side_b),
        context.get("actor_side"), context.get("recipient_side"),
        context.get("selected_side"),
    )


def _independent_save_side_comparison(value: object) -> dict[str, object]:
    """Compare sets with R37 while keeping role inference explicitly disabled."""

    context = _native_war_context(value)
    side_a = context.get("side_a_members") if context else None
    side_b = context.get("side_b_members") if context else None
    observed_a = sorted(side_a) if isinstance(side_a, list) else []
    observed_b = sorted(side_b) if isinstance(side_b, list) else []
    observed_sets = {frozenset(observed_a), frozenset(observed_b)}
    expected_sets = {R37_ATTACKERS, R37_DEFENDERS}
    return {
        "reference": R37_SAVE_REFERENCE,
        "reference_attacker_tags": sorted(R37_ATTACKERS),
        "reference_defender_tags": sorted(R37_DEFENDERS),
        "observed_side_a": observed_a,
        "observed_side_b": observed_b,
        "participant_sets_match_reference": observed_sets == expected_sets,
        "role_inference_performed": False,
        "save_side_comparison_is_not_native_role_proof": True,
    }


def _private_context_events(path: Path, expected_session_id: object) -> list[dict[str, object]]:
    """Index bounded private context events without copying native addresses."""

    records: list[dict[str, object]] = []
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except (TypeError, ValueError, UnicodeDecodeError):
                    continue
                if (not isinstance(event, dict)
                        or event.get("event") != "native_peace_war_context_private"
                        or event.get("private") is not True):
                    continue
                session_id = event.get("session_id")
                query_id = event.get("query_id")
                raw_context = event.get("native_war_context")
                if (not isinstance(session_id, str) or not session_id
                        or not isinstance(query_id, str) or not query_id
                        or not isinstance(raw_context, str)
                        or not raw_context.startswith("0x")):
                    continue
                records.append({
                    "event": event["event"],
                    "private": True,
                    "session_id": session_id,
                    "session_matches": session_id == expected_session_id,
                    "query_id": query_id,
                    "native_war_context_present": raw_context != "0x0",
                    "side_a_count": event.get("side_a_count"),
                    "side_b_count": event.get("side_b_count"),
                    "members_capture_complete": event.get(
                        "members_capture_complete"),
                })
    except OSError:
        return []
    return records


def _private_context_contract(
        records: object, expected_session_id: object) -> bool:
    if not isinstance(records, list) or len(records) < 2:
        return False
    query_ids: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            return False
        if (record.get("session_matches") is not True
                or record.get("native_war_context_present") is not True
                or record.get("members_capture_complete") is not True):
            return False
        query_id = record.get("query_id")
        if not isinstance(query_id, str) or query_id in query_ids:
            return False
        query_ids.add(query_id)
    return True


def _native_payload(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    payload = value.get("native_payload")
    return payload if isinstance(payload, dict) else None


def _native_payload_summary_contract(value: object, kind: str) -> bool:
    """Validate the public serialized-field summary without hiding partial data."""

    payload = _native_payload(value)
    if payload is None or payload.get("schema") != PAYLOAD_SCHEMA:
        return False
    if payload.get("authority_bound") is not False:
        return False
    for field in (
            "capture_available", "serialized_fields_complete",
            "source_owner_verified", "action_owner_verified",
            "selected_index_complete"):
        if not isinstance(payload.get(field), bool):
            return False
    counts = (
        payload.get("term_count"), payload.get("selected_term_count"),
        payload.get("unsupported_term_count"),
    )
    if any(not _integer(count) or count < 0 or count > 512 for count in counts):
        return False
    term_count, selected_count, unsupported_count = counts
    if selected_count > term_count or unsupported_count > term_count:
        return False
    if (payload.get("capture_available") is not True
            or payload.get("source_owner_verified") is not True
            or payload.get("action_owner_verified") is not True):
        return False
    complete = payload.get("serialized_fields_complete")
    source_equal = payload.get("source_copy_equal")
    unchanged = payload.get("serialized_fields_unchanged")
    if complete:
        if (unsupported_count != 0
                or payload.get("selected_index_complete") is not True
                or source_equal is not True or unchanged is not True):
            return False
    elif source_equal is not None or unchanged is not None:
        # A partial native capture is observable, but equality is deliberately
        # unavailable instead of being inferred from the readable fields.
        return False
    if kind == "white":
        return selected_count == 1 and term_count > 0
    if kind == "money":
        return term_count > 0 and selected_count == 1
    return False


def _payload_term_record(event: dict[str, object], expected_session_id: object
                         ) -> dict[str, object] | None:
    """Keep only bounded private term fields needed for source/action checks."""

    session_id = event.get("session_id")
    query_id = event.get("query_id")
    stage = event.get("stage")
    index = event.get("index")
    vtable = event.get("vtable_rva")
    if (not isinstance(session_id, str) or not session_id
            or not isinstance(query_id, str) or not query_id
            or stage not in ("source", "action")
            or not _integer(index) or index < 0 or index > 512
            or not isinstance(vtable, str) or not vtable.startswith("0x")):
        return None
    record: dict[str, object] = {
        "query_id": query_id,
        "session_id": session_id,
        "session_matches": session_id == expected_session_id,
        "stage": stage,
        "index": index,
        "vtable_rva": vtable,
    }
    for field in ("type_id", "bucket", "nested_id", "gold_raw", "flag40",
                  "definition_name_size",
                  "selected", "selected_index"):
        value = event.get(field)
        if not _integer(value):
            return None
        record[field] = value
    encoded_name = event.get("definition_name_hex")
    if (not isinstance(encoded_name, str) or len(encoded_name) > 256
            or re.fullmatch(r"[0-9a-f]*", encoded_name) is None
            or len(encoded_name) != 2 * record["definition_name_size"]):
        return None
    record["definition_name_hex"] = encoded_name
    for field in ("field10", "field18", "field22", "extra30"):
        value = event.get(field)
        if not isinstance(value, str) or not value.startswith("0x"):
            return None
        record[field] = value
    for field in ("nested_present", "complete"):
        value = event.get(field)
        if not isinstance(value, bool):
            return None
        record[field] = value
    # The native unsupported-descriptor path leaves type_id at zero and the
    # term incomplete, while retaining the actual vtable RVA for diagnosis.
    record["unknown_vtable"] = record["type_id"] == 0 and not record["complete"]
    return record


def _read_payload_term_groups(
        path: Path, expected_session_id: object
        ) -> dict[str, dict[str, list[dict[str, object]]]]:
    """Group bounded source/action term events by their native query id."""

    grouped: dict[str, dict[str, list[dict[str, object]]]] = {}
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except (TypeError, ValueError, UnicodeDecodeError):
                    continue
                if (not isinstance(event, dict)
                        or event.get("event") != PAYLOAD_EVENT
                        or event.get("private") is not True):
                    continue
                record = _payload_term_record(event, expected_session_id)
                if record is None:
                    continue
                query_id = record["query_id"]
                stage = record["stage"]
                group = grouped.setdefault(query_id, {"source": [], "action": []})
                group[stage].append(record)
    except OSError:
        return {}
    return grouped


def _resolve_payload_query_ids(
        path: Path, expected_session_id: object, war_id: object
        ) -> dict[str, list[str]]:
    """Resolve public inspection IDs from the bounded native event slice.

    The public bridge intentionally omits ``query_id``.  This resolver keeps
    that identifier in the private report only and binds it using the native
    event's session, country pair, and selected war.
    """

    found: dict[str, set[str]] = {"white": set(), "money": set()}
    event_kinds = {
        "native_peace_empty_offer_inspection": "white",
        "native_peace_money_offer_inspection": "money",
    }
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except (TypeError, ValueError, UnicodeDecodeError):
                    continue
                if not isinstance(event, dict):
                    continue
                kind = event_kinds.get(event.get("event"))
                if (kind is None or event.get("session_id") != expected_session_id
                        or event.get("actor") != WAR_ACTOR
                        or event.get("recipient") != WAR_RECIPIENT
                        or event.get("war_id") != war_id):
                    continue
                query_id = event.get("query_id")
                if isinstance(query_id, str) and query_id:
                    found[kind].add(query_id)
    except OSError:
        return {"white": [], "money": []}
    return {kind: sorted(query_ids) for kind, query_ids in found.items()}


def _bind_private_query_id(value: object, query_id: object) -> dict[str, object]:
    """Make a private validation copy without mutating public query data."""

    bound = dict(value) if isinstance(value, dict) else {}
    bound["query_id"] = query_id
    return bound


def _payload_logical_signature(record: dict[str, object]) -> tuple[object, ...]:
    return tuple(record.get(field) for field in PAYLOAD_LOGICAL_FIELDS)


def _payload_term_observation(
        groups: dict[str, dict[str, list[dict[str, object]]]],
        value: object, kind: str) -> dict[str, object]:
    """Validate stage/index continuity and the selected Gold term."""

    payload = _native_payload(value)
    query_id = value.get("query_id") if isinstance(value, dict) else None
    group = groups.get(query_id) if isinstance(query_id, str) else None
    source = list(group.get("source", [])) if group else []
    action = list(group.get("action", [])) if group else []
    term_count = payload.get("term_count") if payload else None

    def stage_indices(records: list[dict[str, object]]) -> bool:
        indices = [record.get("index") for record in records]
        return (len(indices) == len(set(indices))
                and sorted(indices) == list(range(term_count))
                if _integer(term_count) else False)

    source_indices_complete = stage_indices(source)
    action_indices_complete = stage_indices(action)
    source_by_index = {
        record["index"]: record for record in source
        if _integer(record.get("index"))
    }
    action_by_index = {
        record["index"]: record for record in action
        if _integer(record.get("index"))
    }
    common_indices = sorted(set(source_by_index).intersection(action_by_index))
    logical_equal = (
        source_indices_complete and action_indices_complete
        and len(source) == len(action)
        and all(_payload_logical_signature(source_by_index[index])
                == _payload_logical_signature(action_by_index[index])
                for index in common_indices)
        and len(common_indices) == len(source))
    unknown_vtables = [
        {
            "stage": record["stage"], "index": record["index"],
            "vtable_rva": record["vtable_rva"],
        }
        for record in source + action if record.get("unknown_vtable") is True
    ]
    gold_source = [
        record for record in source
        if record.get("type_id") == GOLD_TYPE_ID
        and record.get("bucket") == 0 and record.get("gold_raw") == 10000
        and record.get("selected") == 1 and record.get("selected_index") == 0
    ]
    gold_action = [
        record for record in action
        if record.get("type_id") == GOLD_TYPE_ID
        and record.get("bucket") == 0 and record.get("gold_raw") == 10000
        and record.get("selected") == 1 and record.get("selected_index") == 0
    ]
    gold_verified = (
        kind == "money" and len(gold_source) == 1 and len(gold_action) == 1
        and _payload_logical_signature(gold_source[0])
            == _payload_logical_signature(gold_action[0]))
    white_gold_source = [
        record for record in source
        if record.get("type_id") == GOLD_TYPE_ID
        and record.get("bucket") == 0 and record.get("gold_raw") == 0
        and record.get("selected") == 1 and record.get("selected_index") == 0
    ]
    white_gold_action = [
        record for record in action
        if record.get("type_id") == GOLD_TYPE_ID
        and record.get("bucket") == 0 and record.get("gold_raw") == 0
        and record.get("selected") == 1 and record.get("selected_index") == 0
    ]
    white_gold_verified = (
        kind == "white" and len(white_gold_source) == 1
        and len(white_gold_action) == 1
        and _payload_logical_signature(white_gold_source[0])
            == _payload_logical_signature(white_gold_action[0]))
    unselected_gold_source = [
        record for record in source
        if record.get("type_id") == GOLD_TYPE_ID
        and record.get("bucket") == 0 and record.get("gold_raw") == 0
        and record.get("selected") == 0
    ]
    unselected_gold_action = [
        record for record in action
        if record.get("type_id") == GOLD_TYPE_ID
        and record.get("bucket") == 0 and record.get("gold_raw") == 0
        and record.get("selected") == 0
    ]
    unselected_gold_verified = (
        kind == "white" and len(unselected_gold_source) >= 1
        and len(unselected_gold_action) >= 1
        and any(_payload_logical_signature(source_record)
                == _payload_logical_signature(action_record)
                for source_record in unselected_gold_source
                for action_record in unselected_gold_action))
    if kind == "white":
        contract = (
            isinstance(payload, dict)
            and _integer(term_count)
            and len(source) == term_count and len(action) == term_count
            and source_indices_complete and action_indices_complete
            and logical_equal
            and white_gold_verified
            and sum(record.get("selected") == 1 for record in source) == 1
            and sum(record.get("selected") == 1 for record in action) == 1)
    else:
        contract = (
            isinstance(payload, dict)
            and _integer(term_count) and term_count > 0
            and len(source) == term_count and len(action) == term_count
            and source_indices_complete and action_indices_complete
            and logical_equal and gold_verified)
    return {
        "query_id": query_id,
        "kind": kind,
        "source_count": len(source),
        "action_count": len(action),
        "source_indices_complete": source_indices_complete,
        "action_indices_complete": action_indices_complete,
        "source_action_logical_fields_equal": logical_equal,
        "gold_term_verified": gold_verified,
        "selected_white_gold_verified": white_gold_verified,
        "unselected_gold_verified": unselected_gold_verified,
        "other_unselected_count": sum(
            1 for record in source
            if record.get("selected") == 0
            and not (record.get("type_id") == GOLD_TYPE_ID
                     and record.get("bucket") == 0
                     and record.get("gold_raw") == 0)),
        "unknown_vtables": unknown_vtables,
        "source_records": source,
        "action_records": action,
        "contract": contract,
    }


def _offline_contract_assertions() -> None:
    """Exercise the public contract without opening a game session."""

    context = {
        "war_context_resolved": True,
        "side_a_count": 2,
        "side_b_count": 2,
        "side_a_members": ["FRA", "AMG"],
        "side_b_members": ["ENG", "TYR"],
        "participant_lists_complete": True,
        "members_capture_complete": True,
        "actor_side": "side_a",
        "recipient_side": "side_b",
        "selected_side": "side_a",
        "actor_side_verified": True,
        "recipient_side_verified": True,
        "actor_recipient_opposite": True,
        "offer_identity_verified": True,
        "offer_vectors_readable": True,
        "primary_offer_mapping_verified": True,
        "derived_offer_mapping_verified": False,
        "offer_vector_mapping_verified": False,
        "roles_verified": False,
        "leaders_verified": False,
        "context_complete": False,
    }
    value = {"native_war_context": context}
    if not _native_war_context_contract(value):
        raise AssertionError("valid native_war_context fixture rejected")
    invalid = dict(context)
    invalid["side_b_members"] = ["ENG", "FRA"]
    if _native_war_context_contract({"native_war_context": invalid}):
        raise AssertionError("overlapping participant fixture accepted")
    white_payload = {
        "schema": PAYLOAD_SCHEMA,
        "capture_available": True,
        "serialized_fields_complete": True,
        "source_copy_equal": True,
        "serialized_fields_unchanged": True,
        "source_owner_verified": True,
        "action_owner_verified": True,
        "term_count": 2,
        "selected_term_count": 1,
        "unsupported_term_count": 0,
        "selected_index_complete": True,
        "authority_bound": False,
    }
    if not _native_payload_summary_contract(
            {"native_payload": white_payload}, "white"):
        raise AssertionError("valid unselected-candidate payload fixture rejected")
    def white_term(index: int, type_id: int, bucket: int,
                   field10: str, field18: str) -> dict[str, object]:
        return {
            "query_id": "q_white", "session_id": "test-session",
            "session_matches": True, "stage": "source", "index": index,
            "vtable_rva": "0x1c7b000", "type_id": type_id,
            "bucket": bucket, "field10": field10, "field18": field18,
            "field22": "0x0", "extra30": "0x0", "nested_present": False,
            "nested_id": 0, "gold_raw": 0, "flag40": 0,
            "definition_name_size": 0, "definition_name_hex": "", "selected": 0,
            "selected_index": 0xffffffff, "complete": True,
            "unknown_vtable": False,
        }
    gold_source = white_term(0, GOLD_TYPE_ID, 0, "0x11", "0x22")
    other_source = white_term(1, 0x1234, 1, "0x33", "0x44")
    gold_source["selected"] = 1
    gold_source["selected_index"] = 0
    gold_action = dict(gold_source, stage="action")
    other_action = dict(other_source, stage="action")
    white_groups = {
        "q_white": {"source": [gold_source, other_source],
                    "action": [gold_action, other_action]},
    }
    white_observation = _payload_term_observation(
        white_groups, {"query_id": "q_white", "native_payload": white_payload},
        "white")
    if (white_observation["contract"] is not True
            or white_observation["selected_white_gold_verified"] is not True
            or white_observation["other_unselected_count"] != 1):
        raise AssertionError("default white-peace selection was not validated")
    partial_payload = dict(white_payload)
    partial_payload.update({
        "serialized_fields_complete": False,
        "source_copy_equal": None,
        "serialized_fields_unchanged": None,
        "term_count": 1,
        "selected_term_count": 1,
        "unsupported_term_count": 1,
        "selected_index_complete": False,
    })
    partial_value = {"query_id": "q_partial",
                     "native_payload": partial_payload}
    if not _native_payload_summary_contract(partial_value, "money"):
        raise AssertionError("valid partial payload summary rejected")
    if _payload_term_observation({}, partial_value, "money")["contract"]:
        raise AssertionError("partial payload accepted without term evidence")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--expected-date-raw", type=int, required=True)
    args = parser.parse_args()
    _offline_contract_assertions()
    installation = args.installation.resolve(strict=True)
    session = ObserverSession(installation, game_exe())
    artifact = _new_artifact(installation.parent, "peace-payload-context")
    report: dict[str, object] = {
        "validator": Path(__file__).name,
        "artifact": str(artifact),
        "installation": str(installation),
        "status": "running",
        "action_id": MONEY_ACTION,
        "phase": "initiate",
        "actor": WAR_ACTOR,
        "recipient": WAR_RECIPIENT,
        "expected_date_raw": args.expected_date_raw,
        "reference_save": R37_SAVE_REFERENCE,
        "execute_call_count": 0,
        "business_submission": False,
        "time_advance_call_count": 0,
        "save_call_count": 0,
        "query_call_count": 0,
        "queries": {},
    }
    log = session.directory / "control-probe.jsonl"
    log_start: int | None = None
    before: dict[str, object] | None = None
    after: dict[str, object] | None = None
    control_before: object = None
    control_after: object = None
    discovery: dict[str, object] | None = None
    selected_white: dict[str, object] | None = None
    selected_money: dict[str, object] | None = None
    war_id: str | None = None
    try:
        health = wait_runtime_ready(session, restore_minimized=True)
        if health.get("status") != "ready":
            raise RuntimeError("PEACE_PAYLOAD_CONTEXT_SESSION_UNREADY")
        report.update(_installation_binding(installation))
        report["session"] = {
            key: session.record.get(key)
            for key in ("pid", "session_id", "experiment_id", "dll_sha256")
        }
        before = _run_snapshots(session, artifact / "before" / "probes")
        control_before = _control_summary(before["control_state"]["snapshot"])
        report["before"] = {
            "control": control_before,
            "health": session.health(),
            "probes": _public_probe_records(before),
        }
        if (not factor_operator._control_is_expected(
                control_before, args.expected_date_raw)
                or not _snapshots_complete(before)):
            raise RuntimeError("PEACE_PAYLOAD_CONTEXT_BASELINE_UNAVAILABLE")
        log_start = log.stat().st_size

        with DurableJournal(artifact / "diplomacy.sqlite3",
                            session.experiment_id, session.session_id) as journal:
            api = DiplomacyTools(journal, session)
            report["query_call_count"] += 1
            discovery = api.inspect_diplomatic_action(
                "white_peace", WAR_ACTOR, WAR_RECIPIENT,
                phase="initiate", parameters={})
            report["queries"]["discovery_white_peace"] = discovery
            _write_json(artifact / "discovery-white-peace.json", discovery)
            war_id = factor_operator._single_discovered_war_id(
                discovery, WAR_ACTOR, WAR_RECIPIENT)
            if war_id is None:
                raise RuntimeError("PEACE_PAYLOAD_CONTEXT_DISCOVERY_INCOMPLETE")
            report["war_id"] = war_id

            white_parameters = {
                "peace_context": {"war_id": war_id, "terms": []},
            }
            report["query_call_count"] += 1
            selected_white = api.inspect_diplomatic_action(
                "white_peace", WAR_ACTOR, WAR_RECIPIENT,
                phase="initiate", parameters=white_parameters)
            report["queries"]["selected_white_peace"] = selected_white
            _write_json(artifact / "selected-white-peace.json", selected_white)

            money_parameters = _money_parameters(war_id, MONEY_AMOUNT)
            report["query_call_count"] += 1
            selected_money = api.inspect_diplomatic_action(
                MONEY_ACTION, WAR_ACTOR, WAR_RECIPIENT,
                phase="initiate", parameters=money_parameters)
            report["queries"]["selected_money_10_0"] = selected_money
            _write_json(artifact / "selected-money-10-0.json", selected_money)

        after = _run_snapshots(session, artifact / "after" / "probes")
        control_after = _control_summary(after["control_state"]["snapshot"])
        health_after = session.health()
        report["after"] = {
            "control": control_after,
            "health": health_after,
            "probes": _public_probe_records(after),
        }
        context_comparisons = {
            "selected_white": _independent_save_side_comparison(
                selected_white),
            "selected_money": _independent_save_side_comparison(
                selected_money),
        }
        report["independent_save_side_comparison"] = context_comparisons
        report["context_observations"] = {
            "selected_white": _native_war_context(selected_white),
            "selected_money": _native_war_context(selected_money),
        }
        report["payload_observations"] = {
            "selected_white": _native_payload(selected_white),
            "selected_money": _native_payload(selected_money),
        }
        report["checks"] = {
            "discovery_public_contract": factor_operator._public_context_contract(
                discovery, WAR_ACTOR, WAR_RECIPIENT),
            "discovery_one_war": factor_operator._single_discovered_war_id(
                discovery, WAR_ACTOR, WAR_RECIPIENT) == war_id,
            "selected_white_contract": factor_operator._public_empty_offer_contract(
                selected_white, WAR_ACTOR, WAR_RECIPIENT, war_id),
            "selected_money_contract": factor_operator._native_money_contract(
                selected_money, MONEY_AMOUNT, True),
            "selected_white_factor_contract": factor_operator._factor_projection_contract(
                selected_white, 5, -45, 0),
            "selected_money_factor_contract": factor_operator._factor_projection_contract(
                selected_money, 8, -100, 1),
            "selected_white_payload_summary_contract": (
                _native_payload_summary_contract(selected_white, "white")),
            "selected_money_payload_summary_contract": (
                _native_payload_summary_contract(selected_money, "money")),
            "selected_white_war_context_contract": _native_war_context_contract(
                selected_white, WAR_ACTOR, WAR_RECIPIENT),
            "selected_money_war_context_contract": _native_war_context_contract(
                selected_money, WAR_ACTOR, WAR_RECIPIENT),
            "same_selected_war": all(
                isinstance(value, dict)
                and value.get("selected_war_id") == war_id
                for value in (selected_white, selected_money)),
            "same_participant_context": (
                _context_signature(selected_white) is not None
                and _context_signature(selected_white)
                    == _context_signature(selected_money)),
            "independent_save_side_comparison": all(
                comparison["participant_sets_match_reference"] is True
                for comparison in context_comparisons.values()),
            "save_comparison_role_neutral": all(
                comparison["role_inference_performed"] is False
                and comparison["save_side_comparison_is_not_native_role_proof"]
                is True for comparison in context_comparisons.values()),
            "public_queries_have_no_private_fields": not factor_operator._has_private_fields(
                report["queries"]),
            "control_unchanged": control_before == control_after,
            "health_ready_after": health_after.get("status") == "ready",
            "four_snapshots_complete": (
                _snapshots_complete(before) and _snapshots_complete(after)),
            "independent_war_state_unchanged": (
                before["war_state"]["snapshot"].get("countries")
                == after["war_state"]["snapshot"].get("countries")),
            "no_business_submission": (
                report["execute_call_count"] == 0
                and report["business_submission"] is False
                and report["time_advance_call_count"] == 0
                and report["save_call_count"] == 0),
        }
    except Exception as error:
        report["error"] = {"type": type(error).__name__,
                            "message": str(error)}
    finally:
        if isinstance(log_start, int):
            native_events = _copy_log_slice(
                log, log_start, artifact / "native-events-slice.jsonl")
            report["native_events"] = native_events
            if native_events.get("status") == "ok":
                private_events = _private_context_events(
                    artifact / "native-events-slice.jsonl",
                    session.record.get("session_id"))
                report["private_context_events"] = private_events
                payload_groups = _read_payload_term_groups(
                    artifact / "native-events-slice.jsonl",
                    session.record.get("session_id"))
                report["private_payload_term_groups"] = payload_groups
                payload_query_ids = _resolve_payload_query_ids(
                    artifact / "native-events-slice.jsonl",
                    session.record.get("session_id"), war_id)
                report["payload_query_ids"] = payload_query_ids
                white_ids = payload_query_ids.get("white", [])
                money_ids = payload_query_ids.get("money", [])
                query_ids_complete = (
                    len(white_ids) == 1 and len(money_ids) == 1
                    and white_ids[0] != money_ids[0])
                if "checks" in report:
                    report["checks"]["private_context_contract"] = (
                        _private_context_contract(
                            private_events, session.record.get("session_id")))
                    bound_white = _bind_private_query_id(
                        selected_white, white_ids[0]) if len(white_ids) == 1 else selected_white
                    bound_money = _bind_private_query_id(
                        selected_money, money_ids[0]) if len(money_ids) == 1 else selected_money
                    white_terms = _payload_term_observation(
                        payload_groups, bound_white, "white")
                    money_terms = _payload_term_observation(
                        payload_groups, bound_money, "money")
                    report["payload_term_observations"] = {
                        "selected_white": white_terms,
                        "selected_money": money_terms,
                    }
                    report["checks"]["payload_query_id_resolution_contract"] = (
                        query_ids_complete)
                    report["checks"]["selected_white_payload_terms_contract"] = (
                        white_terms["contract"] is True)
                    report["checks"]["selected_money_payload_terms_contract"] = (
                        money_terms["contract"] is True)
            elif "checks" in report:
                report["payload_query_ids"] = {"white": [], "money": []}
                report["checks"]["payload_query_id_resolution_contract"] = False
                report["checks"]["private_context_contract"] = False
                report["checks"]["selected_white_payload_terms_contract"] = False
                report["checks"]["selected_money_payload_terms_contract"] = False
        checks = report.get("checks")
        report["status"] = (
            "passed" if not report.get("error") and isinstance(checks, dict)
            and all(checks.values()) else "failed")
        _write_json(artifact / "report.json", report)
    print(json.dumps({"status": report["status"], "artifact": str(artifact)},
                     ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
