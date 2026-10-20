from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal


class SemanticDiplomacySession:
    """Small in-memory session for the public inspect/execute facade."""

    def __init__(self, *, required: bool, count: int,
                 capabilities: set[str]) -> None:
        self.record = {"controlled_countries": ["FRA"]}
        self._capabilities = frozenset(capabilities)
        self.native = {
            "ui_selection_checked": True,
            "native_visibility": True,
            "ui_enabled_gate_checked": True,
            "common_action_gate": True,
            "validity_called": True,
            "native_validity": True,
            "initiation_gate": True,
            "tooltip_gate": True,
            "full_rules_complete": True,
            "score_applicable": False,
            "score_available": False,
            "acceptance_predicate_available": False,
            "date_raw": 1,
            "diplomat_context_readable": True,
            "diplomat_required": required,
            "available_diplomat_count": count,
        }
        self.inspect_calls: list[tuple[str, str, str, str]] = []
        self.submit_calls: list[tuple[str, str, str, str, str]] = []

    def health(self) -> dict:
        return {
            "status": "ready",
            "state_id": "semantic-ready",
            "date_raw": 1,
            "reasons": [],
            "complete": True,
        }

    def alliance_objects(self, actor: str, recipient: str) -> dict:
        return {"status": "observed", "items": [], "complete": False}

    def installation_capabilities(self) -> frozenset[str]:
        return self._capabilities

    def _native(self, action_id: str, actor: str, recipient: str,
                phase: str) -> dict:
        self.inspect_calls.append((action_id, actor, recipient, phase))
        return dict(self.native)

    def inspect_alliance(self, action_id: str, actor: str, recipient: str,
                         phase: str) -> dict:
        return self._native(action_id, actor, recipient, phase)

    def inspect_improve_relations(self, action_id: str, actor: str,
                                  recipient: str, phase: str) -> dict:
        return self._native(action_id, actor, recipient, phase)

    def submit_offer_alliance(self, request_id: str, actor: str,
                              recipient: str, phase: str,
                              date_raw: int) -> dict:
        self.submit_calls.append(("offer_alliance", request_id, actor,
                                  recipient, phase))
        return {"status": "failed", "reason_code": "TEST_UNEXPECTED_SUBMIT"}

    def submit_stop_improving_relations(self, request_id: str, actor: str,
                                        recipient: str, phase: str,
                                        date_raw: int) -> dict:
        self.submit_calls.append(("stop_improving_relations", request_id,
                                  actor, recipient, phase))
        return {"status": "failed", "reason_code": "TEST_STOP_SUBMITTED"}


def _write_observer_files(root: Path, *, declare_war: bool = False) -> tuple[Path, Path]:
    session_id = "diplomat-integration-session"
    installation = root / "installation.json"
    installation.write_text(json.dumps({
        "experiment_id": "diplomat-integration",
        "session_id": session_id,
        "pid": 1,
        "creation_filetime": 2,
        "dll_sha256": "dll",
        "installation_returncode": 0,
    }), encoding="utf-8")
    ack = {
        "event": "diplomacy_observer_installed",
        "session_id": session_id,
        "caps": ["native_offer_submission"],
    }
    if declare_war:
        ack["native_declare_war_submission"] = True
    log = root / "control-probe.jsonl"
    log.write_text(json.dumps(ack) + "\n", encoding="utf-8")
    return installation, log


def _write_rejection_when_request_appears(
        root: Path, *, legacy: bool = False,
        overrides: dict[str, object] | None = None,
        errors: list[str]) -> threading.Thread:
    request = root / "diplomacy-execute.req"
    log = root / "control-probe.jsonl"

    def writer() -> None:
        deadline = time.monotonic() + 2
        while not request.exists() and time.monotonic() < deadline:
            time.sleep(0.001)
        if not request.exists():
            errors.append("execute request was not published")
            return
        try:
            fields = request.read_text(encoding="ascii").rstrip("\n").split("|")
            event: dict[str, object] = {
                "event": "native_alliance_execution_rejected",
                "request_id": fields[1],
                "session_id": fields[2],
                "submitted": False,
                "reason_code": "NATIVE_DIPLOMAT_UNAVAILABLE",
            }
            if not legacy:
                event.update({
                    "actor": fields[6],
                    "recipient": fields[7],
                    "phase": fields[8],
                    "date_raw": int(fields[4]),
                    "action_id": fields[5],
                    "reason_source": "native_rule",
                })
            if overrides:
                event.update(overrides)
            request.unlink(missing_ok=True)
            with log.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(event) + "\n")
        except (IndexError, OSError, ValueError, UnicodeError) as exc:
            errors.append(str(exc))

    thread = threading.Thread(target=writer)
    thread.start()
    return thread


