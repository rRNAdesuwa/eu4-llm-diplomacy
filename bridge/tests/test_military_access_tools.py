from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal


class MilitaryAccessSession:
    """Small in-memory adapter for the public Military Access contract."""

    session_id = "military-session"

    def __init__(self, *, response_event: dict | None = None,
                 execution_event: dict | None = None,
                 inbound_response: dict | None = None):
        self.record = {"controlled_countries": ["FRA"]}
        self.capabilities = frozenset({
            "native_military_access_query",
            "native_military_access_submission",
            "native_inbound_alliance",
            "native_inbound_military_access_response",
        })
        self.response_event = response_event
        self.execution_event = execution_event
        self.inbound_response = inbound_response
        self.submit_calls: list[tuple[str, str]] = []
        self._private = {
            "proposal_id": 17,
            "actor": "SAV",
            "recipient": "FRA",
            "session_id": self.session_id,
            "action_id": "ask_military_access",
            "family": "military_access",
            "native_proposal_id": 17,
        }

    def health(self) -> dict:
        return {"status": "ready", "state_id": "ready", "date_raw": 1,
                "reasons": [], "complete": True}

    def installation_capabilities(self) -> frozenset[str]:
        return self.capabilities

    @staticmethod
    def _inspection_event(action_id: str, *, actor: str = "FRA",
                          recipient: str = "SAV") -> dict:
        active = action_id == "cancel_military_access"
        return {
            "event": "native_alliance_inspection",
            "action_id": action_id,
            "family": "military_access",
            "military_access_active": active,
            "military_access_state_verified": True,
            "relationship_state": {
                "military_access_active": active, "complete": True,
            },
            "actor": actor,
            "recipient": recipient,
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
            "score_applicable": True,
            "score_available": True,
            "acceptance_predicate_available": True,
            "native_would_accept": True,
            "native_total_raw": 12,
            "acceptance_threshold_raw": 0,
            "diplomat_context_readable": True,
            "diplomat_required": True,
            "available_diplomat_count": 2,
            "reason_container_readable": True,
            "reason_count": 0,
            "reason_items": [],
            "reason_items_truncated": False,
            "diagnostic_readable": True,
            "native_diagnostic_hex": "6f6b",
            "diagnostic_truncated": False,
        }

    def inspect_military_access(self, action_id: str, actor: str,
                                recipient: str, phase: str) -> dict:
        return self._inspection_event(action_id, actor=actor, recipient=recipient)

    @staticmethod
    def _receipt(request_id: str, action_id: str, recipient: str = "SAV") -> dict:
        return {
            "event": "native_alliance_submission_result",
            "request_id": request_id,
            "session_id": MilitaryAccessSession.session_id,
            "action_id": action_id,
            "actor": "FRA",
            "recipient": recipient,
            "phase": "initiate",
            "date_raw": 1,
            "submitted": True,
            "native_queue_verified": True,
            "transport_ring_receipt": True,
            "native_sequence": 7,
            "native_origin": 65535,
            "native_flags": 0,
        }

    def _submit(self, request_id: str, action_id: str, recipient: str) -> dict:
        self.submit_calls.append((request_id, action_id))
        return {"status": "submitted", "receipt": self._receipt(
            request_id, action_id, recipient)}

    def submit_ask_military_access(self, request_id: str, actor: str,
                                   recipient: str, phase: str, date_raw: int) -> dict:
        return self._submit(request_id, "ask_military_access", recipient)

    def submit_cancel_military_access(self, request_id: str, actor: str,
                                      recipient: str, phase: str, date_raw: int) -> dict:
        return self._submit(request_id, "cancel_military_access", recipient)

    def _read(self, request_id: str, actor: str, recipient: str,
              phase: str, date_raw: int, action_id: str) -> dict | None:
        event = (self.response_event if action_id == "ask_military_access"
                 else self.execution_event)
        if event is None:
            return None
        event = {**event, "request_id": request_id, "session_id": self.session_id,
                 "action_id": action_id, "actor": actor, "recipient": recipient,
                 "phase": phase, "date_raw": date_raw}
        parser = (ObserverSession._public_native_military_access_response_result
                  if action_id == "ask_military_access"
                  else ObserverSession._public_native_military_access_execution_result)
        result = parser(event, request_id, self.session_id, actor, recipient, phase, date_raw)
        if result is None:
            return {"status": "invalid", "reason_code": "NATIVE_RESPONSE_RESULT_INVALID"}
        return {"status": result["native_outcome"], "result": result}

    def read_native_military_access_response(
            self, request_id: str, actor: str, recipient: str,
            phase: str, date_raw: int,
            action_id: str = "ask_military_access") -> dict | None:
        return self._read(request_id, actor, recipient, phase, date_raw, action_id)

    def read_native_military_access_execution(
            self, request_id: str, actor: str, recipient: str,
            phase: str, date_raw: int,
            action_id: str = "cancel_military_access") -> dict | None:
        return self._read(request_id, actor, recipient, phase, date_raw, action_id)

    def read_native_alliance_inbound_offers(self) -> list[dict]:
        return [{
            "proposal_id": "a" * 32,
            "action_id": "ask_military_access",
            "family": "military_access",
            "actor": "SAV",
            "recipient": "FRA",
            "decision_country": "FRA",
            "observer_status": "observed_pending",
        }]

    def _native_alliance_inbound_context(self, public_id: object) -> dict | None:
        if public_id != "a" * 32:
            return None
        return dict(self._private)

    @staticmethod
    def _inbound_inspection(**overrides: object) -> dict:
        event = {
            "event": "native_alliance_inbound_inspection",
            "action_id": "ask_military_access",
            "family": "military_access",
            "actor": "SAV",
            "recipient": "FRA",
            "phase": "accept",
            "native_proposal_id": 17,
            "date_raw": 1,
            "pending_active": True,
            "decision_country": "FRA",
            "decision_country_verified": True,
            "native_validity": True,
            "response_rules_complete": True,
            "military_access_active": False,
            "military_access_state_verified": True,
            "reason": "none",
        }
        event.update(overrides)
        return event

    def inspect_native_inbound_response(self, query_id: str, actor: str,
                                        phase: str, date_raw: int,
                                        native_proposal_id: int,
                                        action_id: str = "offer_alliance") -> dict:
        event = self._inbound_inspection(
            query_id=query_id, session_id=self.session_id, actor=actor,
            phase=phase, date_raw=date_raw, native_proposal_id=native_proposal_id)
        return ObserverSession._public_native_inbound_inspection(event, date_raw, action_id)

    def submit_native_inbound_response(self, request_id: str, actor: str,
                                       recipient: str, phase: str, date_raw: int,
                                       native_proposal_id: int,
                                       action_id: str = "offer_alliance") -> dict:
        return {"status": "submitted", "receipt": {
            **self._receipt(request_id, action_id, recipient),
            "actor": actor, "recipient": recipient, "phase": phase,
            "native_proposal_id": native_proposal_id,
        }}

    def read_native_military_access_inbound_response(
            self, request_id: str, actor: str, recipient: str,
            phase: str, date_raw: int, native_proposal_id: int) -> dict | None:
        event = self.inbound_response
        if event is None:
            return None
        event = {**event, "request_id": request_id, "session_id": self.session_id,
                 "action_id": "ask_military_access", "actor": actor,
                 "recipient": recipient, "phase": phase, "date_raw": date_raw}
        result = ObserverSession._public_native_inbound_response_result(
            event, request_id, self.session_id, actor, phase, date_raw,
            native_proposal_id, "ask_military_access")
        if result is None:
            return {"status": "invalid", "reason_code": "NATIVE_RESPONSE_RESULT_INVALID"}
        return {"status": result["native_outcome"], "result": result}


