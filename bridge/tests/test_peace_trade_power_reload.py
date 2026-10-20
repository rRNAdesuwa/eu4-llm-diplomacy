from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from work import validate_peace_outbound_reload as validator


DATE_RAW = 56548944
OPEN_END = 0x29C77F8
PAIR = ("ENG", "FRA")


def _trade_term() -> dict[str, str]:
    return {
        "action_id": "transfer_trade_power",
        "source": PAIR[0],
        "beneficiary": PAIR[1],
    }


def _execution(*terms: dict[str, object], action: str = "transfer_trade_power",
               request_id: str = "trade-reload") -> dict[str, object]:
    return {
        "request_id": request_id,
        "actor": "FRA",
        "recipient": "ENG",
        "parameters": {
            "execute": {
                "peace_context": {
                    "terms": list(terms),
                },
            },
        },
        "result_contract": {"effects_contract": {"all": True}},
    }


def _accepted_source(*, mixed_money: bool = False) -> dict[str, object]:
    effects: dict[str, object] = {
        "complete": True,
        "date_unchanged": True,
        "currency_scale": 1000,
        "money": None,
        "provinces": [],
        "war_reparations": None,
        "transfer_trade_power": {
            "source": PAIR[0],
            "beneficiary": PAIR[1],
            "present_before": False,
            "present_after": True,
            "start_date_raw": DATE_RAW - 1,
            "end_date_raw": OPEN_END,
            "amount_raw": 500,
            "amount_scale": 1000,
            "peace_treaty": True,
            "verified": True,
        },
    }
    if mixed_money:
        effects["money"] = {
            "amount_raw": 1000,
            "payer": "ENG",
            "paid_raw": 1000,
            "credits": [{"country": "ENG", "amount_raw": 1000}],
            "verified": True,
        }
    return {
        "outcome": "executed",
        "action_id": "demand_ducats" if mixed_money else "transfer_trade_power",
        "effects": effects,
    }


def _rejected_source() -> dict[str, object]:
    return {
        "outcome": "rejected",
        "action_id": "transfer_trade_power",
        "effects": {
            "complete": True,
            "date_unchanged": True,
            "currency_scale": 1000,
            "money": None,
            "provinces": [],
            "war_reparations": None,
            "transfer_trade_power": {
                "source": PAIR[0],
                "beneficiary": PAIR[1],
                "present_before": False,
                "present_after": False,
                "start_date_raw": 0,
                "end_date_raw": 0,
                "amount_raw": 0,
                "amount_scale": 1000,
                "peace_treaty": False,
                "verified": False,
            },
        },
    }


def _native(*, present: bool = True) -> dict[str, object]:
    trade = {
        "source": PAIR[0],
        "beneficiary": PAIR[1],
        "present": present,
        "start_date_raw": DATE_RAW - 1 if present else 0,
        "end_date_raw": OPEN_END if present else 0,
        "amount_raw": 500 if present else 0,
        "amount_scale": 1000,
        "peace_treaty": present,
        "complete": True,
    }
    return {
        "status": "ok",
        "snapshot": {"runtime": {
            "current_raw_date": DATE_RAW,
            "countries": [],
            "provinces": [],
            "war_reparations": None,
            "transfer_trade_power": trade,
        }},
    }


def _save_probe(*, include_trade: bool, include_money: bool = False) -> dict[str, object]:
    country_block = (
        "countries={\n"
        "FRA={\n treasury=5.000\n}\n"
        "ENG={\n treasury=7.000\n}\n"
        "}\n"
        if include_money else "")
    trade_block = (
        "transfer_trade_power={\n"
        " amount=0.500\n"
        " is_enforced=yes\n"
        " first=ENG\n"
        " second=FRA\n"
        " start_date=1455.1.5\n"
        "}\n"
        if include_trade else "")
    gamestate = (
        "EU4txt\n"
        "date=1455.1.5\n"
        + country_block
        + trade_block
    ).encode("utf-8")
    directory = tempfile.TemporaryDirectory()
    path = Path(directory.name) / "effect.eu4"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("gamestate", gamestate)
    # Keep the TemporaryDirectory alive by attaching it to the returned
    # object.  The validator only receives the plain dictionary; the test
    # deletes the owner after the comparison completes.
    result = validator._stream_save_effect_state(
        {"save": {"path": str(path)}},
        ["ENG", "FRA"],
        [],
        trade_power_source=PAIR[0],
        trade_power_beneficiary=PAIR[1],
    )
    result["_temporary_directory"] = directory
    return result


