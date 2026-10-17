"""Run one read-only peace-factor identifier and detail-completeness batch.

The operator discovers the FRA--ENG war, inspects a selected empty white-peace
offer, and inspects one selected 10.0-ducat demand.  It checks the public
factor projection against the private provenance records written by the
observer.  It never submits an offer, advances time, saves the game, or turns
the observed score into an acceptance decision.
"""
from __future__ import annotations

import argparse
from collections import OrderedDict
import json
from pathlib import Path
import sys

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
    _has_private_fields, _public_context_contract, _public_empty_offer_contract,
    _single_discovered_war_id,
)
from work.run_peace_money_offer_queries import (
    _money_parameters, _native_money_contract,
)
from work.run_royal_marriage_execution import (
    _installation_binding, _public_probe_records, _snapshots_complete,
)
from work.validate_alliance_reload import _control_summary, _run_snapshots


WAR_ACTOR = "FRA"
WAR_RECIPIENT = "ENG"
MONEY_AMOUNT = "10.0"
MONEY_ACTION = "demand_ducats"
WHITE_FACTOR_COUNT = 5
MONEY_FACTOR_COUNT = 8
WHITE_SCORE = -45
MONEY_SCORE = -100
WHITE_AGGREGATE = 0
MONEY_AGGREGATE = 1
PROVENANCE_EVENT = "native_alliance_reason_provenance"


def _control_is_expected(control: object, expected_date_raw: int) -> bool:
    return control == {
        "date_raw": expected_date_raw,
        "paused_flag": 1,
        "player_slot": 189,
    }


