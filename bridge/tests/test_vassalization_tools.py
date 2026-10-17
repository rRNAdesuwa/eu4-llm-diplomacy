from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal


FIXTURE = (Path(__file__).parent / "fixtures" /
           "vassalization_r35_native_inspections.json")


class VassalizationToolsTests(unittest.TestCase):
    """Contract tests for the query-only R35 Vassalization family."""

    @staticmethod
    def _events() -> dict:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        events = dict(payload["events"])
        events["execution_events"] = payload["execution_events"]
        return events

    @staticmethod
    def _installation(root: Path, ack: object = True, *, submission: object = None,
                      inbound: object = None) -> tuple[Path, Path]:
        session_id = "vassal-session"
        installation = root / "installation.json"
        installation.write_text(json.dumps({
            "experiment_id": "vassal-contract",
            "session_id": session_id,
            "pid": 1,
            "creation_filetime": 2,
            "dll_sha256": "dll",
            "controlled_countries": ["FRA"],
            "installation_returncode": 0,
        }), encoding="utf-8")
        event = {
            "event": "diplomacy_observer_installed",
            "session_id": session_id,
        }
        if ack is not None:
            event["native_vassalization_query"] = ack
        if submission is not None:
            event["native_vassalization_submission"] = submission
        if inbound is not None:
            event["native_inbound_vassalization_response"] = inbound
        log = root / "control-probe.jsonl"
        log.write_text(json.dumps(event) + "\n", encoding="utf-8")
        return installation, log

    def setUp(self) -> None:
        self.journal = DurableJournal(":memory:", "vassal-contract", "vassal-session")

    def tearDown(self) -> None:
        self.journal.close()

    def _run_query(self, session: ObserverSession, action_id: str,
                   overrides: dict | None = None, *, recipient: str = "SAV") -> dict:
        request = session.directory / "diplomacy-query.request"
        log = session.directory / "control-probe.jsonl"
        event = {**self._events()[action_id], **(overrides or {})}
        expected_date = event["date_raw"]
        errors: list[BaseException] = []

        def writer() -> None:
            try:
                deadline = time.monotonic() + 2
                while not request.exists() and time.monotonic() < deadline:
                    time.sleep(0.001)
                if not request.exists():
                    raise AssertionError("query request was not published")
                fields = request.read_text(encoding="ascii").strip().split()
                self.assertEqual("EU4DIP_QUERY1", fields[0])
                self.assertEqual(action_id, fields[3])
                self.assertEqual("FRA", fields[4])
                self.assertEqual(recipient, fields[5])
                self.assertEqual(8, len(fields))
                request.unlink(missing_ok=True)
                event["query_id"] = fields[2]
                event["session_id"] = session.session_id
                with log.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(event) + "\n")
            except BaseException as exc:
                errors.append(exc)

        thread = threading.Thread(target=writer)
        thread.start()
        ready = {"status": "ready", "state_id": "ready",
                 "date_raw": expected_date, "reasons": [], "complete": True}
        with patch.object(session, "health", return_value=ready), \
             patch("bridge.diplomacy.probe_identity",
                   return_value={"session_id": session.session_id}):
            result = DiplomacyTools(self.journal, session).inspect_diplomatic_action(
                action_id, "FRA", recipient)
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], errors)
        return result

    def test_catalog_registers_family_and_query_only_execution(self):
        api = DiplomacyTools(self.journal)
        by_id = {item["action_id"]: item for item in api.list_diplomatic_actions()["actions"]}
        self.assertEqual("vassalization", by_id["offer_vassalization"]["native_identifier"])
        self.assertEqual("vassalization", by_id["cancel_vassalization"]["native_identifier"])
        self.assertEqual({}, by_id["offer_vassalization"]["parameter_definitions"])
        self.assertEqual({}, by_id["cancel_vassalization"]["parameter_definitions"])
        self.assertEqual("unimplemented",
                         by_id["offer_vassalization"]["phases"]["initiate"]["execute"])
        offer = api.inspect_diplomatic_action("offer_vassalization", "FRA", "SAV")
        cancel = api.inspect_diplomatic_action("cancel_vassalization", "FRA", "SAV")
        self.assertEqual("applicable", offer["acceptance"]["applicability"])
        self.assertEqual("not_applicable", cancel["acceptance"]["applicability"])
        with self.assertRaisesRegex(ValueError, "VASSALIZATION_PARAMETERS_UNSUPPORTED"):
            api.inspect_diplomatic_action("offer_vassalization", "FRA", "SAV",
                                          parameters={"foo": 1})
        with self.assertRaisesRegex(ValueError, "VASSALIZATION_PARAMETERS_UNSUPPORTED"):
            api.inspect_diplomatic_action("cancel_vassalization", "FRA", "SAV",
                                          parameters={"foo": 1})

    def test_query_ack_is_exact_and_does_not_grant_submission(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = self._installation(root, ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            self.assertEqual(frozenset({"native_vassalization_query"}),
                             session.installation_capabilities())
            with patch.object(session, "health", return_value={
                    "status": "ready", "state_id": "ready", "date_raw": 1,
                    "reasons": [], "complete": True}):
                by_id = {item["action_id"]: item for item in
                         DiplomacyTools(self.journal, session).list_diplomatic_actions()["actions"]}
            self.assertEqual("partial_native_rules",
                             by_id["offer_vassalization"]["phases"]["initiate"]["query"])
            self.assertEqual("unimplemented",
                             by_id["offer_vassalization"]["phases"]["initiate"]["execute"])
            self.assertEqual("partial_native_rules",
                             by_id["cancel_vassalization"]["phases"]["initiate"]["query"])

            copied, _ = self._installation(root, ack=1)
            copied_session = ObserverSession(copied, root / "eu4.exe")
            self.assertEqual(frozenset(), copied_session.installation_capabilities())

    def test_offer_projects_vassal_state_and_ai_acceptance_only_for_npc(self):
        event = self._events()["offer_vassalization"]
        self.assertTrue(ObserverSession._valid_native_inspection(
            event, "offer_vassalization", "FRA", "SAV", "initiate", 1))
        public = ObserverSession._semantic_inspection(event, {}, "eu4_escape", False)
        self.assertEqual("vassalization", public["family"])
        self.assertFalse(public["vassal_active"])
        self.assertTrue(public["vassal_state_verified"])
        self.assertFalse(public["actor_is_overlord"])
        self.assertEqual("vassal", public["subject_type"])
        self.assertEqual({"vassal_active": False, "complete": True},
                         public["relationship_state"])

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = self._installation(root, ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            result = self._run_query(session, "offer_vassalization")
        self.assertEqual("reject", result["acceptance"]["predicted_response"])
        self.assertTrue(result["acceptance"]["prediction_available"])
        self.assertFalse(result["acceptance"]["complete"])
        self.assertEqual(1, result["acceptance"]["reason_count"])

    def test_player_target_does_not_expose_ai_prediction_and_cancel_is_one_sided(self):
        offer = {**self._events()["offer_vassalization"],
                 "recipient": "POR", "native_would_accept": True}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = self._installation(root, ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            player_result = self._run_query(
                session, "offer_vassalization", offer, recipient="POR")
        self.assertFalse(player_result["acceptance"]["prediction_available"])
        self.assertEqual("unknown", player_result["acceptance"]["predicted_response"])
        self.assertNotIn("acceptance_gate", player_result["native_rule_components"])

        cancel = self._events()["cancel_vassalization"]
        self.assertTrue(ObserverSession._valid_native_inspection(
            cancel, "cancel_vassalization", "FRA", "SAV", "initiate", 1))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = self._installation(root, ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            result = self._run_query(session, "cancel_vassalization")
        self.assertEqual("not_applicable", result["acceptance"]["applicability"])
        self.assertTrue(result["acceptance"]["complete"])
        self.assertTrue(result["vassal_active"])
        self.assertTrue(result["actor_is_overlord"])
        self.assertEqual(2, result["costs"]["items"][0]["amount"])
        self.assertEqual(2000, result["costs"]["items"][0]["amount_raw"])
        self.assertFalse(result["costs"]["complete"])

    def test_family_and_vassal_state_contract_are_strict(self):
        event = self._events()["offer_vassalization"]
        self.assertFalse(ObserverSession._valid_native_inspection(
            {**event, "family": "guarantee"}, "offer_vassalization",
            "FRA", "SAV", "initiate", 1))
        self.assertFalse(ObserverSession._valid_native_inspection(
            {**event, "vassal_state_verified": "true"}, "offer_vassalization",
            "FRA", "SAV", "initiate", 1))
        self.assertFalse(ObserverSession._valid_native_inspection(
            {**event, "vassal_active": 1}, "offer_vassalization",
            "FRA", "SAV", "initiate", 1))
        self.assertFalse(ObserverSession._valid_native_inspection(
            {**event, "subject_type": 1}, "offer_vassalization",
            "FRA", "SAV", "initiate", 1))
        self.assertFalse(ObserverSession._valid_native_inspection(
            {**self._events()["cancel_vassalization"],
             "score_applicable": True}, "cancel_vassalization",
            "FRA", "SAV", "initiate", 1))

    def test_submission_ack_is_separate_and_inspection_advertises_adapter(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = self._installation(root, ack=None, submission=True)
            session = ObserverSession(installation, root / "eu4.exe")
            caps = session.installation_capabilities()
            self.assertNotIn("native_vassalization_query", caps)
            self.assertIn("native_vassalization_submission", caps)
            self.assertNotIn("native_inbound_vassalization_response", caps)
            ready = {"status": "ready", "state_id": "ready", "date_raw": 1,
                     "reasons": [], "complete": True}
            with patch.object(session, "health", return_value=ready):
                inspection = DiplomacyTools(self.journal, session).inspect_diplomatic_action(
                    "offer_vassalization", "FRA", "SAV")
            self.assertEqual("native_vassalization_submission",
                             inspection["interface_support"]["execute"])
            self.assertEqual("available", inspection["authorization"]["status"])

    def test_outbound_vassal_results_require_family_and_project_cancel_cost(self):
        events = self._events()["execution_events"]
        submission = events["submission_offer"]
        self.assertTrue(ObserverSession._valid_native_vassalization_submission_result(
            submission, "vassal-offer-1", "vassal-session", "FRA", "SAV",
            "initiate", 1, "offer_vassalization"))
        self.assertFalse(ObserverSession._valid_native_vassalization_submission_result(
            {**submission, "family": "alliance"}, "vassal-offer-1", "vassal-session",
            "FRA", "SAV", "initiate", 1, "offer_vassalization"))
        response = ObserverSession._public_native_vassalization_response_result(
            events["offer_response"], "vassal-offer-1", "vassal-session",
            "FRA", "SAV", "initiate", 1)
        self.assertEqual("accepted", response["native_outcome"])
        self.assertTrue(response["vassalization_after"])
        cancel = ObserverSession._public_native_vassalization_execution_result(
            events["cancel_response"], "vassal-cancel-1", "vassal-session",
            "FRA", "SAV", "initiate", 1)
        self.assertEqual("executed", cancel["native_outcome"])
        self.assertEqual(2000, cancel["costs"]["items"][0]["amount_raw"])
        self.assertEqual(2, cancel["costs"]["items"][0]["amount"])
        self.assertIsNone(ObserverSession._public_native_vassalization_execution_result(
            {**events["cancel_response"], "family": "guarantee"},
            "vassal-cancel-1", "vassal-session", "FRA", "SAV", "initiate", 1))

    def test_observer_readers_route_family_specific_result_events(self):
        events = self._events()["execution_events"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, log = self._installation(root, ack=None)
            log.write_text(json.dumps(events["offer_response"]) + "\n"
                           + json.dumps(events["cancel_response"]) + "\n",
                           encoding="utf-8")
            session = ObserverSession(installation, root / "eu4.exe")
            offer = session.read_native_vassalization_response(
                "vassal-offer-1", "FRA", "SAV", "initiate", 1)
            cancel = session.read_native_vassalization_execution(
                "vassal-cancel-1", "FRA", "SAV", "initiate", 1)
        self.assertEqual("accepted", offer["status"])
        self.assertEqual("executed", cancel["status"])

    def test_authorized_outbound_path_uses_family_receipt_and_result_reader(self):
        events = self._events()["execution_events"]

        class Session:
            session_id = "vassal-session"

            def installation_capabilities(self):
                return frozenset({"native_vassalization_submission"})

            @staticmethod
            def _receipt(request_id, action_id, actor, recipient, phase, date_raw):
                event = dict(events["submission_offer"])
                event.update({"request_id": request_id, "action_id": action_id,
                              "actor": actor, "recipient": recipient,
                              "phase": phase, "date_raw": date_raw})
                if action_id == "cancel_vassalization":
                    event["request_id"] = request_id
                return {"status": "submitted", "receipt": event}

            def submit_offer_vassalization(self, request_id, actor, recipient, phase, date_raw):
                return self._receipt(request_id, "offer_vassalization", actor,
                                     recipient, phase, date_raw)

            def submit_cancel_vassalization(self, request_id, actor, recipient, phase, date_raw):
                return self._receipt(request_id, "cancel_vassalization", actor,
                                     recipient, phase, date_raw)

            def read_native_vassalization_response(self, request_id, actor, recipient,
                                                   phase, date_raw):
                event = dict(events["offer_response"])
                event.update({"request_id": request_id, "actor": actor,
                              "recipient": recipient, "phase": phase,
                              "date_raw": date_raw})
                result = ObserverSession._public_native_vassalization_response_result(
                    event, request_id, self.session_id, actor, recipient, phase, date_raw)
                return {"status": result["native_outcome"], "result": result}

            def read_native_vassalization_execution(self, request_id, actor, recipient,
                                                    phase, date_raw):
                event = dict(events["cancel_response"])
                event.update({"request_id": request_id, "actor": actor,
                              "recipient": recipient, "phase": phase,
                              "date_raw": date_raw})
                result = ObserverSession._public_native_vassalization_execution_result(
                    event, request_id, self.session_id, actor, recipient, phase, date_raw)
                return {"status": result["native_outcome"], "result": result}

        inspection = {
            "action_id": "offer_vassalization",
            "session": {"status": "ready", "date_raw": 1},
            "legality": {"status": "available", "reasons": [], "complete": True},
            "authorization": {"status": "available", "complete": True},
            "interface_support": {"execute": "native_vassalization_submission"},
        }
        session = Session()
        api = DiplomacyTools(self.journal, session)
        with patch.object(api, "inspect_diplomatic_action", return_value=inspection):
            result = api.execute_diplomatic_action(
                "vassal-offer-e2e", "offer_vassalization", "FRA", "SAV")
        self.assertEqual("accepted", result["status"])
        self.assertEqual("vassalization", result["result"]["family"])
        self.assertTrue(result["result"]["vassalization_after"])

        inspection["action_id"] = "cancel_vassalization"
        with patch.object(api, "inspect_diplomatic_action", return_value=inspection):
            result = api.execute_diplomatic_action(
                "vassal-cancel-e2e", "cancel_vassalization", "FRA", "SAV")
        self.assertEqual("executed", result["status"])
        self.assertEqual(2, result["result"]["costs"]["items"][0]["amount"])

    def test_inbound_vassal_response_requires_pending_removal_and_family(self):
        events = self._events()["execution_events"]
        offer = events["inbound_offer"]
        self.assertTrue(ObserverSession._valid_native_inbound_offer_event(
            offer, "vassal-session"))
        inspection = events["inbound_inspection"]
        self.assertTrue(ObserverSession._valid_native_inbound_inspection(
            inspection, "vassal-inbound-q", "vassal-session", "SAV", "accept",
            17, 1, "offer_vassalization"))
        response = ObserverSession._public_native_inbound_response_result(
            events["inbound_response"], "vassal-inbound-1", "vassal-session",
            "SAV", "accept", 1, 17, "offer_vassalization")
        self.assertEqual("accepted", response["native_outcome"])
        self.assertTrue(response["pending_removed"])
        self.assertIsNone(ObserverSession._public_native_inbound_response_result(
            {**events["inbound_response"], "pending_removed": False},
            "vassal-inbound-1", "vassal-session", "SAV", "accept", 1, 17,
            "offer_vassalization"))
        self.assertIsNone(ObserverSession._public_native_inbound_response_result(
            {**events["inbound_response"], "family": "royal_marriage"},
            "vassal-inbound-1", "vassal-session", "SAV", "accept", 1, 17,
            "offer_vassalization"))


if __name__ == "__main__":
    unittest.main()
