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
from bridge.peace_execution import normalize_peace_execution_parameters


WAR_ID = "war_0123456789abcdef_01234567"


def white_parameters() -> dict:
    return {"peace_context": {"war_id": WAR_ID, "direction": "demand", "terms": []}}


def money_parameters() -> dict:
    return {"peace_context": {"war_id": WAR_ID, "direction": "demand", "terms": [{
        "action_id": "demand_ducats", "amount": "10.0",
        "payer": "ENG", "claimant": "FRA"}]}}


def mixed_parameters() -> dict:
    return {"peace_context": {"war_id": WAR_ID, "direction": "demand", "terms": [
        {"action_id": "demand_ducats", "amount": "10.0",
         "payer": "ENG", "claimant": "FRA"},
        {"action_id": "cede_province", "province_ids": [177, 4111],
         "beneficiary": "FRA"},
    ]}}


class PeaceExecutionAdapterTests(unittest.TestCase):
    @staticmethod
    def _installation(root: Path, *, submission_ack: object = None,
                      advertised_caps: object = None) -> Path:
        session_id = "peace-execution-session"
        installation = root / "installation.json"
        installation.write_text(json.dumps({
            "experiment_id": "peace-execution-contract",
            "session_id": session_id,
            "pid": 1,
            "creation_filetime": 116444736000000000,
            "dll_sha256": "dll",
        }), encoding="utf-8")
        ack = {"event": "diplomacy_observer_installed", "session_id": session_id}
        if advertised_caps is not None:
            ack["caps"] = advertised_caps
        if submission_ack is not None:
            ack["native_peace_submission"] = submission_ack
        (root / "control-probe.jsonl").write_text(
            json.dumps(ack) + "\n", encoding="utf-8")
        return installation

    def test_submission_ack_is_literal_and_wire_is_parameter_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = self._installation(root, submission_ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            self.assertIn("native_peace_submission", session.installation_capabilities())

            errors: list[BaseException] = []

            def native_writer() -> None:
                try:
                    request = root / "diplomacy-peace-execute.req"
                    deadline = time.monotonic() + 2
                    while not request.exists() and time.monotonic() < deadline:
                        time.sleep(0.001)
                    self.assertTrue(request.exists())
                    fields = request.read_text(encoding="ascii").strip().split()
                    self.assertEqual("EU4PEACE_EXEC1", fields[0])
                    self.assertEqual("white_peace", fields[3])
                    self.assertEqual("FRA", fields[4])
                    self.assertEqual("ENG", fields[5])
                    self.assertEqual(WAR_ID, fields[8])
                    self.assertEqual("demand", fields[9])
                    self.assertEqual("-1", fields[10])
                    self.assertEqual("-", fields[11])
                    self.assertEqual("-", fields[12])
                    request.unlink(missing_ok=True)
                    with (root / "control-probe.jsonl").open(
                            "a", encoding="utf-8", newline="\n") as stream:
                        stream.write(json.dumps({
                            "event": "native_peace_submission_result",
                            "family": "peace",
                            "session_id": session.session_id,
                            "request_id": "peace_wire_001",
                            "action_id": "white_peace",
                            "actor": "FRA", "recipient": "ENG", "phase": "initiate",
                            "date_raw": 42, "war_id": WAR_ID, "direction": "demand",
                            "amount_raw": -1, "province_ids": [], "beneficiary": "-",
                            "submitted": True, "transport_verified": True,
                            "request_binding_verified": True,
                            "native_origin": 1, "native_flags": 0,
                            "native_sequence": 2,
                        }) + "\n")
                except BaseException as exc:
                    errors.append(exc)

            writer = threading.Thread(target=native_writer)
            writer.start()
            result = session.submit_peace(
                "peace_wire_001", "FRA", "ENG", "initiate", 42,
                "white_peace", white_parameters(), timeout=2)
            writer.join(2)
            self.assertFalse(writer.is_alive())
            self.assertEqual([], errors)
            self.assertEqual("submitted", result["status"])
            self.assertTrue(result["receipt"]["request_binding_verified"])

            copied = self._installation(root, submission_ack=1)
            self.assertNotIn("native_peace_submission",
                             ObserverSession(copied, root / "eu4.exe").installation_capabilities())

    def test_execution_result_requires_transition_and_keeps_terms_verification_separate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = self._installation(root)
            session = ObserverSession(installation, root / "eu4.exe")
            event = {
                "event": "native_peace_execution_result", "family": "peace",
                "session_id": session.session_id, "request_id": "peace_result_001",
                "action_id": "demand_ducats", "actor": "FRA", "recipient": "ENG",
                "phase": "initiate", "date_raw": 43, "war_id": WAR_ID,
                "direction": "demand", "amount_raw": 10000, "province_ids": [],
                "beneficiary": "-", "native_state": 0, "outcome": "executed",
                "war_before": True, "war_after": False,
                "response_verified": True, "request_binding_verified": True,
                "execution_verified": True, "terms_verified": False,
            }
            with (root / "control-probe.jsonl").open(
                    "a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(event) + "\n")
            result = session.read_native_peace_execution(
                "peace_result_001", "FRA", "ENG", "initiate", 43,
                "demand_ducats", money_parameters())
            self.assertEqual("executed", result["status"])
            self.assertFalse(result["result"]["terms_verified"])
            self.assertIsNone(result["result"].get("native_origin"))

            invalid = dict(event, war_before=False)
            self.assertIsNone(
                ObserverSession._public_native_peace_execution_result(
                    invalid, "peace_result_001", session.session_id,
                    "FRA", "ENG", "initiate", 43, "demand_ducats",
                    money_parameters()))
            contradictory_state = dict(event, native_state=1,
                                       outcome="accepted")
            self.assertIsNone(
                ObserverSession._public_native_peace_execution_result(
                    contradictory_state, "peace_result_001", session.session_id,
                    "FRA", "ENG", "initiate", 43, "demand_ducats",
                    money_parameters()))
            contradictory_rejection = dict(
                event, native_state=2, outcome="rejected", war_after=True,
                execution_verified=False)
            self.assertIsNone(
                ObserverSession._public_native_peace_execution_result(
                    contradictory_rejection, "peace_result_001", session.session_id,
                    "FRA", "ENG", "initiate", 43, "demand_ducats",
                    money_parameters()))

    def test_verified_money_effects_are_strictly_bound_and_sanitized(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = self._installation(root)
            session = ObserverSession(installation, root / "eu4.exe")
            event = {
                "event": "native_peace_execution_result", "family": "peace",
                "session_id": session.session_id, "request_id": "peace_effect_001",
                "action_id": "demand_ducats", "actor": "FRA", "recipient": "ENG",
                "phase": "initiate", "date_raw": 43, "war_id": WAR_ID,
                "direction": "demand", "amount_raw": 10000, "province_ids": [],
                "beneficiary": "-", "native_state": 0, "outcome": "executed",
                "war_before": True, "war_after": False,
                "response_verified": True, "request_binding_verified": True,
                "execution_verified": True, "terms_verified": True,
                "effects": {
                    "complete": True, "date_unchanged": True,
                    "currency_scale": 1000,
                    "money": {
                        "amount_raw": 10000, "payer": "ENG", "paid_raw": 10000,
                        "credits": [{"country": "FRA", "amount_raw": 10000}],
                        "verified": True,
                    },
                    "provinces": [],
                },
            }
            projected = ObserverSession._public_native_peace_execution_result(
                event, "peace_effect_001", session.session_id, "FRA", "ENG",
                "initiate", 43, "demand_ducats", money_parameters())
            self.assertIsNotNone(projected)
            self.assertEqual(10000, projected["effects"]["money"]["paid_raw"])
            self.assertEqual("FRA", projected["effects"]["money"]["credits"][0][
                "country"])
            self.assertNotIn("private", json.dumps(projected))

            invalid = json.loads(json.dumps(event))
            invalid["effects"]["money"]["paid_raw"] = 9999
            self.assertIsNone(ObserverSession._public_native_peace_execution_result(
                invalid, "peace_effect_001", session.session_id, "FRA", "ENG",
                "initiate", 43, "demand_ducats", money_parameters()))

            payer_credit = json.loads(json.dumps(event))
            payer_credit["effects"]["money"]["credits"] = [
                {"country": "ENG", "amount_raw": 10000}]
            self.assertIsNone(ObserverSession._public_native_peace_execution_result(
                payer_credit, "peace_effect_001", session.session_id, "FRA",
                "ENG", "initiate", 43, "demand_ducats", money_parameters()))

            incomplete_verified = json.loads(json.dumps(event))
            incomplete_verified["effects"]["complete"] = False
            incomplete_verified["effects"]["date_unchanged"] = False
            incomplete_verified["terms_verified"] = False
            self.assertIsNone(ObserverSession._public_native_peace_execution_result(
                incomplete_verified, "peace_effect_001", session.session_id, "FRA",
                "ENG", "initiate", 43, "demand_ducats", money_parameters()))

            rejected_verified = json.loads(json.dumps(event))
            rejected_verified.update({
                "native_state": 1, "outcome": "rejected",
                "war_after": True, "execution_verified": False,
                "terms_verified": False,
            })
            self.assertIsNone(ObserverSession._public_native_peace_execution_result(
                rejected_verified, "peace_effect_001", session.session_id, "FRA",
                "ENG", "initiate", 43, "demand_ducats", money_parameters()))

    def test_offer_effect_uses_french_payer(self):
        parameters = {"peace_context": {"war_id": WAR_ID,
            "direction": "offer", "terms": [{
                "action_id": "demand_ducats", "amount": "10.0",
                "payer": "FRA", "claimant": "ENG"}]}}
        event = {
            "event": "native_peace_execution_result", "family": "peace",
            "session_id": "peace-execution-session", "request_id": "peace_effect_offer",
            "action_id": "demand_ducats", "actor": "FRA", "recipient": "ENG",
            "phase": "initiate", "date_raw": 43, "war_id": WAR_ID,
            "direction": "offer", "amount_raw": 10000, "province_ids": [],
            "beneficiary": "-", "native_state": 0, "outcome": "executed",
            "war_before": True, "war_after": False,
            "response_verified": True, "request_binding_verified": True,
            "execution_verified": True, "terms_verified": True,
            "effects": {
                "complete": True, "date_unchanged": True,
                "currency_scale": 1000,
                "money": {"amount_raw": 10000, "payer": "FRA",
                           "paid_raw": 10000,
                           "credits": [{"country": "ENG", "amount_raw": 10000}],
                           "verified": True},
                "provinces": [],
            },
        }
        self.assertIsNotNone(ObserverSession._public_native_peace_execution_result(
            event, "peace_effect_offer", "peace-execution-session", "FRA", "ENG",
            "initiate", 43, "demand_ducats", parameters))

    def test_verified_province_effect_allows_third_country_controller(self):
        parameters = {"peace_context": {"war_id": WAR_ID,
            "direction": "demand", "terms": [{
                "action_id": "cede_province", "province_ids": [177],
                "beneficiary": "FRA"}]}}
        event = {
            "event": "native_peace_execution_result", "family": "peace",
            "session_id": "peace-execution-session", "request_id": "peace_effect_province",
            "action_id": "cede_province", "actor": "FRA", "recipient": "ENG",
            "phase": "initiate", "date_raw": 43, "war_id": WAR_ID,
            "direction": "demand", "amount_raw": -1, "province_ids": [177],
            "beneficiary": "FRA", "native_state": 0, "outcome": "executed",
            "war_before": True, "war_after": False,
            "response_verified": True, "request_binding_verified": True,
            "execution_verified": True, "terms_verified": True,
            "effects": {
                "complete": True, "date_unchanged": True,
                "currency_scale": 1000, "money": None,
                "provinces": [{
                    "province_id": 177, "beneficiary": "FRA",
                    "owner_before": "ENG", "owner_after": "FRA",
                    "controller_before": "ENG", "controller_after": "ORL",
                    "verified": True,
                }],
            },
        }
        projected = ObserverSession._public_native_peace_execution_result(
            event, "peace_effect_province", "peace-execution-session", "FRA",
            "ENG", "initiate", 43, "cede_province", parameters)
        self.assertIsNotNone(projected)
        self.assertEqual("ORL", projected["effects"]["provinces"][0][
            "controller_after"])

        invalid = json.loads(json.dumps(event))
        invalid["effects"]["provinces"][0]["owner_before"] = "FRA"
        self.assertIsNone(ObserverSession._public_native_peace_execution_result(
            invalid, "peace_effect_province", "peace-execution-session", "FRA",
            "ENG", "initiate", 43, "cede_province", parameters))

    def test_native_submission_failure_preserves_reason_field(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = self._installation(root, submission_ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            errors: list[BaseException] = []

            def native_writer() -> None:
                try:
                    request = root / "diplomacy-peace-execute.req"
                    deadline = time.monotonic() + 2
                    while not request.exists() and time.monotonic() < deadline:
                        time.sleep(0.001)
                    self.assertTrue(request.exists())
                    request.unlink(missing_ok=True)
                    with (root / "control-probe.jsonl").open(
                            "a", encoding="utf-8", newline="\n") as stream:
                        stream.write(json.dumps({
                            "event": "native_peace_submission_result",
                            "family": "peace",
                            "session_id": session.session_id,
                            "request_id": "peace_wire_failed_001",
                            "action_id": "white_peace",
                            "actor": "FRA", "recipient": "ENG", "phase": "initiate",
                            "date_raw": 42, "war_id": WAR_ID, "direction": "demand",
                            "amount_raw": -1, "province_ids": [], "beneficiary": "-",
                            "submitted": False, "transport_verified": False,
                            "request_binding_verified": False,
                            "reason": "NATIVE_PEACE_COMMON_GATE_UNAVAILABLE",
                        }) + "\n")
                except BaseException as exc:
                    errors.append(exc)

            writer = threading.Thread(target=native_writer)
            writer.start()
            result = session.submit_peace(
                "peace_wire_failed_001", "FRA", "ENG", "initiate", 42,
                "white_peace", white_parameters(), timeout=2)
            writer.join(2)
            self.assertFalse(writer.is_alive())
            self.assertEqual([], errors)
            self.assertEqual("failed", result["status"])
            self.assertEqual(
                "NATIVE_PEACE_COMMON_GATE_UNAVAILABLE", result["reason_code"])

    def test_wrapper_rule_proof_controls_public_legality(self):
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" /
             "peace_empty_offer_inspection.json").read_text(encoding="utf-8"))
        base = fixture["event"]
        params = white_parameters()
        cases = (
            ("legacy", {}, False, "unknown"),
            ("wrapper_false", {
                "native_wrapper_gate_checked": True,
                "native_wrapper_gate": False,
                "wrapper_identity_verified": True,
                "wrapper_payload_unchanged": True,
                # The proof was completely observed even though the native
                # wrapper predicate itself returned false.
                "full_rules_complete": True,
            }, True, "unavailable"),
            ("wrapper_true", {
                "native_wrapper_gate_checked": True,
                "native_wrapper_gate": True,
                "wrapper_identity_verified": True,
                "wrapper_payload_unchanged": True,
                "full_rules_complete": True,
            }, True, "available"),
        )
        for name, updates, require_wrapper, expected_legality in cases:
            with self.subTest(name=name):
                event = dict(base)
                event.update(updates)
                self.assertTrue(ObserverSession._valid_native_peace_empty_offer_inspection(
                    event, "white_peace", "FRA", "ENG", "initiate",
                    event["date_raw"], WAR_ID, event["query_id"],
                    event["session_id"], require_wrapper_rule=require_wrapper))
                native = ObserverSession._semantic_peace_empty_offer_inspection(event)
                projected = DiplomacyTools._apply_peace_execution_inspection(
                    {"interface_support": {},
                     "session": {"date_raw": event["date_raw"]},
                     "acceptance": {}, "costs": {}},
                    native, params)
                self.assertEqual(expected_legality,
                                 projected["legality"]["status"])
                if name == "wrapper_false":
                    self.assertEqual(
                        "NATIVE_PEACE_WRAPPER_GATE_FALSE",
                        projected["legality"]["reasons"][0]["code"])
                if name == "wrapper_true":
                    self.assertTrue(projected["native_rule_components"][
                        "native_wrapper_gate"])

    def test_r43c_real_wrapper_events_replay_through_query_projection(self):
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" /
             "peace_wrapper_r43c_real_inspections.json").read_text(
                 encoding="utf-8"))
        events = {item["event"]["action_id"]: item["event"]
                  for item in fixture["events"]}
        self.assertEqual({"white_peace", "demand_ducats", "cede_province"},
                         set(events))
        capabilities = frozenset({
            "native_peace_empty_offer_query",
            "native_peace_money_offer_query",
            "native_peace_province_offer_query",
            "native_peace_wrapper_rule_query",
        })

        class FixtureSession:
            session_id = fixture["source"]["session_id"]

            def health(self):
                return {"status": "ready", "state_id": "r43c",
                        "date_raw": 56545080, "reasons": [],
                        "complete": True}

            def installation_capabilities(self):
                return capabilities

            @staticmethod
            def _copy(action_id):
                return json.loads(json.dumps(events[action_id]))

            def inspect_peace_empty_offer(self, *args):
                return self._copy("white_peace")

            def inspect_peace_money_offer(self, *args):
                return self._copy("demand_ducats")

            def inspect_peace_province_offer(self, *args):
                return self._copy("cede_province")

        for action_id, event in events.items():
            with self.subTest(action_id=action_id):
                war_id = event["war_id"]
                if action_id == "white_peace":
                    parameters = {"peace_context": {
                        "war_id": war_id, "terms": []}}
                    self.assertTrue(
                        ObserverSession._valid_native_peace_empty_offer_inspection(
                            event, action_id, event["actor"], event["recipient"],
                            event["phase"], event["date_raw"], war_id,
                            event["query_id"], event["session_id"],
                            require_wrapper_rule=True))
                elif action_id == "demand_ducats":
                    money = event["native_money"]
                    parameters = {"peace_context": {
                        "war_id": war_id, "direction": "demand", "terms": [{
                            "action_id": action_id,
                            "amount": f"{money['requested_amount_raw'] // 1000}."
                                       f"{(money['requested_amount_raw'] % 1000) // 100}",
                            "payer": event["recipient"],
                            "claimant": event["actor"],
                        }]}}
                    expected = {
                        "war_id": war_id, "direction": "demand",
                        "amount_raw": money["requested_amount_raw"],
                        "payer": event["recipient"],
                        "claimant": event["actor"],
                    }
                    self.assertTrue(
                        ObserverSession._valid_native_peace_money_offer_inspection(
                            event, action_id, event["actor"], event["recipient"],
                            event["phase"], event["date_raw"], expected,
                            event["query_id"], event["session_id"],
                            require_wrapper_rule=True))
                else:
                    provinces = event["native_provinces"]
                    parameters = {"peace_context": {
                        "war_id": war_id, "direction": "demand", "terms": [{
                            "action_id": action_id,
                            "province_ids": provinces["requested_province_ids"],
                            "beneficiary": provinces["requested_beneficiary"],
                        }]}}
                    expected = {
                        "war_id": war_id, "direction": "demand",
                        "province_ids": provinces["requested_province_ids"],
                        "beneficiary": provinces["requested_beneficiary"],
                    }
                    self.assertTrue(
                        ObserverSession._valid_native_peace_province_offer_inspection(
                            event, action_id, event["actor"], event["recipient"],
                            event["phase"], event["date_raw"], expected,
                            event["query_id"], event["session_id"],
                            require_wrapper_rule=True))

                journal = DurableJournal(":memory:", "r43c-wrapper", 
                                         event["session_id"])
                try:
                    result = DiplomacyTools(
                        journal, FixtureSession()).inspect_diplomatic_action(
                            action_id, event["actor"], event["recipient"],
                            event["phase"], parameters)
                finally:
                    journal.close()
                self.assertEqual("unavailable", result["legality"]["status"])
                self.assertIn(
                    "NATIVE_PEACE_WRAPPER_GATE_FALSE",
                    {item["code"] for item in result["legality"]["reasons"]})
                self.assertTrue(result["full_rules_complete"])
                self.assertFalse(result["reasons_complete"])
                self.assertTrue(result["native_wrapper_gate_checked"])
                self.assertFalse(result["native_wrapper_gate"])
                self.assertTrue(result["wrapper_identity_verified"])
                self.assertTrue(result["wrapper_payload_unchanged"])
                public_text = json.dumps(result, ensure_ascii=False)
                self.assertNotIn("frame_thread", public_text)
                self.assertNotIn('"private"', public_text)

    def test_r45a_real_full_public_inspection_uses_execution_overlay(self):
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" /
             "peace_r45a_real_selected_inspection.json").read_text(
                 encoding="utf-8"))
        event = fixture["event"]
        params = {"peace_context": {
            "war_id": event["war_id"], "direction": "demand", "terms": []}}
        self.assertTrue(ObserverSession._valid_native_peace_empty_offer_inspection(
            event, "white_peace", "FRA", "ENG", "initiate", event["date_raw"],
            event["war_id"], event["query_id"], event["session_id"],
            require_wrapper_rule=True))

        capabilities = frozenset({
            "native_peace_empty_offer_query",
            "native_peace_wrapper_rule_query",
            "native_peace_submission",
        })

        class FixtureSession:
            session_id = event["session_id"]

            @staticmethod
            def health():
                return {"status": "ready", "state_id": "r45a",
                        "date_raw": event["date_raw"], "reasons": [],
                        "complete": True}

            @staticmethod
            def installation_capabilities():
                return capabilities

            @staticmethod
            def inspect_peace_execution(*args):
                return json.loads(json.dumps(event))

        journal = DurableJournal(":memory:", "r45a-public-inspection",
                                 event["session_id"])
        try:
            result = DiplomacyTools(journal, FixtureSession()).inspect_diplomatic_action(
                "white_peace", "FRA", "ENG", "initiate", params)
        finally:
            journal.close()

        self.assertEqual("native_peace_execution_inspection",
                         result["interface_support"]["query"])
        self.assertEqual("native_peace_submission",
                         result["interface_support"]["execute"])
        self.assertTrue(result["interface_support"]["complete"])
        self.assertEqual("available", result["authorization"]["status"])
        self.assertEqual("available", result["legality"]["status"])
        self.assertTrue(result["parameters"]["complete"])
        self.assertTrue(result["execution_context"]["complete"])
        self.assertTrue(result["peace_context"]["complete"])
        self.assertFalse(result["execution_context"]["war_context_complete"])
        self.assertFalse(result["native_war_context"]["context_complete"])
        self.assertEqual(params, result["parameters"]["requested"])
        public_text = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("frame_thread", public_text)

    def test_combined_inspection_binds_money_provinces_and_payload_once(self):
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" /
             "peace_wrapper_r43c_real_inspections.json").read_text(
                 encoding="utf-8"))
        events = {item["event"]["action_id"]: item["event"]
                  for item in fixture["events"]}
        # Keep this contract fixture bounded and based on the established
        # public event shapes.  The R47 runtime fixture will replace the
        # synthetic merge once the aggregate native event is available.
        event = json.loads(json.dumps(events["demand_ducats"]))
        event.update({
            "event": "native_peace_combined_offer_inspection",
            "action_id": "demand_ducats",
            "direction": "demand",
            "native_provinces": events["cede_province"]["native_provinces"],
        })
        event["native_payload"] = json.loads(json.dumps(
            events["cede_province"]["native_payload"]))
        # Native selected_term_count includes the default selected Gold term;
        # it is not the public term count (money + province).
        event["native_payload"]["selected_term_count"] = 5
        selection = {
            "action_id": "demand_ducats", "war_id": event["war_id"],
            "direction": "demand", "amount_raw": 10000,
            "payer": "ENG", "claimant": "FRA",
            "province_ids": [177], "beneficiary": "FRA",
        }
        self.assertTrue(ObserverSession._valid_native_peace_combined_offer_inspection(
            event, "demand_ducats", "FRA", "ENG", "initiate",
            event["date_raw"], selection, event["query_id"],
            event["session_id"], require_wrapper_rule=True))
        projected = ObserverSession._semantic_peace_combined_offer_inspection(event)
        self.assertEqual("native_peace_combined_offer_inspection", projected["event"])
        self.assertTrue(projected["parameters_matched"])
        self.assertEqual(
            ["demand_ducats", "cede_province"],
            [term["action_id"] for term in projected["peace_context"]["terms"]])
        self.assertEqual(10000, projected["native_money"]["requested_amount_raw"])
        self.assertEqual([177], projected["native_provinces"]["selected_province_ids"])
        public_text = json.dumps(projected, ensure_ascii=False)
        self.assertNotIn("frame_thread", public_text)
        self.assertNotIn('"private"', public_text)

    def test_combined_execution_uses_dedicated_ack_and_single_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = self._installation(root, submission_ack=True)
            ack_path = root / "control-probe.jsonl"
            ack = json.loads(ack_path.read_text(encoding="utf-8"))
            ack["native_peace_combined_query"] = True
            ack_path.write_text(json.dumps(ack) + "\n", encoding="utf-8")
            session = ObserverSession(installation, root / "eu4.exe")
            ready = {"status": "ready", "state_id": "r47",
                     "date_raw": 42, "reasons": [], "complete": True}
            with patch.object(session, "health", return_value=ready), \
                    patch.object(session, "inspect_alliance",
                                 return_value={"event": "native_peace_combined_offer_inspection"}) as inspect:
                result = session.inspect_peace_execution(
                    "demand_ducats", "FRA", "ENG", "initiate", mixed_parameters())
            self.assertEqual("native_peace_combined_offer_inspection", result["event"])
            self.assertEqual(1, inspect.call_count)
            kwargs = inspect.call_args.kwargs
            self.assertEqual("native_peace_combined_offer_inspection",
                             kwargs["inspection_event"])
            selected = kwargs["peace_combined_offer"]
            self.assertEqual(10000, selected["amount_raw"])
            self.assertEqual([177, 4111], selected["province_ids"])
            self.assertEqual("demand_ducats", selected["action_id"])

    def test_r47a_real_combined_inspection_replay_preserves_selected_five_and_score(self):
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" /
             "peace_r47a_combined_real_inspections.json").read_text(
                 encoding="utf-8"))
        events = {item["role"]: item["event"] for item in fixture["events"]}
        event = events["combined_query"]
        selection = {
            "action_id": "cede_province",
            "war_id": event["war_id"],
            "direction": "offer",
            "amount_raw": 1000,
            "payer": "FRA",
            "claimant": "ENG",
            "province_ids": [4388, 4111, 4112, 4389],
            "beneficiary": "ENG",
        }
        self.assertTrue(ObserverSession._valid_native_peace_combined_offer_inspection(
            event, "cede_province", "FRA", "ENG", "initiate",
            event["date_raw"], selection, event["query_id"],
            event["session_id"], require_wrapper_rule=True))
        projected = ObserverSession._semantic_peace_combined_offer_inspection(event)
        self.assertTrue(projected["parameters_matched"])
        self.assertEqual(5, projected["native_payload"]["selected_term_count"])
        self.assertEqual(12, projected["native_evaluation"]["score_raw"])
        self.assertEqual("FRA", projected["native_money"]["payer"])
        self.assertEqual(1000, projected["native_money"]["requested_amount_raw"])
        self.assertEqual([4111, 4112, 4388, 4389],
                         projected["native_provinces"]["selected_province_ids"])
        self.assertEqual(
            ["demand_ducats", "cede_province"],
            [term["action_id"] for term in projected["peace_context"]["terms"]])
        public_text = json.dumps(projected, ensure_ascii=False)
        self.assertNotIn("frame_thread", public_text)
        self.assertNotIn('"private"', public_text)

    def test_r47a_real_combined_submission_and_accepted_effects_replay(self):
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" /
             "peace_r47a_combined_real_inspections.json").read_text(
                 encoding="utf-8"))
        events = {item["role"]: item["event"] for item in fixture["events"]}
        query = events["combined_query"]
        receipt = events["submission_receipt"]
        execution = events["accepted_execution"]
        parameters = {
            "peace_context": {
                "war_id": query["war_id"], "direction": "offer",
                "terms": [
                    {"action_id": "demand_ducats", "amount": "1.0",
                     "payer": "FRA", "claimant": "ENG"},
                    {"action_id": "cede_province",
                     "province_ids": [4388, 4111, 4112, 4389],
                     "beneficiary": "ENG"},
                ],
            }
        }
        self.assertTrue(ObserverSession._valid_native_peace_submission_result(
            receipt, receipt["request_id"], receipt["session_id"],
            "FRA", "ENG", "initiate", receipt["date_raw"],
            "cede_province", parameters))
        public_receipt = ObserverSession._public_native_peace_submission_receipt(
            receipt, receipt["request_id"], "FRA", "ENG", "initiate",
            receipt["date_raw"], "cede_province", parameters)
        self.assertEqual(1000, public_receipt["amount_raw"])
        self.assertEqual([4388, 4111, 4112, 4389],
                         public_receipt["province_ids"])
        self.assertNotIn("native_origin", public_receipt)
        projected = ObserverSession._public_native_peace_execution_result(
            execution, execution["request_id"], execution["session_id"],
            "FRA", "ENG", "initiate", execution["date_raw"],
            "cede_province", parameters)
        self.assertIsNotNone(projected)
        self.assertTrue(projected["execution_verified"])
        self.assertTrue(projected["terms_verified"])
        effects = projected["effects"]
        self.assertEqual(1000, effects["money"]["paid_raw"])
        self.assertEqual("FRA", effects["money"]["payer"])
        self.assertEqual(
            {"ENG": 661, "SWE": 23, "UTR": 316},
            {item["country"]: item["amount_raw"]
             for item in effects["money"]["credits"]})
        self.assertEqual(
            {4388, 4111, 4112, 4389},
            {item["province_id"] for item in effects["provinces"]})
        self.assertTrue(all(
            item["verified"]
            and item["beneficiary"] == "ENG"
            and item["owner_before"] == "FRA"
            and item["owner_after"] == "ENG"
            and item["controller_before"] == "FRA"
            and item["controller_after"] == "ENG"
            for item in effects["provinces"]))
        public_text = json.dumps(projected, ensure_ascii=False)
        self.assertNotIn("native_origin", public_text)
        self.assertNotIn("frame_thread", public_text)

    def test_public_mixed_inspection_uses_combined_route_with_single_caps_present(self):
        """A mixed public request must not fall into a legacy single-term parser."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = self._installation(root, submission_ack=True)
            ack_path = root / "control-probe.jsonl"
            ack = json.loads(ack_path.read_text(encoding="utf-8"))
            ack.update({
                "native_peace_combined_query": True,
                "native_peace_money_offer_query": True,
                "native_peace_province_offer_query": True,
            })
            ack_path.write_text(json.dumps(ack) + "\n", encoding="utf-8")
            session = ObserverSession(installation, root / "eu4.exe")
            ready = {"status": "ready", "state_id": "r47",
                     "date_raw": 42, "reasons": [], "complete": True}
            with patch.object(session, "health", return_value=ready), \
                    patch.object(
                        session, "inspect_peace_execution",
                        return_value={"error_code":
                                      "NATIVE_PEACE_COMMON_GATE_UNAVAILABLE"}) as inspect:
                journal = DurableJournal(":memory:", "peace-combined-public",
                                         session.session_id)
                try:
                    result = DiplomacyTools(journal, session).inspect_diplomatic_action(
                        "demand_ducats", "FRA", "ENG", "initiate",
                        mixed_parameters())
                finally:
                    journal.close()
            self.assertEqual(1, inspect.call_count)
            self.assertEqual("demand_ducats", inspect.call_args.args[0])
            self.assertEqual(mixed_parameters(), inspect.call_args.args[4])
            self.assertEqual("native_peace_execution_inspection",
                             result["interface_support"]["query"])
            self.assertIn(
                "NATIVE_PEACE_COMMON_GATE_UNAVAILABLE",
                {item["code"] for item in result["legality"]["reasons"]})

    def test_missing_submission_capability_never_publishes_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = self._installation(root, submission_ack=None)
            session = ObserverSession(installation, root / "eu4.exe")
            journal = DurableJournal(":memory:", "peace-execution-contract",
                                     session.session_id)
            tools = DiplomacyTools(journal, session)
            ready = {"status": "ready", "state_id": "ready", "date_raw": 44,
                     "reasons": [], "complete": True}
            with patch.object(session, "health", return_value=ready):
                result = tools.execute_diplomatic_action(
                    "peace_no_ack_001", "white_peace", "FRA", "ENG",
                    parameters=white_parameters())
            self.assertEqual("invalidated", result["status"])
            self.assertEqual("EXECUTION_ADAPTER_UNIMPLEMENTED",
                             result.get("result", {}).get("reason", {}).get("code"))
            self.assertFalse((root / "diplomacy-peace-execute.req").exists())
            journal.close()

    def test_submission_ack_exposes_execute_capability_in_action_list(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = self._installation(root, submission_ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            journal = DurableJournal(":memory:", "peace-execution-contract",
                                     session.session_id)
            tools = DiplomacyTools(journal, session)
            ready = {"status": "ready", "state_id": "ready", "date_raw": 44,
                     "reasons": [], "complete": True}
            with patch.object(session, "health", return_value=ready):
                listed = tools.list_diplomatic_actions(
                    actor="FRA", recipient="ENG", category="peace_term")
            action = next(item for item in listed["actions"]
                          if item["action_id"] == "white_peace")
            self.assertEqual(
                "native_peace_submission",
                action["phases"]["initiate"]["execute"])
            self.assertEqual(
                "NATIVE_PEACE_SUBMISSION_CAPABILITY_ACKNOWLEDGED",
                action["phases"]["initiate"]["execute_reason_code"])
            journal.close()

    def test_offer_submission_wire_preserves_direction_and_money_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = self._installation(root, submission_ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            parameters = {"peace_context": {"war_id": WAR_ID,
                "direction": "offer", "terms": [{
                    "action_id": "demand_ducats", "amount": "10.0",
                    "payer": "FRA", "claimant": "ENG"}]}}
            errors: list[BaseException] = []

            def native_writer() -> None:
                try:
                    request = root / "diplomacy-peace-execute.req"
                    deadline = time.monotonic() + 2
                    while not request.exists() and time.monotonic() < deadline:
                        time.sleep(0.001)
                    self.assertTrue(request.exists())
                    fields = request.read_text(encoding="ascii").strip().split()
                    self.assertEqual("EU4PEACE_EXEC1", fields[0])
                    self.assertEqual("demand_ducats", fields[3])
                    self.assertEqual("FRA", fields[4])
                    self.assertEqual("ENG", fields[5])
                    self.assertEqual(WAR_ID, fields[8])
                    self.assertEqual("offer", fields[9])
                    self.assertEqual("10000", fields[10])
                    self.assertEqual("-", fields[11])
                    self.assertEqual("-", fields[12])
                    request.unlink(missing_ok=True)
                    with (root / "control-probe.jsonl").open(
                            "a", encoding="utf-8", newline="\n") as stream:
                        stream.write(json.dumps({
                            "event": "native_peace_submission_result",
                            "family": "peace",
                            "session_id": session.session_id,
                            "request_id": "peace_offer_wire_001",
                            "action_id": "demand_ducats",
                            "actor": "FRA", "recipient": "ENG", "phase": "initiate",
                            "date_raw": 42, "war_id": WAR_ID, "direction": "offer",
                            "amount_raw": 10000, "province_ids": [], "beneficiary": "-",
                            "submitted": True, "transport_verified": True,
                            "request_binding_verified": True,
                        }) + "\n")
                except BaseException as exc:
                    errors.append(exc)

            writer = threading.Thread(target=native_writer)
            writer.start()
            result = session.submit_peace(
                "peace_offer_wire_001", "FRA", "ENG", "initiate", 42,
                "demand_ducats", parameters, timeout=2)
            writer.join(2)
            self.assertFalse(writer.is_alive())
            self.assertEqual([], errors)
            self.assertEqual("submitted", result["status"])
            self.assertEqual("offer", result["receipt"]["direction"])

    def test_copied_submission_capability_cannot_authorize_action_list(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = self._installation(
                root, advertised_caps=["native_peace_submission"])
            session = ObserverSession(installation, root / "eu4.exe")
            journal = DurableJournal(":memory:", "peace-execution-contract",
                                     session.session_id)
            tools = DiplomacyTools(journal, session)
            ready = {"status": "ready", "state_id": "ready", "date_raw": 44,
                     "reasons": [], "complete": True}
            with patch.object(session, "health", return_value=ready):
                listed = tools.list_diplomatic_actions(
                    actor="FRA", recipient="ENG", category="peace_term")
            action = next(item for item in listed["actions"]
                          if item["action_id"] == "white_peace")
            self.assertEqual(
                "unimplemented",
                action["phases"]["initiate"]["execute"])
            journal.close()


if __name__ == "__main__":
    unittest.main()
