from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal


SESSION_ID = "saved-pending-session"
INBOUND_CAPABILITY = "native_inbound_alliance"


class SavedPendingDiscoveryTests(unittest.TestCase):
    """Contract tests for native pending offers restored after save/load."""

    @staticmethod
    def _event(action_id: str, family: str, proposal_id: int,
               *, session_id: str = SESSION_ID, **overrides) -> dict:
        event = {
            "event": "native_diplomacy_inbound_pending_restored",
            "session_id": session_id,
            "proposal_id": proposal_id,
            "action_id": action_id,
            "family": family,
            "extra60": 0,
            "phase": "initiate",
            "actor": "SAV",
            "mirror": "SAV",
            "recipient": "FRA",
            "decision_country": "FRA",
            "state34": 0,
            "variant38": 1,
            "pending_source": "native_saved_pending_queue",
            "queue_readable": True,
            "list_integrity": True,
            "payload_readable": True,
            "decision_country_verified": True,
            "source_verified": True,
            "saved_queue_restored": True,
            "native_queue_membership_verified": True,
            "new_entry": False,
            "call_redirected": False,
            "business_result": "pending_restored",
            # These fields stand in for bounded native diagnostics.  They
            # must remain private when the event is projected publicly.
            "native_address": "0x1234",
            "token3c": 99,
        }
        event.update(overrides)
        return event

    @staticmethod
    def _legacy_event(proposal_id: int = 201, **overrides) -> dict:
        event = {
            "event": "native_alliance_inbound_offer",
            "session_id": SESSION_ID,
            "proposal_id": proposal_id,
            "action_id": "offer_alliance",
            "family": "alliance",
            "phase": "initiate",
            "actor": "PRO",
            "mirror": "PRO",
            "recipient": "FRA",
            "decision_country": "FRA",
            "state34": 0,
            "variant38": 1,
            "queue_readable": True,
            "list_integrity": True,
            "new_entry": True,
            "payload_readable": True,
            "decision_country_verified": True,
            "source_verified": True,
            "call_redirected": True,
            "business_result": "pending_observed",
        }
        event.update(overrides)
        return event

    @staticmethod
    def _installation(root: Path, *events: dict):
        installation = root / "installation.json"
        installation.write_text(json.dumps({
            "experiment_id": "saved-pending-test",
            "session_id": SESSION_ID,
            "pid": 1,
            "creation_filetime": 2,
            "dll_sha256": "test-dll",
            "installation_returncode": 0,
        }), encoding="utf-8")
        lines = [{
            "event": "diplomacy_observer_installed",
            "session_id": SESSION_ID,
            INBOUND_CAPABILITY: True,
        }]
        lines.extend(events)
        (root / "control-probe.jsonl").write_text(
            "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines),
            encoding="utf-8",
        )
        return installation

    def test_all_five_families_restore_with_one_safe_opaque_offer_each(self):
        cases = (
            ("offer_alliance", "alliance", "SAV"),
            ("offer_royal_marriage", "royal_marriage", "PRO"),
            ("support_independence", "support_independence", "GEN"),
            ("ask_military_access", "military_access", "LIT"),
            ("offer_vassalization", "vassalization", "BUR"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            events = []
            for index, (action_id, family, actor) in enumerate(cases, 101):
                events.append(self._event(action_id, family, index, actor=actor,
                                          mirror=actor))
            installation = self._installation(root, *events)
            session = ObserverSession(installation, root / "eu4.exe")

            first = session.read_native_alliance_inbound_offers()
            second = session.read_native_alliance_inbound_offers()

            self.assertEqual(5, len(first))
            self.assertEqual(first, second)
            self.assertEqual(
                {"alliance", "royal_marriage", "support_independence",
                 "military_access", "vassalization"},
                {item["family"] for item in first},
            )
            self.assertEqual({"saved_native_pending"},
                             {item.get("source") for item in first})
            for item in first:
                context = session._native_alliance_inbound_context(item["proposal_id"])
                self.assertIsNotNone(context)
                self.assertEqual(item["family"], context["family"])
                self.assertEqual("FRA", context["recipient"])
            public_text = json.dumps(first, ensure_ascii=False)
            for private_name in ("native_proposal_id", "session_id", "token3c",
                                 "native_address", "pending_source", "RVA"):
                self.assertNotIn(private_name, public_text)

            journal = DurableJournal(":memory:", "saved-pending-test", SESSION_ID)
            try:
                api = DiplomacyTools(journal, session)
                projected = api._read_inbound_proposals({
                    "status": "ready", "state_id": "opaque", "date_raw": 1,
                })
                self.assertEqual(first, projected)
            finally:
                journal.close()

    def test_legacy_offer_keeps_old_contract_without_restored_source(self):
        legacy = self._legacy_event()
        self.assertTrue(ObserverSession._valid_native_inbound_offer_event(
            legacy, SESSION_ID))
        self.assertFalse(ObserverSession._valid_native_inbound_pending_restored_event(
            legacy, SESSION_ID))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = self._installation(root, legacy)
            session = ObserverSession(installation, root / "eu4.exe")
            offers = session.read_native_alliance_inbound_offers()
            self.assertEqual(1, len(offers))
            self.assertNotIn("source", offers[0])
            context = session._native_alliance_inbound_context(
                offers[0]["proposal_id"])
            self.assertEqual("alliance", context["family"])
            self.assertEqual(201, context["native_proposal_id"])

    def test_restored_proof_is_strict_about_identity_and_queue_state(self):
        base = self._event("offer_alliance", "alliance", 300)
        invalid = [
            {"pending_source": None},
            {"source_verified": False},
            {"saved_queue_restored": False},
            {"native_queue_membership_verified": False},
            {"session_id": "other-session"},
            {"actor": "FRA", "mirror": "FRA"},
            {"mirror": "PRO"},
            {"recipient": "SAV", "decision_country": "SAV"},
            {"action_id": "offer_royal_marriage"},
            {"family": "royal_marriage"},
            {"new_entry": True},
            {"call_redirected": True},
            {"state34": 1},
            {"variant38": 2},
            {"extra60": 1},
            {"business_result": "accepted"},
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            events = []
            for index, change in enumerate(invalid, 301):
                event = dict(base)
                event["proposal_id"] = index
                event.update(change)
                events.append(event)
            valid = dict(base)
            valid["proposal_id"] = 999
            events.append(valid)
            installation = self._installation(root, *events)
            session = ObserverSession(installation, root / "eu4.exe")
            offers = session.read_native_alliance_inbound_offers()
            self.assertEqual(1, len(offers))
            self.assertEqual("saved_native_pending", offers[0]["source"])

    def test_public_adapter_does_not_accept_arbitrary_source_or_private_fields(self):
        journal = DurableJournal(":memory:", "saved-pending-test", SESSION_ID)
        try:
            item = {
                "proposal_id": "a" * 32,
                "action_id": "offer_alliance",
                "family": "alliance",
                "actor": "SAV",
                "recipient": "FRA",
                "decision_country": "FRA",
                "observer_status": "observed_pending",
                "source": "native_address_leak",
                "native_proposal_id": 99,
                "token3c": 10,
            }
            safe = DiplomacyTools._safe_inbound_proposal(item)
            self.assertIsNotNone(safe)
            self.assertNotIn("source", safe)
            self.assertNotIn("native_proposal_id", safe)
            self.assertNotIn("token3c", safe)
        finally:
            journal.close()


if __name__ == "__main__":
    unittest.main()
