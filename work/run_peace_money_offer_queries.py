"""Run read-only money peace-term inspections for one paused batch.

The operator discovers one FRA--ENG war, checks an empty white-peace
baseline, and then queries exact demand-ducats amounts.  It never submits a
peace offer, advances time, saves the game, or assumes that an acceptance
score means that an NPC would accept the offer.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
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
    _evaluation_observation, _evaluation_projection, _has_private_fields,
    _public_context_contract, _public_empty_offer_contract,
    _single_discovered_war_id,
)
from work.run_royal_marriage_execution import (
    _installation_binding, _public_probe_records, _snapshots_complete,
)
from work.validate_alliance_reload import _control_summary, _run_snapshots


CASES = (
    ("money_10_0", "10.0"),
    ("money_20_0", "20.0"),
    ("money_10_0_repeat", "10.0"),
)
WAR_ACTOR = "FRA"
WAR_RECIPIENT = "ENG"
MONEY_ACTION = "demand_ducats"
DECIMAL_SCALE = Decimal("1000")
DECIMAL_PRECISION = Decimal("0.1")
EXPECTED_SCALE = 1000
EXPECTED_PRECISION_RAW = 100
EXPECTED_INPUT_CEILING_RAW = 100000


def _amount_raw(amount: str) -> int:
    try:
        decimal_amount = Decimal(amount)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("MONEY_AMOUNT_NOT_DECIMAL") from error
    if not decimal_amount.is_finite() or decimal_amount <= 0:
        raise ValueError("MONEY_AMOUNT_NOT_POSITIVE")
    scaled = decimal_amount * DECIMAL_SCALE
    if scaled != scaled.to_integral_value():
        raise ValueError("MONEY_AMOUNT_SCALE_INVALID")
    raw = int(scaled)
    if raw <= 0 or raw % EXPECTED_PRECISION_RAW != 0:
        raise ValueError("MONEY_AMOUNT_PRECISION_INVALID")
    return raw


def _overlimit_amount(ceiling_raw: int) -> tuple[str, int]:
    if (isinstance(ceiling_raw, bool) or not isinstance(ceiling_raw, int)
            or ceiling_raw < 0):
        raise ValueError("MONEY_CEILING_INVALID")
    # The native precision is exactly 100 raw units (0.1 ducat).  Select the
    # next legal precision bucket first, then use Decimal only for the public
    # amount string.  This handles an unaligned ceiling such as 860050 by
    # selecting 860100 rather than rounding 860.15 up to 860.2.
    raw = ((ceiling_raw // EXPECTED_PRECISION_RAW) + 1) * EXPECTED_PRECISION_RAW
    candidate = Decimal(raw) / DECIMAL_SCALE
    if raw <= ceiling_raw or raw % EXPECTED_PRECISION_RAW != 0:
        raise ValueError("MONEY_OVERLIMIT_AMOUNT_NOT_STRICTLY_ABOVE_CEILING")
    return format(candidate, "f"), raw


def _offline_contract_assertions() -> None:
    """Keep the non-aligned-ceiling precision contract executable offline."""

    # A ceiling need not itself be aligned to the 0.1-ducat input precision.
    # The amount must therefore be selected in raw units before formatting.
    assert _overlimit_amount(860050) == ("860.1", 860100)


def _money_parameters(war_id: str, amount: str) -> dict:
    return {
        "peace_context": {
            "war_id": war_id,
            "direction": "demand",
            "terms": [{
                "action_id": MONEY_ACTION,
                "amount": amount,
                "payer": WAR_RECIPIENT,
                "claimant": WAR_ACTOR,
            }],
        },
    }


def _integer(value: object, *, minimum: int | None = None) -> bool:
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return minimum is None or value >= minimum


def _normalized_amount(amount_raw: int) -> str:
    """Format the bridge's one-decimal normalized amount representation."""

    return f"{amount_raw // 1000}.{(amount_raw % 1000) // 100}"


