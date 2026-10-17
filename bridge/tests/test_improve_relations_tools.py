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


class ImproveExecutionSession:
    def __init__(self, execution_event: dict | None = None,
                 capabilities: set[str] | None = None):
        self.session_id = "improve-session"
        self.record = {"controlled_countries": ["FRA"]}
        self.capabilities = frozenset(capabilities or {
            "native_improve_relations_query",
            "native_improve_relations_submission",
        })
        self.execution_event = execution_event
        self.submit_calls: list[tuple[str, str]] = []

    def health(self) -> dict:
        return {"status": "ready", "state_id": "ready", "date_raw": 1,
                "reasons": [], "complete": True}

    def installation_capabilities(self) -> frozenset[str]:
        return self.capabilities

    def inspect_improve_relations(self, action_id: str, actor: str,
                                  recipient: str, phase: str) -> dict:
        return ImproveRelationsToolsTests._native_event(
            "improve-query", action_id, recipient=recipient)

    def _submit(self, request_id: str, action_id: str, actor: str,
                recipient: str, phase: str, date_raw: int) -> dict:
        self.submit_calls.append((request_id, action_id))
        receipt = ImproveRelationsToolsTests._submission_receipt(request_id, action_id)
        return {"status": "submitted", "receipt": receipt}

    def submit_improve_relations(self, request_id: str, actor: str,
                                 recipient: str, phase: str, date_raw: int) -> dict:
        return self._submit(request_id, "improve_relations", actor, recipient, phase, date_raw)

    def submit_stop_improving_relations(self, request_id: str, actor: str,
                                        recipient: str, phase: str, date_raw: int) -> dict:
        return self._submit(request_id, "stop_improving_relations", actor, recipient, phase, date_raw)

    def read_native_improve_relations_execution(
            self, request_id: str, actor: str, recipient: str,
            phase: str, date_raw: int, action_id: str = "improve_relations") -> dict | None:
        if self.execution_event is None:
            return None
        event = {**self.execution_event, "request_id": request_id,
                 "session_id": self.session_id, "action_id": action_id,
                 "actor": actor, "recipient": recipient, "phase": phase,
                 "date_raw": date_raw}
        result = ObserverSession._public_native_improve_relations_execution_result(
            event, request_id, self.session_id, actor, recipient, phase, date_raw, action_id)
        if result is None:
            return {"status": "invalid", "reason_code": "NATIVE_RESPONSE_RESULT_INVALID"}
        return {"status": result["native_outcome"], "result": result}


