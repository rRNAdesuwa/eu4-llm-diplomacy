"""Pure validator-contract tests; these never attach to EU4 or write requests."""
from __future__ import annotations

import unittest

from work import validate_alliance_queries as validator


DATE_RAW = 56459880


def _inspection(action_id: str, recipient: str, *, response: str | None = None,
                resource: bool = False) -> dict:
    dissolve = action_id == "dissolve_alliance"
    visible = not dissolve and recipient != "PRO"
    available = visible
    common_gate = True
    initiation_gate = True
    executor_validity = True
    components = {
        "specific_validity_query_called": True,
        "ui_selection_checked": True,
        "native_visibility": visible,
        "ui_enabled_gate_checked": True,
        "common_action_gate": common_gate,
        "initiation_gate": initiation_gate,
        "executor_validity": executor_validity,
        "tooltip_gate": initiation_gate,
        "full_rules_complete": True,
    }
    acceptance = {
        "applicability": "not_applicable" if dissolve else "applicable",
        "prediction_available": False,
        "native_total": None,
        "unit": None if dissolve else "unknown",
        "scale_verified": False,
        "predicted_response": "not_applicable" if dissolve else "unknown",
        "details_available": False,
        "items": [],
        "complete": dissolve,
    }
    if response is not None:
        accepted = response == "accept"
        acceptance.update(
            prediction_available=True,
            native_total=64 if accepted else -26,
            native_threshold=1,
            predicted_response=response,
            prediction_basis="native_current_acceptance_check",
            native_would_accept=accepted,
            actual_response_verified=False,
            complete=False,
        )
        components["acceptance_gate"] = accepted
    if dissolve:
        acceptance.update(
            applicability="not_applicable",
            prediction_available=False,
            native_total=None,
            unit=None,
            predicted_response="not_applicable",
            items=[],
            complete=True,
        )
    result = {
        "contract_version": 1,
        "action_id": action_id,
        "actor": "FRA",
        "recipient": recipient,
        "phase": "initiate",
        "interface_support": {"query": "partial_native_rules"},
        "session": {"status": "ready", "date_raw": DATE_RAW},
        "visibility": {"status": "visible" if visible else "hidden", "complete": True},
        "legality": {"status": "available" if available else "unavailable", "complete": True},
        "native_rule_components": components,
        "acceptance": acceptance,
    }
    if resource:
        result["resources"] = {"diplomats": {
            "native_requirement": True,
            "available_count": 1,
            "availability_verified": True,
            "allocation_verified": False,
            "source": "native_rule",
            "complete": False,
        }}
    return result


class ValidatorR13ContractTests(unittest.TestCase):
    def test_r12_unknown_prediction_remains_legacy(self) -> None:
        result = _inspection("offer_alliance", "SAV")
        self.assertFalse(validator._has_r13_extensions(result))
        validator._require_ui_covered_inspection(
            "offer_alliance:FRA->SAV", result, DATE_RAW,
            validator.UI_COVERED_EXPECTATIONS[("offer_alliance", "SAV")],
        )

    def test_r13_accept_and_reject_require_native_check(self) -> None:
        sav = _inspection("offer_alliance", "SAV", response="accept", resource=True)
        lit = _inspection("offer_alliance", "LIT", response="reject", resource=True)
        validator._require_ui_covered_inspection(
            "offer_alliance:FRA->SAV", sav, DATE_RAW,
            validator.UI_COVERED_EXPECTATIONS[("offer_alliance", "SAV")],
        )
        validator._require_ui_covered_inspection(
            "offer_alliance:FRA->LIT", lit, DATE_RAW,
            validator.UI_COVERED_EXPECTATIONS[("offer_alliance", "LIT")],
        )
        validator._require_r13_native_acceptance("offer_alliance:FRA->SAV", sav, "accept")
        validator._require_r13_native_acceptance("offer_alliance:FRA->LIT", lit, "reject")

    def test_r13_contract_requires_por_and_cancel_without_prediction(self) -> None:
        inspections = {
            "offer_alliance:FRA->SAV": _inspection("offer_alliance", "SAV", response="accept", resource=True),
            "offer_alliance:FRA->LIT": _inspection("offer_alliance", "LIT", response="reject", resource=True),
            "offer_alliance:FRA->POR": _inspection("offer_alliance", "POR", resource=True),
            "dissolve_alliance:FRA->SAV": _inspection("dissolve_alliance", "SAV", resource=True),
            "dissolve_alliance:FRA->SCO": _inspection("dissolve_alliance", "SCO", resource=True),
            "dissolve_alliance:FRA->PRO": _inspection("dissolve_alliance", "PRO", resource=True),
        }
        validator._require_r13_contract(inspections, DATE_RAW)

    def test_actual_response_true_is_rejected(self) -> None:
        result = _inspection("offer_alliance", "SAV", response="accept", resource=True)
        result["acceptance"]["actual_response_verified"] = True
        with self.assertRaises(validator.ValidationStop) as raised:
            validator._require_r13_native_acceptance("offer_alliance:FRA->SAV", result, "accept")
        self.assertEqual(raised.exception.code, "R13_ACCEPTANCE_PREDICATE_MISMATCH")

    def test_incomplete_resource_fields_are_unknown(self) -> None:
        result = _inspection("offer_alliance", "SAV", response="accept", resource=True)
        result["resources"]["diplomats"]["allocation_verified"] = True
        with self.assertRaises(validator.ValidationStop) as raised:
            validator._require_r13_resources("offer_alliance:FRA->SAV", result)
        self.assertEqual(raised.exception.code, "R13_RESOURCE_FIELDS_INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
