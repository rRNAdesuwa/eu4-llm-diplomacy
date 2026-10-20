"""Batch both directions of Trust/Men preflight before choosing test scenes."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.favor_resources import validate_query
from work.local_config import game_exe
from work.observer_runtime_ready import wait_runtime_ready
from work.run_alliance_inbound_response import control_snapshot
from work.run_peace_consequence_queries import _copy_bounded_slice, _write_json

ACTIONS = {"trade_favors_for_trust": "trust", "trade_favors_for_men": "men"}
_MAX_NATIVE_LINE = 2 * 1024 * 1024


def _private_preflight(native: object, kind: str) -> dict:
    if not isinstance(native, dict) or native.get("error_code"):
        return {"status": "unknown", "resource_valid": False}
    resource_valid = (validate_query(native.get("native_favor_trade"))
                      and native["native_favor_trade"]["kind"] == kind)
    resource_complete = (resource_valid and native["native_favor_trade"]["complete"] is True
                         and native["native_favor_trade"]["amount_readable"] is True)
    gates = {key: native.get(key) for key in (
        "native_visibility", "common_action_gate", "display_predicate",
        "initiation_gate", "tooltip_gate", "native_validity")}
    complete = (resource_complete and native.get("full_rules_complete") is True
                and all(isinstance(value, bool) for value in gates.values())
                and native.get("diplomat_context_readable") is True)
    diplomat_ok = (native.get("diplomat_required") is False
                   or type(native.get("available_diplomat_count")) is int
                   and native["available_diplomat_count"] > 0)
    return {"status": ("available" if all(gates.values()) and diplomat_ok
                       else "unavailable") if complete else "unknown",
            "resource_valid": resource_valid, "resource_complete": resource_complete, "gates": gates,
            "diplomat_required": native.get("diplomat_required"),
            "available_diplomat_count": native.get("available_diplomat_count"),
            "diagnostic_readable": native.get("diagnostic_readable"),
            "native_diagnostic_hex": native.get("native_diagnostic_hex")}


def _read_native_events(path: Path) -> list[dict]:
    """Read only the bounded JSONL slice emitted for one query."""

    events: list[dict] = []
    with path.open("rb") as stream:
        while True:
            line = stream.readline(_MAX_NATIVE_LINE + 1)
            if not line:
                break
            if len(line) > _MAX_NATIVE_LINE:
                continue
            try:
                value = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                events.append(value)
    return events


def _select_raw_event(events: list[dict], session_id: str, action: str,
                      actor: str, recipient: str) -> dict:
    matches = [event for event in events
               if event.get("event") == "native_alliance_inspection"
               and event.get("session_id") == session_id
               and event.get("action_id") == action
               and event.get("actor") == actor
               and event.get("recipient") == recipient
               and event.get("phase") == "initiate"]
    if len(matches) != 1:
        raise ValueError(
            f"expected one raw native event for {action} {actor}->{recipient}, "
            f"found {len(matches)}")
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--targets", nargs="+", default=["PAP", "SAV", "LIT", "GEN"])
    parser.add_argument("--actions", choices=tuple(ACTIONS), nargs="+", default=list(ACTIONS))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    session = ObserverSession(args.installation.resolve(), game_exe())
    api = DiplomacyTools(None, session)
    log = session.directory / "control-probe.jsonl"
    report = {"status": "running", "session_id": session.session_id,
              "installation": str(args.installation.resolve()), "cases": [],
              "business_submission": False}
    try:
        report["health"] = wait_runtime_ready(session, timeout=25, restore_minimized=True)
        if report["health"]["status"] != "ready":
            raise ValueError("Session is not ready")
        before = control_snapshot(int(session.record["pid"]), args.output / "control-before.json")
        report["before"] = before
        if before["paused_flag"] != 1:
            raise ValueError("Preflight requires the paused experimental scene")
        _write_json(args.output / "catalog.json", api.list_diplomatic_actions())
        for action in args.actions:
            kind = ACTIONS[action]
            for target in args.targets:
                for actor, recipient in (("FRA", target), (target, "FRA")):
                    private = actor != "FRA"
                    directory = args.output / "cases" / f"{kind}_{actor}_{recipient}"
                    directory.mkdir(parents=True)
                    offset = log.stat().st_size
                    normalized = None
                    if private:
                        # Operator-only source selection. This does not grant
                        # another country to the controlled LLM API.
                        session.inspect_alliance(
                            action, actor, recipient, "initiate",
                            frozenset({f"native_favor_{kind}_query"}),
                            allow_recipient_scope=True)
                        public = None
                    else:
                        public = api.inspect_diplomatic_action(action, actor, recipient)
                    native = None
                    raw_path = directory / "native.jsonl"
                    raw_slice = _copy_bounded_slice(log, offset, raw_path)
                    # Always use the raw event from native.jsonl as the source
                    # of truth.  ObserverSession.inspect_alliance returns its
                    # semantic projection for operator-private calls, which
                    # must never be mistaken for the native event schema.
                    native = _select_raw_event(
                        _read_native_events(raw_path), session.session_id,
                        action, actor, recipient)
                    normalized = ObserverSession._semantic_inspection(
                        native, {}, codec=session.native_text_codec)
                    preflight = _private_preflight(native, kind)
                    _write_json(directory / "native-event.json", native)
                    _write_json(directory / "normalized.json", normalized)
                    if public is not None:
                        _write_json(directory / "public.json", public)
                    report["cases"].append({
                        "action_id": action, "actor": actor, "recipient": recipient,
                        "operator_private_scope": private, "preflight": preflight,
                        "public_legality": public["legality"] if public else None,
                        "public_resources": public.get("favor_trade") if public else None,
                        "normalized": normalized,
                        "native_slice": raw_slice})
                    _write_json(args.output / "report.json", report)
        after = control_snapshot(int(session.record["pid"]), args.output / "control-after.json")
        report["after"] = after
        report["checks"] = {
            "same_paused_date": all(before[key] == after[key]
                                    for key in ("date_raw", "paused_flag", "player_slot")),
            "all_resources_valid": all(row["preflight"]["resource_valid"] for row in report["cases"]),
            "all_rule_results_known": all(row["preflight"]["status"] != "unknown"
                                          for row in report["cases"]),
            "all_public_results_consumed": all(
                row["public_legality"]["status"] in ("available", "unavailable")
                and isinstance(row["public_resources"], dict)
                for row in report["cases"] if not row["operator_private_scope"]),
        }
        report["status"] = "passed" if all(report["checks"].values()) else "incomplete"
    except Exception as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
    _write_json(args.output / "report.json", report)
    print(json.dumps({key: report.get(key) for key in ("status", "checks", "error")}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