class ImproveRelationsToolsTests(unittest.TestCase):
    """Contract tests for the independent ImproveRelations query family."""

    @staticmethod
    def _installation(root: Path, *, top_ack: object = True,
                      submission_ack: object = None,
                      caps: list[str] | None = None) -> tuple[Path, Path]:
        session_id = "improve-session"
        installation = root / "installation.json"
        installation.write_text(json.dumps({
            "experiment_id": "improve-contract",
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
        if top_ack is not None:
            ack["native_improve_relations_query"] = top_ack
        if submission_ack is not None:
            ack["native_improve_relations_submission"] = submission_ack
        if caps is not None:
            ack["caps"] = caps
        log = root / "control-probe.jsonl"
        log.write_text(json.dumps(ack) + "\n", encoding="utf-8")
        return installation, log

    @staticmethod
    def _execution_event(action_id: str = "improve_relations",
                         **overrides: object) -> dict:
        event = {
            "event": "native_diplomacy_task_execution_result",
            "request_id": "improve-execution",
            "session_id": "improve-session",
            "action_id": action_id,
            "actor": "FRA",
            "recipient": "SAV",
            "phase": "initiate",
            "date_raw": 1,
            "outcome": "executed",
            "native_state": 0,
            "native_variant": 1 if action_id == "improve_relations" else 0,
            "family": "improve_relations",
            "task_before": action_id == "stop_improving_relations",
            "task_after": action_id == "improve_relations",
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
            "session_id": "improve-session",
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
    def _native_event(query_id: str, action_id: str = "improve_relations",
                      **overrides: object) -> dict:
        event = {
            "event": "native_alliance_inspection",
            "query_id": query_id,
            "session_id": "improve-session",
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
        self.journal = DurableJournal(":memory:", "improve-contract", "improve-session")

    def tearDown(self) -> None:
        self.journal.close()

    def test_catalog_uses_native_identifier_and_empty_parameters(self):
        api = DiplomacyTools(self.journal)
        catalog = api.list_diplomatic_actions()
        by_id = {item["action_id"]: item for item in catalog["actions"]}
        for action_id in ("improve_relations", "stop_improving_relations"):
            action = by_id[action_id]
            self.assertEqual("improve_relations", action["native_identifier"])
            self.assertEqual({}, action["parameter_definitions"])
            self.assertEqual(["initiate"], list(action["phases"]))
            self.assertEqual("unimplemented", action["phases"]["initiate"]["execute"])

            inspection = api.inspect_diplomatic_action(action_id, "FRA", "SAV")
            self.assertEqual("improve_relations", inspection["native_identifier"])
            self.assertEqual({}, inspection["parameters"]["requested"])
            self.assertEqual("not_applicable", inspection["acceptance"]["applicability"])
            self.assertTrue(inspection["acceptance"]["complete"])
            self.assertEqual("unimplemented", inspection["interface_support"]["execute"])
            with self.assertRaisesRegex(ValueError, "IMPROVE_RELATIONS_PARAMETERS_UNSUPPORTED"):
                api.inspect_diplomatic_action(
                    action_id, "FRA", "SAV", parameters={"diplomat_id": 1})
            with self.assertRaisesRegex(ValueError, "IMPROVE_RELATIONS_INITIATE_ONLY"):
                api.inspect_diplomatic_action(action_id, "FRA", "SAV", "accept")

    def test_improve_ack_is_exact_and_does_not_infer_other_families(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = self._installation(root, top_ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            ready = {"status": "ready", "state_id": "ready", "date_raw": 1,
                     "reasons": [], "complete": True}
            with patch.object(session, "health", return_value=ready):
                self.assertEqual(frozenset({"native_improve_relations_query"}),
                                 session.installation_capabilities())
                catalog = DiplomacyTools(self.journal, session).list_diplomatic_actions()
            by_id = {item["action_id"]: item for item in catalog["actions"]}
            self.assertEqual(
                "partial_native_rules",
                by_id["improve_relations"]["phases"]["initiate"]["query"])
            self.assertEqual(
                "unimplemented",
                by_id["offer_royal_marriage"]["phases"]["initiate"]["query"])
            self.assertEqual(
                "partial_native_queue_read",
                by_id["offer_alliance"]["phases"]["initiate"]["query"])

            copied_caps_installation, _ = self._installation(
                root, top_ack=None, caps=["native_improve_relations_query"])
            copied_caps = ObserverSession(copied_caps_installation, root / "eu4.exe")
            self.assertEqual(frozenset(), copied_caps.installation_capabilities())

    def test_alliance_or_royal_ack_cannot_open_improve_query(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = self._installation(
                root, top_ack=None, caps=["native_alliance_inspection", "native_royal_marriage_query"])
            session = ObserverSession(installation, root / "eu4.exe")
            ready = {"status": "ready", "state_id": "ready", "date_raw": 1,
                     "reasons": [], "complete": True}
            with patch.object(session, "health", return_value=ready):
                self.assertIsNone(session.inspect_improve_relations(
                    "improve_relations", "FRA", "SAV", "initiate"))
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
                with log.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(event) + "\n")
            except BaseException as exc:  # surfaced after the bounded query
                writer_errors.append(exc)

        thread = threading.Thread(target=writer)
        thread.start()
        ready = {"status": "ready", "state_id": "ready", "date_raw": 1,
                 "reasons": [], "complete": True}
        with patch.object(session, "health", return_value=ready), \
             patch("bridge.diplomacy.probe_identity",
                   return_value={"session_id": "improve-session"}):
            result = DiplomacyTools(self.journal, session).inspect_diplomatic_action(
                action_id, "FRA", "SAV")
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], writer_errors)
        return result

    def test_bounded_native_query_returns_ui_validity_diplomat_and_diagnostic(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = self._installation(root, top_ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            for action_id in ("improve_relations", "stop_improving_relations"):
                result = self._run_query_event(session, action_id)
                self.assertEqual("partial_native_rules",
                                 result["interface_support"]["query"])
                self.assertEqual("unimplemented", result["interface_support"]["execute"])
                self.assertEqual("unavailable", result["authorization"]["status"])
                self.assertEqual("available", result["legality"]["status"])
                self.assertTrue(result["legality"]["complete"])
                self.assertEqual("not_applicable", result["acceptance"]["applicability"])
                self.assertFalse(result["acceptance"]["prediction_available"])
                self.assertNotIn("acceptance_gate", result["native_rule_components"])
                self.assertEqual("visible", result["visibility"]["status"])
                self.assertEqual(2, result["resources"]["diplomats"]["available_count"])
                self.assertEqual("ok", result["native_diagnostic"]["text"])
                self.assertTrue(result["native_rule_components"]["complete"])
                self.assertEqual({}, result["parameters"]["requested"])

    def test_improve_query_rejects_acceptance_score_flags(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = self._installation(root, top_ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            result = self._run_query_event(
                session, "improve_relations", {"score_applicable": True})
            self.assertEqual("QUERY_NATIVE_RESULT_INVALID",
                             result["legality"]["reasons"][0]["code"])

    def test_improve_submission_ack_is_dedicated_and_not_inferred(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            query_only, _ = self._installation(root, top_ack=True)
            query_session = ObserverSession(query_only, root / "eu4.exe")
            self.assertNotIn("native_improve_relations_submission",
                             query_session.installation_capabilities())
            self.assertEqual(
                "NATIVE_IMPROVE_RELATIONS_SUBMISSION_CAPABILITY_MISSING",
                query_session.submit_improve_relations(
                    "improve-submit", "FRA", "SAV", "initiate", 1, timeout=0)["reason_code"])

            copied_caps, _ = self._installation(
                root, top_ack=None, caps=[
                    "native_improve_relations_query",
                    "native_improve_relations_submission",
                    "native_royal_marriage_submission",
                    "native_offer_submission",
                ])
            copied_session = ObserverSession(copied_caps, root / "eu4.exe")
            copied_capabilities = copied_session.installation_capabilities()
            self.assertNotIn("native_improve_relations_submission", copied_capabilities)
            self.assertNotIn("native_royal_marriage_submission", copied_capabilities)
            self.assertIn("native_offer_submission", copied_capabilities)

            submission_ack, _ = self._installation(
                root, top_ack=True, submission_ack=True)
            submission_session = ObserverSession(submission_ack, root / "eu4.exe")
            self.assertIn("native_improve_relations_submission",
                          submission_session.installation_capabilities())
            ready = {"status": "ready", "state_id": "ready", "date_raw": 1,
                     "reasons": [], "complete": True}
            with patch.object(submission_session, "health", return_value=ready):
                actions = DiplomacyTools(self.journal, submission_session).list_diplomatic_actions()
            by_id = {item["action_id"]: item for item in actions["actions"]}
            for action_id in ("improve_relations", "stop_improving_relations"):
                self.assertEqual(
                    "native_improve_relations_submission",
                    by_id[action_id]["phases"]["initiate"]["execute"])

    def test_native_improve_submission_receipt_binds_exact_action(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, log = self._installation(
                root, top_ack=None, submission_ack=True)
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
                    self.assertEqual("improve_relations", fields[5])
                    request.unlink(missing_ok=True)
                    with log.open("a", encoding="utf-8", newline="\n") as stream:
                        stream.write(json.dumps(self._submission_receipt(
                            fields[1], "improve_relations")) + "\n")
                except BaseException as exc:
                    errors.append(exc)

            thread = threading.Thread(target=writer)
            thread.start()
            result = session.submit_improve_relations(
                "improve-submit", "FRA", "SAV", "initiate", 1, timeout=2)
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual([], errors)
            self.assertEqual("submitted", result["status"])
            self.assertEqual("improve_relations", result["receipt"]["action_id"])

    def test_native_stop_improving_submission_uses_exact_action(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, log = self._installation(
                root, top_ack=None, submission_ack=True)
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
                    self.assertEqual("stop_improving_relations", fields[5])
                    request.unlink(missing_ok=True)
                    with log.open("a", encoding="utf-8", newline="\n") as stream:
                        stream.write(json.dumps(self._submission_receipt(
                            fields[1], "stop_improving_relations")) + "\n")
                except BaseException as exc:
                    errors.append(exc)

            thread = threading.Thread(target=writer)
            thread.start()
            result = session.submit_stop_improving_relations(
                "stop-submit", "FRA", "SAV", "initiate", 1, timeout=2)
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual([], errors)
            self.assertEqual("submitted", result["status"])
            self.assertEqual("stop_improving_relations", result["receipt"]["action_id"])

    def test_improve_execution_result_contract_rejects_crossed_fields(self):
        valid = self._execution_event()
        accepted = ObserverSession._public_native_improve_relations_execution_result(
            valid, "improve-execution", "improve-session", "FRA", "SAV", "initiate", 1,
            "improve_relations")
        self.assertIsNotNone(accepted)
        self.assertEqual("executed", accepted["native_outcome"])
        for field, value in (
                ("family", "royal_marriage"),
                ("native_variant", 0),
                ("native_state", 1),
                ("execution_verified", False),
                ("request_binding_verified", False),
                ("outcome", "malformed")):
            with self.subTest(field=field):
                self.assertIsNone(
                    ObserverSession._public_native_improve_relations_execution_result(
                        {**valid, field: value}, "improve-execution", "improve-session",
                        "FRA", "SAV", "initiate", 1, "improve_relations"))

        unknown = ObserverSession._public_native_improve_relations_execution_result(
            {**valid, "task_before": True, "task_after": True},
            "improve-execution", "improve-session", "FRA", "SAV", "initiate", 1,
            "improve_relations")
        self.assertIsNotNone(unknown)
        self.assertEqual("unknown", unknown["native_outcome"])

        stop = self._execution_event("stop_improving_relations")
        stop_result = ObserverSession._public_native_improve_relations_execution_result(
            stop, "improve-execution", "improve-session", "FRA", "SAV", "initiate", 1,
            "stop_improving_relations")
        self.assertIsNotNone(stop_result)
        self.assertEqual("executed", stop_result["native_outcome"])

    def test_improve_execution_missing_result_stays_submitted_then_executes(self):
        session = ImproveExecutionSession()
        api = DiplomacyTools(self.journal, session)
        submitted = api.execute_diplomatic_action(
            "improve-pending", "improve_relations", "FRA", "SAV")
        self.assertEqual("submitted", submitted["status"])
        self.assertTrue(submitted["submitted"])
        self.assertEqual("unknown", submitted["game_outcome"])
        self.assertEqual(1, len(session.submit_calls))

        session.execution_event = self._execution_event()
        executed = api.get_diplomatic_result("improve-pending")
        self.assertEqual("executed", executed["status"])
        self.assertEqual("executed", executed["game_outcome"])
        self.assertEqual("executed", executed["result"]["native_outcome"])

    def test_improve_execution_is_idempotent_across_sql_reopen(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "journal.sqlite3"
            session = ImproveExecutionSession(self._execution_event())
            journal = DurableJournal(database, "improve-contract", "improve-session")
            api = DiplomacyTools(journal, session)
            first = api.execute_diplomatic_action(
                "improve-reopen", "improve_relations", "FRA", "SAV")
            again = api.execute_diplomatic_action(
                "improve-reopen", "improve_relations", "FRA", "SAV")
            self.assertEqual("executed", first["status"])
            self.assertTrue(again["idempotent"])
            self.assertEqual(1, len(session.submit_calls))
            journal.close()

            reopened = DurableJournal(database, "improve-contract", "improve-session")
            recovered = DiplomacyTools(
                reopened, ImproveExecutionSession(self._execution_event())).get_diplomatic_result(
                    "improve-reopen")
            self.assertEqual("executed", recovered["status"])
            self.assertEqual("executed", recovered["game_outcome"])
            reopened.close()

    def test_improve_execution_stays_unimplemented_and_does_not_require_diplomat_id(self):
        api = DiplomacyTools(self.journal)
        result = api.execute_diplomatic_action(
            "improve_unimplemented", "improve_relations", "FRA", "SAV")
        self.assertEqual("invalidated", result["status"])
        self.assertFalse(result["submitted"])
        self.assertEqual("unknown", result["game_outcome"])
        self.assertEqual("EXECUTION_ADAPTER_UNIMPLEMENTED", result["result"]["reason"]["code"])
        self.assertEqual({}, self.journal.get_request("improve_unimplemented").payload["parameters"])


if __name__ == "__main__":
    unittest.main()
