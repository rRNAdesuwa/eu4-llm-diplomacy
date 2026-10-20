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
from work.run_rival_queries import _rival_query_shape


FIXTURE = (Path(__file__).parent / "fixtures" / "rival_r34_native_inspections.json")


class RivalToolsTests(unittest.TestCase):
    """Contract tests for the query-only R34 Rival family."""

    @staticmethod
    def _events() -> dict:
        return json.loads(FIXTURE.read_text(encoding="utf-8"))["events"]

    @staticmethod
    def _real_events() -> list[dict]:
        fixture = (Path(__file__).parent / "fixtures" /
                   "rival_r34a_native_inspections.json")
        return [item["event"] for item in json.loads(
            fixture.read_text(encoding="utf-8"))["events"]]

    @staticmethod
    def _schema2_events() -> dict:
        fixture = (Path(__file__).parent / "fixtures" /
                   "rival_r34b_native_inspections.json")
        return json.loads(fixture.read_text(encoding="utf-8"))["events"]

    @staticmethod
    def _real_schema2_events() -> list[dict]:
        fixture = (Path(__file__).parent / "fixtures" /
                   "rival_r34b_real_native_inspections.json")
        return [item["event"] for item in json.loads(
            fixture.read_text(encoding="utf-8"))["events"]]

    @staticmethod
    def _installation(root: Path, *, ack: object = True,
                      caps: list[str] | None = None,
                      submission_ack: object = None) -> tuple[Path, Path]:
        session_id = "rival-session"
        installation = root / "installation.json"
        installation.write_text(json.dumps({
            "experiment_id": "rival-contract",
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
        if ack is not None:
            event["native_rival_query"] = ack
        if submission_ack is not None:
            event["native_rival_submission"] = submission_ack
        if caps is not None:
            event["caps"] = caps
        log = root / "control-probe.jsonl"
        log.write_text(json.dumps(event) + "\n", encoding="utf-8")
        return installation, log

    def setUp(self) -> None:
        self.journal = DurableJournal(":memory:", "rival-contract", "rival-session")

    def tearDown(self) -> None:
        self.journal.close()

    def test_catalog_keeps_query_only_rival_contract(self):
        api = DiplomacyTools(self.journal)
        catalog = api.list_diplomatic_actions()
        by_id = {item["action_id"]: item for item in catalog["actions"]}
        for action_id in ("set_rival", "remove_rival"):
            action = by_id[action_id]
            self.assertEqual("rival", action["native_identifier"])
            self.assertEqual({}, action["parameter_definitions"])
            self.assertEqual(["initiate"], list(action["phases"]))
            self.assertEqual("unimplemented", action["phases"]["initiate"]["execute"])
            inspection = api.inspect_diplomatic_action(action_id, "FRA", "SAV")
            self.assertEqual("not_applicable", inspection["acceptance"]["applicability"])
            self.assertTrue(inspection["acceptance"]["complete"])
            self.assertEqual("unimplemented", inspection["interface_support"]["execute"])
            with self.assertRaisesRegex(ValueError, "RIVAL_PARAMETERS_UNSUPPORTED"):
                api.inspect_diplomatic_action(action_id, "FRA", "SAV",
                                              parameters={"foo": 1})
            with self.assertRaisesRegex(ValueError, "RIVAL_INITIATE_ONLY"):
                api.inspect_diplomatic_action(action_id, "FRA", "SAV", "accept")

    def test_rival_query_ack_is_exact_and_not_inferred(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = self._installation(root, ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            self.assertEqual(frozenset({"native_rival_query"}),
                             session.installation_capabilities())
            with patch.object(session, "health", return_value={
                    "status": "ready", "state_id": "ready", "date_raw": 1,
                    "reasons": [], "complete": True}):
                by_id = {item["action_id"]: item for item in
                         DiplomacyTools(self.journal, session).list_diplomatic_actions()["actions"]}
            self.assertEqual("partial_native_rules",
                             by_id["set_rival"]["phases"]["initiate"]["query"])
            self.assertEqual("unimplemented",
                             by_id["set_rival"]["phases"]["initiate"]["execute"])

            copied, _ = self._installation(
                root, ack=None, caps=["native_rival_query"])
            copied_session = ObserverSession(copied, root / "eu4.exe")
            self.assertEqual(frozenset(), copied_session.installation_capabilities())
            copied_submission, _ = self._installation(
                root, ack=True, caps=["native_rival_submission"])
            copied_submission_session = ObserverSession(
                copied_submission, root / "eu4.exe")
            self.assertNotIn("native_rival_submission",
                             copied_submission_session.installation_capabilities())

    def _run_query(self, session: ObserverSession, action_id: str,
                   overrides: dict | None = None, *, recipient: str = "SAV",
                   date_raw: int | None = None) -> dict:
        request = session.directory / "diplomacy-query.request"
        log = session.directory / "control-probe.jsonl"
        event = {**self._events()[action_id], **(overrides or {})}
        expected_date = date_raw if date_raw is not None else event.get("date_raw", 1)
        errors: list[BaseException] = []

        def writer() -> None:
            try:
                deadline = time.monotonic() + 2
                while not request.exists() and time.monotonic() < deadline:
                    time.sleep(0.001)
                if not request.exists():
                    raise AssertionError("query request was not published")
                fields = request.read_text(encoding="ascii").strip().split()
                self.assertEqual("EU4DIP_QUERY1", fields[0])
                self.assertEqual(action_id, fields[3])
                self.assertEqual("FRA", fields[4])
                self.assertEqual(recipient, fields[5])
                # The command token is followed by the existing seven-field
                # Query1 payload.
                self.assertEqual(8, len(fields))
                request.unlink(missing_ok=True)
                event["query_id"] = fields[2]
                event["session_id"] = session.session_id
                with log.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(event) + "\n")
            except BaseException as exc:
                errors.append(exc)

        thread = threading.Thread(target=writer)
        thread.start()
        ready = {"status": "ready", "state_id": "ready", "date_raw": expected_date,
                 "reasons": [], "complete": True}
        with patch.object(session, "health", return_value=ready), \
             patch("bridge.diplomacy.probe_identity",
                   return_value={"session_id": session.session_id}):
            result = DiplomacyTools(self.journal, session).inspect_diplomatic_action(
                action_id, "FRA", recipient)
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], errors)
        return result

    def test_bounded_rival_query_projects_relation_counts_diagnostic_and_unknown_true(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = self._installation(root, ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            result = self._run_query(session, "set_rival")
            self.assertEqual("partial_native_rules", result["interface_support"]["query"])
            self.assertEqual("unavailable", result["authorization"]["status"])
            self.assertEqual("unimplemented", result["interface_support"]["execute"])
            self.assertEqual("unknown", result["legality"]["status"])
            self.assertFalse(result["legality"]["complete"])
            self.assertEqual("NATIVE_RIVAL_UI_RULES_INCOMPLETE",
                             result["legality"]["reasons"][0]["code"])
            self.assertEqual({"rival_active": False,
                              "rival_since_date_raw": None,
                              "complete": True}, result["relationship_state"])
            self.assertEqual(0, result["resources"]["rivals"]["current_count"])
            self.assertEqual(3, result["resources"]["rivals"]["max_count"])
            self.assertEqual(100, result["resources"]["diplomatic_power"]["native_value_raw"])
            self.assertEqual("ok", result["native_diagnostic"]["text"])
            self.assertFalse(result["acceptance"]["prediction_available"])
            self.assertEqual("not_applicable", result["acceptance"]["applicability"])
            public_text = json.dumps(result, ensure_ascii=False)
            self.assertNotIn("frame_thread", public_text)
            self.assertNotIn('"pid"', public_text)
            self.assertNotIn("address", public_text)

    def test_rival_membership_predicates_report_unavailable_without_complete_rules(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = self._installation(root, ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            active = self._run_query(session, "set_rival", {
                "rival_active": True, "rival_since_date_raw": 1, "rival_count": 1})
            self.assertEqual("unavailable", active["legality"]["status"])
            self.assertEqual("NATIVE_RIVAL_ALREADY_ACTIVE",
                             active["legality"]["reasons"][0]["code"])

            inactive = self._run_query(session, "remove_rival", {
                "rival_active": False, "rival_since_date_raw": None, "rival_count": 0})
            self.assertEqual("unavailable", inactive["legality"]["status"])
            self.assertEqual("NATIVE_RIVAL_MEMBERSHIP_FALSE",
                             inactive["legality"]["reasons"][0]["code"])

    def test_schema2_candidate_fields_are_public_and_set_predicate_failures_are_explicit(self):
        schema2 = self._schema2_events()["set_rival"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = self._installation(
                root, ack=True, submission_ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            result = self._run_query(session, "set_rival", schema2)
            self.assertEqual(2, result["rules_schema"])
            self.assertTrue(result["candidate_eligibility_available"])
            self.assertTrue(result["candidate_eligible"])
            self.assertTrue(result["target_exists"])
            self.assertTrue(result["ui_war_allowed"])
            self.assertEqual("unknown", result["legality"]["status"])
            self.assertFalse(result["legality"]["complete"])
            self.assertEqual("NATIVE_RIVAL_EXECUTION_PREFLIGHT_INCOMPLETE",
                             result["legality"]["reasons"][0]["code"])
            self.assertEqual("native_rival_submission",
                             result["interface_support"]["execute"])
            self.assertEqual("available", result["authorization"]["status"])

            for field, code in (
                    ("candidate_eligible", "NATIVE_RIVAL_CANDIDATE_INELIGIBLE"),
                    ("target_exists", "NATIVE_RIVAL_TARGET_NOT_FOUND"),
                    ("ui_war_allowed", "NATIVE_RIVAL_WAR_GATE_FALSE")):
                overrides = {**schema2, field: False}
                checked = self._run_query(session, "set_rival", overrides)
                self.assertEqual("unavailable", checked["legality"]["status"])
                self.assertEqual(code, checked["legality"]["reasons"][0]["code"])

            unavailable = self._run_query(
                session, "set_rival",
                {**schema2, "candidate_eligibility_available": False})
            self.assertEqual("unknown", unavailable["legality"]["status"])
            self.assertEqual("NATIVE_RIVAL_CANDIDATE_RULE_UNAVAILABLE",
                             unavailable["legality"]["reasons"][0]["code"])

            remove = self._run_query(
                session, "remove_rival", self._schema2_events()["remove_rival"])
            self.assertEqual("unknown", remove["legality"]["status"])
            self.assertFalse(remove["candidate_eligible"])

    def test_schema1_real_events_remain_partial_and_new_fields_are_not_invented(self):
        for event in self._real_events():
            semantic = ObserverSession._semantic_rival_inspection(event)
            self.assertEqual(1, semantic["rules_schema"])
            self.assertFalse(semantic["candidate_eligibility_available"])
            self.assertIsNone(semantic["candidate_eligible"])
            self.assertIsNone(semantic["target_exists"])
            self.assertIsNone(semantic["ui_war_allowed"])
            self.assertFalse(semantic["full_rules_complete"])

    def test_operator_accepts_schema1_and_requires_schema2_only_when_requested(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = self._installation(root, ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            schema1_public = self._run_query(session, "set_rival")
            old_shape = _rival_query_shape(schema1_public, "set_rival", "SAV", 1)
            self.assertTrue(old_shape["complete"])
            self.assertFalse(_rival_query_shape(
                schema1_public, "set_rival", "SAV", 1,
                require_ui_candidates=True)["complete"])

            schema2_public = self._run_query(
                session, "set_rival", self._schema2_events()["set_rival"])
            new_shape = _rival_query_shape(
                schema2_public, "set_rival", "SAV", 1,
                require_ui_candidates=True)
            self.assertTrue(new_shape["complete"])
            self.assertEqual(2, new_shape["rules_schema"])
            self.assertTrue(new_shape["candidate_shape"]["complete"])

    def test_rival_validator_rejects_cross_family_and_score_fields(self):
        valid = self._events()["set_rival"]
        self.assertTrue(ObserverSession._valid_native_rival_inspection(
            valid, "set_rival", "FRA", "SAV", "initiate", 1))
        for field, value in (
                ("family", "guarantee"),
                ("action_id", "remove_rival"),
                ("native_command_validity", "true"),
                ("rival_state_verified", False),
                ("score_available", True),
                ("full_rules_complete", True),
                ("submitted", True)):
            with self.subTest(field=field):
                self.assertFalse(ObserverSession._valid_native_rival_inspection(
                    {**valid, field: value}, "set_rival", "FRA", "SAV", "initiate", 1))

    def test_real_r34a_events_preserve_literal_false_status_fields(self):
        events = self._real_events()
        self.assertEqual(4, len(events))
        for event in events:
            with self.subTest(query_id=event["query_id"]):
                self.assertTrue(ObserverSession._valid_native_rival_inspection(
                    event, event["action_id"], event["actor"], event["recipient"],
                    event["phase"], event["date_raw"], event["query_id"],
                    event["session_id"]))
                semantic = ObserverSession._semantic_rival_inspection(event)
                self.assertFalse(semantic["candidate_eligibility_available"])
                self.assertFalse(semantic["submitted"])
                self.assertFalse(semantic["native_rule_components"][
                    "candidate_eligibility_available"])
                self.assertFalse(semantic["native_rule_components"]["complete"])

    def test_real_r34b_events_preserve_candidate_fields_and_false_values(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" /
                              "rival_r34b_real_native_inspections.json"
                              ).read_text(encoding="utf-8"))
        self.assertEqual(14, len(fixture["events"]))
        self.assertEqual(2, len(fixture["source"]["files"]))
        self.assertEqual("eu4_escape", fixture["source"]["native_text_codec"])
        for item in fixture["events"]:
            event = item["event"]
            with self.subTest(query_id=event["query_id"]):
                self.assertTrue(ObserverSession._valid_native_rival_inspection(
                    event, event["action_id"], event["actor"], event["recipient"],
                    event["phase"], event["date_raw"], event["query_id"],
                    event["session_id"]))
                semantic = ObserverSession._semantic_rival_inspection(
                    event, "eu4_escape")
                self.assertEqual(2, semantic["rules_schema"])
                self.assertTrue(semantic["candidate_eligibility_available"])
                self.assertTrue(semantic["target_exists"])
                self.assertFalse(semantic["ui_war_allowed"])
                self.assertFalse(semantic["native_command_validity"])
                self.assertFalse(semantic["full_rules_complete"])
                self.assertFalse(semantic["submitted"])

        candidate_by_recipient = {
            event["recipient"]: event["candidate_eligible"]
            for event in self._real_schema2_events()
            if event["action_id"] == "set_rival"
        }
        self.assertEqual({"BUR": True, "ENG": True, "HAB": True, "CAS": True,
                          "SAV": False, "GEN": False, "LAN": False},
                         candidate_by_recipient)

    def test_schema2_legality_aggregates_independent_native_failures(self):
        schema2 = self._schema2_events()["set_rival"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = self._installation(root, ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            result = self._run_query(session, "set_rival", {
                **schema2,
                "native_command_validity": False,
                "rival_active": True,
                "rival_count": 3,
                "max_rivals": 3,
                "candidate_eligible": False,
                "target_exists": True,
                "ui_war_allowed": False,
                "native_diagnostic_hex": "6f6b",
            })
        self.assertEqual("unavailable", result["legality"]["status"])
        self.assertFalse(result["legality"]["complete"])
        codes = {item["code"] for item in result["legality"]["reasons"]}
        self.assertTrue({
            "NATIVE_RIVAL_COMMAND_VALIDITY_FALSE",
            "NATIVE_RIVAL_CANDIDATE_INELIGIBLE",
            "NATIVE_RIVAL_WAR_GATE_FALSE",
            "NATIVE_RIVAL_SLOTS_FULL",
            "NATIVE_RIVAL_ALREADY_ACTIVE",
            "NATIVE_RIVAL_DIAGNOSTIC",
        }.issubset(codes))
        diagnostic = next(item for item in result["legality"]["reasons"]
                          if item["code"] == "NATIVE_RIVAL_DIAGNOSTIC")
        self.assertEqual("ok", diagnostic["text"])

    def test_final_power_cost_is_bound_to_remove_with_verified_diplomatic_power_scale(self):
        event = {**self._schema2_events()["remove_rival"],
                 "cost_query_called": True, "diplomatic_power_cost_raw": 100,
                 "diplomatic_power_raw": 162}
        self.assertTrue(ObserverSession._valid_native_rival_inspection(
            event, "remove_rival", event["actor"], event["recipient"],
            event["phase"], event["date_raw"]))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = self._installation(root, ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            result = self._run_query(session, "remove_rival", event)
        item = result["costs"]["items"][0]
        self.assertEqual(100, item["amount_raw"])
        self.assertEqual(100, item["amount"])
        self.assertTrue(item["affordable"])
        self.assertEqual("diplomatic_power", item["unit"])
        self.assertTrue(item["unit_verified"])
        self.assertEqual(1, item["scale"])
        self.assertTrue(item["scale_verified"])
        self.assertEqual("native_rule_and_execution_consequence", item["source"])
        self.assertTrue(item["complete"])
        self.assertEqual("available", result["costs"]["status"])
        self.assertFalse(result["costs"]["complete"])
        self.assertEqual("unknown", result["costs"]["coverage"]["additional_costs"])
        for override in ({"cost_query_called": "true"},
                         {"diplomatic_power_cost_raw": True},
                         {"diplomatic_power_cost_raw": -1},
                         {"cost_query_called": False},
                         {"action_id": "set_rival"}):
            invalid = {**event, **override}
            self.assertFalse(ObserverSession._valid_native_rival_inspection(
                invalid, invalid["action_id"], invalid["actor"], invalid["recipient"],
                invalid["phase"], invalid["date_raw"]))

    def test_real_peace_queries_preserve_final_cost_and_nonmember_predicate(self):
        fixture = Path(__file__).parent / "fixtures" / "rival_r34d_real_native_inspections.json"
        observations = json.loads(fixture.read_text(encoding="utf-8"))["events"]
        self.assertEqual(8, len(observations))
        for record in observations:
            event = record["event"]
            self.assertTrue(ObserverSession._valid_native_rival_inspection(
                event, event["action_id"], "FRA", event["recipient"], "initiate",
                56462016, event["query_id"], event["session_id"]))
            native = ObserverSession._semantic_rival_inspection(event, "eu4_escape")
            self.assertFalse(native["at_war"])
            self.assertEqual(143, native["diplomatic_power_raw"])
            if event["action_id"] == "remove_rival":
                self.assertTrue(native["cost_query_called"])
                self.assertEqual(101, native["costs"]["items"][0]["amount_raw"])
                self.assertEqual(101, native["costs"]["items"][0]["amount"])
                self.assertTrue(native["costs"]["items"][0]["affordable"])
                self.assertEqual(1, native["costs"]["items"][0]["scale"])
                self.assertTrue(native["costs"]["items"][0]["scale_verified"])
                if event["recipient"] in ("BUR", "SAV"):
                    self.assertTrue(native["native_command_validity"])
                    self.assertFalse(native["rival_active"])
                else:
                    self.assertFalse(native["native_command_validity"])
                    self.assertIn("1449", native["native_diagnostic_text"])
            else:
                self.assertFalse(native["cost_query_called"])
                self.assertIsNone(native["diplomatic_power_cost_raw"])

    def test_schema3_full_rules_and_action_availability_are_projected_literally(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" /
                              "rival_r35_execution.json").read_text(encoding="utf-8"))
        event = fixture["schema3"]
        self.assertTrue(ObserverSession._valid_native_rival_inspection(
            event, "set_rival", "FRA", "SAV", "initiate", 1,
            "inspect_r35_set", "rival-session"))
        semantic = ObserverSession._semantic_rival_inspection(event)
        self.assertEqual(3, semantic["rules_schema"])
        self.assertTrue(semantic["full_rules_complete"])
        self.assertTrue(semantic["native_action_available"])
        self.assertTrue(semantic["native_rule_components"]["complete"])
        unavailable = {**event, "native_action_available": False}
        self.assertTrue(ObserverSession._valid_native_rival_inspection(
            unavailable, "set_rival", "FRA", "SAV", "initiate", 1,
            "inspect_r35_set", "rival-session"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = self._installation(root, ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            api_result = self._run_query(session, "set_rival", event)
            self.assertEqual("available", api_result["legality"]["status"])
            self.assertTrue(api_result["legality"]["complete"])
            self.assertTrue(api_result["native_action_available"])

    def test_rival_submission_support_is_separate_from_target_legality(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" /
                              "rival_r34_f_set_execution.json").read_text(
                                  encoding="utf-8"))
        after = fixture["inspections"]["after"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, _ = self._installation(
                root, ack=True, submission_ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            result = self._run_query(
                session, "set_rival", after, recipient="BUR",
                date_raw=after["date_raw"])
        self.assertEqual("unavailable", result["legality"]["status"])
        self.assertFalse(result["legality"]["complete"])
        self.assertEqual("native_rival_submission",
                         result["interface_support"]["execute"])
        self.assertEqual("available", result["authorization"]["status"])
        self.assertTrue(result["authorization"]["complete"])
        self.assertEqual("NATIVE_RIVAL_SUBMISSION_CAPABILITY_ACKNOWLEDGED",
                         result["authorization"]["reasons"][0]["code"])

    def test_rival_submission_receipt_uses_exact_family_and_hides_headers(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" /
                              "rival_r35_execution.json").read_text(encoding="utf-8"))
        event = fixture["submission"]
        self.assertTrue(ObserverSession._valid_native_rival_submission_result(
            event, "r35-set-001", "rival-session", "FRA", "SAV", "initiate", 1,
            "set_rival"))
        public = ObserverSession._public_native_rival_submission_receipt(
            event, "r35-set-001", "FRA", "SAV", "initiate", 1, "set_rival")
        self.assertEqual("rival", public["family"])
        self.assertNotIn("native_origin", public)
        self.assertNotIn("native_flags", public)
        self.assertNotIn("native_sequence", public)
        self.assertNotIn("flags", public)
        self.assertNotIn("sequence", public)
        self.assertFalse(ObserverSession._valid_native_rival_submission_result(
            {**event, "family": "guarantee"}, "r35-set-001", "rival-session",
            "FRA", "SAV", "initiate", 1, "set_rival"))
        self.assertFalse(ObserverSession._valid_native_rival_submission_result(
            event, "r35-set-001", "other-session", "FRA", "SAV", "initiate", 1,
            "set_rival"))
        legacy_names = {key: event[key] for key in ("flags", "sequence")
                        if key in event}
        legacy_event = {key: value for key, value in event.items()
                        if key not in ("native_flags", "native_sequence")}
        legacy_event.update(legacy_names)
        self.assertFalse(ObserverSession._valid_native_rival_submission_result(
            legacy_event, "r35-set-001", "rival-session", "FRA", "SAV",
            "initiate", 1, "set_rival"))

    def test_rival_execution_result_enforces_transition_and_cost(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" /
                              "rival_r35_execution.json").read_text(encoding="utf-8"))
        event = fixture["execution_set"]
        result = ObserverSession._public_native_rival_execution_result(
            event, "r35-set-001", "rival-session", "FRA", "SAV", "initiate", 1,
            "set_rival")
        self.assertEqual("executed", result["status"])
        remove = ObserverSession._public_native_rival_execution_result(
            fixture["execution_remove"], "r35-remove-001", "rival-session",
            "FRA", "SAV", "initiate", 1, "remove_rival")
        self.assertEqual(20, remove["cost_raw"])
        self.assertIsNone(ObserverSession._public_native_rival_execution_result(
            {**event, "cost_raw": 1}, "r35-set-001", "rival-session",
            "FRA", "SAV", "initiate", 1, "set_rival"))
        self.assertIsNone(ObserverSession._public_native_rival_execution_result(
            {**remove, "family": "alliance"}, "r35-remove-001", "rival-session",
            "FRA", "SAV", "initiate", 1, "remove_rival"))

    def test_r34f_actual_native_fields_and_remove_result_are_accepted(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" /
                              "rival_r34_f_remove_execution.json").read_text(
                                  encoding="utf-8"))
        submission = fixture["submission"]
        execution = fixture["execution"]
        self.assertTrue(ObserverSession._valid_native_rival_submission_result(
            submission, "r34f_remove_cas_001", submission["session_id"],
            "FRA", "CAS", "initiate", 56500920, "remove_rival"))
        receipt = ObserverSession._public_native_rival_submission_receipt(
            submission, "r34f_remove_cas_001", "FRA", "CAS", "initiate",
            56500920, "remove_rival")
        self.assertEqual(5106, submission["native_origin"])
        self.assertEqual(0, submission["native_flags"])
        self.assertEqual(15, submission["native_sequence"])
        self.assertNotIn("native_flags", receipt)
        self.assertNotIn("native_sequence", receipt)
        result = ObserverSession._public_native_rival_execution_result(
            execution, "r34f_remove_cas_001", execution["session_id"],
            "FRA", "CAS", "initiate", 56500920, "remove_rival")
        self.assertEqual("executed", result["status"])
        self.assertEqual(101, result["cost_raw"])
        self.assertEqual(3, result["rival_count_before"])
        self.assertEqual(2, result["rival_count_after"])

        set_fixture = json.loads((Path(__file__).parent / "fixtures" /
                                  "rival_r34_f_set_execution.json").read_text(
                                      encoding="utf-8"))
        set_submission = set_fixture["submission"]
        set_execution = set_fixture["execution"]
        self.assertTrue(ObserverSession._valid_native_rival_submission_result(
            set_submission, "r34f_set_bur_001", set_submission["session_id"],
            "FRA", "BUR", "initiate", 56500920, "set_rival"))
        set_result = ObserverSession._public_native_rival_execution_result(
            set_execution, "r34f_set_bur_001", set_execution["session_id"],
            "FRA", "BUR", "initiate", 56500920, "set_rival")
        self.assertEqual("executed", set_result["status"])
        self.assertEqual(0, set_result["cost_raw"])
        self.assertEqual(480, set_result["dip_before"])
        self.assertEqual(480, set_result["dip_after"])
        self.assertEqual(2, set_result["rival_count_before"])
        self.assertEqual(3, set_result["rival_count_after"])

    def test_rival_invalidated_submission_reconciles_only_with_verified_execution(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" /
                              "rival_r34_f_remove_execution.json").read_text(
                                  encoding="utf-8"))
        submission = fixture["submission"]
        execution = fixture["execution"]
        request_id = "r34f_remove_cas_001"
        payload = {"action_id": "remove_rival", "actor": "FRA",
                   "recipient": "CAS", "phase": "initiate", "parameters": {}}
        self.journal.register(request_id, payload)
        for status in ("queued", "consumed", "constructed"):
            self.journal.transition(request_id, status, result={})
        claim = self.journal.claim_submission(
            request_id, submission_id="native_r34f_remove_cas_001")
        self.journal.transition(
            request_id, "invalidated",
            result={"submitted": False, "reason": {
                "code": "NATIVE_RIVAL_SUBMISSION_RESULT_INVALID"}},
            evidence_type="native_submission_failure",
            evidence_content={"submitted": False},
            arrival_layer="bridge_validation",
            event_id="native-submit-failure:r34f_remove_cas_001",
        )
        receipt = ObserverSession._public_native_rival_submission_receipt(
            submission, request_id, "FRA", "CAS", "initiate", 56500920,
            "remove_rival")
        result = ObserverSession._public_native_rival_execution_result(
            execution, request_id, execution["session_id"], "FRA", "CAS",
            "initiate", 56500920, "remove_rival")
        reconciled = self.journal.reconcile_executed(
            request_id, result, receipt,
            expected_reason_code="NATIVE_RIVAL_SUBMISSION_RESULT_INVALID",
            expected_payload=payload,
            evidence_content={"source_fixture": "rival_r34_f_remove_execution.json"},
            event_id="native-rival-reconcile:r34f_remove_cas_001",
        )
        self.assertEqual("executed", reconciled.status)
        evidence = self.journal.list_evidence_for_record(reconciled)
        self.assertEqual(2, len(evidence))
        self.assertEqual("native_rival_reconciliation", evidence[-1].evidence_type)
        repeated = self.journal.reconcile_executed(
            request_id, result, receipt,
            expected_reason_code="NATIVE_RIVAL_SUBMISSION_RESULT_INVALID",
            expected_payload=payload,
            evidence_content={"source_fixture": "rival_r34_f_remove_execution.json"},
            event_id="native-rival-reconcile:r34f_remove_cas_001",
        )
        self.assertEqual("executed", repeated.status)
        self.assertEqual(2, len(self.journal.list_evidence_for_record(repeated)))

    def test_rival_submit_wire_requires_exact_ack_and_is_idempotent_at_journal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, log = self._installation(
                root, ack=True, submission_ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            self.assertIn("native_rival_submission", session.installation_capabilities())
            # No receipt is written by this test; the writer observes the
            # independent channel and closes it, so the adapter times out
            # without inventing a submission.
            request = root / "rival-execute.req"

            def consume_wire() -> None:
                deadline = time.monotonic() + 1
                while not request.exists() and time.monotonic() < deadline:
                    time.sleep(0.001)
                if request.exists():
                    fields = request.read_text(encoding="ascii").strip().split()
                    self.assertEqual("RIVAL_EXEC1", fields[0])
                    self.assertEqual("set_rival", fields[5])
                    self.assertEqual(["FRA", "SAV"], fields[6:8])
                    request.unlink(missing_ok=True)

            thread = threading.Thread(target=consume_wire)
            thread.start()
            result = session.submit_set_rival(
                "r35-wire-001", "FRA", "SAV", "initiate", 1, timeout=0.05)
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual("timeout", result["status"])
            self.assertEqual(1, len(log.read_text(encoding="utf-8").splitlines()))

    def test_rival_execution_result_recovers_from_journal_without_resubmission(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" /
                              "rival_r35_execution.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, log = self._installation(
                root, ack=True, submission_ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            payload = {"action_id": "set_rival", "actor": "FRA",
                       "recipient": "SAV", "phase": "initiate", "parameters": {}}
            self.journal.register("r35-set-001", payload)
            for status in ("queued", "consumed", "constructed"):
                self.journal.transition("r35-set-001", status, result={})
            claim = self.journal.claim_submission(
                "r35-set-001", submission_id="native_r35-set-001")
            receipt = ObserverSession._public_native_rival_submission_receipt(
                fixture["submission"], "r35-set-001", "FRA", "SAV", "initiate", 1,
                "set_rival")
            self.journal.mark_submitted("r35-set-001", claim.claim_token, receipt)
            event = {**fixture["execution_set"], "session_id": session.session_id}
            with log.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(event) + "\n")
            api = DiplomacyTools(self.journal, session)
            result = api.get_diplomatic_result("r35-set-001")
            self.assertEqual("executed", result["status"])
            self.assertEqual("executed", result["result"]["status"])
            self.assertNotIn("native_origin", json.dumps(result, ensure_ascii=False))
            again = api.get_diplomatic_result("r35-set-001")
            self.assertEqual("executed", again["status"])
            duplicate = api.execute_diplomatic_action(
                "r35-set-001", "set_rival", "FRA", "SAV")
            self.assertTrue(duplicate["idempotent"])
            self.assertEqual("executed", duplicate["status"])

    def test_rival_execution_stays_unsupported_and_does_not_submit(self):
        api = DiplomacyTools(self.journal)
        result = api.execute_diplomatic_action("rival-unimplemented", "set_rival",
                                               "FRA", "SAV")
        self.assertEqual("invalidated", result["status"])
        self.assertFalse(result["submitted"])
        self.assertEqual("EXECUTION_ADAPTER_UNIMPLEMENTED",
                         result["result"]["reason"]["code"])
        self.assertEqual({}, self.journal.get_request(
            "rival-unimplemented").payload["parameters"])


if __name__ == "__main__":
    unittest.main()