def _money_parameters_contract(
        parameters: object, amount: str, expected_within_limit: bool) -> bool:
    """Validate requested input and the bridge's normalized actual context."""

    if not isinstance(parameters, dict):
        return False
    requested = parameters.get("requested")
    actual = parameters.get("actual")
    if not isinstance(requested, dict) or not isinstance(actual, dict):
        return False
    requested_context = requested.get("peace_context")
    actual_context = actual.get("peace_context")
    if not isinstance(requested_context, dict) or not isinstance(actual_context, dict):
        return False
    war_id = requested_context.get("war_id")
    if not isinstance(war_id, str):
        return False
    if requested != _money_parameters(war_id, amount):
        return False
    if (actual_context.get("war_id") != war_id
            or actual_context.get("direction") != "demand"):
        return False
    terms = actual_context.get("terms")
    if not isinstance(terms, list):
        return False
    if parameters.get("complete") is not expected_within_limit:
        return False
    if not expected_within_limit:
        return terms == []
    if len(terms) != 1 or not isinstance(terms[0], dict):
        return False
    expected_raw = _amount_raw(amount)
    actual_term = terms[0]
    return (
        actual_term.get("action_id") == MONEY_ACTION
        and actual_term.get("amount") == _normalized_amount(expected_raw)
        and actual_term.get("amount_raw") == expected_raw
        and actual_term.get("payer") == WAR_RECIPIENT
        and actual_term.get("claimant") == WAR_ACTOR)


def _native_money_contract(
        value: object, amount: str, expected_within_limit: bool) -> bool:
    """Validate native money fields and the bridge's normalized parameters."""

    if not isinstance(value, dict) or value.get("family") != "peace":
        return False
    if any(value.get(key) != wanted for key, wanted in (
        ("action_id", MONEY_ACTION), ("actor", WAR_ACTOR),
        ("recipient", WAR_RECIPIENT), ("phase", "initiate"),
    )):
        return False
    parameters = value.get("parameters")
    if not isinstance(parameters, dict):
        return False
    requested = parameters.get("requested")
    if not isinstance(requested, dict):
        return False
    requested_context = requested.get("peace_context")
    if not isinstance(requested_context, dict):
        return False
    war_id = requested_context.get("war_id")
    if not isinstance(war_id, str):
        return False
    if not _money_parameters_contract(parameters, amount, expected_within_limit):
        return False
    money = value.get("native_money")
    if not isinstance(money, dict):
        return False
    if money.get("query_complete") is not True:
        return False
    requested_raw = _amount_raw(amount)
    if (money.get("requested_amount_raw") != requested_raw
            or not _integer(money.get("requested_amount_raw"), minimum=1)
            or money["requested_amount_raw"] % EXPECTED_PRECISION_RAW != 0):
        return False
    if any(money.get(key) != wanted for key, wanted in (
        ("currency_scale", EXPECTED_SCALE),
        ("currency_precision_raw", EXPECTED_PRECISION_RAW),
        ("currency_scale_verified", True),
        ("ceiling_input_raw", EXPECTED_INPUT_CEILING_RAW),
        ("direction", "demand"), ("direction_verified", True),
        ("payer", WAR_RECIPIENT), ("claimant", WAR_ACTOR),
        ("action_copy_verified", True),
    )):
        return False
    if not _integer(money.get("currency_ceiling_raw"), minimum=0):
        return False
    if not all(isinstance(money.get(field), bool) for field in (
            "amount_within_limit", "setter_called",
            "source_readback_matches", "action_copy_verified",
            "parameters_matched")):
        return False
    if money.get("amount_within_limit") is not expected_within_limit:
        return False
    if expected_within_limit:
        if (money.get("setter_called") is not True
                or money.get("source_amount_raw") != requested_raw
                or money.get("action_amount_raw") != requested_raw
                or money.get("source_readback_matches") is not True
                or money.get("parameters_matched") is not True):
            return False
    else:
        if (money.get("setter_called") is not False
                or money.get("source_amount_raw") != 0
                or money.get("action_amount_raw") != 0
                or money.get("source_readback_matches") is not False
                or money.get("parameters_matched") is not False):
            return False
    return True


def _native_money_ceiling(value: object) -> int | None:
    if not isinstance(value, dict) or not isinstance(value.get("native_money"), dict):
        return None
    raw = value["native_money"].get("currency_ceiling_raw")
    return raw if _integer(raw, minimum=0) else None


