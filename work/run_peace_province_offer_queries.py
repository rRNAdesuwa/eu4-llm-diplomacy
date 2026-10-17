"""Run read-only cede-province query inspections for one paused batch.

The operator discovers the shared FRA--ENG war, enumerates the native
province candidates, and then queries a one-province selection, a two-province
selection when two candidates exist, and an explicit missing-province
selection.  Empty province-ID input is rejected locally.  It never submits a
peace offer, advances time, saves the game, or treats a missing native-province
contract as a successful legality result.

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
from work.run_peace_empty_offer_queries import (
    _has_private_fields, _public_context_contract, _single_discovered_war_id,
)
from work.run_royal_marriage_execution import (
    _installation_binding, _public_probe_records, _snapshots_complete,
)
from work.validate_alliance_reload import _control_summary, _run_snapshots


WAR_ACTOR = "FRA"
WAR_RECIPIENT = "ENG"
PROVINCE_ACTION = "cede_province"
BENEFICIARY = WAR_ACTOR
PREFERRED_PROVINCE_ID = 177
MISSING_PROVINCE_ID = 2147483647
MAX_SELECTED_PROVINCES = 16
TAG_RE = re.compile(r"[A-Z0-9]{3}\Z")
HEX_RE = re.compile(r"[0-9a-fA-F]*\Z")

# Native event names are not part of the public query contract.  The resolver
# accepts the known naming forms and also requires the province action so a
# generic war-context event cannot be mistaken for a selected offer.
_PROVINCE_INSPECTION_EVENTS = frozenset({
    "native_peace_province_offer_inspection",
})
_PROVINCE_PRIVATE_EVENT = "native_peace_province_candidate_private"


def _integer(value: object, *, minimum: int | None = None) -> bool:
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return minimum is None or value >= minimum


def _province_parameters(
        war_id: str, province_ids: list[int] | tuple[int, ...] | None,
        *, beneficiary: str = BENEFICIARY) -> dict[str, object]:
    """Build the public peace-context shape used by the unified query API.

    ``None`` means candidate enumeration and therefore has no cede-province
    term.  An empty list is different: it is an explicit cede-province term
    with no candidate ID and is retained as its own negative/unknown check.
    """

    context: dict[str, object] = {"war_id": war_id, "direction": "demand"}
    if province_ids is None:
        context["terms"] = []
    else:
        context["terms"] = [{
            "action_id": PROVINCE_ACTION,
            "province_ids": list(province_ids),
            "beneficiary": beneficiary,
        }]
    return {"peace_context": context}


def _public_province_query_contract(
        value: object, expected_parameters: object | None = None) -> bool:
    """Validate stable public envelope fields without assuming native rules."""

    if not isinstance(value, dict):
        return False
    if any(value.get(key) != wanted for key, wanted in (
            ("action_id", PROVINCE_ACTION), ("actor", WAR_ACTOR),
            ("recipient", WAR_RECIPIENT), ("phase", "initiate"),
            ("family", "peace"))):
        return False
    parameters = value.get("parameters")
    if not isinstance(parameters, dict):
        return False
    requested = parameters.get("requested")
    if not isinstance(requested, dict):
        return False
    context = requested.get("peace_context")
    if not isinstance(context, dict) or not isinstance(context.get("war_id"), str):
        return False
    if expected_parameters is not None and requested != expected_parameters:
        return False
    actual = parameters.get("actual")
    if actual is not None and not isinstance(actual, dict):
        return False
    return True


def _candidate_id(value: object) -> int | None:
    if _integer(value, minimum=1):
        return int(value)
    return None


def _append_candidate_id(output: list[int], value: object) -> None:
    candidate = _candidate_id(value)
    if candidate is not None and candidate not in output:
        output.append(candidate)


def _candidate_ids_from_sequence(value: object, output: list[int]) -> None:
    if not isinstance(value, list):
        return
    for item in value:
        if isinstance(item, dict):
            for key in (
                    "province_id", "target_province_id", "id",
                    "candidate_province_id"):
                if key in item:
                    _append_candidate_id(output, item.get(key))
                    break
        else:
            _append_candidate_id(output, item)


def _province_candidate_ids(value: object) -> list[int] | None:
    """Extract candidate IDs from known container shapes, if native data exists.

    Returning ``None`` means the native/API contract has not supplied a
    candidate projection.  An empty list is a valid completed enumeration with
    no candidates and is kept distinct from ``None``.
    """

    if not isinstance(value, dict):
        return None
    native = value.get("native_provinces")
    if not isinstance(native, dict):
        return None
    output: list[int] = []
    # The final public contract uses ``candidates``.  Keep the older aliases
    # only for offline compatibility with pre-contract artifacts.
    for key in (
            "candidates", "candidate_ids", "available_province_ids",
            "province_ids", "available"):
        _candidate_ids_from_sequence(native.get(key), output)
    return output


def _selection_plan(candidate_ids: object) -> dict[str, object]:
    """Choose the requested one/two-province forms without inventing IDs."""

    if not isinstance(candidate_ids, list):
        return {
            "candidate_ids_known": False,
            "candidate_ids": None,
            "preferred_present": None,
            "single_ids": None,
            "pair_ids": None,
            "missing_ids": [MISSING_PROVINCE_ID],
            "empty_ids_rejected_locally": True,
            "selection_plan_complete": None,
        }
    bounded = [item for item in candidate_ids
               if _candidate_id(item) is not None][:MAX_SELECTED_PROVINCES]
    if not bounded:
        return {
            "candidate_ids_known": True,
            "candidate_ids": [],
            "preferred_present": False,
            "single_ids": None,
            "pair_ids": None,
            "missing_ids": [MISSING_PROVINCE_ID],
            "empty_ids_rejected_locally": True,
            "selection_plan_complete": True,
        }
    selected = (PREFERRED_PROVINCE_ID
                if PREFERRED_PROVINCE_ID in bounded else bounded[0])
    remaining = [item for item in bounded if item != selected]
    pair = [selected, remaining[0]] if remaining else None
    return {
        "candidate_ids_known": True,
        "candidate_ids": bounded,
        "preferred_present": PREFERRED_PROVINCE_ID in bounded,
        "single_ids": [selected],
        "pair_ids": pair,
        "missing_ids": [MISSING_PROVINCE_ID],
        "empty_ids_rejected_locally": True,
        "selection_plan_complete": True,
    }


def _native_evaluation_not_called(value: object) -> bool | None:
    """Return the strict no-evaluation proof when the native object exists."""

    if not isinstance(value, dict):
        return None
    evaluation = value.get("native_evaluation")
    if evaluation is None:
        return None
    if not isinstance(evaluation, dict):
        return False
    items = evaluation.get("items")
    return (
        evaluation.get("called") is False
        and evaluation.get("score_available") is False
        and evaluation.get("aggregate_score_available") is False
        and evaluation.get("factor_native_count") == 0
        and items == []
    )


def _native_evaluation_summary(value: object) -> dict[str, object]:
    """Keep the bounded raw-event evaluation result separate from public data."""

    evaluation = value.get("native_evaluation") if isinstance(value, dict) else None
    if not isinstance(evaluation, dict):
        return {
            "present": False,
            "called": None,
            "score_available": None,
            "aggregate_score_available": None,
            "factor_native_count": None,
            "items_count": None,
            "not_called_contract": None,
        }
    items = evaluation.get("items")
    return {
        "present": True,
        "called": evaluation.get("called")
        if isinstance(evaluation.get("called"), bool) else None,
        "score_available": evaluation.get("score_available")
        if isinstance(evaluation.get("score_available"), bool) else None,
        "aggregate_score_available": evaluation.get(
            "aggregate_score_available")
        if isinstance(evaluation.get("aggregate_score_available"), bool) else None,
        "factor_native_count": evaluation.get("factor_native_count")
        if _integer(evaluation.get("factor_native_count"), minimum=0) else None,
        "items_count": len(items) if isinstance(items, list) else None,
        "not_called_contract": _native_evaluation_not_called(value),
    }


def _native_province_contract(
        value: object, requested_ids: object) -> bool | None:
    """Validate the final native_provinces projection for one query form.

    ``requested_ids=[]`` means the native candidate-enumeration form.  A
    non-empty list is a selected request; the sentinel-only list is kept as a
    separate missing-candidate proof.  Selection-copy proof and requested
    parameter matching are deliberately checked independently.
    """

    if not isinstance(value, dict):
        return None
    native = value.get("native_provinces")
    if not isinstance(native, dict):
        return None
    if not isinstance(requested_ids, list):
        return None
    bool_fields = (
        "query_complete", "candidate_enumeration_complete",
        "selection_requested", "requested_candidates_found", "toggle_called",
        "parameters_matched", "selection_copy_verified",
        "selected_term_records_complete", "direction_verified",
    )
    if any(not isinstance(native.get(field), bool) for field in bool_fields):
        return False
    if (native.get("query_complete") is not True
            or native.get("candidate_enumeration_complete") is not True
            or native.get("direction") != "demand"
            or native.get("direction_verified") is not True):
        return False
    candidate_count = native.get("candidate_count")
    candidates = native.get("candidates")
    if (not isinstance(candidate_count, int) or isinstance(candidate_count, bool)
            or not 0 <= candidate_count <= 512
            or not isinstance(candidates, list)
            or len(candidates) != candidate_count):
        return False
    seen_candidates: set[int] = set()
    for row in candidates:
        if not isinstance(row, dict):
            return False
        province_id = row.get("province_id")
        beneficiary = row.get("beneficiary")
        name_hex = row.get("name_hex")
        name = row.get("name")
        if name_hex is not None:
            name_shape_valid = (
                isinstance(name_hex, str)
                and len(name_hex) <= 1024
                and len(name_hex) % 2 == 0
                and HEX_RE.fullmatch(name_hex) is not None)
        else:
            # The public bridge decodes name_hex and removes the raw bytes.
            # Query artifacts therefore carry ``name`` instead.
            name_shape_valid = (
                (name is None or isinstance(name, str))
                and (row.get("name_readable") is False or isinstance(name, str)))
        if (not isinstance(province_id, int) or isinstance(province_id, bool)
                or not 1 <= province_id <= 2147483647
                or province_id in seen_candidates
                or not isinstance(beneficiary, str)
                or TAG_RE.fullmatch(beneficiary) is None
                or beneficiary != BENEFICIARY
                or not isinstance(row.get("selected"), bool)
                or not name_shape_valid
                or not isinstance(row.get("name_readable"), bool)
                or not isinstance(row.get("name_truncated"), bool)
                or row.get("native_selectability_checked") is not False
                or row.get("native_selectable") is not None):
            return False
        seen_candidates.add(province_id)
    requested = native.get("requested_province_ids")
    if (not isinstance(requested, list) or requested != requested_ids
            or len(requested) > MAX_SELECTED_PROVINCES
            or len(set(requested)) != len(requested)
            or any(_candidate_id(item) is None for item in requested)):
        return False
    expected_beneficiary = BENEFICIARY if requested_ids else None
    if native.get("requested_beneficiary") != expected_beneficiary:
        return False
    selected = native.get("selected_province_ids")
    if (not isinstance(selected, list) or len(selected) > 512
            or len(set(selected)) != len(selected)
            or any(_candidate_id(item) is None for item in selected)):
        return False
    selected_beneficiary = native.get("selected_beneficiary")
    if (selected_beneficiary is not None
            and (not isinstance(selected_beneficiary, str)
                 or TAG_RE.fullmatch(selected_beneficiary) is None)):
        return False
    toggle_count = native.get("toggle_call_count")
    if (not isinstance(toggle_count, int) or isinstance(toggle_count, bool)
            or not 0 <= toggle_count <= 512
            or native.get("toggle_called") != (toggle_count > 0)
            or native.get("selection_copy_verified") is not True
            or native.get("selected_term_records_complete") is not True):
        return False
    if not requested_ids:
        # Candidate enumeration has no selection request.  The native action
        # copy is still inspected and must prove an identical empty selection.
        if (native.get("selection_requested") is not False
                or native.get("requested_candidates_found") is not False
                or native.get("parameters_matched") is not False
                or selected
                or selected_beneficiary is not None
                or toggle_count != 0):
            return False
    elif requested_ids == [MISSING_PROVINCE_ID]:
        if (native.get("selection_requested") is not True
                or native.get("requested_candidates_found") is not False
                or native.get("parameters_matched") is not False
                or selected
                or selected_beneficiary is not None
                or native.get("reason_code") !=
                    "NATIVE_PEACE_PROVINCE_CANDIDATE_ABSENT"):
            return False
    else:
        if (native.get("selection_requested") is not True
                or native.get("requested_candidates_found") is not True
                or native.get("parameters_matched") is not True
                or set(selected) != set(requested_ids)
                or selected_beneficiary != BENEFICIARY
                or native.get("reason_code") is not None):
            return False
    delta = native.get("selection_delta_raw")
    if (delta is not None
            and (not isinstance(delta, int) or isinstance(delta, bool)
                 or not -2147483648 <= delta <= 2147483647)):
        return False
    return True


def _native_province_observation(
        value: object, requested_ids: object = None) -> dict[str, object]:
    """Capture native-province fields and the strict query-form contract."""

    if requested_ids is None:
        requested_ids = []
    native = value.get("native_provinces") if isinstance(value, dict) else None
    candidates = _province_candidate_ids(value)
    selected_ids = None
    selected_beneficiary = None
    if isinstance(native, dict):
        raw_selected = native.get("selected_province_ids")
        if isinstance(raw_selected, list):
            selected_ids = list(raw_selected)
        selected_beneficiary = native.get("selected_beneficiary")
    return {
        "native_provinces_present": isinstance(native, dict),
        "contract": _native_province_contract(value, requested_ids),
        "contract_reason": None if isinstance(native, dict)
        else "native_province_contract_missing",
        "requested_province_ids": requested_ids,
        "candidate_ids": candidates,
        "selected_province_ids": selected_ids,
        "selected_beneficiary": selected_beneficiary,
        "native_query_complete": native.get("query_complete")
        if isinstance(native, dict) else None,
        "native_enumeration_complete": native.get(
            "candidate_enumeration_complete") if isinstance(native, dict) else None,
        "native_candidate_count": native.get("candidate_count")
        if isinstance(native, dict) else None,
        "native_selection_requested": native.get("selection_requested")
        if isinstance(native, dict) else None,
        "native_requested_candidates_found": native.get(
            "requested_candidates_found") if isinstance(native, dict) else None,
        "native_parameters_matched": native.get("parameters_matched")
        if isinstance(native, dict) else None,
        "native_selection_copy_verified": native.get(
            "selection_copy_verified") if isinstance(native, dict) else None,
        "native_reason_code": native.get("reason_code")
        if isinstance(native, dict) else None,
        "native_evaluation_not_called": _native_evaluation_not_called(value),
    }


def _resolve_province_query_ids(
        path: Path, expected_session_id: object, war_id: object
        ) -> list[dict[str, object]]:
    """Resolve private inspection IDs without adding IDs to public queries."""

    found: list[dict[str, object]] = []
    seen: set[str] = set()
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except (TypeError, ValueError, UnicodeDecodeError):
                    continue
                if not isinstance(event, dict):
                    continue
                name = event.get("event")
                action_id = event.get("action_id")
                if (name not in _PROVINCE_INSPECTION_EVENTS
                        and not (isinstance(name, str)
                                 and "province" in name
                                 and "inspection" in name
                                 and action_id == PROVINCE_ACTION)):
                    continue
                if event.get("session_id") != expected_session_id:
                    continue
                if event.get("actor") not in (None, WAR_ACTOR):
                    continue
                if event.get("recipient") not in (None, WAR_RECIPIENT):
                    continue
                event_war_id = event.get("war_id", event.get("selected_war_id"))
                if event_war_id not in (None, war_id):
                    continue
                query_id = event.get("query_id")
                if not isinstance(query_id, str) or not query_id or query_id in seen:
                    continue
                seen.add(query_id)
                requested_ids = None
                for key in (
                        "requested_province_ids", "province_ids",
                        "selected_province_ids"):
                    if isinstance(event.get(key), list):
                        requested_ids = list(event[key])
                        break
                native = event.get("native_provinces")
                if requested_ids is None and isinstance(native, dict):
                    for key in (
                            "requested_province_ids", "province_ids",
                            "selected_province_ids"):
                        if isinstance(native.get(key), list):
                            requested_ids = list(native[key])
                            break
                found.append({
                    "query_id": query_id,
                    "event": name,
                    "session_matches": True,
                    "war_id_matches": event_war_id in (None, war_id),
                    "requested_province_ids": requested_ids,
                    "native_evaluation": _native_evaluation_summary(event),
                })
    except OSError:
        return []
    return found


def _private_province_events(
        path: Path, expected_session_id: object) -> list[dict[str, object]]:
    """Read only bounded, private candidate observations from the log slice."""

    allowed = frozenset({
        "event", "private", "session_id", "query_id", "stage", "index",
        "candidate_index", "province_id", "target_province_id", "selected",
        "selected_index", "complete", "identifier_verified", "available",
        "candidate_count", "candidate_enumeration_complete", "beneficiary",
        "beneficiary_tag", "term_pointer", "province_pointer",
        "name_readable", "name_truncated", "native_selectability_checked",
        "native_selectable", "capture_complete", "native_value", "native_flag",
    })
    records: list[dict[str, object]] = []
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except (TypeError, ValueError, UnicodeDecodeError):
                    continue
                if not isinstance(event, dict):
                    continue
                name = event.get("event")
                if (event.get("private") is not True
                        or name != _PROVINCE_PRIVATE_EVENT):
                    continue
                query_id = event.get("query_id")
                if not isinstance(query_id, str) or not query_id:
                    continue
                record = {
                    key: event.get(key) for key in allowed if key in event
                }
                record["session_matches"] = (
                    event.get("session_id") == expected_session_id)
                records.append(record)
    except OSError:
        return []
    return records


def _private_province_events_contract(
        records: object, expected_query_ids: object) -> bool | None:
    """Validate the final private candidate-event name and bounded fields."""

    if not isinstance(records, list) or not isinstance(expected_query_ids, list):
        return None
    if any(not isinstance(query_id, str) or not query_id
           for query_id in expected_query_ids):
        return False
    by_query: dict[str, int] = {query_id: 0 for query_id in expected_query_ids}
    for record in records:
        if not isinstance(record, dict):
            return False
        query_id = record.get("query_id")
        if query_id not in by_query:
            return False
        if (record.get("event") != _PROVINCE_PRIVATE_EVENT
                or record.get("private") is not True
                or record.get("session_matches") is not True
                or not isinstance(record.get("index"), int)
                or not isinstance(record.get("candidate_index"), int)
                or record.get("index") != record.get("candidate_index")
                or not isinstance(record.get("province_id"), int)
                or not 1 <= record["province_id"] <= 2147483647
                or not isinstance(record.get("beneficiary_tag"), str)
                or TAG_RE.fullmatch(record["beneficiary_tag"]) is None
                or not isinstance(record.get("term_pointer"), str)
                or not re.fullmatch(r"0x[0-9a-fA-F]+", record["term_pointer"])
                or not isinstance(record.get("province_pointer"), str)
                or not re.fullmatch(r"0x[0-9a-fA-F]+", record["province_pointer"])
                or not isinstance(record.get("selected"), bool)
                or not isinstance(record.get("name_readable"), bool)
                or not isinstance(record.get("name_truncated"), bool)
                or record.get("native_selectability_checked") is not False
                or record.get("native_selectable") is not None
                or record.get("complete") is not True):
            return False
        by_query[query_id] += 1
    # A zero-candidate query legitimately emits no per-row event.  Non-empty
    # query captures must still be bound to their native query id.
    return all(count > 0 for count in by_query.values()) if by_query else bool(records) is False


def _requested_ids_from_parameters(value: object) -> list[int] | None:
    if not isinstance(value, dict):
        return None
    context = value.get("peace_context")
    if not isinstance(context, dict):
        return None
    terms = context.get("terms")
    if (not isinstance(terms, list) or not terms
            or not isinstance(terms[0], dict)):
        return []
    province_ids = terms[0].get("province_ids")
    return list(province_ids) if isinstance(province_ids, list) else None


def _bind_query_ids(
        query_records: list[dict[str, object]], query_names: list[str],
        query_parameters: object = None) -> dict[str, list[str]]:
    bindings: dict[str, list[str]] = {name: [] for name in query_names}
    parameters = query_parameters if isinstance(query_parameters, dict) else {}
    unused = set(query_names)
    unresolved: list[dict[str, object]] = []
    for index, record in enumerate(query_records):
        query_id = record.get("query_id")
        if not isinstance(query_id, str) or not query_id:
            continue
        requested_ids = record.get("requested_province_ids")
        matches = [name for name in unused
                   if isinstance(parameters.get(name), dict)
                   and _requested_ids_from_parameters(parameters[name])
                   == requested_ids]
        if len(matches) == 1:
            bindings[matches[0]].append(query_id)
            unused.remove(matches[0])
        else:
            unresolved.append(record)
    # Keep the old sequential fallback only for an ambiguous/missing request
    # shape.  Normal province query records are bound by their requested IDs.
    for record in unresolved:
        query_id = record.get("query_id")
        if not isinstance(query_id, str) or not query_id:
            continue
        if not unused:
            break
        name = next((candidate for candidate in query_names
                     if candidate in unused), None)
        if name is None:
            break
        bindings[name].append(query_id)
        unused.remove(name)
    return bindings


def _reconcile_raw_evaluations(
        bindings: object, query_records: object,
        observations: dict[str, dict[str, object]]) -> dict[str, object]:
    """Bind raw native evaluation summaries by query id.

    The public projection intentionally omits ``native_evaluation``.  This
    function therefore updates only the internal observation/check view from
    the bounded raw-event summary; it never treats a public projection field
    as a substitute for the native event.
    """

    if not isinstance(bindings, dict) or not isinstance(query_records, list):
        return {}
    by_query_id: dict[str, dict[str, object]] = {}
    for record in query_records:
        if not isinstance(record, dict):
            continue
        query_id = record.get("query_id")
        summary = record.get("native_evaluation")
        if (isinstance(query_id, str) and query_id
                and isinstance(summary, dict)):
            if "not_called_contract" not in summary:
                summary = _native_evaluation_summary(
                    {"native_evaluation": summary})
            by_query_id[query_id] = summary
    reconciled: dict[str, object] = {}
    for query_name, query_ids in bindings.items():
        summary: dict[str, object] | None = None
        if (isinstance(query_ids, list) and len(query_ids) == 1
                and isinstance(query_ids[0], str)):
            candidate = by_query_id.get(query_ids[0])
            if isinstance(candidate, dict):
                summary = candidate
        reconciled[query_name] = summary
        observation = observations.get(query_name)
        if isinstance(observation, dict):
            observation["raw_native_evaluation"] = summary
            observation["native_evaluation_not_called"] = (
                summary.get("not_called_contract")
                if isinstance(summary, dict) else None)
    return reconciled


def _evaluation_stage_contract(
        observations: dict[str, dict[str, object]],
        selection_plan: object) -> bool | None:
    """Require no evaluation before a match; unmatched selections are explicit."""

    required_names = ("province_candidates", "province_missing_candidate")
    required = [observations.get(name, {}).get("native_evaluation_not_called")
                for name in required_names]
    if any(value is None for value in required):
        return None
    if any(value is not True for value in required):
        return False
    selected_names = ["province_single", "province_pair"]
    selected_present = False
    for name in selected_names:
        observation = observations.get(name)
        if not isinstance(observation, dict):
            continue
        selected_present = True
        # A native selector mismatch is a real native result.  It must not be
        # relabeled as a consumer projection failure; it also must not run
        # evaluation for an offer that never matched its requested terms.
        if observation.get("native_parameters_matched") is False:
            if observation.get("native_evaluation_not_called") is not True:
                return False
    if not selected_present and isinstance(selection_plan, dict):
        return True
    return True


def _selection_plan_contract(
        plan: object, candidate_query: object) -> bool | None:
    if not isinstance(plan, dict) or plan.get("candidate_ids_known") is not True:
        return None
    candidates = plan.get("candidate_ids")
    if not isinstance(candidates, list):
        return None
    native = (candidate_query.get("native_provinces")
              if isinstance(candidate_query, dict) else None)
    if not isinstance(native, dict):
        return None
    # Verify the selection plan independently from native legality/evaluation.
    single = plan.get("single_ids")
    pair = plan.get("pair_ids")
    if (plan.get("missing_ids") != [MISSING_PROVINCE_ID]
            or plan.get("empty_ids_rejected_locally") is not True):
        return False
    if not candidates:
        return single is None and pair is None
    if (not isinstance(single, list) or len(single) != 1
            or single[0] not in candidates):
        return False
    if pair is not None:
        if (not isinstance(pair, list) or len(pair) != 2
                or pair[0] != single[0]
                or pair[1] not in candidates or pair[1] == pair[0]):
            return False
    return True


def _reject_empty_province_selection(war_id: object) -> dict[str, object]:
    """Reject an empty cede-province selection without publishing QUERY6."""

    return {
        "status": "rejected",
        "reason_code": "PEACE_PROVINCE_EMPTY_IDS_REJECTED_LOCAL",
        "query_called": False,
        "parameters": _province_parameters(str(war_id), []),
    }


def _offline_contract_assertions() -> None:
    """Exercise query forms and preserve unknown native results offline."""

    discovery = _province_parameters("war_demo", None)
    assert discovery == {
        "peace_context": {"war_id": "war_demo", "direction": "demand",
                           "terms": []}}
    explicit_empty = _province_parameters("war_demo", [])
    assert explicit_empty["peace_context"]["terms"] == [{
        "action_id": PROVINCE_ACTION, "province_ids": [],
        "beneficiary": BENEFICIARY,
    }]
    preferred = _selection_plan([12, 177, 178])
    assert preferred["single_ids"] == [177]
    assert preferred["pair_ids"] == [177, 12]
    fallback = _selection_plan([12, 13])
    assert fallback["single_ids"] == [12]
    assert fallback["pair_ids"] == [12, 13]
    assert fallback["missing_ids"] == [MISSING_PROVINCE_ID]
    assert fallback["empty_ids_rejected_locally"] is True
    unknown = _native_province_observation(
        {"action_id": PROVINCE_ACTION}, [177])
    assert unknown["contract"] is None
    sample = {"native_provinces": {
        "query_complete": True,
        "candidate_enumeration_complete": True,
        "candidate_count": 2,
        "candidates": [
            {"province_id": 177, "beneficiary": "FRA", "selected": False,
             "name_hex": "", "name_readable": False,
             "name_truncated": False, "native_selectability_checked": False,
             "native_selectable": None},
            {"province_id": 178, "beneficiary": "FRA", "selected": False,
             "name_hex": "", "name_readable": False,
             "name_truncated": False, "native_selectability_checked": False,
             "native_selectable": None},
        ],
        "selection_requested": False, "requested_province_ids": [],
        "requested_beneficiary": None, "requested_candidates_found": False,
        "toggle_called": False, "toggle_call_count": 0,
        "parameters_matched": False, "selected_province_ids": [],
        "selected_beneficiary": None, "selection_copy_verified": True,
        "selected_term_records_complete": True, "direction": "demand",
        "direction_verified": True, "reason_code": None,
        "selection_delta_raw": None,
    }}
    assert _province_candidate_ids(sample) == [177, 178]
    assert _native_province_contract(sample, []) is True
    assert _native_province_contract(sample, [MISSING_PROVINCE_ID]) is False
    rejected = _reject_empty_province_selection("war_demo")
    assert rejected["query_called"] is False
    assert rejected["status"] == "rejected"
    observations = {
        "province_candidates": {"native_evaluation_not_called": None},
        "province_missing_candidate": {
            "native_evaluation_not_called": None},
        "province_single": {
            "native_parameters_matched": False,
            "selected_province_ids": [],
            "native_evaluation_not_called": None},
    }
    raw_evaluations = _reconcile_raw_evaluations(
        {"province_candidates": ["q-candidates"],
         "province_missing_candidate": ["q-missing"],
         "province_single": ["q-single"]},
        [{"query_id": "q-candidates", "native_evaluation": {
            "called": False, "score_available": False,
            "aggregate_score_available": False, "factor_native_count": 0,
            "items": []}},
         {"query_id": "q-missing", "native_evaluation": {
            "called": False, "score_available": False,
            "aggregate_score_available": False, "factor_native_count": 0,
            "items": []}},
         {"query_id": "q-single", "native_evaluation": {
            "called": False, "score_available": False,
            "aggregate_score_available": False, "factor_native_count": 0,
            "items": []}}], observations)
    assert raw_evaluations["province_candidates"]["not_called_contract"] is True
    assert observations["province_missing_candidate"][
        "native_evaluation_not_called"] is True
    assert _evaluation_stage_contract(observations, fallback) is True


def _status_for_checks(checks: dict[str, object]) -> str:
    if any(value is False for value in checks.values()):
        return "failed"
    if any(value is None for value in checks.values()):
        return "unknown"
    return "passed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--expected-date-raw", type=int, required=True)
    args = parser.parse_args()
    _offline_contract_assertions()
    installation = args.installation.resolve(strict=True)
    session = ObserverSession(installation, game_exe())
    artifact = _new_artifact(installation.parent, "peace-province-offer-queries")
    report: dict[str, object] = {
        "validator": Path(__file__).name,
        "artifact": str(artifact),
        "installation": str(installation),
        "status": "running",
        "action_id": PROVINCE_ACTION,
        "phase": "initiate",
        "actor": WAR_ACTOR,
        "recipient": WAR_RECIPIENT,
        "beneficiary": BENEFICIARY,
        "preferred_province_id": PREFERRED_PROVINCE_ID,
        "expected_date_raw": args.expected_date_raw,
        "execute_call_count": 0,
        "business_submission": False,
        "time_advance_call_count": 0,
        "save_call_count": 0,
        "query_call_count": 0,
        "queries": {},
        "local_rejections": {},
    }
    log = session.directory / "control-probe.jsonl"
    log_start: int | None = None
    before: dict[str, object] | None = None
    after: dict[str, object] | None = None
    control_before: object = None
    control_after: object = None
    discovery: dict[str, object] | None = None
    candidate_query: dict[str, object] | None = None
    war_id: str | None = None
    selection_plan: dict[str, object] = _selection_plan(None)
    query_parameters: dict[str, dict[str, object]] = {}
    try:
        health = wait_runtime_ready(session, restore_minimized=True)
        if health.get("status") != "ready":
            raise RuntimeError("PEACE_PROVINCE_QUERY_SESSION_UNREADY")
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
        if (control_before != {"date_raw": args.expected_date_raw,
                               "paused_flag": 1, "player_slot": 189}
                or not _snapshots_complete(before)):
            raise RuntimeError("PEACE_PROVINCE_QUERY_BASELINE_UNAVAILABLE")
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
            war_id = _single_discovered_war_id(
                discovery, WAR_ACTOR, WAR_RECIPIENT)
            report["war_id"] = war_id
            if war_id is not None:
                candidate_parameters = _province_parameters(war_id, None)
                query_parameters["province_candidates"] = candidate_parameters
                report["query_call_count"] += 1
                candidate_query = api.inspect_diplomatic_action(
                    PROVINCE_ACTION, WAR_ACTOR, WAR_RECIPIENT,
                    phase="initiate", parameters=candidate_parameters)
                report["queries"]["province_candidates"] = candidate_query
                _write_json(artifact / "province-candidates.json", candidate_query)
                selection_plan = _selection_plan(
                    _province_candidate_ids(candidate_query))
                report["selection_plan"] = selection_plan

                single_ids = selection_plan.get("single_ids")
                if isinstance(single_ids, list):
                    parameters = _province_parameters(war_id, single_ids)
                    query_parameters["province_single"] = parameters
                    report["query_call_count"] += 1
                    result = api.inspect_diplomatic_action(
                        PROVINCE_ACTION, WAR_ACTOR, WAR_RECIPIENT,
                        phase="initiate", parameters=parameters)
                    report["queries"]["province_single"] = result
                    _write_json(artifact / "province-single.json", result)

                pair_ids = selection_plan.get("pair_ids")
                if isinstance(pair_ids, list):
                    parameters = _province_parameters(war_id, pair_ids)
                    query_parameters["province_pair"] = parameters
                    report["query_call_count"] += 1
                    result = api.inspect_diplomatic_action(
                        PROVINCE_ACTION, WAR_ACTOR, WAR_RECIPIENT,
                        phase="initiate", parameters=parameters)
                    report["queries"]["province_pair"] = result
                    _write_json(artifact / "province-pair.json", result)

                missing_ids = [MISSING_PROVINCE_ID]
                missing_parameters = _province_parameters(war_id, missing_ids)
                query_parameters["province_missing_candidate"] = missing_parameters
                report["query_call_count"] += 1
                result = api.inspect_diplomatic_action(
                    PROVINCE_ACTION, WAR_ACTOR, WAR_RECIPIENT,
                    phase="initiate", parameters=missing_parameters)
                report["queries"]["province_missing_candidate"] = result
                _write_json(artifact / "province-missing-candidate.json", result)

                # Empty IDs are an invalid selection form for this operator.
                # Keep the attempted shape in the report, but do not publish
                # a QUERY6 wire or count it as a native query.
                report["local_rejections"]["province_empty_ids"] = (
                    _reject_empty_province_selection(war_id))

        after = _run_snapshots(session, artifact / "after" / "probes")
        control_after = _control_summary(after["control_state"]["snapshot"])
        health_after = session.health()
        report["query_parameters"] = query_parameters
        report["after"] = {
            "control": control_after,
            "health": health_after,
            "probes": _public_probe_records(after),
        }
        native_observations: dict[str, dict[str, object]] = {}
        for name, parameters in query_parameters.items():
            result = report["queries"].get(name)
            requested_context = parameters.get("peace_context")
            requested_ids: list[int] = []
            if (isinstance(requested_context, dict)
                    and isinstance(requested_context.get("terms"), list)
                    and requested_context.get("terms")
                    and isinstance(requested_context["terms"][0], dict)):
                raw_ids = requested_context["terms"][0].get("province_ids")
                if isinstance(raw_ids, list):
                    requested_ids = list(raw_ids)
            native_observations[name] = _native_province_observation(
                result, requested_ids)
        report["native_province_observations"] = native_observations
        report["checks"] = {
            "discovery_public_contract": (
                _public_context_contract(discovery, WAR_ACTOR, WAR_RECIPIENT)
                if isinstance(discovery, dict) else False),
            "discovery_one_war": (
                _single_discovered_war_id(
                    discovery, WAR_ACTOR, WAR_RECIPIENT) == war_id
                if isinstance(discovery, dict) else False),
            "candidate_public_contract": (
                _public_province_query_contract(
                    candidate_query, query_parameters.get("province_candidates"))
                if candidate_query is not None else False),
            "selected_public_contracts": all(
                _public_province_query_contract(
                    report["queries"].get(name), parameters)
                for name, parameters in query_parameters.items()
                if name != "province_candidates"),
            "selection_plan_contract": _selection_plan_contract(
                selection_plan, candidate_query),
            "native_province_contract": (
                None if any(observation.get("contract") is None
                            for observation in native_observations.values())
                else all(observation.get("contract") is True
                         for observation in native_observations.values())),
            "candidate_enumeration_copy_verified": (
                native_observations.get("province_candidates", {}).get(
                    "native_selection_copy_verified") is True),
            "missing_candidate_copy_verified": (
                native_observations.get("province_missing_candidate", {}).get(
                    "native_selection_copy_verified") is True),
            "parameters_match_independent_from_copy": (
                native_observations.get("province_candidates", {}).get(
                    "native_parameters_matched") is False
                and native_observations.get("province_missing_candidate", {}).get(
                    "native_parameters_matched") is False
                and (not isinstance(selection_plan.get("single_ids"), list)
                     or native_observations.get("province_single", {}).get(
                         "native_parameters_matched") is True)),
            "evaluation_not_called_for_enumeration": (
                native_observations.get("province_candidates", {}).get(
                    "native_evaluation_not_called") is True),
            "evaluation_not_called_for_missing_candidate": (
                native_observations.get("province_missing_candidate", {}).get(
                    "native_evaluation_not_called") is True),
            "evaluation_only_after_matched_selection": (
                all(observation.get("native_evaluation_not_called") is True
                    for name, observation in native_observations.items()
                    if name in {"province_candidates", "province_missing_candidate"})
                and (not isinstance(selection_plan.get("single_ids"), list)
                     or native_observations.get("province_single", {}).get(
                         "native_parameters_matched") is True)),
            "public_queries_have_no_private_fields": not _has_private_fields(
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
            "empty_ids_rejected_locally": (
                report["local_rejections"].get("province_empty_ids", {}).get(
                    "status") == "rejected"
                and report["local_rejections"].get("province_empty_ids", {}).get(
                    "query_called") is False),
            "empty_ids_not_published": (
                "province_empty_ids" not in query_parameters),
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
                slice_path = artifact / "native-events-slice.jsonl"
                resolved = _resolve_province_query_ids(
                    slice_path, session.record.get("session_id"), war_id)
                report["native_query_id_records"] = resolved
                bindings = _bind_query_ids(
                    resolved, list(query_parameters), query_parameters)
                report["native_query_id_bindings"] = bindings
                raw_evaluations = _reconcile_raw_evaluations(
                    bindings, resolved, native_observations)
                report["native_raw_evaluation_by_query"] = raw_evaluations
                report["private_province_events"] = _private_province_events(
                    slice_path, session.record.get("session_id"))
                if "checks" in report:
                    report["checks"]["native_query_id_resolution_contract"] = (
                        True if resolved else None)
                    report["checks"]["raw_native_evaluation_query_binding"] = (
                        bool(raw_evaluations)
                        and all(isinstance(summary, dict)
                                and summary.get("present") is True
                                for summary in raw_evaluations.values()))
                    report["checks"]["evaluation_not_called_for_enumeration"] = (
                        native_observations.get("province_candidates", {}).get(
                            "native_evaluation_not_called") is True)
                    report["checks"]["evaluation_not_called_for_missing_candidate"] = (
                        native_observations.get("province_missing_candidate", {}).get(
                            "native_evaluation_not_called") is True)
                    report["checks"]["evaluation_only_after_matched_selection"] = (
                        _evaluation_stage_contract(
                            native_observations, selection_plan))
                    required_private_ids: list[str] = []
                    for query_name, query_ids in bindings.items():
                        observation = native_observations.get(query_name, {})
                        if observation.get("candidate_ids"):
                            required_private_ids.extend(query_ids)
                    report["checks"]["private_province_events_contract"] = (
                        _private_province_events_contract(
                            report["private_province_events"], required_private_ids))
                    selected_reconcile: dict[str, object] = {}
                    for query_name in ("province_single", "province_pair"):
                        observation = native_observations.get(query_name)
                        if not isinstance(observation, dict):
                            continue
                        matched = observation.get("native_parameters_matched")
                        selected_ids = observation.get("selected_province_ids")
                        if matched is False and selected_ids == []:
                            state = "native_selector_unmatched"
                        elif matched is True:
                            state = "native_selector_matched"
                        else:
                            state = "native_selector_result_unknown"
                        selected_reconcile[query_name] = {
                            "state": state,
                            "parameters_matched": matched,
                            "selected_province_ids": selected_ids,
                            "reason_code": observation.get(
                                "native_reason_code"),
                        }
                    report["reconcile"] = {
                        "evaluation_source": "raw_native_event_by_query_id",
                        "public_projection_evaluation_used": False,
                        "selected_selector": selected_reconcile,
                    }
            elif "checks" in report:
                report["checks"]["native_query_id_resolution_contract"] = None
                report["checks"]["private_province_events_contract"] = None
                report["checks"]["raw_native_evaluation_query_binding"] = None
                report["checks"]["evaluation_not_called_for_enumeration"] = None
                report["checks"]["evaluation_not_called_for_missing_candidate"] = None
                report["checks"]["evaluation_only_after_matched_selection"] = None
        checks = report.get("checks")
        report["unknown_checks"] = (
            [key for key, value in checks.items() if value is None]
            if isinstance(checks, dict) else [])
        report["status"] = (
            _status_for_checks(checks)
            if not report.get("error") and isinstance(checks, dict)
            else "failed")
        _write_json(artifact / "report.json", report)
    print(json.dumps({"status": report["status"], "artifact": str(artifact)},
                     ensure_ascii=False))
    return 0 if report["status"] in ("passed", "unknown") else 1


if __name__ == "__main__":
    raise SystemExit(main())
