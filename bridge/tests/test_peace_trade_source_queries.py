from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from work.run_peace_trade_source_queries import (
    _CASE_NAMES,
    _TRADE_POWER_ACTION,
    _case_contract,
    _case_specs,
    _output_paths,
    _summary,
)


WAR_ID = "war_0123456789abcdef_01234567"


class PeaceTradeSourceQueryTests(unittest.TestCase):
    def test_batch_specs_have_the_five_requested_public_shapes(self):
        specs = _case_specs(WAR_ID)
        self.assertEqual(list(_CASE_NAMES), [spec["name"] for spec in specs])
        self.assertEqual([], specs[0]["parameters"]["peace_context"]["terms"])
        self.assertEqual(
            {"source": "UTR", "beneficiary": "FRA", "action_id": _TRADE_POWER_ACTION},
            specs[1]["parameters"]["peace_context"]["terms"][0])
        self.assertEqual(
            {"source": "ENG", "beneficiary": "FRA", "action_id": _TRADE_POWER_ACTION},
            specs[2]["parameters"]["peace_context"]["terms"][0])
        self.assertEqual(
            {"source": "FRA", "beneficiary": "ENG", "action_id": _TRADE_POWER_ACTION},
            specs[3]["parameters"]["peace_context"]["terms"][0])
        self.assertEqual(
            ["war_reparations", _TRADE_POWER_ACTION],
            [term["action_id"] for term in specs[4]["parameters"]["peace_context"]["terms"]])

    def test_source_ack_comes_from_installation_capability_not_query_label(self):
        spec = _case_specs(WAR_ID)[1]
        result = {
            "action_id": _TRADE_POWER_ACTION,
            "family": "peace", "actor": "FRA", "recipient": "ENG",
            "phase": "initiate",
            "interface_support": {"query": "native_peace_execution_inspection"},
            "legality": {"status": "unknown", "complete": False},
        }
        acknowledged = _summary(
            result, spec, source_capability_acknowledged=True)
        unacknowledged = _summary(
            result, spec, source_capability_acknowledged=False)
        self.assertTrue(acknowledged["native_source_query_ack"])
        self.assertFalse(unacknowledged["native_source_query_ack"])

        legacy_label = dict(result)
        legacy_label["interface_support"] = {
            "query": "native_peace_trade_power_sources",
        }
        self.assertFalse(_summary(
            legacy_label, spec,
            source_capability_acknowledged=False)["native_source_query_ack"])

    def test_candidate_discovery_is_unknown_with_a_complete_source_list(self):
        spec = _case_specs(WAR_ID)[0]
        result = {
            "action_id": _TRADE_POWER_ACTION,
            "family": "peace", "actor": "FRA", "recipient": "ENG",
            "phase": "initiate", "selected_war_id": WAR_ID,
            "interface_support": {"query": "native_peace_execution_inspection"},
            "peace_context": {"war_id": WAR_ID, "terms": []},
            "legality": {"status": "unavailable", "complete": True},
            "native_trade_power": {
                "candidate_count": 2,
                "candidate_enumeration_complete": True,
                "candidates": [{"source": "ENG"}, {"source": "UTR"}],
            },
        }
        summary = _summary(result, spec, source_capability_acknowledged=True)
        self.assertEqual("unknown", summary["legality_status"])
        self.assertTrue(summary["candidate_list_complete"])
        self.assertEqual([{"source": "ENG"}, {"source": "UTR"}],
                         summary["candidate_sources"])
        checks = _case_contract(spec, result, summary, WAR_ID)
        self.assertTrue(all(checks.values()), checks)

        parameters_result = dict(result)
        parameters_result.pop("native_trade_power")
        parameters_result["parameters"] = {
            "candidates": {
                "candidate_count": 2,
                "candidates_complete": True,
                "candidates": [{"source": "ENG"}, {"source": "UTR"}],
            },
        }
        parameters_summary = _summary(
            parameters_result, spec, source_capability_acknowledged=True)
        self.assertTrue(parameters_summary["candidate_list_complete"])
        self.assertEqual(2, parameters_summary["candidate_count"])

    def test_default_eng_missing_candidate_is_unknown_without_claiming_available(self):
        spec = _case_specs(WAR_ID)[2]
        result = {
            "action_id": _TRADE_POWER_ACTION,
            "family": "peace", "actor": "FRA", "recipient": "ENG",
            "phase": "initiate", "selected_war_id": WAR_ID,
            "interface_support": {"query": "native_peace_execution_inspection"},
            "peace_context": {"war_id": WAR_ID, "terms": []},
            "legality": {"status": "unavailable", "complete": True},
            "native_trade_power": {
                "candidate_count": 1,
                "candidate_enumeration_complete": True,
                "candidate_found": False,
                "matching_candidate_count": 0,
                "candidates": [{"source": "UTR"}],
            },
        }
        summary = _summary(result, spec, source_capability_acknowledged=True)
        self.assertEqual("unknown", summary["legality_status"])
        self.assertNotEqual("available", summary["legality_status"])

    def test_utr_source_and_reparations_roles_are_compared_when_present(self):
        spec = _case_specs(WAR_ID)[4]
        result = {
            "action_id": _TRADE_POWER_ACTION,
            "family": "peace", "actor": "FRA", "recipient": "ENG",
            "phase": "initiate", "selected_war_id": WAR_ID,
            "interface_support": {"query": "native_peace_execution_inspection"},
            "peace_context": {
                "war_id": WAR_ID,
                "terms": [
                    {"action_id": "war_reparations", "payer": "ENG",
                     "claimant": "FRA"},
                    {"action_id": _TRADE_POWER_ACTION, "source": "UTR",
                     "beneficiary": "FRA"},
                ],
            },
            "legality": {"status": "available", "complete": True},
            "native_trade_power": {
                "rule_available": True,
                "source": "UTR", "beneficiary": "FRA",
                "candidate_found": True,
                "matching_candidate_count": 1,
            },
        }
        summary = _summary(result, spec, source_capability_acknowledged=True)
        self.assertEqual("UTR", summary["actual_source"])
        self.assertTrue(summary["actual_source_matches"])
        self.assertTrue(summary["actual_beneficiary_matches"])
        self.assertTrue(summary["reparations_pair_matches"])
        checks = _case_contract(spec, result, summary, WAR_ID)
        self.assertTrue(all(checks.values()), checks)

    def test_output_requires_a_unique_report_and_creates_evidence_sibling(self):
        with tempfile.TemporaryDirectory() as directory:
            report, evidence = _output_paths(Path(directory) / "batch" / "report.json")
            self.assertEqual("report.json", report.name)
            self.assertTrue(evidence.is_dir())
            self.assertEqual("report-evidence", evidence.name)


if __name__ == "__main__":
    unittest.main()
