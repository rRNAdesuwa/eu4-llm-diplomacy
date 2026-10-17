"""Record live Alliance factor identifiers through the public inspection API."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from work.local_config import game_exe
from work.observer_runtime_ready import wait_runtime_ready
from work.run_alliance_execution import _copy_log_slice, _sha256_file, _write_json
from work.run_alliance_inbound_response import control_snapshot

FACTOR_IDS = {
    "DIPLO_ENEMY_ALLIES", "DIPLO_OPINION", "DIPLO_DIPLOMATIC_REP",
    "DIPLO_ARMY_SIZE", "DIPLO_NAVY_SIZE", "DIPLO_ATTITUDE",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", required=True, type=Path)
    parser.add_argument("--native-text-codec", choices=("utf8", "eu4_escape"))
    args = parser.parse_args()
    installation = args.installation.resolve(strict=True)
    directory = installation.parent
    artifact = directory / ("reason-metadata-validation-" + uuid.uuid4().hex)
    artifact.mkdir()
    report = {"status": "unknown", "checks": {}, "inspections": {}}
    log = directory / "control-probe.jsonl"
    log_start = log.stat().st_size
    try:
        session = ObserverSession(installation, game_exe())
        runtime_health = wait_runtime_ready(session, restore_minimized=True)
        if args.native_text_codec:
            # Operator configuration, never accepted as an LLM action argument.
            session.native_text_codec = args.native_text_codec
        report.update({"session_id": session.session_id,
                       "installation": _sha256_file(installation),
                       "manifest": _sha256_file(directory / "build-manifest.json"),
                       "operator_native_text_codec": session.native_text_codec})
        before = control_snapshot(int(session.record["pid"]), artifact / "before-control.json")
        report["before"] = {"health": runtime_health, "control": before}
        with DurableJournal(artifact / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            for recipient in ("SAV", "LIT"):
                report["inspections"][recipient] = api.inspect_diplomatic_action(
                    "offer_alliance", "FRA", recipient)
        after = control_snapshot(int(session.record["pid"]), artifact / "after-control.json")
        report["after"] = {"health": session.health(), "control": after}
        checks = report["checks"]
        checks["metadata_capability_acknowledged"] = (
            "native_alliance_reason_metadata" in session.installation_capabilities())
        for recipient, inspection in report["inspections"].items():
            items = inspection.get("acceptance", {}).get("items", [])
            expected = FACTOR_IDS if recipient == "SAV" else (
                FACTOR_IDS - {"DIPLO_ENEMY_ALLIES"}) | {"DIPLO_BORDER_DISTANCE"}
            checks[recipient + "_six_identified_factors"] = (
                len(items) == 6 and {row.get("native_identifier") for row in items} == expected
                and all(row.get("identifier_verified") is True
                        and row.get("native_value_verified") is True
                        and row.get("identity_source") == "native_localization_key"
                        and row.get("value_representation") == "signed_int32"
                        and row.get("value_normalized") is False for row in items))
        checks["query_preserves_por_pause_and_date"] = (
            before.get("player_slot") == after.get("player_slot") == 189
            and before.get("paused_flag") == after.get("paused_flag") == 1
            and before.get("date_raw") == after.get("date_raw"))
        checks["health_ready"] = report["after"]["health"].get("status") == "ready"
        report["status"] = "passed" if all(checks.values()) else "failed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        report["native_events"] = _copy_log_slice(log, log_start, artifact / "native-events.jsonl")
        _write_json(artifact / "report.json", report)
    print(json.dumps({"status": report["status"], "checks": report["checks"],
                      "artifact": str(artifact)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
