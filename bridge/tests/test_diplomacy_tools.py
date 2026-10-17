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


class ReadySession:
    def __init__(self):
        self.checks = 0
        self.inspect_calls = 0

    def health(self):
        self.checks += 1
        return {"status": "ready", "state_id": str(self.checks), "date_raw": 1, "reasons": [], "complete": True}

    def alliance_objects(self, actor, recipient):
        return {"status": "observed", "items": [], "complete": False, "reason_code": "QUEUE_LIFECYCLE_NOT_RECOVERED"}

    def inspect_alliance(self, action_id, actor, recipient, phase):
        self.inspect_calls += 1
        return None


class NativeSession(ReadySession):
    def __init__(self, **overrides):
        super().__init__()
        self.native = {"display_predicate": True, "common_action_gate": True,
                       "validity_called": True, "native_validity": True, "initiation_gate": True,
                       "score_applicable": True, "score_available": True, "native_total_raw": 64,
                       "acceptance_threshold_raw": 1, "reason_count": 6, "reason_items": [],
                       "reason_items_truncated": False, "date_raw": 1, **overrides}

    def inspect_alliance(self, action_id, actor, recipient, phase):
        return self.native


class NativeSubmissionSession(NativeSession):
    def __init__(self, *, capabilities=None, submit_response=None, unready=False, **overrides):
        super().__init__(**overrides)
        self.native.update(ui_selection_checked=True, native_visibility=True,
                           ui_enabled_gate_checked=True, tooltip_gate=True,
                           full_rules_complete=True)
        self.capabilities = frozenset(capabilities or {"native_offer_submission"})
        self.submit_response = submit_response
        self.submit_calls = []
        self.unready = unready

    def installation_capabilities(self):
        return self.capabilities

    def health(self):
        if self.unready:
            return {"status": "unready", "state_id": None, "date_raw": None,
                    "reasons": [], "complete": False}
        return super().health()

    def submit_offer_alliance(self, request_id, actor, recipient, phase, date_raw):
        self.submit_calls.append((request_id, actor, recipient, phase, date_raw))
        if self.submit_response is not None:
            return self.submit_response
        return {"status": "submitted", "receipt": {
            "event": "native_alliance_submission_result", "request_id": request_id,
            "action_id": "offer_alliance", "actor": actor, "recipient": recipient,
            "phase": phase, "date_raw": date_raw, "submitted": True,
            "native_queue_verified": True, "transport_ring_receipt": True,
            "native_sequence": 7, "native_origin": 1, "native_flags": 0,
        }}


