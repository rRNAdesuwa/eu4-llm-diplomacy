from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from work import run_peace_inbound_fixture as fixture
from work import run_peace_inbound_response as response_runner
from work import validate_peace_inbound_reload as reload_validator


DATE_RAW = 56548944
OPEN_END = 0x29C77F8
PAIR = ("FRA", "ENG")
WAR_ID = "war_0123456789abcdef_01234567"


def _context(*, mixed: bool = False) -> dict[str, object]:
    terms: list[dict[str, object]] = []
    if mixed:
        terms.append({
            "action_id": "war_reparations",
            "payer": "FRA",
            "claimant": "ENG",
        })
    terms.append({
        "action_id": "transfer_trade_power",
        "source": PAIR[0],
        "beneficiary": PAIR[1],
    })
    return {
        "war_id": WAR_ID,
        "direction": "demand",
        "terms": terms,
        "original_actor": "ENG",
        "original_recipient": "FRA",
        "complete": True,
        "selected_terms_complete": True,
        "white_peace": False,
    }


def _effects(*, accepted: bool, mixed: bool = False) -> dict[str, object]:
    value: dict[str, object] = {
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
            "present_after": accepted,
            "start_date_raw": DATE_RAW - 1 if accepted else 0,
            "end_date_raw": OPEN_END if accepted else 0,
            "amount_raw": 500 if accepted else 0,
            "amount_scale": 1000,
            "peace_treaty": accepted,
            "verified": accepted,
        },
    }
    if mixed:
        value["war_reparations"] = {
            "payer": "FRA",
            "claimant": "ENG",
            "active_before": False,
            "active_after": accepted,
            "verified": accepted,
            "start_date_raw": DATE_RAW - 1 if accepted else 0,
            "end_date_raw": DATE_RAW + 365 if accepted else 0,
        }
    return value


def _response(*, decision: str, accepted: bool,
              mixed: bool = False) -> dict[str, object]:
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
        "peace_context": _context(mixed=mixed),
        "effects": _effects(accepted=accepted, mixed=mixed),
    }


def _final(*, decision: str, accepted: bool,
           mixed: bool = False) -> dict[str, object]:
    projected = _response(decision=decision, accepted=accepted, mixed=mixed)
    return {
        "status": "accepted" if accepted else "rejected",
        "game_outcome": "accepted" if accepted else "rejected",
        "result": projected,
    }


def _source_payload(*, decision: str, accepted: bool,
                    mixed: bool = False) -> dict[str, object]:
    request_id = f"inbound-trade-{decision}"
    return {
        "status": "passed",
        "action_id": "peace_offer",
        "family": "peace",
        "actor": "ENG",
        "recipient": "FRA",
        "decision": decision,
        "request_id": request_id,
        "checks": {"one": True},
        "session": {"session_id": "source-session"},
        "after": {"control": {"date_raw": DATE_RAW}},
        "native_response": {
            "contract": True,
            "full_payload": True,
            "response_verified": True,
            "request_binding_verified": True,
            "handler_forwarded": True,
            "handler_consumed": True,
            "pending_removed": True,
            "response_event": {
                "event": "native_peace_inbound_response_result",
                "family": "peace",
                "action_id": "peace_offer",
                "actor": "ENG",
                "recipient": "FRA",
                "phase": decision,
                "request_id": request_id,
                "session_id": "source-session",
                "war_before": True,
                "war_after": not accepted,
            },
        },
        "result": _final(decision=decision, accepted=accepted, mixed=mixed),
    }


def _native_probe(*, present: bool) -> dict[str, object]:
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


