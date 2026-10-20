from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from work import inspect_peace_save_pair
from work import probe_peace_effect_state
from work import run_peace_inbound_fixture as fixture
from work import run_peace_inbound_response as inbound
from work import run_peace_outbound_execution as outbound
from work import validate_peace_inbound_reload as inbound_reload
from work import validate_peace_outbound_reload as outbound_reload


WAR_ID = "war_0123456789abcdef_01234567"
DATE_RAW = 56548944
PAIR = ("FRA", "ENG")


def _c_term() -> dict[str, str]:
    return {
        "action_id": "concede_defeat",
        "conceding_country": PAIR[0],
        "beneficiary": PAIR[1],
    }


def _c_effect(*, accepted: bool, after_conceding: int = 5000) -> dict[str, object]:
    return {
        "conceding_country": PAIR[0],
        "beneficiary": PAIR[1],
        "conceding_prestige_before_raw": 10000,
        "conceding_prestige_after_raw": after_conceding,
        "conceding_prestige_delta_raw": after_conceding - 10000,
        "beneficiary_prestige_before_raw": 8000,
        "beneficiary_prestige_after_raw": 9000 if accepted else 8000,
        "beneficiary_prestige_delta_raw": 1000 if accepted else 0,
        "prestige_scale": 1000,
        "values_readable": True,
        "verified": accepted,
    }


def _complete_money_effect() -> dict[str, object]:
    return {
        "amount_raw": 1000,
        "payer": PAIR[0],
        "paid_raw": 1000,
        "credits": [{"country": PAIR[1], "amount_raw": 1000}],
        "verified": True,
    }


def _complete_province_effect() -> dict[str, object]:
    return {
        "province_id": 177,
        "beneficiary": PAIR[1],
        "owner_before": PAIR[0],
        "owner_after": PAIR[1],
        "controller_before": PAIR[0],
        "controller_after": PAIR[1],
        "verified": True,
    }


def _native_probe(*, accepted: bool, after_conceding: int = 5000) -> dict[str, object]:
    effect = _c_effect(accepted=accepted, after_conceding=after_conceding)
    return {
        "status": "ok",
        "snapshot": {"runtime": {
            "current_raw_date": DATE_RAW,
            "countries": [
                {"tag": PAIR[0], "prestige_readable": True,
                 "prestige_scale": 1000,
                 "prestige_raw": effect["conceding_prestige_after_raw"]},
                {"tag": PAIR[1], "prestige_readable": True,
                 "prestige_scale": 1000,
                 "prestige_raw": effect["beneficiary_prestige_after_raw"]},
            ],
            "provinces": [],
            "war_reparations": None,
            "transfer_trade_power": None,
        }},
    }


def _save_probe(*, accepted: bool, after_conceding: int = 5000) -> dict[str, object]:
    effect = _c_effect(accepted=accepted, after_conceding=after_conceding)
    return {
        "status": "ok",
        "parsed": {"countries": {
            PAIR[0]: {
                "complete": True,
                "prestige_raw": effect["conceding_prestige_after_raw"],
                "prestige_scale": 1000,
                "prestige": {"found": True, "raw": "5.000"},
            },
            PAIR[1]: {
                "complete": True,
                "prestige_raw": effect["beneficiary_prestige_after_raw"],
                "prestige_scale": 1000,
                "prestige": {"found": True, "raw": "9.000"},
            },
        }, "provinces": {}},
    }


def _response(*, decision: str, accepted: bool,
              terms: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "action_id": "peace_offer",
        "family": "peace",
        "actor": "ENG",
        "recipient": "FRA",
        "phase": decision,
        "war_before": True,
        "war_after": not accepted,
        "pending_removed": True,
        "response_verified": True,
        "request_binding_verified": True,
        "native_outcome": "accepted" if accepted else "rejected",
        "terms_verified": accepted,
        "date_raw": DATE_RAW,
        "peace_context": {
            "war_id": WAR_ID,
            "direction": "demand",
            "original_actor": "ENG",
            "original_recipient": "FRA",
            "complete": True,
            "selected_terms_complete": True,
            "terms": terms or [_c_term()],
        },
        "effects": {
            "complete": True,
            "date_unchanged": True,
            "currency_scale": 1000,
            "money": None,
            "provinces": [],
            "war_reparations": None,
            "transfer_trade_power": None,
            "concede_defeat": _c_effect(accepted=accepted),
        },
    }


