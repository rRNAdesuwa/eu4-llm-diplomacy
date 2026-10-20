"""Inspect trade-power peace terms in one paused operator session."""
from __future__ import annotations

import argparse
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
from work.run_peace_empty_offer_queries import _single_discovered_war_id


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    session = ObserverSession(args.installation, game_exe())
    health = wait_runtime_ready(session, timeout=25, restore_minimized=True)
    write(output / "health-before.json", health)
    if health.get("status") != "ready":
        raise RuntimeError("OBSERVER_NOT_READY")
    log = session.directory / "control-probe.jsonl"
    start = log.stat().st_size
    journal = DurableJournal(output / "queries.sqlite3", experiment_id=session.experiment_id,
                             session_id=session.session_id, global_request_ids=True)
    results: dict[str, dict] = {}
    try:
        api = DiplomacyTools(journal, session)
        actions = api.list_diplomatic_actions(actor="FRA", recipient="ENG", category="peace")
        write(output / "list-result.json", actions)
        discovery = api.inspect_diplomatic_action(action_id="white_peace", actor="FRA",
            recipient="ENG", phase="initiate", parameters={})
        write(output / "discovery-result.json", discovery)
        war_id = _single_discovered_war_id(discovery, "FRA", "ENG")
        if not war_id:
            raise RuntimeError("SINGLE_CURRENT_WAR_REQUIRED")
        trade = {"action_id": "transfer_trade_power", "source": "FRA", "beneficiary": "ENG"}
        money = {"action_id": "demand_ducats", "amount": "1.0", "payer": "FRA", "claimant": "ENG"}
        provinces = {"action_id": "cede_province", "province_ids": [4388, 4111, 4112, 4389],
                     "beneficiary": "ENG"}
        reparations = {"action_id": "war_reparations", "payer": "FRA", "claimant": "ENG"}
        cases = [
            ("trade-demand", "demand", [{"action_id": "transfer_trade_power", "source": "ENG", "beneficiary": "FRA"}]),
            ("trade-offer", "offer", [trade]),
            ("money-four-provinces-trade", "offer", [money, provinces, trade]),
            ("money-five-provinces-trade", "offer", [money, {**provinces, "province_ids": [4388, 4111, 4112, 4389, 4118]}, trade]),
            ("all-four-term-kinds", "offer", [money, provinces, reparations, trade]),
        ]
        for name, direction, terms in cases:
            arguments = {"action_id": "transfer_trade_power", "actor": "FRA", "recipient": "ENG",
                "phase": "initiate", "parameters": {"peace_context": {
                    "war_id": war_id, "direction": direction, "terms": terms}}}
            write(output / f"{name}-input.json", arguments)
            result = api.inspect_diplomatic_action(**arguments)
            write(output / f"{name}-result.json", result)
            results[name] = result
    finally:
        journal.close()
    health_after = session.health()
    write(output / "health-after.json", health_after)
    with log.open("rb") as stream:
        stream.seek(start)
        raw = stream.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise RuntimeError("NATIVE_SLICE_LIMIT")
    (output / "native-events-slice.jsonl").write_bytes(raw)
    checks = {
        "ready_before_after": health_after.get("status") == "ready",
        "paused_date_unchanged": health.get("date_raw") == health_after.get("date_raw"),
        "all_cases_returned": len(results) == 5,
        "no_business_submission": all(value.get("submitted") is not True for value in results.values()),
        "all_queries_have_native_legality": all(value.get("legality", {}).get("status")
            in ("available", "unavailable") for value in results.values()),
    }
    report = {"status": "passed" if all(checks.values()) else "failed", "checks": checks,
        "session_id": session.session_id, "installation": str(args.installation.resolve()),
        "date_raw": health.get("date_raw"), "business_submission": False,
        "cases": {key: {"legality": value.get("legality"), "acceptance": value.get("acceptance")}
                  for key, value in results.items()}}
    write(output / "report.json", report)
    print(json.dumps({"status": report["status"], "report": str(output / "report.json")}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
