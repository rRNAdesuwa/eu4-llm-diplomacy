from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal


class DissolveSession:
    """Small session adapter exposing the already-verified dissolve contract."""

    def __init__(self, *, native_validity: bool = True,
                 alliance_after: bool = False,
                 drop_execution_proof: bool = False,
                 receipt_action: str = "dissolve_alliance"):
        self.session_id = "session-r24-dissolve"
        self.record = {"controlled_countries": ["FRA"]}
        self.capabilities = frozenset({"native_dissolve_submission"})
        self.native_validity = native_validity
        self.alliance_after = alliance_after
        self.drop_execution_proof = drop_execution_proof
        self.receipt_action = receipt_action
        self.submit_calls: list[tuple[str, str, str, str, int]] = []
        self.read_calls = 0

    def health(self) -> dict:
        return {"status": "ready", "state_id": "r24-state", "date_raw": 42,
                "reasons": [], "complete": True}

    def installation_capabilities(self) -> frozenset[str]:
        return self.capabilities

    def alliance_objects(self, actor: str, recipient: str) -> dict:
        return {"status": "observed", "items": [], "complete": False,
                "reason_code": "QUEUE_LIFECYCLE_NOT_RECOVERED"}

    def inspect_alliance(self, action_id: str, actor: str,
                        recipient: str, phase: str) -> dict:
        return {
            "display_predicate": True,
            "common_action_gate": True,
            "validity_called": True,
            "native_validity": self.native_validity,
            "initiation_gate": True,
            "ui_selection_checked": True,
            "native_visibility": True,
            "ui_enabled_gate_checked": True,
            "tooltip_gate": True,
            "full_rules_complete": True,
            "date_raw": 42,
            "reason_count": 0,
            "reason_items": [],
            "reason_items_truncated": False,
        }

    def submit_dissolve_alliance(self, request_id: str, actor: str,
                                 recipient: str, phase: str,
                                 date_raw: int) -> dict:
        self.submit_calls.append((request_id, actor, recipient, phase, date_raw))
        return {"status": "submitted", "receipt": {
            "event": "native_alliance_submission_result",
            "request_id": request_id,
            "action_id": self.receipt_action,
            "actor": actor,
            "recipient": recipient,
            "phase": phase,
            "date_raw": date_raw,
            "submitted": True,
            "native_queue_verified": True,
            "transport_ring_receipt": True,
            "native_sequence": 17,
            "native_origin": 1,
            "native_flags": 0,
        }}

    def _execution_event(self, request_id: str, actor: str,
                         recipient: str, phase: str, date_raw: int) -> dict:
        event = {
            "event": "native_alliance_execution_result",
            "request_id": request_id,
            "session_id": self.session_id,
            "action_id": "dissolve_alliance",
            "actor": actor,
            "recipient": recipient,
            "phase": phase,
            "date_raw": date_raw,
            "native_state": 0,
            "native_variant": 0,
            "alliance_before": True,
            "alliance_after": self.alliance_after,
            "execution_verified": True,
            "request_binding_verified": True,
            # These private values must be removed by the public reducer.
            "native_return_rva": "0x17067e0",
            "wrapper_address": "0x12345678",
            "source_address": "0x87654321",
        }
        if self.drop_execution_proof:
            event.pop("execution_verified")
            event.pop("request_binding_verified")
        return event

    def read_native_dissolve_result(self, request_id: str, actor: str,
                                    recipient: str, phase: str,
                                    date_raw: int) -> dict | None:
        self.read_calls += 1
        event = self._execution_event(request_id, actor, recipient, phase, date_raw)
        reduced = ObserverSession._public_native_dissolve_result(
            event, request_id, self.session_id, actor, recipient, phase, date_raw)
        if reduced is None:
            return None
        return {"status": reduced["native_outcome"], "result": reduced}


def _write_installation(root: Path, ack: dict) -> tuple[Path, Path]:
    installation = root / "installation.json"
    installation.write_text(json.dumps({
        "experiment_id": "r24-dissolve",
        "session_id": "session-r24-dissolve",
        "pid": 1,
        "creation_filetime": 2,
        "dll_sha256": "dll",
        "installation_returncode": 0,
    }), encoding="utf-8")
    log = root / "control-probe.jsonl"
    log.write_text(json.dumps({
        "event": "diplomacy_observer_installed",
        "session_id": "session-r24-dissolve",
        **ack,
    }) + "\n", encoding="utf-8")
    return installation, log


