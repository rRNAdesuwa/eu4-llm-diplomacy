from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from typing import Any

from bridge.diplomacy import DiplomacyTools, ObserverSession


FIXTURE = Path(__file__).parent / "fixtures" / "peace_trade_sources_r51_real.json"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

# These keys may occur in the preserved raw native layer.  The tests apply the
# check only to production public projections, because a replay fixture must
# retain the metadata required by the native validators.
_PRIVATE_KEYS = {
    "session_id",
    "query_id",
    "frame_thread",
    "creation_filetime",
    "native_origin",
    "native_sequence",
    "native_flags",
    "native_war_reference",
    "module_base",
    "vtable_rva",
    "private",
    "private_fields",
}

_EXPECTED_FACTORS = [
    ("DIPLO_WAR_INCONCLUSIVE", -1000),
    ("DIPLO_WAR_SCORE", 1),
    ("DIPLO_PEACEOFFER_VALUE", -30),
    ("DIPLO_WAR_DESPERATION", 6),
    ("DIPLO_HOLD_CAPITAL", -5),
    ("DIPLO_WAR_TIME_PASSED", -41),
    ("DIPLO_MILITARY_STRENGTH", 7),
    ("DIPLO_WAR_FORCE_BALANCE", -2),
    ("DIPLO_HIGH_DEMANDS", -100),
]


def _private_key_paths(value: Any, path: tuple[str, ...] = ()) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in _PRIVATE_KEYS:
                found.append(".".join(path + (key,)))
            found.extend(_private_key_paths(nested, path + (str(key),)))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            found.extend(_private_key_paths(nested, path + (str(index),)))
    return found


def _optional_source_line(source: dict[str, Any], line: int,
                          expected_sha256: str, expected_event: str) -> None:
    """Verify bounded provenance when the runtime evidence tree is present."""
    path = REPOSITORY_ROOT / source["path"]
    if not path.exists():
        return
    lines = path.read_bytes().splitlines()
    if line < 1 or line > len(lines):
        raise AssertionError((path, line, len(lines)))
    raw = lines[line - 1]
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise AssertionError((path, line, "line hash"))
    event = json.loads(raw.decode("utf-8"))
    if event.get("event") != expected_event:
        raise AssertionError((path, line, event.get("event")))


def _query_selection(case: dict[str, Any]) -> dict[str, Any]:
    context = case["input"]["peace_context"]
    trade = next((term for term in context["terms"]
                  if term["action_id"] == "transfer_trade_power"), None)
    event = case["native_event"]
    return {
        "action_id": "transfer_trade_power",
        "war_id": context["war_id"],
        "direction": context["direction"],
        "amount_raw": -1,
        "province_ids": [],
        "beneficiary": None,
        "source": case["input"]["requested_source"],
        "trade_power_beneficiary": (
            trade.get("beneficiary", case["input"]["expected_beneficiary"])
            if trade is not None else case["input"]["expected_beneficiary"]),
        "term_mask": event["term_mask"],
        "_sources_protocol": True,
    }