def _integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _factor_item_contract(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    identifier = item.get("native_identifier")
    if (not isinstance(identifier, str) or not identifier
            or item.get("identifier_verified") is not True):
        return False
    if (not _integer(item.get("native_value"))
            or item.get("native_value_verified") is not True
            or not isinstance(item.get("native_flag"), bool)
            or item.get("native_flag_verified") is not True
            or item.get("row_binding_verified") is not True):
        return False
    if (not isinstance(item.get("text"), str)
            or item.get("text_decoded") is not True
            or item.get("text_truncated") is not False):
        return False
    return item.get("complete") is True


def _factor_projection_contract(
        value: object, expected_count: int, expected_score: int,
        expected_aggregate: int) -> bool:
    """Validate score/factor fields without treating them as acceptance."""

    if not isinstance(value, dict):
        return False
    native = value.get("native_evaluation")
    acceptance = value.get("acceptance")
    costs = value.get("costs")
    if (not isinstance(native, dict) or not isinstance(acceptance, dict)
            or not isinstance(costs, dict)):
        return False
    if any(native.get(key) != wanted for key, wanted in (
        ("called", True), ("score_available", True),
        ("score_raw", expected_score),
        ("aggregate_score_available", True),
        ("aggregate_score_raw", expected_aggregate),
        ("score_representation", "signed_int32"),
        ("factor_native_count", expected_count),
        ("factor_capture_truncated", False), ("factors_available", True),
        ("factors_complete", True), ("complete", False),
    )):
        return False
    native_items = native.get("items")
    acceptance_items = acceptance.get("items")
    if (not isinstance(native_items, list)
            or not isinstance(acceptance_items, list)
            or len(native_items) != expected_count
            or len(acceptance_items) != expected_count
            or not all(_factor_item_contract(item) for item in native_items)
            or not all(_factor_item_contract(item) for item in acceptance_items)):
        return False
    compared_fields = (
        "native_identifier", "identifier_verified", "native_value",
        "native_value_verified", "native_flag", "native_flag_verified",
        "row_binding_verified", "text", "text_decoded", "text_truncated",
        "complete",
    )
    for native_item, acceptance_item in zip(native_items, acceptance_items):
        if any(native_item.get(field) != acceptance_item.get(field)
               for field in compared_fields):
            return False

    if any(acceptance.get(key) != wanted for key, wanted in (
        ("details_available", True), ("details_complete", True),
        ("prediction_available", False), ("native_total", expected_score),
        ("predicted_response", "unknown"), ("unit", "unknown"),
        ("scale_verified", False), ("complete", False),
    )):
        return False
    cost_evaluation = costs.get("native_evaluation")
    if not isinstance(cost_evaluation, dict):
        return False
    return all(cost_evaluation.get(key) == wanted for key, wanted in (
        ("aggregate_score_available", True),
        ("aggregate_score_raw", expected_aggregate),
        ("unit", "unknown"), ("scale_verified", False),
        ("complete", False),
    ))


def _read_provenance_groups(path: Path) -> list[dict[str, object]]:
    """Read only bounded provenance fields, grouped by private query id."""

    grouped: OrderedDict[str, list[dict[str, object]]] = OrderedDict()
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except (TypeError, ValueError, UnicodeDecodeError):
                    continue
                if (not isinstance(event, dict)
                        or event.get("event") != PROVENANCE_EVENT
                        or event.get("private") is not True):
                    continue
                query_id = event.get("query_id")
                index = event.get("index")
                if (not isinstance(query_id, str) or not query_id
                        or not _integer(index) or index < 0):
                    continue
                grouped.setdefault(query_id, []).append({
                    "query_id": query_id,
                    "index": index,
                    "constructor_caller_rva": event.get(
                        "constructor_caller_rva"),
                    "constructor_call_rva": event.get("constructor_call_rva"),
                    "localization_key": event.get("localization_key"),
                    "native_value": event.get("native_value"),
                    "constructor_argument_value": event.get(
                        "constructor_argument_value"),
                    "native_flag": event.get("native_flag"),
                    "constructor_value_verified": event.get(
                        "constructor_value_verified"),
                    "final_row_binding": event.get("final_row_binding"),
                    "complete": event.get("complete"),
                })
    except OSError:
        return []
    return [{"query_id": query_id, "items": items}
            for query_id, items in grouped.items()]


def _provenance_group_contract(
        groups: object, public_value: object, expected_count: int) -> bool:
    """Bind one private query group to the public factor list by index."""

    if (not isinstance(groups, list) or len(groups) != 1
            or not isinstance(groups[0], dict)):
        return False
    group = groups[0]
    query_id = group.get("query_id")
    records = group.get("items")
    if (not isinstance(query_id, str) or not query_id
            or not isinstance(records, list)
            or len(records) != expected_count):
        return False
    acceptance = public_value.get("acceptance") if isinstance(
        public_value, dict) else None
    public_items = acceptance.get("items") if isinstance(acceptance, dict) else None
    if not isinstance(public_items, list) or len(public_items) != expected_count:
        return False
    records_by_index = {item.get("index"): item for item in records
                        if isinstance(item, dict)}
    if set(records_by_index) != set(range(expected_count)):
        return False
    for index, public_item in enumerate(public_items):
        record = records_by_index[index]
        if not isinstance(public_item, dict):
            return False
        if any(record.get(key) != wanted for key, wanted in (
            ("constructor_value_verified", True),
            ("final_row_binding", True), ("complete", True),
        )):
            return False
        caller = record.get("constructor_caller_rva")
        key = record.get("localization_key")
        if (not isinstance(caller, str) or not caller
                or not isinstance(key, str) or not key):
            return False
        if (public_item.get("native_identifier") != key
                or public_item.get("native_value") != record.get("native_value")
                or public_item.get("native_flag") != record.get("native_flag")
                or record.get("constructor_argument_value")
                    != record.get("native_value")):
            return False
    return True


def _provenance_observation(
        groups: list[dict[str, object]]) -> list[dict[str, object]]:
    """Keep private provenance fields useful while excluding raw allocations."""

    return groups


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--expected-date-raw", type=int, required=True)
    args = parser.parse_args()
    installation = args.installation.resolve(strict=True)
    session = ObserverSession(installation, game_exe())
    artifact = _new_artifact(installation.parent, "peace-factor-identifiers")
    report: dict = {
        "validator": Path(__file__).name,
        "artifact": str(artifact),
        "installation": str(installation),
        "status": "running",
        "action_id": MONEY_ACTION,
        "phase": "initiate",
        "actor": WAR_ACTOR,
        "recipient": WAR_RECIPIENT,
        "expected_date_raw": args.expected_date_raw,
        "expected_factor_counts": {"white_peace": WHITE_FACTOR_COUNT,
                                    MONEY_ACTION: MONEY_FACTOR_COUNT},
        "expected_scores": {
            "white_peace": {"score_raw": WHITE_SCORE,
                             "aggregate_score_raw": WHITE_AGGREGATE},
            MONEY_ACTION: {"score_raw": MONEY_SCORE,
                           "aggregate_score_raw": MONEY_AGGREGATE},
        },
        "execute_call_count": 0,
        "business_submission": False,
        "time_advance_call_count": 0,
        "save_call_count": 0,
        "query_call_count": 0,
        "queries": {},
    }
    log = session.directory / "control-probe.jsonl"
    log_start: int | None = None
    before: dict | None = None
    after: dict | None = None
    control_before: object = None
    control_after: object = None
    discovery: dict | None = None
    selected_white: dict | None = None
    selected_money: dict | None = None
    try:
        health = wait_runtime_ready(session, restore_minimized=True)
        if health.get("status") != "ready":
            raise RuntimeError("PEACE_FACTOR_QUERY_SESSION_UNREADY")
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
        if (not _control_is_expected(control_before, args.expected_date_raw)
                or not _snapshots_complete(before)):
            raise RuntimeError("PEACE_FACTOR_QUERY_BASELINE_UNAVAILABLE")
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
            if war_id is None:
                raise RuntimeError("PEACE_FACTOR_DISCOVERY_INCOMPLETE")
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
        report["factor_observations"] = {
            "white_peace": {
                "factor_count": (len(selected_white.get("acceptance", {}).get(
                    "items", [])) if isinstance(selected_white, dict) else None),
                "score_raw": (selected_white.get("native_evaluation", {}).get(
                    "score_raw") if isinstance(selected_white, dict) else None),
                "aggregate_score_raw": (selected_white.get("costs", {}).get(
                    "native_evaluation", {}).get("aggregate_score_raw")
                    if isinstance(selected_white, dict) else None),
            },
            MONEY_ACTION: {
                "factor_count": (len(selected_money.get("acceptance", {}).get(
                    "items", [])) if isinstance(selected_money, dict) else None),
                "score_raw": (selected_money.get("native_evaluation", {}).get(
                    "score_raw") if isinstance(selected_money, dict) else None),
                "aggregate_score_raw": (selected_money.get("costs", {}).get(
                    "native_evaluation", {}).get("aggregate_score_raw")
                    if isinstance(selected_money, dict) else None),
            },
        }
        report["checks"] = {
            "discovery_public_contract": _public_context_contract(
                discovery, WAR_ACTOR, WAR_RECIPIENT),
            "discovery_one_war": _single_discovered_war_id(
                discovery, WAR_ACTOR, WAR_RECIPIENT) == war_id,
            "selected_white_contract": _public_empty_offer_contract(
                selected_white, WAR_ACTOR, WAR_RECIPIENT, war_id),
            "selected_white_factor_contract": _factor_projection_contract(
                selected_white, WHITE_FACTOR_COUNT, WHITE_SCORE,
                WHITE_AGGREGATE),
            "selected_money_contract": _native_money_contract(
                selected_money, MONEY_AMOUNT, True),
            "selected_money_factor_contract": _factor_projection_contract(
                selected_money, MONEY_FACTOR_COUNT, MONEY_SCORE,
                MONEY_AGGREGATE),
            "same_selected_war": all(
                isinstance(value, dict)
                and value.get("selected_war_id") == war_id
                for value in (selected_white, selected_money)),
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
        }
    except Exception as error:
        report["error"] = {"type": type(error).__name__,
                            "message": str(error)}
    finally:
        if isinstance(log_start, int):
            native_events = _copy_log_slice(
                log, log_start, artifact / "native-events-slice.jsonl")
            report["native_events"] = native_events
            groups = []
            if native_events.get("status") == "ok":
                groups = _read_provenance_groups(
                    artifact / "native-events-slice.jsonl")
            report["private_provenance"] = _provenance_observation(groups)
            if "checks" in report:
                report["checks"]["private_provenance_contract"] = (
                    len(groups) == 2
                    and _provenance_group_contract(
                        groups[:1], selected_white, WHITE_FACTOR_COUNT)
                    and _provenance_group_contract(
                        groups[1:2], selected_money, MONEY_FACTOR_COUNT))
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
