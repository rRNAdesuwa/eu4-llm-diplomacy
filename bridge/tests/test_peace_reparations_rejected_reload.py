import unittest
from pathlib import Path
from unittest.mock import patch

from work import validate_peace_outbound_reload as validator


DATE_RAW = 56548944
PAIR = ("ENG", "FRA")


def _execution(*, mixed: bool = False) -> dict[str, object]:
    terms: list[dict[str, object]] = [{
        "action_id": "war_reparations",
        "payer": PAIR[0],
        "claimant": PAIR[1],
    }]
    if mixed:
        terms.append({
            "action_id": "demand_ducats",
            "amount": "1.0",
            "payer": "ENG",
        })
    return {
        "request_id": "r49-rejected-reparations",
        "actor": "FRA",
        "recipient": "ENG",
        "parameters": {
            "execute": {"peace_context": {"terms": terms}},
        },
        "result_contract": {
            "effects_contract": {"all": True},
        },
    }


def _source(*, before: bool = False, after: bool = False,
            start: int = 0, end: int = 0) -> dict[str, object]:
    return {
        "outcome": "rejected",
        "action_id": "war_reparations",
        "effects": {
            "complete": True,
            "date_unchanged": True,
            "currency_scale": 1000,
            "money": None,
            "provinces": [],
            "war_reparations": {
                "payer": PAIR[0],
                "claimant": PAIR[1],
                "active_before": before,
                "active_after": after,
                "start_date_raw": start,
                "end_date_raw": end,
                "verified": False,
            },
        },
    }


def _native(*, present: bool = False, active: bool = False,
            start: int | None = None,
            end: int | None = None) -> dict[str, object]:
    return {
        "status": "ok",
        "snapshot": {"runtime": {
            "countries": [],
            "provinces": [],
            "war_reparations": {
                "payer": PAIR[0],
                "claimant": PAIR[1],
                "active": active,
                "present": present,
                "complete": True,
                "start_date_raw": start,
                "end_date_raw": end,
            },
        }},
    }


def _save(*, exact: bool = False, pair: tuple[str, str] = PAIR,
          status: str = "active") -> dict[str, object]:
    records: list[dict[str, object]] = []
    if exact:
        records.append({
            "complete": True,
            "payer": pair[0],
            "claimant": pair[1],
            "start_date": "1455.5.12",
            "end_date": "1465.5.12",
            "date_status": {
                "comparison_available": True,
                "status": status,
            },
        })
    return {
        "status": "ok",
        "parsed": {"countries": {}, "provinces": {}},
        "war_reparations": {"query": {
            "exact_pair_present": exact,
            "matching_records": records,
        }},
    }


class PeaceReparationsRejectedReloadTests(unittest.TestCase):
    def _run(self, source: dict[str, object], execution: dict[str, object],
             native: dict[str, object], saved: dict[str, object]) -> tuple[dict[str, object], object, object]:
        observations = {"all": True, "by_country": {}, "checks": {}}
        with patch.object(
                validator, "_read_native_effect_observations",
                return_value=observations), patch.object(
                    validator, "_run_effect_probe",
                    return_value=native) as native_probe, patch.object(
                        validator, "_stream_save_effect_state",
                        return_value=saved) as save_probe:
            result = validator._peace_effect_reload_contract(
                source, execution, {}, object(), DATE_RAW,
                Path("rejected-reparations-evidence"))
        return result, native_probe, save_probe

    def test_rejected_baseline_without_relation_is_checked_in_process_and_save(self) -> None:
        result, native_probe, save_probe = self._run(
            _source(), _execution(), _native(), _save())

        self.assertTrue(result["applicable"])
        self.assertTrue(result["all"])
        checks = result["comparison"]["checks"]
        self.assertTrue(checks["native_war_reparations_complete"])
        self.assertTrue(checks["native_war_reparations_present"])
        self.assertTrue(checks["native_war_reparations_active"])
        self.assertTrue(checks["save_war_reparations_exact_pair_absent"])
        self.assertTrue(checks["save_war_reparations_matching_records_absent"])
        self.assertEqual(1, native_probe.call_count)
        self.assertEqual(1, save_probe.call_count)
        self.assertEqual(PAIR, native_probe.call_args.kwargs["reparations_pair"])
        self.assertEqual(PAIR, save_probe.call_args.kwargs["reparations_pair"])

    def test_source_missing_activity_field_fails_the_rejected_contract(self) -> None:
        source = _source()
        del source["effects"]["war_reparations"]["active_after"]

        result, _, _ = self._run(source, _execution(), _native(), _save())

        self.assertFalse(result["all"])
        self.assertFalse(result["comparison"]["checks"][
            "source_war_reparations_active_after"])

    def test_source_roles_must_match_requested_payer_and_claimant(self) -> None:
        source = _source()
        source["effects"]["war_reparations"]["payer"] = "FRA"

        result, _, _ = self._run(source, _execution(), _native(), _save())

        self.assertFalse(result["all"])
        self.assertFalse(result["comparison"]["checks"][
            "source_war_reparations_pair"])

    def test_native_present_relation_is_not_accepted_for_absent_source_state(self) -> None:
        result, _, _ = self._run(
            _source(), _execution(),
            _native(present=True, active=True, start=10, end=100), _save())

        self.assertFalse(result["all"])
        self.assertFalse(result["comparison"]["checks"][
            "native_war_reparations_present"])

    def test_save_wrong_pair_does_not_satisfy_absent_exact_pair(self) -> None:
        result, _, _ = self._run(
            _source(), _execution(), _native(),
            _save(exact=True, pair=("FRA", "ENG")))

        self.assertFalse(result["all"])
        self.assertFalse(result["comparison"]["checks"][
            "save_war_reparations_exact_pair_absent"])

    def test_rejected_state_rejects_relation_still_present_after_request(self) -> None:
        result, _, _ = self._run(
            _source(), _execution(),
            _native(present=True, active=False, start=10, end=100),
            _save(exact=True, status="expired"))

        self.assertFalse(result["all"])
        self.assertFalse(result["comparison"]["checks"][
            "native_war_reparations_present"])
        self.assertFalse(result["comparison"]["checks"][
            "save_war_reparations_exact_pair_absent"])

    def test_existing_active_relation_is_compared_from_source_state(self) -> None:
        source = _source(before=True, after=True, start=10, end=100)
        result, _, _ = self._run(
            source, _execution(),
            _native(present=True, active=True, start=10, end=100),
            _save(exact=True, status="active"))

        self.assertTrue(result["all"])
        self.assertTrue(result["comparison"]["checks"][
            "native_war_reparations_dates"])
        self.assertTrue(result["comparison"]["checks"][
            "save_war_reparations_active_matches_source"])

    def test_mixed_rejected_terms_are_explicitly_out_of_scope(self) -> None:
        result, _, _ = self._run(
            _source(), _execution(mixed=True), _native(), _save())

        self.assertFalse(result["all"])
        self.assertTrue(result["public_summary"]["mixed_terms"])
        self.assertFalse(result["comparison"]["checks"][
            "rejected_mixed_effect_persistence_scope"])


if __name__ == "__main__":
    unittest.main()
