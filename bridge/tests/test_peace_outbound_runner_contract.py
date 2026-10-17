from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from work.run_peace_outbound_execution import (
    _build_parameters,
    _derive_wire_correction,
    _expected_native_fields,
    _normalize_province_ids,
    _parse_province_ids_csv,
    _province_id_sequence_matches,
    _result_contract,
    _wire_submission_correlation,
)
from work.validate_peace_outbound_reload import (
    _REQUIRED_SOURCE_FLOOR,
    _REQUIRED_SOURCE_NAMES,
    _binding_contract,
    _compare_effect_states,
    _requested_peace_province_ids,
    _requested_peace_terms,
    _read_native_effect_observations,
    _serialized_treasury_to_raw,
    _stream_save_effect_state,
    _source_map,
)


WAR_ID = "war_0123456789abcdef_01234567"


def _sources(count: int) -> list[dict[str, str]]:
    names = sorted(_REQUIRED_SOURCE_NAMES)
    extras = ["peace-effects.h", "peace-effect-state.inc", "effects-extra.inc"]
    names.extend(extras)
    return [
        {"name": name, "sha256": f"{index + 1:064x}"}
        for index, name in enumerate(names[:count])
    ]


class PeaceOutboundRunnerContractTests(unittest.TestCase):
    def test_province_csv_is_bounded_duplicate_free_and_ordered(self) -> None:
        self.assertEqual(_parse_province_ids_csv("177, 0xB2,185"), [177, 178, 185])
        self.assertEqual(_normalize_province_ids((177, 178)), [177, 178])
        with self.assertRaises(Exception):
            _parse_province_ids_csv("177,,178")
        with self.assertRaises(Exception):
            _parse_province_ids_csv(",177")
        with self.assertRaises(Exception):
            _normalize_province_ids([177, 177])
        with self.assertRaises(Exception):
            _normalize_province_ids(list(range(1, 18)))

    def test_multi_province_selection_is_copied_to_query_and_execution(self) -> None:
        parameters = _build_parameters(
            "cede_province", WAR_ID, "10.0", 177, "FRA", "demand",
            province_ids=[177, 178, 185])
        context = parameters["peace_context"]
        term = context["terms"][0]
        self.assertEqual(term["province_ids"], [177, 178, 185])
        self.assertEqual(
            _expected_native_fields("cede_province", parameters)["province_ids"],
            [177, 178, 185])
        self.assertTrue(_province_id_sequence_matches(
            [185, 177, 178], [177, 178, 185]))
        self.assertFalse(_province_id_sequence_matches([177, 177], [177, 178]))

    def test_mixed_money_and_province_terms_keep_native_wire_order(self) -> None:
        parameters = _build_parameters(
            "cede_province", WAR_ID, "10.0", 177, None, "offer",
            province_ids=[177, 178], with_money="1.0")
        terms = parameters["peace_context"]["terms"]
        self.assertEqual([term["action_id"] for term in terms],
                         ["demand_ducats", "cede_province"])
        self.assertEqual(terms[0]["amount"], "1.0")
        self.assertEqual(terms[0]["payer"], "FRA")
        self.assertEqual(terms[0]["claimant"], "ENG")
        self.assertEqual(terms[1]["province_ids"], [177, 178])

        with self.assertRaises(Exception):
            _build_parameters(
                "demand_ducats", WAR_ID, "10.0", 177, None, "offer",
                with_money="1.0")

    def test_reload_reads_both_mixed_terms_for_payment_and_allocation(self) -> None:
        parameters = _build_parameters(
            "cede_province", WAR_ID, "10.0", 177, None, "offer",
            province_ids=[177, 178], with_money="1.0")
        execution = {"parameters": {"execute": parameters}}
        terms = _requested_peace_terms(execution)
        self.assertIsInstance(terms, list)
        self.assertEqual([term["action_id"] for term in terms],
                         ["demand_ducats", "cede_province"])
        self.assertEqual(_requested_peace_province_ids(execution), [177, 178])

    def test_serialized_treasury_uses_exact_native_scale(self) -> None:
        self.assertEqual(_serialized_treasury_to_raw("8.000"), 8000)
        self.assertEqual(_serialized_treasury_to_raw("-0.125"), -125)
        self.assertIsNone(_serialized_treasury_to_raw("not-a-number"))
        self.assertIsNone(_serialized_treasury_to_raw("0.0005"))

    def test_private_effect_slice_binds_request_and_country(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_text("\n".join([
                json.dumps({"event": "other", "request_id": "r"}),
                json.dumps({
                    "event": "native_peace_effect_observation", "private": True,
                    "request_id": "other", "country": "ENG", "date_before": 1,
                    "date_after": 1, "treasury_before_raw": 9000,
                    "treasury_after_raw": 8000, "currency_scale": 1000,
                }),
                json.dumps({
                    "event": "native_peace_effect_observation", "private": True,
                    "request_id": "r", "country": "ENG", "date_before": 1,
                    "date_after": 1, "treasury_before_raw": 9000,
                    "treasury_after_raw": 8000, "currency_scale": 1000,
                }),
            ]) + "\n", encoding="utf-8")
            result = _read_native_effect_observations({
                "native_events": {"path": str(path), "complete": True},
            }, "r")
        self.assertTrue(result["all"])
        self.assertEqual(list(result["by_country"]), ["ENG"])
        self.assertEqual(result["by_country"]["ENG"]["treasury_after_raw"], 8000)

    def test_effect_state_compares_private_after_and_save_fields(self) -> None:
        observations = {
            "all": True,
            "by_country": {
                "ENG": {"treasury_after_raw": 8000},
            },
        }
        native = {
            "status": "ok",
            "snapshot": {"runtime": {
                "countries": [{
                    "tag": "ENG", "treasury_readable": True,
                    "currency_scale": 1000, "treasury_raw": 8000,
                }],
                "provinces": [],
            }},
        }
        saved = {
            "status": "ok",
            "parsed": {
                "countries": {
                    "ENG": {
                        "complete": True,
                        "treasury": {"found": True, "raw": "8.000"},
                    },
                },
                "provinces": {},
            },
        }
        result = _compare_effect_states(
            observations, native, saved, {"provinces": []}, "demand_ducats")
        self.assertTrue(result["all"])
        self.assertTrue(result["checks"]["native_treasury_after_matches_private"])
        self.assertTrue(result["checks"]["save_treasury_after_matches_private"])

    def test_effect_state_keeps_controller_observation_independent(self) -> None:
        observations = {
            "all": True,
            "by_country": {"ENG": {"treasury_after_raw": 8000}},
        }
        native = {
            "status": "ok",
            "snapshot": {"runtime": {
                "countries": [{
                    "tag": "ENG", "treasury_readable": True,
                    "currency_scale": 1000, "treasury_raw": 8000,
                }],
                "provinces": [{
                    "province_id": 177, "record_readable": True,
                    "owner": {"tag": "FRA", "identity_verified": True},
                    "controller": {"tag": "ENG", "identity_verified": True},
                }],
            }},
        }
        saved = {
            "status": "ok",
            "parsed": {
                "countries": {
                    "ENG": {
                        "complete": True,
                        "treasury": {"found": True, "raw": "8.000"},
                    },
                },
                "provinces": {
                    "177": {
                        "complete": True,
                        "fields": {
                            "owner": {"value": "FRA"},
                            "controller": {"value": "ENG"},
                        },
                    },
                },
            },
        }
        effects = {"provinces": [{
            "province_id": 177,
            "owner_after": "FRA",
            "controller_after": "ENG",
        }]}
        result = _compare_effect_states(
            observations, native, saved, effects, "cede_province",
            expected_province_ids=[177])
        self.assertTrue(result["all"])
        self.assertTrue(result["checks"]["native_province_effects_match_public_after"])
        self.assertTrue(result["checks"]["save_province_effects_match_public_after"])

        incomplete = _compare_effect_states(
            observations, native, saved, {"provinces": []}, "cede_province",
            expected_province_ids=[177, 178])
        self.assertFalse(incomplete["all"])
        self.assertFalse(incomplete["checks"]["public_province_ids_exact"])

    def test_effect_save_scan_is_streamed_for_requested_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "effects.eu4"
            gamestate = (
                'date="1455.1.5"\n'
                "countries={\n"
                "FRA={\n treasury=5.000\n}\n"
                "ENG={\n treasury=8.000\n}\n}\n"
                "provinces={\n"
                "-177={\n owner=FRA\n controller=ENG\n}\n}\n"
            ).encode("utf-8")
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("gamestate", gamestate)
            result = _stream_save_effect_state(
                {"save": {"path": str(path)}}, ["ENG", "FRA"], [177])
        self.assertEqual(result["status"], "ok")
        parsed = result["parsed"]
        self.assertEqual(parsed["countries"]["ENG"]["treasury"]["raw"], "8.000")
        self.assertEqual(parsed["provinces"]["177"]["fields"]["owner"]["value"], "FRA")

    def test_direction_reverses_money_and_default_province_roles(self) -> None:
        demand_money = _build_parameters(
            "demand_ducats", WAR_ID, "10.0", 177, None, "demand")
        offer_money = _build_parameters(
            "demand_ducats", WAR_ID, "10.0", 177, None, "offer")
        self.assertEqual(
            demand_money["peace_context"]["terms"][0]["payer"], "ENG")
        self.assertEqual(
            demand_money["peace_context"]["terms"][0]["claimant"], "FRA")
        self.assertEqual(
            offer_money["peace_context"]["terms"][0]["payer"], "FRA")
        self.assertEqual(
            offer_money["peace_context"]["terms"][0]["claimant"], "ENG")

        offer_province = _build_parameters(
            "cede_province", WAR_ID, "10.0", 177, None, "offer")
        self.assertEqual(
            offer_province["peace_context"]["direction"], "offer")
        self.assertEqual(
            offer_province["peace_context"]["terms"][0]["beneficiary"], "ENG")

    def test_expected_native_direction_and_effects_are_retained(self) -> None:
        parameters = _build_parameters(
            "white_peace", WAR_ID, "10.0", 177, None, "offer")
        expected = _expected_native_fields("white_peace", parameters)
        self.assertEqual(expected["direction"], "offer")
        final = {
            "status": "accepted",
            "request_id": "peace_contract_1",
            "result": {
                **expected,
                "date_raw": 1,
                "request_id": "peace_contract_1",
                "outcome": "accepted",
                "response_verified": True,
                "request_binding_verified": True,
                "execution_verified": True,
                "terms_verified": True,
                "war_before": True,
                "war_after": False,
                "effects": {
                    "complete": True,
                    "date_unchanged": True,
                    "currency_scale": 1000,
                    "money": None,
                    "provinces": [],
                },
            },
        }
        result = _result_contract(
            final, "white_peace", parameters, 1,
            {"complete": True, "pair_at_war": True},
            {"complete": True, "pair_at_war": False},
        )
        self.assertTrue(result["all"])
        self.assertTrue(result["native_effects"]["present"])
        self.assertEqual(result["effects_contract"]["currency_scale"], 1000)

    def test_rejected_result_keeps_war_and_requires_unapplied_terms(self) -> None:
        parameters = _build_parameters(
            "white_peace", WAR_ID, "10.0", 177, None, "demand")
        expected = _expected_native_fields("white_peace", parameters)
        final = {
            "status": "rejected",
            "request_id": "peace_contract_rejected",
            "result": {
                **expected,
                "date_raw": 1,
                "request_id": "peace_contract_rejected",
                "outcome": "rejected",
                "response_verified": True,
                "request_binding_verified": True,
                "execution_verified": False,
                "terms_verified": False,
                "war_before": True,
                "war_after": True,
            },
        }
        result = _result_contract(
            final, "white_peace", parameters, 1,
            {"complete": True, "pair_at_war": True},
            {"complete": True, "pair_at_war": True},
        )
        self.assertTrue(result["all"])
        self.assertTrue(result["checks"]["terms_verified"])

    def test_accepted_money_requires_effects_and_direction_payer(self) -> None:
        parameters = _build_parameters(
            "demand_ducats", WAR_ID, "10.0", 177, None, "demand")
        expected = _expected_native_fields("demand_ducats", parameters)
        final = {
            "status": "executed",
            "request_id": "peace_contract_money",
            "result": {
                **expected,
                "date_raw": 1,
                "request_id": "peace_contract_money",
                "outcome": "executed",
                "response_verified": True,
                "request_binding_verified": True,
                "execution_verified": True,
                "terms_verified": True,
                "war_before": True,
                "war_after": False,
                "effects": {
                    "complete": True,
                    "date_unchanged": True,
                    "currency_scale": 1000,
                    "money": {
                        "amount_raw": 10000,
                        "payer": "ENG",
                        "paid_raw": 10000,
                        "credits": [{"country": "ENG", "amount_raw": 10000}],
                        "verified": True,
                    },
                    "provinces": [],
                },
            },
        }
        result = _result_contract(
            final, "demand_ducats", parameters, 1,
            {"complete": True, "pair_at_war": True},
            {"complete": True, "pair_at_war": False},
        )
        self.assertTrue(result["all"])
        self.assertTrue(result["effects_contract"]["checks"]["money_payer"])

    def test_accepted_province_requires_effect_owner_controller_fields(self) -> None:
        parameters = _build_parameters(
            "cede_province", WAR_ID, "10.0", 177, None, "demand")
        expected = _expected_native_fields("cede_province", parameters)
        final = {
            "status": "accepted",
            "request_id": "peace_contract_province",
            "result": {
                **expected,
                "date_raw": 1,
                "request_id": "peace_contract_province",
                "outcome": "accepted",
                "response_verified": True,
                "request_binding_verified": True,
                "execution_verified": True,
                "terms_verified": True,
                "war_before": True,
                "war_after": False,
                "effects": {
                    "complete": True,
                    "date_unchanged": True,
                    "currency_scale": 1000,
                    "money": None,
                    "provinces": [{
                        "province_id": 177,
                        "beneficiary": "FRA",
                        "owner_before": "ENG",
                        "owner_after": "FRA",
                        "controller_before": "ENG",
                        "controller_after": "ENG",
                        "verified": True,
                    }],
                },
            },
        }
        result = _result_contract(
            final, "cede_province", parameters, 1,
            {"complete": True, "pair_at_war": True},
            {"complete": True, "pair_at_war": False},
        )
        self.assertTrue(result["all"])
        self.assertTrue(result["effects_contract"]["checks"]["province_owner_transition"])
        self.assertTrue(result["effects_contract"]["checks"]["province_effect_fields"])

    def test_accepted_mixed_terms_require_both_money_and_province_effects(self) -> None:
        parameters = _build_parameters(
            "cede_province", WAR_ID, "10.0", 177, None, "offer",
            province_ids=[177], with_money="1.0")
        expected = _expected_native_fields("cede_province", parameters)
        final = {
            "status": "accepted",
            "request_id": "peace_contract_mixed",
            "result": {
                **expected,
                "date_raw": 1,
                "request_id": "peace_contract_mixed",
                "outcome": "accepted",
                "response_verified": True,
                "request_binding_verified": True,
                "execution_verified": True,
                "terms_verified": True,
                "war_before": True,
                "war_after": False,
                "effects": {
                    "complete": True,
                    "date_unchanged": True,
                    "currency_scale": 1000,
                    "money": {
                        "amount_raw": 1000,
                        "payer": "FRA",
                        "paid_raw": 1000,
                        "credits": [{"country": "FRA", "amount_raw": 1000}],
                        "verified": True,
                    },
                    "provinces": [{
                        "province_id": 177,
                        "beneficiary": "ENG",
                        "owner_before": "FRA",
                        "owner_after": "ENG",
                        "controller_before": "FRA",
                        "controller_after": "FRA",
                        "verified": True,
                    }],
                },
            },
        }
        result = _result_contract(
            final, "cede_province", parameters, 1,
            {"complete": True, "pair_at_war": True},
            {"complete": True, "pair_at_war": False})
        self.assertTrue(result["all"])
        self.assertTrue(result["effects_contract"]["checks"]["money_object"])
        self.assertTrue(result["effects_contract"]["checks"]["province_ids_exact"])

    def test_effect_contract_rejects_missing_or_extra_province_rows(self) -> None:
        parameters = _build_parameters(
            "cede_province", WAR_ID, "10.0", 177, "FRA", "demand",
            province_ids=[177, 178])
        expected = _expected_native_fields("cede_province", parameters)
        rows = [{
            "province_id": 177,
            "beneficiary": "FRA",
            "owner_before": "ENG",
            "owner_after": "FRA",
            "controller_before": "ENG",
            "controller_after": "ENG",
            "verified": True,
        }]
        final = {
            "status": "accepted",
            "request_id": "peace_contract_partial_province",
            "result": {
                **expected,
                "date_raw": 1,
                "request_id": "peace_contract_partial_province",
                "outcome": "accepted",
                "response_verified": True,
                "request_binding_verified": True,
                "execution_verified": True,
                "terms_verified": True,
                "war_before": True,
                "war_after": False,
                "effects": {
                    "complete": True,
                    "date_unchanged": True,
                    "currency_scale": 1000,
                    "money": None,
                    "provinces": rows,
                },
            },
        }
        result = _result_contract(
            final, "cede_province", parameters, 1,
            {"complete": True, "pair_at_war": True},
            {"complete": True, "pair_at_war": False},
        )
        self.assertFalse(result["all"])
        self.assertFalse(result["effects_contract"]["checks"]["province_ids_exact"])

    def test_manifest_source_count_is_dynamic_but_has_floor(self) -> None:
        self.assertEqual(_REQUIRED_SOURCE_FLOOR, 61)
        self.assertEqual(len(_REQUIRED_SOURCE_NAMES), 61)
        baseline = _sources(61)
        extended = _sources(63)
        self.assertEqual(len(_source_map(baseline) or {}), 61)
        self.assertEqual(len(_source_map(extended) or {}), 63)
        self.assertIsNone(_source_map(_sources(60)))
        duplicate = list(baseline)
        duplicate[-1] = dict(duplicate[0])
        self.assertIsNone(_source_map(duplicate))
        empty_name = list(baseline)
        empty_name[0] = {"name": " ", "sha256": "1" * 64}
        self.assertIsNone(_source_map(empty_name))

        alias = list(baseline)
        alias[0] = {
            "name": "renamed-required-source.inc",
            "sha256": baseline[0]["sha256"],
        }
        self.assertIsNone(_source_map(alias))

        dll = "a" * 64
        source = {
            "build_manifest": {"sources": extended},
            "build_binding": {"installation_matches_build_manifest": True},
            "session": {"dll_sha256": dll},
        }
        current = {
            "build_manifest": {"sources": extended},
            "build_binding": {"installation_matches_build_manifest": True},
            "installation": {"declared_dll_sha256": dll},
        }
        binding = _binding_contract(source, current, dll)
        self.assertTrue(binding["all"])
        self.assertEqual(binding["source_source_count"], 63)
        self.assertEqual(binding["reload_source_count"], 63)

    def test_wire_receipt_is_separate_from_business_submission(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            event_path = Path(directory) / "events.jsonl"
            event = {
                "event": "native_peace_submission_result",
                "session_id": "session-wire-1",
                "request_id": "wire_request_1",
                "family": "peace",
                "action_id": "cede_province",
                "actor": "FRA",
                "recipient": "ENG",
                "phase": "initiate",
                "date_raw": 56548944,
                "war_id": WAR_ID,
                "direction": "offer",
                "province_ids": [4388, 4111, 4112, 4389],
                "beneficiary": "ENG",
                "submitted": False,
                "transport_verified": False,
                "request_binding_verified": False,
                "reason": "NATIVE_PEACE_AUTHORITY_SEED_FAILED",
            }
            event_path.write_text(
                json.dumps({"event": "native_alliance_execution_rejected",
                            "request_id": "wire_request_1"}) + "\n"
                + json.dumps(event) + "\n", encoding="utf-8")
            report = {
                "session": {"session_id": "session-wire-1"},
                "request_id": "wire_request_1",
                "action_id": "cede_province",
                "actor": "FRA",
                "recipient": "ENG",
                "phase": "initiate",
                "expected_date_raw": 56548944,
                "war_id": WAR_ID,
                "direction": "offer",
                "parameters": {
                    "execute": {"peace_context": {
                        "terms": [{"action_id": "cede_province",
                                   "province_ids": [4388, 4111, 4112, 4389]}]
                    }}
                },
                "native_events": {"path": str(event_path)},
            }
            result = _wire_submission_correlation(report)
        self.assertEqual(result["status"], "observed")
        self.assertTrue(result["wire_published"])
        self.assertTrue(result["wire_consumed"])
        self.assertEqual(result["wire_publish_count"], 1)
        self.assertEqual(result["wire_consume_count"], 1)
        self.assertFalse(result["native_submitted"])
        self.assertFalse(result["transport_submitted"])
        self.assertEqual(result["matching_event_count"], 1)

    def test_wire_correction_is_non_destructive_and_rewrites_only_statistics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event_path = root / "events.jsonl"
            event_path.write_text(json.dumps({
                "event": "native_peace_submission_result",
                "session_id": "session-wire-2",
                "request_id": "wire_request_2",
                "family": "peace", "action_id": "white_peace",
                "actor": "FRA", "recipient": "ENG", "phase": "initiate",
                "date_raw": 1, "war_id": WAR_ID, "direction": "demand",
                "submitted": False, "transport_verified": False,
                "request_binding_verified": False,
                "reason": "NATIVE_PEACE_AUTHORITY_SEED_FAILED",
            }) + "\n", encoding="utf-8")
            source = root / "report.json"
            source_payload = {
                "status": "failed", "request_publish_count": 0,
                "business_submission": False,
                "session": {"session_id": "session-wire-2"},
                "request_id": "wire_request_2", "action_id": "white_peace",
                "actor": "FRA", "recipient": "ENG", "phase": "initiate",
                "expected_date_raw": 1, "war_id": WAR_ID, "direction": "demand",
                "native_events": {"path": str(event_path)},
            }
            source.write_text(json.dumps(source_payload) + "\n", encoding="utf-8")
            original_bytes = source.read_bytes()
            output = root / "wire-submission-correction-001.json"
            correction = _derive_wire_correction(source, output)
            self.assertEqual(source.read_bytes(), original_bytes)
            self.assertEqual(correction["corrected"]["request_publish_count"], 1)
            self.assertEqual(correction["corrected"]["wire_publish_count"], 1)
            self.assertEqual(correction["corrected"]["business_submission_count"], 0)
            self.assertFalse(correction["corrected"]["business_transport_submitted"])
            self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
