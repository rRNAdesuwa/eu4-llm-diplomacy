from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.peace_execution import normalize_peace_execution_parameters


FIXTURE = Path(__file__).parent / "fixtures" / (
    "peace_special_r54_real_queries.json")
SF_FIXTURE = Path(__file__).parent / "fixtures" / (
    "peace_special_r54_real_sf_queries.json")
ACTOR = "FRA"
RECIPIENT = "ENG"


def _load_fixture() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _mask(terms: list[dict[str, object]]) -> str:
    bits = {
        "demand_ducats": "m", "cede_province": "p",
        "war_reparations": "r", "transfer_trade_power": "t",
        "concede_defeat": "c", "annul_treaties": "a",
        "humiliate_rival": "h", "show_strength": "s",
        "force_religion": "f",
    }
    return "".join(bits[term["action_id"]] for term in terms)


def _selection(case: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    """Build the internal validator selection from the captured public request."""

    request = case["request"]
    action_id = case["action_id"]
    context = request["peace_context"]
    normalized = normalize_peace_execution_parameters(
        action_id, ACTOR, RECIPIENT, "initiate", request)
    fields = ObserverSession._peace_execution_fields(normalized)
    assert fields is not None
    (war_id, direction, amount_raw, province_ids, beneficiary,
     reparations_payer, reparations_claimant, trade_source,
     trade_beneficiary, concede_country, concede_beneficiary,
     annul_country, annul_partners, term_mask) = fields
    special_terms = [
        dict(term) for term in context["terms"]
        if term["action_id"] in {
            "humiliate_rival", "show_strength", "force_religion"}
    ]
    selection = {
        "action_id": action_id,
        "war_id": war_id,
        "direction": direction,
        "amount_raw": amount_raw,
        "province_ids": list(province_ids),
        "beneficiary": beneficiary,
        "source": trade_source if "t" in term_mask else "-",
        "trade_power_beneficiary": trade_beneficiary,
        "payer": reparations_payer,
        "claimant": reparations_claimant,
        "conceding_country": concede_country,
        "concede_beneficiary": concede_beneficiary,
        "annul_country": annul_country or "-",
        "annul_partners": list(annul_partners or []),
        "term_mask": term_mask,
        "special_terms": special_terms,
    }
    return selection, normalized


def _without_internal_amount(terms: list[dict[str, object]]) -> list[dict[str, object]]:
    return [{key: value for key, value in term.items() if key != "amount_raw"}
            for term in terms]


class PeaceSpecialRealQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = _load_fixture()
        cls.cases = {case["name"]: case for case in cls.fixture["cases"]}
        cls.sf_fixture = json.loads(SF_FIXTURE.read_text(encoding="utf-8"))

    def test_fixture_source_hashes_and_selected_event_lines_are_intact(self):
        source = self.fixture["source"]
        report_path = Path(source["report_path"])
        events_path = Path(source["native_events_path"])
        self.assertTrue(report_path.is_file())
        self.assertTrue(events_path.is_file())
        self.assertEqual(source["report_bytes"], report_path.stat().st_size)
        self.assertEqual(source["native_events_bytes"], events_path.stat().st_size)
        self.assertEqual(source["report_sha256"],
                         hashlib.sha256(report_path.read_bytes()).hexdigest())
        self.assertEqual(source["native_events_sha256"],
                         hashlib.sha256(events_path.read_bytes()).hexdigest())
        lines = events_path.read_bytes().splitlines()
        for selected in source["selected_line_sha256"]:
            raw = lines[selected["line"] - 1]
            self.assertEqual(selected["bytes"], len(raw))
            self.assertEqual(selected["sha256"], hashlib.sha256(raw).hexdigest())

    def test_real_query13_selected_h_roles_counts_factors_and_projection(self):
        expected = {
            "humiliate_rival-demand": ("demand", "ENG", "FRA", 9, 1),
            "humiliate_rival-offer": ("offer", "FRA", "ENG", 8, 1),
            "money-humiliate": ("demand", "ENG", "FRA", 9, 2),
        }
        for name, (direction, country, beneficiary, factor_count,
                   rule_term_count) in expected.items():
            with self.subTest(name=name):
                case = self.cases[name]
                event = case["event"]
                selection, _ = _selection(case)
                self.assertTrue(ObserverSession._valid_native_peace_special_offer_inspection(
                    event, case["action_id"], ACTOR, RECIPIENT, "initiate",
                    event["date_raw"], selection, event["query_id"],
                    event["session_id"]))
                native = event["native_humiliate_rival"]
                self.assertEqual(direction, event["direction"])
                self.assertEqual(1, native["candidate_count"])
                self.assertEqual(1, native["matching_candidate_count"])
                self.assertEqual(1, native["selected_term_count"])
                self.assertEqual(country, native["country"])
                self.assertEqual(beneficiary, native["beneficiary"])
                self.assertTrue(native["parameters_matched"])
                self.assertTrue(native["rule_checked"])
                self.assertTrue(native["rule_available"])
                self.assertEqual(rule_term_count, native["rule_term_count"])
                semantic = ObserverSession._semantic_peace_special_offer_inspection(
                    event)
                self.assertTrue(semantic["parameters_matched"])
                self.assertTrue(semantic["parameters_complete"])
                self.assertEqual(
                    case["public"]["parameters"]["actual"]["peace_context"]["terms"],
                    _without_internal_amount(semantic["peace_context"]["terms"]))
                self.assertEqual("available", case["public"]["legality"]["status"])
                self.assertEqual(factor_count,
                                 len(case["public"]["acceptance"]["items"]))
                self.assertTrue(case["public"]["private_fields_absent"])

    def test_real_c_plus_h_rule_rejection_stays_unavailable_with_selected_roles(self):
        case = self.cases["concede-humiliate"]
        event = case["event"]
        selection, _ = _selection(case)
        self.assertTrue(ObserverSession._valid_native_peace_special_offer_inspection(
            event, case["action_id"], ACTOR, RECIPIENT, "initiate",
            event["date_raw"], selection, event["query_id"], event["session_id"]))
        self.assertEqual("ch", event["term_mask"])
        self.assertTrue(event["native_concede_defeat"]["parameters_matched"])
        native = event["native_humiliate_rival"]
        self.assertTrue(native["selected"])
        self.assertTrue(native["parameters_matched"])
        self.assertFalse(native["rule_available"])
        self.assertEqual("NATIVE_PEACE_SELECTED_TERM_RULE_UNAVAILABLE",
                         native["reason_code"])
        semantic = ObserverSession._semantic_peace_special_offer_inspection(event)
        self.assertEqual(selection["term_mask"], semantic["term_mask"])
        self.assertTrue(semantic["parameters_matched"])
        self.assertFalse(semantic["native_term_gate"])
        self.assertEqual(
            case["public"]["parameters"]["actual"]["peace_context"]["terms"],
            semantic["peace_context"]["terms"])
        self.assertEqual("unavailable", case["public"]["legality"]["status"])
        self.assertTrue(case["public"]["private_fields_absent"])

    def test_real_missing_s_and_f_candidates_remain_unknown(self):
        for name, native_key in (
                ("show_strength-demand", "native_show_strength"),
                ("force_religion-demand", "native_force_religion")):
            with self.subTest(name=name):
                case = self.cases[name]
                event = case["event"]
                selection, _ = _selection(case)
                self.assertTrue(ObserverSession._valid_native_peace_special_offer_inspection(
                    event, case["action_id"], ACTOR, RECIPIENT, "initiate",
                    event["date_raw"], selection, event["query_id"],
                    event["session_id"]))
                native = event[native_key]
                self.assertEqual(0, native["candidate_count"])
                self.assertEqual(0, native["matching_candidate_count"])
                self.assertFalse(native["candidate_found"])
                self.assertFalse(native["selected"])
                self.assertFalse(native["parameters_matched"])
                self.assertEqual("NATIVE_PEACE_SPECIAL_CANDIDATE_NOT_FOUND",
                                 native["reason_code"])
                semantic = ObserverSession._semantic_peace_special_offer_inspection(
                    event)
                self.assertFalse(semantic["parameters_matched"])
                self.assertEqual([], semantic["peace_context"]["terms"])
                self.assertIsNone(case["public"]["parameters"]["actual"])
                self.assertEqual("unknown", case["public"]["legality"]["status"])

    def test_real_hs_mixed_candidate_failure_cannot_be_available(self):
        case = self.cases["humiliate-strength"]
        event = case["event"]
        selection, _ = _selection(case)
        self.assertTrue(ObserverSession._valid_native_peace_special_offer_inspection(
            event, case["action_id"], ACTOR, RECIPIENT, "initiate",
            event["date_raw"], selection, event["query_id"], event["session_id"]))
        self.assertTrue(event["native_humiliate_rival"]["selected"])
        self.assertFalse(event["native_show_strength"]["candidate_found"])
        semantic = ObserverSession._semantic_peace_special_offer_inspection(event)
        self.assertFalse(semantic["parameters_matched"])
        self.assertEqual(
            [{"action_id": "humiliate_rival", "country": "ENG",
              "beneficiary": "FRA"}],
            semantic["peace_context"]["terms"])
        self.assertEqual("unknown", case["public"]["legality"]["status"])
        self.assertNotEqual("available", case["public"]["legality"]["status"])

    def test_real_sf_fixture_sources_and_rule_diagnostics_are_projected(self):
        fixture = self.sf_fixture
        for source in fixture["source"]["reports"]:
            with self.subTest(source=source["report_path"]):
                report_path = Path(source["report_path"])
                events_path = Path(source["native_events_path"])
                self.assertEqual(source["report_bytes"], report_path.stat().st_size)
                self.assertEqual(source["native_events_bytes"], events_path.stat().st_size)
                self.assertEqual(
                    source["report_sha256"],
                    hashlib.sha256(report_path.read_bytes()).hexdigest())
                self.assertEqual(
                    source["native_events_sha256"],
                    hashlib.sha256(events_path.read_bytes()).hexdigest())
                lines = events_path.read_bytes().splitlines()
                self.assertEqual(source["native_events_line_count"], len(lines))
                for selected in source["selected_line_sha256"]:
                    raw = lines[selected["line"] - 1]
                    self.assertEqual(selected["bytes"], len(raw))
                    self.assertEqual(
                        selected["sha256"],
                        hashlib.sha256(raw).hexdigest())

        for case in fixture["cases"]:
            with self.subTest(name=case["name"]):
                event = case["event"]
                request = case["request"]
                selection, _ = _selection(case)
                self.assertTrue(
                    ObserverSession._valid_native_peace_special_offer_inspection(
                        event, case["action_id"], ACTOR, RECIPIENT, "initiate",
                        event["date_raw"], selection, event["query_id"],
                        event["session_id"]))
                expected = case["expected"]
                self.assertEqual(expected["term_mask"], event["term_mask"])
                native = event[expected["native_key"]]
                for field in (
                        "candidate_count", "matching_candidate_count",
                        "candidate_found", "selected", "parameters_matched",
                        "rule_available", "rule_diagnostic_truncated"):
                    self.assertEqual(expected[field], native[field], field)

                semantic = ObserverSession._semantic_peace_special_offer_inspection(
                    event, fixture["source"]["native_text_codec"])
                diagnostic = semantic["diagnostics"]["selected_term_gate"]
                self.assertEqual(expected["rule_diagnostic_text"], diagnostic["text"])
                self.assertEqual(
                    expected["rule_diagnostic_text"] is not None,
                    diagnostic["text_decoded"])
                self.assertEqual(expected["rule_diagnostic_truncated"],
                                 diagnostic["text_truncated"])
                self.assertEqual("native_rule", diagnostic["source"])
                self.assertFalse(diagnostic["complete"])
                self.assertNotIn("private", json.dumps(semantic))

                inspection = {
                    "interface_support": {},
                    "session": {},
                    "acceptance": {},
                    "costs": {},
                }
                projected = DiplomacyTools._apply_peace_execution_inspection(
                    inspection, semantic, request)
                self.assertEqual(expected["status"],
                                 projected["legality"]["status"])
                if expected["rule_diagnostic_text"] is not None:
                    self.assertEqual(
                        expected["rule_diagnostic_text"],
                        projected["legality"]["reasons"][0]["text"])
                self.assertEqual(expected["details_count"], len(
                    projected["acceptance"].get("items", [])))
                self.assertEqual(expected["native_total"],
                                 projected["acceptance"].get("native_total"))


if __name__ == "__main__":
    unittest.main()
