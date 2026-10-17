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


FIXTURE = (Path(__file__).parent / "fixtures" /
           "declare_war_r36_native_inspection.json")
REAL_FIXTURE = (Path(__file__).parent / "fixtures" /
                "declare_war_r36a_real_native_inspections.json")
REAL_C_FIXTURE = (Path(__file__).parent / "fixtures" /
                  "declare_war_r36c_real_candidate_inspections.json")
REAL_E_FIXTURE = (Path(__file__).parent / "fixtures" /
                  "declare_war_r36e_real_query3_inspections.json")
CANDIDATE_FIXTURE = (Path(__file__).parent / "fixtures" /
                     "declare_war_r36_candidate_inspection.json")
COST_FIXTURE = (Path(__file__).parent / "fixtures" /
                "declare_war_r36_native_costs.json")
R37_EXECUTION_FIXTURE = (Path(__file__).parent / "fixtures" /
                         "declare_war_r37_execution_contract.json")
R37B_REAL_EXECUTION_FIXTURE = (Path(__file__).parent / "fixtures" /
                               "declare_war_r37b_real_execution.json")


class DeclareWarToolsTests(unittest.TestCase):
    """Contract tests for the first read-only Declare War query adapter."""

    @staticmethod
    def _event() -> dict:
        return json.loads(FIXTURE.read_text(encoding="utf-8"))["events"]["default"]

    @staticmethod
    def _cost_event() -> dict:
        return json.loads(COST_FIXTURE.read_text(encoding="utf-8"))["event"]

    def _selected_event(self, *, matched: bool = True,
                       province_id: int = 177) -> dict:
        event = self._event()
        candidate = json.loads(CANDIDATE_FIXTURE.read_text(
            encoding="utf-8"))["event"]["candidates"][0]
        candidate.update({
            "native_metadata_hex": "63625f636f7265",
            "metadata_group_raw": 24,
            "casus_belli_key": "cb_core",
            "casus_belli_key_verified": True,
            "target_province_id": province_id,
            "province_identifier_verified": True,
            "beneficiary_tag": "FRA",
            "beneficiary_identifier_verified": True,
        })
        event.update({
            "candidate_enumeration_called": True,
            "candidate_enumeration_complete": True,
            "candidate_native_count": 1 if matched else 0,
            "candidate_capture_truncated": False,
            "candidate_cleanup_verified": True,
            "candidates": [candidate] if matched else [],
            "selection_requested": True,
            "selection_matched": matched,
            "selection_match_count": 1 if matched else 0,
            "requested_casus_belli": "cb_core",
            "requested_province_id": province_id,
            "requested_beneficiary": "FRA",
            "parameter_context_complete": matched,
            "candidate_context_complete": matched,
            "full_rules_complete": matched,
            "native_default_payload": not matched,
        })
        return event

    @staticmethod
    def _installation(root: Path, ack: object = True, *, caps: object = None,
                      submission_ack: object = None):
        session_id = "declare-session"
        installation = root / "installation.json"
        installation.write_text(json.dumps({
            "experiment_id": "declare-contract",
            "session_id": session_id,
            "pid": 1,
            "creation_filetime": 2,
            "dll_sha256": "dll",
            "controlled_countries": ["FRA"],
            "installation_returncode": 0,
        }), encoding="utf-8")
        event = {
            "event": "diplomacy_observer_installed",
            "session_id": session_id,
        }
        if caps is not None:
            event["caps"] = caps
        if ack is not None:
            event["native_declare_war_query"] = ack
        if submission_ack is not None:
            event["native_declare_war_submission"] = submission_ack
        log = root / "control-probe.jsonl"
        log.write_text(json.dumps(event) + "\n", encoding="utf-8")
        return installation

    def setUp(self) -> None:
        self.journal = DurableJournal(":memory:", "declare-contract", "declare-session")

    def tearDown(self) -> None:
        self.journal.close()

    def _run_query(self, session: ObserverSession, *, recipient: str = "BUR",
                   overrides: dict | None = None,
                   parameters: dict | None = None) -> dict:
        request = session.directory / "diplomacy-query.request"
        log = session.directory / "control-probe.jsonl"
        event = {**self._event(), **(overrides or {})}
        errors: list[BaseException] = []

        def writer() -> None:
            try:
                deadline = time.monotonic() + 2
                while not request.exists() and time.monotonic() < deadline:
                    time.sleep(0.001)
                if not request.exists():
                    raise AssertionError("query request was not published")
                fields = request.read_text(encoding="ascii").strip().split()
                selected = bool(parameters)
                self.assertEqual("EU4DIP_QUERY3" if selected else "EU4DIP_QUERY1",
                                 fields[0])
                self.assertEqual("declare_war", fields[3])
                self.assertEqual("FRA", fields[4])
                self.assertEqual(recipient, fields[5])
                self.assertEqual(11 if selected else 8, len(fields))
                if selected:
                    self.assertEqual(parameters["casus_belli"], fields[8])
                    self.assertEqual(str(parameters["war_goal"]["province_id"]), fields[9])
                    self.assertEqual(parameters["war_goal"]["beneficiary"], fields[10])
                request.unlink(missing_ok=True)
                event["query_id"] = fields[2]
                event["session_id"] = session.session_id
                event["recipient"] = recipient
                with log.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(event) + "\n")
            except BaseException as exc:
                errors.append(exc)

        thread = threading.Thread(target=writer)
        thread.start()
        ready = {"status": "ready", "state_id": "ready",
                 "date_raw": event["date_raw"], "reasons": [], "complete": True}
        with patch.object(session, "health", return_value=ready), \
             patch("bridge.diplomacy.probe_identity",
                   return_value={"session_id": session.session_id}):
            result = DiplomacyTools(self.journal, session).inspect_diplomatic_action(
                "declare_war", "FRA", recipient, parameters=parameters or {})
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], errors)
        return result

    def test_catalog_declares_native_query_without_submission(self):
        catalog = DiplomacyTools(self.journal).list_diplomatic_actions()
        item = next(item for item in catalog["actions"]
                    if item["action_id"] == "declare_war")
        self.assertEqual("declare_war", item["native_identifier"])
        self.assertEqual({
            "casus_belli": {"status": "context_required"},
            "war_goal": {"status": "context_required"},
            "call_allies": {"status": "context_required"},
        }, item["parameter_definitions"])
        self.assertEqual("unimplemented", item["phases"]["initiate"]["execute"])

    def test_query_ack_is_top_level_literal_true_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(self._installation(root, ack=True), root / "eu4.exe")
            self.assertIn("native_declare_war_query", session.installation_capabilities())

            copied = self._installation(root, ack=1)
            self.assertNotIn("native_declare_war_query",
                             ObserverSession(copied, root / "eu4.exe").installation_capabilities())

            copied = self._installation(root, ack=None,
                                        caps=["native_declare_war_query"])
            self.assertNotIn("native_declare_war_query",
                             ObserverSession(copied, root / "eu4.exe").installation_capabilities())

    def test_default_event_validates_and_preserves_native_booleans(self):
        event = self._event()
        self.assertTrue(ObserverSession._valid_native_declare_war_inspection(
            event, "declare_war", "FRA", "BUR", "initiate",
            event["date_raw"], event["query_id"], event["session_id"]))
        self.assertTrue(ObserverSession._valid_native_inspection(
            event, "declare_war", "FRA", "BUR", "initiate", event["date_raw"]))
        public = ObserverSession._semantic_declare_war_inspection(
            event, "eu4_escape")
        self.assertEqual("native_declare_war_inspection", public["event"])
        self.assertEqual("declare_war", public["family"])
        self.assertTrue(public["native_validity"])
        self.assertFalse(public["score_applicable"])
        self.assertFalse(public["parameter_context_complete"])
        self.assertTrue(public["native_default_payload"])
        self.assertEqual([], public["candidates"])
        self.assertFalse(public["native_rule_components"]["complete"])

    def test_r36a_real_events_include_pro_forbidden_and_other_targets_true(self):
        payload = json.loads(REAL_FIXTURE.read_text(encoding="utf-8"))
        source = Path(payload["source"]["path"])
        if not source.is_absolute():
            source = Path(__file__).resolve().parents[2] / source
        self.assertEqual(payload["source"]["sha256"],
                         hashlib.sha256(source.read_bytes()).hexdigest())
        events = payload["events"]
        self.assertEqual(5, len(events))
        by_recipient = {event["recipient"]: event for event in events}
        self.assertEqual({"BUR", "ENG", "ORL", "POR", "PRO"}, set(by_recipient))
        for event in events:
            self.assertTrue(ObserverSession._valid_native_declare_war_inspection(
                event, "declare_war", "FRA", event["recipient"], "initiate",
                event["date_raw"], event["query_id"], event["session_id"]))
        self.assertTrue(by_recipient["BUR"]["native_validity"])
        self.assertFalse(by_recipient["PRO"]["native_validity"])
        self.assertFalse(by_recipient["PRO"]["common_action_gate"])
        self.assertTrue(by_recipient["ENG"]["native_validity"])

    def test_r36c_real_candidates_project_metadata_and_empty_sets_safely(self):
        payload = json.loads(REAL_C_FIXTURE.read_text(encoding="utf-8"))
        source = Path(payload["source"]["path"])
        if not source.is_absolute():
            source = Path(__file__).resolve().parents[2] / source
        self.assertEqual(payload["source"]["sha256"],
                         hashlib.sha256(source.read_bytes()).hexdigest())
        events = {event["recipient"]: event for event in payload["events"]}
        self.assertEqual({"ENG", "BUR", "PRO", "ORL", "POR"}, set(events))
        expected_counts = {"ENG": 12, "BUR": 7, "PRO": 0, "ORL": 0, "POR": 0}
        for recipient, event in events.items():
            self.assertTrue(ObserverSession._valid_native_declare_war_inspection(
                event, "declare_war", "FRA", recipient, "initiate",
                event["date_raw"], event["query_id"], event["session_id"]))
            public = ObserverSession._semantic_declare_war_inspection(
                event, "eu4_escape")
            candidates = public["candidates"]
            self.assertEqual(expected_counts[recipient], len(candidates))
            self.assertEqual(list(range(expected_counts[recipient])),
                             [item["candidate_index"] for item in candidates])
            self.assertTrue(public["candidate_enumeration"]["query_complete"])
            self.assertFalse(public["parameter_context_complete"])
            self.assertFalse(public["full_rules_complete"])
            for item in candidates:
                self.assertFalse(item["identifier_verified"])
                for private_key in (
                        "native_metadata_hex", "native_discriminator",
                        "native_address", "native_pointer", "frame_thread"):
                    self.assertNotIn(private_key, item)
                self.assertNotIn("address", " ".join(item).lower())
                self.assertNotIn("pointer", " ".join(item).lower())
            for private_key in (
                    "frame_thread", "common_diagnostic_hex", "send_diagnostic_hex"):
                self.assertNotIn(private_key, public)

        eng_text = [item["metadata_text"] for item in
                    ObserverSession._semantic_declare_war_inspection(
                        events["ENG"], "eu4_escape")["candidates"]]
        bur_text = [item["metadata_text"] for item in
                    ObserverSession._semantic_declare_war_inspection(
                        events["BUR"], "eu4_escape")["candidates"]]
        self.assertEqual(["cb_core"] * 8 + ["cb_conquest"] * 4, eng_text)
        self.assertEqual(["cb_conquest"] * 7, bur_text)

    def test_r36e_real_query1_query3_events_use_session_reader_and_projection(self):
        """Reproject the four R36E events through the real query reader.

        The fixture contains the native event slice from the failed runtime
        report.  The writer below only supplies that observed event after the
        production session publishes its QUERY1/QUERY3 request, so this test
        exercises request generation, event identity validation and public
        projection together.
        """

        payload = json.loads(REAL_E_FIXTURE.read_text(encoding="utf-8"))
        source = Path(payload["source"]["path"])
        if not source.is_absolute():
            source = Path(__file__).resolve().parents[2] / source
        self.assertEqual(payload["source"]["sha256"],
                         hashlib.sha256(source.read_bytes()).hexdigest())
        events = payload["events"]
        self.assertEqual(4, len(events))

        for event in events:
            if event.get("selection_requested") is True:
                parameters = {
                    "casus_belli": event["requested_casus_belli"],
                    "war_goal": {
                        "province_id": event["requested_province_id"],
                        "beneficiary": event["requested_beneficiary"],
                    },
                    "call_allies": [],
                }
            else:
                parameters = {}
            with self.subTest(query_id=event["query_id"],
                              parameters=parameters):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    session = ObserverSession(
                        self._installation(root, ack=True), root / "eu4.exe")
                    result = self._run_query(
                        session, recipient="ENG", overrides=event,
                        parameters=parameters)
                self.assertNotEqual("QUERY_NATIVE_RESULT_INVALID",
                                    result.get("error_code"))
                if not parameters:
                    self.assertEqual("unknown", result["legality"]["status"])
                    self.assertFalse(result["parameters"]["complete"])
                    continue
                self.assertTrue(result["selection_requested"])
                self.assertEqual(parameters, result["parameters"]["requested"])
                if event["selection_matched"]:
                    self.assertTrue(result["selection_matched"])
                    self.assertTrue(result["parameters"]["complete"])
                    self.assertEqual("available", result["legality"]["status"])
                    self.assertTrue(result["legality"]["complete"])
                else:
                    self.assertFalse(result["selection_matched"])
                    self.assertFalse(result["parameters"]["complete"])
                    self.assertEqual("unavailable", result["legality"]["status"])
                    self.assertEqual(
                        "requested_selection_unavailable",
                        result["costs"]["context"])
                    self.assertEqual([], result["costs"]["items"])

    def test_candidate_enumeration_is_validated_and_decoded_without_stable_id(self):
        event = json.loads(CANDIDATE_FIXTURE.read_text(encoding="utf-8"))["event"]
        self.assertTrue(ObserverSession._valid_native_declare_war_inspection(
            event, "declare_war", "FRA", "BUR", "initiate", event["date_raw"],
            event["query_id"], event["session_id"]))
        public = ObserverSession._semantic_declare_war_inspection(event, "eu4_escape")
        self.assertTrue(public["candidate_enumeration"]["query_complete"])
        self.assertEqual(2, public["candidate_enumeration"]["native_count"])
        self.assertEqual(2, len(public["candidates"]))
        self.assertEqual(0, public["candidates"][0]["candidate_index"])
        self.assertEqual(1, public["candidates"][0]["metadata_group_raw"])
        self.assertEqual(
            "如果一个国家接受了我们的结盟提议，那么我们在战争时期就会得到该国的援助。",
            public["candidates"][0]["metadata_text"])
        self.assertFalse(public["candidates"][0]["identifier_verified"])
        self.assertNotIn("native_metadata_hex", public["candidates"][0])
        self.assertNotIn("native_discriminator", public["candidates"][0])

        for overrides in (
                {"candidate_native_count": True},
                {"candidates": [{**event["candidates"][0], "candidate_index": 0},
                                 {**event["candidates"][1], "candidate_index": 0}]},
                {"candidates": [{**event["candidates"][0],
                                  "identifier_verified": True}, event["candidates"][1]]},
                {"candidates": [{**event["candidates"][0],
                                  "native_metadata_hex": "zz"}, event["candidates"][1]]},
        ):
            self.assertFalse(ObserverSession._valid_native_declare_war_inspection(
                {**event, **overrides}, "declare_war", "FRA", "BUR", "initiate",
                event["date_raw"], event["query_id"], event["session_id"]))

    def test_optional_native_costs_are_strictly_validated_and_projected(self):
        event = self._cost_event()
        self.assertTrue(ObserverSession._valid_native_declare_war_inspection(
            event, "declare_war", "FRA", "BUR", "initiate",
            event["date_raw"], event["query_id"], event["session_id"]))
        public = ObserverSession._semantic_declare_war_inspection(event, "eu4_escape")
        costs = public["costs"]
        self.assertEqual("partial", costs["status"])
        self.assertFalse(costs["complete"])
        self.assertEqual("default_parameters_unselected", costs["context"])
        self.assertEqual(1, len(costs["items"]))
        item = costs["items"][0]
        self.assertEqual("stability_loss", item["resource"])
        self.assertEqual(1500, item["native_raw"])
        self.assertEqual(1.5, item["amount"])
        self.assertEqual(1000, item["scale"])
        self.assertEqual("native_rule", item["source"])
        self.assertEqual(1500, costs["raw_components"]["warex_display_raw"])
        self.assertEqual(10000, costs["raw_components"]["primary_raw"])
        self.assertEqual(15000, costs["raw_components"]["secondary_raw"])
        self.assertEqual("WAREX_FROM_STABHIT",
                         costs["raw_components"]["native_text"])
        self.assertEqual("WAREX_FROM_STABHIT", costs["native_text"])
        self.assertTrue(costs["native_text_decoded"])
        self.assertNotIn("diplomatic_power", costs["raw_components"])

        for mutation in (
                {"called": False},
                {"action_unchanged": False},
                {"complete": True},
                {"stability_hit_raw": True},
                {"stability_scale": 999},
                {"native_text_hex": "0"},
                {"text_readable": 1}):
            malformed = json.loads(json.dumps(event))
            malformed["native_costs"].update(mutation)
            self.assertFalse(ObserverSession._valid_native_declare_war_inspection(
                malformed, "declare_war", "FRA", "BUR", "initiate",
                event["date_raw"], event["query_id"], event["session_id"]),
                             mutation)

    def test_query_projects_native_costs_without_changing_unknown_legality(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(self._installation(root, ack=True), root / "eu4.exe")
            result = self._run_query(
                session,
                overrides={"native_costs": self._cost_event()["native_costs"]})
        self.assertEqual("partial", result["costs"]["status"])
        self.assertFalse(result["costs"]["complete"])
        self.assertEqual(1.5, result["costs"]["items"][0]["amount"])
        self.assertEqual("unknown", result["legality"]["status"])
        self.assertEqual("NATIVE_DECLARE_WAR_PARAMETER_CONTEXT_INCOMPLETE",
                         result["legality"]["reasons"][0]["code"])

    def test_identity_and_default_contract_are_strict(self):
        event = self._event()
        kwargs = ("declare_war", "FRA", "BUR", "initiate",
                  event["date_raw"], event["query_id"], event["session_id"])
        self.assertFalse(ObserverSession._valid_native_declare_war_inspection(
            {**event, "family": "alliance"}, *kwargs))
        self.assertFalse(ObserverSession._valid_native_declare_war_inspection(
            {**event, "query_id": "other"}, *kwargs))
        self.assertFalse(ObserverSession._valid_native_declare_war_inspection(
            {**event, "native_validity": 1}, *kwargs))
        self.assertFalse(ObserverSession._valid_native_declare_war_inspection(
            {**event, "native_default_payload": False}, *kwargs))
        self.assertFalse(ObserverSession._valid_native_declare_war_inspection(
            {**event, "candidates": [{"id": 1}]}, *kwargs))

    def test_query_projects_unknown_until_parameter_context_is_complete(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(self._installation(root, ack=True), root / "eu4.exe")
            result = self._run_query(session)
        self.assertEqual("partial_native_rules", result["interface_support"]["query"])
        self.assertEqual("declare_war", result["family"])
        self.assertEqual("unknown", result["legality"]["status"])
        self.assertEqual("NATIVE_DECLARE_WAR_PARAMETER_CONTEXT_INCOMPLETE",
                         result["legality"]["reasons"][0]["code"])
        self.assertFalse(result["legality"]["complete"])
        self.assertEqual("not_applicable", result["acceptance"]["applicability"])
        self.assertTrue(result["acceptance"]["complete"])
        self.assertTrue(result["native_rule_components"]["native_validity"])
        self.assertFalse(result["native_rule_components"]["parameter_context_complete"])
        self.assertEqual([], result["parameters"]["candidates"])

    def test_query3_matches_cb_core_province_and_beneficiary(self):
        parameters = {
            "casus_belli": "cb_core",
            "war_goal": {"province_id": 177, "beneficiary": "FRA"},
            "call_allies": [],
        }
        event = self._selected_event()
        event["native_costs"] = self._cost_event()["native_costs"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(self._installation(root, ack=True), root / "eu4.exe")
            result = self._run_query(session, recipient="ENG", overrides=event,
                                     parameters=parameters)
        self.assertEqual("ENG", result["recipient"])
        self.assertTrue(result["selection_requested"])
        self.assertTrue(result["selection_matched"])
        self.assertTrue(result["parameters"]["complete"])
        self.assertEqual(parameters, result["parameters"]["actual"])
        self.assertEqual("available", result["legality"]["status"])
        self.assertTrue(result["legality"]["complete"])
        self.assertEqual("selected_parameters", result["costs"]["context"])
        candidate = result["parameters"]["candidates"][0]
        self.assertEqual("cb_core", candidate["casus_belli_key"])
        self.assertTrue(candidate["casus_belli_key_verified"])
        self.assertEqual(177, candidate["target_province_id"])
        self.assertTrue(candidate["province_identifier_verified"])
        self.assertEqual("FRA", candidate["beneficiary_tag"])
        self.assertTrue(candidate["beneficiary_identifier_verified"])

    def test_query3_unknown_province_is_unavailable(self):
        parameters = {
            "casus_belli": "cb_core",
            "war_goal": {"province_id": 999, "beneficiary": "FRA"},
            "call_allies": [],
        }
        event = self._selected_event(matched=False, province_id=999)
        event["native_costs"] = self._cost_event()["native_costs"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(self._installation(root, ack=True), root / "eu4.exe")
            result = self._run_query(session, recipient="ENG", overrides=event,
                                     parameters=parameters)
        self.assertTrue(result["selection_requested"])
        self.assertFalse(result["selection_matched"])
        self.assertEqual(0, result["selection_match_count"])
        self.assertEqual("unavailable", result["legality"]["status"])
        self.assertEqual("NATIVE_DECLARE_WAR_SELECTION_NOT_FOUND",
                         result["legality"]["reasons"][0]["code"])
        self.assertFalse(result["parameters"]["complete"])
        self.assertIsNone(result["parameters"]["actual"])
        self.assertEqual("unknown", result["costs"]["status"])
        self.assertEqual([], result["costs"]["items"])
        self.assertFalse(result["costs"]["complete"])
        self.assertEqual("requested_selection_unavailable",
                         result["costs"]["context"])

    def test_query3_rejects_receipt_bound_to_different_request_parameters(self):
        requested = {
            "casus_belli": "cb_core",
            "war_goal": {"province_id": 178, "beneficiary": "FRA"},
            "call_allies": [],
        }
        event = self._selected_event(matched=True, province_id=177)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(self._installation(root, ack=True), root / "eu4.exe")
            result = self._run_query(session, recipient="ENG", overrides=event,
                                     parameters=requested)
        self.assertEqual("QUERY_NATIVE_RESULT_INVALID",
                         result["legality"]["reasons"][0]["code"])

    def test_query3_rejects_nonempty_call_allies_before_wire(self):
        parameters = {
            "casus_belli": "cb_core",
            "war_goal": {"province_id": 177, "beneficiary": "FRA"},
            "call_allies": ["POR"],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(self._installation(root, ack=True), root / "eu4.exe")
            api = DiplomacyTools(self.journal, session)
            with self.assertRaisesRegex(ValueError, "DECLARE_WAR_CALL_ALLIES_UNSUPPORTED"):
                api.inspect_diplomatic_action("declare_war", "FRA", "ENG",
                                              parameters=parameters)

    def test_query_capability_gates_dispatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(self._installation(root, ack=None), root / "eu4.exe")
            api = DiplomacyTools(self.journal, session)
            result = api.inspect_diplomatic_action("declare_war", "FRA", "BUR")
            self.assertEqual("catalog_only", result["interface_support"]["query"])
            self.assertEqual("NATIVE_RULE_QUERY_UNIMPLEMENTED",
                             result["legality"]["reasons"][0]["code"])
            with patch.object(session, "health", return_value={
                    "status": "ready", "state_id": "ready", "date_raw": 1,
                    "reasons": [], "complete": True}):
                item = next(item for item in api.list_diplomatic_actions()["actions"]
                            if item["action_id"] == "declare_war")
            self.assertEqual("unimplemented", item["phases"]["initiate"]["query"])

    def test_submission_ack_is_top_level_literal_true_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(
                self._installation(root, ack=True, submission_ack=True),
                root / "eu4.exe")
            self.assertIn("native_declare_war_submission",
                          session.installation_capabilities())
            copied = self._installation(root, ack=True, submission_ack=1)
            self.assertNotIn("native_declare_war_submission",
                             ObserverSession(copied, root / "eu4.exe").installation_capabilities())
            copied = self._installation(root, ack=True, submission_ack=None,
                                        caps=["native_declare_war_submission"])
            self.assertNotIn("native_declare_war_submission",
                             ObserverSession(copied, root / "eu4.exe").installation_capabilities())
            session = ObserverSession(
                self._installation(root, ack=True, submission_ack=True),
                root / "eu4.exe")
            ready = {"status": "ready", "state_id": "ready", "date_raw": 56501040,
                     "reasons": [], "complete": True}
            with patch.object(session, "health", return_value=ready):
                actions = DiplomacyTools(self.journal, session).list_diplomatic_actions()
            item = next(item for item in actions["actions"]
                        if item["action_id"] == "declare_war")
            self.assertEqual("native_declare_war_submission",
                             item["phases"]["initiate"]["execute"])

    def test_declare_war_submission_and_execution_strict_bindings(self):
        fixture = json.loads(R37_EXECUTION_FIXTURE.read_text(encoding="utf-8"))
        selected = {
            "casus_belli": "cb_core",
            "war_goal": {"province_id": 177, "beneficiary": "FRA"},
            "call_allies": [],
        }
        submission = fixture["submission"]
        self.assertTrue(ObserverSession._valid_native_declare_war_submission_result(
            submission, submission["request_id"], submission["session_id"],
            "FRA", "ENG", "initiate", submission["date_raw"], selected))
        self.assertFalse(ObserverSession._valid_native_declare_war_submission_result(
            {**submission, "family": "rival"}, submission["request_id"],
            submission["session_id"], "FRA", "ENG", "initiate",
            submission["date_raw"], selected))
        self.assertFalse(ObserverSession._valid_native_declare_war_submission_result(
            {**submission, "war_goal_province": 178}, submission["request_id"],
            submission["session_id"], "FRA", "ENG", "initiate",
            submission["date_raw"], selected))
        public_receipt = ObserverSession._public_native_declare_war_submission_receipt(
            submission, submission["request_id"], "FRA", "ENG", "initiate",
            submission["date_raw"], selected)
        self.assertEqual("declare_war", public_receipt["family"])
        self.assertNotIn("session_id", public_receipt)

        execution = fixture["execution"]
        public = ObserverSession._public_native_declare_war_execution_result(
            execution, execution["request_id"], execution["session_id"],
            "FRA", "ENG", "initiate", execution["date_raw"], selected)
        self.assertEqual("executed", public["native_outcome"])
        self.assertTrue(public["war_after"])
        self.assertTrue(public["war_identity_verified"])
        self.assertTrue(public["stability_verified"])
        self.assertIsNone(ObserverSession._public_native_declare_war_execution_result(
            {**execution, "war_before": True}, execution["request_id"],
            execution["session_id"], "FRA", "ENG", "initiate",
            execution["date_raw"], selected))
        self.assertIsNone(ObserverSession._public_native_declare_war_execution_result(
            {**execution, "family": "rival"}, execution["request_id"],
            execution["session_id"], "FRA", "ENG", "initiate",
            execution["date_raw"], selected))
        unknown = fixture["unknown_execution"]
        unknown_public = ObserverSession._public_native_declare_war_execution_result(
            unknown, unknown["request_id"], unknown["session_id"],
            "FRA", "ENG", "initiate", unknown["date_raw"], selected)
        self.assertEqual("unknown", unknown_public["native_outcome"])
        self.assertFalse(unknown_public["war_after"])
        self.assertFalse(unknown_public["war_identity_verified"])
        self.assertFalse(unknown_public["stability_verified"])
        self.assertIsNone(unknown_public["war_id"])
        self.assertIsNone(unknown_public["stability_before_raw"])
        self.assertIsNone(unknown_public["stability_after_raw"])

    def test_declare_war_nullable_identity_and_stability_require_consistent_flags(self):
        fixture = json.loads(R37_EXECUTION_FIXTURE.read_text(encoding="utf-8"))
        parameters = {
            "casus_belli": "cb_core",
            "war_goal": {"province_id": 177, "beneficiary": "FRA"},
            "call_allies": [],
        }
        nullable = fixture["execution_unmapped"]
        public = ObserverSession._public_native_declare_war_execution_result(
            nullable, nullable["request_id"], nullable["session_id"],
            "FRA", "ENG", "initiate", nullable["date_raw"], parameters)
        self.assertEqual("executed", public["native_outcome"])
        self.assertIsNone(public["war_id"])
        self.assertIsNone(public["stability_before_raw"])
        self.assertIsNone(public["stability_after_raw"])
        self.assertFalse(public["war_identity_verified"])
        self.assertFalse(public["stability_verified"])
        self.assertIsNone(ObserverSession._public_native_declare_war_execution_result(
            {**nullable, "war_identity_verified": True},
            nullable["request_id"], nullable["session_id"], "FRA", "ENG",
            "initiate", nullable["date_raw"], parameters))
        self.assertIsNone(ObserverSession._public_native_declare_war_execution_result(
            {**nullable, "stability_before_raw": 0},
            nullable["request_id"], nullable["session_id"], "FRA", "ENG",
            "initiate", nullable["date_raw"], parameters))

    def test_declare_war_real_nullable_event_and_reduced_receipt_round_trip(self):
        fixture = json.loads(R37B_REAL_EXECUTION_FIXTURE.read_text(encoding="utf-8"))
        parameters = {
            "casus_belli": "cb_core",
            "war_goal": {"province_id": 177, "beneficiary": "FRA"},
            "call_allies": [],
        }
        submission = fixture["submission"]
        execution = fixture["execution"]
        reduced = ObserverSession._public_native_declare_war_submission_receipt(
            submission, fixture["request_id"], "FRA", "ENG", "initiate",
            fixture["execution"]["date_raw"], parameters)
        self.assertIsNotNone(reduced)
        self.assertNotIn("session_id", reduced)
        self.assertIsNotNone(DiplomacyTools._public_declare_war_submission_receipt(
            reduced, fixture["request_id"], "FRA", "ENG", "initiate",
            fixture["execution"]["date_raw"], parameters))
        public = ObserverSession._public_native_declare_war_execution_result(
            execution, fixture["request_id"], fixture["session_id"],
            "FRA", "ENG", "initiate", fixture["execution"]["date_raw"],
            parameters)
        self.assertEqual("executed", public["native_outcome"])
        self.assertTrue(public["execution_verified"])
        self.assertIsNone(public["war_id"])
        self.assertIsNone(public["stability_before_raw"])
        self.assertFalse(public["war_identity_verified"])
        self.assertFalse(public["stability_verified"])

    def test_declare_war_execute_accepts_already_reduced_native_receipt(self):
        fixture = json.loads(R37B_REAL_EXECUTION_FIXTURE.read_text(encoding="utf-8"))
        parameters = {
            "casus_belli": "cb_core",
            "war_goal": {"province_id": 177, "beneficiary": "FRA"},
            "call_allies": [],
        }
        reduced = ObserverSession._public_native_declare_war_submission_receipt(
            fixture["submission"], fixture["request_id"], "FRA", "ENG",
            "initiate", fixture["execution"]["date_raw"], parameters)
        execution_public = ObserverSession._public_native_declare_war_execution_result(
            fixture["execution"], fixture["request_id"], fixture["session_id"],
            "FRA", "ENG", "initiate", fixture["execution"]["date_raw"],
            parameters)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(
                self._installation(root, ack=True, submission_ack=True),
                root / "eu4.exe")
            api = DiplomacyTools(self.journal, session)
            inspection = {
                "action_id": "declare_war", "actor": "FRA", "recipient": "ENG",
                "phase": "initiate",
                "session": {"status": "ready", "date_raw": fixture["execution"]["date_raw"]},
                "legality": {"status": "available", "complete": True},
                "authorization": {"status": "available", "complete": True},
                "interface_support": {"execute": "native_declare_war_submission"},
                "parameters": {"requested": parameters, "actual": parameters,
                                "complete": True},
            }
            with patch.object(api, "inspect_diplomatic_action",
                              return_value=inspection), \
                 patch.object(session, "submit_declare_war",
                              return_value={"status": "submitted",
                                            "receipt": reduced}) as submitter, \
                 patch.object(session, "read_native_declare_war_execution",
                              return_value={"status": "executed",
                                            "result": execution_public}):
                result = api.execute_diplomatic_action(
                    fixture["request_id"], "declare_war", "FRA", "ENG",
                    "initiate", parameters)
            submitter.assert_called_once()
            self.assertEqual("executed", result["status"])
            self.assertEqual("executed", result["game_outcome"])
            self.assertIsNone(result["result"]["war_id"])

    def test_declare_war_invalidated_submission_reconciles_from_real_events(self):
        fixture = json.loads(R37B_REAL_EXECUTION_FIXTURE.read_text(encoding="utf-8"))
        request_id = fixture["request_id"]
        payload = {
            "action_id": "declare_war", "actor": "FRA", "recipient": "ENG",
            "phase": "initiate", "parameters": {
                "casus_belli": "cb_core",
                "war_goal": {"province_id": 177, "beneficiary": "FRA"},
                "call_allies": [],
            },
        }
        self.journal.register(request_id, payload)
        for status in ("queued", "consumed", "constructed"):
            self.journal.transition(request_id, status, result={})
        self.journal.claim_submission(request_id, submission_id="native_" + request_id)
        self.journal.transition(
            request_id, "invalidated",
            result={"submitted": False, "reason": {
                "code": "NATIVE_DECLARE_WAR_SUBMISSION_RECEIPT_INVALID"}},
            evidence_type="native_submission_failure",
            evidence_content={"submitted": False},
            arrival_layer="bridge_validation",
            event_id="native-submit-failure:" + request_id,
        )
        selected = payload["parameters"]
        receipt = ObserverSession._public_native_declare_war_submission_receipt(
            fixture["submission"], request_id, "FRA", "ENG", "initiate",
            fixture["execution"]["date_raw"], selected)
        result = ObserverSession._public_native_declare_war_execution_result(
            fixture["execution"], request_id, fixture["session_id"],
            "FRA", "ENG", "initiate", fixture["execution"]["date_raw"],
            selected)
        reconciled = self.journal.reconcile_declare_war_executed(
            request_id, result, receipt,
            expected_reason_code="NATIVE_DECLARE_WAR_SUBMISSION_RECEIPT_INVALID",
            expected_payload=payload,
            evidence_content={"source_fixture": R37B_REAL_EXECUTION_FIXTURE.name},
            event_id="native-declare-war-reconcile:" + request_id,
        )
        self.assertEqual("executed", reconciled.status)
        self.assertIsNotNone(reconciled.native_receipt)
        self.assertIsNone(reconciled.result["war_id"])
        evidence = self.journal.list_evidence_for_record(reconciled)
        self.assertEqual(2, len(evidence))
        self.assertEqual("native_declare_war_reconciliation", evidence[-1].evidence_type)
        repeated = self.journal.reconcile_declare_war_executed(
            request_id, result, receipt,
            expected_reason_code="NATIVE_DECLARE_WAR_SUBMISSION_RECEIPT_INVALID",
            expected_payload=payload,
            evidence_content={"source_fixture": R37B_REAL_EXECUTION_FIXTURE.name},
            event_id="native-declare-war-reconcile:" + request_id,
        )
        self.assertEqual("executed", repeated.status)
        self.assertEqual(2, len(self.journal.list_evidence_for_record(repeated)))

    def test_submit_declare_war_uses_exec3_and_bound_receipt(self):
        fixture = json.loads(R37_EXECUTION_FIXTURE.read_text(encoding="utf-8"))
        parameters = {
            "casus_belli": "cb_core",
            "war_goal": {"province_id": 177, "beneficiary": "FRA"},
            "call_allies": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(
                self._installation(root, ack=True, submission_ack=True),
                root / "eu4.exe")
            log = root / "control-probe.jsonl"
            request = root / "diplomacy-execute.req"
            errors: list[BaseException] = []

            def writer() -> None:
                try:
                    deadline = time.monotonic() + 2
                    while not request.exists() and time.monotonic() < deadline:
                        time.sleep(0.001)
                    self.assertTrue(request.exists())
                    fields = request.read_text(encoding="ascii").strip().split("|")
                    self.assertEqual("EU4DIP_EXEC3", fields[0])
                    self.assertEqual(12, len(fields))
                    self.assertEqual("declare_war", fields[5])
                    self.assertEqual("FRA", fields[6])
                    self.assertEqual("ENG", fields[7])
                    self.assertEqual("initiate", fields[8])
                    self.assertEqual(["cb_core", "177", "FRA"], fields[9:12])
                    request.unlink(missing_ok=True)
                    event = {**fixture["submission"],
                             "request_id": fields[1],
                             "session_id": session.session_id,
                             "date_raw": int(fields[4])}
                    with log.open("a", encoding="utf-8", newline="\n") as stream:
                        stream.write(json.dumps(event) + "\n")
                except BaseException as exc:
                    errors.append(exc)

            thread = threading.Thread(target=writer)
            thread.start()
            receipt = session.submit_declare_war(
                "r37_wire_001", "FRA", "ENG", "initiate", 56501040,
                parameters, timeout=1)
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual([], errors)
            self.assertEqual("submitted", receipt["status"])
            self.assertEqual("declare_war", receipt["receipt"]["family"])

    def test_read_native_declare_war_execution_is_family_and_parameter_bound(self):
        fixture = json.loads(R37_EXECUTION_FIXTURE.read_text(encoding="utf-8"))
        parameters = {
            "casus_belli": "cb_core",
            "war_goal": {"province_id": 177, "beneficiary": "FRA"},
            "call_allies": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(self._installation(root, ack=True), root / "eu4.exe")
            with (root / "control-probe.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(fixture["execution"]) + "\n")
            result = session.read_native_declare_war_execution(
                "r37_declare_eng_001", "FRA", "ENG", "initiate",
                56501040, parameters)
            self.assertEqual("executed", result["status"])
            self.assertEqual(42, result["result"]["war_id"])
            bad = {**fixture["execution"], "family": "rival",
                   "request_id": "r37_declare_eng_002"}
            with (root / "control-probe.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(bad) + "\n")
            invalid = session.read_native_declare_war_execution(
                "r37_declare_eng_002", "FRA", "ENG", "initiate",
                56501040, parameters)
            self.assertEqual("invalid", invalid["status"])

    def test_execute_declare_war_binds_parameters_and_is_idempotent(self):
        fixture = json.loads(R37_EXECUTION_FIXTURE.read_text(encoding="utf-8"))
        parameters = {
            "casus_belli": "cb_core",
            "war_goal": {"province_id": 177, "beneficiary": "FRA"},
            "call_allies": [],
        }
        execution_public = ObserverSession._public_native_declare_war_execution_result(
            fixture["execution"], fixture["execution"]["request_id"],
            fixture["execution"]["session_id"], "FRA", "ENG", "initiate",
            fixture["execution"]["date_raw"], parameters)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(
                self._installation(root, ack=True, submission_ack=True),
                root / "eu4.exe")
            api = DiplomacyTools(self.journal, session)
            inspection = {
                "action_id": "declare_war", "actor": "FRA", "recipient": "ENG",
                "phase": "initiate",
                "session": {"status": "ready", "date_raw": 56501040},
                "legality": {"status": "available", "complete": True},
                "authorization": {"status": "available", "complete": True},
                "interface_support": {"execute": "native_declare_war_submission"},
                "parameters": {"requested": parameters, "actual": parameters,
                                "complete": True},
            }
            with patch.object(api, "inspect_diplomatic_action",
                              return_value=inspection), \
                 patch.object(session, "submit_declare_war",
                              return_value={"status": "submitted",
                                            "receipt": {**fixture["submission"],
                                                        "request_id": "r37_execute_001"}}) as submitter, \
                 patch.object(session, "read_native_declare_war_execution",
                              return_value={"status": "executed",
                                            "result": execution_public}):
                first = api.execute_diplomatic_action(
                    "r37_execute_001", "declare_war", "FRA", "ENG",
                    "initiate", parameters)
                repeated = api.execute_diplomatic_action(
                    "r37_execute_001", "declare_war", "FRA", "ENG",
                    "initiate", parameters)
                conflict = api.execute_diplomatic_action(
                    "r37_execute_001", "declare_war", "FRA", "ENG", "initiate", {
                        **parameters, "war_goal": {"province_id": 178, "beneficiary": "FRA"}})
            self.assertEqual("executed", first["status"])
            self.assertEqual("executed", first["game_outcome"])
            self.assertEqual("executed", first["result"]["native_outcome"])
            self.assertTrue(repeated["idempotent"])
            self.assertEqual("executed", repeated["status"])
            self.assertEqual("conflict", conflict["status"])
            self.assertEqual(1, submitter.call_count)


if __name__ == "__main__":
    unittest.main()
