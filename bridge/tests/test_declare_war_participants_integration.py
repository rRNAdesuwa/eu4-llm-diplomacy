from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from bridge.declarewar_participants import PARTICIPANT_EVENT
from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal


ROOT = Path(__file__).parent
DEFAULT_FIXTURE = ROOT / "fixtures" / "declare_war_r36_native_inspection.json"
CANDIDATE_FIXTURE = ROOT / "fixtures" / "declare_war_r36_candidate_inspection.json"
EXECUTION_FIXTURE = ROOT / "fixtures" / "declare_war_r37_execution_contract.json"


def _installation(root: Path, *, participants: bool = True,
                  submission: bool = True) -> Path:
    session_id = "declare-participants-session"
    installation = root / "installation.json"
    installation.write_text(json.dumps({
        "experiment_id": "declare-participants-contract",
        "session_id": session_id,
        "pid": 1,
        "creation_filetime": 2,
        "dll_sha256": "fixture-dll",
        "controlled_countries": ["FRA"],
        "installation_returncode": 0,
        "native_text_codec": "eu4_escape",
    }), encoding="utf-8")
    ack = {
        "event": "diplomacy_observer_installed",
        "session_id": session_id,
        "native_declare_war_query": True,
    }
    if participants:
        ack["native_declare_war_participants"] = True
    if submission:
        ack["native_declare_war_submission"] = True
    (root / "control-probe.jsonl").write_text(
        json.dumps(ack) + "\n", encoding="utf-8")
    return installation


def _row(index: int, country: str, side: str, *, selected: bool,
         promise: bool) -> dict:
    return {
        "event": PARTICIPANT_EVENT,
        "query_id": "query-placeholder",
        "session_id": "declare-participants-session",
        "actor": "FRA",
        "recipient": "POR",
        "date_raw": 56465136,
        "index": index,
        "side": side,
        "country": country,
        "related_country": "POR" if side == "attacker" else "FRA",
        "join_reason_raw": 7 + index,
        "automatic": False,
        "selected": selected,
        "promise_land": promise,
        "promise_available": True,
        "legality_checked": True,
        "native_legality": True,
        "diagnostic_hex": "636f6e74657874",
        "diagnostic_readable": True,
        "diagnostic_truncated": False,
        "score_available": True,
        "native_total_raw": 4,
        "acceptance_threshold_raw": 1,
        "reason_count": 0,
        "reasons": [],
        "reasons_complete": True,
        "context_complete": True,
    }


def _selected_event() -> tuple[dict, list[dict]]:
    event = json.loads(DEFAULT_FIXTURE.read_text(encoding="utf-8"))["events"]["default"]
    candidate = json.loads(CANDIDATE_FIXTURE.read_text(
        encoding="utf-8"))["event"]["candidates"][0]
    candidate.update({
        "native_metadata_hex": "63625f636f7265",
        "metadata_group_raw": 24,
        "casus_belli_key": "cb_core",
        "casus_belli_key_verified": True,
        "target_province_id": 177,
        "province_identifier_verified": True,
        "beneficiary_tag": "FRA",
        "beneficiary_identifier_verified": True,
    })
    event.update({
        "recipient": "POR",
        "candidate_enumeration_called": True,
        "candidate_enumeration_complete": True,
        "candidate_native_count": 1,
        "candidate_capture_truncated": False,
        "candidate_cleanup_verified": True,
        "candidates": [candidate],
        "selection_requested": True,
        "selection_matched": True,
        "selection_match_count": 1,
        "requested_casus_belli": "cb_core",
        "requested_province_id": 177,
        "requested_beneficiary": "FRA",
        "parameter_context_complete": True,
        "candidate_context_complete": True,
        "full_rules_complete": True,
        "native_default_payload": False,
    })
    rows = [_row(0, "ENG", "attacker", selected=True, promise=True),
            _row(1, "SCO", "defender", selected=True, promise=False)]
    return event, rows


