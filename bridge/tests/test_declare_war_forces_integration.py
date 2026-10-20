from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bridge.declarewar_forces import project_declare_war_forces
from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal


FIXTURE = (Path(__file__).parent / "fixtures" /
           "declare_war_r36_native_inspection.json")


def _forces() -> dict:
    def side(countries: list[str], infantry: int, cavalry: int,
             artillery: int, reserve: int) -> dict:
        return {
            "countries": countries,
            "infantry_raw": infantry,
            "cavalry_raw": cavalry,
            "artillery_raw": artillery,
            "deployed_total_raw": infantry + cavalry + artillery,
            "reserve_manpower_raw": reserve,
            "deployed_complete": True,
            "reserve_complete": True,
            "scope_complete": True,
        }

    return {
        "called": True,
        "action_unchanged": True,
        "unit": "men",
        "units_verified": True,
        "complete": True,
        "attackers": side(["FRA"], 10000, 2000, 500, 4000),
        "defenders": side(["BUR"], 8000, 1000, 250, 3000),
    }


def _installation(root: Path, *, forces: object = True) -> Path:
    session_id = "declare-forces-session"
    installation = root / "installation.json"
    installation.write_text(json.dumps({
        "experiment_id": "declare-forces-contract",
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
    if forces is not None:
        ack["native_declare_war_forces"] = forces
    (root / "control-probe.jsonl").write_text(
        json.dumps(ack) + "\n", encoding="utf-8")
    return installation


class DeclareWarForcesIntegrationTests(unittest.TestCase):
    @staticmethod
    def _event() -> dict:
        return json.loads(FIXTURE.read_text(encoding="utf-8"))["events"]["default"]

    def test_optional_forces_are_validated_projected_and_role_bound(self) -> None:
        event = self._event()
        event["native_forces"] = _forces()
        self.assertTrue(ObserverSession._valid_native_declare_war_inspection(
            event, "declare_war", "FRA", "BUR", "initiate",
            event["date_raw"], event["query_id"], event["session_id"]))

        public = ObserverSession._semantic_declare_war_inspection(
            event, "eu4_escape")
        self.assertEqual(["FRA"], public["forces"]["attackers"]["countries"])
        self.assertEqual(["BUR"], public["forces"]["defenders"]["countries"])
        self.assertEqual(12500, public["forces"]["attackers"]["deployed"]["total"])
        self.assertEqual(3000, public["forces"]["defenders"]["reserve_manpower"]["amount"])
        self.assertNotIn("native_forces", public)

        tampered_total = copy.deepcopy(event)
        tampered_total["native_forces"]["attackers"]["deployed_total_raw"] += 1
        self.assertFalse(ObserverSession._valid_native_declare_war_inspection(
            tampered_total, "declare_war", "FRA", "BUR", "initiate",
            event["date_raw"], event["query_id"], event["session_id"]))

        tampered_role = copy.deepcopy(event)
        tampered_role["native_forces"]["attackers"]["countries"] = ["ENG"]
        self.assertFalse(ObserverSession._valid_native_declare_war_inspection(
            tampered_role, "declare_war", "FRA", "BUR", "initiate",
            event["date_raw"], event["query_id"], event["session_id"]))

    def test_historical_event_without_forces_remains_valid(self) -> None:
        event = self._event()
        self.assertTrue(ObserverSession._valid_native_declare_war_inspection(
            event, "declare_war", "FRA", "BUR", "initiate",
            event["date_raw"], event["query_id"], event["session_id"]))
        public = ObserverSession._semantic_declare_war_inspection(
            event, "eu4_escape")
        self.assertNotIn("forces", public)

    def test_forces_ack_is_exact_and_catalog_registers_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(_installation(root), root / "eu4.exe")
            self.assertIn("native_declare_war_forces",
                          session.installation_capabilities())

            copied_caps = _installation(root, forces=None)
            (root / "control-probe.jsonl").write_text(json.dumps({
                "event": "diplomacy_observer_installed",
                "session_id": "declare-forces-session",
                "caps": ["native_declare_war_forces"],
            }) + "\n", encoding="utf-8")
            self.assertNotIn("native_declare_war_forces",
                             ObserverSession(copied_caps,
                                             root / "eu4.exe").installation_capabilities())

            session = ObserverSession(_installation(root), root / "eu4.exe")
            journal = DurableJournal(":memory:", "declare-forces-contract",
                                     "declare-forces-session")
            try:
                ready = {"status": "ready", "state_id": "ready",
                         "date_raw": 56465136, "reasons": [], "complete": True}
                with patch.object(session, "health", return_value=ready):
                    catalog = DiplomacyTools(journal, session).list_diplomatic_actions()
            finally:
                journal.close()
        action = next(item for item in catalog["actions"]
                      if item["action_id"] == "declare_war")
        self.assertEqual(
            "native_declare_war_forces",
            action["observed_outputs"]["forces"]["capability"])
        self.assertEqual(
            "native_declare_war_forces",
            action["phases"]["initiate"]["query_forces"])


if __name__ == "__main__":
    unittest.main()