def _production_query_replay(case: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """Run the real QUERY10 validator and public execution projection."""
    event = case["native_event"]
    selection = _query_selection(case)
    valid = ObserverSession._valid_native_peace_trade_power_offer_inspection(
        event, "transfer_trade_power", "FRA", "ENG", "initiate",
        event["date_raw"], selection, event["query_id"], event["session_id"])
    semantic = ObserverSession._semantic_peace_trade_power_offer_inspection(event)
    inspection = {
        "interface_support": {},
        "session": {"date_raw": event["date_raw"]},
        "acceptance": {},
        "costs": {},
    }
    public = DiplomacyTools._apply_peace_execution_inspection(
        inspection, semantic, {"peace_context": case["input"]["peace_context"]})
    return valid, public


def _production_execution_replay(record: dict[str, Any]) -> dict[str, Any]:
    """Run the real submission/execution validators and public reducers."""
    request = record["request"]
    params = request["parameters"]
    submission = record["submission_event"]["event"]
    execution = record["execution_event"]["event"]
    session_id = execution["session_id"]
    valid_submission = ObserverSession._valid_native_peace_submission_result(
        submission, request["request_id"], session_id, request["actor"],
        request["recipient"], request["phase"], request["date_raw"],
        request["action_id"], params)
    public_submission = ObserverSession._public_native_peace_submission_receipt(
        submission, request["request_id"], request["actor"],
        request["recipient"], request["phase"], request["date_raw"],
        request["action_id"], params)
    valid_execution = ObserverSession._valid_native_peace_execution_result(
        execution, request["request_id"], session_id, request["actor"],
        request["recipient"], request["phase"], request["date_raw"],
        request["action_id"], params)
    public_execution = ObserverSession._public_native_peace_execution_result(
        execution, request["request_id"], session_id, request["actor"],
        request["recipient"], request["phase"], request["date_raw"],
        request["action_id"], params)
    return {
        "valid_submission": valid_submission,
        "public_submission": public_submission,
        "valid_execution": valid_execution,
        "public_execution": public_execution,
    }


class PeaceTradeSourcesR51RealFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_fixture_preserves_validator_metadata_and_separates_public_layer(self):
        fixture = self.fixture
        self.assertEqual(1, fixture["fixture_version"])
        self.assertEqual("peace-trade-sources-r51-real", fixture["fixture_id"])
        self.assertEqual("QUERY10", fixture["contract"]["query_protocol"])
        self.assertEqual("native_peace_trade_power_sources",
                         fixture["contract"]["source_capability"])
        self.assertTrue(fixture["contract"]
                        ["private_fields_absent_from_public_projection"])
        self.assertTrue(fixture["contract"]["fixture_layers"]
                        ["native_events_include_private_metadata"])
        self.assertTrue(fixture["contract"]["fixture_layers"]
                        ["public_projection_excludes_private_metadata"])
        self.assertTrue(fixture["contract"]["fixture_layers"]
                        ["production_validator_replay"])
        self.assertTrue(fixture["contract"]
                        ["inbound_context_response_production_replay"])
        self.assertEqual("E_pending_to_F_accept",
                         fixture["contract"][
                             "inbound_pending_acceptance_comparison"])

        identity = fixture["identity"]
        self.assertEqual({"actor": "FRA", "recipient": "ENG",
                          "family": "peace", "action_id": "transfer_trade_power",
                          "phase": "initiate", "war_id": identity["war_id"],
                          "date_raw": 56548944}, identity)
        self.assertRegex(identity["war_id"], r"^war_[0-9a-f]+_[0-9a-f]+$")

        for source in fixture["sources"].values():
            if "path" in source and "sha256" in source:
                self.assertRegex(source["sha256"], r"^[0-9a-f]{64}$")
                self.assertGreater(source["size"], 0)

        self.assertEqual(5, len(fixture["query_cases"]))
        for case in fixture["query_cases"]:
            raw = case["native_event"]
            self.assertIn("query_id", raw)
            self.assertIn("session_id", raw)
            self.assertEqual("native_peace_trade_power_offer_inspection",
                             raw["event"])
            self.assertFalse(case["public_summary"]["private_fields_present"])
            self.assertFalse(case["public_summary"]["submitted"])
            self.assertTrue(case["public_summary"]["query_complete"])
            self.assertTrue(case["public_summary"]["candidate_list_complete"])
            self.assertEqual([], _private_key_paths(case["public_summary"]))

        for name in ("wrong_source_execution", "correct_source_execution"):
            record = fixture[name]
            self.assertIn("session_id", record["submission_event"]["event"])
            self.assertIn("session_id", record["execution_event"]["event"])
            self.assertEqual([], _private_key_paths(record["request"]))

    def test_query10_real_events_validate_and_public_projection_has_candidates(self):
        cases = {case["name"]: case for case in self.fixture["query_cases"]}
        self.assertEqual({
            "primary-trade-power-candidates",
            "demand-trade-power-utr",
            "demand-trade-power-default-eng",
            "offer-trade-power-fra",
            "demand-reparations-trade-power-utr",
        }, set(cases))

        for name, case in cases.items():
            with self.subTest(case=name):
                valid, public = _production_query_replay(case)
                self.assertTrue(valid)
                summary = case["public_summary"]
                self.assertEqual(summary["legality_status"],
                                 public["legality"]["status"])
                self.assertEqual(summary["parameters_complete"],
                                 public["parameters"]["complete"])
                candidates = public["parameters"]["candidates"]
                self.assertEqual(summary["candidate_count"],
                                 candidates["candidate_count"])
                self.assertEqual(summary["matching_candidate_count"],
                                 candidates["matching_candidate_count"])
                self.assertEqual(summary["candidate_sources"],
                                 candidates["candidates"])
                self.assertEqual([], _private_key_paths(public))

                expected_source = summary["actual_source"]
                actual = public["parameters"]["actual"]
                if summary["candidate_found"]:
                    self.assertIsInstance(actual, dict)
                    terms = actual["peace_context"]["terms"]
                    trade = next(term for term in terms
                                  if term["action_id"] == "transfer_trade_power")
                    self.assertEqual(expected_source, trade["source"])
                    self.assertEqual(summary["actual_beneficiary"],
                                     trade["beneficiary"])
                else:
                    self.assertIsNone(actual)

        discovery = cases["primary-trade-power-candidates"]
        self.assertEqual([], discovery["input"]["peace_context"]["terms"])
        self.assertEqual("-", discovery["input"]["requested_source"])
        self.assertEqual("unknown",
                         discovery["public_summary"]["legality_status"])
        self.assertFalse(discovery["public_summary"]["candidate_found"])
        self.assertEqual([{"source": "UTR", "beneficiary": "FRA",
                            "selected": False, "complete": True}],
                         discovery["public_summary"]["candidate_sources"])

        default_eng = cases["demand-trade-power-default-eng"]
        self.assertEqual("ENG", default_eng["input"]["requested_source"])
        self.assertEqual("unknown", default_eng["public_summary"]["legality_status"])
        self.assertFalse(default_eng["public_summary"]["candidate_found"])
        self.assertEqual("ENG", default_eng["native_event"]["native_trade_power"]["source"])

        offer = cases["offer-trade-power-fra"]
        self.assertEqual("offer", offer["input"]["direction"])
        self.assertEqual("FRA", offer["public_summary"]["actual_source"])
        self.assertEqual("ENG", offer["public_summary"]["actual_beneficiary"])

        combined = cases["demand-reparations-trade-power-utr"]
        terms = combined["input"]["peace_context"]["terms"]
        self.assertEqual(["war_reparations", "transfer_trade_power"],
                         [term["action_id"] for term in terms])
        self.assertTrue(combined["public_summary"]["reparations_pair_matches"])
        self.assertEqual(3, combined["native_event"]["native_payload"]["selected_term_count"])

    def test_factor_branch_and_single_t_nine_identifiers_are_verified(self):
        proof = self.fixture["factor_proof"]
        self.assertEqual(9, proof["single_t_factor_count"])
        self.assertTrue(proof["single_t_factors_complete"])
        self.assertFalse(proof["single_t_factor_capture_truncated"])
        self.assertEqual(_EXPECTED_FACTORS,
                         [(item["native_identifier"], item["native_value"])
                          for item in proof["single_t_factor_identifiers"]])
        for item in proof["single_t_factor_identifiers"]:
            self.assertTrue(item["identifier_verified"])
            self.assertTrue(item["row_binding_verified"])

        branch = proof["branch"]
        self.assertEqual("0x3728dd", branch["caller_return_rva"])
        self.assertEqual("0x3728d8", branch["constructor_call_rva"])
        self.assertTrue(branch["branch_condition_readable"])
        self.assertEqual(1, branch["branch_condition_value"])
        self.assertEqual(248, branch["branch_condition_row_offset"])
        self.assertEqual(6, branch["native_value"])
        self.assertEqual("DIPLO_WAR_DESPERATION", branch["identifier"])
        self.assertTrue(branch["identifier_verified"])
        self.assertTrue(branch["row_binding_verified"])
        self.assertEqual("0x1c5d950", branch["static_key_rva"])

        raw = proof["raw_event"]
        self.assertEqual("native_alliance_reason_provenance", raw["event"])
        self.assertEqual([], _private_key_paths(proof["branch"]))
        factor_source = self.fixture["sources"]["factor_event"]
        _optional_source_line(factor_source, factor_source["line"],
                              factor_source["line_sha256"],
                              "native_alliance_reason_provenance")

    def test_a_wrong_source_fails_production_execution_validation(self):
        record = self.fixture["wrong_source_execution"]
        replay = _production_execution_replay(record)
        self.assertTrue(replay["valid_submission"])
        self.assertIsNotNone(replay["public_submission"])
        self.assertFalse(replay["valid_execution"])
        self.assertIsNone(replay["public_execution"])
        self.assertEqual([], _private_key_paths(replay["public_submission"]))

        request = record["request"]
        execution = record["execution_event"]["event"]
        effect = execution["effects"]["transfer_trade_power"]
        self.assertEqual("UTR", request["trade_power_source"])
        self.assertEqual("UTR", execution["trade_power_source"])
        self.assertEqual("ENG", effect["source"])
        self.assertEqual("FRA", effect["beneficiary"])
        self.assertEqual(1, execution["native_state"])
        self.assertEqual("rejected", execution["outcome"])
        self.assertTrue(execution["war_before"])
        self.assertTrue(execution["war_after"])
        self.assertFalse(record["consumer_replay"]["complete"])
        self.assertEqual("EFFECT_SOURCE_MISMATCH",
                         record["consumer_replay"]["reason"])

        wrapper = record["wrapper_report"]
        self.assertEqual("unknown", wrapper["status"])
        self.assertEqual("submitted", wrapper["result_status"])
        self.assertEqual("unknown", wrapper["result_game_outcome"])
        self.assertEqual(1, wrapper["execute_call_count"])
        self.assertFalse(wrapper["result_contract_all"])
        self.assertFalse(wrapper["checks"]["native_result_contract"])

        source = self.fixture["sources"]["outbound_events"]
        _optional_source_line(source, record["submission_event"]["evidence"]["line"],
                              record["submission_event"]["evidence"]["line_sha256"],
                              "native_peace_submission_result")
        _optional_source_line(source, record["execution_event"]["evidence"]["line"],
                              record["execution_event"]["evidence"]["line_sha256"],
                              "native_peace_execution_result")

    def test_b_correct_source_passes_production_execution_validation(self):
        record = self.fixture["correct_source_execution"]
        replay = _production_execution_replay(record)
        self.assertTrue(replay["valid_submission"])
        self.assertIsNotNone(replay["public_submission"])
        self.assertTrue(replay["valid_execution"])
        public = replay["public_execution"]
        self.assertIsNotNone(public)
        self.assertEqual([], _private_key_paths(public))
        self.assertEqual("UTR", public["trade_power_source"])
        self.assertEqual("FRA", public["trade_power_beneficiary"])
        self.assertEqual("rejected", public["native_outcome"])
        self.assertEqual(1, public["native_state"])
        self.assertEqual("UTR", public["effects"]["transfer_trade_power"]["source"])
        self.assertFalse(public["effects"]["transfer_trade_power"]["verified"])

        execution = record["execution_event"]["event"]
        self.assertEqual("UTR", execution["effects"]["transfer_trade_power"]["source"])
        self.assertEqual("rejected", execution["outcome"])
        self.assertTrue(record["consumer_replay"]["complete"])
        self.assertEqual("NATIVE_REJECTED_RESULT_COMPLETE",
                         record["consumer_replay"]["reason"])
        wrapper = record["wrapper_report"]
        self.assertEqual("passed", wrapper["status"])
        self.assertEqual("rejected", wrapper["result_status"])
        self.assertEqual("rejected", wrapper["result_game_outcome"])
        self.assertEqual(1, wrapper["execute_call_count"])
        self.assertEqual(17, wrapper["check_count"])
        self.assertTrue(wrapper["checks_all"])
        self.assertTrue(wrapper["result_contract_all"])

        source = self.fixture["sources"]["b_outbound_events"]
        _optional_source_line(source, record["submission_event"]["evidence"]["line"],
                              record["submission_event"]["evidence"]["line_sha256"],
                              "native_peace_submission_result")
        _optional_source_line(source, record["execution_event"]["evidence"]["line"],
                              record["execution_event"]["evidence"]["line_sha256"],
                              "native_peace_execution_result")

    def test_e_inbound_pending_replays_production_offer_validator_and_projection(self):
        record = self.fixture["inbound_pending"]
        self.assertEqual("passed", record["report_status"])
        self.assertEqual(9, record["fixture_check_count"])
        self.assertEqual(1, record["dispatch_count"])
        self.assertEqual(1, record["pending_count"])
        self.assertFalse(record["fra_decision_submitted"])
        self.assertTrue(record["pending_held"])
        self.assertEqual("UTR", record["trade_power_source"])
        self.assertEqual("FRA", record["trade_power_beneficiary"])

        source = self.fixture["sources"][record["source"]]
        dispatch_record = record["dispatch_event"]
        offer_record = record["offer_event"]
        _optional_source_line(
            source, dispatch_record["evidence"]["line"],
            dispatch_record["evidence"]["line_sha256"],
            "native_peace_inbound_fixture_dispatched")
        _optional_source_line(
            source, offer_record["evidence"]["line"],
            offer_record["evidence"]["line_sha256"],
            "native_alliance_inbound_offer")

        dispatch = dispatch_record["event"]
        self.assertTrue(dispatch["native_gates_available"])
        self.assertTrue(dispatch["dispatcher_accepted"])
        self.assertEqual("UTR", dispatch["trade_power_source"])

        offer = offer_record["event"]
        self.assertTrue(_private_key_paths(offer))
        session_id = offer["session_id"]
        self.assertTrue(ObserverSession._valid_native_inbound_offer_event(
            offer, session_id))
        public = ObserverSession._public_native_inbound_offer(
            record["request_id"], offer)
        self.assertEqual(record["public_projection"], public)
        self.assertEqual([], _private_key_paths(public))
        self.assertEqual("peace_offer", public["action_id"])
        self.assertEqual("ENG", public["actor"])
        self.assertEqual("FRA", public["recipient"])
        self.assertEqual("observed_pending", public["observer_status"])
        self.assertEqual("unknown", public["legality_status"])

    def test_f_inbound_context_and_accept_replay_production_validators(self):
        record = self.fixture["inbound_accept"]
        self.assertEqual("passed", record["report_status"])
        self.assertEqual(22, record["check_count"])
        self.assertEqual(1, record["execute_call_count"])
        self.assertEqual(1, record["publish_count"])
        self.assertTrue(record["decision_submitted"])
        self.assertEqual("UTR", record["trade_power_source"])
        self.assertEqual("FRA", record["trade_power_beneficiary"])

        source = self.fixture["sources"][record["source"]]
        for key, event_name in (
                ("restored_event", "native_diplomacy_inbound_pending_restored"),
                ("inspection_event", "native_alliance_inbound_inspection"),
                ("handler_event", "native_peace_handler_return"),
                ("submission_event", "native_peace_inbound_submission_result"),
                ("response_event", "native_peace_inbound_response_result")):
            event_record = record[key]
            _optional_source_line(
                source, event_record["evidence"]["line"],
                event_record["evidence"]["line_sha256"], event_name)

        restored = record["restored_event"]["event"]
        self.assertTrue(_private_key_paths(restored))
        self.assertTrue(ObserverSession._valid_native_inbound_pending_restored_event(
            restored, record["session_id"]))

        inspection = record["inspection_event"]["event"]
        self.assertTrue(_private_key_paths(inspection))
        self.assertTrue(ObserverSession._valid_native_inbound_inspection(
            inspection, inspection["query_id"], inspection["session_id"],
            inspection["actor"], inspection["phase"],
            inspection["native_proposal_id"], inspection["date_raw"],
            "peace_offer"))
        public_inspection = ObserverSession._public_native_inbound_inspection(
            inspection, inspection["date_raw"], "peace_offer")
        self.assertEqual(record["public_inspection"], public_inspection)
        self.assertEqual([], _private_key_paths(public_inspection))
        context = public_inspection["peace_context"]
        self.assertTrue(context["complete"])
        self.assertEqual("offer", context["direction"])
        self.assertEqual("ENG", context["original_actor"])
        self.assertEqual("FRA", context["original_recipient"])
        self.assertEqual({
            "action_id": "transfer_trade_power",
            "source": "UTR", "beneficiary": "FRA",
        }, context["terms"][0])

        submission = record["submission_event"]["event"]
        self.assertTrue(ObserverSession._valid_native_inbound_submission_result(
            submission, record["request_id"], record["session_id"],
            "ENG", "FRA", "accept", submission["date_raw"],
            record["native_proposal_id"], "peace_offer"))
        public_submission = ObserverSession._public_native_inbound_submission_receipt(
            submission, record["request_id"], "ENG", "accept",
            submission["date_raw"], "peace_offer")
        self.assertEqual(record["public_submission"], public_submission)
        self.assertEqual([], _private_key_paths(public_submission))

        response = record["response_event"]["event"]
        self.assertTrue(_private_key_paths(response))
        public_result = ObserverSession._public_native_inbound_response_result(
            response, record["request_id"], record["session_id"],
            "ENG", "accept", response["date_raw"],
            record["native_proposal_id"], "peace_offer")
        self.assertIsNotNone(public_result)
        self.assertEqual(record["public_result"], public_result)
        self.assertEqual([], _private_key_paths(public_result))
        self.assertEqual("accepted", public_result["native_outcome"])
        self.assertEqual(2, public_result["native_state"])
        self.assertTrue(public_result["pending_removed"])
        self.assertTrue(public_result["terms_verified"])
        self.assertTrue(public_result["war_before"])
        self.assertFalse(public_result["war_after"])
        effect = public_result["effects"]["transfer_trade_power"]
        self.assertEqual(record["effect_summary"]["source"], effect["source"])
        self.assertEqual(record["effect_summary"]["beneficiary"],
                         effect["beneficiary"])
        self.assertFalse(effect["present_before"])
        self.assertTrue(effect["present_after"])
        self.assertEqual(500, effect["amount_raw"])
        self.assertEqual(1000, effect["amount_scale"])
        self.assertTrue(effect["peace_treaty"])
        self.assertEqual(56549088, effect["start_date_raw"])
        self.assertEqual(43808760, effect["end_date_raw"])

    def test_a_and_b_are_one_submit_source_identity_control_pair(self):
        wrong = self.fixture["wrong_source_execution"]
        correct = self.fixture["correct_source_execution"]
        self.assertEqual(1, wrong["wrapper_report"]["execute_call_count"])
        self.assertEqual(1, correct["wrapper_report"]["execute_call_count"])
        self.assertEqual("UTR", wrong["request"]["trade_power_source"])
        self.assertEqual("UTR", correct["request"]["trade_power_source"])
        self.assertEqual("rejected", wrong["execution_event"]["event"]["outcome"])
        self.assertEqual("rejected", correct["execution_event"]["event"]["outcome"])
        self.assertNotEqual(
            wrong["execution_event"]["event"]["effects"]
            ["transfer_trade_power"]["source"],
            correct["execution_event"]["event"]["effects"]
            ["transfer_trade_power"]["source"])
        self.assertFalse(wrong["consumer_replay"]["complete"])
        self.assertTrue(correct["consumer_replay"]["complete"])
        self.assertFalse(wrong["consumer_replay"]["success_claimed"])
        self.assertFalse(correct["consumer_replay"]["success_claimed"])


if __name__ == "__main__":
    unittest.main()
