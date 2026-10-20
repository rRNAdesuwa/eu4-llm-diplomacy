from __future__ import annotations

import unittest

from bridge.declarewar_selection import (
    MAX_PARTICIPANTS,
    PARTICIPANT_FIELDS,
    country_csv,
    normalize_participant_selection,
    participant_selection_requested,
    validate_participant_selection,
)


class DeclareWarSelectionTests(unittest.TestCase):
    def test_missing_fields_default_and_valid_lists_are_sorted(self):
        self.assertEqual(
            normalize_participant_selection({}),
            {"call_allies": [], "promise_land_to": [],
             "co_belligerents": []},
        )
        parameters = {
            "casus_belli": "cb_conquest",
            "call_allies": ["ZZZ", "ENG", "SWE"],
            "promise_land_to": ["SWE", "ENG"],
            "co_belligerents": ["AUV", "POR"],
        }
        self.assertEqual(
            normalize_participant_selection(parameters, actor="FRA",
                                            recipient="GEN"),
            {"call_allies": ["ENG", "SWE", "ZZZ"],
             "promise_land_to": ["ENG", "SWE"],
             "co_belligerents": ["AUV", "POR"]},
        )
        self.assertEqual(
            validate_participant_selection(parameters, actor="FRA",
                                           recipient="GEN"),
            normalize_participant_selection(parameters, actor="FRA",
                                            recipient="GEN"),
        )

    def test_promise_is_subset_and_co_belligerents_are_disjoint(self):
        with self.assertRaisesRegex(
                ValueError, "DECLARE_WAR_PROMISE_LAND_TO_NOT_CALL_ALLY"):
            normalize_participant_selection({
                "call_allies": ["ENG"],
                "promise_land_to": ["SWE"],
            }, recipient="POR")
        with self.assertRaisesRegex(
                ValueError, "DECLARE_WAR_CO_BELLIGERENT_OVERLAP"):
            normalize_participant_selection({
                "call_allies": ["ENG"],
                "promise_land_to": ["ENG"],
                "co_belligerents": ["ENG"],
            }, recipient="POR")

    def test_each_field_has_type_tag_duplicate_and_bound_checks(self):
        for field in PARTICIPANT_FIELDS:
            with self.assertRaisesRegex(
                    ValueError, f"DECLARE_WAR_{field.upper()}_INVALID"):
                normalize_participant_selection({field: "ENG"}, recipient="POR")
            with self.assertRaisesRegex(
                    ValueError, f"DECLARE_WAR_{field.upper()}_TAG_INVALID"):
                normalize_participant_selection({field: ["eng"]}, recipient="POR")
            with self.assertRaisesRegex(
                    ValueError, f"DECLARE_WAR_{field.upper()}_DUPLICATE"):
                normalize_participant_selection({field: ["ENG", "ENG"]},
                                                recipient="POR")
            tags = [f"A{index:02d}" for index in range(MAX_PARTICIPANTS + 1)]
            with self.assertRaisesRegex(
                    ValueError, f"DECLARE_WAR_{field.upper()}_TOO_MANY"):
                normalize_participant_selection({field: tags}, recipient="POR")

    def test_actor_and_recipient_cannot_be_selected_participants(self):
        for field in PARTICIPANT_FIELDS:
            with self.assertRaisesRegex(
                    ValueError, f"DECLARE_WAR_{field.upper()}_MAIN_PARTY"):
                normalize_participant_selection({field: ["FRA"]},
                                                actor="FRA", recipient="POR")
            with self.assertRaisesRegex(
                    ValueError, f"DECLARE_WAR_{field.upper()}_MAIN_PARTY"):
                normalize_participant_selection({field: ["POR"]},
                                                actor="FRA", recipient="POR")
        with self.assertRaisesRegex(ValueError, "DECLARE_WAR_ACTOR_INVALID"):
            normalize_participant_selection({}, actor="fra")
        with self.assertRaisesRegex(ValueError, "DECLARE_WAR_RECIPIENT_INVALID"):
            normalize_participant_selection({}, recipient="eng")

    def test_csv_serialization_and_requested_marker(self):
        self.assertEqual("-", country_csv([]))
        self.assertEqual("ENG,SWE,ZZZ", country_csv(["ZZZ", "ENG", "SWE"]))
        with self.assertRaisesRegex(ValueError,
                                    "DECLARE_WAR_PARTICIPANTS_DUPLICATE"):
            country_csv(["ENG", "ENG"])
        self.assertFalse(participant_selection_requested({}))
        self.assertFalse(participant_selection_requested({
            "call_allies": [], "promise_land_to": [],
            "co_belligerents": [],
        }))
        self.assertTrue(participant_selection_requested({"promise_land_to": ["ENG"]}))
        self.assertTrue(participant_selection_requested({"co_belligerents": ["SWE"]}))
        with self.assertRaisesRegex(ValueError,
                                    "DECLARE_WAR_PARTICIPANT_SELECTION_INVALID"):
            participant_selection_requested(None)
        with self.assertRaisesRegex(ValueError, "DECLARE_WAR_CALL_ALLIES_INVALID"):
            participant_selection_requested({"call_allies": "ENG"})


if __name__ == "__main__":
    unittest.main()