def _execution_event(**overrides: object) -> dict:
    event = {
        "event": "native_alliance_execution_result",
        "request_id": "dissolve_1",
        "session_id": "session-r24-dissolve",
        "action_id": "dissolve_alliance",
        "actor": "FRA",
        "recipient": "PRO",
        "phase": "initiate",
        "date_raw": 42,
        "native_state": 0,
        "native_variant": 0,
        "alliance_before": True,
        "alliance_after": False,
        "execution_verified": True,
        "request_binding_verified": True,
    }
    event.update(overrides)
    return event


class DissolveToolsTests(unittest.TestCase):
    def test_dissolve_ack_requires_top_level_literal_true(self) -> None:
        cases = (
            ({"native_dissolve_submission": True}, True),
            ({"caps": ["native_dissolve_submission"]}, False),
            ({"native_dissolve_submission": "true"}, False),
        )
        for ack, expected in cases:
            with self.subTest(ack=ack), tempfile.TemporaryDirectory() as temporary:
                installation, _ = _write_installation(Path(temporary), ack)
                session = ObserverSession(installation, Path(temporary) / "eu4.exe")
                self.assertEqual(
                    expected,
                    "native_dissolve_submission" in session.installation_capabilities(),
                )

    def test_dissolve_inspection_and_submission_execute_once_and_persist(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            journal_path = root / "journal.sqlite3"
            session = DissolveSession()
            with DurableJournal(journal_path, "experiment", session.session_id) as journal:
                api = DiplomacyTools(journal, session)
                inspection = api.inspect_diplomatic_action(
                    "dissolve_alliance", "FRA", "PRO", "initiate", {})
                self.assertEqual("available", inspection["authorization"]["status"])
                self.assertEqual("native_dissolve_submission",
                                 inspection["interface_support"]["execute"])
                first = api.execute_diplomatic_action(
                    "dissolve_1", "dissolve_alliance", "FRA", "PRO",
                    "initiate", {})
                self.assertEqual("executed", first["status"])
                self.assertTrue(first["submitted"])
                self.assertEqual("executed", first["game_outcome"])
                self.assertEqual(1, len(session.submit_calls))
                self.assertEqual({
                    "event", "request_id", "action_id", "actor", "recipient", "phase",
                    "date_raw", "native_state", "native_variant", "execution_verified",
                    "request_binding_verified", "alliance_before", "alliance_after",
                    "native_outcome",
                }, set(first["result"]))
                self.assertEqual("dissolve_alliance", first["result"]["action_id"])
                self.assertEqual(session.session_id, journal.get_request("dissolve_1").session_id)
                self.assertEqual("dissolve_1", first["result"]["request_id"])
                self.assertEqual(42, first["result"]["date_raw"])
                self.assertEqual(0, first["result"]["native_state"])
                self.assertEqual(0, first["result"]["native_variant"])
                self.assertTrue(first["result"]["alliance_before"])
                self.assertFalse(first["result"]["alliance_after"])
                self.assertTrue(first["result"]["execution_verified"])
                self.assertTrue(first["result"]["request_binding_verified"])

                repeated = api.execute_diplomatic_action(
                    "dissolve_1", "dissolve_alliance", "FRA", "PRO",
                    "initiate", {})
                self.assertTrue(repeated["idempotent"])
                self.assertEqual("executed", repeated["status"])
                self.assertEqual(1, len(session.submit_calls))

            with DurableJournal(journal_path, "experiment", session.session_id) as reopened:
                reopened_api = DiplomacyTools(reopened, DissolveSession())
                recovered = reopened_api.get_diplomatic_result("dissolve_1")
                self.assertEqual("executed", recovered["status"])
                self.assertEqual(first["result"], recovered["result"])
                self.assertEqual(first["evidence"], recovered["evidence"])

    def test_missing_proof_or_existing_alliance_stays_unknown(self) -> None:
        missing_proof = ObserverSession._public_native_dissolve_result(
            _execution_event(execution_verified=False), "dissolve_1",
            "session-r24-dissolve", "FRA", "PRO", "initiate", 42)
        self.assertIsNone(missing_proof)

        with DurableJournal(":memory:", "experiment", "session-r24-dissolve") as journal:
            session = DissolveSession(alliance_after=True)
            result = DiplomacyTools(journal, session).execute_diplomatic_action(
                "dissolve_unknown", "dissolve_alliance", "FRA", "PRO", "initiate", {})
            self.assertEqual("submitted", result["status"])
            self.assertEqual("unknown", result["game_outcome"])
            self.assertEqual("unknown", result["result"]["native_outcome"])
            self.assertNotEqual("accepted", result["status"])
            self.assertNotEqual("executed", result["status"])

        with DurableJournal(":memory:", "experiment", "session-r24-dissolve") as journal:
            session = DissolveSession(drop_execution_proof=True)
            result = DiplomacyTools(journal, session).execute_diplomatic_action(
                "dissolve_no_proof", "dissolve_alliance", "FRA", "PRO", "initiate", {})
            self.assertEqual("submitted", result["status"])
            self.assertEqual("unknown", result["game_outcome"])
            self.assertFalse(result.get("status") == "accepted")

    def test_unavailable_legality_does_not_call_dissolve_submitter(self) -> None:
        with DurableJournal(":memory:", "experiment", "session-r24-dissolve") as journal:
            session = DissolveSession(native_validity=False)
            api = DiplomacyTools(journal, session)
            inspection = api.inspect_diplomatic_action(
                "dissolve_alliance", "FRA", "PRO", "initiate", {})
            self.assertEqual("unavailable", inspection["legality"]["status"])
            result = api.execute_diplomatic_action(
                "dissolve_illegal", "dissolve_alliance", "FRA", "PRO", "initiate", {})
            self.assertEqual("invalidated", result["status"])
            self.assertEqual("NATIVE_LEGALITY_UNAVAILABLE",
                             result["result"]["reason"]["code"])
            self.assertEqual([], session.submit_calls)

    def test_wrong_action_submission_receipt_cannot_bind_dissolve_request(self) -> None:
        with DurableJournal(":memory:", "experiment", "session-r24-dissolve") as journal:
            session = DissolveSession(receipt_action="offer_alliance")
            result = DiplomacyTools(journal, session).execute_diplomatic_action(
                "dissolve_bad_receipt", "dissolve_alliance", "FRA", "PRO", "initiate", {})
            self.assertEqual("invalidated", result["status"])
            self.assertFalse(result["submitted"])
            self.assertEqual("NATIVE_SUBMISSION_RECEIPT_INVALID",
                             result["result"]["reason"]["code"])
            self.assertIsNone(journal.get_request("dissolve_bad_receipt").native_receipt)
            self.assertEqual(1, len(session.submit_calls))

    def test_public_dissolve_result_whitelist_rejects_wrong_action_and_private_addresses(self) -> None:
        event = _execution_event(
            native_return_rva="0x15801e2", source_address="0xabcdef",
            wrapper_address="0x123456")
        result = ObserverSession._public_native_dissolve_result(
            event, "dissolve_1", "session-r24-dissolve", "FRA", "PRO", "initiate", 42)
        self.assertIsNotNone(result)
        serialized = json.dumps(result, ensure_ascii=False)
        for private in ("native_return_rva", "source_address", "wrapper_address",
                        "0x15801e2", "0xabcdef", "0x123456"):
            self.assertNotIn(private, serialized)

        wrong_action = ObserverSession._public_native_dissolve_result(
            _execution_event(action_id="offer_alliance"), "dissolve_1",
            "session-r24-dissolve", "FRA", "PRO", "initiate", 42)
        self.assertIsNone(wrong_action)

        for field, value in (("session_id", "other-session"),
                             ("request_id", "other-request"),
                             ("date_raw", 43)):
            with self.subTest(field=field):
                mismatched = ObserverSession._public_native_dissolve_result(
                    _execution_event(**{field: value}), "dissolve_1",
                    "session-r24-dissolve", "FRA", "PRO", "initiate", 42)
                self.assertIsNone(mismatched)


if __name__ == "__main__":
    unittest.main()
