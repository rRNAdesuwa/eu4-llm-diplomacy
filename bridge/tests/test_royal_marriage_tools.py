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


ROYAL_QUERY = "native_royal_marriage_query"
ROYAL_SUBMISSION = "native_royal_marriage_submission"
INBOUND_OBSERVER = "native_inbound_alliance"
ROYAL_INBOUND_RESPONSE = "native_inbound_royal_marriage_response"


class RoyalQuerySession:
    """Small adapter double for the public Royal query boundary."""

    def __init__(self, capabilities=(), **overrides):
        self.capabilities = capabilities
        self.record = {"controlled_countries": ["FRA"]}
        self.inspect_calls = []
        self.submit_calls = []
        self.native = {
            "display_predicate": True,
            "native_visibility": True,
            "ui_selection_checked": True,
            "ui_enabled_gate_checked": True,
            "common_action_gate": True,
            "validity_called": True,
            "native_validity": True,
            "initiation_gate": True,
            "tooltip_gate": True,
            "full_rules_complete": True,
            "score_applicable": True,
            "score_available": True,
            "native_total_raw": 12,
            "acceptance_threshold_raw": 20,
            "acceptance_predicate_available": True,
            "native_would_accept": False,
            "diplomat_context_readable": True,
            "diplomat_required": True,
            "available_diplomat_count": 1,
            "reason_count": 1,
            "reason_items": [{"name": "DIPLO_RELIGION", "native_value": -5}],
            "reason_items_truncated": False,
            "date_raw": 1,
        }
        self.native.update(overrides)

    def health(self):
        return {"status": "ready", "state_id": "opaque", "date_raw": 1,
                "reasons": [], "complete": True}

    def installation_capabilities(self):
        return self.capabilities

    def inspect_royal_marriage(self, action_id, actor, recipient, phase):
        self.inspect_calls.append((action_id, actor, recipient, phase))
        return self.native

    def inspect_alliance(self, *args):
        raise AssertionError("Royal query must not borrow the Alliance adapter")


class RoyalExecutionSession(RoyalQuerySession):
    """Execution adapter double for the two outbound Royal actions."""

    def __init__(self, *, offer_outcome="accepted", capabilities=None, **overrides):
        super().__init__(capabilities or frozenset({ROYAL_QUERY, ROYAL_SUBMISSION}), **overrides)
        self.session_id = "session"
        self.offer_outcome = offer_outcome

    @staticmethod
    def _receipt(request_id, action_id, actor, recipient, phase, date_raw):
        return {"status": "submitted", "receipt": {
            "event": "native_alliance_submission_result", "request_id": request_id,
            "action_id": action_id, "actor": actor, "recipient": recipient,
            "phase": phase, "date_raw": date_raw, "submitted": True,
            "native_queue_verified": True, "transport_ring_receipt": True,
            "native_sequence": 7, "native_origin": 1, "native_flags": 0,
        }}

    def submit_offer_royal_marriage(self, request_id, actor, recipient, phase, date_raw):
        self.submit_calls.append((request_id, actor, recipient, phase, date_raw,
                                  "offer_royal_marriage"))
        return self._receipt(request_id, "offer_royal_marriage", actor, recipient, phase, date_raw)

    def submit_break_royal_ties(self, request_id, actor, recipient, phase, date_raw):
        self.submit_calls.append((request_id, actor, recipient, phase, date_raw,
                                  "break_royal_ties"))
        return self._receipt(request_id, "break_royal_ties", actor, recipient, phase, date_raw)

    def read_native_royal_marriage_response(self, request_id, actor, recipient, phase, date_raw):
        accepted = self.offer_outcome == "accepted"
        event = {
            "event": "native_alliance_response_result", "request_id": request_id,
            "session_id": self.session_id, "action_id": "offer_royal_marriage",
            "actor": actor, "recipient": recipient, "phase": phase, "date_raw": date_raw,
            "family": "royal_marriage", "response_verified": True,
            "request_binding_verified": True, "native_state": 2 if accepted else 1,
            "royal_marriage_before": False, "royal_marriage_after": accepted,
        }
        result = ObserverSession._public_native_response_result(
            event, request_id, self.session_id, actor, recipient, phase, date_raw,
            "offer_royal_marriage")
        return {"status": result["native_outcome"], "result": result}

    def read_native_royal_break_result(self, request_id, actor, recipient, phase, date_raw):
        event = {
            "event": "native_alliance_execution_result", "request_id": request_id,
            "session_id": self.session_id, "action_id": "break_royal_ties",
            "actor": actor, "recipient": recipient, "phase": phase, "date_raw": date_raw,
            "family": "royal_marriage", "execution_verified": True,
            "request_binding_verified": True, "native_state": 0, "native_variant": 0,
            "royal_marriage_before": True, "royal_marriage_after": False,
        }
        result = ObserverSession._public_native_royal_break_result(
            event, request_id, self.session_id, actor, recipient, phase, date_raw)
        return {"status": result["native_outcome"], "result": result}