class DeclareWarParticipantsIntegrationTests(unittest.TestCase):
    def test_query19_binds_rows_and_projects_selection_allowed(self) -> None:
        event, rows = _selected_event()
        parameters = {
            "casus_belli": "cb_core",
            "war_goal": {"province_id": 177, "beneficiary": "FRA"},
            "call_allies": ["ENG"],
            "promise_land_to": ["ENG"],
            "co_belligerents": ["SCO"],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(_installation(root), root / "eu4.exe")
            request = root / "diplomacy-query.request"
            log = root / "control-probe.jsonl"
            errors: list[BaseException] = []

            def writer() -> None:
                try:
                    deadline = time.monotonic() + 2
                    while not request.exists() and time.monotonic() < deadline:
                        time.sleep(0.001)
                    self.assertTrue(request.exists())
                    fields = request.read_text(encoding="ascii").strip().split()
                    self.assertEqual("EU4DIP_QUERY19", fields[0])
                    self.assertEqual(14, len(fields))
                    self.assertEqual(["ENG", "ENG", "SCO"], fields[11:14])
                    request.unlink(missing_ok=True)
                    final = copy.deepcopy(event)
                    final.update({
                        "query_id": fields[2],
                        "session_id": session.session_id,
                        "date_raw": int(fields[6]),
                        "native_participants": {
                            "called": True,
                            "complete": True,
                            "selection_applied": True,
                            "selection_allowed": True,
                            "action_unchanged": True,
                            "candidate_count": len(rows),
                            "requested_call_allies_csv": "ENG",
                            "requested_promise_land_to_csv": "ENG",
                            "requested_co_belligerents_csv": "SCO",
                        },
                    })
                    with log.open("a", encoding="utf-8", newline="\n") as stream:
                        for row in rows:
                            row = {**row, "query_id": fields[2],
                                   "session_id": session.session_id,
                                   "date_raw": int(fields[6])}
                            stream.write(json.dumps(row) + "\n")
                        stream.write(json.dumps(final) + "\n")
                except BaseException as exc:
                    errors.append(exc)

            thread = threading.Thread(target=writer)
            thread.start()
            ready = {"status": "ready", "state_id": "ready",
                     "date_raw": event["date_raw"], "reasons": [],
                     "complete": True}
            with patch.object(session, "health", return_value=ready), \
                    patch("bridge.diplomacy.probe_identity",
                          return_value={"session_id": session.session_id}):
                result = session.inspect_declare_war(
                    "declare_war", "FRA", "POR", "initiate", parameters)
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual([], errors)
        self.assertNotEqual("QUERY_NATIVE_RESULT_INVALID", result.get("error_code"))
        self.assertTrue(result["native_rule_components"]["full_rules_complete"])
        self.assertIn("participants", result)
        self.assertEqual(["ENG"], result["participants"]["selection"]["call_allies"])
        self.assertTrue(result["participants"]["selection"]["allowed"])
        self.assertTrue(result["participants"]["complete"])

    def test_participant_capability_is_required_for_nonempty_selection(self) -> None:
        parameters = {
            "casus_belli": "cb_core",
            "war_goal": {"province_id": 177, "beneficiary": "FRA"},
            "call_allies": ["ENG"],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(
                _installation(root, participants=False), root / "eu4.exe")
            result = session.inspect_declare_war(
                "declare_war", "FRA", "POR", "initiate", parameters)
        self.assertEqual(
            "NATIVE_DECLARE_WAR_PARTICIPANTS_CAPABILITY_MISSING",
            result["error_code"])

    def test_exec4_echoes_all_three_csv_lists_and_old_exec3_stays_unchanged(self) -> None:
        fixture = json.loads(EXECUTION_FIXTURE.read_text(encoding="utf-8"))
        parameters = {
            "casus_belli": "cb_core",
            "war_goal": {"province_id": 177, "beneficiary": "FRA"},
            "call_allies": ["ENG"],
            "promise_land_to": ["ENG"],
            "co_belligerents": ["SCO"],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(_installation(root), root / "eu4.exe")
            request = root / "diplomacy-execute.req"
            log = root / "control-probe.jsonl"
            errors: list[BaseException] = []

            def writer() -> None:
                try:
                    deadline = time.monotonic() + 2
                    while not request.exists() and time.monotonic() < deadline:
                        time.sleep(0.001)
                    self.assertTrue(request.exists())
                    fields = request.read_text(encoding="ascii").strip().split("|")
                    self.assertEqual("EU4DIP_EXEC4", fields[0])
                    self.assertEqual(15, len(fields))
                    self.assertEqual(["ENG", "ENG", "SCO"], fields[12:15])
                    request.unlink(missing_ok=True)
                    submission = {**fixture["submission"],
                                  "request_id": fields[1],
                                  "session_id": session.session_id,
                                  "date_raw": int(fields[4]),
                                  "recipient": "POR",
                                  "casus_belli": "cb_core",
                                  "war_goal_province": 177,
                                  "war_goal_beneficiary": "FRA",
                                  "call_allies_csv": "ENG",
                                  "promise_land_to_csv": "ENG",
                                  "co_belligerents_csv": "SCO"}
                    with log.open("a", encoding="utf-8", newline="\n") as stream:
                        stream.write(json.dumps(submission) + "\n")
                except BaseException as exc:
                    errors.append(exc)

            thread = threading.Thread(target=writer)
            thread.start()
            result = session.submit_declare_war(
                "r63_exec4_001", "FRA", "POR", "initiate", 56501040,
                parameters, timeout=1)
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual([], errors)
        self.assertEqual("submitted", result["status"])
        self.assertEqual(["ENG"], result["receipt"]["call_allies"])
        self.assertEqual(["ENG"], result["receipt"]["promise_land_to"])
        self.assertEqual(["SCO"], result["receipt"]["co_belligerents"])


if __name__ == "__main__":
    unittest.main()
