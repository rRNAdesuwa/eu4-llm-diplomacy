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


class SpyNetworkExecutionSession:
    def __init__(self, execution_event: dict | None = None,
                 capabilities: set[str] | None = None):
        self.session_id = "spy-session"
        self.record = {"controlled_countries": ["FRA"]}
        self.capabilities = frozenset(capabilities or {
            "native_spy_network_query",
            "native_spy_network_submission",
        })
        self.execution_event = execution_event
        self.submit_calls: list[tuple[str, str]] = []

    def health(self) -> dict:
        return {"status": "ready", "state_id": "ready", "date_raw": 1,
                "reasons": [], "complete": True}

    def installation_capabilities(self) -> frozenset[str]:
        return self.capabilities

    def inspect_spy_network(self, action_id: str, actor: str,
                            recipient: str, phase: str) -> dict:
        return SpyNetworkToolsTests._native_event(
            "spy-query", action_id, recipient=recipient)

    def _submit(self, request_id: str, action_id: str, actor: str,
                recipient: str, phase: str, date_raw: int) -> dict:
        self.submit_calls.append((request_id, action_id))
        receipt = SpyNetworkToolsTests._submission_receipt(request_id, action_id)
        return {"status": "submitted", "receipt": receipt}

    def submit_build_spy_network(self, request_id: str, actor: str,
                                 recipient: str, phase: str, date_raw: int) -> dict:
        return self._submit(request_id, "build_spy_network", actor, recipient, phase, date_raw)

    def submit_stop_building_spy_network(self, request_id: str, actor: str,
                                         recipient: str, phase: str, date_raw: int) -> dict:
        return self._submit(request_id, "stop_building_spy_network", actor, recipient, phase, date_raw)

    def read_native_spy_network_execution(
            self, request_id: str, actor: str, recipient: str,
            phase: str, date_raw: int,
            action_id: str = "build_spy_network") -> dict | None:
        if self.execution_event is None:
            return None
        event = {**self.execution_event, "request_id": request_id,
                 "session_id": self.session_id, "action_id": action_id,
                 "actor": actor, "recipient": recipient, "phase": phase,
                 "date_raw": date_raw}
        result = ObserverSession._public_native_spy_network_execution_result(
            event, request_id, self.session_id, actor, recipient, phase, date_raw, action_id)
        if result is None:
            return {"status": "invalid", "reason_code": "NATIVE_RESPONSE_RESULT_INVALID"}
        return {"status": result["native_outcome"], "result": result}


