from __future__ import annotations

import unittest

from work import inspect_peace_save_pair as save_pair
from work import probe_peace_effect_state as probe
from work import run_peace_inbound_fixture as fixture
from work import run_peace_inbound_response as inbound
from work import run_peace_outbound_execution as outbound
from work import validate_peace_outbound_reload as reload_validator


WAR_ID = "war_0123456789abcdef_01234567"
DATE_RAW = 56548944


def _effect(action: str, *, accepted: bool = True) -> dict[str, object]:
    if action == "force_religion":
        return {
            "country": "FRA", "beneficiary": "ENG",
            "religion_before": "catholic", "religion_after": "protestant",
            "beneficiary_religion_before": "protestant",
            "beneficiary_religion_after": "protestant",
            "capital_religion_before": "catholic",
            "capital_religion_after": "protestant",
            "values_readable": True, "verified": accepted,
        }
    result: dict[str, object] = {
        "country": "FRA", "beneficiary": "ENG",
        "humiliated_before": False, "humiliated_after": accepted,
        "country_prestige_before_raw": 10000,
        "country_prestige_after_raw": 9000,
        "country_prestige_delta_raw": -1000,
        "beneficiary_prestige_before_raw": 8000,
        "beneficiary_prestige_after_raw": 9000,
        "beneficiary_prestige_delta_raw": 1000,
        "prestige_scale": 1000, "values_readable": True,
        "verified": accepted,
    }
    if action == "show_strength":
        result.update({
            "powers_before": [101, 202, 303],
            "powers_after": [151, 252, 353],
            "powers_delta": [50, 50, 50], "powers_requested": 100,
        })
    return result


def _response(action: str, *, accepted: bool = True) -> dict[str, object]:
    return {
        "action_id": "peace_offer", "family": "peace",
        "war_before": True, "war_after": not accepted,
        "pending_removed": True, "native_outcome": "accepted" if accepted else "rejected",
        "terms_verified": accepted,
        "peace_context": {
            "war_id": WAR_ID, "direction": "demand",
            "original_actor": "ENG", "original_recipient": "FRA",
            "complete": True, "selected_terms_complete": True,
            "terms": [{"action_id": action, "country": "FRA", "beneficiary": "ENG"}],
        },
        "effects": {
            "complete": True, "date_unchanged": True, "currency_scale": 1000,
            "money": None, "provinces": [], "war_reparations": None,
            action: _effect(action, accepted=accepted),
        },
    }