class PeaceTradePowerReloadTests(unittest.TestCase):
    def _run(
            self,
            source: dict[str, object],
            execution: dict[str, object],
            native: dict[str, object],
            saved: dict[str, object],
            ) -> tuple[dict[str, object], object, object]:
        observations = {"all": True, "by_country": {}, "checks": {}}
        native_calls: list[dict[str, object]] = []
        save_calls: list[dict[str, object]] = []

        def fake_native(*args: object, **kwargs: object) -> dict[str, object]:
            native_calls.append(kwargs)
            return native

        def fake_save(*args: object, **kwargs: object) -> dict[str, object]:
            save_calls.append(kwargs)
            return saved

        with patch.object(
                validator, "_read_native_effect_observations",
                return_value=observations), patch.object(
                    validator, "_run_effect_probe",
                    side_effect=fake_native) as native_probe, patch.object(
                        validator, "_stream_save_effect_state",
                        side_effect=fake_save) as save_probe:
            result = validator._peace_effect_reload_contract(
                source, execution, {}, object(), DATE_RAW,
                Path("trade-power-reload-evidence"))
        self.assertEqual(1, native_probe.call_count)
        self.assertEqual(1, save_probe.call_count)
        self.assertEqual(1, len(native_calls))
        self.assertEqual(1, len(save_calls))
        self.assertEqual(PAIR[0], native_calls[0]["trade_power_source"])
        self.assertEqual(PAIR[1], native_calls[0]["trade_power_beneficiary"])
        self.assertEqual(PAIR[0], save_calls[0]["trade_power_source"])
        self.assertEqual(PAIR[1], save_calls[0]["trade_power_beneficiary"])
        return result, native_probe, save_probe

    def test_requested_pair_comes_from_terms_even_when_money_is_primary(self) -> None:
        execution = _execution(
            {"action_id": "demand_ducats", "amount": "10.0",
             "payer": "ENG", "claimant": "FRA"},
            _trade_term(),
            action="demand_ducats")
        self.assertEqual(PAIR, validator._requested_peace_trade_power_pair(execution))

    def test_accepted_t_only_compares_source_native_and_streamed_save(self) -> None:
        execution = _execution(_trade_term())
        source = _accepted_source()
        saved = _save_probe(include_trade=True)
        try:
            result, _, _ = self._run(source, execution, _native(), saved)
        finally:
            saved.pop("_temporary_directory").cleanup()

        self.assertTrue(result["all"])
        checks = result["comparison"]["checks"]
        for name in (
                "public_transfer_trade_power_source",
                "public_transfer_trade_power_present_after",
                "public_transfer_trade_power_amount",
                "public_transfer_trade_power_scale",
                "public_transfer_trade_power_end_sentinel",
                "native_transfer_trade_power_present",
                "native_transfer_trade_power_complete",
                "native_transfer_trade_power_amount",
                "native_transfer_trade_power_scale",
                "native_transfer_trade_power_end_sentinel",
                "save_transfer_trade_power_exact_pair",
                "save_transfer_trade_power_amount",
                "save_transfer_trade_power_scale",
                "save_transfer_trade_power_enforced",
                "save_transfer_trade_power_end_normalized"):
            self.assertTrue(checks[name], name)
        self.assertEqual(OPEN_END, result["comparison"][
            "transfer_trade_power"]["expected"]["open_end_raw"])

    def test_accepted_mixed_money_and_t_uses_terms_and_keeps_t_contract(self) -> None:
        execution = _execution(
            {"action_id": "demand_ducats", "amount": "10.0",
             "payer": "ENG", "claimant": "FRA"},
            _trade_term(), action="demand_ducats")
        source = _accepted_source(mixed_money=True)
        saved = _save_probe(include_trade=True, include_money=True)
        try:
            observations = {
                "all": True,
                "by_country": {
                    "ENG": {"treasury_after_raw": 7000},
                    "FRA": {"treasury_after_raw": 5000},
                },
                "checks": {},
            }
            native = _native()
            native["snapshot"]["runtime"]["countries"] = [
                {"tag": "ENG", "treasury_readable": True,
                 "currency_scale": 1000, "treasury_raw": 7000},
                {"tag": "FRA", "treasury_readable": True,
                 "currency_scale": 1000, "treasury_raw": 5000},
            ]
            native_calls: list[dict[str, object]] = []
            save_calls: list[dict[str, object]] = []
            with patch.object(
                    validator, "_read_native_effect_observations",
                    return_value=observations), patch.object(
                        validator, "_run_effect_probe",
                        side_effect=lambda *args, **kwargs: (
                            native_calls.append(kwargs) or native)), patch.object(
                                validator, "_stream_save_effect_state",
                                side_effect=lambda *args, **kwargs: (
                                    save_calls.append(kwargs) or saved)):
                result = validator._peace_effect_reload_contract(
                    source, execution, {}, object(), DATE_RAW,
                    Path("trade-power-mixed-evidence"))
        finally:
            saved.pop("_temporary_directory").cleanup()
        self.assertTrue(result["all"])
        self.assertTrue(result["comparison"]["checks"][
            "native_treasury_after_matches_private"])
        self.assertTrue(result["comparison"]["checks"][
            "native_transfer_trade_power_present"])
        self.assertEqual(PAIR[0], native_calls[0]["trade_power_source"])
        self.assertEqual(PAIR[1], save_calls[0]["trade_power_beneficiary"])

    def test_rejected_t_absence_is_a_successful_complete_probe_and_save_read(self) -> None:
        execution = _execution(_trade_term(), request_id="trade-rejected")
        saved = _save_probe(include_trade=False)
        try:
            result, _, _ = self._run(
                _rejected_source(), execution, _native(present=False), saved)
        finally:
            saved.pop("_temporary_directory").cleanup()

        self.assertTrue(result["all"])
        checks = result["comparison"]["checks"]
        self.assertTrue(checks["source_transfer_trade_power_absent"])
        self.assertTrue(checks["native_transfer_trade_power_complete"])
        self.assertTrue(checks["native_transfer_trade_power_present_absent"])
        self.assertTrue(checks["save_transfer_trade_power_exact_pair_absent"])
        self.assertTrue(checks["save_transfer_trade_power_matching_records_absent"])
        self.assertTrue(result["public_summary"]["rejected_trade_power_only"])

    def test_end_normalization_never_invents_ten_year_duration(self) -> None:
        self.assertTrue(validator._trade_power_saved_end_matches(
            OPEN_END, OPEN_END, None))
        self.assertTrue(validator._trade_power_saved_end_matches(
            OPEN_END, OPEN_END, "0x29c77f8"))
        self.assertTrue(validator._trade_power_saved_end_matches(
            123456, 123456, 123456))
        self.assertFalse(validator._trade_power_saved_end_matches(
            123456, 123456, 123457))
        self.assertFalse(validator._trade_power_saved_end_matches(
            OPEN_END, OPEN_END, "1465.1.5"))
        self.assertFalse(validator._trade_power_saved_end_matches(
            OPEN_END, OPEN_END, "56548944"))


if __name__ == "__main__":
    unittest.main()