class DiplomatAvailabilityIntegrationTests(unittest.TestCase):
    def test_inspect_and_execute_offer_are_blocked_before_submit_and_result_keeps_reason(self):
        session = SemanticDiplomacySession(
            required=True,
            count=0,
            capabilities={"native_offer_submission"},
        )
        with DurableJournal(":memory:", "diplomat-test", "semantic-session") as journal:
            api = DiplomacyTools(journal, session)
            inspection = api.inspect_diplomatic_action(
                "offer_alliance", "FRA", "SAV")
            self.assertEqual("unavailable", inspection["legality"]["status"])
            self.assertTrue(any(
                item.get("code") == "NATIVE_DIPLOMAT_UNAVAILABLE"
                for item in inspection["legality"]["reasons"]))
            self.assertEqual(0, inspection["resources"]["diplomats"]["available_count"])

            result = api.execute_diplomatic_action(
                "offer-zero", "offer_alliance", "FRA", "SAV")
            self.assertEqual("invalidated", result["status"])
            self.assertEqual([], session.submit_calls)
            stored_reason_codes = [
                item.get("code")
                for item in result["result"]["inspection"]["legality"]["reasons"]
            ]
            self.assertIn("NATIVE_DIPLOMAT_UNAVAILABLE", stored_reason_codes)

            reread = api.get_diplomatic_result("offer-zero")
            self.assertEqual("invalidated", reread["status"])
            self.assertIn(
                "NATIVE_DIPLOMAT_UNAVAILABLE",
                [item.get("code") for item in
                 reread["result"]["inspection"]["legality"]["reasons"]],
            )

    def test_stop_improving_relations_does_not_use_zero_diplomats_as_a_gate(self):
        session = SemanticDiplomacySession(
            required=False,
            count=0,
            capabilities={
                "native_improve_relations_query",
                "native_improve_relations_submission",
            },
        )
        with DurableJournal(":memory:", "diplomat-test", "semantic-session") as journal:
            api = DiplomacyTools(journal, session)
            inspection = api.inspect_diplomatic_action(
                "stop_improving_relations", "FRA", "SAV")
            self.assertEqual("available", inspection["legality"]["status"])
            self.assertEqual(0, inspection["resources"]["diplomats"]["available_count"])
            self.assertFalse(any(
                item.get("code") in {
                    "NATIVE_DIPLOMAT_UNAVAILABLE",
                    "NATIVE_DIPLOMAT_CONTEXT_UNAVAILABLE",
                }
                for item in inspection["legality"]["reasons"]))

            result = api.execute_diplomatic_action(
                "stop-zero", "stop_improving_relations", "FRA", "SAV")
            self.assertEqual("stop_improving_relations", session.submit_calls[0][0])
            self.assertNotEqual("NATIVE_LEGALITY_UNAVAILABLE",
                                result.get("reason", {}).get("code"))

    def test_generic_submit_consumes_bound_rejection_without_timeout(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = _write_observer_files(root)
            session = ObserverSession(installation, root / "eu4.exe")
            errors: list[str] = []
            writer = _write_rejection_when_request_appears(root, errors=errors)
            result = session.submit_offer_alliance(
                "generic-reject", "FRA", "SAV", "initiate", 1, timeout=1)
            writer.join(2)
            self.assertFalse(writer.is_alive())
            self.assertEqual([], errors)
            self.assertEqual("failed", result["status"])
            self.assertEqual("NATIVE_DIPLOMAT_UNAVAILABLE", result["reason_code"])
            self.assertTrue(result["submitted"] is False)
            self.assertTrue(result["binding_complete"])
            self.assertEqual("native_rule", result["reason"]["source"])
            self.assertEqual("unavailable", result["legality"]["status"])

    def test_declare_war_submit_consumes_bound_rejection_without_timeout(self):
        parameters = {
            "casus_belli": "cb_core",
            "war_goal": {"province_id": 177, "beneficiary": "FRA"},
            "call_allies": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = _write_observer_files(root, declare_war=True)
            session = ObserverSession(installation, root / "eu4.exe")
            errors: list[str] = []
            writer = _write_rejection_when_request_appears(root, errors=errors)
            result = session.submit_declare_war(
                "declare-reject", "FRA", "BUR", "initiate", 1,
                parameters, timeout=1)
            writer.join(2)
            self.assertFalse(writer.is_alive())
            self.assertEqual([], errors)
            self.assertEqual("failed", result["status"])
            self.assertEqual("NATIVE_DIPLOMAT_UNAVAILABLE", result["reason_code"])
            self.assertTrue(result["binding_complete"])
            self.assertEqual("native_rule", result["reason"]["source"])

    def test_generic_rejection_rejects_wrong_actor_date_and_action_bindings(self):
        variants = (
            {"actor": "ENG"},
            {"date_raw": 2},
            {"action_id": "declare_war"},
        )
        for index, overrides in enumerate(variants):
            with self.subTest(overrides=overrides), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                installation, _ = _write_observer_files(root)
                session = ObserverSession(installation, root / "eu4.exe")
                errors: list[str] = []
                writer = _write_rejection_when_request_appears(
                    root, overrides=overrides, errors=errors)
                result = session.submit_offer_alliance(
                    f"binding-{index}", "FRA", "SAV", "initiate", 1,
                    timeout=1)
                writer.join(2)
                self.assertFalse(writer.is_alive())
                self.assertEqual([], errors)
                self.assertEqual("failed", result["status"])
                self.assertEqual("NATIVE_REJECTION_BINDING_INVALID",
                                 result["reason_code"])
                self.assertFalse(result.get("binding_complete", False))

    def test_legacy_request_session_reason_rejection_is_immediate_and_unbound(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = _write_observer_files(root)
            session = ObserverSession(installation, root / "eu4.exe")
            errors: list[str] = []
            writer = _write_rejection_when_request_appears(
                root, legacy=True, errors=errors)
            result = session.submit_offer_alliance(
                "legacy-reject", "FRA", "SAV", "initiate", 1, timeout=1)
            writer.join(2)
            self.assertFalse(writer.is_alive())
            self.assertEqual([], errors)
            self.assertEqual("failed", result["status"])
            self.assertEqual("NATIVE_DIPLOMAT_UNAVAILABLE", result["reason_code"])
            self.assertFalse(result["binding_complete"])
            self.assertEqual("runtime_error", result["reason"]["source"])
            self.assertEqual("unknown", result["legality"]["status"])


if __name__ == "__main__":
    unittest.main()
