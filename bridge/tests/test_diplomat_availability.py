from __future__ import annotations

import copy
import unittest

from bridge.diplomat_availability import (
    NATIVE_DIPLOMAT_CONTEXT_UNAVAILABLE,
    NATIVE_DIPLOMAT_UNAVAILABLE,
    apply_diplomat_legality,
    project_native_diplomat_context,
    validate_native_diplomat_context,
)


def _event(*, readable: bool = True, required: bool = True,
           count: int | None = 0) -> dict:
    return {
        "diplomat_context_readable": readable,
        "diplomat_required": required,
        "available_diplomat_count": count,
    }


def _inspection(*, phase: str = "initiate", required: bool = True,
                verified: bool = True, count: object = 0,
                status: str = "unknown", complete: bool = True,
                reasons: list[dict] | None = None) -> dict:
    return {
        "phase": phase,
        "complete": complete,
        "resources": {
            "diplomats": {
                "native_requirement": required,
                "available_count": count,
                "availability_verified": verified,
                "allocation_verified": False,
                "source": "native_rule",
                "complete": verified,
            },
        },
        "legality": {
            "status": status,
            "reasons": [] if reasons is None else reasons,
            "complete": complete,
        },
    }


class DiplomatContextValidationTests(unittest.TestCase):
    def test_legacy_context_is_optional_as_a_whole(self):
        self.assertTrue(validate_native_diplomat_context({}))
        self.assertTrue(validate_native_diplomat_context({"unrelated": True}))
        self.assertIsNone(project_native_diplomat_context({}))

    def test_readable_count_zero_and_positive_counts_are_valid(self):
        for count in (0, 1, 256):
            event = _event(count=count)
            self.assertTrue(validate_native_diplomat_context(event))
            self.assertEqual({
                "native_requirement": True,
                "available_count": count,
                "availability_verified": True,
                "allocation_verified": False,
                "source": "native_rule",
                "complete": True,
            }, project_native_diplomat_context(event))

    def test_unreadable_context_hides_count_and_allows_explicit_none(self):
        event = _event(readable=False, count=None)
        self.assertTrue(validate_native_diplomat_context(event))
        self.assertEqual({
            "native_requirement": True,
            "available_count": None,
            "availability_verified": False,
            "allocation_verified": False,
            "source": "native_rule",
            "complete": False,
        }, project_native_diplomat_context(event))

        # A captured count is still not exposed when the context says it is
        # unreadable.
        captured = _event(readable=False, count=3)
        self.assertEqual(3, captured["available_diplomat_count"])
        self.assertEqual(None, project_native_diplomat_context(captured)["available_count"])

    def test_partial_context_and_wrong_types_are_rejected(self):
        fields = _event()
        for field in fields:
            partial = dict(fields)
            del partial[field]
            self.assertFalse(validate_native_diplomat_context(partial), field)

        invalid = [
            {**fields, "diplomat_context_readable": 1},
            {**fields, "diplomat_required": 0},
            {**fields, "available_diplomat_count": True},
            {**fields, "available_diplomat_count": -1},
            {**fields, "available_diplomat_count": 257},
            {**_event(readable=False, count=None),
             "available_diplomat_count": False},
            {**_event(readable=True, count=None)},
        ]
        for event in invalid:
            self.assertFalse(validate_native_diplomat_context(event), event)
            with self.assertRaises(ValueError):
                project_native_diplomat_context(event)

    def test_non_mapping_present_context_is_invalid(self):
        self.assertFalse(validate_native_diplomat_context(None))
        with self.assertRaises(ValueError):
            project_native_diplomat_context(None)