def _money_evaluation_contract(value: object, *, overlimit: bool) -> bool:
    """Keep preview and aggregate scores separate in public evidence."""

    projection = _evaluation_projection(value)
    if projection is None:
        # An over-limit native branch may omit evaluation entirely.  In that
        # case the public acceptance total must still remain unavailable.
        if overlimit:
            acceptance = value.get("acceptance") if isinstance(value, dict) else None
            if isinstance(acceptance, dict) and acceptance.get("native_total") is not None:
                return False
            costs = value.get("costs") if isinstance(value, dict) else None
            cost_evaluation = (
                costs.get("native_evaluation")
                if isinstance(costs, dict) else None)
            return not (isinstance(cost_evaluation, dict)
                        and cost_evaluation.get("aggregate_score_available") is True)
        return False
    if projection.get("cross_projection_equal") is not True:
        return False
    if overlimit:
        return (
            projection.get("called") is False
            and projection.get("score_available") is False
            and projection.get("native_total") is None
            and projection.get("native_aggregate_score_available") is False
            and projection.get("costs_aggregate_score_available") is False)
    if (projection.get("called") is not True
            or projection.get("score_available") is not True
            or projection.get("native_aggregate_score_available") is not True
            or projection.get("costs_aggregate_score_available") is not True):
        return False
    for field in ("score_raw", "native_total",
                  "native_aggregate_score_raw", "acceptance_native_total",
                  "costs_aggregate_score_raw"):
        if not _integer(projection.get(field)):
            return False
    return True


def _same_public_money_shape(first: object, second: object) -> bool:
    if not isinstance(first, dict) or not isinstance(second, dict):
        return False
    left = first.get("native_money")
    right = second.get("native_money")
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    fields = (
        "currency_scale", "currency_precision_raw",
        "currency_scale_verified", "ceiling_input_raw",
        "currency_ceiling_raw", "amount_within_limit", "setter_called",
        "source_amount_raw", "action_amount_raw", "source_readback_matches",
        "action_copy_verified", "parameters_matched", "direction",
        "direction_verified", "payer", "claimant",
    )
    return all(left.get(field) == right.get(field) for field in fields)


def _native_metadata_indices(path: Path) -> list[dict[str, object]]:
    """Index private metadata records without copying them into public query data."""

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
                if event.get("event") == "native_alliance_reason_provenance":
                    index = event.get("index")
                    if (not isinstance(index, bool) and isinstance(index, int)
                            and index >= 0):
                        records.append({
                            "query_id": event.get("query_id"),
                            "event": event.get("event"),
                            "field": "index",
                            "index": index,
                            "private": event.get("private") is True,
                        })
                for key, value in event.items():
                    if ("metadata" not in key.lower()
                            or "index" not in key.lower()
                            or isinstance(value, bool)
                            or not isinstance(value, int)
                            or value < 0):
                        continue
                    records.append({
                        "query_id": event.get("query_id"),
                        "event": event.get("event"),
                        "field": key,
                        "index": value,
                    })
    except OSError:
        return []
    return records