class MilitaryAccessToolsTests(unittest.TestCase):
    @staticmethod
    def _response_event(**overrides: object) -> dict:
        event = {
            "event": "native_diplomacy_relation_response_result",
            "request_id": "military-response",
            "session_id": "military-session",
            "action_id": "ask_military_access",
            "actor": "FRA",
            "recipient": "SAV",
            "phase": "initiate",
            "date_raw": 1,
            "outcome": "accepted",
            "native_variant": 1,
            "native_state": 2,
            "family": "military_access",
            "military_access_before": False,
            "military_access_after": True,
            "response_verified": True,
            "request_binding_verified": True,
        }
        event.update(overrides)
        return event

    @staticmethod
    def _cancel_event(**overrides: object) -> dict:
        event = {
            "event": "native_diplomacy_relation_execution_result",
            "request_id": "military-cancel",
            "session_id": "military-session",
            "action_id": "cancel_military_access",
            "actor": "FRA",
            "recipient": "SAV",
            "phase": "initiate",
            "date_raw": 1,
            "outcome": "executed",
            "native_variant": 0,
            "native_state": 0,
            "family": "military_access",
            "military_access_before": True,
            "military_access_after": False,
            "execution_verified": True,
            "request_binding_verified": True,
        }
        event.update(overrides)
        return event

    @staticmethod
    def _inbound_response(**overrides: object) -> dict:
        event = {
            "event": "native_diplomacy_relation_response_result",
            "request_id": "military-inbound",
            "session_id": "military-session",
            "action_id": "ask_military_access",
            "actor": "SAV",
            "recipient": "FRA",
            "phase": "accept",
            "date_raw": 1,
            "outcome": "accepted",
            "native_variant": 1,
            "native_state": 2,
            "family": "military_access",
            "military_access_before": False,
            "military_access_after": True,
            "response_verified": True,
            "request_binding_verified": True,
            "pending_removed": True,
        }
        event.update(overrides)
        return event

    def setUp(self) -> None:
        self.journal = DurableJournal(":memory:", "military-contract", "military-session")

    def tearDown(self) -> None:
        self.journal.close()

    def test_catalog_ack_scope_and_relationship_query(self):
        session = MilitaryAccessSession()
        api = DiplomacyTools(self.journal, session)
        by_id = {item["action_id"]: item for item in api.list_diplomatic_actions()["actions"]}
        ask = by_id["ask_military_access"]
        cancel = by_id["cancel_military_access"]
        self.assertEqual("military_access", ask["native_identifier"])
        self.assertEqual("military_access", cancel["native_identifier"])
        self.assertEqual({}, ask["parameter_definitions"])
        self.assertEqual({}, cancel["parameter_definitions"])
        self.assertEqual("applicable", api.inspect_diplomatic_action(
            "ask_military_access", "FRA", "SAV")["acceptance"]["applicability"])
        self.assertEqual("not_applicable", api.inspect_diplomatic_action(
            "cancel_military_access", "FRA", "SAV")["acceptance"]["applicability"])
        query = api.inspect_diplomatic_action("cancel_military_access", "FRA", "SAV")
        self.assertEqual("available", query["legality"]["status"])
        self.assertEqual({"military_access_active": True, "complete": True},
                         query["relationship_state"])
        self.assertEqual("native_military_access_submission",
                         query["interface_support"]["execute"])

        caps_only = MilitaryAccessSession()
        caps_only.capabilities = frozenset({"native_support_independence_query"})
        actions = {item["action_id"]: item for item in DiplomacyTools(
            self.journal, caps_only).list_diplomatic_actions()["actions"]}
        self.assertEqual("unimplemented",
                         actions["ask_military_access"]["phases"]["initiate"]["query"])

    def test_real_scored_ask_inspections_pass_common_acceptance_validation(self):
        fixture_path = Path(__file__).parent / "fixtures" / (
            "military_access_r32_native_inspections.json")
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertEqual(1, fixture["fixture_version"])
        self.assertEqual(2, len(fixture["events"]))
        for item in fixture["events"]:
            event = item["event"]
            canonical = json.dumps(
                event, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False).encode("utf-8")
            self.assertEqual(item["event_sha256"], hashlib.sha256(canonical).hexdigest())
            self.assertTrue(ObserverSession._valid_native_inspection(
                event, "ask_military_access", "FRA", event["recipient"],
                "initiate", event["date_raw"]))
            semantic = ObserverSession._semantic_inspection(event, {})
            self.assertEqual("military_access", semantic["family"])
            self.assertTrue(semantic["score_applicable"])
            self.assertTrue(semantic["score_available"])
            self.assertTrue(semantic["acceptance_predicate_available"])
            self.assertTrue(semantic["native_would_accept"])
            self.assertEqual(event["native_total_raw"], semantic["native_total_raw"])
        self.assertFalse(ObserverSession._valid_native_inspection(
            {**fixture["events"][0]["event"], "action_id": "cancel_military_access"},
            "cancel_military_access", "FRA", "SAV", "initiate",
            fixture["events"][0]["event"]["date_raw"]))

    def test_real_r32_response_fixture_recovers_rejected_and_accepted_results(self):
        fixture_path = Path(__file__).parent / "fixtures" / (
            "military_access_r32_native_events.json")
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertEqual(1, fixture["fixture_version"])
        self.assertEqual(2, len(fixture["events"]))
        expected_outcomes = {
            "r32_military_access_bur_rejected_response": ("BUR", "rejected", 1, False),
            "r32_military_access_sav_accepted_response": ("SAV", "accepted", 2, True),
        }
        for item in fixture["events"]:
            event = item["event"]
            source = Path(item["source_path"])
            self.assertEqual(item["source_file_sha256"], hashlib.sha256(
                source.read_bytes()).hexdigest())
            canonical = json.dumps(
                event, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False).encode("utf-8")
            self.assertEqual(item["event_sha256"], hashlib.sha256(canonical).hexdigest())
            recipient, outcome, state, after = expected_outcomes[item["fixture_id"]]
            result = ObserverSession._public_native_military_access_response_result(
                event, event["request_id"], event["session_id"], "FRA", recipient,
                "initiate", event["date_raw"])
            self.assertIsNotNone(result)
            self.assertEqual(outcome, result["native_outcome"])
            self.assertEqual(state, result["native_state"])
            self.assertFalse(result["military_access_before"])
            self.assertIs(after, result["military_access_after"])
            self.assertFalse(result["pending_removed"])
            self.assertIsNone(ObserverSession._public_native_military_access_response_result(
                {**event, "family": "support_independence"}, event["request_id"],
                event["session_id"], "FRA", recipient, "initiate", event["date_raw"]))

    def test_outbound_response_cancel_and_family_variant_binding(self):
        accepted = ObserverSession._public_native_military_access_response_result(
            self._response_event(), "military-response", "military-session", "FRA", "SAV",
            "initiate", 1)
        self.assertEqual("accepted", accepted["native_outcome"])
        rejected = ObserverSession._public_native_military_access_response_result(
            self._response_event(outcome="rejected", native_state=1,
                                 military_access_after=False),
            "military-response", "military-session", "FRA", "SAV", "initiate", 1)
        self.assertEqual("rejected", rejected["native_outcome"])
        cancelled = ObserverSession._public_native_military_access_execution_result(
            self._cancel_event(), "military-cancel", "military-session", "FRA", "SAV",
            "initiate", 1)
        self.assertEqual("executed", cancelled["native_outcome"])
        self.assertIsNone(ObserverSession._public_native_military_access_response_result(
            self._response_event(family="support_independence"),
            "military-response", "military-session", "FRA", "SAV", "initiate", 1))
        self.assertIsNone(ObserverSession._public_native_military_access_response_result(
            self._response_event(native_variant=0, mode=1),
            "military-response", "military-session", "FRA", "SAV", "initiate", 1))
        self.assertIsNone(ObserverSession._public_native_military_access_response_result(
            self._response_event(native_state=2.0),
            "military-response", "military-session", "FRA", "SAV", "initiate", 1))
        inconsistent = ObserverSession._public_native_military_access_execution_result(
            self._cancel_event(military_access_before=False),
            "military-cancel", "military-session", "FRA", "SAV", "initiate", 1)
        self.assertEqual("unknown", inconsistent["native_outcome"])

    def test_observer_ack_is_literal_and_not_caps_inferred(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = root / "installation.json"
            installation.write_text(json.dumps({
                "experiment_id": "military-contract",
                "session_id": "military-session",
                "pid": 1,
                "creation_filetime": 2,
                "dll_sha256": "dll",
            }), encoding="utf-8")
            log = root / "control-probe.jsonl"
            log.write_text(json.dumps({
                "event": "diplomacy_observer_installed",
                "session_id": "military-session",
                "caps": ["native_military_access_query",
                         "native_military_access_submission",
                         "native_inbound_military_access_response"],
            }) + "\n", encoding="utf-8")
            session = ObserverSession(installation, root / "eu4.exe")
            self.assertNotIn("native_military_access_query", session.installation_capabilities())
            self.assertNotIn("native_military_access_submission", session.installation_capabilities())
            self.assertNotIn("native_inbound_military_access_response",
                             session.installation_capabilities())
            log.write_text(json.dumps({
                "event": "diplomacy_observer_installed",
                "session_id": "military-session",
                "native_military_access_query": True,
                "native_military_access_submission": True,
                "native_inbound_military_access_response": True,
            }) + "\n", encoding="utf-8")
            self.assertIn("native_military_access_query", session.installation_capabilities())
            self.assertIn("native_military_access_submission", session.installation_capabilities())
            self.assertIn("native_inbound_military_access_response",
                          session.installation_capabilities())

    def test_bounded_log_reader_dispatches_both_military_result_events(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = root / "installation.json"
            installation.write_text(json.dumps({
                "experiment_id": "military-contract",
                "session_id": "military-session",
                "pid": 1,
                "creation_filetime": 2,
                "dll_sha256": "dll",
            }), encoding="utf-8")
            log = root / "control-probe.jsonl"
            log.write_text(json.dumps({
                "event": "diplomacy_observer_installed",
                "session_id": "military-session",
                "native_military_access_query": True,
                "native_military_access_submission": True,
            }) + "\n" + json.dumps(self._response_event()) + "\n"
            + json.dumps(self._cancel_event()) + "\n", encoding="utf-8")
            session = ObserverSession(installation, root / "eu4.exe")
            response = session.read_native_military_access_response(
                "military-response", "FRA", "SAV", "initiate", 1)
            cancelled = session.read_native_military_access_execution(
                "military-cancel", "FRA", "SAV", "initiate", 1)
            self.assertEqual("accepted", response["status"])
            self.assertEqual("executed", cancelled["status"])

    def test_inbound_direction_pending_and_family_isolation(self):
        offer = {
            "event": "native_alliance_inbound_offer",
            "session_id": "military-session",
            "proposal_id": 17,
            "action_id": "ask_military_access",
            "family": "military_access",
            "phase": "initiate",
            "actor": "SAV",
            "mirror": "SAV",
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
        }
        self.assertTrue(ObserverSession._valid_native_inbound_offer_event(
            offer, "military-session"))
        self.assertFalse(ObserverSession._valid_native_inbound_offer_event(
            {**offer, "family": "support_independence"}, "military-session"))

        inspection = MilitaryAccessSession._inbound_inspection(
            query_id="q", session_id="military-session")
        self.assertTrue(ObserverSession._valid_native_inbound_inspection(
            inspection, "q", "military-session", "SAV", "accept", 17, 1,
            "ask_military_access"))
        public = ObserverSession._public_native_inbound_inspection(
            inspection, 1, "ask_military_access")
        self.assertEqual("military_access", public["family"])
        self.assertFalse(public["military_access_before"])
        self.assertFalse(public["military_access_active"])
        self.assertTrue(public["military_access_state_verified"])
        self.assertNotIn("native_proposal_id", public)
        accepted = ObserverSession._public_native_inbound_response_result(
            self._inbound_response(), "military-inbound", "military-session",
            "SAV", "accept", 1, 17, "ask_military_access")
        self.assertEqual("SAV", accepted["actor"])
        self.assertEqual("FRA", accepted["recipient"])
        self.assertEqual("accepted", accepted["native_outcome"])
        self.assertNotIn("native_would_accept", accepted)
        self.assertIsNone(ObserverSession._public_native_inbound_response_result(
            self._inbound_response(pending_removed=False),
            "military-inbound", "military-session", "SAV", "accept", 1, 17,
            "ask_military_access"))
        self.assertIsNone(ObserverSession._public_native_inbound_response_result(
            self._inbound_response(family="royal_marriage"),
            "military-inbound", "military-session", "SAV", "accept", 1, 17,
            "ask_military_access"))
        self.assertIsNone(ObserverSession._public_native_inbound_response_result(
            self._inbound_response(native_state=0),
            "military-inbound", "military-session", "SAV", "accept", 1, 17,
            "ask_military_access"))

    def test_real_r32_inbound_inspection_fixture_uses_active_state_fields(self):
        fixture_path = Path(__file__).parent / "fixtures" / (
            "military_access_r32_inbound_inspections.json")
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertEqual(1, fixture["fixture_version"])
        self.assertEqual(2, len(fixture["events"]))
        for item in fixture["events"]:
            event = item["event"]
            source = Path(item["source_path"])
            self.assertEqual(item["source_file_sha256"], hashlib.sha256(
                source.read_bytes()).hexdigest())
            canonical = json.dumps(
                event, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False).encode("utf-8")
            self.assertEqual(item["event_sha256"], hashlib.sha256(canonical).hexdigest())
            self.assertNotIn("military_access_before", event)
            self.assertNotIn("native_current_military_access", event)
            self.assertTrue(ObserverSession._valid_native_inbound_inspection(
                event, event["query_id"], event["session_id"], event["actor"],
                event["phase"], event["native_proposal_id"], event["date_raw"],
                "ask_military_access"))
            public = ObserverSession._public_native_inbound_inspection(
                event, event["date_raw"], "ask_military_access")
            self.assertEqual("military_access", public["family"])
            self.assertIs(public["military_access_before"], event["military_access_active"])
            self.assertIs(public["military_access_active"], event["military_access_active"])
            self.assertTrue(public["military_access_state_verified"])
            self.assertTrue(public["pending_active"])

        legacy_shape = {
            **fixture["events"][0]["event"],
            "military_access_before": False,
            "native_current_military_access": False,
            "native_current_military_access_readable": True,
        }
        legacy_shape.pop("military_access_active", None)
        legacy_shape.pop("military_access_state_verified", None)
        self.assertFalse(ObserverSession._valid_native_inbound_inspection(
            legacy_shape, fixture["events"][0]["event"]["query_id"],
            fixture["events"][0]["event"]["session_id"], "SAV", "accept", 1,
            fixture["events"][0]["event"]["date_raw"], "ask_military_access"))

    def test_real_r32_inbound_pending_inactive_fixture_preserves_native_reason(self):
        fixture_path = Path(__file__).parent / "fixtures" / (
            "military_access_r32_inbound_pending_inactive.json")
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertEqual(1, fixture["fixture_version"])
        self.assertEqual(1, len(fixture["events"]))
        item = fixture["events"][0]
        event = item["event"]
        source = Path(item["source_path"])
        self.assertEqual(item["source_file_sha256"], hashlib.sha256(
            source.read_bytes()).hexdigest())
        canonical = json.dumps(
            event, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode("utf-8")
        self.assertEqual(item["event_sha256"], hashlib.sha256(canonical).hexdigest())
        self.assertEqual("PENDING_NOT_ACTIVE", event["reason"])
        self.assertFalse(event["pending_active"])
        self.assertTrue(ObserverSession._valid_native_inbound_inspection(
            event, event["query_id"], event["session_id"], event["actor"],
            event["phase"], event["native_proposal_id"], event["date_raw"],
            "ask_military_access"))
        public = ObserverSession._public_native_inbound_inspection(
            event, event["date_raw"], "ask_military_access")
        self.assertEqual("PENDING_NOT_ACTIVE", public["reason"])
        self.assertFalse(public["pending_active"])
        self.assertFalse(public["military_access_state_verified"])
        self.assertFalse(public["native_validity"])
        # A pending-inactive event with a different reason or a partially
        # populated proof tuple remains invalid rather than widening the schema.
        self.assertFalse(ObserverSession._valid_native_inbound_inspection(
            {**event, "reason": "FRAME_CONTEXT_UNAVAILABLE"}, event["query_id"],
            event["session_id"], event["actor"], event["phase"],
            event["native_proposal_id"], event["date_raw"],
            "ask_military_access"))
        self.assertFalse(ObserverSession._valid_native_inbound_inspection(
            {**event, "military_access_state_verified": True}, event["query_id"],
            event["session_id"], event["actor"], event["phase"],
            event["native_proposal_id"], event["date_raw"],
            "ask_military_access"))

    def test_pending_inactive_fixture_projects_as_unavailable_not_schema_error(self):
        fixture_path = Path(__file__).parent / "fixtures" / (
            "military_access_r32_inbound_pending_inactive.json")
        event = json.loads(fixture_path.read_text(encoding="utf-8"))["events"][0]["event"]
        public_id = "a" * 32

        class InactiveInboundSession(MilitaryAccessSession):
            def health(self) -> dict:
                return {"status": "ready", "state_id": "inactive-fixture",
                        "date_raw": event["date_raw"], "reasons": [], "complete": True}

            def read_native_alliance_inbound_offers(self) -> list[dict]:
                return [{
                    "proposal_id": public_id,
                    "action_id": "ask_military_access",
                    "family": "military_access",
                    "actor": event["actor"],
                    "recipient": "FRA",
                    "decision_country": "FRA",
                    "observer_status": "observed_pending",
                }]

            def _native_alliance_inbound_context(self, requested_id: str) -> dict:
                return {
                    "action_id": "ask_military_access",
                    "family": "military_access",
                    "actor": event["actor"],
                    "recipient": "FRA",
                    "native_proposal_id": event["native_proposal_id"],
                    "session_id": self.session_id,
                }

            def inspect_native_inbound_response(self, *args: object, **kwargs: object) -> dict:
                return ObserverSession._public_native_inbound_inspection(
                    event, event["date_raw"], "ask_military_access")

        api = DiplomacyTools(self.journal, InactiveInboundSession())
        inspection = api.inspect_diplomatic_action(
            "ask_military_access", event["actor"], "FRA", "accept",
            {"proposal_id": public_id})
        self.assertEqual("PENDING_NOT_ACTIVE",
                         inspection["native_inbound_inspection"]["reason"])
        self.assertEqual("invalidated", inspection["proposal_status"])
        self.assertEqual("unavailable", inspection["legality"]["status"])
        self.assertEqual(
            "NATIVE_INBOUND_PENDING_INVALIDATED",
            inspection["legality"]["reasons"][0]["code"])
        self.assertEqual("available", inspection["authorization"]["status"])
        self.assertEqual("native_inbound_response",
                         inspection["interface_support"]["execute"])

    def test_outbound_execute_result_and_idempotency(self):
        session = MilitaryAccessSession(response_event=self._response_event())
        api = DiplomacyTools(self.journal, session)
        first = api.execute_diplomatic_action(
            "military-ask", "ask_military_access", "FRA", "SAV")
        self.assertEqual("accepted", first["status"])
        self.assertEqual("accepted", first["game_outcome"])
        self.assertEqual(1, len(session.submit_calls))
        duplicate = api.execute_diplomatic_action(
            "military-ask", "ask_military_access", "FRA", "SAV")
        self.assertTrue(duplicate["idempotent"])
        self.assertEqual(1, len(session.submit_calls))

        cancel_session = MilitaryAccessSession(execution_event=self._cancel_event())
        cancel_journal = DurableJournal(":memory:", "military-cancel", "military-session")
        try:
            cancel_api = DiplomacyTools(cancel_journal, cancel_session)
            result = cancel_api.execute_diplomatic_action(
                "military-cancel", "cancel_military_access", "FRA", "SAV")
            self.assertEqual("executed", result["status"])
            self.assertEqual("executed", result["result"]["native_outcome"])
        finally:
            cancel_journal.close()

    def test_missing_result_stays_submitted_and_inbound_execute_keeps_direction(self):
        missing = MilitaryAccessSession()
        api = DiplomacyTools(self.journal, missing)
        result = api.execute_diplomatic_action(
            "military-missing", "ask_military_access", "FRA", "SAV")
        self.assertEqual("submitted", result["status"])
        self.assertEqual("unknown", result["game_outcome"])
        again = api.execute_diplomatic_action(
            "military-missing", "ask_military_access", "FRA", "SAV")
        self.assertTrue(again["idempotent"])
        self.assertEqual(1, len(missing.submit_calls))

        inbound = MilitaryAccessSession(inbound_response=self._inbound_response())
        inbound_journal = DurableJournal(":memory:", "military-inbound", "military-session")
        try:
            inbound_api = DiplomacyTools(inbound_journal, inbound)
            result = inbound_api.execute_diplomatic_action(
                "military-inbound-execute", "ask_military_access", "SAV", "FRA",
                "accept", {"proposal_id": "a" * 32})
            self.assertEqual("accepted", result["status"])
            self.assertEqual("SAV", result["result"]["actor"])
            self.assertEqual("FRA", result["result"]["recipient"])
            self.assertTrue(result["result"]["pending_removed"])
        finally:
            inbound_journal.close()


if __name__ == "__main__":
    unittest.main()
