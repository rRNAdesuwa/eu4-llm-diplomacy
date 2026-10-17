"""Send one legal native test packet without a bridge authority seed."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from work.local_config import game_exe
from work.observer_runtime_ready import wait_runtime_ready
from work.run_alliance_execution import _copy_log_slice, _write_json
from work.run_alliance_inbound_response import control_snapshot
from work.validate_alliance_queries import PROBE_SPECS, _run_probe
from work.validate_alliance_reload import _diplomat_semantics

FULL_DIPLOMAT_SNAPSHOT_ACTIONS = ("improve_relations", "build_spy_network", "stop_building_spy_network",
                      "proclaim_guarantee", "revoke_guarantee", "support_independence", "revoke_support_independence",
                      "ask_military_access", "cancel_military_access", "send_insult", "scornful_insult",
                      "offer_vassalization", "cancel_vassalization")

_INSULT_ACTIONS = ("send_insult", "scornful_insult")
_INSULT_STATE_FIELDS = (
    "family", "action_id", "insult_id", "insult_parameter_selected",
    "insult_state_verified", "insult_active", "opinion_modifier_raw",
    "actor_prestige_raw", "prestige_cost_raw",
)


def _insult_state(query: object) -> dict[str, object]:
    """Keep the native Insult state fields bounded and directly comparable."""

    if not isinstance(query, dict):
        return {field: None for field in _INSULT_STATE_FIELDS}
    return {field: query.get(field) for field in _INSULT_STATE_FIELDS}


def _insult_query_complete(query: object, action_id: str, insult_id: int) -> bool:
    """Require a family-specific native state before comparing it."""

    if not isinstance(query, dict):
        return False
    cost = query.get("prestige_cost_raw")
    return (
        query.get("family") == "insult"
        and query.get("action_id") == action_id
        and query.get("insult_id") == insult_id
        and query.get("insult_parameter_selected") is True
        and query.get("insult_state_verified") is True
        and type(query.get("insult_active")) is bool
        and isinstance(query.get("opinion_modifier_raw"), int)
        and not isinstance(query.get("opinion_modifier_raw"), bool)
        and isinstance(query.get("actor_prestige_raw"), int)
        and not isinstance(query.get("actor_prestige_raw"), bool)
        and (cost is None or (isinstance(cost, int) and not isinstance(cost, bool)))
    )


_VASSAL_STATE_FIELDS = (
    "family", "action_id", "vassal_active", "vassal_state_verified",
    "relationship_state", "prestige_raw", "cancel_prestige_delta_raw",
    "cancel_prestige_effect_allowed", "actor_is_overlord", "actor_is_subject",
    "subject_type",
)


def _vassal_state(query: object) -> dict[str, object]:
    """Keep native Vassalization relation and cost fields bounded."""

    if not isinstance(query, dict):
        return {field: None for field in _VASSAL_STATE_FIELDS}
    return {field: query.get(field) for field in _VASSAL_STATE_FIELDS}


def _vassal_query_complete(query: object, action_id: str,
                           recipient: str) -> bool:
    """Require verified relation state and raw prestige before comparing."""

    if not isinstance(query, dict):
        return False
    relationship = query.get("relationship_state")
    active = query.get("vassal_active")
    prestige = query.get("prestige_raw")
    return (
        query.get("family") == "vassalization"
        and query.get("action_id") == action_id
        and query.get("actor") == "FRA"
        and query.get("recipient") == recipient
        and type(active) is bool
        and query.get("vassal_state_verified") is True
        and isinstance(relationship, dict)
        and relationship.get("vassal_active") is active
        and relationship.get("complete") is True
        and type(prestige) is int
        and query.get("submitted", False) is False
    )

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--action", choices=("dissolve_alliance", "offer_alliance",
                        "offer_royal_marriage", "break_royal_ties", "improve_relations",
                        "build_spy_network", "stop_building_spy_network",
                        "proclaim_guarantee", "revoke_guarantee", "support_independence",
                        "revoke_support_independence", "ask_military_access", "cancel_military_access",
                        "send_insult", "scornful_insult", "offer_vassalization",
                        "cancel_vassalization"), required=True)
    parser.add_argument("--route", choices=("transport", "direct_entry"), default="transport")
    parser.add_argument("--recipient", help="Support, Military Access, Insult, or Vassalization target; defaults HOL or SAV")
    parser.add_argument("--insult-id", type=int,
                        help="Nonnegative native candidate for scornful_insult")
    args = parser.parse_args()
    support = args.action in ("support_independence", "revoke_support_independence")
    military = args.action in ("ask_military_access", "cancel_military_access")
    insult = args.action in _INSULT_ACTIONS
    vassal = args.action in ("offer_vassalization", "cancel_vassalization")
    if args.recipient is not None and (not (support or military or insult or vassal) or len(args.recipient) != 3
            or not args.recipient.isascii() or not args.recipient.isupper() or not args.recipient.isalpha()):
        parser.error("--recipient requires a three-letter target for Support, Military Access, Insult, or Vassalization")
    if args.action == "send_insult" and args.insult_id is not None:
        parser.error("send_insult uses the native ordinary Insult ID -1; omit --insult-id")
    if args.action == "scornful_insult" and (
            args.insult_id is None or args.insult_id < 0 or args.insult_id > 2147483647):
        parser.error("scornful_insult requires --insult-id in 0..2147483647")
    if not insult and args.insult_id is not None:
        parser.error("--insult-id is only valid with scornful_insult")
    if args.route == "direct_entry" and args.action not in FULL_DIPLOMAT_SNAPSHOT_ACTIONS:
        parser.error("direct_entry requires an implemented action fixture")
    installation = args.installation.resolve(strict=True)
    directory = installation.parent
    artifact = directory / ("authority-test-" + uuid.uuid4().hex)
    artifact.mkdir()
    session = ObserverSession(installation, game_exe())
    log = directory / "control-probe.jsonl"
    start = log.stat().st_size
    report = {"status": "unknown", "action_id": args.action, "session_id": session.session_id,
              "dispatch_route": args.route, "native_ai_self_choice_evidence": False, "checks": {}}
    fixture = {
        "dissolve_alliance": ("PRO", "UNAUTHORIZED_FRA_DISSOLVE", "FRA_DISSOLVE_PRO"),
        "offer_alliance": ("SAV", "UNAUTHORIZED_FRA_OFFER", "FRA_OFFER_SAV"),
        "offer_royal_marriage": ("SAV", "UNAUTHORIZED_FRA_ROYAL_OFFER", "FRA_ROYAL_OFFER_SAV"),
        "break_royal_ties": ("PRO", "UNAUTHORIZED_FRA_ROYAL_BREAK", "FRA_ROYAL_BREAK_PRO"),
        "improve_relations": ("SAV", "UNAUTHORIZED_FRA_IMPROVE_TASK",
            "FRA_IMPROVE_SAV_DIRECT" if args.route == "direct_entry" else "FRA_IMPROVE_SAV"),
        "build_spy_network": ("SAV", "UNAUTHORIZED_FRA_SPY_TASK",
            "FRA_SPY_SAV_DIRECT" if args.route == "direct_entry" else "FRA_SPY_SAV"),
        "stop_building_spy_network": ("SAV", "UNAUTHORIZED_FRA_SPY_TASK",
            "FRA_STOP_SPY_SAV_DIRECT" if args.route == "direct_entry" else "FRA_STOP_SPY_SAV"),
        "proclaim_guarantee": ("SAV", "UNAUTHORIZED_FRA_GUARANTEE",
            "FRA_GUARANTEE_SAV_DIRECT" if args.route == "direct_entry" else "FRA_GUARANTEE_SAV"),
        "revoke_guarantee": ("SAV", "UNAUTHORIZED_FRA_GUARANTEE",
            "FRA_REVOKE_GUARANTEE_SAV_DIRECT" if args.route == "direct_entry" else "FRA_REVOKE_GUARANTEE_SAV"),
        "support_independence": (args.recipient or "HOL", "UNAUTHORIZED_FRA_SUPPORT_OFFER",
            "FRA_SUPPORT_DIRECT" if args.route == "direct_entry" else "FRA_SUPPORT"),
        "revoke_support_independence": (args.recipient or "HOL", "UNAUTHORIZED_FRA_SUPPORT_REVOKE",
            "FRA_REVOKE_SUPPORT_DIRECT" if args.route == "direct_entry" else "FRA_REVOKE_SUPPORT"),
        "ask_military_access": (args.recipient or "SAV", "UNAUTHORIZED_FRA_MILITARY_ACCESS_REQUEST",
            "FRA_MILITARY_ACCESS_DIRECT" if args.route == "direct_entry" else "FRA_MILITARY_ACCESS"),
        "cancel_military_access": (args.recipient or "SAV", "UNAUTHORIZED_FRA_MILITARY_ACCESS_CANCEL",
            "FRA_CANCEL_MILITARY_ACCESS_DIRECT" if args.route == "direct_entry" else "FRA_CANCEL_MILITARY_ACCESS"),
        "send_insult": (args.recipient or "SAV", "UNAUTHORIZED_FRA_INSULT",
            "FRA_INSULT_DIRECT" if args.route == "direct_entry" else "FRA_INSULT"),
        "scornful_insult": (args.recipient or "SAV", "UNAUTHORIZED_FRA_INSULT",
            "FRA_INSULT_DIRECT" if args.route == "direct_entry" else "FRA_INSULT"),
        "offer_vassalization": (args.recipient or "SAV", "UNAUTHORIZED_FRA_VASSALIZATION_OFFER",
            "FRA_VASSALIZATION_DIRECT_WITHOUT_AUTHORITY"
            if args.route == "direct_entry" else "FRA_VASSALIZATION_WITHOUT_AUTHORITY"),
        "cancel_vassalization": (args.recipient or "SAV", "UNAUTHORIZED_FRA_VASSALIZATION_CANCEL",
            "FRA_CANCEL_VASSALIZATION_DIRECT_WITHOUT_AUTHORITY"
            if args.route == "direct_entry" else "FRA_CANCEL_VASSALIZATION_WITHOUT_AUTHORITY"),
    }[args.action]
    recipient, expected, packet = fixture
    insult_id = -1 if args.action == "send_insult" else args.insult_id
    parameters = {} if not insult else {"insult_id": insult_id} if args.action == "scornful_insult" else {}
    try:
        health = wait_runtime_ready(session, restore_minimized=True)
        before = control_snapshot(session.record["pid"], artifact / "before-control.json")
        diplomat_spec = next(spec for spec in PROBE_SPECS if spec.name == "diplomats")
        before_diplomats = _run_probe(diplomat_spec, session.record["pid"],
            artifact / "before-diplomats.json") if args.action in FULL_DIPLOMAT_SNAPSHOT_ACTIONS else None
        if health.get("status") != "ready" or before.get("player_slot") != 189 or before.get("paused_flag") != 1:
            raise RuntimeError("POR_PAUSED_READY_BASELINE_REQUIRED")
        if vassal:
            capabilities = session.installation_capabilities()
            report["capabilities"] = sorted(capabilities)
            required = {"native_vassalization_query", "native_vassalization_submission"}
            if not required.issubset(capabilities):
                raise RuntimeError("VASSALIZATION_CAPABILITY_MISSING")
        with DurableJournal(artifact / "diplomacy.sqlite3", session.experiment_id, session.session_id) as journal:
            api = DiplomacyTools(journal, session)
            first = api.inspect_diplomatic_action(
                args.action, "FRA", recipient, parameters=parameters)
            if first.get("legality", {}).get("status") != "available":
                raise RuntimeError("TEST_REQUIRES_LEGAL_NATIVE_ACTION")
            if insult:
                token = f"TEST_ONLY {packet}_WITHOUT_AUTHORITY {recipient} {insult_id}\n"
            elif vassal:
                token = f"TEST_ONLY {packet} {recipient}\n"
            else:
                token = f"TEST_ONLY {packet}_WITHOUT_AUTHORITY" + (f" {recipient}" if support or military else "") + "\n"
            with (directory / "diplomacy-authority-test.req").open("xb") as stream:
                stream.write(token.encode("ascii"))
            deadline = time.monotonic() + 10
            seen = []
            while time.monotonic() < deadline:
                with log.open("rb") as stream:
                    stream.seek(start)
                    data = stream.read(1024 * 1024)
                seen = []
                for line in data.splitlines():
                    try:
                        event = json.loads(line)
                    except (ValueError, UnicodeDecodeError):
                        continue
                    if isinstance(event, dict) and event.get("session_id") == session.session_id:
                        seen.append(event)
                if (any(e.get("event") == "native_alliance_authority_test_dispatched" for e in seen)
                        and any(e.get("reason") == expected for e in seen)):
                    break
                time.sleep(0.1)
            after_query = api.inspect_diplomatic_action(
                args.action, "FRA", recipient, parameters=parameters)
        after = control_snapshot(session.record["pid"], artifact / "after-control.json")
        after_diplomats = _run_probe(diplomat_spec, session.record["pid"],
            artifact / "after-diplomats.json") if args.action in FULL_DIPLOMAT_SNAPSHOT_ACTIONS else None
        dispatched = [e for e in seen if e.get("event") == "native_alliance_authority_test_dispatched"]
        rejected = [e for e in seen if e.get("event") == "native_alliance_execution_rejected" and e.get("reason") == expected]
        report.update({"before": before, "after": after, "before_query": first,
                       "after_query": after_query, "dispatched": dispatched, "gate_rejection": rejected})
        if insult:
            report["insult"] = {
                "insult_id": insult_id,
                "parameters": parameters,
                "before": _insult_state(first),
                "after": _insult_state(after_query),
            }
        if vassal:
            report["vassalization"] = {
                "recipient": recipient,
                "before": _vassal_state(first),
                "after": _vassal_state(after_query),
            }
        report["checks"] = {
            "native_packet_dispatched_without_seed": len(dispatched) == 1
                and dispatched[0].get("dispatcher_accepted") is (args.route == "transport")
                and dispatched[0].get("dispatch_route", "transport") == args.route
                and dispatched[0].get("authority_seed_created") is False
                and dispatched[0].get("action_id") == args.action
                and dispatched[0].get("recipient") == recipient,
            "blocked_at_command_entry": len(rejected) == 1 and rejected[0].get("submitted") is False,
            "relation_visibility_unchanged": first.get("visibility") == after_query.get("visibility"),
            "diplomat_availability_unchanged": first.get("resources") == after_query.get("resources"),
            "por_paused_same_date": before.get("date_raw") == after.get("date_raw")
                and after.get("player_slot") == 189 and after.get("paused_flag") == 1,
            "health_ready": session.health().get("status") == "ready",
        }
        if insult:
            before_insult = _insult_state(first)
            after_insult = _insult_state(after_query)
            report["checks"]["insult_query_state_complete"] = (
                _insult_query_complete(first, args.action, insult_id)
                and _insult_query_complete(after_query, args.action, insult_id)
            )
            report["checks"]["insult_state_unchanged"] = (
                report["checks"]["insult_query_state_complete"]
                and before_insult == after_insult
            )
        if before_diplomats is not None and after_diplomats is not None:
            report["diplomats"] = {"before": before_diplomats, "after": after_diplomats}
            report["checks"]["diplomat_tasks_unchanged"] = (
                before_diplomats["snapshot_completeness"]["complete"] is True
                and after_diplomats["snapshot_completeness"]["complete"] is True
                and _diplomat_semantics(before_diplomats["snapshot"])
                    == _diplomat_semantics(after_diplomats["snapshot"]))
        if args.action in ("proclaim_guarantee", "revoke_guarantee"):
            report["checks"]["guarantee_relationship_unchanged"] = (
                first.get("relationship_state", {}).get("complete") is True
                and first.get("relationship_state") == after_query.get("relationship_state"))
        if support:
            report["checks"]["support_relationship_unchanged"] = (
                first.get("relationship_state", {}).get("complete") is True
                and first.get("relationship_state") == after_query.get("relationship_state"))
        if military:
            report["checks"]["military_access_relationship_unchanged"] = (
                first.get("relationship_state", {}).get("complete") is True
                and first.get("relationship_state") == after_query.get("relationship_state"))
        if vassal:
            report["checks"]["vassal_query_state_complete"] = (
                _vassal_query_complete(first, args.action, recipient)
                and _vassal_query_complete(after_query, args.action, recipient)
            )
            report["checks"]["vassal_state_unchanged"] = (
                report["checks"]["vassal_query_state_complete"]
                and _vassal_state(first) == _vassal_state(after_query)
            )
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        report["native_events"] = _copy_log_slice(log, start, artifact / "native-events.jsonl")
        _write_json(artifact / "report.json", report)
    print(json.dumps({"status": report["status"], "checks": report["checks"], "artifact": str(artifact)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
