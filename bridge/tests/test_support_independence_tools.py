from __future__ import annotations

import json
import hashlib
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal


class SupportSession:
    def __init__(self, *, capabilities: set[str] | None = None,
                 response_event: dict | None = None,
                 revoke_event: dict | None = None):
        self.session_id = "support-session"
        self.record = {"controlled_countries": ["FRA"]}
        self.capabilities = frozenset(capabilities or {
            "native_support_independence_query",
            "native_support_independence_submission",
        })
        self.response_event = response_event
        self.revoke_event = revoke_event
        self.submit_calls: list[tuple[str, str]] = []

    def health(self) -> dict:
        return {"status": "ready", "state_id": "ready", "date_raw": 1,
                "reasons": [], "complete": True}

    def installation_capabilities(self) -> frozenset[str]:
        return self.capabilities

    def inspect_support_independence(self, action_id: str, actor: str,
                                     recipient: str, phase: str) -> dict:
        return SupportIndependenceToolsTests._inspection_event(action_id, recipient=recipient)

    def _submit(self, request_id: str, action_id: str, actor: str,
                recipient: str, phase: str, date_raw: int) -> dict:
        self.submit_calls.append((request_id, action_id))
        return {"status": "submitted", "receipt":
                SupportIndependenceToolsTests._submission_receipt(
                    request_id, action_id, recipient)}

    def submit_support_independence(self, request_id: str, actor: str,
                                    recipient: str, phase: str, date_raw: int) -> dict:
        return self._submit(request_id, "support_independence", actor,
                            recipient, phase, date_raw)

    def submit_revoke_support_independence(self, request_id: str, actor: str,
                                           recipient: str, phase: str, date_raw: int) -> dict:
        return self._submit(request_id, "revoke_support_independence", actor,
                            recipient, phase, date_raw)

    def _read(self, request_id: str, actor: str, recipient: str,
              phase: str, date_raw: int, action_id: str) -> dict | None:
        event = self.response_event if action_id == "support_independence" else self.revoke_event
        if event is None:
            return None
        event = {**event, "request_id": request_id, "session_id": self.session_id,
                 "action_id": action_id, "actor": actor, "recipient": recipient,
                 "phase": phase, "date_raw": date_raw}
        if action_id == "support_independence":
            result = ObserverSession._public_native_support_independence_response_result(
                event, request_id, self.session_id, actor, recipient, phase, date_raw)
        else:
            result = ObserverSession._public_native_support_independence_execution_result(
                event, request_id, self.session_id, actor, recipient, phase, date_raw)
        if result is None:
            return {"status": "invalid", "reason_code": "NATIVE_RESPONSE_RESULT_INVALID"}
        return {"status": result["native_outcome"], "result": result}

    def read_native_support_independence_response(
            self, request_id: str, actor: str, recipient: str,
            phase: str, date_raw: int, action_id: str = "support_independence") -> dict | None:
        return self._read(request_id, actor, recipient, phase, date_raw, action_id)

    def read_native_support_independence_execution(
            self, request_id: str, actor: str, recipient: str,
            phase: str, date_raw: int,
            action_id: str = "revoke_support_independence") -> dict | None:
        return self._read(request_id, actor, recipient, phase, date_raw, action_id)


