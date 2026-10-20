from __future__ import annotations

import copy
import unittest

from bridge.declarewar_forces import (
    project_declare_war_forces,
    valid_declare_war_forces,
)


def _real_forces() -> dict:
    # Small contract fixture retaining the four raw manpower observations from
    # the same-day save.  Country order is intentionally native/arbitrary.
    return {
        "called": True,
        "action_unchanged": True,
        "unit": "men",
        "units_verified": True,
        "complete": True,
        "attackers": {
            "countries": ["SAV", "FRA"],
            "infantry_raw": 44783,
            "cavalry_raw": 21375,
            "artillery_raw": 0,
            "deployed_total_raw": 66158,
            "reserve_manpower_raw": 66158,
            "deployed_complete": True,
            "reserve_complete": True,
            "scope_complete": True,
        },
        "defenders": {
            "countries": ["HSA", "BUR"],
            "infantry_raw": 28304,
            "cavalry_raw": 22505,
            "artillery_raw": 0,
            "deployed_total_raw": 50809,
            "reserve_manpower_raw": 50809,
            "deployed_complete": True,
            "reserve_complete": True,
            "scope_complete": True,
        },
    }


class DeclareWarForcesTests(unittest.TestCase):
    def test_real_complete_fixture_projects_sorted_safe_public_shape(self) -> None:
        native = _real_forces()
        self.assertTrue(valid_declare_war_forces(native))
        public = project_declare_war_forces(native)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertEqual("native_declare_war_dialog", public["source"])
        self.assertTrue(public["complete"])
        self.assertEqual(["FRA", "SAV"], public["attackers"]["countries"])
        self.assertEqual(["BUR", "HSA"], public["defenders"]["countries"])
        self.assertEqual(
            {"infantry": 44783, "cavalry": 21375, "artillery": 0,
             "total": 66158, "unit": "men", "complete": True},
            public["attackers"]["deployed"],
        )
        self.assertEqual(
            {"amount": 66158, "unit": "men", "complete": True},
            public["attackers"]["reserve_manpower"],
        )
        self.assertNotIn("infantry_raw", str(public))

    def test_unverified_units_hide_all_numeric_values(self) -> None:
        native = _real_forces()
        native["units_verified"] = False
        native["complete"] = False
        self.assertTrue(valid_declare_war_forces(native))
        public = project_declare_war_forces(native)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertFalse(public["complete"])
        for side in (public["attackers"], public["defenders"]):
            self.assertEqual(
                {"infantry": None, "cavalry": None, "artillery": None,
                 "total": None, "unit": None, "complete": False},
                side["deployed"],
            )
            self.assertEqual(
                {"amount": None, "unit": None, "complete": False},
                side["reserve_manpower"],
            )

    def test_total_and_side_identity_contracts_reject_tampering(self) -> None:
        cases = []
        changed = copy.deepcopy(_real_forces())
        changed["attackers"]["deployed_total_raw"] += 1
        cases.append(changed)
        changed = copy.deepcopy(_real_forces())
        changed["attackers"]["countries"] = ["FRA", "FRA"]
        cases.append(changed)
        changed = copy.deepcopy(_real_forces())
        changed["defenders"]["countries"] = ["BUR", "FRA"]
        cases.append(changed)
        changed = copy.deepcopy(_real_forces())
        changed["attackers"]["countries"] = [["FRA"]]
        cases.append(changed)
        for native in cases:
            with self.subTest(native=native):
                self.assertFalse(valid_declare_war_forces(native))
                self.assertIsNone(project_declare_war_forces(native))

    def test_complete_requires_verified_units_and_all_side_completeness(self) -> None:
        native = _real_forces()
        native["units_verified"] = False
        self.assertFalse(valid_declare_war_forces(native))
        native = _real_forces()
        native["attackers"]["scope_complete"] = False
        self.assertFalse(valid_declare_war_forces(native))
        native = _real_forces()
        native["complete"] = False
        native["attackers"]["deployed_complete"] = False
        self.assertTrue(valid_declare_war_forces(native))
        public = project_declare_war_forces(native)
        self.assertFalse(public["complete"])
        self.assertFalse(public["attackers"]["deployed"]["complete"])


if __name__ == "__main__":
    unittest.main()
