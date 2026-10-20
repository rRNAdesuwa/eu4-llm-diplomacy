from __future__ import annotations

import copy
import unittest

from bridge.peace_overextension import (
    MAX_COUNTRIES,
    MAX_PROVINCES_PER_COUNTRY,
    project_native_overextension,
    validate_native_overextension,
)


def _row(country: str = "FRA", *, current: int = 100,
         recomputed: int | None = None, gained: int = 20, lost: int = 5,
         delta: int | None = None, projected: int | None = None,
         complete: bool = True, cache_matches: bool = True,
         gained_ids: list[int] | None = None,
         lost_ids: list[int] | None = None) -> dict:
    recomputed = current if recomputed is None else recomputed
    projected = current + gained - lost if projected is None else projected
    delta = projected - current if delta is None else delta
    return {
        "country": country,
        "complete": complete,
        "current_raw": current,
        "current_recomputed_raw": recomputed,
        "cache_matches_recomputed": cache_matches,
        "gained_raw": gained,
        "lost_raw": lost,
        "delta_raw": delta,
        "projected_raw": projected,
        "scale": 1000,
        "gained_province_ids": [1] if gained_ids is None else gained_ids,
        "lost_province_ids": [2] if lost_ids is None else lost_ids,
    }


def _native(*countries: dict, called: bool = True,
            complete: bool = True,
            unsupported: bool = False) -> dict:
    return {
        "called": called,
        "complete": complete,
        "scope": "selected_territorial_preview",
        "unsupported_territorial_terms": unsupported,
        "countries": list(countries),
    }


class PeaceOverextensionTests(unittest.TestCase):
    def test_complete_positive_and_negative_net_changes_project_units(self):
        raw = _native(
            _row("FRA", current=100, gained=20, lost=5),
            _row("ENG", current=80, gained=0, lost=30),
        )
        self.assertTrue(validate_native_overextension(raw))
        public = project_native_overextension(raw)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertTrue(public["available"])
        self.assertEqual(15, public["countries"][0]["delta_raw"])
        self.assertAlmostEqual(0.015, public["countries"][0]["delta_fraction"])
        self.assertAlmostEqual(1.5,
                               public["countries"][0]["delta_percentage_points"])
        self.assertEqual(-30, public["countries"][1]["delta_raw"])
        self.assertAlmostEqual(-3.0,
                               public["countries"][1]["delta_percentage_points"])
        self.assertEqual("fraction", public["countries"][0]["unit"])

    def test_one_country_can_gain_and_lose_in_same_preview(self):
        raw = _native(_row(
            "FRA", current=200, gained=40, lost=70, projected=170,
            gained_ids=[10, 11], lost_ids=[20, 21]))
        self.assertTrue(validate_native_overextension(raw))
        public = project_native_overextension(raw)
        self.assertIsNotNone(public)
        assert public is not None
        row = public["countries"][0]
        self.assertEqual([10, 11], row["gained_province_ids"])
        self.assertEqual([20, 21], row["lost_province_ids"])
        self.assertEqual(-30, row["delta_raw"])

    def test_cache_mismatch_is_valid_partial_raw_diagnostic(self):
        raw = _native(_row(
            current=-4, recomputed=9, gained=-3, lost=-2,
            delta=17, projected=13, complete=False, cache_matches=False),
            complete=False)
        self.assertTrue(validate_native_overextension(raw))
        public = project_native_overextension(raw)
        self.assertIsNotNone(public)
        assert public is not None
        row = public["countries"][0]
        self.assertFalse(public["complete"])
        self.assertFalse(row["available"])
        self.assertEqual(-4, row["current_raw"])
        self.assertEqual(-0.003, row["gained_fraction"])

    def test_unsupported_release_keeps_called_but_not_complete(self):
        raw = _native(
            _row("FRA"), _row("ENG", current=0, gained=0, lost=0,
                              projected=0, gained_ids=[], lost_ids=[]),
            complete=False, unsupported=True)
        self.assertTrue(validate_native_overextension(raw))
        public = project_native_overextension(raw)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertTrue(public["available"])
        self.assertFalse(public["complete"])
        self.assertTrue(public["unsupported_territorial_terms"])

    def test_bounds_duplicates_and_faked_arithmetic_are_rejected(self):
        too_many = _native(*[_row(f"{index:03d}")
                              for index in range(MAX_COUNTRIES + 1)])
        self.assertFalse(validate_native_overextension(too_many))

        duplicate_country = _native(_row("FRA"), _row("FRA"))
        self.assertFalse(validate_native_overextension(duplicate_country))

        duplicate_province = _native(_row(gained_ids=[10, 10]))
        self.assertFalse(validate_native_overextension(duplicate_province))
        too_many_provinces = _native(_row(
            gained_ids=list(range(1, MAX_PROVINCES_PER_COUNTRY + 2))))
        self.assertFalse(validate_native_overextension(too_many_provinces))

        faked_delta = _native(_row(delta=999))
        self.assertFalse(validate_native_overextension(faked_delta))

        cache_false_complete = _native(_row(cache_matches=False))
        self.assertFalse(validate_native_overextension(cache_false_complete))

        bad_scale = _native(_row())
        bad_scale["countries"][0]["scale"] = 100
        self.assertFalse(validate_native_overextension(bad_scale))

        malformed = copy.deepcopy(_native(_row()))
        malformed["extra"] = True
        self.assertFalse(validate_native_overextension(malformed))

    def test_top_complete_requires_supported_complete_rows(self):
        raw = _native(_row(), complete=True, unsupported=True)
        self.assertFalse(validate_native_overextension(raw))
        raw = _native(_row(complete=False), complete=True)
        self.assertFalse(validate_native_overextension(raw))
        raw = _native(_row(), called=False, complete=True)
        self.assertFalse(validate_native_overextension(raw))


if __name__ == "__main__":
    unittest.main()
