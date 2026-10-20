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


class CurryExecutionSession:
    def __init__(self, execution_event: dict | None = None,
                 capabilities: set[str] | None = None):
        self.session_id = "curry-session"
        self.record = {"controlled_countries": ["FRA"]}
        self.capabilities = frozenset(capabilities or {
            "native_curry_favors_query",
            "native_curry_favors_submission",
        })
        self.execution_event = execution_event
        self.submit_calls: list[tuple[str, str]] = []

    def health(self) -> dict:
        return {"status": "ready", "state_id": "ready", "date_raw": 1,
                "reasons": [], "complete": True}

    def installation_capabilities(self) -> frozenset[str]:
        return self.capabilities

    def inspect_curry_favors(self, action_id: str, actor: str,
                             recipient: str, phase: str) -> dict:
        return CurryFavorsToolsTests._native_event(
            "curry-query", action_id, recipient=recipient)

    def _submit(self, request_id: str, action_id: str, actor: str,
                recipient: str, phase: str, date_raw: int) -> dict:
        self.submit_calls.append((request_id, action_id))
        return {"status": "submitted", "receipt":
                CurryFavorsToolsTests._submission_receipt(request_id, action_id)}

    def submit_curry_favors(self, request_id: str, actor: str,
                            recipient: str, phase: str, date_raw: int) -> dict:
        return self._submit(request_id, "curry_favors", actor, recipient, phase, date_raw)

    def submit_stop_curry_favors(self, request_id: str, actor: str,
                                 recipient: str, phase: str, date_raw: int) -> dict:
        return self._submit(request_id, "stop_curry_favors", actor, recipient, phase, date_raw)

    def read_native_curry_favors_execution(
            self, request_id: str, actor: str, recipient: str,
            phase: str, date_raw: int,
            action_id: str = "curry_favors") -> dict | None:
        if self.execution_event is None:
            return None
        event = {**self.execution_event, "request_id": request_id,
                 "session_id": self.session_id, "action_id": action_id,
                 "actor": actor, "recipient": recipient, "phase": phase,
                 "date_raw": date_raw}
        result = ObserverSession._public_native_curry_favors_execution_result(
            event, request_id, self.session_id, actor, recipient, phase,
            date_raw, action_id)
        if result is None:
            return {"status": "invalid", "reason_code": "NATIVE_RESPONSE_RESULT_INVALID"}
        return {"status": result["native_outcome"], "result": result}