class SupportIndependenceToolsTests(unittest.TestCase):
    @staticmethod
    def _installation(root: Path, *, query_ack: object = None,
                       submission_ack: object = None,
                       caps: list[str] | None = None) -> tuple[Path, Path]:
        session_id = "support-session"
        installation = root / "installation.json"
        installation.write_text(json.dumps({
            "experiment_id": "support-contract",
            "session_id": session_id,
            "pid": 1,
            "creation_filetime": 2,
            "dll_sha256": "dll",
            "controlled_countries": ["FRA"],
            "installation_returncode": 0,
        }), encoding="utf-8")
        ack = {"event": "diplomacy_observer_installed", "session_id": session_id}
        if query_ack is not None:
            ack["native_support_independence_query"] = query_ack
        if submission_ack is not None:
            ack["native_support_independence_submission"] = submission_ack
        if caps is not None:
            ack["caps"] = caps
        log = root / "control-probe.jsonl"
        log.write_text(json.dumps(ack) + "\n", encoding="utf-8")
        return installation, log

    @staticmethod
    def _inspection_event(action_id: str = "support_independence", **overrides: object) -> dict:
        event = {
            "event": "native_alliance_inspection",
            "action_id": action_id,
            "family": "support_independence",
            "support_independence_active": action_id == "revoke_support_independence",
            "support_independence_state_verified": True,
            "relationship_state": {
                "support_independence_active": action_id == "revoke_support_independence",
                "complete": True,
            },
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
            "score_applicable": True,
            "score_available": True,
            "acceptance_predicate_available": True,
            "native_would_accept": True,
            "native_total_raw": 21,
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
        event.update(overrides)
        return event

    @staticmethod
    def _submission_receipt(request_id: str, action_id: str, recipient: str = "SAV") -> dict:
        return {
            "event": "native_alliance_submission_result",
            "request_id": request_id,
            "session_id": "support-session",
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

    @staticmethod
    def _response_event(**overrides: object) -> dict:
        event = {
            "event": "native_diplomacy_relation_response_result",
            "request_id": "support-response",
            "session_id": "support-session",
            "action_id": "support_independence",
            "actor": "FRA",
            "recipient": "SAV",
            "phase": "initiate",
            "date_raw": 1,
            "outcome": "accepted",
            "native_variant": 1,
            "native_state": 2,
            "family": "support_independence",
            "support_independence_before": False,
            "support_independence_after": True,
            "response_verified": True,
            "request_binding_verified": True,
        }
        event.update(overrides)
        return event

    @staticmethod
    def _revoke_event(**overrides: object) -> dict:
        event = {
            "event": "native_diplomacy_relation_execution_result",
            "request_id": "support-revoke",
            "session_id": "support-session",
            "action_id": "revoke_support_independence",
            "actor": "FRA",
            "recipient": "SAV",
            "phase": "initiate",
            "date_raw": 1,
            "outcome": "executed",
            "native_variant": 0,
            "native_state": 0,
            "family": "support_independence",
            "support_independence_before": True,
            "support_independence_after": False,
            "execution_verified": True,
            "request_binding_verified": True,
        }
        event.update(overrides)
        return event

    @staticmethod
    def _support_inbound_offer(**overrides: object) -> dict:
        event = {
            "event": "native_alliance_inbound_offer",
            "session_id": "support-session",
            "proposal_id": 17,
            "action_id": "support_independence",
            "family": "support_independence",
            "phase": "initiate",
            "actor": "SAV",
            "mirror": "SAV",
            "recipient": "FRA",
            "decision_country": "FRA",
            "date28": 1,
            "date2c": 1,
            "envoy30": 1,
            "state34": 0,
            "variant38": 1,
            "proposal3c": 2,
            "token3c": 3,
            "created2c": 4,
            "queue_before_count": 0,
            "queue_after_count": 1,
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
    def _support_inbound_inspection(query_id: str, **overrides: object) -> dict:
        event = {
            "event": "native_alliance_inbound_inspection",
            "query_id": query_id,
            "session_id": "support-session",
            "action_id": "support_independence",
            "family": "support_independence",
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
            "support_independence_before": False,
            "native_current_support_independence": False,
            "native_current_support_independence_readable": True,
            "reason": "none",
        }
        event.update(overrides)
        return event

    @staticmethod
    def _support_inbound_response(**overrides: object) -> dict:
        event = {
            "event": "native_diplomacy_relation_response_result",
            "request_id": "support-inbound-execute",
            "session_id": "support-session",
            "action_id": "support_independence",
            "actor": "SAV",
            "recipient": "FRA",
            "phase": "accept",
            "date_raw": 1,
            "outcome": "accepted",
            "native_variant": 1,
            "native_state": 2,
            "family": "support_independence",
            "support_independence_before": False,
            "support_independence_after": True,
            "response_verified": True,
            "request_binding_verified": True,
            "pending_removed": True,
        }
        event.update(overrides)
        return event

    @staticmethod
    def _observed_r31_support_response() -> dict:
        """Load the observed outbound HOL rejection without a runtime path."""

        path = (Path(__file__).resolve().parent / "fixtures"
                / "support_independence_r31_native_events.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("fixture_version") != 1:
            raise AssertionError("unsupported Support Independence event fixture version")
        entries = payload.get("events")
        if not isinstance(entries, list):
            raise AssertionError("malformed Support Independence event fixture")
        for entry in entries:
            if entry.get("fixture_id") != "r31a_support_hol_rejection_response":
                continue
            event = entry.get("event")
            if not isinstance(event, dict):
                raise AssertionError("malformed observed Support Independence event")
            canonical = json.dumps(
                event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            actual_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if actual_hash != entry.get("event_sha256"):
                raise AssertionError("observed Support Independence event hash mismatch")
            return event
        raise AssertionError("observed R31 Support Independence event is missing")

    def setUp(self) -> None:
        self.journal = DurableJournal(":memory:", "support-contract", "support-session")

    def tearDown(self) -> None:
        self.journal.close()

    def test_catalog_response_required_and_revoke_is_single_party(self):
        api = DiplomacyTools(self.journal)
        by_id = {item["action_id"]: item for item in api.list_diplomatic_actions()["actions"]}
        support = by_id["support_independence"]
        revoke = by_id["revoke_support_independence"]
        self.assertEqual("support_independence_action", support["native_identifier"])
        self.assertEqual({}, support["parameter_definitions"])
        self.assertEqual(["initiate", "accept", "reject", "withdraw"], list(support["phases"]))
        self.assertEqual(["initiate"], list(revoke["phases"]))
        self.assertEqual("applicable", api.inspect_diplomatic_action(
            "support_independence", "FRA", "SAV")["acceptance"]["applicability"])
        self.assertEqual("not_applicable", api.inspect_diplomatic_action(
            "revoke_support_independence", "FRA", "SAV")["acceptance"]["applicability"])
        with self.assertRaisesRegex(ValueError, "INBOUND_RESPONSE_PARAMETERS_UNSUPPORTED"):
            api.inspect_diplomatic_action("support_independence", "FRA", "SAV", "accept")
        with self.assertRaisesRegex(ValueError, "SUPPORT_INDEPENDENCE_PARAMETERS_UNSUPPORTED"):
            api.inspect_diplomatic_action("support_independence", "FRA", "SAV",
                                          parameters={"diplomat_id": 1})

    def test_ack_is_dedicated_and_query_preserves_native_acceptance_data(self):
        no_support = SupportSession(capabilities={"native_guarantee_query"})
        api = DiplomacyTools(self.journal, no_support)
        by_id = {item["action_id"]: item for item in api.list_diplomatic_actions()["actions"]}
        self.assertEqual("unimplemented",
                         by_id["support_independence"]["phases"]["initiate"]["query"])
        self.assertEqual("unimplemented",
                         by_id["support_independence"]["phases"]["initiate"]["execute"])

        session = SupportSession()
        result = DiplomacyTools(self.journal, session).inspect_diplomatic_action(
            "support_independence", "FRA", "SAV")
        self.assertEqual("partial_native_rules", result["interface_support"]["query"])
        self.assertEqual("native_support_independence_submission",
                         result["interface_support"]["execute"])
        self.assertEqual("available", result["legality"]["status"])
        self.assertEqual("available", result["authorization"]["status"])
        self.assertEqual({"support_independence_active": False, "complete": True},
                         result["relationship_state"])
        self.assertTrue(result["acceptance"]["prediction_available"])
        self.assertEqual(21, result["acceptance"]["native_total"])
        self.assertTrue(result["acceptance"]["native_would_accept"])

    def test_inbound_support_ack_is_exact_and_family_isolated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, log = self._installation(root)
            log.write_text(json.dumps({
                "event": "diplomacy_observer_installed",
                "session_id": "support-session",
                "native_inbound_alliance": True,
                "caps": ["native_inbound_support_independence_response"],
            }) + "\n", encoding="utf-8")
            session = ObserverSession(installation, root / "eu4.exe")
            self.assertNotIn("native_inbound_support_independence_response",
                             session.installation_capabilities())

            log.write_text(json.dumps({
                "event": "diplomacy_observer_installed",
                "session_id": "support-session",
                "native_inbound_alliance": True,
                "native_inbound_support_independence_response": True,
            }) + "\n", encoding="utf-8")
            self.assertIn("native_inbound_support_independence_response",
                          session.installation_capabilities())

    def test_response_reject_revoke_and_family_binding(self):
        accepted = ObserverSession._public_native_support_independence_response_result(
            self._response_event(), "support-response", "support-session", "FRA", "SAV", "initiate", 1)
        self.assertIsNotNone(accepted)
        self.assertEqual("accepted", accepted["native_outcome"])
        rejected = ObserverSession._public_native_support_independence_response_result(
            self._response_event(outcome="rejected", native_state=1,
                                 support_independence_after=False),
            "support-response", "support-session", "FRA", "SAV", "initiate", 1)
        self.assertIsNotNone(rejected)
        self.assertEqual("rejected", rejected["native_outcome"])
        revoked = ObserverSession._public_native_support_independence_execution_result(
            self._revoke_event(), "support-revoke", "support-session", "FRA", "SAV", "initiate", 1)
        self.assertIsNotNone(revoked)
        self.assertEqual("executed", revoked["native_outcome"])
        for event in (
                self._response_event(family="guarantee"),
                self._response_event(native_variant=0),
                self._response_event(native_variant=None, mode=1),
                self._response_event(recipient="SA!"),
                self._revoke_event(family="spy_network"),
                self._revoke_event(support_independence_before=False)):
            with self.subTest(event=event):
                parser = (ObserverSession._public_native_support_independence_execution_result
                          if event["action_id"] == "revoke_support_independence"
                          else ObserverSession._public_native_support_independence_response_result)
                result = parser(
                    event, event["request_id"], "support-session", "FRA",
                    event["recipient"], "initiate", 1)
                if event["action_id"] == "revoke_support_independence" \
                        and event["family"] == "support_independence":
                    self.assertEqual("unknown", result["native_outcome"])
                else:
                    self.assertIsNone(result)
        self.assertIsNone(ObserverSession._public_native_support_independence_execution_result(
            self._revoke_event(native_variant=None, mode=0),
            "support-revoke", "support-session", "FRA", "SAV", "initiate", 1))

    def test_inbound_support_family_and_pending_removal_binding(self):
        offer = self._support_inbound_offer()
        self.assertTrue(ObserverSession._valid_native_inbound_offer_event(
            offer, "support-session"))
        self.assertFalse(ObserverSession._valid_native_inbound_offer_event(
            {**offer, "family": "royal_marriage"}, "support-session"))

        inspection = self._support_inbound_inspection("support-query")
        self.assertTrue(ObserverSession._valid_native_inbound_inspection(
            inspection, "support-query", "support-session", "SAV", "accept", 17, 1,
            "support_independence"))
        public_inspection = ObserverSession._public_native_inbound_inspection(
            inspection, 1, "support_independence")
        self.assertEqual("support_independence", public_inspection["family"])
        self.assertFalse(public_inspection["support_independence_before"])
        self.assertFalse(public_inspection["native_current_support_independence"])
        self.assertTrue(public_inspection["native_current_support_independence_readable"])

        accepted = ObserverSession._public_native_inbound_response_result(
            self._support_inbound_response(), "support-inbound-execute", "support-session",
            "SAV", "accept", 1, 17, "support_independence")
        self.assertEqual("accepted", accepted["native_outcome"])
        rejected = ObserverSession._public_native_inbound_response_result(
            self._support_inbound_response(
                request_id="support-inbound-reject", outcome="rejected", native_state=1,
                support_independence_after=False),
            "support-inbound-reject", "support-session", "SAV", "accept", 1, 17,
            "support_independence")
        self.assertEqual("rejected", rejected["native_outcome"])
        for invalid in (
                self._support_inbound_response(family="royal_marriage"),
                self._support_inbound_response(native_variant=None, mode=1),
                self._support_inbound_response(pending_removed=False)):
            self.assertIsNone(ObserverSession._public_native_inbound_response_result(
                invalid, invalid["request_id"], "support-session", "SAV", "accept", 1, 17,
                "support_independence"))
        inconsistent = self._support_inbound_response(support_independence_after=False)
        parsed_inconsistent = ObserverSession._public_native_inbound_response_result(
            inconsistent, inconsistent["request_id"], "support-session", "SAV", "accept", 1,
            17, "support_independence")
        self.assertEqual("unknown", parsed_inconsistent["native_outcome"])

    def test_support_query_acceptance_fields_are_validated_and_projected(self):
        event = self._inspection_event(
            recipient="SAV", score_applicable=True, score_available=True,
            acceptance_predicate_available=True, native_would_accept=False,
            native_total_raw=-921, acceptance_threshold_raw=1,
            reason_count=2,
            reason_items=[{"name": "DIPLO_OPINION", "native_value": 5},
                          {"name": "DIPLO_DIPLOMATIC_REP", "native_value": 8}],
            reason_items_truncated=False)
        self.assertTrue(ObserverSession._valid_native_inspection(
            event, "support_independence", "FRA", "SAV", "initiate", 1))

    def test_inbound_support_offer_query_and_execute_use_support_wire(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, log = self._installation(root)
            ack = {
                "event": "diplomacy_observer_installed",
                "session_id": "support-session",
                "native_inbound_alliance": True,
                "native_inbound_support_independence_response": True,
            }
            log.write_text(json.dumps(ack) + "\n" + json.dumps(
                self._support_inbound_offer()) + "\n", encoding="utf-8")
            session = ObserverSession(installation, root / "eu4.exe")
            ready = {"status": "ready", "state_id": "support", "date_raw": 1,
                     "reasons": [], "complete": True}
            api = DiplomacyTools(self.journal, session)
            server_errors: list[object] = []
            query_count = 0

            def append(event: dict) -> None:
                with log.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(event) + "\n")

            def serve() -> None:
                nonlocal query_count
                deadline = time.monotonic() + 4
                query = root / "diplomacy-inbound-query.req"
                response_request = root / "diplomacy-respond.req"
                while time.monotonic() < deadline:
                    if query.exists():
                        fields = query.read_text(encoding="ascii").rstrip("\n").split("|")
                        query.unlink()
                        if len(fields) != 10 or fields[5] != "support_independence":
                            server_errors.append(("query", fields))
                        else:
                            query_count += 1
                            append(self._support_inbound_inspection(
                                fields[1], session_id=fields[2], actor=fields[6],
                                phase=fields[8], native_proposal_id=int(fields[9]),
                                date_raw=int(fields[4])))
                    if response_request.exists():
                        fields = response_request.read_text(encoding="ascii").rstrip("\n").split("|")
                        response_request.unlink()
                        if len(fields) != 10 or fields[5] != "support_independence":
                            server_errors.append(("response", fields))
                            return
                        common = {
                            "request_id": fields[1], "session_id": fields[2],
                            "action_id": fields[5], "actor": fields[6],
                            "recipient": fields[7], "phase": fields[8],
                            "native_proposal_id": int(fields[9]),
                            "date_raw": int(fields[4]),
                        }
                        append({
                            "event": "native_alliance_submission_result", **common,
                            "submitted": True, "native_queue_verified": True,
                            "transport_ring_receipt": True, "native_sequence": 7,
                            "native_origin": 1, "native_flags": 0,
                        })
                        append(self._support_inbound_response(
                            request_id=fields[1], session_id=fields[2],
                            actor=fields[6], recipient=fields[7], phase=fields[8],
                            date_raw=int(fields[4])))
                        return
                    time.sleep(0.001)
                server_errors.append("wire timeout")

            with patch.object(session, "health", return_value=ready):
                catalog = api.list_diplomatic_actions()
                support_action = next(item for item in catalog["actions"]
                                     if item["action_id"] == "support_independence")
                self.assertEqual("native_inbound_response",
                                 support_action["phases"]["accept"]["execute"])
                proposal = catalog["incoming_proposals"][0]
                self.assertEqual("support_independence", proposal["family"])
                writer = threading.Thread(target=serve)
                writer.start()
                inspected = api.inspect_diplomatic_action(
                    "support_independence", "SAV", "FRA", "accept",
                    parameters={"proposal_id": proposal["proposal_id"]})
                result = api.execute_diplomatic_action(
                    "support-inbound-execute", "support_independence", "SAV", "FRA", "accept",
                    parameters={"proposal_id": proposal["proposal_id"]})
                writer.join(4)

            self.assertFalse(writer.is_alive())
            self.assertEqual([], server_errors)
            self.assertEqual(2, query_count)
            self.assertEqual("available", inspected["legality"]["status"])
            self.assertEqual("support_independence",
                             inspected["native_inbound_inspection"]["family"])
            self.assertEqual("available", inspected["authorization"]["status"])
            self.assertEqual("accepted", result["status"])
            self.assertEqual("accepted", result["game_outcome"])
            self.assertEqual("support_independence", result["result"]["family"])
            self.assertTrue(result["result"]["pending_removed"])
            duplicate = api.execute_diplomatic_action(
                "support-inbound-execute", "support_independence", "SAV", "FRA", "accept",
                parameters={"proposal_id": proposal["proposal_id"]})
            self.assertTrue(duplicate["idempotent"])

    def test_real_log_reader_and_execute_idempotency(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, log = self._installation(root, query_ack=True, submission_ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            event = self._response_event()
            log.write_text(json.dumps(event) + "\n", encoding="utf-8")
            read = session.read_native_support_independence_response(
                "support-response", "FRA", "SAV", "initiate", 1)
            self.assertEqual("accepted", read["status"])

        session = SupportSession(response_event=self._response_event())
        api = DiplomacyTools(self.journal, session)
        first = api.execute_diplomatic_action("support-execute", "support_independence", "FRA", "SAV")
        self.assertEqual("accepted", first["status"])
        self.assertEqual(1, len(session.submit_calls))
        again = api.execute_diplomatic_action("support-execute", "support_independence", "FRA", "SAV")
        self.assertTrue(again["idempotent"])
        self.assertEqual(1, len(session.submit_calls))

    def test_observed_outbound_rejection_uses_native_variant_and_persists_result(self):
        """A native NPC rejection is terminal even when pending_removed is false."""

        event = self._observed_r31_support_response()
        request_id = event["request_id"]
        session_id = event["session_id"]
        date_raw = event["date_raw"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = root / "installation.json"
            installation.write_text(json.dumps({
                "experiment_id": "support-contract",
                "session_id": session_id,
                "pid": 1,
                "creation_filetime": 2,
                "dll_sha256": "dll",
                "controlled_countries": ["FRA"],
                "installation_returncode": 0,
            }), encoding="utf-8")
            receipt = {
                "event": "native_alliance_submission_result",
                "request_id": request_id,
                "session_id": session_id,
                "action_id": "support_independence",
                "actor": "FRA",
                "recipient": "HOL",
                "phase": "initiate",
                "date_raw": date_raw,
                "submitted": True,
                "native_queue_verified": True,
                "transport_ring": True,
                "transport_ring_receipt": True,
                "native_sequence": 17,
                "native_origin": 65535,
                "native_flags": 0,
            }
            log = root / "control-probe.jsonl"
            log.write_text(
                json.dumps({
                    "event": "diplomacy_observer_installed",
                    "session_id": session_id,
                    "native_support_independence_query": True,
                    "native_support_independence_submission": True,
                }) + "\n" + json.dumps(receipt) + "\n" + json.dumps(event) + "\n",
                encoding="utf-8")

            # Exercise the actual bounded control-log reader independently of
            # the journal recovery pass; the second session starts at offset 0.
            direct = ObserverSession(installation, root / "eu4.exe").read_native_support_independence_response(
                request_id, "FRA", "HOL", "initiate", date_raw)
            self.assertEqual("rejected", direct["status"])
            self.assertEqual(1, direct["result"]["native_variant"])
            self.assertFalse(direct["result"]["pending_removed"])

            journal = DurableJournal(":memory:", "support-contract", session_id)
            try:
                journal.register(request_id, {
                    "action_id": "support_independence",
                    "actor": "FRA",
                    "recipient": "HOL",
                    "phase": "initiate",
                    "parameters": {},
                })
                for status in ("queued", "consumed", "constructed"):
                    journal.transition(request_id, status, result={"submitted": False})
                claim = journal.claim_submission(request_id, submission_id="native_" + request_id)
                journal.mark_submitted(request_id, claim.claim_token, receipt)
                recovered = DiplomacyTools(
                    journal, ObserverSession(installation, root / "eu4.exe")
                ).get_diplomatic_result(request_id)
                self.assertEqual("rejected", recovered["status"])
                self.assertEqual("rejected", recovered["game_outcome"])
                self.assertEqual("rejected", recovered["result"]["native_outcome"])
                self.assertEqual("HOL", recovered["result"]["recipient"])
                self.assertFalse(recovered["result"]["pending_removed"])
                self.assertEqual("rejected", journal.get_request(request_id).status)
            finally:
                journal.close()


if __name__ == "__main__":
    unittest.main()
