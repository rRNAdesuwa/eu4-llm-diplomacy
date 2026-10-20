from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal


FIXTURE = (Path(__file__).parent / "fixtures" /
           "peace_concede_defeat_r52_real_execution.json")
QUERY_FIXTURE = (Path(__file__).parent / "fixtures" /
                 "peace_concede_defeat_r52_real_queries.json")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


PRIVATE_KEYS = {
    "session_id", "frame_thread", "native_origin", "native_flags",
    "native_sequence", "treasury_before_raw", "treasury_after_raw",
    "private", "query_id", "native_proposal_id", "token3c", "date28",
    "date2c", "envoy30", "native_action", "native_node", "proposal3c",
    "created2c",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _all_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        keys.update(str(key) for key in value)
        for child in value.values():
            keys.update(_all_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_all_keys(child))
    return keys


def _query_selection(event: dict) -> dict:
    """Bind the recorded native selection fields into the production contract."""

    mask = event["term_mask"]
    native_c = event["native_concede_defeat"]
    selection = {
        "action_id": event["action_id"],
        "war_id": event["war_id"],
        "direction": event["direction"],
        "amount_raw": -1,
        "province_ids": [],
        "beneficiary": None,
        "source": "-",
        "trade_power_beneficiary": None,
        "conceding_country": native_c["conceding_country"],
        "concede_beneficiary": native_c["beneficiary"],
        "term_mask": mask,
    }
    if "m" in mask:
        selection["amount_raw"] = event["native_money"]["requested_amount_raw"]
    if "p" in mask:
        selected = [row for row in event["native_provinces"]["candidates"]
                    if row.get("selected") is True]
        selection["province_ids"] = [row["province_id"] for row in selected]
        selection["beneficiary"] = event["native_provinces"][
            "selected_beneficiary"]
    if "r" in mask:
        selection["payer"] = event["native_reparations"]["payer"]
        selection["claimant"] = event["native_reparations"]["claimant"]
    if "t" in mask:
        selection["source"] = event["native_trade_power"]["source"]
        selection["trade_power_beneficiary"] = event[
            "native_trade_power"]["beneficiary"]
    return selection


def _query_parameters(event: dict) -> dict:
    """Build the public normalized terms represented by one real QUERY11 event."""

    mask = event["term_mask"]
    native_c = event["native_concede_defeat"]
    terms: list[dict] = []
    if "m" in mask:
        terms.append({
            "action_id": "demand_ducats",
            "amount": "10.0",
            "payer": native_c["conceding_country"],
            "claimant": native_c["beneficiary"],
        })
    if "p" in mask:
        selected = [row for row in event["native_provinces"]["candidates"]
                    if row.get("selected") is True]
        terms.append({
            "action_id": "cede_province",
            "province_ids": [row["province_id"] for row in selected],
            "beneficiary": event["native_provinces"]["selected_beneficiary"],
        })
    if "r" in mask:
        terms.append({
            "action_id": "war_reparations",
            "payer": event["native_reparations"]["payer"],
            "claimant": event["native_reparations"]["claimant"],
        })
    if "t" in mask:
        terms.append({
            "action_id": "transfer_trade_power",
            "source": event["native_trade_power"]["source"],
            "beneficiary": event["native_trade_power"]["beneficiary"],
        })
    terms.append({
        "action_id": "concede_defeat",
        "conceding_country": native_c["conceding_country"],
        "beneficiary": native_c["beneficiary"],
    })
    return {"peace_context": {
        "war_id": event["war_id"],
        "direction": event["direction"],
        "terms": terms,
    }}


def _replay_inbound_offer(raw_events: list[dict], session_id: str,
                          date_raw: int = 56549088) -> tuple[list[dict], dict]:
    """Replay a bounded native slice through the production inbound reader.

    The temporary control log contains the exact installation ACK shape and
    the recorded native events.  No game process or native probe is started;
    the explicit ready health value is the same one used by the public
    bridge's response adapter.
    """

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        installation = root / "installation.json"
        installation.write_text(json.dumps({
            "experiment_id": "r52-real-replay",
            "session_id": session_id,
            "native_text_codec": "eu4_escape",
        }, separators=(",", ":")), encoding="utf-8")
        ack = {
            "event": "diplomacy_observer_installed",
            "session_id": session_id,
            "native_inbound_alliance": True,
            "native_inbound_peace_response": True,
        }
        lines = [json.dumps(ack, separators=(",", ":"))]
        lines.extend(json.dumps(record["event"], ensure_ascii=False,
                                separators=(",", ":"))
                     for record in raw_events)
        (root / "control-probe.jsonl").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")
        session = ObserverSession(installation, root / "eu4.exe")
        journal = DurableJournal(":memory:", "r52-real-replay", session_id)
        try:
            api = DiplomacyTools(journal, session)
            health = {"status": "ready", "date_raw": date_raw}
            offers = api._read_inbound_proposals(health, recipient="FRA")
            if len(offers) != 1:
                raise AssertionError(
                    f"expected one replayed offer, got {offers!r}")
            context = api._private_inbound_context(
                health, offers[0]["proposal_id"], "peace_offer")
            if context is None:
                raise AssertionError(
                    "replayed offer did not resolve to a private context")
            return offers, context
        finally:
            journal.close()


def _replay_inbound_response(raw_events: list[dict], session_id: str,
                             request_id: str, actor: str = "ENG",
                             phase: str = "accept",
                             date_raw: int = 56549088,
                             native_proposal_id: int = 1) -> dict | None:
    """Consume a recorded response through the production response reader."""

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        installation = root / "installation.json"
        installation.write_text(json.dumps({
            "experiment_id": "r52-real-response-replay",
            "session_id": session_id,
            "native_text_codec": "eu4_escape",
        }, separators=(",", ":")), encoding="utf-8")
        ack = {
            "event": "diplomacy_observer_installed",
            "session_id": session_id,
            "native_inbound_alliance": True,
            "native_inbound_peace_response": True,
        }
        lines = [json.dumps(ack, separators=(",", ":"))]
        lines.extend(json.dumps(record["event"], ensure_ascii=False,
                                separators=(",", ":"))
                     for record in raw_events)
        (root / "control-probe.jsonl").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")
        session = ObserverSession(installation, root / "eu4.exe")
        return session.read_native_peace_inbound_response(
            request_id, actor, "FRA", phase, date_raw, native_proposal_id)


class PeaceConcedeDefeatR52RealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.query_fixture = json.loads(
            QUERY_FIXTURE.read_text(encoding="utf-8"))

    def _check_optional_source_file(self, source: dict, path_key: str,
                                    size_key: str, sha_key: str) -> None:
        """Check captured provenance when the runtime evidence is available."""

        path = REPOSITORY_ROOT / source[path_key]
        if path.exists():
            self.assertEqual(source[size_key], path.stat().st_size)
            self.assertEqual(source[sha_key], _sha256(path))

    def _check_optional_event_line(self, source: dict, record: dict) -> None:
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

    def _check_real_source_metadata(self, source: dict) -> None:
        for key in (
                "runtime_artifact", "experiment_id", "report_path",
                "report_sha256", "native_events_path", "native_events_sha256",
                "build_manifest_path", "build_manifest_sha256",
                "installation_path", "installation_sha256", "dll_sha256",
                "build_manifest_dll_sha256", "installation_dll_sha256",
                "session_id"):
            self.assertTrue(source.get(key), key)
        for key in (
                "report_sha256", "native_events_sha256", "build_manifest_sha256",
                "installation_sha256", "dll_sha256",
                "build_manifest_dll_sha256", "installation_dll_sha256"):
            self.assertRegex(source[key], r"^[0-9a-f]{64}$")
        self.assertEqual(source["dll_sha256"],
                         source["build_manifest_dll_sha256"])
        self.assertEqual(source["dll_sha256"],
                         source["installation_dll_sha256"])
        self._check_optional_source_file(
            source, "report_path", "report_size", "report_sha256")
        self._check_optional_source_file(
            source, "native_events_path", "native_events_size",
            "native_events_sha256")
        self._check_optional_source_file(
            source, "build_manifest_path", "build_manifest_size",
            "build_manifest_sha256")
        self._check_optional_source_file(
            source, "installation_path", "installation_size",
            "installation_sha256")

    def test_fixture_preserves_real_a_provenance_and_raw_private_metadata(self):
        self.assertEqual(1, self.fixture["fixture_version"])
        source = self.fixture["sources"]["a"]
        for key in (
                "runtime_artifact", "report_path", "report_sha256",
                "native_events_path", "native_events_sha256",
                "build_manifest_path", "build_manifest_sha256",
                "installation_path", "installation_sha256", "dll_sha256",
                "build_manifest_dll_sha256", "installation_dll_sha256",
                "session_id"):
            self.assertTrue(source.get(key), key)
        for key in (
                "report_sha256", "native_events_sha256", "build_manifest_sha256",
                "installation_sha256", "dll_sha256",
                "build_manifest_dll_sha256", "installation_dll_sha256"):
            self.assertRegex(source[key], r"^[0-9a-f]{64}$")
        self.assertEqual(source["dll_sha256"],
                         source["build_manifest_dll_sha256"])
        self.assertEqual(source["dll_sha256"],
                         source["installation_dll_sha256"])
        self._check_optional_source_file(source, "report_path", "report_size",
                                         "report_sha256")
        self._check_optional_source_file(
            source, "native_events_path", "native_events_size",
            "native_events_sha256")
        self._check_optional_source_file(
            source, "build_manifest_path", "build_manifest_size",
            "build_manifest_sha256")
        self._check_optional_source_file(
            source, "installation_path", "installation_size",
            "installation_sha256")
        query_source = self.fixture["sources"]["query_fixture"]
        self._check_optional_source_file(query_source, "path", "bytes",
                                         "sha256")

        raw = self.fixture["raw_metadata"]
        self.assertTrue(raw["wire_submission_private"])
        self.assertEqual({"ENG", "FRA"}, {
            row["country"] for row in raw["native_effect_observations"]})
        self.assertTrue(all(row["private"] is True
                            for row in raw["native_effect_observations"]))
        self.assertIn("session_id", raw["wire_submission_event_private_keys"])
        self.assertIn("native_origin", raw["wire_submission_event_private_keys"])

    def test_real_a_rejection_uses_c_validators_and_execution_consumer(self):
        request = self.fixture["request"]
        parameters = request["parameters"]
        source = self.fixture["sources"]["a"]
        submission_record = self.fixture["submission_event"]
        execution_record = self.fixture["execution_event"]
        self._check_optional_event_line(source, submission_record)
        self._check_optional_event_line(source, execution_record)

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
        self.assertEqual(self.fixture["public_submission_consumer"],
                         DiplomacyTools._public_peace_submission_receipt(
                             public_submission, request["request_id"],
                             request["actor"], request["recipient"],
                             request["phase"], request["date_raw"],
                             request["action_id"], parameters))

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
        self.assertEqual("c", public["term_mask"])
        self.assertEqual("ENG", public["conceding_country"])
        self.assertEqual("FRA", public["concede_beneficiary"])
        self.assertEqual("rejected", public["native_outcome"])
        self.assertEqual(1, public["native_state"])
        self.assertFalse(public["execution_verified"])
        self.assertFalse(public["terms_verified"])
        self.assertTrue(public["war_before"])
        self.assertTrue(public["war_after"])

        effects = public["effects"]
        c_effect = effects["concede_defeat"]
        self.assertEqual({
            "conceding_country", "beneficiary",
            "conceding_prestige_before_raw", "conceding_prestige_after_raw",
            "conceding_prestige_delta_raw", "beneficiary_prestige_before_raw",
            "beneficiary_prestige_after_raw", "beneficiary_prestige_delta_raw",
            "prestige_scale", "values_readable", "verified",
        }, set(c_effect))
        self.assertEqual("ENG", c_effect["conceding_country"])
        self.assertEqual("FRA", c_effect["beneficiary"])
        self.assertEqual(62778, c_effect["conceding_prestige_before_raw"])
        self.assertEqual(62778, c_effect["conceding_prestige_after_raw"])
        self.assertEqual(0, c_effect["conceding_prestige_delta_raw"])
        self.assertEqual(-10990, c_effect["beneficiary_prestige_before_raw"])
        self.assertEqual(-10990, c_effect["beneficiary_prestige_after_raw"])
        self.assertEqual(0, c_effect["beneficiary_prestige_delta_raw"])
        self.assertEqual(1000, c_effect["prestige_scale"])
        self.assertTrue(c_effect["values_readable"])
        self.assertFalse(c_effect["verified"])
        self.assertIsNone(effects["money"])
        self.assertIsNone(effects["war_reparations"])

        public_keys = _all_keys(public)
        self.assertTrue(PRIVATE_KEYS.isdisjoint(public_keys))
        public_text = json.dumps(public, ensure_ascii=False)
        self.assertNotIn("treasury_before_raw", public_text)
        self.assertNotIn("treasury_after_raw", public_text)

        contract = self.fixture["report_contract"]
        self.assertTrue(contract["business_submission"])
        self.assertEqual(1, contract["business_submission_count"])
        self.assertTrue(contract["business_transport_submitted"])
        self.assertEqual(1, contract["execute_call_count"])
        self.assertEqual("rejected", contract["submission_status"])
        self.assertEqual("rejected", contract["game_outcome"])
        self.assertTrue(contract["native_result_contract_all"])
        self.assertTrue(contract["effects_contract_all"])

    def test_real_a_roles_and_mask_are_bound_by_both_c_result_validators(self):
        request = self.fixture["request"]
        parameters = request["parameters"]
        submission = self.fixture["submission_event"]["event"]
        execution = self.fixture["execution_event"]["event"]
        for field, value in (
                ("term_mask", "r"),
                ("conceding_country", "FRA"),
                ("concede_beneficiary", "ENG")):
            with self.subTest(result="submission", field=field):
                invalid = dict(submission, **{field: value})
                self.assertFalse(
                    ObserverSession._valid_native_peace_submission_result(
                        invalid, request["request_id"], request["session_id"],
                        request["actor"], request["recipient"], request["phase"],
                        request["date_raw"], request["action_id"], parameters))
            with self.subTest(result="execution", field=field):
                invalid = dict(execution, **{field: value})
                self.assertFalse(
                    ObserverSession._valid_native_peace_execution_result(
                        invalid, request["request_id"], request["session_id"],
                        request["actor"], request["recipient"], request["phase"],
                        request["date_raw"], request["action_id"], parameters))

    def test_real_d_restored_pending_replay_reads_public_offer_and_private_context(self):
        data = self.fixture["inbound_d_restored"]
        source = self.fixture["sources"]["d"]
        self._check_real_source_metadata(source)
        self.assertEqual(6, source["native_events_line_count"])
        self.assertTrue(source["native_events_complete"])
        for record in data["raw_event_slice"]:
            self._check_optional_event_line(source, record)

        restored = data["restored_event"]["event"]
        self.assertTrue(ObserverSession._valid_native_inbound_pending_restored_event(
            restored, data["session_id"]))
        self.assertEqual("native_diplomacy_inbound_pending_restored",
                         restored["event"])
        self.assertEqual("native_saved_pending_queue", restored["pending_source"])
        self.assertFalse(restored["new_entry"])
        self.assertFalse(restored["call_redirected"])
        self.assertTrue(restored["saved_queue_restored"])

        offers, private_context = _replay_inbound_offer(
            data["raw_event_slice"], data["session_id"], data["date_raw"])
        self.assertEqual([data["public_offer"]], offers)
        self.assertEqual(data["private_context"], private_context)
        public_offer = offers[0]
        self.assertEqual("saved_native_pending", public_offer["source"])
        self.assertEqual("native_inbound_response", public_offer["execute"]["accept"])
        self.assertEqual("native_inbound_response", public_offer["execute"]["reject"])
        self.assertTrue(PRIVATE_KEYS.isdisjoint(_all_keys(public_offer)))
        public_text = json.dumps(public_offer, ensure_ascii=False)
        self.assertNotIn("native_proposal_id", public_text)
        self.assertNotIn("3156-1dd5edff31c8a1c", public_text)

        contract = data["report_contract"]
        self.assertEqual("failed", contract["report_status"])
        self.assertTrue(contract["native_events_complete"])
        self.assertTrue(contract["restored_event_valid"])
        self.assertEqual(0, contract["execute_call_count"])

    def test_real_e_accept_uses_inbound_consumers_and_preserves_observed_prestige(self):
        data = self.fixture["inbound_accept"]
        source = self.fixture["sources"]["e"]
        self._check_real_source_metadata(source)
        self.assertEqual(63, source["native_events_line_count"])
        self.assertTrue(source["native_events_complete"])
        for key in ("restored_event", "inspection_event", "handler_entry_event",
                    "handler_return_event", "submission_event", "response_event"):
            self._check_optional_event_line(source, data[key])
        for record in data["effect_observations"]:
            self._check_optional_event_line(source, record)

        restored = data["restored_event"]["event"]
        inspection = data["inspection_event"]["event"]
        submission = data["submission_event"]["event"]
        response = data["response_event"]["event"]
        self.assertTrue(ObserverSession._valid_native_inbound_pending_restored_event(
            restored, data["session_id"]))
        self.assertTrue(ObserverSession._valid_native_inbound_inspection(
            inspection, inspection["query_id"], data["session_id"],
            data["actor"], data["phase"], data["native_proposal_id"],
            data["date_raw"], data["action_id"]))
        self.assertTrue(ObserverSession._valid_native_inbound_submission_result(
            submission, data["request_id"], data["session_id"], data["actor"],
            data["recipient"], data["phase"], data["date_raw"],
            data["native_proposal_id"], data["action_id"]))

        context = response["peace_context"]
        self.assertTrue(ObserverSession._valid_inbound_peace_context(
            context, data["actor"], data["recipient"]))
        fields = ObserverSession._inbound_peace_context_fields(
            context, data["actor"], data["recipient"])
        self.assertIsNotNone(fields)
        self.assertEqual("demand", fields["direction"])
        self.assertEqual("FRA", fields["concede_defeat_country"])
        self.assertEqual("ENG", fields["concede_defeat_beneficiary"])
        self.assertTrue(fields["concede_defeat_requested"])

        public_inspection = ObserverSession._public_native_inbound_inspection(
            inspection, data["date_raw"], data["action_id"])
        self.assertEqual(data["public_inspection"], public_inspection)
        public_submission = ObserverSession._public_native_inbound_submission_receipt(
            submission, data["request_id"], data["actor"], data["phase"],
            data["date_raw"], data["action_id"])
        self.assertEqual(data["public_submission"], public_submission)
        public_result = ObserverSession._public_native_inbound_response_result(
            response, data["request_id"], data["session_id"], data["actor"],
            data["phase"], data["date_raw"], data["native_proposal_id"],
            data["action_id"])
        self.assertEqual(data["public_result"], public_result)
        self.assertIsNotNone(public_result)

        consumed = _replay_inbound_response(
            [data["response_event"]], data["session_id"], data["request_id"],
            data["actor"], data["phase"], data["date_raw"],
            data["native_proposal_id"])
        self.assertEqual({"status": "accepted", "result": data["public_result"]},
                         consumed)

        offers, private_context = _replay_inbound_offer(
            [data["restored_event"]], data["session_id"], data["date_raw"])
        self.assertEqual([data["public_offer"]], offers)
        self.assertEqual(data["private_context"], private_context)
        self.assertTrue(PRIVATE_KEYS.isdisjoint(
            _all_keys(public_inspection) | _all_keys(public_submission)
            | _all_keys(public_result) | _all_keys(offers[0])))
        public_text = json.dumps(
            {"inspection": public_inspection, "submission": public_submission,
             "result": public_result, "offer": offers[0]}, ensure_ascii=False)
        for private_marker in (
                "native_proposal_id", "query_id", "token3c", "date28", "date2c",
                "envoy30", "native_action", "native_node", "proposal3c",
                "created2c", "treasury_before_raw", "treasury_after_raw"):
            self.assertNotIn(private_marker, public_text)

        effects = public_result["effects"]
        concede = effects["concede_defeat"]
        self.assertEqual("FRA", concede["conceding_country"])
        self.assertEqual("ENG", concede["beneficiary"])
        self.assertEqual(-10990, concede["conceding_prestige_before_raw"])
        self.assertEqual(-20990, concede["conceding_prestige_after_raw"])
        self.assertEqual(-10000, concede["conceding_prestige_delta_raw"])
        self.assertEqual(62778, concede["beneficiary_prestige_before_raw"])
        self.assertEqual(69384, concede["beneficiary_prestige_after_raw"])
        self.assertEqual(6606, concede["beneficiary_prestige_delta_raw"])
        self.assertEqual(1000, concede["prestige_scale"])
        self.assertTrue(concede["values_readable"])
        self.assertTrue(concede["verified"])
        self.assertEqual(
            concede["beneficiary_prestige_after_raw"]
            - concede["beneficiary_prestige_before_raw"],
            concede["beneficiary_prestige_delta_raw"])
        self.assertEqual(
            concede["conceding_prestige_after_raw"]
            - concede["conceding_prestige_before_raw"],
            concede["conceding_prestige_delta_raw"])
        self.assertTrue(all(row["event"].get("private") is True
                            for row in data["effect_observations"]))
        self.assertTrue(all("treasury_before_raw" in row["event"]
                            and "treasury_after_raw" in row["event"]
                            for row in data["effect_observations"]))

        contract = data["report_contract"]
        self.assertEqual("passed", contract["report_status"])
        self.assertEqual(22, contract["check_count"])
        self.assertTrue(contract["checks_all"])
        self.assertEqual(1, contract["execute_call_count"])
        self.assertEqual(2, contract["native_state"])
        self.assertEqual("accepted", contract["outcome"])
        self.assertTrue(contract["pending_removed"])
        self.assertTrue(contract["war_before"])
        self.assertFalse(contract["war_after"])
        self.assertTrue(contract["terms_verified"])
        self.assertTrue(contract["effects_complete"])
        self.assertTrue(contract["concede_defeat_verified"])

    def test_real_query11_semantic_and_execution_consumer_keep_c_rules_and_evaluation_distinct(self):
        query_source = self.query_fixture["source"]
        self._check_optional_source_file(query_source, "native_events_path",
                                         "native_events_bytes",
                                         "native_events_sha256")
        facts = self.query_fixture["expected_facts"]
        observed_names = set()
        for case in self.query_fixture["cases"]:
            event = case["event"]
            name = case["name"]
            observed_names.add(name)
            selection = _query_selection(event)
            self.assertTrue(
                ObserverSession._valid_native_peace_concede_defeat_offer_inspection(
                    event, event["action_id"], event["actor"],
                    event["recipient"], event["phase"], event["date_raw"],
                    selection, event["query_id"], event["session_id"]), name)
            semantic = ObserverSession._semantic_peace_concede_defeat_offer_inspection(
                event, "eu4_escape")
            self.assertEqual(event["term_mask"], semantic["term_mask"])
            self.assertEqual(event["native_concede_defeat"]["rule_available"],
                             semantic["native_concede_defeat"]["rule_available"])
            parameters = _query_parameters(event)
            public = DiplomacyTools._apply_peace_execution_inspection(
                {"interface_support": {}, "acceptance": {}, "costs": {},
                 "session": {}}, event, parameters)
            self.assertEqual("native_peace_execution_inspection",
                             public["interface_support"]["query"])

            if name in ("demand-c", "offer-c"):
                expected = facts["evaluation"][name]
                self.assertEqual("available", public["legality"]["status"])
                self.assertTrue(public["parameters"]["complete"])
                self.assertEqual(expected["score_raw"],
                                 public["acceptance"]["native_total"])
                self.assertEqual(expected["aggregate_score_raw"],
                                 public["costs"]["native_evaluation"][
                                     "aggregate_score_raw"])
                self.assertEqual(expected["factor_native_count"],
                                 semantic["native_evaluation"][
                                     "factor_native_count"])
                self.assertEqual(expected["factors_complete"],
                                 semantic["native_evaluation"][
                                     "factors_complete"])
                self.assertNotEqual(expected["score_raw"],
                                    expected["aggregate_score_raw"])
            else:
                expected = next(item for item in facts["rule"].values()
                                if item["case"] == name)
                self.assertEqual("unavailable", public["legality"]["status"])
                self.assertFalse(public["parameters"]["complete"])
                self.assertEqual(
                    "NATIVE_PEACE_SELECTED_TERM_RULE_UNAVAILABLE",
                    public["legality"]["reasons"][0]["code"])
                self.assertFalse(semantic["native_concede_defeat"][
                    "rule_available"])
                diagnostic = semantic["diagnostics"]["selected_term_gate"]
                self.assertEqual(expected["diagnostic_decoded"],
                                 diagnostic["text"])
                self.assertIn(expected["diagnostic_text"], diagnostic["text"])
                self.assertFalse(public["acceptance"]["details_available"])
                self.assertFalse(public["costs"]["native_evaluation"][
                    "aggregate_score_available"])

        self.assertEqual({
            "demand-c", "offer-c", "money-c", "reparations-c", "trade-c",
            "province-c",
        }, observed_names)


if __name__ == "__main__":
    unittest.main()