def _control_is_expected(control: object, expected_date_raw: int) -> bool:
    return control == {
        "date_raw": expected_date_raw,
        "paused_flag": 1,
        "player_slot": 189,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--expected-date-raw", type=int, required=True)
    args = parser.parse_args()
    _offline_contract_assertions()
    installation = args.installation.resolve(strict=True)
    session = ObserverSession(installation, game_exe())
    artifact = _new_artifact(installation.parent, "peace-money-offer-queries")
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
        "execute_call_count": 0,
        "business_submission": False,
        "time_advance_call_count": 0,
        "save_call_count": 0,
        "query_call_count": 0,
        "queries": {},
    }
    log = session.directory / "control-probe.jsonl"
    log_start: int | None = None
    try:
        health = wait_runtime_ready(session, restore_minimized=True)
        if health.get("status") != "ready":
            raise RuntimeError("PEACE_MONEY_QUERY_SESSION_UNREADY")
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
            raise RuntimeError("PEACE_MONEY_QUERY_BASELINE_UNAVAILABLE")
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
                raise RuntimeError("PEACE_MONEY_DISCOVERY_INCOMPLETE")
            report["war_id"] = war_id

            baseline_parameters = {
                "peace_context": {"war_id": war_id, "terms": []},
            }
            report["query_call_count"] += 1
            baseline = api.inspect_diplomatic_action(
                "white_peace", WAR_ACTOR, WAR_RECIPIENT,
                phase="initiate", parameters=baseline_parameters)
            report["queries"]["baseline_white_peace"] = baseline
            _write_json(artifact / "baseline-white-peace.json", baseline)
            if not _public_empty_offer_contract(
                    baseline, WAR_ACTOR, WAR_RECIPIENT, war_id):
                raise RuntimeError("PEACE_MONEY_WHITE_PEACE_BASELINE_INVALID")

            money_queries: dict[str, dict] = {}
            ceilings: dict[str, int] = {}
            for name, amount in CASES:
                params = _money_parameters(war_id, amount)
                report["query_call_count"] += 1
                result = api.inspect_diplomatic_action(
                    MONEY_ACTION, WAR_ACTOR, WAR_RECIPIENT,
                    phase="initiate", parameters=params)
                money_queries[name] = result
                report["queries"][name] = result
                _write_json(artifact / f"{name}.json", result)
                ceiling = _native_money_ceiling(result)
                if ceiling is not None:
                    ceilings[name] = ceiling

            first_ceiling = ceilings.get("money_10_0")
            if first_ceiling is None:
                raise RuntimeError("PEACE_MONEY_FIRST_CEILING_UNAVAILABLE")
            over_amount, over_raw = _overlimit_amount(first_ceiling)
            report["overlimit"] = {
                "based_on_query": "money_10_0",
                "currency_ceiling_raw": first_ceiling,
                "amount": over_amount,
                "amount_raw": over_raw,
            }
            over_parameters = _money_parameters(war_id, over_amount)
            report["query_call_count"] += 1
            overlimit = api.inspect_diplomatic_action(
                MONEY_ACTION, WAR_ACTOR, WAR_RECIPIENT,
                phase="initiate", parameters=over_parameters)
            money_queries["money_overlimit"] = overlimit
            report["queries"]["money_overlimit"] = overlimit
            _write_json(artifact / "money-overlimit.json", overlimit)

        after = _run_snapshots(session, artifact / "after" / "probes")
        control_after = _control_summary(after["control_state"]["snapshot"])
        health_after = session.health()
        report["discovery"] = discovery
        report["baseline"] = baseline
        report["money_queries"] = money_queries
        report["evaluation_observations"] = {
            name: _evaluation_observation(value)
            for name, value in money_queries.items()
        }
        report["after"] = {
            "control": control_after,
            "health": health_after,
            "probes": _public_probe_records(after),
        }
        normal_contracts = {
            name: _native_money_contract(
                money_queries[name], amount, expected_within_limit=True)
            for name, amount in CASES
        }
        over_contract = _native_money_contract(
            money_queries["money_overlimit"], report["overlimit"]["amount"],
            expected_within_limit=False)
        ceiling_values = [
            _native_money_ceiling(money_queries[name])
            for name, _ in CASES + (("money_overlimit", report["overlimit"]["amount"]),)
        ]
        report["checks"] = {
            "white_peace_discovery_contract": _public_context_contract(
                discovery, WAR_ACTOR, WAR_RECIPIENT),
            "white_peace_discovery_one_war": (
                _single_discovered_war_id(
                    discovery, WAR_ACTOR, WAR_RECIPIENT) == war_id),
            "white_peace_baseline_selected_contract": _public_empty_offer_contract(
                baseline, WAR_ACTOR, WAR_RECIPIENT, war_id),
            "white_peace_baseline_war_id_match": (
                baseline.get("selected_war_id") == war_id
                and baseline.get("peace_context", {}).get("war_id") == war_id),
            "normal_money_contracts": all(normal_contracts.values()),
            "overlimit_money_contract": over_contract,
            "repeat_10_public_shape": _same_public_money_shape(
                money_queries.get("money_10_0"),
                money_queries.get("money_10_0_repeat")),
            "ceiling_consistent": (
                all(value is not None for value in ceiling_values)
                and len(set(ceiling_values)) == 1),
            "score_aggregate_separated": all(
                _money_evaluation_contract(money_queries[name], overlimit=False)
                for name, _ in CASES),
            "overlimit_no_score": _money_evaluation_contract(
                money_queries["money_overlimit"], overlimit=True),
            "no_private_identifiers": not _has_private_fields(
                {"discovery": discovery, "baseline": baseline,
                 "money_queries": money_queries}),
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
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        if isinstance(log_start, int):
            native_events = _copy_log_slice(
                log, log_start, artifact / "native-events-slice.jsonl")
            report["native_events"] = native_events
            if native_events.get("status") == "ok":
                report["native_metadata_records"] = _native_metadata_indices(
                    artifact / "native-events-slice.jsonl")
        _write_json(artifact / "report.json", report)
    print(json.dumps({"status": report["status"], "artifact": str(artifact)},
                     ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