class RoyalMarriageToolsTests(unittest.TestCase):
    def setUp(self):
        self.journal = DurableJournal(":memory:", "experiment", "session")

    def tearDown(self):
        self.journal.close()

    @staticmethod
    def _write_royal_inbound_installation(root, session_id="session"):
        installation = root / "installation.json"
        installation.write_text(json.dumps({
            "experiment_id": "r26", "session_id": session_id, "pid": 1,
            "creation_filetime": 2, "dll_sha256": "dll", "installation_returncode": 0,
        }), encoding="utf-8")
        log = root / "control-probe.jsonl"
        log.write_text(json.dumps({
            "event": "diplomacy_observer_installed", "session_id": session_id,
            INBOUND_OBSERVER: True, ROYAL_INBOUND_RESPONSE: True,
        }) + "\n", encoding="utf-8")
        return installation, log

    @staticmethod
    def _royal_inbound_offer(session_id="session", proposal_id=17, **overrides):
        event = {
            "event": "native_alliance_inbound_offer",
            "session_id": session_id, "proposal_id": proposal_id,
            "action_id": "offer_royal_marriage", "family": "royal_marriage",
            "extra60": 0, "phase": "initiate", "actor": "SAV", "mirror": "SAV",
            "recipient": "FRA", "decision_country": "FRA", "date28": 1,
            "date2c": 1, "envoy30": 1, "state34": 0, "variant38": 1,
            "proposal3c": 2, "token3c": 3, "created2c": 4,
            "queue_before_count": 0, "queue_after_count": 1,
            "queue_readable": True, "list_integrity": True, "new_entry": True,
            "payload_readable": True, "decision_country_verified": True,
            "source_verified": True, "call_redirected": True,
            "business_result": "pending_observed",
        }
        event.update(overrides)
        return event

    @staticmethod
    def _royal_inbound_inspection(query_id, session_id="session",
                                  actor="SAV", phase="accept", proposal_id=17,
                                  date_raw=1, **overrides):
        event = {
            "event": "native_alliance_inbound_inspection",
            "query_id": query_id, "session_id": session_id,
            "action_id": "offer_royal_marriage", "family": "royal_marriage",
            "extra60": 0, "actor": actor, "recipient": "FRA", "phase": phase,
            "native_proposal_id": proposal_id, "date_raw": date_raw,
            "pending_active": True, "decision_country": "FRA",
            "decision_country_verified": True, "native_validity": True,
            "response_rules_complete": True, "royal_marriage_before": False,
        }
        event.update(overrides)
        return event

    @staticmethod
    def _observed_r27_rejection_events():
        """Read the two observed E native events from the portable fixture."""

        fixture = RoyalMarriageToolsTests._read_observed_native_event_fixture()
        selected = {}
        for fixture_id in ("r27e_rejection_submission", "r27e_rejection_response"):
            event = fixture[fixture_id]
            if (event.get("request_id") == "r27e_reject_sav_002"
                    and event.get("event") in (
                        "native_alliance_submission_result",
                        "native_alliance_response_result")):
                selected[event["event"]] = event
        if set(selected) != {
                "native_alliance_submission_result",
                "native_alliance_response_result"}:
            raise AssertionError("portable r27 Royal rejection event pair is incomplete")
        return selected

    @staticmethod
    def _observed_r27_daily_l_pending_inactive_event():
        """Read the actual L-run pending-inactive event from the fixture."""

        return RoyalMarriageToolsTests._read_observed_native_event_fixture()[
            "r27l_pending_inactive_inspection"]

    @staticmethod
    def _read_observed_native_event_fixture():
        path = Path(__file__).resolve().parent / "fixtures" / "royal_marriage_r27_native_events.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("fixture_version") != 1:
            raise AssertionError("unsupported Royal native event fixture version")
        entries = {}
        for entry in payload.get("events", []):
            fixture_id = entry.get("fixture_id")
            event = entry.get("event")
            if not isinstance(fixture_id, str) or not isinstance(event, dict):
                raise AssertionError("malformed Royal native event fixture entry")
            canonical = json.dumps(
                event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            actual_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if actual_hash != entry.get("event_sha256"):
                raise AssertionError(f"fixture event hash mismatch: {fixture_id}")
            entries[fixture_id] = event
        return entries

    def test_royal_inbound_ack_and_family_are_independent_from_alliance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, log = self._write_royal_inbound_installation(root)
            invalid_royal = self._royal_inbound_offer(proposal_id=11, family="alliance")
            invalid_alliance = self._royal_inbound_offer(
                proposal_id=12, action_id="offer_alliance", family="royal_marriage")
            valid = self._royal_inbound_offer(proposal_id=13)
            with log.open("a", encoding="utf-8", newline="\n") as stream:
                for event in (invalid_royal, invalid_alliance, valid):
                    stream.write(json.dumps(event) + "\n")
            session = ObserverSession(installation, root / "eu4.exe")
            ready = {"status": "ready", "state_id": "opaque", "date_raw": 1,
                     "reasons": [], "complete": True}
            api = DiplomacyTools(self.journal, session)
            with patch.object(session, "health", return_value=ready):
                catalog = api.list_diplomatic_actions()
            self.assertEqual({INBOUND_OBSERVER, ROYAL_INBOUND_RESPONSE},
                             session.installation_capabilities())
            self.assertEqual(1, len(catalog["incoming_proposals"]))
            proposal = catalog["incoming_proposals"][0]
            self.assertEqual("offer_royal_marriage", proposal["action_id"])
            self.assertEqual("royal_marriage", proposal["family"])
            self.assertEqual("native_inbound_response", proposal["execute"]["accept"])
            by_id = {item["action_id"]: item for item in catalog["actions"]}
            for phase_name in ("accept", "reject"):
                self.assertEqual("native_inbound_response",
                                 by_id["offer_royal_marriage"]["phases"][phase_name]["execute"])
                self.assertEqual("unimplemented",
                                 by_id["offer_alliance"]["phases"][phase_name]["execute"])

            # A caps-list mention cannot grant the inbound Royal response ACK.
            log.write_text(json.dumps({
                "event": "diplomacy_observer_installed", "session_id": "session",
                INBOUND_OBSERVER: True, "caps": [ROYAL_INBOUND_RESPONSE],
            }) + "\n", encoding="utf-8")
            self.assertEqual(frozenset({INBOUND_OBSERVER}), session.installation_capabilities())

    def test_royal_inbound_accept_uses_royal_wire_result_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, log = self._write_royal_inbound_installation(root)
            with log.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(self._royal_inbound_offer()) + "\n")
            session = ObserverSession(installation, root / "eu4.exe")
            ready = {"status": "ready", "state_id": "opaque", "date_raw": 1,
                     "reasons": [], "complete": True}
            api = DiplomacyTools(self.journal, session)
            server_errors = []
            response_requests = []

            def serve_query_and_response():
                deadline = time.monotonic() + 3
                query = root / "diplomacy-inbound-query.req"
                while not query.exists() and time.monotonic() < deadline:
                    time.sleep(0.001)
                if not query.exists():
                    server_errors.append("query timeout")
                    return
                query_fields = query.read_text(encoding="ascii").rstrip("\n").split("|")
                query.unlink()
                if query_fields[5] != "offer_royal_marriage":
                    server_errors.append(("query action", query_fields))
                inspection = self._royal_inbound_inspection(
                    query_fields[1], query_fields[2], actor=query_fields[6],
                    phase=query_fields[8], proposal_id=int(query_fields[9]),
                    date_raw=int(query_fields[4]))
                with log.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(inspection) + "\n")
                response = root / "diplomacy-respond.req"
                while not response.exists() and time.monotonic() < deadline:
                    time.sleep(0.001)
                if not response.exists():
                    server_errors.append("response timeout")
                    return
                response_fields = response.read_text(encoding="ascii").rstrip("\n").split("|")
                response.unlink()
                response_requests.append(response_fields)
                if response_fields[5] != "offer_royal_marriage":
                    server_errors.append(("response action", response_fields))
                common = {
                    "request_id": response_fields[1], "session_id": response_fields[2],
                    "action_id": response_fields[5], "actor": response_fields[6],
                    "recipient": response_fields[7], "phase": response_fields[8],
                    "native_proposal_id": int(response_fields[9]),
                    "date_raw": int(response_fields[4]), "family": "royal_marriage",
                    "extra60": 0,
                }
                submission = {
                    "event": "native_alliance_submission_result", **common,
                    "submitted": True, "native_queue_verified": True,
                    "transport_ring_receipt": True, "native_sequence": 7,
                    "native_origin": 1, "native_flags": 0,
                }
                outcome = {
                    "event": "native_alliance_response_result", **common,
                    "response_verified": True, "request_binding_verified": True,
                    "native_state": 2, "royal_marriage_after": True,
                    "pending_removed": True,
                }
                with log.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(submission) + "\n")
                    stream.write(json.dumps(outcome) + "\n")

            with patch.object(session, "health", return_value=ready):
                proposal = api.list_diplomatic_actions()["incoming_proposals"][0]
                writer = threading.Thread(target=serve_query_and_response)
                writer.start()
                result = api.execute_diplomatic_action(
                    "royal_inbound_accept", "offer_royal_marriage", "SAV", "FRA", "accept",
                    parameters={"proposal_id": proposal["proposal_id"]})
                writer.join(3)
                duplicate = api.execute_diplomatic_action(
                    "royal_inbound_accept", "offer_royal_marriage", "SAV", "FRA", "accept",
                    parameters={"proposal_id": proposal["proposal_id"]})
            self.assertFalse(writer.is_alive())
            self.assertEqual([], server_errors)
            self.assertEqual(1, len(response_requests))
            self.assertEqual("accepted", result["status"])
            self.assertEqual("accepted", result["game_outcome"])
            self.assertEqual("offer_royal_marriage", result["action_id"])
            self.assertEqual("royal_marriage", result["result"]["family"])
            self.assertTrue(result["result"]["royal_marriage_after"])
            self.assertTrue(result["result"]["pending_removed"])
            self.assertTrue(duplicate["idempotent"])
            serialized = json.dumps(result, ensure_ascii=False)
            for private in ("native_proposal_id", "session_id", "pid", "extra60"):
                self.assertNotIn(private, serialized)

    def test_alliance_response_ack_does_not_authorize_royal_inbound(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, log = self._write_royal_inbound_installation(root)
            log.write_text(json.dumps({
                "event": "diplomacy_observer_installed", "session_id": "session",
                INBOUND_OBSERVER: True, "native_inbound_alliance_response": True,
            }) + "\n" + json.dumps(self._royal_inbound_offer()) + "\n", encoding="utf-8")
            session = ObserverSession(installation, root / "eu4.exe")
            ready = {"status": "ready", "state_id": "opaque", "date_raw": 1,
                     "reasons": [], "complete": True}
            api = DiplomacyTools(self.journal, session)
            with patch.object(session, "health", return_value=ready):
                catalog = api.list_diplomatic_actions()
                proposal = catalog["incoming_proposals"][0]
                royal = next(item for item in catalog["actions"]
                              if item["action_id"] == "offer_royal_marriage")
                inspected = api.inspect_diplomatic_action(
                    "offer_royal_marriage", "SAV", "FRA", "accept",
                    parameters={"proposal_id": proposal["proposal_id"]})
            self.assertEqual("unimplemented", proposal["execute"]["accept"])
            self.assertEqual("unimplemented", royal["phases"]["accept"]["execute"])
            self.assertEqual("unimplemented", inspected["interface_support"]["execute"])
            self.assertEqual("unavailable", inspected["authorization"]["status"])
            self.assertFalse((root / "diplomacy-respond.req").exists())

    def test_royal_native_clone_failure_is_query_error_not_legality_false(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, log = self._write_royal_inbound_installation(root)
            with log.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(self._royal_inbound_offer()) + "\n")
            session = ObserverSession(installation, root / "eu4.exe")
            ready = {"status": "ready", "state_id": "opaque", "date_raw": 1,
                     "reasons": [], "complete": True}
            api = DiplomacyTools(self.journal, session)
            server_errors = []

            def serve_query_error():
                request = root / "diplomacy-inbound-query.req"
                deadline = time.monotonic() + 2
                while not request.exists() and time.monotonic() < deadline:
                    time.sleep(0.001)
                if not request.exists():
                    server_errors.append("query timeout")
                    return
                fields = request.read_text(encoding="ascii").rstrip("\n").split("|")
                request.unlink()
                event = self._royal_inbound_inspection(
                    fields[1], fields[2], actor=fields[6], phase=fields[8],
                    proposal_id=int(fields[9]), date_raw=int(fields[4]),
                    pending_active=False, decision_country_verified=False,
                    native_validity=False, response_rules_complete=False,
                    reason="NATIVE_RESPONSE_CLONE_UNVERIFIED")
                with log.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(event) + "\n")

            with patch.object(session, "health", return_value=ready):
                proposal = api.list_diplomatic_actions()["incoming_proposals"][0]
                writer = threading.Thread(target=serve_query_error)
                writer.start()
                inspected = api.inspect_diplomatic_action(
                    "offer_royal_marriage", "SAV", "FRA", "accept",
                    parameters={"proposal_id": proposal["proposal_id"]})
                writer.join(2)
            self.assertFalse(writer.is_alive())
            self.assertEqual([], server_errors)
            self.assertEqual("unknown", inspected["legality"]["status"])
            self.assertFalse(inspected["legality"]["complete"])
            self.assertEqual("NATIVE_RESPONSE_CLONE_UNVERIFIED",
                             inspected["legality"]["reasons"][0]["code"])
            self.assertEqual("runtime_error",
                             inspected["legality"]["reasons"][0]["source"])
            self.assertNotIn("proposal_status", inspected)
            self.assertNotIn("NATIVE_INBOUND_VALIDITY_FALSE",
                             {item["code"] for item in inspected["legality"]["reasons"]})
            self.assertEqual("NATIVE_RESPONSE_CLONE_UNVERIFIED",
                             inspected["native_inbound_inspection"]["reason"])

    def test_r27_actual_pending_inactive_event_keeps_royal_adapter_support(self):
        """PENDING_NOT_ACTIVE invalidates legality without hiding an installed adapter."""

        actual = self._observed_r27_daily_l_pending_inactive_event()
        session_id = actual["session_id"]
        date_raw = actual["date_raw"]
        proposal_id = actual["native_proposal_id"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, log = self._write_royal_inbound_installation(
                root, session_id=session_id)
            with log.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(self._royal_inbound_offer(
                    session_id=session_id, proposal_id=proposal_id,
                    actor=actual["actor"], mirror=actual["actor"],
                    date28=date_raw, date2c=date_raw, created2c=date_raw,
                    decision_country_verified=True)) + "\n")
            session = ObserverSession(installation, root / "eu4.exe")
            ready = {"status": "ready", "state_id": "r27l", "date_raw": date_raw,
                     "reasons": [], "complete": True}
            api = DiplomacyTools(self.journal, session)
            server_errors = []

            def serve_query():
                request = root / "diplomacy-inbound-query.req"
                deadline = time.monotonic() + 2
                while not request.exists() and time.monotonic() < deadline:
                    time.sleep(0.001)
                if not request.exists():
                    server_errors.append("query timeout")
                    return
                fields = request.read_text(encoding="ascii").rstrip("\n").split("|")
                request.unlink()
                event = dict(actual)
                event["query_id"] = fields[1]
                event["session_id"] = fields[2]
                event["action_id"] = fields[5]
                event["actor"] = fields[6]
                event["phase"] = fields[8]
                event["native_proposal_id"] = int(fields[9])
                event["date_raw"] = int(fields[4])
                with log.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(event) + "\n")

            with patch.object(session, "health", return_value=ready):
                proposal = api.list_diplomatic_actions()["incoming_proposals"][0]
                writer = threading.Thread(target=serve_query)
                writer.start()
                inspected = api.inspect_diplomatic_action(
                    "offer_royal_marriage", actual["actor"], "FRA", "reject",
                    parameters={"proposal_id": proposal["proposal_id"]})
                writer.join(2)
            self.assertFalse(writer.is_alive())
            self.assertEqual([], server_errors)
            self.assertEqual("unavailable", inspected["legality"]["status"])
            self.assertFalse(inspected["legality"]["complete"])
            self.assertEqual("invalidated", inspected["proposal_status"])
            self.assertEqual(
                "NATIVE_INBOUND_PENDING_INVALIDATED",
                inspected["legality"]["reasons"][0]["code"])
            self.assertEqual("native_inbound_rules", inspected["interface_support"]["query"])
            self.assertEqual("native_inbound_response", inspected["interface_support"]["execute"])
            self.assertEqual("available", inspected["authorization"]["status"])
            self.assertTrue(inspected["authorization"]["complete"])
            self.assertEqual(
                "NATIVE_INBOUND_ROYAL_MARRIAGE_RESPONSE_CAPABILITY_ACKNOWLEDGED",
                inspected["authorization"]["reasons"][0]["code"])
            self.assertFalse(inspected["decision_country_verified"])
            self.assertFalse(inspected["native_inbound_inspection"]["decision_country_verified"])
            self.assertEqual("PENDING_NOT_ACTIVE", inspected["native_inbound_inspection"]["reason"])
            self.assertNotEqual(
                "EXECUTION_ADAPTER_UNIMPLEMENTED",
                inspected["authorization"]["reasons"][0]["code"])
            self.assertFalse((root / "diplomacy-respond.req").exists())

    def test_r27_actual_royal_inspection_event_reaches_available_legality(self):
        """Consume the observed r27 event through the wire reader and API."""

        session_id = "41308-1dd5c6283ad1d47"
        date_raw = 56459880
        actual_offer = {
            "event": "native_alliance_inbound_offer", "session_id": session_id,
            "proposal_id": 1, "action_id": "offer_royal_marriage",
            "family": "royal_marriage", "extra60": 0, "phase": "initiate",
            "actor": "SAV", "mirror": "SAV", "recipient": "FRA",
            "date28": 43808760, "date2c": date_raw, "envoy30": 2,
            "state34": 0, "variant38": 1, "proposal3c": 2, "token3c": 2,
            "created2c": date_raw, "queue_before_count": 0,
            "queue_after_count": 1, "queue_readable": True,
            "list_integrity": True, "new_entry": True, "payload_readable": True,
            "decision_country": "FRA", "decision_country_verified": True,
            "pending_source": "native_executor_pending_block",
            "source_verified": True, "call_redirected": True,
            "business_result": "pending_observed",
        }
        actual_inspection = {
            "event": "native_alliance_inbound_inspection",
            "query_id": "inbound_inspect_fb7147b436ca401a856312ef82dcab9a",
            "session_id": session_id, "action_id": "offer_royal_marriage",
            "family": "royal_marriage", "extra60": 0, "actor": "SAV",
            "mirror": "SAV", "recipient": "FRA", "phase": "reject",
            "native_proposal_id": 1, "date_raw": date_raw,
            "pending_active": True, "decision_country": "FRA",
            "decision_country_verified": True, "native_validity": True,
            "response_rules_complete": True, "royal_marriage_before": False,
            "native_current_royal_marriage": False,
            "native_current_royal_marriage_readable": True,
            "date28": 43808760, "date2c": date_raw, "envoy30": 2,
            "state34": 0, "variant38": 1, "token3c": 2,
            "requested_decision": "reject", "reason": "none",
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, log = self._write_royal_inbound_installation(
                root, session_id=session_id)
            with log.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(actual_offer) + "\n")
            session = ObserverSession(installation, root / "eu4.exe")
            journal = DurableJournal(":memory:", "experiment", session_id)
            try:
                api = DiplomacyTools(journal, session)
                ready = {"status": "ready", "state_id": "r27", "date_raw": date_raw,
                         "reasons": [], "complete": True}
                server_errors = []

                def serve_query():
                    request = root / "diplomacy-inbound-query.req"
                    deadline = time.monotonic() + 2
                    while not request.exists() and time.monotonic() < deadline:
                        time.sleep(0.001)
                    if not request.exists():
                        server_errors.append("query timeout")
                        return
                    fields = request.read_text(encoding="ascii").rstrip("\n").split("|")
                    request.unlink()
                    event = dict(actual_inspection)
                    event["query_id"] = fields[1]
                    with log.open("a", encoding="utf-8", newline="\n") as stream:
                        stream.write(json.dumps(event) + "\n")

                with patch.object(session, "health", return_value=ready):
                    proposal = api.list_diplomatic_actions()["incoming_proposals"][0]
                    writer = threading.Thread(target=serve_query)
                    writer.start()
                    inspected = api.inspect_diplomatic_action(
                        "offer_royal_marriage", "SAV", "FRA", "reject",
                        parameters={"proposal_id": proposal["proposal_id"]})
                    writer.join(2)
                self.assertFalse(writer.is_alive())
                self.assertEqual([], server_errors)
                self.assertEqual("available", inspected["legality"]["status"])
                self.assertTrue(inspected["legality"]["complete"])
                self.assertEqual("none", inspected["native_inbound_inspection"]["reason"])
                self.assertEqual("royal_marriage",
                                 inspected["native_inbound_inspection"]["family"])
                self.assertFalse(inspected["native_inbound_inspection"]["royal_marriage_before"])
            finally:
                journal.close()

    def test_r27_actual_submission_and_response_reconcile_to_rejected(self):
        """The observed family-less receipt must complete get_result recovery."""

        events = self._observed_r27_rejection_events()
        submission = events["native_alliance_submission_result"]
        response = events["native_alliance_response_result"]
        session_id = submission["session_id"]
        experiment_id = "diplomacy-query-20261015-r27-royal-inbound-e"
        request_id = "r27e_reject_sav_002"
        payload = {
            "action_id": "offer_royal_marriage", "actor": "SAV",
            "recipient": "FRA", "phase": "reject",
            "parameters": {"proposal_id": "f4ca2ffd79128c2f5d511714686ebe97"},
        }
        invalidated = {
            "submitted": False, "game_outcome": "unknown",
            "inspection": {"session": {"date_raw": submission["date_raw"]}},
            "reason": {"code": "NATIVE_SUBMISSION_RESULT_INVALID"},
        }
        with DurableJournal(":memory:", experiment_id, session_id) as journal:
            journal.register(request_id, payload)
            journal.mark_invalidated(
                request_id, invalidated, evidence_type="native_submission_failure",
                arrival_layer="bridge_validation", event_id="native-submit-failure:r27")
            api = DiplomacyTools(journal)
            recovered = api.reconcile_native_inbound_response(
                request_id, submission, response, native_proposal_id=1)
            self.assertEqual("rejected", recovered["status"])
            self.assertEqual("rejected", recovered["game_outcome"])
            self.assertTrue(recovered["submitted"])
            self.assertEqual("royal_marriage", recovered["result"]["family"])
            self.assertEqual(1, recovered["result"]["native_state"])
            self.assertFalse(recovered["result"]["royal_marriage_after"])
            evidence = journal.list_evidence(request_id)
            self.assertEqual(2, len(evidence))
            self.assertEqual("native_response_reconciliation", evidence[-1].evidence_type)
            repeated = api.get_diplomatic_result(request_id)
            self.assertEqual("rejected", repeated["status"])
            self.assertEqual(2, journal.get_request(request_id).evidence_count)

        # An explicit cross-family discriminator cannot use the repair path,
        # even though the request/action/date fields remain otherwise equal.
        cross_family = dict(submission, family="alliance")
        with DurableJournal(":memory:", experiment_id, session_id) as journal:
            journal.register(request_id, payload)
            journal.mark_invalidated(
                request_id, invalidated, evidence_type="native_submission_failure",
                arrival_layer="bridge_validation", event_id="native-submit-failure:r27")
            unrecovered = DiplomacyTools(journal).reconcile_native_inbound_response(
                request_id, cross_family, response, native_proposal_id=1)
            self.assertEqual("invalidated", unrecovered["status"])
            self.assertFalse(unrecovered["submitted"])

    def test_raw_caps_list_or_string_does_not_grant_royal_query(self):
        for advertised in ([ROYAL_QUERY], ROYAL_QUERY, {"caps": [ROYAL_QUERY]}):
            session = RoyalQuerySession(advertised)
            api = DiplomacyTools(self.journal, session)
            catalog = api.list_diplomatic_actions()
            by_id = {item["action_id"]: item for item in catalog["actions"]}
            self.assertEqual("unimplemented",
                             by_id["offer_royal_marriage"]["phases"]["initiate"]["query"])
            self.assertEqual([], session.inspect_calls)
            result = api.inspect_diplomatic_action("offer_royal_marriage", "FRA", "SAV")
            self.assertEqual("catalog_only", result["interface_support"]["query"])
            self.assertEqual([], session.inspect_calls)

    def test_only_exact_top_level_ack_is_returned_by_observer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = root / "installation.json"
            installation.write_text(json.dumps({
                "experiment_id": "r25", "session_id": "royal-session", "pid": 1,
                "creation_filetime": 2, "dll_sha256": "dll", "installation_returncode": 0,
            }), encoding="utf-8")
            log = root / "control-probe.jsonl"
            base = {"event": "diplomacy_observer_installed", "session_id": "royal-session",
                    "caps": [ROYAL_QUERY]}
            log.write_text(json.dumps({**base, ROYAL_QUERY: False}) + "\n", encoding="utf-8")
            session = ObserverSession(installation, root / "eu4.exe")
            self.assertNotIn(ROYAL_QUERY, session.installation_capabilities())
            log.write_text(json.dumps({**base, ROYAL_QUERY: "true"}) + "\n", encoding="utf-8")
            self.assertNotIn(ROYAL_QUERY, session.installation_capabilities())
            log.write_text(json.dumps({**base, ROYAL_QUERY: True}) + "\n", encoding="utf-8")
            self.assertIn(ROYAL_QUERY, session.installation_capabilities())

    def test_royal_submission_requires_exact_top_level_boolean_ack(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = root / "installation.json"
            installation.write_text(json.dumps({
                "experiment_id": "r26", "session_id": "royal-session", "pid": 1,
                "creation_filetime": 2, "dll_sha256": "dll", "installation_returncode": 0,
            }), encoding="utf-8")
            log = root / "control-probe.jsonl"
            base = {"event": "diplomacy_observer_installed", "session_id": "royal-session",
                    "caps": [ROYAL_SUBMISSION]}
            session = ObserverSession(installation, root / "eu4.exe")
            for value in (False, "true"):
                log.write_text(json.dumps({**base, ROYAL_SUBMISSION: value}) + "\n",
                               encoding="utf-8")
                self.assertNotIn(ROYAL_SUBMISSION, session.installation_capabilities())
            log.write_text(json.dumps({**base, ROYAL_SUBMISSION: True}) + "\n",
                            encoding="utf-8")
            self.assertIn(ROYAL_SUBMISSION, session.installation_capabilities())

    def test_royal_offer_acceptance_is_submitted_and_persisted(self):
        session = RoyalExecutionSession(offer_outcome="accepted")
        api = DiplomacyTools(self.journal, session)
        catalog = api.list_diplomatic_actions(actor="FRA", recipient="SAV")
        offer = next(item for item in catalog["actions"]
                     if item["action_id"] == "offer_royal_marriage")
        self.assertEqual("native_royal_marriage_submission",
                         offer["phases"]["initiate"]["execute"])
        result = api.execute_diplomatic_action("royal_accept", "offer_royal_marriage", "FRA", "SAV")
        self.assertEqual("accepted", result["status"])
        self.assertEqual("accepted", result["game_outcome"])
        self.assertEqual("royal_marriage", result["result"]["family"])
        self.assertFalse(result["result"]["royal_marriage_before"])
        self.assertTrue(result["result"]["royal_marriage_after"])
        self.assertEqual(1, len(session.submit_calls))

    def test_observed_r26_royal_response_without_before_is_read_as_accepted(self):
        """The observed native response omits before but still binds acceptance."""

        # This is the event shape observed in
        # work/runtime/diplomacy-query-20261015-r26-royal-b/
        # royal-marriage-execution-0f2ba3d86df648fabe67069e84085ace/
        # native-events-slice.jsonl (line 100).  Do not add a synthetic
        # royal_marriage_before field: its absence is the regression.
        event = {
            "event": "native_alliance_response_result",
            "request_id": "r26b_rm_sav_001",
            "session_id": "royal-observed-session",
            "action_id": "offer_royal_marriage",
            "actor": "FRA",
            "recipient": "SAV",
            "phase": "initiate",
            "date_raw": 56459880,
            "outcome": "accepted",
            "native_state": 2,
            "family": "royal_marriage",
            "royal_marriage_after": True,
            "response_verified": True,
            "request_binding_verified": True,
            "pending_removed": False,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = root / "installation.json"
            installation.write_text(json.dumps({
                "experiment_id": "r26",
                "session_id": event["session_id"],
                "pid": 1,
                "creation_filetime": 2,
                "dll_sha256": "dll",
                "installation_returncode": 0,
            }), encoding="utf-8")
            (root / "control-probe.jsonl").write_text(
                json.dumps(event) + "\n", encoding="utf-8")
            session = ObserverSession(installation, root / "eu4.exe")
            result = session.read_native_royal_marriage_response(
                event["request_id"], "FRA", "SAV", "initiate", event["date_raw"])

        self.assertEqual("accepted", result["status"])
        self.assertEqual("royal_marriage", result["result"]["family"])
        self.assertFalse(result["result"]["royal_marriage_before"])
        self.assertTrue(result["result"]["royal_marriage_after"])
        self.assertEqual(2, result["result"]["native_state"])

    def test_royal_offer_rejection_is_distinct_from_illegal_submission(self):
        session = RoyalExecutionSession(offer_outcome="rejected")
        result = DiplomacyTools(self.journal, session).execute_diplomatic_action(
            "royal_reject", "offer_royal_marriage", "FRA", "SAV")
        self.assertEqual("rejected", result["status"])
        self.assertEqual("rejected", result["game_outcome"])
        self.assertEqual(1, result["result"]["native_state"])
        self.assertFalse(result["result"]["royal_marriage_after"])
        self.assertEqual("royal_marriage", result["result"]["family"])

    def test_royal_break_uses_execution_event_and_executes(self):
        session = RoyalExecutionSession()
        result = DiplomacyTools(self.journal, session).execute_diplomatic_action(
            "royal_break", "break_royal_ties", "FRA", "SAV")
        self.assertEqual("executed", result["status"])
        self.assertEqual("executed", result["game_outcome"])
        self.assertEqual("native_alliance_execution_result", result["result"]["event"])
        self.assertEqual("royal_marriage", result["result"]["family"])
        self.assertTrue(result["result"]["royal_marriage_before"])
        self.assertFalse(result["result"]["royal_marriage_after"])
        self.assertEqual(0, result["result"]["native_state"])

    def test_royal_result_rejects_cross_family_fields(self):
        royal_response = {
            "event": "native_alliance_response_result", "request_id": "r1",
            "session_id": "s1", "action_id": "offer_royal_marriage", "actor": "FRA",
            "recipient": "SAV", "phase": "initiate", "date_raw": 1,
            "response_verified": True, "request_binding_verified": True,
            "native_state": 2, "alliance_after": True,
        }
        self.assertIsNone(ObserverSession._public_native_response_result(
            royal_response, "r1", "s1", "FRA", "SAV", "initiate", 1,
            "offer_royal_marriage"))
        alliance_break = {
            "event": "native_alliance_execution_result", "request_id": "r1",
            "session_id": "s1", "action_id": "dissolve_alliance", "actor": "FRA",
            "recipient": "SAV", "phase": "initiate", "date_raw": 1,
            "execution_verified": True, "request_binding_verified": True,
            "native_state": 0, "native_variant": 0,
            "alliance_before": True, "alliance_after": False,
        }
        self.assertIsNone(ObserverSession._public_native_royal_break_result(
            alliance_break, "r1", "s1", "FRA", "SAV", "initiate", 1))

    def test_exact_ack_lists_query_for_both_actions_without_execute_authority(self):
        session = RoyalQuerySession(frozenset({ROYAL_QUERY}))
        api = DiplomacyTools(self.journal, session)
        catalog = api.list_diplomatic_actions()
        by_id = {item["action_id"]: item for item in catalog["actions"]}
        for action_id in ("offer_royal_marriage", "break_royal_ties"):
            phase = by_id[action_id]["phases"]["initiate"]
            self.assertEqual("partial_native_rules", phase["query"])
            self.assertEqual("unimplemented", phase["execute"])
        self.assertEqual("unimplemented",
                         by_id["offer_royal_marriage"]["phases"]["accept"]["query"])
        self.assertEqual("unimplemented",
                         by_id["offer_royal_marriage"]["phases"]["reject"]["query"])

    def test_offer_royal_query_distinguishes_native_rejection_from_illegality(self):
        session = RoyalQuerySession(frozenset({ROYAL_QUERY}))
        api = DiplomacyTools(self.journal, session)
        result = api.inspect_diplomatic_action("offer_royal_marriage", "FRA", "SAV")
        self.assertEqual("available", result["legality"]["status"])
        self.assertTrue(result["legality"]["complete"])
        self.assertTrue(result["acceptance"]["prediction_available"])
        self.assertEqual("reject", result["acceptance"]["predicted_response"])
        self.assertEqual("native_current_acceptance_check",
                         result["acceptance"]["prediction_basis"])
        self.assertEqual([("offer_royal_marriage", "FRA", "SAV", "initiate")],
                         session.inspect_calls)

    def test_government_native_false_is_unavailable(self):
        session = RoyalQuerySession(frozenset({ROYAL_QUERY}), native_validity=False)
        result = DiplomacyTools(self.journal, session).inspect_diplomatic_action(
            "offer_royal_marriage", "FRA", "SAV")
        self.assertEqual("unavailable", result["legality"]["status"])
        self.assertTrue(any(item["code"] == "NATIVE_VALIDITY_FALSE"
                            for item in result["legality"]["reasons"]))

    def test_break_royal_ties_has_no_acceptance_prediction(self):
        session = RoyalQuerySession(frozenset({ROYAL_QUERY}))
        result = DiplomacyTools(self.journal, session).inspect_diplomatic_action(
            "break_royal_ties", "FRA", "SAV")
        self.assertEqual("not_applicable", result["acceptance"]["applicability"])
        self.assertTrue(result["acceptance"]["complete"])
        self.assertFalse(result["acceptance"]["prediction_available"])
        self.assertNotIn("acceptance_gate", result["native_rule_components"])

    def test_query_ack_does_not_enable_royal_execution(self):
        session = RoyalQuerySession(frozenset({ROYAL_QUERY}))
        result = DiplomacyTools(self.journal, session).execute_diplomatic_action(
            "royal_execute_1", "offer_royal_marriage", "FRA", "SAV")
        self.assertEqual("invalidated", result["status"])
        self.assertFalse(result["submitted"])
        self.assertEqual("EXECUTION_ADAPTER_UNIMPLEMENTED", result["result"]["reason"]["code"])
        self.assertEqual([], session.submit_calls)

    def test_royal_query_rejects_nonempty_initiate_parameters(self):
        session = RoyalQuerySession(frozenset({ROYAL_QUERY}))
        with self.assertRaisesRegex(ValueError, "ROYAL_MARRIAGE_PARAMETERS_UNSUPPORTED"):
            DiplomacyTools(self.journal, session).inspect_diplomatic_action(
                "offer_royal_marriage", "FRA", "SAV", parameters={"queen": True})

    def test_public_result_contains_no_private_coordinates(self):
        session = RoyalQuerySession(frozenset({ROYAL_QUERY}), RVA="0x141c5f580",
                                    native_object=0x12345678, session_id="private")
        result = DiplomacyTools(self.journal, session).inspect_diplomatic_action(
            "offer_royal_marriage", "FRA", "SAV")
        serialized = json.dumps(result, ensure_ascii=False)
        for private in ("session_id", "native_object", "RVA", "rva", "0x12345678"):
            self.assertNotIn(private, serialized)


if __name__ == "__main__":
    unittest.main()