class CurryFavorsToolsTests(unittest.TestCase):
    """Bounded contract tests for the independent Curry Favors task family."""

    @staticmethod
    def _installation(root: Path, *, query_ack: object = None,
                      submission_ack: object = None,
                      caps: list[str] | None = None) -> tuple[Path, Path]:
        installation = root / "installation.json"
        installation.write_text(json.dumps({
            "experiment_id": "curry-contract",
            "session_id": "curry-session",
            "pid": 1,
            "creation_filetime": 2,
            "dll_sha256": "dll",
            "controlled_countries": ["FRA"],
            "installation_returncode": 0,
        }), encoding="utf-8")
        ack = {
            "event": "diplomacy_observer_installed",
            "session_id": "curry-session",
        }
        if query_ack is not None:
            ack["native_curry_favors_query"] = query_ack
        if submission_ack is not None:
            ack["native_curry_favors_submission"] = submission_ack
        if caps is not None:
            ack["caps"] = caps
        log = root / "control-probe.jsonl"
        log.write_text(json.dumps(ack) + "\n", encoding="utf-8")
        return installation, log

    @staticmethod
    def _native_event(query_id: str, action_id: str = "curry_favors",
                      **overrides: object) -> dict:
        event = {
            "event": "native_alliance_inspection",
            "query_id": query_id,
            "session_id": "curry-session",
            "action_id": action_id,
            "family": "curry_favors",
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
            "task_active": action_id == "stop_curry_favors",
            "task_state_verified": True,
            "diplomat_context_readable": True,
            "diplomat_required": True,
            "available_diplomat_count": 2,
            "diplomat_assignment_verified": False,
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

    @staticmethod
    def _submission_receipt(request_id: str, action_id: str,
                            **overrides: object) -> dict:
        receipt = {
            "event": "native_alliance_submission_result",
            "request_id": request_id,
            "session_id": "curry-session",
            "action_id": action_id,
            "family": "curry_favors",
            "actor": "FRA",
            "recipient": "SAV",
            "phase": "initiate",
            "date_raw": 1,
            "native_variant": 1 if action_id == "curry_favors" else 0,
            "submitted": True,
            "native_queue_verified": True,
            "transport_ring_receipt": True,
            "native_sequence": 7,
            "native_origin": 65535,
            "native_flags": 0,
            "before_active": action_id == "stop_curry_favors",
        }
        receipt.update(overrides)
        return receipt

    @staticmethod
    def _execution_event(action_id: str = "curry_favors",
                         **overrides: object) -> dict:
        event = {
            "event": "native_diplomacy_task_execution_result",
            "request_id": "curry-execution",
            "session_id": "curry-session",
            "action_id": action_id,
            "actor": "FRA",
            "recipient": "SAV",
            "phase": "initiate",
            "date_raw": 1,
            "outcome": "executed",
            "native_state": 0,
            "native_variant": 1 if action_id == "curry_favors" else 0,
            "family": "curry_favors",
            "before_active": action_id == "stop_curry_favors",
            "after_active": action_id == "curry_favors",
            "task_before": action_id == "stop_curry_favors",
            "task_after": action_id == "curry_favors",
            "diplomat_required": True,
            "diplomat_context_verified": True,
            "available_diplomat_count": 2,
            "diplomat_assignment_verified": True,
            "execution_verified": True,
            "request_binding_verified": True,
        }
        event.update(overrides)
        return event

    def setUp(self) -> None:
        self.journal = DurableJournal(":memory:", "curry-contract", "curry-session")

    def tearDown(self) -> None:
        self.journal.close()

    def test_catalog_scope_and_empty_parameters(self):
        api = DiplomacyTools(self.journal)
        by_id = {item["action_id"]: item
                  for item in api.list_diplomatic_actions()["actions"]}
        for action_id in ("curry_favors", "stop_curry_favors"):
            action = by_id[action_id]
            self.assertEqual("curry_favors", action["native_identifier"])
            self.assertEqual({}, action["parameter_definitions"])
            self.assertEqual(["initiate"], list(action["phases"]))
            inspection = api.inspect_diplomatic_action(action_id, "FRA", "SAV")
            self.assertEqual("not_applicable", inspection["acceptance"]["applicability"])
            self.assertTrue(inspection["acceptance"]["complete"])
            with self.assertRaisesRegex(ValueError, "CURRY_FAVORS_PARAMETERS_UNSUPPORTED"):
                api.inspect_diplomatic_action(
                    action_id, "FRA", "SAV", parameters={"diplomat_id": 1})
            with self.assertRaisesRegex(ValueError, "CURRY_FAVORS_INITIATE_ONLY"):
                api.inspect_diplomatic_action(action_id, "FRA", "SAV", "accept")

    def test_ack_is_exact_and_isolated_from_other_families(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = self._installation(
                root, query_ack=True, caps=["native_curry_favors_submission",
                                            "native_improve_relations_query"])
            session = ObserverSession(installation, root / "eu4.exe")
            self.assertEqual(frozenset({"native_curry_favors_query"}),
                             session.installation_capabilities())
            copied, _ = self._installation(
                root, query_ack=None, submission_ack=None,
                caps=["native_curry_favors_query", "native_curry_favors_submission"])
            copied_session = ObserverSession(copied, root / "eu4.exe")
            self.assertEqual(frozenset(), copied_session.installation_capabilities())
            other, _ = self._installation(
                root, query_ack=None, submission_ack=True,
                caps=["native_improve_relations_query"])
            other_session = ObserverSession(other, root / "eu4.exe")
            self.assertNotIn("native_curry_favors_query",
                             other_session.installation_capabilities())
            self.assertIn("native_curry_favors_submission",
                          other_session.installation_capabilities())

    def _run_query_event(self, session: ObserverSession, action_id: str,
                         event_overrides: dict | None = None) -> dict:
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
                query_id = request.read_text(encoding="ascii").split()[2]
                request.unlink(missing_ok=True)
                event = self._native_event(
                    query_id, action_id, **(event_overrides or {}))
                with log.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            except BaseException as exc:
                errors.append(exc)

        thread = threading.Thread(target=writer)
        thread.start()
        ready = {"status": "ready", "state_id": "ready", "date_raw": 1,
                 "reasons": [], "complete": True}
        with patch.object(session, "health", return_value=ready), \
             patch("bridge.diplomacy.probe_identity",
                   return_value={"session_id": "curry-session"}):
            result = DiplomacyTools(self.journal, session).inspect_diplomatic_action(
                action_id, "FRA", "SAV")
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], errors)
        return result

    def test_query_uses_task_state_and_never_invents_acceptance_or_progress(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = self._installation(root, query_ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            result = self._run_query_event(session, "curry_favors")
            self.assertEqual("partial_native_rules",
                             result["interface_support"]["query"])
            self.assertEqual("curry_favors", result["family"])
            self.assertFalse(result["task_active"])
            self.assertTrue(result["task_state_verified"])
            self.assertEqual({"task_active": False, "complete": True},
                             result["relationship_state"])
            self.assertEqual("not_applicable", result["acceptance"]["applicability"])
            self.assertFalse(result["acceptance"]["prediction_available"])
            self.assertNotIn("progress", result)
            self.assertNotIn("monthly_growth", result)
            self.assertEqual(2, result["resources"]["diplomats"]["available_count"])

            invalid = self._run_query_event(
                session, "curry_favors", {"score_applicable": True})
            self.assertEqual("QUERY_NATIVE_RESULT_INVALID",
                             invalid["legality"]["reasons"][0]["code"])

            chinese = "原生规则拒绝获取人情"
            rejected = self._run_query_event(
                session, "curry_favors",
                {"native_validity": False,
                 "native_diagnostic_hex": chinese.encode("utf-8").hex()})
            self.assertEqual("unavailable", rejected["legality"]["status"])
            self.assertEqual(chinese, rejected["legality"]["reasons"][0]["text"])

    def test_inactive_stop_and_duplicate_start_report_the_verified_task_reason(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = self._installation(root, query_ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            for action, active, code in (
                    ("curry_favors", True, "NATIVE_CURRY_TASK_ALREADY_ACTIVE"),
                    ("stop_curry_favors", False, "NATIVE_CURRY_TASK_NOT_ACTIVE")):
                with self.subTest(action=action):
                    result = self._run_query_event(session, action, {
                        "native_validity": False, "task_active": active,
                        "native_diagnostic_hex": ""})
                    self.assertEqual("unavailable", result["legality"]["status"])
                    first = result["legality"]["reasons"][0]
                    self.assertEqual(code, first["code"])
                    self.assertIn("FRA", first["text"])
                    self.assertIn("SAV", first["text"])
                    self.assertEqual("native_rule", first["source"])

    def test_submission_ack_receipt_and_cross_family_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            query_only, _ = self._installation(root, query_ack=True)
            query_session = ObserverSession(query_only, root / "eu4.exe")
            self.assertEqual(
                "NATIVE_CURRY_FAVORS_SUBMISSION_CAPABILITY_MISSING",
                query_session.submit_curry_favors(
                    "curry-missing", "FRA", "SAV", "initiate", 1,
                    timeout=0)["reason_code"])

            installation, log = self._installation(
                root, submission_ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            request = root / "diplomacy-execute.req"
            errors: list[BaseException] = []

            def writer(family: str = "curry_favors") -> None:
                try:
                    deadline = time.monotonic() + 2
                    while not request.exists() and time.monotonic() < deadline:
                        time.sleep(0.001)
                    if not request.exists():
                        raise AssertionError("execute request was not published")
                    fields = request.read_text(encoding="ascii").strip().split("|")
                    request.unlink(missing_ok=True)
                    with log.open("a", encoding="utf-8", newline="\n") as stream:
                        stream.write(json.dumps(self._submission_receipt(
                            fields[1], fields[5], family=family)) + "\n")
                except BaseException as exc:
                    errors.append(exc)

            thread = threading.Thread(target=writer)
            thread.start()
            result = session.submit_curry_favors(
                "curry-submit", "FRA", "SAV", "initiate", 1, timeout=2)
            thread.join(2)
            self.assertEqual([], errors)
            self.assertEqual("submitted", result["status"])
            self.assertEqual("curry_favors", result["receipt"]["family"])

            thread = threading.Thread(target=writer)
            thread.start()
            stopped = session.submit_stop_curry_favors(
                "curry-stop-submit", "FRA", "SAV", "initiate", 1, timeout=2)
            thread.join(2)
            self.assertEqual([], errors)
            self.assertEqual("submitted", stopped["status"])
            self.assertEqual("stop_curry_favors", stopped["receipt"]["action_id"])

            thread = threading.Thread(target=lambda: writer("improve_relations"))
            thread.start()
            rejected = session.submit_stop_curry_favors(
                "curry-cross-family", "FRA", "SAV", "initiate", 1, timeout=2)
            thread.join(2)
            self.assertEqual([], errors)
            self.assertEqual("NATIVE_SUBMISSION_RESULT_INVALID", rejected["reason_code"])

    def test_execution_result_requires_family_variant_state_and_transition(self):
        valid = self._execution_event()
        accepted = ObserverSession._public_native_curry_favors_execution_result(
            valid, "curry-execution", "curry-session", "FRA", "SAV",
            "initiate", 1, "curry_favors")
        self.assertIsNotNone(accepted)
        self.assertEqual("executed", accepted["native_outcome"])
        for field, value in (
                ("family", "spy_network"), ("native_variant", 0),
                ("native_state", 1), ("request_binding_verified", False),
                ("before_active", True), ("task_before", True)):
            with self.subTest(field=field):
                self.assertIsNone(
                    ObserverSession._public_native_curry_favors_execution_result(
                        {**valid, field: value}, "curry-execution", "curry-session",
                        "FRA", "SAV", "initiate", 1, "curry_favors"))
        self.assertIsNone(ObserverSession._public_native_curry_favors_execution_result(
            valid, "curry-execution", "curry-session", "FRA", "SAV",
            "initiate", 1, "build_spy_network"))
        stop = ObserverSession._public_native_curry_favors_execution_result(
            self._execution_event("stop_curry_favors"), "curry-execution",
            "curry-session", "FRA", "SAV", "initiate", 1,
            "stop_curry_favors")
        self.assertIsNotNone(stop)
        self.assertEqual("executed", stop["native_outcome"])

    def test_execution_dedupes_and_survives_sqlite_reopen(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "journal.sqlite3"
            journal = DurableJournal(database, "curry-contract", "curry-session")
            session = CurryExecutionSession()
            api = DiplomacyTools(journal, session)
            submitted = api.execute_diplomatic_action(
                "curry-reopen", "curry_favors", "FRA", "SAV")
            self.assertEqual("submitted", submitted["status"])
            self.assertEqual(1, len(session.submit_calls))
            session.execution_event = self._execution_event()
            executed = api.get_diplomatic_result("curry-reopen")
            self.assertEqual("executed", executed["status"])
            again = api.execute_diplomatic_action(
                "curry-reopen", "curry_favors", "FRA", "SAV")
            self.assertTrue(again["idempotent"])
            self.assertEqual(1, len(session.submit_calls))
            journal.close()

            reopened = DurableJournal(database, "curry-contract", "curry-session")
            recovered = DiplomacyTools(
                reopened, CurryExecutionSession(self._execution_event())).get_diplomatic_result(
                    "curry-reopen")
            self.assertEqual("executed", recovered["status"])
            self.assertEqual("executed", recovered["game_outcome"])
            reopened.close()


if __name__ == "__main__":
    unittest.main()
