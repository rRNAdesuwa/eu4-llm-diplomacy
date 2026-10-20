from __future__ import annotations

import copy
import unittest

from bridge.peace_justification import (
    NATIVE_TERM_ACTIONS,
    project_native_justification,
    validate_native_justification,
)


def _row(index: int = 0, *, type_id: int = 0x2D2B, bucket: int = 0,
         selected: bool = True, applicable: bool = True,
         evaluated: bool = True, justified: bool | None = True,
         province_id: int | None = None, object_country: str | None = None,
         complete: bool = True) -> dict:
    return {
        "index": index,
        "type_id": type_id,
        "bucket": bucket,
        "selected": selected,
        "applicable": applicable,
        "evaluated": evaluated,
        "justified": justified,
        "province_id": province_id,
        "object_country": object_country,
        "complete": complete,
    }


def _native(*terms: dict, called: bool = True, complete: bool = True,
            direction: str = "demand", unsupported: int = 0) -> dict:
    return {
        "called": called,
        "complete": complete,
        "direction": direction,
        "term_count": len(terms) + unsupported,
        "unsupported_count": unsupported,
        "terms": list(terms),
    }


class PeaceJustificationTests(unittest.TestCase):
    def test_complete_projection_maps_native_families(self):
        rows = [
            _row(0, type_id=0x2D25, bucket=3, province_id=123),
            _row(1, type_id=0x2D28, bucket=0x0F, object_country="ENG"),
            _row(2, type_id=0x3C05, bucket=2, object_country="FRA"),
            _row(3, type_id=0x2D2A, bucket=0x1A, object_country="SAV"),
        ]
        raw = _native(*rows)
        self.assertTrue(validate_native_justification(raw))
        public = project_native_justification(raw)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertTrue(public["complete"])
        self.assertEqual("justified", public["selected_terms_status"])
        self.assertEqual(
            ["cede_province", "release_nation", "force_vassalization",
             "form_personal_union"],
            [term["action_id"] for term in public["terms"]],
        )
        self.assertEqual("native_rule", public["terms"][0]["source"])

    def test_selected_status_precedence_and_no_selection(self):
        raw = _native(
            _row(0, selected=True, evaluated=True, justified=True),
            _row(1, selected=True, evaluated=True, justified=False),
            _row(2, selected=True, evaluated=False, justified=None,
                 complete=False),
            complete=False,
        )
        public = project_native_justification(raw)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertEqual("unjustified", public["selected_terms_status"])
        self.assertEqual(
            ["justified", "unjustified", "unknown"],
            [term["status"] for term in public["terms"]],
        )

        no_selection = _native(_row(selected=False))
        public = project_native_justification(no_selection)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertEqual("not_applicable", public["selected_terms_status"])

    def test_unknown_family_or_unassessed_row_is_unknown(self):
        raw = _native(
            _row(type_id=0xDEADBEEF, bucket=39),
            _row(1, evaluated=False, justified=None, complete=False),
            complete=False,
        )
        self.assertTrue(validate_native_justification(raw))
        public = project_native_justification(raw)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertEqual("unknown", public["selected_terms_status"])
        self.assertIsNone(public["terms"][0]["action_id"])
        self.assertEqual("unknown", public["terms"][0]["status"])

    def test_strict_shape_bounds_and_cardinality(self):
        valid = _native(_row())
        malformed = copy.deepcopy(valid)
        malformed["extra"] = True
        self.assertFalse(validate_native_justification(malformed))

        malformed = copy.deepcopy(valid)
        malformed["terms"][0]["index"] = 1
        self.assertFalse(validate_native_justification(malformed))
        malformed = copy.deepcopy(valid)
        malformed["terms"].append(_row(0))
        malformed["term_count"] = 2
        self.assertFalse(validate_native_justification(malformed))

        malformed = copy.deepcopy(valid)
        malformed["unsupported_count"] = 1
        self.assertFalse(validate_native_justification(malformed))
        malformed = copy.deepcopy(valid)
        malformed["terms"][0]["bucket"] = 40
        self.assertFalse(validate_native_justification(malformed))

    def test_complete_requires_called_evaluated_rows_and_no_unsupported(self):
        raw = _native(_row(), called=False)
        self.assertFalse(validate_native_justification(raw))
        raw = _native(_row(complete=False), complete=True)
        self.assertFalse(validate_native_justification(raw))
        raw = _native(_row(), unsupported=1)
        self.assertFalse(validate_native_justification(raw))

        partial = _native(
            _row(evaluated=False, justified=None, complete=False),
            complete=False,
        )
        self.assertTrue(validate_native_justification(partial))
        self.assertIsNotNone(project_native_justification(partial))

    def test_all_native_term_pairs_have_public_action_ids(self):
        self.assertEqual(18, len(NATIVE_TERM_ACTIONS))
        for index, ((type_id, bucket), action_id) in enumerate(
                NATIVE_TERM_ACTIONS.items()):
            raw = _native(_row(index, type_id=type_id, bucket=bucket),
                          complete=False, unsupported=index)
            public = project_native_justification(raw)
            self.assertIsNotNone(public)
            assert public is not None
            self.assertEqual(action_id, public["terms"][0]["action_id"])


if __name__ == "__main__":
    unittest.main()
