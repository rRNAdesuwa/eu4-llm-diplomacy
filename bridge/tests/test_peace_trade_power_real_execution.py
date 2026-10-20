import hashlib
import json
import copy
import unittest
from pathlib import Path

from bridge.diplomacy import DiplomacyTools, DurableJournal, ObserverSession


FIXTURE = (Path(__file__).parent / "fixtures" /
           "peace_trade_power_r50_real_execution.json")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PeaceTradePowerR50RealExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def _check_optional_source_file(self, source: dict, path_key: str,
                                    size_key: str, sha_key: str):
        """Verify captured provenance when the runtime artifact is present.

        The fixture remains portable when the large work/runtime evidence tree
        is omitted from a checkout; the embedded event and line digests still
        provide its provenance in that case.
        """
        path = REPOSITORY_ROOT / source[path_key]
        if path.exists():
            self.assertEqual(source[size_key], path.stat().st_size)
            self.assertEqual(source[sha_key], _sha256(path))

    def _check_optional_event_line(self, source: dict, record: dict):
        path = REPOSITORY_ROOT / source["native_events_path"]
        if not path.exists():
            return
        lines = path.read_bytes().splitlines()
        line_no = record["source_line"]
        self.assertGreaterEqual(line_no, 1)
        raw = lines[line_no - 1]
        self.assertEqual(record["source_line_sha256"],
                         hashlib.sha256(raw).hexdigest())
        self.assertEqual(record["event"], json.loads(raw.decode("utf-8")))

    def test_fixture_records_real_a_provenance_and_build_identity(self):
        self.assertEqual(1, self.fixture["fixture_version"])
        sources = self.fixture["sources"]
        self.assertEqual({"a", "c", "d", "e"}, set(sources))
        for name in ("a", "c", "d", "e"):
            source = sources[name]
            for key in ("runtime_artifact", "build_manifest_path",
                        "build_manifest_sha256", "dll_sha256",
                        "build_manifest_dll_sha256",
                        "installation_dll_sha256", "session_id"):
                self.assertTrue(source.get(key), (name, key))
            for key in ("build_manifest_sha256", "dll_sha256",
                        "build_manifest_dll_sha256",
                        "installation_dll_sha256"):
                self.assertRegex(source[key], r"^[0-9a-f]{64}$")
            self.assertEqual(source["dll_sha256"],
                             source["build_manifest_dll_sha256"])
            self.assertEqual(source["dll_sha256"],
                             source["installation_dll_sha256"])

        a = sources["a"]
        self._check_optional_source_file(
            a, "report_path", "report_size", "report_sha256")
        self._check_optional_source_file(
            a, "native_events_path", "native_events_size",
            "native_events_sha256")
        self._check_optional_source_file(
            a, "selected_inspection_path", "selected_inspection_size",
            "selected_inspection_sha256")
        self._check_optional_source_file(
            a, "build_manifest_path", "build_manifest_size",
            "build_manifest_sha256")
        self._check_optional_source_file(
            a, "installation_path", "installation_size",
            "installation_sha256")

        for name in ("d", "e"):
            source = sources[name]
            for path_key, size_key, sha_key in (
                    ("report_path", "report_size", "report_sha256"),
                    ("native_events_path", "native_events_size",
                     "native_events_sha256"),
                    ("build_manifest_path", "build_manifest_size",
                     "build_manifest_sha256"),
                    ("installation_path", "installation_size",
                     "installation_sha256"),
                    ("save_observer_report_path",
                     "save_observer_report_size",
                     "save_observer_report_sha256")):
                self._check_optional_source_file(
                    source, path_key, size_key, sha_key)

        request = self.fixture["request"]
        self.assertEqual("transfer_trade_power", request["action_id"])
        self.assertEqual("offer", request["parameters"]["peace_context"][
            "direction"])
        term = request["parameters"]["peace_context"]["terms"][0]
        self.assertEqual({"action_id", "source", "beneficiary"},
                         set(term))
        self.assertEqual("FRA", term["source"])
        self.assertEqual("ENG", term["beneficiary"])

    def test_a_real_t_submission_and_rejected_execution_replay(self):
        request = self.fixture["request"]
        parameters = request["parameters"]
        submission_record = self.fixture["submission_event"]
        execution_record = self.fixture["execution_event"]
        self._check_optional_event_line(self.fixture["sources"]["a"],
                                        submission_record)
        self._check_optional_event_line(self.fixture["sources"]["a"],
                                        execution_record)

        submission = submission_record["event"]
        self.assertTrue(ObserverSession._valid_native_peace_submission_result(
            submission, request["request_id"], request["session_id"],
            request["actor"], request["recipient"], request["phase"],
            request["date_raw"], request["action_id"], parameters))
        public_submission = ObserverSession._public_native_peace_submission_receipt(
            submission, request["request_id"], request["actor"],
            request["recipient"], request["phase"], request["date_raw"],
            request["action_id"], parameters)
        self.assertEqual(self.fixture["public_submission"], public_submission)
        self.assertEqual("t", public_submission["term_mask"])
        self.assertEqual("FRA", public_submission["trade_power_source"])
        self.assertEqual("ENG", public_submission["trade_power_beneficiary"])
        self.assertIsNone(public_submission["beneficiary"])
        self.assertNotIn("native_origin", public_submission)
        self.assertNotIn("native_flags", public_submission)
        self.assertNotIn("native_sequence", public_submission)

        execution = execution_record["event"]
        self.assertTrue(ObserverSession._valid_native_peace_execution_result(
            execution, request["request_id"], request["session_id"],
            request["actor"], request["recipient"], request["phase"],
            request["date_raw"], request["action_id"], parameters))
        public = ObserverSession._public_native_peace_execution_result(
            execution, request["request_id"], request["session_id"],
            request["actor"], request["recipient"], request["phase"],
            request["date_raw"], request["action_id"], parameters)
        self.assertEqual(self.fixture["public_result"], public)
        self.assertIsNotNone(public)
        self.assertEqual("t", public["term_mask"])
        self.assertEqual("FRA", public["trade_power_source"])
        self.assertEqual("ENG", public["trade_power_beneficiary"])
        self.assertEqual("rejected", public["native_outcome"])
        self.assertEqual(1, public["native_state"])
        self.assertFalse(public["execution_verified"])
        self.assertFalse(public["terms_verified"])
        self.assertTrue(public["war_before"])
        self.assertTrue(public["war_after"])

        effects = public["effects"]
        self.assertIsNone(effects["war_reparations"])
        self.assertEqual({
            "source", "beneficiary", "present_before", "present_after",
            "start_date_raw", "end_date_raw", "amount_raw", "amount_scale",
            "peace_treaty", "verified",
        }, set(effects["transfer_trade_power"]))
        self.assertEqual({
            "source": "FRA", "beneficiary": "ENG",
            "present_before": False, "present_after": False,
            "start_date_raw": 0, "end_date_raw": 0,
            "amount_raw": 0, "amount_scale": 1000,
            "peace_treaty": False, "verified": False,
        }, effects["transfer_trade_power"])

        public_text = json.dumps(public, ensure_ascii=False)
        self.assertNotIn("session_id", public_text)
        self.assertNotIn("native_origin", public_text)
        self.assertNotIn("frame_thread", public_text)

        # The recorded A report says this was one submitted business request;
        # no accepted/replayed outcome is inferred from the rejection.
        contract = self.fixture["report_contract"]
        self.assertTrue(contract["business_submission"])
        self.assertEqual(1, contract["business_submission_count"])
        self.assertTrue(contract["business_transport_submitted"])
        self.assertEqual("rejected", contract["submission_status"])
        self.assertEqual("rejected", contract["game_outcome"])
        self.assertTrue(contract["native_result_contract_all"])
        self.assertTrue(contract["effects_contract_all"])

    def test_a_roles_and_mask_are_bound_by_both_native_result_validators(self):
        request = self.fixture["request"]
        parameters = request["parameters"]
        submission = self.fixture["submission_event"]["event"]
        execution = self.fixture["execution_event"]["event"]
        for field, value in (("term_mask", "r"),
                             ("trade_power_source", "ENG"),
                             ("trade_power_beneficiary", "FRA")):
            with self.subTest(result="submission", field=field):
                invalid = dict(submission, **{field: value})
                self.assertFalse(
                    ObserverSession._valid_native_peace_submission_result(
                        invalid, request["request_id"], request["session_id"],
                        request["actor"], request["recipient"],
                        request["phase"], request["date_raw"],
                        request["action_id"], parameters))
            with self.subTest(result="execution", field=field):
                invalid = dict(execution, **{field: value})
                self.assertFalse(
                    ObserverSession._valid_native_peace_execution_result(
                        invalid, request["request_id"], request["session_id"],
                        request["actor"], request["recipient"],
                        request["phase"], request["date_raw"],
                        request["action_id"], parameters))

    def test_c_real_pending_and_accept_reject_inspections_preserve_t_roles(self):
        source = self.fixture["sources"]["c"]
        self._check_optional_source_file(
            source, "list_result_path", "list_result_size",
            "list_result_sha256")
        self._check_optional_source_file(
            source, "native_events_path", "native_events_size",
            "native_events_sha256")
        for phase in ("accept", "reject"):
            result = self.fixture["inbound_public_results"][phase]
            self._check_optional_source_file(
                source, f"{phase}_result_path", f"{phase}_result_size",
                f"{phase}_result_sha256")
            self.assertEqual(phase, result["phase"])
            self.assertEqual("available", result["legality_status"])
            self.assertEqual("available", result["authorization_status"])
            # The captured C result predates the projection fix, so retain its
            # historical false value while the replay below verifies true for
            # the same complete pending inspection.
            self.assertEqual({"proposal_id"},
                             set(result["requested_parameters"]))
            self.assertEqual({
                "proposal_id", "decision_country", "original_actor",
                "original_recipient", "peace_context",
            }, set(result["actual_parameter_keys"]))
            self.assertFalse(result["parameters_complete"])
            self.assertTrue(result["actual_context_complete"])
            self.assertTrue(result["actual_selected_terms_complete"])

        pending = self.fixture["inbound_pending"]["proposal"]
        self.assertEqual("observed_pending", pending["observer_status"])
        self.assertEqual("ENG", pending["actor"])
        self.assertEqual("FRA", pending["recipient"])
        self.assertIsNone(pending["currently_pending"])
        self.assertEqual("native_inbound_response", pending["execute"]["accept"])
        self.assertEqual("native_inbound_response", pending["execute"]["reject"])

        inspections = self.fixture["inbound_inspections"]
        self.assertEqual({"accept", "reject"},
                         {item["event"]["phase"] for item in inspections})
        for record in inspections:
            event = record["event"]
            self._check_optional_event_line(source, record)
            self.assertTrue(ObserverSession._valid_native_inbound_inspection(
                event, event["query_id"], event["session_id"],
                event["actor"], event["phase"],
                event["native_proposal_id"], event["date_raw"],
                "peace_offer"))
            public = ObserverSession._public_native_inbound_inspection(
                event, event["date_raw"], "peace_offer")
            self.assertEqual("available",
                             self.fixture["inbound_public_results"][
                                 event["phase"]]["legality_status"])
            self.assertEqual("ENG", public["actor"])
            self.assertEqual("FRA", public["recipient"])
            context = public["peace_context"]
            self.assertTrue(context["complete"])
            self.assertTrue(context["selected_terms_complete"])
            self.assertEqual("demand", context["direction"])
            self.assertEqual("ENG", context["original_actor"])
            self.assertEqual("FRA", context["original_recipient"])
            self.assertEqual(1, len(context["terms"]))
            self.assertEqual({
                "action_id": "transfer_trade_power",
                "source": "FRA", "beneficiary": "ENG",
            }, context["terms"][0])
            self.assertNotIn("native_proposal_id", public)
            self.assertNotIn("query_id", public)
            self.assertNotIn("session_id", public)

    def test_d_reject_and_e_accept_real_inbound_execution_replay(self):
        expected = {
            "d_reject": {
                "phase": "reject", "native_state": 1,
                "native_outcome": "rejected", "war_after": True,
                "terms_verified": False, "amount_raw": 0,
                "present_after": False, "peace_treaty": False,
            },
            "e_accept": {
                "phase": "accept", "native_state": 2,
                "native_outcome": "accepted", "war_after": False,
                "terms_verified": True, "amount_raw": 500,
                "present_after": True, "peace_treaty": True,
            },
        }
        for name, wanted in expected.items():
            with self.subTest(execution=name):
                execution = self.fixture["inbound_executions"][name]
                source = self.fixture["sources"][execution["source"]]
                for path_key, size_key, sha_key in (
                        ("report_path", "report_size", "report_sha256"),
                        ("native_events_path", "native_events_size",
                         "native_events_sha256"),
                        ("build_manifest_path", "build_manifest_size",
                         "build_manifest_sha256"),
                        ("installation_path", "installation_size",
                         "installation_sha256"),
                        ("save_observer_report_path",
                         "save_observer_report_size",
                         "save_observer_report_sha256")):
                    self._check_optional_source_file(
                        source, path_key, size_key, sha_key)

                submission_record = execution["submission_event"]
                response_record = execution["response_event"]
                self._check_optional_event_line(source, submission_record)
                self._check_optional_event_line(source, response_record)
                submission = submission_record["event"]
                response = response_record["event"]
                request_id = execution["request_id"]
                session_id = source["session_id"]
                proposal_id = execution["native_proposal_id"]
                self.assertTrue(
                    ObserverSession._valid_native_inbound_submission_result(
                        submission, request_id, session_id, "ENG", "FRA",
                        wanted["phase"], response["date_raw"], proposal_id,
                        "peace_offer"))
                public_submission = (
                    ObserverSession._public_native_inbound_submission_receipt(
                        submission, request_id, "ENG", wanted["phase"],
                        response["date_raw"], "peace_offer"))
                self.assertEqual(execution["public_submission"],
                                 public_submission)
                self.assertEqual("FRA", public_submission["decision_country"])
                self.assertNotIn("session_id", public_submission)

                public_result = ObserverSession._public_native_inbound_response_result(
                    response, request_id, session_id, "ENG", wanted["phase"],
                    response["date_raw"], proposal_id, "peace_offer")
                self.assertIsNotNone(public_result)
                self.assertEqual(execution["public_result"], public_result)
                self.assertEqual(wanted["native_state"],
                                 public_result["native_state"])
                self.assertEqual(wanted["native_outcome"],
                                 public_result["native_outcome"])
                self.assertTrue(public_result["response_verified"])
                self.assertTrue(public_result["request_binding_verified"])
                self.assertTrue(public_result["pending_removed"])
                self.assertTrue(public_result["war_before"])
                self.assertEqual(wanted["war_after"],
                                 public_result["war_after"])
                self.assertEqual(wanted["terms_verified"],
                                 public_result["terms_verified"])
                context = public_result["peace_context"]
                self.assertTrue(context["complete"])
                self.assertTrue(context["selected_terms_complete"])
                self.assertEqual({
                    "action_id": "transfer_trade_power",
                    "source": "FRA", "beneficiary": "ENG",
                }, context["terms"][0])
                effects = public_result["effects"]
                self.assertIsNone(effects["war_reparations"])
                trade_power = effects["transfer_trade_power"]
                self.assertEqual("FRA", trade_power["source"])
                self.assertEqual("ENG", trade_power["beneficiary"])
                self.assertEqual(wanted["amount_raw"],
                                 trade_power["amount_raw"])
                self.assertEqual(1000, trade_power["amount_scale"])
                self.assertEqual(wanted["present_after"],
                                 trade_power["present_after"])
                self.assertEqual(wanted["peace_treaty"],
                                 trade_power["peace_treaty"])
                self.assertTrue(effects["complete"])

                projection = execution["inspection_projection"]
                self.assertTrue(projection["parameters_complete"])
                self.assertEqual({"proposal_id"},
                                 set(projection["requested_parameters"]))
                self.assertEqual("FRA", projection["decision_country"])
                self.assertTrue(projection["decision_country_verified"])
                self.assertTrue(projection["pending_active"])
                self.assertTrue(projection["peace_context_complete"])
                self.assertTrue(projection["selected_terms_complete"])
                contract = execution["report_contract"]
                self.assertEqual(1, contract["execute_call_count"])
                self.assertEqual(1, contract["request_publish_count"])
                self.assertTrue(all(contract["checks"].values()))

    def _replay_c_inbound_parameter_projection(self, event, phase,
                                               *, public_id=None,
                                               native_event=True):
        pending = self.fixture["inbound_pending"]["proposal"]
        proposal_id = (pending["proposal_id"] if public_id is None
                       else public_id)
        source = self.fixture["sources"]["c"]
        session_id = source["session_id"]

        class FixtureSession:
            def health(self):
                return {"status": "ready", "state_id": "r50c",
                        "date_raw": 56545056, "reasons": [],
                        "complete": True}

            def installation_capabilities(self):
                return frozenset({"native_inbound_alliance",
                                  "native_inbound_peace_response"})

            def read_native_alliance_inbound_offers(self):
                return [copy.deepcopy(pending)]

            def _native_alliance_inbound_context(self, candidate):
                if candidate != pending["proposal_id"]:
                    return None
                return {"actor": "ENG", "recipient": "FRA",
                        "native_proposal_id": 1,
                        "session_id": session_id,
                        "action_id": "peace_offer", "family": "peace"}

            def inspect_native_inbound_response(
                    self, query_id, actor, requested_phase, date_raw,
                    native_proposal_id, action_id="offer_alliance"):
                if not native_event:
                    return {"error_code": "QUERY_NATIVE_RESULT_INVALID"}
                return copy.deepcopy(event)

        FixtureSession.session_id = session_id
        journal = DurableJournal(":memory:", "r50c-parameter-replay",
                                 session_id)
        try:
            return DiplomacyTools(journal, FixtureSession()).inspect_diplomatic_action(
                "peace_offer", "ENG", "FRA", phase,
                {"proposal_id": proposal_id})
        finally:
            journal.close()

    def test_c_native_pending_replay_sets_outer_parameters_complete(self):
        for record in self.fixture["inbound_inspections"]:
            phase = record["event"]["phase"]
            with self.subTest(phase=phase):
                inspection = self._replay_c_inbound_parameter_projection(
                    record["event"], phase)
                self.assertTrue(inspection["parameters"]["complete"])
                self.assertEqual(
                    inspection["parameters"]["actual"]["proposal_id"],
                    self.fixture["inbound_pending"]["proposal"]["proposal_id"])
                self.assertTrue(inspection["peace_context"]["complete"])
                self.assertTrue(
                    inspection["peace_context"]["selected_terms_complete"])
                self.assertEqual("FRA", inspection["decision_country"])
                self.assertTrue(inspection["decision_country_verified"])
                self.assertTrue(inspection["observed_inbound_proposal"][
                    "currently_pending"])
                self.assertTrue(self.fixture["inbound_public_results"][phase][
                    "replay_parameters_complete"])
                # The source result was captured before this projection fix;
                # keep that historical false value untouched in the fixture.
                self.assertFalse(self.fixture["inbound_public_results"][phase][
                    "parameters_complete"])

    def test_c_incomplete_or_unbound_inbound_projection_stays_incomplete(self):
        event = self.fixture["inbound_inspections"][0]["event"]
        incomplete = copy.deepcopy(event)
        incomplete["peace_context"]["selected_terms_complete"] = False
        result = self._replay_c_inbound_parameter_projection(
            incomplete, "accept")
        self.assertFalse(result["parameters"]["complete"])

        native_payload_incomplete = copy.deepcopy(event)
        native_payload_incomplete["selected_terms_complete"] = False
        result = self._replay_c_inbound_parameter_projection(
            native_payload_incomplete, "accept")
        self.assertFalse(result["parameters"]["complete"])

        unmatched = self._replay_c_inbound_parameter_projection(
            event, "accept", public_id="0" * 32)
        self.assertFalse(unmatched["parameters"]["complete"])

        unknown = self._replay_c_inbound_parameter_projection(
            event, "accept", native_event=False)
        self.assertFalse(unknown["parameters"]["complete"])


if __name__ == "__main__":
    unittest.main()