class SpyNetworkToolsTests(unittest.TestCase):
    """Contract tests for the independent Spy Network task family."""

    @staticmethod
    def _installation(root: Path, *, query_ack: object = None,
                      submission_ack: object = None,
                      caps: list[str] | None = None) -> tuple[Path, Path]:
        session_id = "spy-session"
        installation = root / "installation.json"
        installation.write_text(json.dumps({
            "experiment_id": "spy-contract",
            "session_id": session_id,
            "pid": 1,
            "creation_filetime": 2,
            "dll_sha256": "dll",
            "controlled_countries": ["FRA"],
            "installation_returncode": 0,
        }), encoding="utf-8")
        ack = {
            "event": "diplomacy_observer_installed",
            "session_id": session_id,
        }
        if query_ack is not None:
            ack["native_spy_network_query"] = query_ack
        if submission_ack is not None:
            ack["native_spy_network_submission"] = submission_ack
        if caps is not None:
            ack["caps"] = caps
        log = root / "control-probe.jsonl"
        log.write_text(json.dumps(ack) + "\n", encoding="utf-8")
        return installation, log

    @staticmethod
    def _execution_event(action_id: str = "build_spy_network",
                         **overrides: object) -> dict:
        starts = action_id == "build_spy_network"
        event = {
            "event": "native_diplomacy_task_execution_result",
            "request_id": "spy-execution",
            "session_id": "spy-session",
            "action_id": action_id,
            "actor": "FRA",
            "recipient": "SAV",
            "phase": "initiate",
            "date_raw": 1,
            "outcome": "executed",
            "native_state": 0,
            "native_variant": 1 if starts else 0,
            "family": "spy_network",
            "task_before": not starts,
            "task_after": starts,
            "execution_verified": True,
            "request_binding_verified": True,
        }
        event.update(overrides)
        return event

    @staticmethod
    def _submission_receipt(request_id: str, action_id: str) -> dict:
        return {
            "event": "native_alliance_submission_result",
            "request_id": request_id,
            "session_id": "spy-session",
            "action_id": action_id,
            "actor": "FRA",
            "recipient": "SAV",
            "phase": "initiate",
            "date_raw": 1,
            "submitted": True,
            "native_queue_verified": True,
            "transport_ring_receipt": True,
            "native_sequence": 7,
            "native_origin": 65535,
            "native_flags": 0,
        }

    @staticmethod
    def _native_event(query_id: str, action_id: str = "build_spy_network",
                      **overrides: object) -> dict:
        event = {
            "event": "native_alliance_inspection",
            "query_id": query_id,
            "session_id": "spy-session",
            "action_id": action_id,
            "actor": "FRA",
            "recipient": "SAV",
            "phase": "initiate",
            "date_raw": 1,
            "ui_selection_checked": True,
            "native_visibility": True,
            "ui_enabled_gate_checked": True,
            "common_action_gate": True,
            "display_predicate": True,
            "initiation_gate": True,
            "tooltip_gate": True,
            "validity_called": True,
            "native_validity": True,
            "full_rules_complete": True,
            "diplomat_context_readable": True,
            "diplomat_required": True,
            "available_diplomat_count": 2,
            "score_applicable": False,
            "score_available": False,
            "acceptance_predicate_available": False,
            "native_would_accept": False,
            "diagnostic_readable": True,
            "native_diagnostic_hex": "6f6b",
            "diagnostic_truncated": False,
            "reason_container_readable": False,
            "reason_count": 0,
            "reason_items": [],
            "reason_items_truncated": False,
            "submitted": False,
        }
        event.update(overrides)
        return event

    def setUp(self) -> None:
        self.journal = DurableJournal(":memory:", "spy-contract", "spy-session")

    def tearDown(self) -> None:
        self.journal.close()

    def test_catalog_scope_and_single_party_parameters(self):
        api = DiplomacyTools(self.journal)
        catalog = api.list_diplomatic_actions()
        by_id = {item["action_id"]: item for item in catalog["actions"]}
        for action_id in ("build_spy_network", "stop_building_spy_network"):
            action = by_id[action_id]
            self.assertEqual("spy_network", action["native_identifier"])
            self.assertEqual({}, action["parameter_definitions"])
            self.assertEqual(["initiate"], list(action["phases"]))
            inspection = api.inspect_diplomatic_action(action_id, "FRA", "SAV")
            self.assertEqual("not_applicable", inspection["acceptance"]["applicability"])
            self.assertTrue(inspection["acceptance"]["complete"])
            with self.assertRaisesRegex(ValueError, "SPY_NETWORK_PARAMETERS_UNSUPPORTED"):
                api.inspect_diplomatic_action(action_id, "FRA", "SAV", parameters={"diplomat_id": 1})
            with self.assertRaisesRegex(ValueError, "SPY_NETWORK_INITIATE_ONLY"):
                api.inspect_diplomatic_action(action_id, "FRA", "SAV", "accept")

    def test_spy_ack_is_dedicated_and_not_inferred(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = self._installation(root, query_ack=True,
                                                  caps=["native_spy_network_submission"])
            session = ObserverSession(installation, root / "eu4.exe")
            self.assertEqual(frozenset({"native_spy_network_query"}),
                             session.installation_capabilities())
            with patch.object(session, "health", return_value={
                    "status": "ready", "state_id": "ready", "date_raw": 1,
                    "reasons": [], "complete": True}):
                by_id = {item["action_id"]: item for item in
                         DiplomacyTools(self.journal, session).list_diplomatic_actions()["actions"]}
            self.assertEqual("partial_native_rules",
                             by_id["build_spy_network"]["phases"]["initiate"]["query"])
            self.assertEqual("unimplemented",
                             by_id["build_spy_network"]["phases"]["initiate"]["execute"])

            copied, _ = self._installation(
                root, query_ack=None, submission_ack=None,
                caps=["native_spy_network_query", "native_spy_network_submission"])
            copied_session = ObserverSession(copied, root / "eu4.exe")
            self.assertEqual(frozenset(), copied_session.installation_capabilities())

            other, _ = self._installation(
                root, query_ack=None, caps=["native_alliance_inspection", "native_improve_relations_query"])
            other_session = ObserverSession(other, root / "eu4.exe")
            with patch.object(other_session, "health", return_value={
                    "status": "ready", "state_id": "ready", "date_raw": 1,
                    "reasons": [], "complete": True}):
                self.assertIsNone(other_session.inspect_spy_network(
                    "build_spy_network", "FRA", "SAV", "initiate"))
            self.assertFalse((root / "diplomacy-query.request").exists())

    def _run_query_event(self, session: ObserverSession, action_id: str,
                         event_overrides: dict | None = None) -> dict:
        request = session.directory / "diplomacy-query.request"
        log = session.directory / "control-probe.jsonl"
        writer_errors: list[BaseException] = []

        def writer() -> None:
            try:
                deadline = time.monotonic() + 2
                while not request.exists() and time.monotonic() < deadline:
                    time.sleep(0.001)
                if not request.exists():
                    raise AssertionError("query request was not published")
                query_id = request.read_text(encoding="ascii").split()[2]
                request.unlink(missing_ok=True)
                event = self._native_event(query_id, action_id, **(event_overrides or {}))
                with log.open("a", encoding="utf-8", newline="") as stream:
                    stream.write(json.dumps(event) + "\n")
            except BaseException as exc:
                writer_errors.append(exc)

        thread = threading.Thread(target=writer)
        thread.start()
        ready = {"status": "ready", "state_id": "ready", "date_raw": 1,
                 "reasons": [], "complete": True}
        with patch.object(session, "health", return_value=ready), \
             patch("bridge.diplomacy.probe_identity",
                   return_value={"session_id": "spy-session"}):
            result = DiplomacyTools(self.journal, session).inspect_diplomatic_action(
                action_id, "FRA", "SAV")
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], writer_errors)
        return result

    def test_bounded_native_query_is_single_party_and_reads_diagnostics(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = self._installation(root, query_ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            for action_id in ("build_spy_network", "stop_building_spy_network"):
                result = self._run_query_event(session, action_id)
                self.assertEqual("partial_native_rules", result["interface_support"]["query"])
                self.assertEqual("unimplemented", result["interface_support"]["execute"])
                self.assertEqual("unavailable", result["authorization"]["status"])
                self.assertEqual("available", result["legality"]["status"])
                self.assertTrue(result["legality"]["complete"])
                self.assertEqual("not_applicable", result["acceptance"]["applicability"])
                self.assertFalse(result["acceptance"]["prediction_available"])
                self.assertNotIn("acceptance_gate", result["native_rule_components"])
                self.assertEqual(2, result["resources"]["diplomats"]["available_count"])
                self.assertEqual("ok", result["native_diagnostic"]["text"])

    def test_spy_query_rejects_acceptance_score_flags(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = self._installation(root, query_ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            result = self._run_query_event(session, "build_spy_network",
                                           {"score_applicable": True})
            self.assertEqual("QUERY_NATIVE_RESULT_INVALID",
                             result["legality"]["reasons"][0]["code"])

    def test_spy_submission_receipt_binds_exact_action(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, log = self._installation(root, submission_ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            request = root / "diplomacy-execute.req"
            errors: list[BaseException] = []

            def writer() -> None:
                try:
                    deadline = time.monotonic() + 2
                    while not request.exists() and time.monotonic() < deadline:
                        time.sleep(0.001)
                    self.assertTrue(request.exists())
                    fields = request.read_text(encoding="ascii").strip().split("|")
                    action_id = fields[5]
                    self.assertIn(action_id, ("build_spy_network", "stop_building_spy_network"))
                    request.unlink(missing_ok=True)
                    with log.open("a", encoding="utf-8", newline="") as stream:
                        stream.write(json.dumps(self._submission_receipt(
                            fields[1], action_id)) + "\n")
                except BaseException as exc:
                    errors.append(exc)

            for action_id, method_name in (
                    ("build_spy_network", "submit_build_spy_network"),
                    ("stop_building_spy_network", "submit_stop_building_spy_network")):
                thread = threading.Thread(target=writer)
                thread.start()
                result = getattr(session, method_name)(
                    "spy-" + action_id, "FRA", "SAV", "initiate", 1, timeout=2)
                thread.join(2)
                self.assertFalse(thread.is_alive())
                self.assertEqual("submitted", result["status"])
                self.assertEqual(action_id, result["receipt"]["action_id"])
            self.assertEqual([], errors)

    def test_spy_execution_contract_checks_family_source_variant_and_transition(self):
        valid = self._execution_event()
        accepted = ObserverSession._public_native_spy_network_execution_result(
            valid, "spy-execution", "spy-session", "FRA", "SAV", "initiate", 1,
            "build_spy_network")
        self.assertIsNotNone(accepted)
        self.assertEqual("executed", accepted["native_outcome"])
        for field, value in (
                ("family", "improve_relations"),
                ("request_id", "other-request"),
                ("session_id", "other-session"),
                ("date_raw", 2),
                ("action_id", "stop_building_spy_network"),
                ("native_variant", 0),
                ("native_state", 1),
                ("execution_verified", False),
                ("request_binding_verified", False)):
            with self.subTest(field=field):
                self.assertIsNone(
                    ObserverSession._public_native_spy_network_execution_result(
                        {**valid, field: value}, "spy-execution", "spy-session",
                        "FRA", "SAV", "initiate", 1, "build_spy_network"))
        unknown = ObserverSession._public_native_spy_network_execution_result(
            {**valid, "task_before": True, "task_after": True},
            "spy-execution", "spy-session", "FRA", "SAV", "initiate", 1,
            "build_spy_network")
        self.assertIsNotNone(unknown)
        self.assertEqual("unknown", unknown["native_outcome"])
        stop = ObserverSession._public_native_spy_network_execution_result(
            self._execution_event("stop_building_spy_network"),
            "spy-execution", "spy-session", "FRA", "SAV", "initiate", 1,
            "stop_building_spy_network")
        self.assertIsNotNone(stop)
        self.assertEqual("executed", stop["native_outcome"])

    def test_spy_execution_missing_result_and_sqlite_reopen_are_idempotent(self):
        session = SpyNetworkExecutionSession()
        api = DiplomacyTools(self.journal, session)
        submitted = api.execute_diplomatic_action(
            "spy-pending", "build_spy_network", "FRA", "SAV")
        self.assertEqual("submitted", submitted["status"])
        self.assertTrue(submitted["submitted"])
        self.assertEqual("unknown", submitted["game_outcome"])
        self.assertEqual(1, len(session.submit_calls))

        session.execution_event = self._execution_event()
        executed = api.get_diplomatic_result("spy-pending")
        self.assertEqual("executed", executed["status"])
        self.assertEqual("executed", executed["result"]["native_outcome"])

        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "journal.sqlite3"
            journal = DurableJournal(database, "spy-contract", "spy-session")
            first_session = SpyNetworkExecutionSession(self._execution_event())
            first_api = DiplomacyTools(journal, first_session)
            first = first_api.execute_diplomatic_action(
                "spy-reopen", "build_spy_network", "FRA", "SAV")
            again = first_api.execute_diplomatic_action(
                "spy-reopen", "build_spy_network", "FRA", "SAV")
            self.assertEqual("executed", first["status"])
            self.assertTrue(again["idempotent"])
            self.assertEqual(1, len(first_session.submit_calls))
            journal.close()

            reopened = DurableJournal(database, "spy-contract", "spy-session")
            recovered = DiplomacyTools(
                reopened, SpyNetworkExecutionSession(self._execution_event())).get_diplomatic_result(
                    "spy-reopen")
            self.assertEqual("executed", recovered["status"])
            self.assertEqual("executed", recovered["game_outcome"])
            reopened.close()


if __name__ == "__main__":
    unittest.main()