class DiplomatLegalityTests(unittest.TestCase):
    def test_verified_zero_adds_concrete_unavailable_reason(self):
        existing = {"code": "OTHER_RULE", "text": "已有禁止", "source": "native_rule",
                    "complete": False}
        inspection = _inspection(reasons=[existing])
        original_top_complete = inspection["complete"]
        original_legality_complete = inspection["legality"]["complete"]
        result = apply_diplomat_legality(inspection)
        self.assertIs(result, inspection)
        self.assertEqual("unavailable", result["legality"]["status"])
        self.assertEqual(original_top_complete, result["complete"])
        self.assertEqual(original_legality_complete, result["legality"]["complete"])
        self.assertEqual(["OTHER_RULE", NATIVE_DIPLOMAT_UNAVAILABLE],
                         [item["code"] for item in result["legality"]["reasons"]])
        reason = result["legality"]["reasons"][-1]
        self.assertEqual("native_rule", reason["source"])
        self.assertTrue(reason["complete"])
        self.assertIn("需要空闲外交官", reason["text"])
        self.assertIn("0", reason["text"])

    def test_verified_positive_count_does_not_claim_allocation(self):
        inspection = _inspection(count=2)
        before = copy.deepcopy(inspection)
        result = apply_diplomat_legality(inspection)
        self.assertEqual(before, result)

    def test_required_false_does_not_change_legality_for_zero_or_unreadable(self):
        for verified, count in ((True, 0), (False, None)):
            inspection = _inspection(required=False, verified=verified,
                                     count=count)
            before = copy.deepcopy(inspection)
            self.assertEqual(before, apply_diplomat_legality(inspection))

    def test_unreadable_required_context_adds_runtime_error_and_unknown(self):
        inspection = _inspection(verified=False, count=None, status="available",
                                 complete=True)
        result = apply_diplomat_legality(inspection)
        self.assertEqual("unknown", result["legality"]["status"])
        reason = result["legality"]["reasons"][-1]
        self.assertEqual(NATIVE_DIPLOMAT_CONTEXT_UNAVAILABLE, reason["code"])
        self.assertEqual("runtime_error", reason["source"])
        self.assertFalse(reason["complete"])
        self.assertTrue(result["complete"])
        self.assertFalse(result["legality"]["complete"])

    def test_unreadable_context_keeps_existing_unavailable_status(self):
        inspection = _inspection(verified=False, count=None,
                                 status="unavailable")
        result = apply_diplomat_legality(inspection)
        self.assertEqual("unavailable", result["legality"]["status"])
        self.assertEqual(1, sum(
            item["code"] == NATIVE_DIPLOMAT_CONTEXT_UNAVAILABLE
            for item in result["legality"]["reasons"]))

    def test_accept_and_reject_phases_are_untouched(self):
        for phase in ("accept", "reject"):
            inspection = _inspection(phase=phase, count=0)
            before = copy.deepcopy(inspection)
            self.assertEqual(before, apply_diplomat_legality(inspection))

    def test_incomplete_resource_is_treated_as_unreadable_only_when_required(self):
        inspection = _inspection(count=None, verified=True)
        result = apply_diplomat_legality(inspection)
        self.assertEqual("unknown", result["legality"]["status"])
        self.assertEqual(NATIVE_DIPLOMAT_CONTEXT_UNAVAILABLE,
                         result["legality"]["reasons"][-1]["code"])

        no_resource = {"phase": "initiate", "legality": {"status": "available",
                                                            "reasons": []}}
        self.assertEqual(copy.deepcopy(no_resource),
                         apply_diplomat_legality(no_resource))

    def test_existing_reasons_are_preserved_and_application_is_idempotent(self):
        existing = {"code": "OTHER_RULE", "text": "已有", "source": "native_rule",
                    "complete": False}
        inspection = _inspection(reasons=[existing])
        apply_diplomat_legality(inspection)
        first = copy.deepcopy(inspection)
        apply_diplomat_legality(inspection)
        self.assertEqual(first, inspection)
        codes = [item["code"] for item in inspection["legality"]["reasons"]]
        self.assertEqual(1, codes.count(NATIVE_DIPLOMAT_UNAVAILABLE))
        self.assertEqual(1, codes.count("OTHER_RULE"))

    def test_existing_unavailable_reason_is_not_duplicated(self):
        existing = {"code": NATIVE_DIPLOMAT_UNAVAILABLE, "text": "已有",
                    "source": "native_rule", "complete": True}
        inspection = _inspection(reasons=[existing])
        apply_diplomat_legality(inspection)
        self.assertEqual(1, sum(
            item["code"] == NATIVE_DIPLOMAT_UNAVAILABLE
            for item in inspection["legality"]["reasons"]))


if __name__ == "__main__":
    unittest.main()
