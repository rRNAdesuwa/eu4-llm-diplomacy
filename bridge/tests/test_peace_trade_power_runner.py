from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from work.run_peace_outbound_execution import (
    PeaceExecutionError,
    _TRADE_POWER_ACTION,
    _build_parameters,
    _expected_native_fields,
    _result_contract,
    _trade_power_source_for_direction,
    _wire_submission_correlation,
)


WAR_ID = "war_0123456789abcdef_01234567"


class PeaceTradePowerRunnerTests(unittest.TestCase):
    def test_direction_bound_trade_term_and_all_canonical_masks(self):
        cases = {
            "t": (_TRADE_POWER_ACTION, {}),
            "mt": ("demand_ducats", {"with_trade_power": True}),
            "pt": ("cede_province", {"with_trade_power": True}),
            "rt": ("war_reparations", {"with_trade_power": True}),
            "mpt": ("cede_province", {
                "with_money": "1.0", "with_trade_power": True}),
            "mrt": ("demand_ducats", {
                "with_reparations": True, "with_trade_power": True}),
            "prt": ("cede_province", {
                "with_reparations": True, "with_trade_power": True}),
            "mprt": ("cede_province", {
                "with_money": "1.0", "with_reparations": True,
                "with_trade_power": True}),
        }
        expected_term_ids = {
            "t": [_TRADE_POWER_ACTION],
            "mt": ["demand_ducats", _TRADE_POWER_ACTION],
            "pt": ["cede_province", _TRADE_POWER_ACTION],
            "rt": ["war_reparations", _TRADE_POWER_ACTION],
            "mpt": ["demand_ducats", "cede_province", _TRADE_POWER_ACTION],
            "mrt": ["demand_ducats", "war_reparations", _TRADE_POWER_ACTION],
            "prt": ["cede_province", "war_reparations", _TRADE_POWER_ACTION],
            "mprt": ["demand_ducats", "cede_province",
                      "war_reparations", _TRADE_POWER_ACTION],
        }
        for direction in ("demand", "offer"):
            expected_source = "ENG" if direction == "demand" else "FRA"
            expected_beneficiary = "FRA" if direction == "demand" else "ENG"
            for mask, (primary, options) in cases.items():
                with self.subTest(direction=direction, mask=mask):
                    parameters = _build_parameters(
                        primary, WAR_ID, "10.0",
                        177 if "p" in mask else None,
                        None, direction,
                        province_ids=[177] if "p" in mask else None,
                        **options)
                    terms = parameters["peace_context"]["terms"]
                    self.assertEqual(expected_term_ids[mask],
                                     [term["action_id"] for term in terms])
                    self.assertEqual(mask, _expected_native_fields(
                        primary, parameters)["term_mask"])
                    trade = next(term for term in terms
                                 if term["action_id"] == _TRADE_POWER_ACTION)
                    self.assertEqual(expected_source, trade["source"])
                    self.assertEqual(expected_beneficiary, trade["beneficiary"])

    def test_transfer_primary_accepts_money_province_and_reparations_terms(self):
        parameters = _build_parameters(
            _TRADE_POWER_ACTION, WAR_ID, "10.0", 177, "FRA", "demand",
            province_ids=[177, 178], with_money="1.0",
            with_reparations=True)
        terms = parameters["peace_context"]["terms"]
        self.assertEqual(
            ["demand_ducats", "cede_province", "war_reparations",
             _TRADE_POWER_ACTION],
            [term["action_id"] for term in terms])
        self.assertEqual("mprt", _expected_native_fields(
            _TRADE_POWER_ACTION, parameters)["term_mask"])

    def test_explicit_third_country_source_binds_every_trade_power_term(self):
        for direction in ("demand", "offer"):
            with self.subTest(direction=direction):
                parameters = _build_parameters(
                    _TRADE_POWER_ACTION, WAR_ID, "10.0", None, None,
                    direction, trade_power_source="UTR")
                trade = parameters["peace_context"]["terms"][0]
                self.assertEqual("UTR", trade["source"])
                self.assertEqual(
                    "FRA" if direction == "demand" else "ENG",
                    trade["beneficiary"])
                expected = _expected_native_fields(
                    _TRADE_POWER_ACTION, parameters)
                self.assertEqual("UTR", expected["trade_power_source"])
                self.assertEqual(trade["beneficiary"],
                                 expected["trade_power_beneficiary"])

    def test_explicit_source_applies_to_combined_mask_and_invalid_tags_fail(self):
        parameters = _build_parameters(
            "demand_ducats", WAR_ID, "10.0", None, None, "demand",
            with_trade_power=True, trade_power_source="UTR")
        trade = parameters["peace_context"]["terms"][1]
        self.assertEqual("UTR", trade["source"])
        self.assertEqual("FRA", trade["beneficiary"])
        self.assertEqual(
            "UTR", _expected_native_fields(
                "demand_ducats", parameters)["trade_power_source"])
        with self.assertRaises(PeaceExecutionError) as raised:
            _build_parameters(
                _TRADE_POWER_ACTION, WAR_ID, "10.0", None, None, "demand",
                trade_power_source="not-a-tag")
        self.assertEqual("TRADE_POWER_SOURCE_INVALID", raised.exception.code)
        with self.assertRaises(PeaceExecutionError) as raised:
            _build_parameters(
                "demand_ducats", WAR_ID, "10.0", None, None, "demand",
                trade_power_source="UTR")
        self.assertEqual("TRADE_POWER_SOURCE_ACTION_INVALID", raised.exception.code)

    def test_direction_defaults_remain_canonical(self):
        self.assertEqual("ENG", _trade_power_source_for_direction("demand"))
        self.assertEqual("FRA", _trade_power_source_for_direction("offer"))

    def test_expected_native_and_wire_receipt_bind_trade_power_fields(self):
        parameters = _build_parameters(
            _TRADE_POWER_ACTION, WAR_ID, "10.0", None, None, "offer")
        expected = _expected_native_fields(_TRADE_POWER_ACTION, parameters)
        self.assertEqual("t", expected["term_mask"])
        self.assertEqual("FRA", expected["trade_power_source"])
        self.assertEqual("ENG", expected["trade_power_beneficiary"])
        event = {
            **expected,
            "event": "native_peace_submission_result",
            "session_id": "session-r50-trade",
            "request_id": "r50-trade-wire",
            "date_raw": 56548944,
            "submitted": False,
            "transport_verified": False,
            "request_binding_verified": False,
            "reason": "NATIVE_PEACE_AUTHORITY_SEED_FAILED",
        }
        with tempfile.TemporaryDirectory() as directory:
            event_path = Path(directory) / "events.jsonl"
            event_path.write_text(json.dumps(event) + "\n", encoding="utf-8")
            report = {
                "session": {"session_id": "session-r50-trade"},
                "request_id": "r50-trade-wire",
                "action_id": _TRADE_POWER_ACTION,
                "actor": "FRA", "recipient": "ENG", "phase": "initiate",
                "expected_date_raw": 56548944,
                "war_id": WAR_ID, "direction": "offer",
                "parameters": {"execute": parameters},
                "native_events": {"path": str(event_path)},
            }
            result = _wire_submission_correlation(report)
        self.assertEqual("observed", result["status"])
        self.assertTrue(result["checks"]["term_mask"])
        self.assertTrue(result["checks"]["trade_power_source"])
        self.assertTrue(result["checks"]["trade_power_beneficiary"])

        event["trade_power_beneficiary"] = "SAV"
        with tempfile.TemporaryDirectory() as directory:
            event_path = Path(directory) / "events.jsonl"
            event_path.write_text(json.dumps(event) + "\n", encoding="utf-8")
            report["native_events"] = {"path": str(event_path)}
            mismatch = _wire_submission_correlation(report)
        self.assertEqual("mismatch", mismatch["status"])
        self.assertFalse(mismatch["checks"]["trade_power_beneficiary"])

    def test_accepted_trade_power_effect_contract_allows_end_sentinel(self):
        parameters = _build_parameters(
            _TRADE_POWER_ACTION, WAR_ID, "10.0", None, None, "demand")
        expected = _expected_native_fields(_TRADE_POWER_ACTION, parameters)
        effects = {
            "complete": True,
            "date_unchanged": True,
            "currency_scale": 1000,
            "transfer_trade_power": {
                "source": "ENG", "beneficiary": "FRA",
                "present_before": False, "present_after": True,
                "start_date_raw": 56548930, "end_date_raw": -1,
                "amount_raw": 250, "amount_scale": 1000,
                "peace_treaty": True, "verified": True,
            },
        }
        final = {
            "status": "accepted",
            "request_id": "peace_contract_trade",
            "result": {
                **expected,
                "date_raw": 56548944,
                "request_id": "peace_contract_trade",
                "outcome": "accepted",
                "response_verified": True,
                "request_binding_verified": True,
                "execution_verified": True,
                "terms_verified": True,
                "war_before": True,
                "war_after": False,
                "effects": effects,
            },
        }
        result = _result_contract(
            final, _TRADE_POWER_ACTION, parameters, 56548944,
            {"complete": True, "pair_at_war": True},
            {"complete": True, "pair_at_war": False})
        self.assertTrue(result["all"])
        self.assertTrue(result["effects_contract"]["checks"][
            "transfer_trade_power_present_after"])
        self.assertTrue(result["effects_contract"]["checks"][
            "transfer_trade_power_start_before_date"])

        malformed = copy.deepcopy(final)
        malformed["result"]["effects"]["transfer_trade_power"].update({
            "present_after": False,
            "peace_treaty": False,
            "amount_raw": 0,
            "amount_scale": 0,
            "start_date_raw": 56548945,
        })
        rejected = _result_contract(
            malformed, _TRADE_POWER_ACTION, parameters, 56548944,
            {"complete": True, "pair_at_war": True},
            {"complete": True, "pair_at_war": False})
        self.assertFalse(rejected["all"])

    def test_rejected_trade_power_requires_false_verified_with_zero_dates(self):
        parameters = _build_parameters(
            _TRADE_POWER_ACTION, WAR_ID, "10.0", None, None, "offer")
        expected = _expected_native_fields(_TRADE_POWER_ACTION, parameters)
        final = {
            "status": "rejected",
            "request_id": "peace_contract_trade_rejected",
            "result": {
                **expected,
                "date_raw": 56548944,
                "request_id": "peace_contract_trade_rejected",
                "outcome": "rejected",
                "response_verified": True,
                "request_binding_verified": True,
                "execution_verified": False,
                "terms_verified": False,
                "war_before": True,
                "war_after": True,
                "effects": {
                    "transfer_trade_power": {
                        "source": "FRA", "beneficiary": "ENG",
                        "present_before": False, "present_after": False,
                        "start_date_raw": 0, "end_date_raw": 0,
                        "amount_raw": 0, "amount_scale": 0,
                        "peace_treaty": False, "verified": False,
                    },
                },
            },
        }
        result = _result_contract(
            final, _TRADE_POWER_ACTION, parameters, 56548944,
            {"complete": True, "pair_at_war": True},
            {"complete": True, "pair_at_war": True})
        self.assertTrue(result["all"])
        self.assertTrue(result["effects_contract"]["checks"][
            "transfer_trade_power_verified"])

        missing_effects = copy.deepcopy(final)
        del missing_effects["result"]["effects"]
        missing = _result_contract(
            missing_effects, _TRADE_POWER_ACTION, parameters, 56548944,
            {"complete": True, "pair_at_war": True},
            {"complete": True, "pair_at_war": True})
        self.assertFalse(missing["all"])

        bad = copy.deepcopy(final)
        bad["result"]["effects"]["transfer_trade_power"]["verified"] = True
        rejected = _result_contract(
            bad, _TRADE_POWER_ACTION, parameters, 56548944,
            {"complete": True, "pair_at_war": True},
            {"complete": True, "pair_at_war": True})
        self.assertFalse(rejected["all"])
        self.assertFalse(rejected["effects_contract"]["checks"][
            "transfer_trade_power_verified"])


if __name__ == "__main__":
    unittest.main()
