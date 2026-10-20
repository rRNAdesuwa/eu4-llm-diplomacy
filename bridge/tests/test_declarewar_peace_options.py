from __future__ import annotations

import copy
import unittest

from bridge.declarewar_peace_options import (
    KIND_ACTION_IDS,
    MAX_RECORDS,
    project_native_peace_options,
    validate_native_peace_options,
    valid_native_peace_options,
)


class DeclareWarPeaceOptionsTests(unittest.TestCase):
    @staticmethod
    def _table(*records: tuple[int, bool], available: bool = True,
               complete: bool = True) -> dict:
        return {
            "available": available,
            "complete": complete,
            "records": [
                {"kind": kind, "auxiliary_present": auxiliary_present}
                for kind, auxiliary_present in records
            ],
        }

    @classmethod
    def _options(cls, *, disabled=None, attacker=None, defender=None,
                 complete: bool = True) -> dict:
        disabled = cls._table((0, False)) if disabled is None else disabled
        attacker = cls._table((3, False), (9, True)) if attacker is None else attacker
        defender = cls._table((7, False)) if defender is None else defender
        return {
            "called": True,
            "action_unchanged": True,
            "complete": complete,
            "disabled": disabled,
            "attacker_declared": attacker,
            "defender_declared": defender,
        }

    def test_full_mapping_preserves_derived_and_auxiliary_identity(self):
        raw = self._options()
        self.assertTrue(valid_native_peace_options(raw))
        self.assertTrue(validate_native_peace_options(raw))
        public = project_native_peace_options(raw)
        self.assertIsNotNone(public)
        assert public is not None

        rules = public
        self.assertFalse(rules["selection_rules_evaluated"])
        self.assertEqual(["demand_ducats"],
                         rules["disabled"]["disabled_actions"])
        self.assertEqual(
            ["cede_province", "full_annexation", "humiliate_rival"],
            rules["attacker_declared"]["declared_justified_actions"],
        )
        self.assertEqual(
            [{"kind": 9, "auxiliary_present": True}],
            rules["attacker_declared"]["unmapped"],
        )
        self.assertTrue(rules["attacker_declared"]["target_evaluation_required"])
        self.assertFalse(rules["attacker_declared"]["target_conditions_evaluated"])
        self.assertEqual(
            ["cede_province", "full_annexation"],
            rules["attacker_declared"]["records"][0]["action_ids"],
        )

    def test_unknown_kind_and_auxiliary_row_are_not_disabled(self):
        raw = self._options(
            disabled=self._table((0, True), (65535, False)),
            attacker=self._table((65535, True)),
            defender=self._table(),
        )
        public = project_native_peace_options(raw)
        self.assertIsNotNone(public)
        assert public is not None
        rules = public
        self.assertEqual([], rules["disabled"]["disabled_actions"])
        self.assertEqual([
            {"kind": 0, "auxiliary_present": True},
            {"kind": 65535, "auxiliary_present": False},
        ], rules["disabled"]["unmapped"])
        self.assertEqual([
            {"kind": 65535, "auxiliary_present": True},
        ], rules["attacker_declared"]["unmapped"])
        self.assertEqual([], rules["attacker_declared"]["declared_justified_actions"])

    def test_empty_and_unavailable_tables_are_valid_without_illegal_inference(self):
        raw = self._options(
            disabled=self._table(available=False, complete=False),
            attacker=self._table(available=True, complete=True),
            defender=self._table(available=False, complete=False),
            complete=False,
        )
        self.assertTrue(valid_native_peace_options(raw))
        public = project_native_peace_options(raw)
        self.assertIsNotNone(public)
        assert public is not None
        rules = public
        self.assertFalse(public["complete"])
        self.assertEqual([], rules["disabled"]["disabled_actions"])
        self.assertEqual([], rules["attacker_declared"]["declared_justified_actions"])
        self.assertTrue(rules["disabled"]["target_evaluation_required"])
        self.assertTrue(rules["defender_declared"]["target_evaluation_required"])

    def test_partial_table_can_be_observed_but_cannot_claim_complete(self):
        raw = self._options(
            attacker=self._table((3, False), available=True, complete=False),
            complete=False,
        )
        self.assertTrue(valid_native_peace_options(raw))
        public = project_native_peace_options(raw)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertFalse(public["complete"])
        self.assertFalse(public["attacker_declared"]["complete"])
        self.assertTrue(public["attacker_declared"]
                        ["target_evaluation_required"])

    def test_shape_and_consistency_errors_are_rejected(self):
        raw = self._options()
        malformed = copy.deepcopy(raw)
        malformed["disabled"]["records"][0]["kind"] = -1
        self.assertFalse(valid_native_peace_options(malformed))
        self.assertIsNone(project_native_peace_options(malformed))

        malformed = copy.deepcopy(raw)
        malformed["attacker_declared"]["records"].append(
            {"kind": 1, "auxiliary_present": False})
        malformed["attacker_declared"]["complete"] = False
        malformed["complete"] = False
        # The outer native summary must track a partial table.
        self.assertFalse(malformed["complete"])
        self.assertTrue(valid_native_peace_options(malformed))
        malformed["complete"] = True
        self.assertFalse(valid_native_peace_options(malformed))

        malformed = copy.deepcopy(raw)
        malformed["defender_declared"]["available"] = False
        malformed["defender_declared"]["records"] = [
            {"kind": 7, "auxiliary_present": False}
        ]
        self.assertFalse(valid_native_peace_options(malformed))

    def test_bounds_and_all_native_action_kinds(self):
        self.assertEqual(256, MAX_RECORDS)
        self.assertIn(26, KIND_ACTION_IDS)
        too_many = self._table(*([(0, False)] * (MAX_RECORDS + 1)))
        raw = self._options(disabled=too_many, complete=True)
        self.assertFalse(valid_native_peace_options(raw))

        raw = self._options(
            disabled=self._table(*[(kind, False)
                                   for kind in KIND_ACTION_IDS]),
            attacker=self._table(*[(kind, True)
                                   for kind in KIND_ACTION_IDS]),
            defender=self._table(),
        )
        self.assertTrue(valid_native_peace_options(raw))
        public = project_native_peace_options(raw)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertIn("force_religion", public
                      ["disabled"]["disabled_actions"])
        self.assertIn("form_personal_union", public
                      ["attacker_declared"]["declared_justified_actions"])


if __name__ == "__main__":
    unittest.main()