class PeaceSpecialRunnerTests(unittest.TestCase):
    def test_primary_builders_and_canonical_masks(self) -> None:
        for action, letter in (("humiliate_rival", "h"),
                               ("show_strength", "s"),
                               ("force_religion", "f")):
            parameters = outbound._build_parameters(
                action, WAR_ID, "10.0", None, None, "demand")
            term = parameters["peace_context"]["terms"][0]
            self.assertEqual(
                {"action_id": action, "country": "ENG", "beneficiary": "FRA"},
                term)
            self.assertEqual(letter, outbound._expected_native_fields(
                action, parameters)["term_mask"])

        mixed = outbound._build_parameters(
            "show_strength", WAR_ID, "10.0", 177, None, "demand",
            province_ids=[177], with_money="1.0", with_reparations=True,
            with_trade_power=True, trade_power_source="UTR")
        self.assertEqual("mprts", outbound._expected_native_fields(
            "show_strength", mixed)["term_mask"])

    def test_native_fixture_wire_and_selected_count(self) -> None:
        for action, kind in (("humiliate_rival", "HUMILIATE_RIVAL"),
                             ("show_strength", "SHOW_STRENGTH"),
                             ("force_religion", "FORCE_RELIGION")):
            self.assertEqual(
                f"TEST_ONLY ENG_PEACE_FRA_{kind}_PENDING\n",
                fixture._fixture_wire(action, "demand", None))
            flags = {
                "humiliate_rival_requested": action == "humiliate_rival",
                "show_strength_requested": action == "show_strength",
                "force_religion_requested": action == "force_religion",
                "reparations_requested": False,
                "trade_power_requested": False,
                "concede_defeat_requested": False,
                "annul_treaties_requested": False,
                "direction": "demand",
            }
            pending = [{"peace": {
                "complete": True, "term_count": 9,
                "selected_term_count": 2, "flag40": 1,
                "direction41": 1, "preview208": 0,
            }}]
            self.assertTrue(fixture._native_special_contract(
                [flags], pending, term=action))
            pending[0]["peace"]["selected_term_count"] = 3
            self.assertFalse(fixture._native_special_contract(
                [flags], pending, term=action))

        self.assertEqual(
            "TEST_ONLY ENG_PEACE_FRA_SHOW_STRENGTH_OFFER_PENDING\n",
            fixture._fixture_wire("show_strength", "offer", None))
        offer_flags = {
            "humiliate_rival_requested": False,
            "show_strength_requested": True,
            "force_religion_requested": False,
            "reparations_requested": False,
            "trade_power_requested": False,
            "concede_defeat_requested": False,
            "annul_treaties_requested": False,
            "direction": "offer",
        }
        offer_pending = [{
            "actor": "ENG", "mirror": "ENG", "recipient": "FRA",
            "decision_country": "FRA", "decision_country_verified": True,
            "peace": {
                "complete": True, "term_count": 9,
                "selected_term_count": 2, "flag40": 1,
                "direction41": 0, "preview208": 0,
            },
        }]
        self.assertTrue(fixture._native_special_contract(
            [offer_flags], offer_pending,
            term="show_strength", direction="offer"))
        offer_pending[0]["peace"]["selected_term_count"] = 3
        self.assertFalse(fixture._native_special_contract(
            [offer_flags], offer_pending,
            term="show_strength", direction="offer"))
        offer_pending[0]["peace"]["selected_term_count"] = 2
        offer_pending[0]["recipient"] = "ENG"
        self.assertFalse(fixture._native_special_contract(
            [offer_flags], offer_pending,
            term="show_strength", direction="offer"))

        self.assertEqual(
            "TEST_ONLY ENG_PEACE_FRA_TRADE_POWER_OFFER_PENDING UTR\n",
            fixture._fixture_wire("transfer_trade_power", "offer", "UTR"))
        for unsupported in ("humiliate_rival", "force_religion"):
            with self.assertRaisesRegex(ValueError, "SPECIAL_OFFER_UNSUPPORTED"):
                fixture._fixture_wire(unsupported, "offer", None)
        with self.assertRaisesRegex(ValueError, "SPECIAL_SOURCE_UNSUPPORTED"):
            fixture._fixture_wire("show_strength", "offer", "UTR")

    def test_public_effect_contract_uses_real_projection(self) -> None:
        for action in ("humiliate_rival", "show_strength", "force_religion"):
            final = _response(action)
            contract = inbound._public_effect_contract({"result": final}, "accept")
            self.assertTrue(contract["all"], (action, contract))
            rejected = inbound._public_effect_contract(
                {"result": _response(action, accepted=False)}, "reject")
            self.assertTrue(rejected["all"], (action, rejected))

    def test_bounded_probe_helpers_and_save_country_fields(self) -> None:
        memory: dict[int, bytes] = {}
        def put(address: int, value: bytes) -> None:
            memory[address] = value
        def read(address: int, size: int) -> bytes:
            return memory[address][:size]
        def qword(address: int) -> int:
            return int.from_bytes(read(address, 8), "little")
        def integer(address: int, size: int = 4, signed: bool = True) -> int:
            return int.from_bytes(read(address, size), "little", signed=signed)
        country = {"pointer": 0x100000, "handle": 0x20000001,
                   "tag": "FRA", "slot": 1}
        beneficiary = {"pointer": 0x110000, "handle": 0x30000002,
                       "tag": "ENG", "slot": 2}
        # The list belongs to the beneficiary (winner).  Put the defeated
        # country in that list; the reverse list must not affect the result.
        put(0x110000 + probe.HUMILIATED_BEGIN_OFFSET,
            (0x120000).to_bytes(8, "little"))
        put(0x110000 + probe.HUMILIATED_COUNT_OFFSET,
            (1).to_bytes(4, "little", signed=True))
        put(0x120000, (0x20000001).to_bytes(8, "little"))
        state = probe._read_humiliated_state(country, beneficiary, qword, integer)
        self.assertTrue(state["complete"])
        self.assertTrue(state["present"])
        self.assertTrue(state["humiliated"])

        # A list containing only the beneficiary on the defeated-country row
        # is the reverse direction and must not count as FRA -> ENG.
        put(0x100000 + probe.HUMILIATED_BEGIN_OFFSET,
            (0x130000).to_bytes(8, "little"))
        put(0x100000 + probe.HUMILIATED_COUNT_OFFSET,
            (1).to_bytes(4, "little", signed=True))
        put(0x130000, (0x30000002).to_bytes(8, "little"))
        put(0x110000 + probe.HUMILIATED_COUNT_OFFSET,
            (0).to_bytes(4, "little", signed=True))
        self.assertFalse(
            probe._read_humiliated_state(country, beneficiary, qword, integer)[
                "present"])

        # Native Show Strength reads the beneficiary (winner) powers.  Keep
        # both rows distinct so a country-side read cannot accidentally pass.
        for offset, value in zip(probe.POWERS_OFFSETS, (11, 22, 33)):
            put(beneficiary["pointer"] + offset,
                value.to_bytes(4, "little", signed=True))
        self.assertEqual(
            [11, 22, 33], probe._read_powers(beneficiary, integer)["values"])
        self.assertEqual(1, probe._read_powers(beneficiary, integer)["scale"])

        short_pointer = 0x130000
        short_key = b"catholic"
        put(short_pointer + probe.RELIGION_STRING_SIZE_OFFSET,
            len(short_key).to_bytes(8, "little"))
        put(short_pointer + probe.RELIGION_STRING_CAPACITY_OFFSET,
            (15).to_bytes(8, "little"))
        put(short_pointer + probe.RELIGION_STRING_OFFSET, short_key)
        self.assertEqual(
            ("catholic", True), probe._read_religion_key(
                short_pointer, read, integer))

        long_pointer = 0x140000
        long_data_pointer = 0x150000
        long_key = b"long_religion_key"
        put(long_pointer + probe.RELIGION_STRING_SIZE_OFFSET,
            len(long_key).to_bytes(8, "little"))
        put(long_pointer + probe.RELIGION_STRING_CAPACITY_OFFSET,
            (31).to_bytes(8, "little"))
        put(long_pointer + probe.RELIGION_STRING_OFFSET,
            long_data_pointer.to_bytes(8, "little"))
        put(long_data_pointer, long_key)
        self.assertEqual(
            ("long_religion_key", True), probe._read_religion_key(
                long_pointer, read, integer))

        text = """FRA={
 treasury=1.000
 prestige=5.000
 religion=catholic
 powers={
  1
  2
  3
 }
 flags={
  humiliated_rival=1455.5.18
 }
 humiliated_countries={
  ENG
 }
 power_projection={
  target="ENG"
  modifier="humiliated_rival"
  current=30.000
 }
}
"""
        capture = save_pair.BlockCapture(
            "FRA", "FRA", 1, 8, text, True, len(text), len(text))
        parsed = save_pair._parse_country(capture, "FRA")
        self.assertEqual("catholic", parsed["religion"]["value"])
        self.assertEqual([1, 2, 3], parsed["powers"]["values"])
        self.assertEqual("1455.5.18", parsed["humiliation"]["humiliated_rival"]["value"])
        self.assertEqual(["ENG"], parsed["humiliation"]["humiliated_countries"]["tags"])
        self.assertEqual(
            "humiliated_rival",
            parsed["humiliation"]["humiliated_power_projection"][0]["modifier"]["value"],
        )

    def test_show_strength_reload_uses_beneficiary_powers(self) -> None:
        public_effect = _effect("show_strength")
        native_runtime = {
            "show_strength": {
                "country": "FRA", "beneficiary": "ENG", "complete": True,
                "country_prestige_raw": 9000,
                "beneficiary_prestige_raw": 9000,
                "powers": {"values": [151, 252, 353]},
                "present": True,
            }
        }
        parsed = {
            "countries": {
                "FRA": {
                    "complete": True,
                    "treasury": {"found": True, "raw": "1.000"},
                    "prestige": {"found": True, "raw": "9.000"},
                    "powers": {"values": [7, 8, 9]},
                    "humiliation": {
                        "relation_readable": True,
                        "humiliated_countries": {"found": False, "tags": []},
                    },
                },
                "ENG": {
                    "complete": True,
                    "treasury": {"found": True, "raw": "1.000"},
                    "prestige": {"found": True, "raw": "9.000"},
                    "powers": {"values": [151, 252, 353]},
                    "humiliation": {
                        "relation_readable": True,
                        "humiliated_countries": {"found": True, "tags": ["FRA"]},
                    },
                },
            }
        }
        comparison = reload_validator._compare_special_effect_state(
            {"snapshot": {"runtime": native_runtime}},
            {"parsed": parsed},
            {"show_strength": public_effect},
            ("FRA", "ENG"), "show_strength", "accepted")
        self.assertTrue(comparison["all"], comparison)


if __name__ == "__main__":
    unittest.main()
