"""Subsidy year-unit migration and exact evidence gating; no game access."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from bridge.diplomacy_api import APIError, validate_value
from tools.build_diplomacy_catalog import Builder, DEFAULT_EXTENSION_REPORT, EXTENSION_REPORT_SHA256, schema

ROOT = Path(__file__).resolve().parents[2]


class SubsidyParameterTests(unittest.TestCase):
    def test_public_contract_uses_years_and_rejects_old_months_without_conversion(self):
        contract = schema("warsubsidy", "diplomacy")
        validate_value({"actor": "FRA", "target": "ENG", "monthly_amount": 1, "duration_years": 10}, contract)
        for args in ({"duration_months": 120}, {"duration_years": 0}, {"duration_years": True}, {"duration_years": 1.5}, {"duration_years": 2147483648}):
            with self.subTest(args=args), self.assertRaises(APIError):
                validate_value({"actor": "FRA", "target": "ENG", "monthly_amount": 1, **args}, contract)
        # Interface bounds are described, not misrepresented as the complete engine domain.
        self.assertIn("UI", contract["properties"]["duration_years"]["description"])

    def test_published_evidence_preserves_static_only_and_exact_unit_proof(self):
        catalog = json.loads((ROOT / "bridge/diplomacy_catalog.json").read_text(encoding="utf-8"))
        action = next(x for x in catalog["actions"] if x["action_id"] == "give_subsidies")
        self.assertIn("duration_years", action["parameters"]["properties"])
        self.assertNotIn("duration_months", action["parameters"]["properties"])
        self.assertEqual(action["parameter_status"], "partial")
        self.assertEqual(action["execution"]["status"], "unimplemented")
        proof = action["parameter_evidence"]
        self.assertEqual(hashlib.sha256(DEFAULT_EXTENSION_REPORT.read_bytes()).hexdigest().upper(), EXTENSION_REPORT_SHA256)
        self.assertEqual(proof["report_sha256"], EXTENSION_REPORT_SHA256)
        self.assertEqual(proof["duration_years"]["native_unit"], "years")
        self.assertEqual(proof["duration_years"]["object_offset"], "0x44")
        self.assertEqual(proof["duration_years"]["ui_step"], 10)
        self.assertFalse(proof["runtime_verified"])
        self.assertEqual(catalog["coverage"]["counts"]["actions_total"], 274)
        self.assertEqual(catalog["coverage"]["counts"]["actions_with_any_static_native_mapping"], 270)

    def test_changed_report_or_wrong_executable_cannot_attach_parameter_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            changed = folder / "report.json"
            raw = DEFAULT_EXTENSION_REPORT.read_bytes()
            changed.write_bytes(raw + b" ")
            builder = Builder(folder, extension_report=changed)
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                builder.reconcile_extension_parameters({"exe_sha256": "0" * 64})
            builder = Builder(folder, extension_report=DEFAULT_EXTENSION_REPORT)
            with self.assertRaisesRegex(ValueError, "executable SHA-256"):
                builder.reconcile_extension_parameters({"exe_sha256": "0" * 64})

    def test_reconciliation_does_not_modify_execution_or_native_mapping(self):
        report = json.loads(DEFAULT_EXTENSION_REPORT.read_text())
        builder = Builder(Path("."), extension_report=DEFAULT_EXTENSION_REPORT)
        execution = {"status": "unimplemented", "supported_builds": []}
        mapping = {"runtime_verified": False}
        builder.actions["give_subsidies"] = {"evidence": [], "execution": deepcopy(execution), "native_mapping": deepcopy(mapping)}
        builder.reconcile_extension_parameters({"exe_sha256": report["game_sha256"].upper()})
        action = builder.actions["give_subsidies"]
        self.assertEqual(action["execution"], execution)
        self.assertEqual(action["native_mapping"], mapping)


if __name__ == "__main__":
    unittest.main()
