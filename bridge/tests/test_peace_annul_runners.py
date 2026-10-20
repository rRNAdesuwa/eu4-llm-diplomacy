from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from work.inspect_peace_treaty_save import scan_save
from work.run_peace_inbound_fixture import (
    _fixture_wire,
    _native_annul_treaties_contract,
)
from work.run_peace_inbound_response import (
    _peace_context_contract,
    _public_effect_contract,
)
from work.run_peace_outbound_execution import (
    _ANNUL_TREATIES_ACTION,
    _build_parameters,
    _expected_native_fields,
)


WAR_ID = "war_0123456789abcdef_01234567"


class PeaceAnnulRunnerContractTests(unittest.TestCase):
    def test_outbound_term_and_fixture_wire_are_explicit_and_directed(self):
        parameters = _build_parameters(
            _ANNUL_TREATIES_ACTION, WAR_ID, "10.0", None, None, "demand",
            annul_country="FRA", annul_partners=["GEN", "SAV"])
        terms = parameters["peace_context"]["terms"]
        self.assertEqual([{
            "action_id": "annul_treaties",
            "country": "FRA",
            "treaty_partners": ["GEN", "SAV"],
        }], terms)
        native = _expected_native_fields(_ANNUL_TREATIES_ACTION, parameters)
        self.assertEqual("a", native["term_mask"])
        self.assertEqual("FRA", native["annul_country"])
        self.assertEqual(["GEN", "SAV"], native["annul_partners"])
        self.assertEqual(
            "TEST_ONLY ENG_PEACE_FRA_ANNUL_TREATIES_PENDING\tFRA\tGEN,SAV\n",
            _fixture_wire("annul_treaties", "demand", None,
                          "FRA", ["GEN", "SAV"]))
        with self.assertRaises(ValueError):
            _fixture_wire("annul_treaties", "demand", None,
                          "FRA", ["SAV", "GEN"])

    def test_public_response_contract_validates_each_row_and_keeps_sentinel(self):
        context = {
            "war_id": WAR_ID,
            "direction": "demand",
            "original_actor": "ENG",
            "original_recipient": "FRA",
            "complete": True,
            "terms": [{
                "action_id": "annul_treaties",
                "country": "FRA",
                "treaty_partners": ["GEN", "SAV"],
            }],
        }
        rows = [{
            "country": "FRA",
            "partner": partner,
            "present_before": False,
            "present_after": True,
            "start_date_raw": 56545080,
            "end_date_raw": 43808760,
            "alliance_before": True,
            "alliance_after": False,
            "values_readable": True,
            "verified": True,
        } for partner in ("GEN", "SAV")]
        final = {"result": {
            "action_id": "peace_offer",
            "native_outcome": "accepted",
            "terms_verified": True,
            "war_after": False,
            "date_raw": 56545080,
            "peace_context": context,
            "effects": {
                "complete": True,
                "date_unchanged": True,
                "currency_scale": 1000,
                "money": None,
                "provinces": [],
                "annul_treaties": rows,
            },
        }}
        contract = _public_effect_contract(final, "accept")
        self.assertTrue(contract["applicable"])
        self.assertTrue(contract["all"])
        self.assertEqual([("FRA", "GEN"), ("FRA", "SAV")],
                         contract["annul_treaties_pairs"])

    def test_streaming_save_parser_keeps_exact_and_reverse_pairs(self):
        text = """EU4txt
date=1455.5.12
gamestate={
  diplomacy={
    annul_treaties={
      first=FRA
      second=GEN
      start_date=1455.5.12
      end_date=9999.1.1
    }
    annul_treaties={
      first=SAV
      second=FRA
      start_date=1455.5.12
    }
  }
}
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.eu4"
            path.write_text(text, encoding="utf-8")
            parsed = scan_save(
                path, annul_country="FRA", annul_partners=["GEN", "SAV"])
        query = parsed["query"]
        self.assertTrue(query["annul_exact_pair_present"])
        self.assertTrue(query["annul_reverse_pair_present"])
        self.assertEqual("FRA", query["annul_matching_records"][0]["country"])
        self.assertEqual("GEN", query["annul_matching_records"][0]["partner"])
        self.assertEqual("SAV", query["annul_reverse_matching_records"][0]["country"])
        self.assertEqual("FRA", query["annul_reverse_matching_records"][0]["partner"])
        self.assertEqual("9999.1.1",
                         query["annul_matching_records"][0]["end_date_raw"])
        self.assertIsNone(query["annul_reverse_matching_records"][0]["end_date_raw"])

    def test_real_r53_inbound_pending_counts_all_selected_annul_partners(self):
        fixture_path = (Path(__file__).resolve().parent / "fixtures"
                        / "peace_annul_r53_inbound_pending.json")
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertEqual(
            "work/runtime/diplomacy-query-20261018-r53-peace-c-inbound-pending/"
            "inbound-fixture-001/report.json",
            fixture["source_report"])
        self.assertEqual("failed", fixture["source_status_before_checker_fix"])
        self.assertFalse(
            fixture["source_checks_before_checker_fix"]["annul_treaties_selected"])

        dispatch = fixture["dispatch"]
        pending = fixture["pending"]
        self.assertEqual(3, pending[0]["peace"]["selected_term_count"])
        self.assertTrue(_native_annul_treaties_contract(
            dispatch, pending, country="FRA", partners=["GEN", "PAP"],
            direction="demand"))

        wrong_count = copy.deepcopy(pending)
        wrong_count[0]["peace"]["selected_term_count"] = 2
        self.assertFalse(_native_annul_treaties_contract(
            dispatch, wrong_count, country="FRA", partners=["GEN", "PAP"],
            direction="demand"))

        single_partner = copy.deepcopy(pending)
        single_partner[0]["peace"]["selected_term_count"] = 2
        self.assertTrue(_native_annul_treaties_contract(
            dispatch, single_partner, country="FRA", partners=["GEN"],
            direction="demand"))


if __name__ == "__main__":
    unittest.main()