class PeaceConcedeDefeatRunnerTests(unittest.TestCase):
    def test_c_builder_supports_all_existing_term_combinations(self) -> None:
        cases = {
            "c": {},
            "mc": {"with_money": "1.0"},
            "pc": {"province_ids": [177]},
            "rc": {"with_reparations": True},
            "tc": {"with_trade_power": True, "trade_power_source": "UTR"},
            "mprtc": {
                "with_money": "1.0", "province_ids": [177],
                "with_reparations": True, "with_trade_power": True,
                "trade_power_source": "UTR",
            },
        }
        for direction in ("demand", "offer"):
            for mask, options in cases.items():
                with self.subTest(direction=direction, mask=mask):
                    parameters = outbound._build_parameters(
                        "concede_defeat", WAR_ID, "10.0",
                        177 if "p" in mask else None, None, direction,
                        **options)
                    terms = parameters["peace_context"]["terms"]
                    self.assertEqual(mask, "".join(
                        {"demand_ducats": "m", "cede_province": "p",
                         "war_reparations": "r", "transfer_trade_power": "t",
                         "concede_defeat": "c"}[term["action_id"]]
                        for term in terms))
                    concede = terms[-1]
                    self.assertEqual("concede_defeat", concede["action_id"])
                    self.assertEqual(
                        ("ENG", "FRA") if direction == "demand"
                        else ("FRA", "ENG"),
                        (concede["conceding_country"], concede["beneficiary"]))
                    expected = outbound._expected_native_fields(
                        "concede_defeat", parameters)
                    self.assertEqual(mask, expected["term_mask"])
                    self.assertEqual(concede["conceding_country"],
                                     expected["conceding_country"])
                    self.assertEqual(concede["beneficiary"],
                                     expected["concede_beneficiary"])

    def test_c_receipt_and_fixture_contract_bind_native_roles(self) -> None:
        parameters = outbound._build_parameters(
            "concede_defeat", WAR_ID, "10.0", None, None, "offer")
        expected = outbound._expected_native_fields("concede_defeat", parameters)
        event = {**expected, "event": "native_peace_submission_result"}
        self.assertEqual("FRA", event["conceding_country"])
        self.assertEqual("ENG", event["concede_beneficiary"])
        dispatched = [{
            "concede_defeat_requested": True,
            "reparations_requested": False,
            "trade_power_requested": False,
            "direction": "demand",
        }]
        pending = [{"peace": {
            "complete": True,
            "term_count": 5,
            "selected_term_count": 2,
            "participant_counts": [1, 1, 0, 0],
            "flag40": 1,
            "direction41": 1,
            "preview208": 0,
        }}]
        self.assertTrue(fixture._native_concede_defeat_contract(
            dispatched, pending))
        self.assertIn("CONCEDE_DEFEAT", fixture._fixture_wire(
            "concede_defeat", "demand", None))

    def test_c_effect_contract_preserves_nonzero_rejection_penalty(self) -> None:
        parameters = outbound._build_parameters(
            "concede_defeat", WAR_ID, "10.0", None, None, "offer")
        expected = outbound._expected_native_fields("concede_defeat", parameters)
        for accepted in (True, False):
            result = {
                **expected,
                "date_raw": DATE_RAW,
                "request_id": "c-runner",
                "outcome": "accepted" if accepted else "rejected",
                "response_verified": True,
                "request_binding_verified": True,
                "execution_verified": accepted,
                "terms_verified": accepted,
                "war_before": True,
                "war_after": not accepted,
                "effects": {
                    "complete": True,
                    "date_unchanged": True,
                    "currency_scale": 1000,
                    "money": None,
                    "provinces": [],
                    "concede_defeat": _c_effect(accepted=accepted),
                },
            }
            contract = outbound._result_contract(
                {"status": "accepted" if accepted else "rejected",
                 "request_id": "c-runner",
                 "result": result}, "concede_defeat", parameters,
                DATE_RAW, {"complete": True, "pair_at_war": True},
                {"complete": True, "pair_at_war": not accepted})
            self.assertTrue(contract["all"], contract)
            if not accepted:
                self.assertFalse(result["effects"]["concede_defeat"]["verified"])
                self.assertTrue(contract["effects_contract"]["checks"].get(
                    "concede_defeat_verified"))

    def test_inbound_public_projection_rejects_incomplete_c_money_province_effects(self) -> None:
        terms = [
            {"action_id": "demand_ducats", "amount": "1.0"},
            {"action_id": "cede_province", "province_ids": [177],
             "beneficiary": "ENG"},
            _c_term(),
        ]
        projected = _response(decision="accept", accepted=True, terms=terms)
        projected["effects"]["money"] = {"amount_raw": 1000,
                                           "verified": True}
        projected["effects"]["provinces"] = []
        contract = inbound._public_effect_contract(
            {"result": projected}, "accept")
        self.assertFalse(contract["all"])
        self.assertFalse(contract["checks"]["money_province_full_effects"])
        self.assertTrue(contract["checks"]["concede_defeat_verified"])
        self.assertTrue(contract["checks"]["effects_money_empty"])
        self.assertTrue(contract["checks"]["effects_provinces_empty"])

    def test_inbound_public_projection_accepts_c_with_complete_money_and_province_effects(self) -> None:
        terms = [
            {"action_id": "demand_ducats", "amount": "1.0",
             "payer": PAIR[0], "claimant": PAIR[1]},
            {"action_id": "cede_province", "province_ids": [177],
             "beneficiary": PAIR[1]},
            _c_term(),
        ]
        projected = _response(decision="accept", accepted=True, terms=terms)
        projected["effects"]["money"] = _complete_money_effect()
        projected["effects"]["provinces"] = [_complete_province_effect()]
        contract = inbound._public_effect_contract(
            {"result": projected}, "accept")
        self.assertTrue(contract["all"], contract)
        self.assertTrue(contract["checks"]["money_province_full_effects"])
        self.assertTrue(contract["checks"]["concede_defeat_verified"])
        self.assertTrue(contract["checks"]["effects_money_empty"])
        self.assertTrue(contract["checks"]["effects_provinces_empty"])

    def test_prestige_parser_and_reload_comparator_use_scale_1000(self) -> None:
        text = """EU4txt
date=1455.1.5
countries={
 FRA={
  treasury=1.000
  prestige=5.000
 }
 ENG={
  treasury=2.000
  prestige=9.000
 }
}
"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = root / "before.eu4"
            after = root / "after.eu4"
            before.write_text(text, encoding="utf-8")
            after.write_text(text.replace("prestige=5.000", "prestige=7.000"),
                             encoding="utf-8")
            payload = inspect_peace_save_pair.build_payload(
                before, after, "FRA", "ENG", ())
        self.assertEqual(5000, payload["before"]["countries"]["FRA"]["prestige_raw"])
        self.assertEqual(7000, payload["after"]["countries"]["FRA"]["prestige_raw"])
        self.assertEqual(2000, payload["comparison"]["countries"]["FRA"]
                         ["prestige"]["delta_raw"])
        self.assertEqual(0xCF8, probe_peace_effect_state.PRESTIGE_OFFSET)
        self.assertEqual(1000, probe_peace_effect_state.PRESTIGE_SCALE1000)

        effects = {"concede_defeat": _c_effect(accepted=False)}
        rejected = outbound_reload._compare_concede_defeat_effect_state(
            _native_probe(accepted=False), _save_probe(accepted=False),
            effects, PAIR, "rejected")
        self.assertTrue(rejected["all"], rejected)
        self.assertEqual(-5000, rejected["public_effect"][
            "conceding_prestige_delta_raw"])
        accepted = outbound_reload._compare_concede_defeat_effect_state(
            _native_probe(accepted=True), _save_probe(accepted=True),
            {"concede_defeat": _c_effect(accepted=True)}, PAIR, "accepted")
        self.assertTrue(accepted["all"], accepted)

    def test_inbound_reload_passes_c_to_shared_after_state_comparison(self) -> None:
        accepted = _c_effect(accepted=True)
        source = {
            "effects_summary": {
                "applicable": True, "all": True, "decision": "accept",
                "mixed": False, "effects": {"concede_defeat": accepted},
                "reparations_pair": None, "trade_power_pair": None,
                "concede_defeat_pair": PAIR,
            },
            "decision": "accept", "outcome": "accepted",
            "action_id": "peace_offer",
        }
        execution = {
            "request_id": "c-reload",
            "actor": "ENG", "recipient": "FRA",
            "parameters": {"execute": {"peace_context": {
                "terms": [_c_term()],
            }}},
            "result_contract": {"effects_contract": {"all": True}},
        }
        native = _native_probe(accepted=True)
        saved = _save_probe(accepted=True)
        with patch.object(inbound_reload, "_run_effect_probe",
                             return_value=native), \
                patch.object(inbound_reload, "_stream_save_effect_state",
                             return_value=saved):
            report = inbound_reload._peace_effect_reload_contract(
                source, execution, {}, object(), DATE_RAW,
                Path("c-reload-evidence"))
        self.assertTrue(report["all"], report)
        self.assertEqual(PAIR, (
            report["concede_defeat_pair"]["conceding_country"],
            report["concede_defeat_pair"]["beneficiary"]))


if __name__ == "__main__":
    unittest.main()