class DiplomacyToolsTests(unittest.TestCase):
    def setUp(self):
        self.journal = DurableJournal(":memory:", "experiment", "session")
        self.api = DiplomacyTools(self.journal)

    def tearDown(self):
        self.journal.close()

    @staticmethod
    def _inbound_event(session_id="session", proposal_id=17, **overrides):
        event = {
            "event": "native_alliance_inbound_offer",
            "session_id": session_id,
            "proposal_id": proposal_id,
            "action_id": "offer_alliance",
            "phase": "initiate",
            "actor": "SAV",
            "mirror": "SAV",
            "recipient": "FRA",
            "date28": 56459880,
            "date2c": 56459880,
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
            "decision_country": "FRA",
            "decision_country_verified": True,
            "pending_source": "native_executor_pending_block",
            "source_verified": True,
            "call_redirected": True,
            "business_result": "pending_observed",
        }
        event.update(overrides)
        return event

    @staticmethod
    def _write_inbound_installation(root, session_id="session", response_capability=False):
        installation = root / "installation.json"
        installation.write_text(json.dumps({
            "experiment_id": "experiment", "session_id": session_id,
            "pid": 1, "creation_filetime": 2, "dll_sha256": "dll",
            "installation_returncode": 0,
        }), encoding="utf-8")
        log = root / "control-probe.jsonl"
        ack = {
            "event": "diplomacy_observer_installed", "session_id": session_id,
            "native_inbound_alliance": True,
        }
        if response_capability:
            ack["native_inbound_alliance_response"] = True
        log.write_text(json.dumps(ack) + "\n", encoding="utf-8")
        return installation, log

    @staticmethod
    def _inbound_inspection_event(query_id, session_id="session", actor="SAV",
                                  phase="accept", proposal_id=17, date_raw=1,
                                  **overrides):
        event = {
            "event": "native_alliance_inbound_inspection",
            "query_id": query_id,
            "session_id": session_id,
            "action_id": "offer_alliance",
            "actor": actor,
            "recipient": "FRA",
            "phase": phase,
            "native_proposal_id": proposal_id,
            "date_raw": date_raw,
            "pending_active": True,
            "decision_country": "FRA",
            "decision_country_verified": True,
            "native_validity": True,
            "response_rules_complete": True,
            "alliance_before": False,
        }
        event.update(overrides)
        return event

    def test_native_inbound_ack_and_valid_event_become_one_safe_public_offer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, log = self._write_inbound_installation(root)
            with log.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(self._inbound_event()) + "\n")
            session = ObserverSession(installation, root / "eu4.exe")
            ready = {"status": "ready", "state_id": "opaque", "date_raw": 56459880,
                     "reasons": [], "complete": True}
            api = DiplomacyTools(self.journal, session)
            with patch.object(session, "health", return_value=ready):
                first = api.list_diplomatic_actions()
                second = api.list_diplomatic_actions(recipient="FRA")
                self.assertEqual(frozenset({"native_inbound_alliance"}),
                                 session.installation_capabilities())
            self.assertEqual(1, len(first["incoming_proposals"]))
            self.assertEqual(1, len(second["incoming_proposals"]))
            proposal = first["incoming_proposals"][0]
            self.assertEqual("observed_pending", proposal["observer_status"])
            self.assertIsNone(proposal["currently_pending"])
            self.assertEqual("unknown", proposal["legality"]["status"])
            self.assertEqual("unimplemented", proposal["execute"]["accept"])
            self.assertNotEqual("17", proposal["proposal_id"])
            self.assertEqual(proposal["proposal_id"], second["incoming_proposals"][0]["proposal_id"])
            public = json.dumps(first, ensure_ascii=False)
            for private in ("session_id", "token3c", "envoy30", "date28", "date2c",
                            "proposal3c", "rawtoken", "RVA", "rva", "pid"):
                self.assertNotIn(private, public)

    def test_native_inbound_rejects_wrong_session_and_missing_proof_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, log = self._write_inbound_installation(root)
            invalid = self._inbound_event(session_id="other", proposal_id=1)
            missing_proof = self._inbound_event(proposal_id=2, call_redirected=False)
            wrong_state_type = self._inbound_event(proposal_id=3, state34=False)
            wrong_variant_type = self._inbound_event(proposal_id=4, variant38=True)
            with log.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(invalid) + "\n")
                stream.write(json.dumps(missing_proof) + "\n")
                stream.write(json.dumps(wrong_state_type) + "\n")
                stream.write(json.dumps(wrong_variant_type) + "\n")
            session = ObserverSession(installation, root / "eu4.exe")
            ready = {"status": "ready", "state_id": "opaque", "date_raw": 1,
                     "reasons": [], "complete": True}
            api = DiplomacyTools(self.journal, session)
            with patch.object(session, "health", return_value=ready):
                self.assertEqual([], api.list_diplomatic_actions()["incoming_proposals"])
                valid = self._inbound_event(proposal_id=9)
                with log.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(valid) + "\n")
                    stream.write(json.dumps(valid) + "\n")
                first = api.list_diplomatic_actions()["incoming_proposals"]
                second = api.list_diplomatic_actions()["incoming_proposals"]
            self.assertEqual(1, len(first))
            self.assertEqual(first, second)

    def test_inbound_response_inspection_shows_reference_without_authorizing_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, log = self._write_inbound_installation(root)
            with log.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(self._inbound_event()) + "\n")
            session = ObserverSession(installation, root / "eu4.exe")
            ready = {"status": "ready", "state_id": "opaque", "date_raw": 1,
                     "reasons": [], "complete": True}
            api = DiplomacyTools(self.journal, session)
            with patch.object(session, "health", return_value=ready):
                proposal = api.list_diplomatic_actions()["incoming_proposals"][0]
                inspected = api.inspect_diplomatic_action(
                    "offer_alliance", "SAV", "FRA", "accept",
                    parameters={"proposal_id": proposal["proposal_id"]})
                missing = api.inspect_diplomatic_action(
                    "offer_alliance", "SAV", "FRA", "reject",
                    parameters={"proposal_id": "0" * 32})
                executed = api.execute_diplomatic_action(
                    "inbound_response_1", "offer_alliance", "SAV", "FRA", "accept",
                    parameters={"proposal_id": proposal["proposal_id"]})
            self.assertTrue(inspected["decision_country_verified"])
            self.assertEqual("FRA", inspected["decision_country"])
            self.assertEqual(proposal["proposal_id"],
                             inspected["observed_inbound_proposal"]["proposal_id"])
            self.assertEqual("unknown", inspected["legality"]["status"])
            self.assertEqual("unavailable", inspected["authorization"]["status"])
            self.assertEqual("unimplemented", inspected["interface_support"]["execute"])
            self.assertEqual("INVALID_PROPOSAL_REFERENCE", missing["legality"]["reasons"][0]["code"])
            self.assertEqual("invalidated", executed["status"])
            self.assertFalse(executed["submitted"])
            self.assertFalse((root / "diplomacy-execute.req").exists())

    def test_r22_fresh_inbound_rule_query_authorizes_only_complete_pending_rules(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, log = self._write_inbound_installation(
                root, response_capability=True)
            with log.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(self._inbound_event()) + "\n")
            session = ObserverSession(installation, root / "eu4.exe")
            ready = {"status": "ready", "state_id": "opaque", "date_raw": 1,
                     "reasons": [], "complete": True}
            api = DiplomacyTools(self.journal, session)
            with patch.object(session, "health", return_value=ready):
                catalog = api.list_diplomatic_actions()
                proposal = catalog["incoming_proposals"][0]
                offer = next(action for action in catalog["actions"] if action["action_id"] == "offer_alliance")
                for response_phase in ("accept", "reject"):
                    self.assertEqual("native_inbound_response_inspection", offer["phases"][response_phase]["query"])
                    self.assertEqual("native_inbound_response", proposal["execute"][response_phase])
                self.assertIsNone(proposal["currently_pending"])

                def serve_query():
                    request = root / "diplomacy-inbound-query.req"
                    deadline = time.monotonic() + 2
                    while not request.exists() and time.monotonic() < deadline:
                        time.sleep(0.001)
                    self.assertTrue(request.exists())
                    fields = request.read_text(encoding="ascii").rstrip("\n").split("|")
                    request.unlink()
                    event = self._inbound_inspection_event(
                        fields[1], fields[2], actor=fields[6], phase=fields[8],
                        proposal_id=int(fields[9]), date_raw=int(fields[4]))
                    with log.open("a", encoding="utf-8", newline="\n") as stream:
                        stream.write(json.dumps(event) + "\n")

                writer = threading.Thread(target=serve_query)
                writer.start()
                inspected = api.inspect_diplomatic_action(
                    "offer_alliance", "SAV", "FRA", "accept",
                    parameters={"proposal_id": proposal["proposal_id"]})
                writer.join(2)
                self.assertFalse(writer.is_alive())
            self.assertEqual("available", inspected["legality"]["status"])
            self.assertEqual("available", inspected["authorization"]["status"])
            self.assertEqual("native_inbound_response",
                             inspected["interface_support"]["execute"])
            self.assertTrue(inspected["native_inbound_inspection"]["response_rules_complete"])
            serialized = json.dumps(inspected, ensure_ascii=False)
            for private in ("native_proposal_id", "session_id", "pid", "token3c", "RVA", "rva"):
                self.assertNotIn(private, serialized)

    def test_r22_unknown_mismatch_and_stale_pending_never_publish_response(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, log = self._write_inbound_installation(
                root, response_capability=True)
            with log.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(self._inbound_event()) + "\n")
            session = ObserverSession(installation, root / "eu4.exe")
            ready = {"status": "ready", "state_id": "opaque", "date_raw": 1,
                     "reasons": [], "complete": True}
            api = DiplomacyTools(self.journal, session)
            with patch.object(session, "health", return_value=ready):
                proposal = api.list_diplomatic_actions()["incoming_proposals"][0]
                with patch.object(session, "inspect_native_inbound_response",
                                  return_value={"error_code": "QUERY_OBSERVATION_TIMEOUT"}):
                    unknown = api.inspect_diplomatic_action(
                        "offer_alliance", "SAV", "FRA", "accept",
                        parameters={"proposal_id": proposal["proposal_id"]})
                    result = api.execute_diplomatic_action(
                        "r22_unknown", "offer_alliance", "SAV", "FRA", "accept",
                        parameters={"proposal_id": proposal["proposal_id"]})
                mismatch = api.inspect_diplomatic_action(
                    "offer_alliance", "LIT", "FRA", "accept",
                    parameters={"proposal_id": proposal["proposal_id"]})
                stale = self._inbound_inspection_event(
                    "unused", pending_active=False)
                with patch.object(session, "inspect_native_inbound_response",
                                  return_value=stale):
                    stale_result = api.execute_diplomatic_action(
                        "r22_stale", "offer_alliance", "SAV", "FRA", "reject",
                        parameters={"proposal_id": proposal["proposal_id"]})
            self.assertEqual("unknown", unknown["legality"]["status"])
            self.assertEqual("native_inbound_response",
                             unknown["interface_support"]["execute"])
            self.assertEqual("available", unknown["authorization"]["status"])
            self.assertEqual("NATIVE_INBOUND_RESPONSE_CAPABILITY_ACKNOWLEDGED",
                             unknown["authorization"]["reasons"][0]["code"])
            self.assertEqual("invalidated", result["status"])
            self.assertEqual("INVALID_PROPOSAL_REFERENCE",
                             mismatch["legality"]["reasons"][0]["code"])
            self.assertEqual("invalidated", stale_result["status"])
            self.assertFalse((root / "diplomacy-respond.req").exists())

    def test_r22_inbound_accept_reject_persist_pending_removed_and_duplicate_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, log = self._write_inbound_installation(
                root, response_capability=True)
            with log.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(self._inbound_event(proposal_id=17)) + "\n")
                stream.write(json.dumps(self._inbound_event(
                    proposal_id=18, actor="LIT", mirror="LIT")) + "\n")
            session = ObserverSession(installation, root / "eu4.exe")
            ready = {"status": "ready", "state_id": "opaque", "date_raw": 1,
                     "reasons": [], "complete": True}
            api = DiplomacyTools(self.journal, session)
            with patch.object(session, "health", return_value=ready):
                proposals = api.list_diplomatic_actions()["incoming_proposals"]
                by_actor = {item["actor"]: item for item in proposals}

                def run_one(request_id, actor, phase, outcome):
                    public_id = by_actor[actor]["proposal_id"]

                    def serve():
                        query = root / "diplomacy-inbound-query.req"
                        deadline = time.monotonic() + 2
                        while not query.exists() and time.monotonic() < deadline:
                            time.sleep(0.001)
                        self.assertTrue(query.exists())
                        query_fields = query.read_text(encoding="ascii").rstrip("\n").split("|")
                        query.unlink()
                        inspection_event = self._inbound_inspection_event(
                            query_fields[1], query_fields[2], actor=query_fields[6],
                            phase=query_fields[8], proposal_id=int(query_fields[9]),
                            date_raw=int(query_fields[4]))
                        with log.open("a", encoding="utf-8", newline="\n") as stream:
                            stream.write(json.dumps(inspection_event) + "\n")
                        response = root / "diplomacy-respond.req"
                        while not response.exists() and time.monotonic() < deadline:
                            time.sleep(0.001)
                        self.assertTrue(response.exists())
                        response_fields = response.read_text(encoding="ascii").rstrip("\n").split("|")
                        response.unlink()
                        submission_event = {
                            "event": "native_alliance_submission_result",
                            "request_id": response_fields[1], "session_id": response_fields[2],
                            "action_id": response_fields[5], "actor": response_fields[6],
                            "recipient": response_fields[7], "phase": response_fields[8],
                            "native_proposal_id": int(response_fields[9]),
                            "date_raw": int(response_fields[4]), "submitted": True,
                            "native_queue_verified": True,
                            "transport_ring": {"receipt": True},
                            "native_sequence": 7, "native_origin": 1, "native_flags": 0,
                        }
                        response_event = {
                            "event": "native_alliance_response_result",
                            "request_id": response_fields[1], "session_id": response_fields[2],
                            "action_id": "offer_alliance", "actor": response_fields[6],
                            "recipient": "FRA", "phase": response_fields[8],
                            "native_proposal_id": int(response_fields[9]),
                            "date_raw": int(response_fields[4]),
                            "response_verified": True, "request_binding_verified": True,
                            "native_state": 2 if outcome == "accepted" else 1,
                            "alliance_after": outcome == "accepted", "pending_removed": True,
                        }
                        with log.open("a", encoding="utf-8", newline="\n") as stream:
                            stream.write(json.dumps(submission_event) + "\n")
                            stream.write(json.dumps(response_event) + "\n")

                    writer = threading.Thread(target=serve)
                    writer.start()
                    result = api.execute_diplomatic_action(
                        request_id, "offer_alliance", actor, "FRA", phase,
                        parameters={"proposal_id": public_id})
                    writer.join(2)
                    self.assertFalse(writer.is_alive())
                    result = api.get_diplomatic_result(request_id)
                    self.assertEqual(outcome, result["status"])
                    self.assertEqual(outcome, result["game_outcome"])
                    return result

                with patch.object(session, "submit_native_inbound_response",
                                  wraps=session.submit_native_inbound_response) as submitter:
                    accepted = run_one("r22_accept", "SAV", "accept", "accepted")
                    rejected = run_one("r22_reject", "LIT", "reject", "rejected")
                    calls_before_duplicate = submitter.call_count
                    duplicate = api.execute_diplomatic_action(
                        "r22_accept", "offer_alliance", "SAV", "FRA", "accept",
                        parameters={"proposal_id": by_actor["SAV"]["proposal_id"]})
                    self.assertEqual(2, calls_before_duplicate)
                    self.assertEqual(calls_before_duplicate, submitter.call_count)
            self.assertEqual("accepted", accepted["status"])
            self.assertEqual("rejected", rejected["status"])
            self.assertTrue(duplicate["idempotent"])
            serialized = json.dumps(accepted, ensure_ascii=False) + json.dumps(rejected, ensure_ascii=False)
            for private in ("native_proposal_id", "session_id", "pid", "token3c", "RVA", "rva"):
                self.assertNotIn(private, serialized)

    def test_priority_catalog_has_40_entries_and_separate_support_independence(self):
        entries = self.api.list_diplomatic_actions()["actions"]
        # The priority catalog contains 19 common diplomatic actions and 19
        # common peace terms.  Support Independence is a separate response
        # family with a matching single-party revoke action.
        self.assertEqual(40, len(entries))
        self.assertEqual(21, sum(entry["category"] == "diplomatic_action" for entry in entries))
        self.assertEqual(19, sum(entry["category"] == "peace_term" for entry in entries))
        by_id = {entry["action_id"]: entry for entry in entries}
        self.assertEqual({"support_independence", "revoke_support_independence"},
                         {action_id for action_id in by_id
                          if action_id in {"support_independence", "revoke_support_independence"}})
        self.assertEqual({}, by_id["support_independence"]["parameter_definitions"])
        self.assertEqual({}, by_id["revoke_support_independence"]["parameter_definitions"])
        self.assertEqual("military_access", by_id["ask_military_access"]["native_identifier"])
        self.assertEqual("military_access", by_id["cancel_military_access"]["native_identifier"])
        self.assertEqual({}, by_id["ask_military_access"]["parameter_definitions"])
        self.assertEqual({}, by_id["cancel_military_access"]["parameter_definitions"])
        self.assertEqual("applicable",
                         self.api.inspect_diplomatic_action(
                             "support_independence", "FRA", "SAV")["acceptance"]["applicability"])
        self.assertEqual("not_applicable",
                         self.api.inspect_diplomatic_action(
                             "revoke_support_independence", "FRA", "SAV")["acceptance"]["applicability"])
        self.assertEqual("applicable",
                         self.api.inspect_diplomatic_action(
                             "ask_military_access", "FRA", "SAV")["acceptance"]["applicability"])
        self.assertEqual("not_applicable",
                         self.api.inspect_diplomatic_action(
                             "cancel_military_access", "FRA", "SAV")["acceptance"]["applicability"])
        self.assertNotEqual(by_id["proclaim_guarantee"]["native_identifier"], by_id["support_independence"]["native_identifier"])
        self.assertTrue(all(not entry["runtime_verified"] for entry in entries))

    def test_ready_session_without_capability_method_keeps_queue_fallback(self):
        entries = DiplomacyTools(self.journal, ReadySession()).list_diplomatic_actions()["actions"]
        offer = next(entry for entry in entries if entry["action_id"] == "offer_alliance")
        self.assertEqual("partial_native_queue_read", offer["phases"]["initiate"]["query"])

    def test_ready_session_does_not_invent_legality_or_acceptance(self):
        session = ReadySession()
        api = DiplomacyTools(self.journal, session)
        result = api.inspect_diplomatic_action("offer_alliance", "FRA", "ENG")
        self.assertEqual("ready", result["session"]["status"])
        self.assertEqual("unknown", result["legality"]["status"])
        self.assertIsNone(result["acceptance"]["native_total"])
        self.assertFalse(result["acceptance"]["prediction_available"])
        self.assertFalse(result["legality"]["complete"])
        self.assertIsNone(result["decision_country"])
        self.assertFalse(result["decision_country_verified"])
        self.assertEqual("FRA", result["requested_decision_country"])

    def test_native_offer_capability_advertises_execute_support_only_for_initiate(self):
        native = NativeSubmissionSession()
        api = DiplomacyTools(self.journal, native)
        catalog = api.list_diplomatic_actions(actor="FRA", recipient="ENG")
        offer = next(action for action in catalog["actions"] if action["action_id"] == "offer_alliance")
        self.assertEqual("native_offer_submission", offer["phases"]["initiate"]["execute"])
        self.assertEqual("NATIVE_OFFER_SUBMISSION_CAPABILITY_ACKNOWLEDGED",
                         offer["phases"]["initiate"]["execute_reason_code"])

        initiate = api.inspect_diplomatic_action("offer_alliance", "FRA", "ENG", "initiate")
        self.assertEqual("native_offer_submission", initiate["interface_support"]["execute"])
        self.assertFalse(initiate["interface_support"]["complete"])
        self.assertEqual("available", initiate["authorization"]["status"])
        self.assertEqual("NATIVE_OFFER_SUBMISSION_CAPABILITY_ACKNOWLEDGED",
                         initiate["authorization"]["reasons"][0]["code"])

        accept = api.inspect_diplomatic_action("offer_alliance", "FRA", "ENG", "accept")
        self.assertEqual("unimplemented", accept["interface_support"]["execute"])
        self.assertEqual("unavailable", accept["authorization"]["status"])

    def test_unilateral_acceptance_is_not_applicable(self):
        result = self.api.inspect_diplomatic_action("proclaim_guarantee", "FRA", "ENG")
        self.assertEqual("not_applicable", result["acceptance"]["applicability"])

    def test_native_cancel_query_keeps_acceptance_not_applicable(self):
        result = DiplomacyTools(self.journal, NativeSession()).inspect_diplomatic_action(
            "dissolve_alliance", "FRA", "PRO")
        self.assertEqual("not_applicable", result["acceptance"]["applicability"])
        self.assertTrue(result["acceptance"]["complete"])
        self.assertFalse(result["acceptance"]["prediction_available"])
        self.assertEqual([], result["acceptance"]["items"])
        self.assertNotIn("acceptance_gate", result["native_rule_components"])

    def test_peace_needs_full_context_and_matching_term(self):
        with self.assertRaisesRegex(ValueError, "PEACE_CONTEXT_REQUIRED"):
            self.api.inspect_diplomatic_action("white_peace", "FRA", "ENG")
        context = {"war_id": "war_1", "direction": "demand", "actor_war_role": "attacker",
                   "recipient_war_role": "defender", "terms": [{"action_id": "white_peace", "parameters": {}}]}
        result = self.api.inspect_diplomatic_action("white_peace", "FRA", "ENG", parameters={"peace_context": context})
        self.assertEqual("unknown", result["legality"]["status"])
        context["terms"] = []
        with self.assertRaisesRegex(ValueError, "ACTION_MISSING"):
            self.api.inspect_diplomatic_action("white_peace", "FRA", "ENG", parameters={"peace_context": context})

    def test_unimplemented_execution_is_persisted_without_submission(self):
        first = self.api.execute_diplomatic_action("alliance_1", "offer_alliance", "FRA", "ENG")
        self.assertEqual("invalidated", first["status"])
        self.assertFalse(first["submitted"])
        self.assertEqual("unknown", first["game_outcome"])
        again = self.api.execute_diplomatic_action("alliance_1", "offer_alliance", "FRA", "ENG")
        self.assertTrue(again["idempotent"])
        self.assertEqual(1, len(again["evidence"]))
        conflict = self.api.execute_diplomatic_action("alliance_1", "offer_alliance", "FRA", "CAS")
        self.assertEqual("conflict", conflict["status"])
        self.assertEqual("ENG", self.journal.get_request("alliance_1").payload["recipient"])

    def test_offer_alliance_initiate_rejects_nonempty_parameters(self):
        native = NativeSubmissionSession()
        with self.assertRaisesRegex(ValueError, "OFFER_ALLIANCE_PARAMETERS_UNSUPPORTED"):
            DiplomacyTools(self.journal, native).execute_diplomatic_action(
                "native_parameters", "offer_alliance", "FRA", "ENG",
                parameters={"unsupported": True})
        self.assertEqual([], native.submit_calls)
        self.assertEqual([], self.journal.list_requests())

    def test_native_offer_submission_success_records_only_verified_receipt(self):
        native = NativeSubmissionSession()
        result = DiplomacyTools(self.journal, native).execute_diplomatic_action(
            "native_1", "offer_alliance", "FRA", "ENG")
        self.assertEqual("submitted", result["status"])
        self.assertTrue(result["submitted"])
        self.assertEqual("unknown", result["game_outcome"])
        self.assertEqual(1, len(native.submit_calls))
        self.assertTrue(result["submitted"])
        serialized = json.dumps(result)
        for private in ("session_id", "pid", "RVA", "rva", "C:/", "C:\\"):
            self.assertNotIn(private, serialized)
        self.assertEqual("available", result["result"]["inspection"]["authorization"]["status"])
        self.assertTrue(result["result"]["inspection"]["authorization"]["complete"])
        self.assertEqual(1, self.journal.get_request("native_1").native_receipt["native_origin"])

    def test_native_offer_capability_off_keeps_unimplemented_and_never_calls_submit(self):
        native = NativeSubmissionSession(capabilities={"native_alliance_inspection"})
        result = DiplomacyTools(self.journal, native).execute_diplomatic_action(
            "native_2", "offer_alliance", "FRA", "ENG")
        self.assertEqual("invalidated", result["status"])
        self.assertFalse(result["submitted"])
        self.assertEqual("EXECUTION_ADAPTER_UNIMPLEMENTED", result["result"]["reason"]["code"])
        self.assertEqual([], native.submit_calls)

    def test_native_offer_requires_ready_session_and_available_legality(self):
        for label, native in (
                ("unready", NativeSubmissionSession(unready=True)),
                ("illegal", NativeSubmissionSession(native_validity=False)),):
            result = DiplomacyTools(self.journal, native).execute_diplomatic_action(
                "native_" + label, "offer_alliance", "FRA", "ENG")
            self.assertEqual("invalidated", result["status"])
            self.assertFalse(result["submitted"])
            self.assertEqual([], native.submit_calls)
            self.assertIn(result["result"]["reason"]["code"],
                          {"NATIVE_SESSION_UNREADY", "NATIVE_LEGALITY_UNAVAILABLE"})

    def test_native_offer_rejects_malformed_receipt_without_marking_submitted(self):
        native = NativeSubmissionSession(submit_response={
            "status": "submitted", "receipt": {"submitted": True,
                                                   "transport_ring_receipt": True,
                                                   "native_sequence": 7}})
        result = DiplomacyTools(self.journal, native).execute_diplomatic_action(
            "native_bad_receipt", "offer_alliance", "FRA", "ENG")
        self.assertEqual("invalidated", result["status"])
        self.assertFalse(result["submitted"])
        self.assertEqual("NATIVE_SUBMISSION_RECEIPT_INVALID", result["result"]["reason"]["code"])
        self.assertIsNone(self.journal.get_request("native_bad_receipt").native_receipt)

    def test_native_offer_duplicate_request_never_submits_twice(self):
        native = NativeSubmissionSession()
        api = DiplomacyTools(self.journal, native)
        first = api.execute_diplomatic_action("native_duplicate", "offer_alliance", "FRA", "ENG")
        second = api.execute_diplomatic_action("native_duplicate", "offer_alliance", "FRA", "ENG")
        self.assertEqual("submitted", first["status"])
        self.assertEqual("submitted", second["status"])
        self.assertTrue(second["idempotent"])
        self.assertTrue(second["submitted"])
        self.assertEqual(1, len(native.submit_calls))

    def test_native_offer_timeout_is_unknown_and_never_retried(self):
        native = NativeSubmissionSession(submit_response={
            "status": "timeout", "reason_code": "NATIVE_SUBMISSION_TIMEOUT"})
        api = DiplomacyTools(self.journal, native)
        first = api.execute_diplomatic_action("native_timeout", "offer_alliance", "FRA", "ENG")
        second = api.execute_diplomatic_action("native_timeout", "offer_alliance", "FRA", "ENG")
        self.assertEqual("unknown", first["status"])
        self.assertEqual("unknown", first["game_outcome"])
        self.assertEqual("unknown", second["status"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(1, len(native.submit_calls))

    def test_observer_native_offer_uses_atomic_ascii_execute_wire(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            session_id = "session-wire"
            installation = directory / "installation.json"
            installation.write_text(json.dumps({
                "experiment_id": "observer-test", "session_id": session_id,
                "pid": 52544, "creation_filetime": 1234, "dll_sha256": "dll",
                "installation_returncode": 0,
            }), encoding="utf-8")
            log = directory / "control-probe.jsonl"
            log.write_text(json.dumps({
                "event": "diplomacy_observer_installed", "session_id": session_id,
                "caps": ["native_offer_submission"],
            }) + "\n", encoding="utf-8")
            session = ObserverSession(installation, directory / "eu4.exe")
            observed = []

            def append_result():
                request = directory / "diplomacy-execute.req"
                deadline = time.monotonic() + 2
                while not request.exists() and time.monotonic() < deadline:
                    time.sleep(0.001)
                if not request.exists():
                    return
                wire = request.read_text(encoding="ascii")
                observed.append(wire)
                fields = wire.rstrip("\n").split("|")
                event = {
                    "event": "native_alliance_submission_result", "request_id": fields[1],
                    "session_id": fields[2], "date_raw": int(fields[4]), "actor": fields[6],
                    "recipient": fields[7], "phase": fields[8], "submitted": True,
                    "native_queue_verified": True, "transport_ring": {"receipt": True},
                    "native_sequence": 11, "native_origin": 1, "native_flags": 0,
                }
                with log.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(event) + "\n")

            writer = threading.Thread(target=append_result)
            writer.start()
            result = session.submit_offer_alliance("wire_1", "FRA", "ENG", "initiate", 42, timeout=2)
            writer.join(2)
            self.assertFalse(writer.is_alive())
            self.assertEqual("submitted", result["status"])
            self.assertEqual(1, len(observed))
            fields = observed[0].rstrip("\n").split("|")
            self.assertEqual(9, len(fields))
            self.assertEqual(["v1", "wire_1", session_id, "42", "offer_alliance", "FRA", "ENG", "initiate"],
                             [fields[0], fields[1], fields[2], fields[4], fields[5], fields[6], fields[7], fields[8]])
            self.assertGreater(int(fields[3]), int(time.time_ns() // 100 + 116444736000000000))
            self.assertFalse(list(directory.glob("*.pending")))
            self.assertEqual(
                "NATIVE_SUBMISSION_WIRE_INVALID",
                session.submit_offer_alliance("wire_bad_recipient", "FRA", "E2G", "initiate", 42)["reason_code"],
            )
            self.assertEqual(
                "NATIVE_SUBMISSION_DATE_INVALID",
                session.submit_offer_alliance("wire_bad_date", "FRA", "ENG", "initiate", 0x80000000)["reason_code"],
            )

    def test_native_submission_result_requires_identity_and_transport_shape(self):
        valid = {
            "event": "native_alliance_submission_result", "request_id": "r1",
            "session_id": "s1", "actor": "FRA", "recipient": "ENG",
            "phase": "initiate", "date_raw": 42, "submitted": True,
            "native_queue_verified": True, "transport_ring": {"receipt": True},
            "native_sequence": 7, "native_origin": 1, "native_flags": 0,
        }
        check = lambda event: ObserverSession._valid_native_submission_result(
            event, "r1", "s1", "FRA", "ENG", "initiate", 42)
        self.assertTrue(check(valid))
        for field, value in (("request_id", "other"), ("session_id", "other"),
                             ("actor", "ENG"), ("recipient", "FRA"),
                             ("phase", "accept"), ("native_sequence", "1"),
                             ("date_raw", None), ("date_raw", 0x80000000),
                             ("native_sequence", 0x100000000),
                             ("native_queue_verified", False),
                             ("transport_ring", {"verified": True}),
                             ("native_flags", -1), ("native_flags", 0x100),
                             ("native_origin", 0x10000), ("native_origin", "native_submit")):
            self.assertFalse(check({**valid, field: value}), (field, value))

    def test_native_response_requires_binding_and_marks_other_state_unknown(self):
        valid = {
            "event": "native_alliance_response_result", "request_id": "r1",
            "session_id": "s1", "action_id": "offer_alliance", "actor": "FRA",
            "recipient": "ENG", "phase": "initiate", "date_raw": 42,
            "response_verified": True, "request_binding_verified": True,
            "native_state": 2, "alliance_after": True,
        }
        check = lambda event: ObserverSession._public_native_response_result(
            event, "r1", "s1", "FRA", "ENG", "initiate", 42)
        self.assertEqual("accepted", check(valid)["native_outcome"])
        self.assertEqual("unknown", check({**valid, "native_state": 2, "alliance_after": False})["native_outcome"])
        self.assertIsNone(check({**valid, "recipient": "FRA"}))
        self.assertIsNone(check({**valid, "request_binding_verified": False}))
        self.assertIsNone(check({**valid, "alliance_after": 1}))

    def test_native_response_accept_reject_persist_across_restart(self):
        def prepare(journal, request_id, recipient, sequence):
            journal.register(request_id, {
                "action_id": "offer_alliance", "actor": "FRA", "recipient": recipient,
                "phase": "initiate", "parameters": {},
            })
            for status in ("queued", "consumed", "constructed"):
                journal.transition(request_id, status, result={"submitted": False})
            claim = journal.claim_submission(request_id, submission_id="native_" + request_id)
            journal.mark_submitted(request_id, claim.claim_token, {
                "event": "native_alliance_submission_result", "request_id": request_id,
                "action_id": "offer_alliance", "actor": "FRA", "recipient": recipient,
                "phase": "initiate", "date_raw": 42, "submitted": True,
                "native_queue_verified": True, "transport_ring": True,
                "transport_ring_receipt": True, "native_sequence": sequence,
                "native_origin": 1, "native_flags": 0,
            })

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal_path = root / "journal.sqlite3"
            installation = root / "installation.json"
            installation.write_text(json.dumps({
                "experiment_id": "experiment", "session_id": "session",
                "pid": 1, "creation_filetime": 2, "native_text_codec": "eu4_escape",
            }), encoding="utf-8")
            log = root / "control-probe.jsonl"
            log.write_text(json.dumps({
                "event": "diplomacy_observer_installed", "session_id": "session",
                "caps": ["native_offer_submission"],
            }) + "\n", encoding="utf-8")

            def response(request_id, recipient, native_state, alliance_after):
                return {
                    "event": "native_alliance_response_result", "request_id": request_id,
                    "session_id": "session", "action_id": "offer_alliance", "actor": "FRA",
                    "recipient": recipient, "phase": "initiate", "date_raw": 42,
                    "response_verified": True, "request_binding_verified": True,
                    "native_state": native_state, "alliance_after": alliance_after,
                }

            with DurableJournal(journal_path, "experiment", "session") as journal:
                prepare(journal, "accept_1", "ENG", 7)
                with log.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(response("accept_1", "ENG", 2, True)) + "\n")
                api = DiplomacyTools(journal, ObserverSession(installation, root / "eu4.exe"))
                accepted = api.get_diplomatic_result("accept_1")
                prepare(journal, "reject_1", "SAV", 8)
                with log.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(response("reject_1", "SAV", 1, False)) + "\n")
                rejected = api.get_diplomatic_result("reject_1")
                self.assertEqual("accepted", accepted["status"])
                self.assertEqual("accepted", accepted["game_outcome"])
                self.assertEqual("rejected", rejected["status"])
                self.assertEqual("rejected", rejected["game_outcome"])
                self.assertNotIn("session_id", json.dumps(accepted))
                self.assertEqual(2, journal.get_request("accept_1").evidence_count)
                self.assertEqual(2, journal.get_request("reject_1").evidence_count)

            with DurableJournal(journal_path, "experiment", "session") as reopened:
                api = DiplomacyTools(reopened, ObserverSession(installation, root / "eu4.exe"))
                accepted_after = api.get_diplomatic_result("accept_1")
                rejected_after = api.get_diplomatic_result("reject_1")
                self.assertEqual("accepted", accepted_after["status"])
                self.assertEqual("rejected", rejected_after["status"])
                self.assertEqual(2, reopened.get_request("accept_1").evidence_count)
                self.assertEqual(2, reopened.get_request("reject_1").evidence_count)

    def test_native_response_cursors_are_independent_across_requests(self):
        def prepare(journal, request_id, recipient, sequence):
            journal.register(request_id, {
                "action_id": "offer_alliance", "actor": "FRA", "recipient": recipient,
                "phase": "initiate", "parameters": {},
            })
            for status in ("queued", "consumed", "constructed"):
                journal.transition(request_id, status, result={"submitted": False})
            claim = journal.claim_submission(request_id, submission_id="native_" + request_id)
            journal.mark_submitted(request_id, claim.claim_token, {
                "event": "native_alliance_submission_result", "request_id": request_id,
                "action_id": "offer_alliance", "actor": "FRA", "recipient": recipient,
                "phase": "initiate", "date_raw": 42, "submitted": True,
                "native_queue_verified": True, "transport_ring": True,
                "transport_ring_receipt": True, "native_sequence": sequence,
                "native_origin": 1, "native_flags": 0,
            })

        def response(request_id, recipient, native_state, alliance_after):
            return {
                "event": "native_alliance_response_result", "request_id": request_id,
                "session_id": "session", "action_id": "offer_alliance", "actor": "FRA",
                "recipient": recipient, "phase": "initiate", "date_raw": 42,
                "response_verified": True, "request_binding_verified": True,
                "native_state": native_state, "alliance_after": alliance_after,
            }

        def create_files(root):
            installation = root / "installation.json"
            installation.write_text(json.dumps({
                "experiment_id": "experiment", "session_id": "session",
                "pid": 1, "creation_filetime": 2, "native_text_codec": "eu4_escape",
            }), encoding="utf-8")
            log = root / "control-probe.jsonl"
            log.write_text(json.dumps({
                "event": "diplomacy_observer_installed", "session_id": "session",
                "caps": ["native_offer_submission"],
            }) + "\n", encoding="utf-8")
            return installation, log

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            simultaneous = root / "simultaneous"
            simultaneous.mkdir()
            installation, log = create_files(simultaneous)
            with DurableJournal(simultaneous / "a.sqlite3", "experiment_a", "session") as journal_a, \
                    DurableJournal(simultaneous / "b.sqlite3", "experiment_b", "session") as journal_b:
                prepare(journal_a, "sim_a", "ENG", 7)
                prepare(journal_b, "sim_b", "SAV", 8)
                with log.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(response("sim_a", "ENG", 2, True)) + "\n")
                    stream.write(json.dumps(response("sim_b", "SAV", 1, False)) + "\n")
                session = ObserverSession(installation, simultaneous / "eu4.exe")
                rejected = DiplomacyTools(journal_b, session).get_diplomatic_result("sim_b")
                accepted = DiplomacyTools(journal_a, session).get_diplomatic_result("sim_a")
                self.assertEqual("accepted", accepted["status"])
                self.assertEqual("rejected", rejected["status"])
                self.assertEqual(2, journal_a.get_request("sim_a").evidence_count)
                self.assertEqual(2, journal_b.get_request("sim_b").evidence_count)

            crossed = root / "crossed"
            crossed.mkdir()
            installation, log = create_files(crossed)
            with DurableJournal(crossed / "a.sqlite3", "experiment_a", "session") as journal_a, \
                    DurableJournal(crossed / "b.sqlite3", "experiment_b", "session") as journal_b:
                prepare(journal_a, "cross_a", "ENG", 9)
                prepare(journal_b, "cross_b", "SAV", 10)
                with log.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(response("cross_b", "SAV", 2, True)) + "\n")
                session = ObserverSession(installation, crossed / "eu4.exe")
                waiting = DiplomacyTools(journal_a, session).get_diplomatic_result("cross_a")
                self.assertEqual("submitted", waiting["status"])
                self.assertEqual("unknown", waiting["game_outcome"])
                self.assertEqual(1, journal_a.get_request("cross_a").evidence_count)

                accepted_b = DiplomacyTools(journal_b, session).get_diplomatic_result("cross_b")
                self.assertEqual("accepted", accepted_b["status"])
                with log.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(response("cross_a", "ENG", 2, True)) + "\n")
                accepted_a = DiplomacyTools(journal_a, session).get_diplomatic_result("cross_a")
                self.assertEqual("accepted", accepted_a["status"])
                self.assertEqual(2, journal_a.get_request("cross_a").evidence_count)
                self.assertEqual(2, journal_b.get_request("cross_b").evidence_count)

    def test_query_does_not_authorize_and_execution_rechecks_session(self):
        session = ReadySession()
        api = DiplomacyTools(self.journal, session)
        query = api.inspect_diplomatic_action("offer_alliance", "FRA", "ENG")
        self.assertEqual([], self.journal.list_requests())
        result = api.execute_diplomatic_action("alliance_2", "offer_alliance", "FRA", "ENG")
        self.assertNotEqual(query["session"]["state_id"], result["result"]["inspection"]["session"]["state_id"])
        serialized = json.dumps(result)
        self.assertNotIn("claim_token", serialized)
        self.assertNotIn("session_id", serialized)
        self.assertNotIn("pid", serialized)

    def test_external_result_survives_session_change_without_reexecution(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "requests.sqlite3"
            with DurableJournal(path, "experiment_1", "session_1", global_request_ids=True) as journal:
                result = DiplomacyTools(journal).execute_diplomatic_action("global_1", "offer_alliance", "FRA", "ENG")
                self.assertEqual("invalidated", result["status"])
            with DurableJournal(path, "experiment_2", "session_2", global_request_ids=True) as journal:
                api = DiplomacyTools(journal)
                self.assertEqual("invalidated", api.get_diplomatic_result("global_1")["status"])
                replay = api.execute_diplomatic_action("global_1", "offer_alliance", "FRA", "ENG")
                self.assertEqual("REQUEST_ID_SESSION_CONFLICT", replay["reason"]["code"])
                self.assertFalse(replay["submitted"])
                self.assertEqual([], journal.list_requests())

    def test_shared_resource_failure_is_not_erased_by_specific_validity(self):
        api = DiplomacyTools(self.journal, NativeSession(common_action_gate=False, display_predicate=False))
        result = api.inspect_diplomatic_action("offer_alliance", "FRA", "SAV")
        self.assertEqual("unavailable", result["legality"]["status"])
        self.assertEqual("NATIVE_COMMON_ACTION_GATE_FALSE", result["legality"]["reasons"][0]["code"])
        self.assertEqual(64, result["acceptance"]["native_total"])
        self.assertEqual("unknown", result["visibility"]["status"])

    def test_native_total_is_not_a_probability_or_complete_rule_proof(self):
        result = DiplomacyTools(self.journal, NativeSession()).inspect_diplomatic_action("offer_alliance", "FRA", "SAV")
        self.assertEqual("unknown", result["legality"]["status"])
        self.assertFalse(result["legality"]["complete"])
        self.assertEqual(64, result["acceptance"]["native_total"])
        self.assertEqual("unknown", result["acceptance"]["unit"])
        self.assertEqual("unknown", result["acceptance"]["predicted_response"])
        self.assertFalse(result["acceptance"]["details_available"])

    def test_current_native_predicate_is_a_prediction_not_an_actual_response(self):
        for would_accept, response in ((True, "accept"), (False, "reject")):
            native = NativeSession(acceptance_predicate_available=True,
                                   native_would_accept=would_accept)
            result = DiplomacyTools(self.journal, native).inspect_diplomatic_action(
                "offer_alliance", "FRA", "SAV")
            self.assertEqual(response, result["acceptance"]["predicted_response"])
            self.assertEqual("native_current_acceptance_check", result["acceptance"]["prediction_basis"])
            self.assertFalse(result["acceptance"]["actual_response_verified"])
            self.assertFalse(result["acceptance"]["complete"])
            self.assertEqual("unknown", result["acceptance"]["unit"])
            self.assertEqual(would_accept, result["native_rule_components"]["acceptance_gate"])

    def test_native_predicate_remains_hidden_for_player_llm_and_unilateral_actions(self):
        native = NativeSession(acceptance_predicate_available=True, native_would_accept=True)
        api = DiplomacyTools(self.journal, native)
        for action, actor, recipient in (("offer_alliance", "FRA", "POR"),
                                         ("offer_alliance", "SAV", "FRA"),
                                         ("dissolve_alliance", "FRA", "PRO")):
            result = api.inspect_diplomatic_action(action, actor, recipient)
            self.assertFalse(result["acceptance"]["prediction_available"])
            self.assertNotIn("prediction_basis", result["acceptance"])
            self.assertNotIn("native_would_accept", result["acceptance"])
            self.assertNotIn("acceptance_gate", result["native_rule_components"])

    def test_diplomat_availability_does_not_prove_allocation(self):
        for count in (0, 3):
            native = NativeSession(diplomat_context_readable=True, diplomat_required=True,
                                   available_diplomat_count=count)
            result = DiplomacyTools(self.journal, native).inspect_diplomatic_action(
                "offer_alliance", "FRA", "SAV")
            resource = result["resources"]["diplomats"]
            self.assertEqual(count, resource["available_count"])
            self.assertTrue(resource["availability_verified"])
            self.assertFalse(resource["allocation_verified"])
            self.assertFalse(resource["complete"])

    def test_native_ui_coverage_proves_only_the_initiation_rules(self):
        native = NativeSession(ui_selection_checked=True, native_visibility=True,
                               ui_enabled_gate_checked=True, tooltip_gate=True,
                               full_rules_complete=True)
        result = DiplomacyTools(self.journal, native).inspect_diplomatic_action("offer_alliance", "FRA", "SAV")
        self.assertEqual("visible", result["visibility"]["status"])
        self.assertTrue(result["visibility"]["complete"])
        self.assertEqual("available", result["legality"]["status"])
        self.assertTrue(result["legality"]["complete"])
        self.assertEqual("unknown", result["costs"]["status"])
        self.assertFalse(result["acceptance"]["complete"])
        self.assertEqual("unknown", result["acceptance"]["predicted_response"])
        self.assertEqual("unavailable", result["authorization"]["status"])

    def test_hidden_native_variant_cannot_become_available(self):
        native = NativeSession(ui_selection_checked=True, native_visibility=False,
                               ui_enabled_gate_checked=True, tooltip_gate=True,
                               full_rules_complete=True)
        result = DiplomacyTools(self.journal, native).inspect_diplomatic_action("offer_alliance", "FRA", "PRO")
        self.assertEqual("hidden", result["visibility"]["status"])
        self.assertEqual("unavailable", result["legality"]["status"])
        self.assertTrue(result["legality"]["complete"])
        self.assertTrue(any(r["code"] == "NATIVE_ACTION_NOT_VISIBLE" for r in result["legality"]["reasons"]))

    def test_inconsistent_native_ui_results_remain_unknown(self):
        native = NativeSession(ui_selection_checked=True, native_visibility=True,
                               ui_enabled_gate_checked=True, tooltip_gate=False,
                               full_rules_complete=True)
        result = DiplomacyTools(self.journal, native).inspect_diplomatic_action("offer_alliance", "FRA", "SAV")
        self.assertEqual("unknown", result["legality"]["status"])
        self.assertFalse(result["legality"]["complete"])
        self.assertEqual("NATIVE_UI_GATE_INCONSISTENT", result["legality"]["reasons"][0]["code"])

    def test_player_or_llm_receiver_cannot_inherit_a_native_ai_prediction(self):
        api = DiplomacyTools(self.journal, NativeSession())
        for actor, recipient in (("FRA", "POR"), ("SAV", "FRA")):
            result = api.inspect_diplomatic_action("offer_alliance", actor, recipient)
            self.assertFalse(result["acceptance"]["prediction_available"])
            self.assertIsNone(result["acceptance"]["native_total"])

    def test_native_initiation_gate_has_a_separate_rule_reason(self):
        result = DiplomacyTools(self.journal, NativeSession(initiation_gate=False)).inspect_diplomatic_action("offer_alliance", "FRA", "SAV")
        self.assertEqual("unavailable", result["legality"]["status"])
        self.assertTrue(any(r["code"] == "NATIVE_INITIATION_GATE_FALSE" for r in result["legality"]["reasons"]))

    def test_legacy_missing_gate_fields_remain_unknown(self):
        event = {"display_predicate": False, "validity_called": True, "native_validity": True}
        semantic = ObserverSession._semantic_inspection(event, {})
        self.assertFalse(semantic["common_action_gate"])
        self.assertIsNone(semantic["initiation_gate"])
        self.assertTrue(semantic["native_validity"])

        native = NativeSession()
        native.native.pop("common_action_gate")
        native.native.pop("display_predicate")
        native.native.pop("initiation_gate")
        result = DiplomacyTools(self.journal, native).inspect_diplomatic_action("offer_alliance", "FRA", "SAV")
        self.assertEqual("unknown", result["legality"]["status"])
        self.assertIsNone(result["native_rule_components"]["common_action_gate"])
        self.assertIsNone(result["native_rule_components"]["initiation_gate"])
        self.assertFalse(any(item["code"] == "NATIVE_COMMON_ACTION_GATE_FALSE"
                             for item in result["legality"]["reasons"]))

    def test_native_result_validation_rejects_identity_and_score_shape_errors(self):
        valid = {"event": "native_alliance_inspection", "action_id": "offer_alliance",
                 "actor": "FRA", "recipient": "SAV", "phase": "initiate", "date_raw": 1,
                 "score_available": True, "native_total_raw": 64, "acceptance_threshold_raw": 1}
        self.assertTrue(ObserverSession._valid_native_inspection(valid, "offer_alliance", "FRA", "SAV", "initiate", 1))
        invalid_score = {**valid, "native_total_raw": "64"}
        self.assertFalse(ObserverSession._valid_native_inspection(invalid_score, "offer_alliance", "FRA", "SAV", "initiate", 1))
        invalid_identity = {**valid, "recipient": "ENG"}
        self.assertFalse(ObserverSession._valid_native_inspection(invalid_identity, "offer_alliance", "FRA", "SAV", "initiate", 1))

    def test_native_result_rejects_malformed_predicate_and_diplomat_fields(self):
        valid = {"event": "native_alliance_inspection", "action_id": "offer_alliance",
                 "actor": "FRA", "recipient": "SAV", "phase": "initiate", "date_raw": 1,
                 "score_available": True, "native_total_raw": 64, "acceptance_threshold_raw": 1,
                 "acceptance_predicate_available": True, "native_would_accept": False,
                 "diplomat_context_readable": True, "diplomat_required": True,
                 "available_diplomat_count": 0}
        check = lambda event: ObserverSession._valid_native_inspection(
            event, "offer_alliance", "FRA", "SAV", "initiate", 1)
        self.assertTrue(check(valid))
        for field, value in (("native_would_accept", "false"),
                             ("acceptance_predicate_available", 1),
                             ("diplomat_context_readable", "true"),
                             ("available_diplomat_count", True),
                             ("available_diplomat_count", -1),
                             ("available_diplomat_count", 257),
                             ("diplomat_required", 1), ("score_available", False)):
            self.assertFalse(check({**valid, field: value}), (field, value))

    def test_observer_aggregates_reason_items_and_removes_private_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            session_id = "52544-test"
            installation = directory / "installation.json"
            installation.write_text(json.dumps({
                "experiment_id": "observer-test", "session_id": session_id,
                "pid": 52544, "creation_filetime": 1234, "dll_sha256": "dll",
                "controlled_countries": ["FRA"], "installation_returncode": 0,
            }), encoding="utf-8")
            log = directory / "control-probe.jsonl"
            log.write_text(json.dumps({
                "event": "diplomacy_observer_installed", "session_id": session_id,
                "native_queries_enabled": True,
            }) + "\n", encoding="utf-8")
            request = directory / "diplomacy-query.request"
            session = ObserverSession(installation, directory / "eu4.exe")
            items = []
            for index in range(32):
                if index == 0:
                    text_hex, readable, truncated, value = "48656c6c6f", True, False, 5
                elif index == 1:
                    text_hex, readable, truncated, value = "", False, True, -7
                else:
                    text_hex, readable, truncated, value = "726561736f6e", True, False, index
                items.append({
                    "event": "native_alliance_reason_item", "index": index,
                    "native_value": value, "text_hex": text_hex,
                    "text_readable": readable, "text_truncated": truncated,
                })
            inspection = {
                "event": "native_alliance_inspection", "action_id": "offer_alliance",
                "actor": "FRA", "recipient": "SAV", "phase": "initiate", "date_raw": 1,
                "common_action_gate": True, "display_predicate": True, "initiation_gate": True,
                "validity_called": True, "native_validity": True,
                "native_diagnostic_hex": "666f726d6174746564206c696e65", "diagnostic_readable": True,
                "diagnostic_truncated": False, "score_applicable": True, "score_available": True,
                "native_total_raw": 64, "acceptance_threshold_raw": 1,
                "reason_container_readable": True, "reason_count": 33,
            }

            def append_events():
                deadline = time.monotonic() + 2
                while not request.exists() and time.monotonic() < deadline:
                    time.sleep(0.001)
                if not request.exists():
                    return
                query_id = request.read_text(encoding="ascii").split()[2]
                with log.open("a", encoding="utf-8", newline="\n") as stream:
                    for event in items + [inspection]:
                        event = {**event, "session_id": session_id, "query_id": query_id}
                        stream.write(json.dumps(event) + "\n")

            writer = threading.Thread(target=append_events)
            writer.start()
            with patch.object(session, "health", return_value={"status": "ready", "date_raw": 1}), \
                 patch("bridge.diplomacy.probe_identity", return_value={"session_id": session_id}):
                result = session.inspect_alliance("offer_alliance", "FRA", "SAV", "initiate")
            writer.join(2)
            self.assertFalse(writer.is_alive())
            self.assertEqual(32, len(result["reason_items"]))
            self.assertTrue(result["reason_items_truncated"])
            self.assertEqual("Hello", result["reason_items"][0]["name"])
            self.assertIsNone(result["reason_items"][1]["name"])
            self.assertEqual(-7, result["reason_items"][1]["native_value"])
            self.assertEqual("formatted line", result["native_diagnostic_text"])
            serialized = json.dumps(result)
            for private_key in ("session_id", "query_id", "text_hex", "native_diagnostic_hex", "raw48"):
                self.assertNotIn(private_key, serialized)

    def test_observer_query_never_overwrites_busy_channel(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            installation = directory / "installation.json"
            installation.write_text(json.dumps({"experiment_id": "test", "session_id": "test",
                                                "creation_filetime": 1}), encoding="utf-8")
            (directory / "control-probe.jsonl").write_text("", encoding="utf-8")
            request = directory / "diplomacy-query.request"
            request.write_bytes(b"another owner's request\n")
            session = ObserverSession(installation, directory / "eu4.exe")
            with patch.object(session, "health", return_value={"status": "ready", "date_raw": 1}), \
                 patch.object(session, "installation_capabilities", return_value=frozenset({"native_queries_enabled"})):
                result = session.inspect_alliance("offer_alliance", "FRA", "SAV", "initiate")
            self.assertEqual("QUERY_CHANNEL_BUSY", result["error_code"])
            self.assertEqual(b"another owner's request\n", request.read_bytes())
            self.assertEqual([], list(directory.glob("*.pending")))

    def test_semantic_acceptance_items_are_readable_but_incomplete(self):
        native_items = [
            {"name": "格式化条件", "native_value": 5, "source": "raw", "complete": True,
             "native_identifier": "unverified", "identifier_verified": True, "truncated": True},
            {"name": None, "native_value": -2, "source": "raw", "complete": True},
        ]
        native = NativeSession(reason_items=native_items, reason_count=33, reason_items_truncated=True)
        result = DiplomacyTools(self.journal, native).inspect_diplomatic_action("offer_alliance", "FRA", "SAV")
        acceptance = result["acceptance"]
        self.assertTrue(acceptance["details_available"])
        self.assertFalse(acceptance["complete"])
        self.assertEqual(33, acceptance["reason_count"])
        self.assertTrue(acceptance["items_truncated"])
        self.assertEqual("格式化条件", acceptance["items"][0]["name"])
        self.assertEqual("native_rule", acceptance["items"][0]["source"])
        self.assertFalse(acceptance["items"][0]["complete"])
        self.assertFalse(acceptance["items"][0]["text_encoding_verified"])
        self.assertFalse(acceptance["items"][0]["text_complete"])
        self.assertIsNone(acceptance["items"][0]["native_identifier"])
        self.assertFalse(acceptance["items"][0]["identifier_verified"])
        self.assertIsNone(acceptance["items"][1]["name"])

    def test_controlled_and_por_recipients_hide_forecast_items_and_gate(self):
        native = NativeSession(reason_items=[{"name": "条件", "native_value": 5}], reason_count=1)
        api = DiplomacyTools(self.journal, native)
        for actor, recipient in (("SAV", "FRA"), ("FRA", "POR")):
            result = api.inspect_diplomatic_action("offer_alliance", actor, recipient)
            self.assertFalse(result["acceptance"]["prediction_available"])
            self.assertIsNone(result["acceptance"]["native_total"])
            self.assertEqual([], result["acceptance"]["items"])
            self.assertNotIn("acceptance_gate", result["native_rule_components"])

    def test_native_value_only_rows_do_not_claim_readable_names(self):
        native = NativeSession(reason_items=[{"name": "", "native_value": -25}], reason_count=1)
        result = DiplomacyTools(self.journal, native).inspect_diplomatic_action("offer_alliance", "FRA", "SAV")
        self.assertFalse(result["acceptance"]["details_available"])
        self.assertIsNone(result["acceptance"]["items"][0]["name"])
        self.assertEqual(-25, result["acceptance"]["items"][0]["native_value"])
        self.assertFalse(result["acceptance"]["complete"])

    def test_list_uses_exact_install_ack_capability_without_query(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            session_id = "session-cap"
            installation = directory / "installation.json"
            installation.write_text(json.dumps({
                "experiment_id": "observer-test", "session_id": session_id,
                "pid": 52544, "creation_filetime": 1234, "dll_sha256": "dll",
                "installation_returncode": 0,
            }), encoding="utf-8")
            log = directory / "control-probe.jsonl"
            log.write_text(json.dumps({
                "event": "diplomacy_observer_installed", "session_id": session_id,
                "caps": ["native_alliance_inspection"], "native_queries_enabled": False,
            }) + "\n", encoding="utf-8")
            session = ObserverSession(installation, directory / "eu4.exe")
            with patch.object(session, "health", return_value={"status": "ready", "date_raw": 1}):
                result = DiplomacyTools(self.journal, session).list_diplomatic_actions()
            by_id = {entry["action_id"]: entry for entry in result["actions"]}
            self.assertEqual("native_alliance_inspection", by_id["offer_alliance"]["phases"]["initiate"]["query"])
            self.assertEqual("NATIVE_ALLIANCE_QUERY_ACKNOWLEDGED",
                             by_id["offer_alliance"]["phases"]["initiate"]["reason_code"])
            self.assertEqual(frozenset({"native_alliance_inspection"}), session.installation_capabilities())

    def test_native_ack_top_level_offer_capability_is_found_in_bounded_header(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            session_id = "session-native-offer-ack"
            installation = directory / "installation.json"
            installation.write_text(json.dumps({
                "experiment_id": "observer-test", "session_id": session_id,
                "pid": 52544, "creation_filetime": 1234, "dll_sha256": "dll",
                "installation_returncode": 0,
            }), encoding="utf-8")
            log = directory / "control-probe.jsonl"
            startup_health = [{
                "event": "diplomacy_observer_health", "session_id": session_id,
                "thread_changed": False, "state_readable": True, "thread": 7,
                "player": "POR", "frames": 2 + index, "date_raw": 1,
            } for index in range(20)]
            ack = {
                "event": "diplomacy_observer_installed", "session_id": session_id,
                "native_offer_submission": True,
            }
            log.write_text("\n".join(json.dumps(event) for event in startup_health + [ack]) + "\n",
                           encoding="utf-8")
            session = ObserverSession(installation, directory / "eu4.exe")
            self.assertEqual(frozenset({"native_offer_submission"}),
                             session.installation_capabilities())

    def test_observer_health_requires_two_same_date_heartbeats(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            session_id = "session-health"
            installation = directory / "installation.json"
            installation.write_text(json.dumps({
                "experiment_id": "observer-test", "session_id": session_id,
                "pid": 52544, "dll_sha256": "dll", "installation_returncode": 0,
            }), encoding="utf-8")
            log = directory / "control-probe.jsonl"
            ack = {"event": "diplomacy_observer_installed", "session_id": session_id}
            old_date = {"event": "diplomacy_observer_health", "session_id": session_id,
                        "thread_changed": False, "state_readable": True, "thread": 7,
                        "player": "POR", "frames": 100, "date_raw": 1}
            first_new_date = {**old_date, "frames": 101, "date_raw": 2}
            log.write_text("\n".join(json.dumps(event) for event in (
                ack, old_date, first_new_date,
            )) + "\n", encoding="utf-8")
            session = ObserverSession(installation, directory / "eu4.exe")
            identity = {"session_id": session_id, "modules": [{"sha256": "dll"}]}
            with patch("bridge.diplomacy.probe_identity", return_value=identity):
                self.assertEqual("unready", session.health()["status"])
                second_new_date = {**first_new_date, "frames": 102}
                with log.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(second_new_date) + "\n")
                self.assertEqual("ready", session.health()["status"])

    def test_observer_health_rejects_thread_change_single_heartbeat_and_unready(self):
        scenarios = {
            "thread-change": (
                {"frames": 2, "thread": 7},
                {"frames": 3, "thread": 8},
            ),
            "single-heartbeat": (
                {"frames": 2, "thread": 7},
            ),
            "unreadable": (
                {"frames": 2, "thread": 7, "state_readable": False},
                {"frames": 3, "thread": 7, "state_readable": False},
            ),
        }
        for name, entries in scenarios.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                session_id = "session-health-reject"
                installation = directory / "installation.json"
                installation.write_text(json.dumps({
                    "experiment_id": "observer-test", "session_id": session_id,
                    "pid": 52544, "dll_sha256": "dll", "installation_returncode": 0,
                }), encoding="utf-8")
                log = directory / "control-probe.jsonl"
                events = []
                for entry in entries:
                    event = {"event": "diplomacy_observer_health", "session_id": session_id,
                             "thread_changed": False, "state_readable": True,
                             "player": "POR", "date_raw": 1, **entry}
                    events.append(event)
                log.write_text("\n".join(json.dumps(event) for event in events) + "\n",
                               encoding="utf-8")
                session = ObserverSession(installation, directory / "eu4.exe")
                identity = {"session_id": session_id, "modules": [{"sha256": "dll"}]}
                with patch("bridge.diplomacy.probe_identity", return_value=identity):
                    self.assertEqual("unready", session.health()["status"])

    def test_observer_health_falls_back_to_one_mib_tail_after_large_log_burst(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            session_id = "session-health-large-log"
            installation = directory / "installation.json"
            installation.write_text(json.dumps({
                "experiment_id": "observer-test", "session_id": session_id,
                "pid": 52544, "dll_sha256": "dll", "installation_returncode": 0,
            }), encoding="utf-8")
            log = directory / "control-probe.jsonl"
            health = {"event": "diplomacy_observer_health", "session_id": session_id,
                      "thread_changed": False, "state_readable": True, "thread": 7,
                      "player": "POR", "frames": 2, "date_raw": 1}
            burst = {"event": "native_alliance_response_result", "payload": "x" * 1024}
            log.write_text(json.dumps(health) + "\n" +
                           json.dumps({**health, "frames": 3}) + "\n" +
                           "".join(json.dumps(burst) + "\n" for _ in range(80)),
                           encoding="utf-8")
            self.assertGreater(log.stat().st_size, 64 * 1024)
            session = ObserverSession(installation, directory / "eu4.exe")
            identity = {"session_id": session_id, "modules": [{"sha256": "dll"}]}
            with patch("bridge.diplomacy.probe_identity", return_value=identity):
                result = session.health()
            self.assertEqual("ready", result["status"])
            self.assertEqual(1, result["date_raw"])

    def test_observer_health_rejects_missing_or_wrong_session_heartbeat_after_fallback(self):
        for heartbeat in (None, "other-session"):
            with self.subTest(heartbeat=heartbeat), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                session_id = "session-health-missing"
                installation = directory / "installation.json"
                installation.write_text(json.dumps({
                    "experiment_id": "observer-test", "session_id": session_id,
                    "pid": 52544, "dll_sha256": "dll", "installation_returncode": 0,
                }), encoding="utf-8")
                log = directory / "control-probe.jsonl"
                lines = []
                if heartbeat is not None:
                    lines.append(json.dumps({
                        "event": "diplomacy_observer_health", "session_id": heartbeat,
                        "thread_changed": False, "state_readable": True, "thread": 7,
                        "player": "POR", "frames": 2, "date_raw": 1,
                    }))
                burst = {"event": "native_alliance_response_result", "payload": "x" * 1024}
                lines.extend(json.dumps(burst) for _ in range(80))
                log.write_text("\n".join(lines) + "\n", encoding="utf-8")
                self.assertGreater(log.stat().st_size, 64 * 1024)
                session = ObserverSession(installation, directory / "eu4.exe")
                identity = {"session_id": session_id, "modules": [{"sha256": "dll"}]}
                with patch("bridge.diplomacy.probe_identity", return_value=identity):
                    self.assertEqual("unready", session.health()["status"])


class NativeReasonMetadataTests(unittest.TestCase):
    @staticmethod
    def event(**overrides):
        event = {
            "native_value": -25, "text_hex": "与敌人结盟".encode("utf-8").hex(),
            "text_readable": True, "text_truncated": False,
            "native_identifier": "DIPLO_ENEMY_ALLIES",
            "native_identifier_verified": True, "identifier_verified": True,
            "identity_source": "native_localization_key", "row_binding_verified": True,
            "constructor_value_verified": True, "value_representation": "signed_int32",
            "value_normalized": False, "caller_return_rva": "0x39f478", "row_address": "0x12345678",
        }
        event.update(overrides)
        return event

    def test_verified_reason_preserves_raw_integer_and_hides_native_coordinates(self):
        semantic = ObserverSession._semantic_reason_item(self.event(), metadata_acknowledged=True)
        public = DiplomacyTools._public_acceptance_items([semantic], metadata_acknowledged=True)[0]
        self.assertEqual("DIPLO_ENEMY_ALLIES", public["native_identifier"])
        self.assertEqual(-25, public["native_value"])
        self.assertTrue(public["identifier_verified"])
        self.assertTrue(public["native_value_verified"])
        self.assertEqual("unknown", public["unit"])
        self.assertFalse(public["unit_verified"])
        self.assertFalse(public["complete"])
        serialized = json.dumps(public)
        self.assertNotIn("0x39f478", serialized)
        self.assertNotIn("0x12345678", serialized)

    def test_missing_ack_or_row_proof_retains_value_without_verified_identity(self):
        without_ack = ObserverSession._semantic_reason_item(self.event())
        self.assertIsNone(without_ack["native_identifier"])
        self.assertEqual(-25, without_ack["native_value"])
        for field in ("row_binding_verified", "constructor_value_verified", "native_identifier_verified"):
            with self.subTest(field=field):
                item = ObserverSession._semantic_reason_item(
                    self.event(**{field: False}), metadata_acknowledged=True)
                self.assertIsNone(item["native_identifier"])
                self.assertFalse(item["identifier_verified"])

    def test_metadata_ack_requires_literal_top_level_true(self):
        session = object.__new__(ObserverSession)
        for value in (None, False, "true", 1):
            with self.subTest(value=value), patch.object(session, "_installation_ack", return_value={
                    "capabilities": ["native_alliance_reason_metadata"],
                    "native_alliance_reason_metadata": value}):
                self.assertNotIn("native_alliance_reason_metadata", session.installation_capabilities())
        with patch.object(session, "_installation_ack", return_value={"native_alliance_reason_metadata": True}):
            self.assertIn("native_alliance_reason_metadata", session.installation_capabilities())


if __name__ == "__main__":
    unittest.main()