def _save_report(directory: Path, *, present: bool) -> dict[str, object]:
    gamestate = "EU4txt\ndate=1455.1.5\n"
    if present:
        gamestate += (
            "transfer_trade_power={\n"
            " amount=0.500\n"
            " is_enforced=yes\n"
            " first=FRA\n"
            " second=ENG\n"
            " start_date=1455.1.5\n"
            "}\n")
    save = directory / ("accepted.eu4" if present else "rejected.eu4")
    with zipfile.ZipFile(save, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("gamestate", gamestate)
    return {
        "status": "success",
        "name": save.name,
        "save": {"path": str(save)},
    }


class PeaceTradePowerInboundRunnerTests(unittest.TestCase):
    def test_fixture_trade_power_publishes_once_and_checks_dispatch_flag(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installation = root / "installation.json"
            installation.write_text("{}", encoding="utf-8")
            output = root / "fixture.json"
            log = root / "control-probe.jsonl"
            log.write_text("", encoding="utf-8")

            class FakeSession:
                session_id = "fixture-session"
                directory = root
                publish_count = 0
                wire = None

                def __init__(self, *_args: object) -> None:
                    pass

                def _publish_atomic_request(self, wire: str, *_args: object) -> str:
                    type(self).publish_count += 1
                    type(self).wire = wire
                    with log.open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps({
                            "event": "native_peace_inbound_fixture_dispatched",
                            "session_id": self.session_id,
                            "dispatcher_accepted": True,
                            "native_gates_available": True,
                            "authority_seed_created": False,
                            "reparations_requested": False,
                            "trade_power_requested": True,
                        }) + "\n")
                        stream.write(json.dumps({
                            "event": "native_alliance_inbound_offer",
                            "session_id": self.session_id,
                            "actor": "ENG", "recipient": "FRA",
                            "family": "peace",
                            "peace": {
                                "complete": True,
                                "term_count": 83,
                                "selected_term_count": 2,
                                "participant_counts": [6, 4, 6, 4],
                                "flag40": 1,
                                "direction41": 1,
                                "preview208": 0,
                            },
                            "source_verified": True,
                            "pending_source": "native_executor_pending_block",
                        }) + "\n")
                    return "published"

            argv = [
                "run_peace_inbound_fixture.py", "--installation", str(installation),
                "--output", str(output), "--request-id", "fixture-trade",
                "--term", "transfer_trade_power", "--expected-date-raw", str(DATE_RAW),
            ]
            with patch.object(sys, "argv", argv), \
                    patch.object(fixture, "ObserverSession", FakeSession), \
                    patch.object(fixture, "game_exe", return_value=Path("eu4.exe")), \
                    patch.object(fixture, "wait_runtime_ready",
                                 return_value={"status": "ready", "date_raw": DATE_RAW}):
                self.assertEqual(0, fixture.main())
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(1, FakeSession.publish_count)
            self.assertEqual(
                "TEST_ONLY ENG_PEACE_FRA_TRADE_POWER_PENDING\n", FakeSession.wire)
            self.assertEqual("passed", report["status"])
            self.assertTrue(report["checks"]["trade_power_selected"])

    def test_t_fixture_uses_native_selection_count_not_public_clause_count(self) -> None:
        dispatched = [{
            "trade_power_requested": True,
            "reparations_requested": False,
        }]
        pending = [{
            "peace": {
                "complete": True,
                "term_count": 83,
                "selected_term_count": 2,
                "participant_counts": [6, 4, 6, 4],
                "flag40": 1,
                "direction41": 1,
                "preview208": 0,
            },
        }]
        self.assertTrue(fixture._native_trade_power_contract(
            dispatched, pending))
        pending[0]["peace"]["selected_term_count"] = 1
        self.assertFalse(fixture._native_trade_power_contract(
            dispatched, pending))

    def test_t_only_public_accept_and_reject_contracts_bind_inbound_roles(self) -> None:
        for decision, accepted in (("accept", True), ("reject", False)):
            with self.subTest(decision=decision):
                final = _final(decision=decision, accepted=accepted)
                context_checks = response_runner._peace_context_contract(
                    _context(), decision, PAIR)
                self.assertTrue(all(context_checks.values()))
                effects = response_runner._public_effect_contract(
                    final, decision, PAIR)
                self.assertTrue(effects["all"])
                self.assertTrue(response_runner._public_response_contract(
                    final, decision, "a" * 32, PAIR)["effects_contract"])
                self.assertEqual(PAIR, effects["trade_power_pair"])

    def test_mixed_r_t_and_money_requires_complete_money_effects(self) -> None:
        mixed = _context(mixed=True)
        checks = response_runner._peace_context_contract(mixed, "accept", PAIR)
        self.assertTrue(checks["effect_scope_supported"])
        self.assertTrue(response_runner._public_effect_contract(
            _final(decision="accept", accepted=True, mixed=True),
            "accept", PAIR)["all"])
        money_context = copy.deepcopy(_context())
        money_context["terms"] = [
            {"action_id": "demand_ducats", "amount": "1.0",
             "payer": "FRA", "claimant": "ENG"},
            *money_context["terms"],
        ]
        money_checks = response_runner._peace_context_contract(
            money_context, "accept", PAIR)
        self.assertTrue(money_checks["effect_scope_supported"])

        complete = _final(decision="accept", accepted=True)
        complete["result"]["peace_context"] = money_context
        complete["result"]["effects"]["money"] = {
            "amount_raw": 1000,
            "payer": "FRA",
            "paid_raw": 1000,
            "credits": [{"country": "ENG", "amount_raw": 1000}],
            "verified": True,
        }
        complete_contract = response_runner._public_effect_contract(
            complete, "accept", PAIR)
        self.assertTrue(complete_contract["all"], complete_contract)
        self.assertTrue(complete_contract["checks"][
            "money_province_full_effects"])

        incomplete = copy.deepcopy(complete)
        incomplete["result"]["effects"]["money"] = {
            "amount_raw": 1000, "verified": True}
        incomplete_contract = response_runner._public_effect_contract(
            incomplete, "accept", PAIR)
        self.assertFalse(incomplete_contract["all"])
        self.assertFalse(incomplete_contract["checks"][
            "money_province_full_effects"])

        forged = copy.deepcopy(complete)
        forged["result"]["effects"]["money"]["credits"] = [
            {"country": "ENG", "amount_raw": 999}]
        forged_contract = response_runner._public_effect_contract(
            forged, "accept", PAIR)
        self.assertFalse(forged_contract["all"])
        self.assertFalse(forged_contract["checks"][
            "money_province_full_effects"])

    def test_t_accept_rejects_wrong_pair_and_missing_applied_state(self) -> None:
        wrong_pair = _final(decision="accept", accepted=True)
        wrong_pair["result"]["effects"]["transfer_trade_power"][
            "beneficiary"] = "SAV"
        self.assertFalse(response_runner._public_effect_contract(
            wrong_pair, "accept", PAIR)["all"])
        missing_state = _final(decision="accept", accepted=True)
        missing_state["result"]["effects"]["transfer_trade_power"].update({
            "present_after": False,
            "amount_raw": 0,
            "peace_treaty": False,
            "verified": False,
        })
        self.assertFalse(response_runner._public_effect_contract(
            missing_state, "accept", PAIR)["all"])

    def test_reload_accepted_t_compares_native_and_save_helper_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save = _save_report(Path(directory), present=True)
            saved = reload_validator._stream_save_effect_state(
                save, ["FRA", "ENG"], [], trade_power_pair=PAIR)
            source = reload_validator._source_contract(
                _source_payload(decision="accept", accepted=True), PAIR)
            with patch.object(reload_validator, "_run_effect_probe",
                              return_value=_native_probe(present=True)) as native, \
                    patch.object(reload_validator, "_stream_save_effect_state",
                                 return_value=saved) as save_scan:
                result = reload_validator._peace_effect_reload_contract(
                    source, {"request_id": "inbound-trade-accept"},
                    {}, object(), DATE_RAW, Path(directory) / "evidence")
            self.assertTrue(result["all"])
            self.assertEqual(1, native.call_count)
            self.assertEqual(PAIR[0], native.call_args.kwargs["trade_power_source"])
            self.assertEqual(PAIR[1], native.call_args.kwargs["trade_power_beneficiary"])
            self.assertEqual(1, save_scan.call_count)
            self.assertEqual(PAIR[0], save_scan.call_args.kwargs["trade_power_source"])
            self.assertEqual(PAIR[1], save_scan.call_args.kwargs["trade_power_beneficiary"])
            self.assertTrue(result["comparison"]["checks"][
                "native_transfer_trade_power_present"])
            self.assertTrue(result["comparison"]["checks"][
                "save_transfer_trade_power_exact_pair"])

    def test_reload_rejected_t_requires_complete_absence_in_native_and_save(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save = _save_report(Path(directory), present=False)
            saved = reload_validator._stream_save_effect_state(
                save, ["FRA", "ENG"], [], trade_power_pair=PAIR)
            source = reload_validator._source_contract(
                _source_payload(decision="reject", accepted=False), PAIR)
            with patch.object(reload_validator, "_run_effect_probe",
                              return_value=_native_probe(present=False)), \
                    patch.object(reload_validator, "_stream_save_effect_state",
                                 return_value=saved):
                result = reload_validator._peace_effect_reload_contract(
                    source, {"request_id": "inbound-trade-reject"},
                    {}, object(), DATE_RAW, Path(directory) / "evidence")
            self.assertTrue(result["all"])
            checks = result["comparison"]["checks"]
            self.assertTrue(checks["native_transfer_trade_power_present_absent"])
            self.assertTrue(checks["save_transfer_trade_power_exact_pair_absent"])
            self.assertTrue(checks["save_transfer_trade_power_matching_records_absent"])


if __name__ == "__main__":
    unittest.main()
