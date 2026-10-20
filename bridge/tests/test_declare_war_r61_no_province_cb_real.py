from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (Path(__file__).parent / "fixtures" /
           "declare_war_r61_no_province_cb_real.json")
OLD_CANDIDATE_FIXTURE = (Path(__file__).parent / "fixtures" /
                         "declare_war_r36_candidate_inspection.json")


class DeclareWarR61NoProvinceCBRealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def setUp(self) -> None:
        self.journal = DurableJournal(":memory:", "declare-r61", "test-session")

    def tearDown(self) -> None:
        self.journal.close()

    def _source_event(self) -> dict:
        source = self.fixture["source"]
        path = ROOT / Path(source["events_path"])
        self.assertTrue(path.is_file(), path)
        digest = hashlib.sha256()
        size = 0
        selected = None
        selected_raw = None
        with path.open("rb") as stream:
            for line_number, raw in enumerate(stream, 1):
                digest.update(raw)
                size += len(raw)
                if line_number == source["line_records"]["selected_inspection"]["line"]:
                    selected_raw = raw.rstrip(b"\r\n")
                    selected = json.loads(selected_raw)
        # The control probe is append-only and root may add later native
        # observations in the same session.  Bind the fixture to its exact
        # source line while accepting an appended tail; an unchanged file
        # still gets the original whole-file hash check.
        self.assertGreaterEqual(size, source["events_size"])
        if size == source["events_size"]:
            self.assertEqual(source["events_sha256"], digest.hexdigest())
        self.assertIsNotNone(selected)
        self.assertIsNotNone(selected_raw)
        line_meta = source["line_records"]["selected_inspection"]
        assert selected is not None and selected_raw is not None
        self.assertEqual(line_meta["bytes"], len(selected_raw))
        self.assertEqual(line_meta["sha256"], hashlib.sha256(selected_raw).hexdigest())
        self.assertEqual(self.fixture["event"], selected)
        return selected

    def _f_source_event(self) -> dict:
        case = self.fixture["f_case"]
        source = case["source"]
        path = ROOT / Path(source["events_path"])
        self.assertTrue(path.is_file(), path)
        digest = hashlib.sha256()
        size = 0
        selected = None
        selected_raw = None
        with path.open("rb") as stream:
            for line_number, raw in enumerate(stream, 1):
                digest.update(raw)
                size += len(raw)
                if line_number == source["line_records"]["selected_inspection"]["line"]:
                    selected_raw = raw.rstrip(b"\r\n")
                    selected = json.loads(selected_raw)
        self.assertEqual(source["events_size"], size)
        self.assertEqual(source["events_sha256"], digest.hexdigest())
        self.assertIsNotNone(selected)
        self.assertIsNotNone(selected_raw)
        line_meta = source["line_records"]["selected_inspection"]
        assert selected is not None and selected_raw is not None
        self.assertEqual(line_meta["bytes"], len(selected_raw))
        self.assertEqual(line_meta["sha256"], hashlib.sha256(selected_raw).hexdigest())
        self.assertEqual(case["event"], selected)
        return selected

    @staticmethod
    def _installation(root: Path) -> Path:
        session_id = "declare-r61-no-province-session"
        installation = root / "installation.json"
        installation.write_text(json.dumps({
            "experiment_id": "declare-r61-no-province",
            "session_id": session_id,
            "pid": 1,
            "creation_filetime": 2,
            "dll_sha256": "fixture-dll",
            "controlled_countries": ["FRA"],
            "installation_returncode": 0,
            "native_text_codec": "eu4_escape",
        }), encoding="utf-8")
        (root / "control-probe.jsonl").write_text(
            json.dumps({
                "event": "diplomacy_observer_installed",
                "session_id": session_id,
                "native_declare_war_query": True,
            }) + "\n", encoding="utf-8")
        return installation

    def _run_query(self, event: dict, parameters: dict) -> dict:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(self._installation(root), root / "eu4.exe")
            request = session.directory / "diplomacy-query.request"
            log = session.directory / "control-probe.jsonl"
            errors: list[BaseException] = []

            def writer() -> None:
                try:
                    deadline = time.monotonic() + 2
                    while not request.exists() and time.monotonic() < deadline:
                        time.sleep(0.001)
                    if not request.exists():
                        raise AssertionError("query request was not published")
                    fields = request.read_text(encoding="ascii").strip().split()
                    self.assertEqual("EU4DIP_QUERY3", fields[0])
                    self.assertEqual(11, len(fields))
                    self.assertEqual("declare_war", fields[3])
                    self.assertEqual("FRA", fields[4])
                    self.assertEqual("ENG", fields[5])
                    self.assertEqual(parameters["casus_belli"], fields[8])
                    self.assertEqual(str(parameters["war_goal"]["province_id"]), fields[9])
                    self.assertEqual(parameters["war_goal"]["beneficiary"], fields[10])
                    request.unlink(missing_ok=True)
                    observed = copy.deepcopy(event)
                    observed["query_id"] = fields[2]
                    observed["session_id"] = session.session_id
                    with log.open("a", encoding="utf-8", newline="\n") as stream:
                        stream.write(json.dumps(observed) + "\n")
                except BaseException as exc:  # pragma: no cover - surfaced below
                    errors.append(exc)

            thread = threading.Thread(target=writer)
            thread.start()
            ready = {
                "status": "ready",
                "state_id": "ready",
                "date_raw": event["date_raw"],
                "reasons": [],
                "complete": True,
            }
            with patch.object(session, "health", return_value=ready), \
                    patch("bridge.diplomacy.probe_identity",
                          return_value={"session_id": session.session_id}):
                result = DiplomacyTools(
                    self.journal, session).inspect_diplomatic_action(
                        "declare_war", "FRA", "ENG", parameters=parameters)
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual([], errors)
            return result

    @staticmethod
    def _parameters() -> dict:
        return {
            "casus_belli": "cb_independence_war",
            "war_goal": {"province_id": -1, "beneficiary": "FRA"},
            "call_allies": [],
        }

    def test_real_unmatched_sentinel_candidate_is_consumable_but_unavailable(self):
        event = self._source_event()
        expected = self.fixture["expected"]
        selection = {"casus_belli": "cb_independence_war",
                     "province_id": -1, "beneficiary": "FRA"}
        self.assertTrue(ObserverSession._valid_native_declare_war_inspection(
            event, "declare_war", "FRA", "ENG", "initiate",
            event["date_raw"], event["query_id"], event["session_id"], selection))
        public = ObserverSession._semantic_declare_war_inspection(
            event, "eu4_escape")
        self.assertEqual(expected["candidate_count"], len(public["candidates"]))
        self.assertEqual(expected["candidate_zero"]["casus_belli"],
                         public["candidates"][0]["casus_belli_key"])
        self.assertEqual(expected["candidate_zero"]["target_province_id"],
                         public["candidates"][0]["target_province_id"])
        self.assertEqual(expected["candidate_zero"]["beneficiary_tag"],
                         public["candidates"][0]["beneficiary_tag"])
        self.assertFalse(public["candidates"][0]["province_identifier_verified"])
        self.assertFalse(public["candidates"][0]["beneficiary_identifier_verified"])
        self.assertEqual(expected["native_rule_status"], "unavailable")
        self.assertFalse(public["native_rule_components"]["native_validity"])
        self.assertFalse(public["native_rule_components"]["common_action_gate"])
        result = self._run_query(event, self._parameters())
        self.assertNotEqual("QUERY_NATIVE_RESULT_INVALID", result.get("error_code"))
        self.assertFalse(result["selection_matched"])
        self.assertFalse(result["parameters"]["complete"])
        self.assertEqual("unavailable", result["legality"]["status"])
        self.assertEqual(
            "NATIVE_DECLARE_WAR_SELECTION_NOT_FOUND",
            result["legality"]["reasons"][0]["code"])
        self.assertEqual(expected["candidate_count"],
                         len(result["parameters"]["candidates"]))

    def test_matched_no_target_candidate_requires_both_identifier_proofs(self):
        event = self._source_event()
        matched = copy.deepcopy(event)
        matched.update({
            "selection_matched": True,
            "selection_match_count": 1,
            "parameter_context_complete": True,
            "candidate_context_complete": True,
            "full_rules_complete": True,
            "native_default_payload": False,
        })
        matched["candidates"][0].update({
            "province_identifier_verified": True,
            "beneficiary_identifier_verified": True,
        })
        selection = {"casus_belli": "cb_independence_war",
                     "province_id": -1, "beneficiary": "FRA"}
        self.assertTrue(ObserverSession._valid_native_declare_war_inspection(
            matched, "declare_war", "FRA", "ENG", "initiate",
            matched["date_raw"], matched["query_id"], matched["session_id"], selection))
        result = self._run_query(matched, self._parameters())
        self.assertNotEqual("QUERY_NATIVE_RESULT_INVALID", result.get("error_code"))
        self.assertTrue(result["selection_matched"])
        self.assertTrue(result["parameters"]["complete"])
        self.assertEqual("unavailable", result["legality"]["status"])
        self.assertFalse(result["native_rule_components"]["native_validity"])

        for field in ("province_identifier_verified",
                      "beneficiary_identifier_verified"):
            malformed = copy.deepcopy(matched)
            malformed["candidates"][0][field] = False
            with self.subTest(field=field):
                self.assertFalse(ObserverSession._valid_native_declare_war_inspection(
                    malformed, "declare_war", "FRA", "ENG", "initiate",
                    malformed["date_raw"], malformed["query_id"],
                    malformed["session_id"], selection))

    def test_default_r36_candidate_fixture_still_validates(self):
        event = json.loads(OLD_CANDIDATE_FIXTURE.read_text(encoding="utf-8"))["event"]
        self.assertTrue(ObserverSession._valid_native_declare_war_inspection(
            event, "declare_war", "FRA", "BUR", "initiate", event["date_raw"],
            event["query_id"], event["session_id"]))

    def test_real_matched_rule_false_preserves_diagnostic_and_cost_text(self):
        case = self.fixture["f_case"]
        event = self._f_source_event()
        params = case["input"]["parameters"]
        selection = {
            "casus_belli": params["casus_belli"],
            "province_id": params["war_goal"]["province_id"],
            "beneficiary": params["war_goal"]["beneficiary"],
        }
        self.assertTrue(ObserverSession._valid_native_declare_war_inspection(
            event, "declare_war", "FRA", "ENG", "initiate",
            event["date_raw"], event["query_id"], event["session_id"], selection))

        public = ObserverSession._semantic_declare_war_inspection(
            event, "eu4_escape")
        expected = case["expected"]
        self.assertTrue(public["selection_matched"])
        self.assertEqual(expected["candidate_count"], len(public["candidates"]))
        self.assertFalse(public["native_rule_components"]["native_validity"])
        self.assertFalse(public["native_rule_components"]["common_action_gate"])
        self.assertTrue(public["native_rule_components"]["full_rules_complete"])
        self.assertIn(expected["diagnostic_text_contains"],
                      public["native_diagnostic_text"])
        for text in expected["cost_text_contains"]:
            self.assertIn(text, public["costs"]["native_text"])

        result = self._run_query(event, params)
        self.assertNotEqual("QUERY_NATIVE_RESULT_INVALID", result.get("error_code"))
        self.assertTrue(result["selection_matched"])
        self.assertEqual(expected["legality_status"], result["legality"]["status"])
        self.assertEqual(expected["legality_code"],
                         result["legality"]["reasons"][0]["code"])
        self.assertIn(expected["diagnostic_text_contains"],
                      result["legality"]["reasons"][0]["text"])
        self.assertEqual(expected["cost_status"], result["costs"]["status"])
        self.assertEqual(expected["cost_context"], result["costs"]["context"])
        for text in expected["cost_text_contains"]:
            self.assertIn(text, result["costs"]["native_text"])


if __name__ == "__main__":
    unittest.main()
