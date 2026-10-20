from __future__ import annotations

import copy
import unittest

from bridge.favor_resources import (
    INT32_MAX,
    INT32_MIN,
    NATIVE_ACCEPT,
    NATIVE_REJECT,
    project_query,
    project_result,
    validate_query,
    validate_result,
)


def trust_query(**overrides):
    value = {
        "kind": "trust",
        "amount_raw": 10,
        "amount_readable": True,
        "favor_cost_raw": 7,
        "favors_available_raw": 20,
        "recipient_trust_raw": 95,
        "resource_scale": 1,
        "complete": True,
    }
    value.update(overrides)
    return value


def men_query(**overrides):
    value = {
        "kind": "men",
        "amount_raw": 25,
        "amount_readable": True,
        "favor_cost_raw": 10,
        "favors_available_raw": 40,
        "actor_manpower_raw": 100,
        "recipient_manpower_raw": 50,
        "resource_scale": 1,
        "complete": True,
    }
    value.update(overrides)
    return value


def trust_state(trust, favors, cost, complete=True):
    return {
        "complete": complete,
        "recipient_trust_raw": trust,
        "favors_raw": favors,
        "cost_raw": cost,
    }


def men_state(actor, recipient, favors, cost, complete=True):
    return {
        "complete": complete,
        "actor_manpower_raw": actor,
        "recipient_manpower_raw": recipient,
        "favors_raw": favors,
        "cost_raw": cost,
    }


def trust_result(*, amount=10, before=None, after=None, complete=True,
                 verified=True):
    before = before or trust_state(95, 20, 7)
    after = after or trust_state(100, 13, 7)
    return {
        "kind": "trust",
        "before": before,
        "after": after,
        "amount_raw": amount,
        "complete": complete,
        "verified": verified,
    }


def men_result(*, amount=25, before=None, after=None, complete=True,
               verified=True):
    before = before or men_state(100, 50, 40, 10)
    after = after or men_state(125, 25, 30, 10)
    return {
        "kind": "men",
        "before": before,
        "after": after,
        "amount_raw": amount,
        "complete": complete,
        "verified": verified,
    }


class FavorResourceQueryTests(unittest.TestCase):
    def test_trust_query_projects_direction_and_scale_one(self):
        value = trust_query()
        self.assertTrue(validate_query(value))
        projected = project_query(value, "FRA", "PAP")
        self.assertEqual(10.0, projected["amount"]["value"])
        self.assertEqual(("PAP", "FRA"),
                         (projected["trust"]["trustor"], projected["trust"]["trusted"]))
        self.assertEqual("recipient_to_actor", projected["trust"]["direction"])
        self.assertEqual("recipient_to_actor", projected["amount"]["direction"])
        self.assertEqual(("PAP", "FRA"),
                         (projected["favors"]["owed_by"], projected["favors"]["held_by"]))
        self.assertEqual(1, projected["amount"]["scale"])
        self.assertEqual(1000, projected["favors"]["scale"])
        self.assertEqual(0.02, projected["favors"]["current"])
        self.assertNotIn("payer", projected["amount"])

    def test_men_query_publishes_both_visible_manpower_values(self):
        projected = project_query(men_query(), "FRA", "SAV")
        self.assertTrue(validate_query(men_query()))
        self.assertEqual({"actor": "FRA", "recipient": "SAV"},
                         {k: projected["manpower"][k] for k in ("actor", "recipient")})
        self.assertEqual((100, 50),
                         (projected["manpower"]["actor_raw"],
                          projected["manpower"]["recipient_raw"]))
        self.assertEqual("men", projected["amount"]["unit"])

    def test_query_rejects_cross_kind_extra_fields_bool_ints_negative_and_bad_scale(self):
        crossed = men_query()
        crossed["recipient_trust_raw"] = 95
        self.assertFalse(validate_query(crossed))
        self.assertFalse(validate_query(trust_query(amount_raw=True)))
        self.assertFalse(validate_query(trust_query(amount_raw=-1)))
        self.assertFalse(validate_query(trust_query(recipient_trust_raw=101)))
        self.assertFalse(validate_query(men_query(recipient_manpower_raw=-1)))
        self.assertFalse(validate_query(men_query(resource_scale=1000)))
        self.assertFalse(validate_query(men_query(amount_raw=INT32_MAX + 1)))


class FavorResourceSettlementTests(unittest.TestCase):
    def test_trust_accept_clamps_at_100_and_spends_favors(self):
        result = trust_result()
        self.assertTrue(validate_result(result, NATIVE_ACCEPT))
        projected = project_result(result, "FRA", "PAP", NATIVE_ACCEPT)
        self.assertEqual("accepted", projected["native_outcome"])
        self.assertEqual(5, projected["trust"]["change_raw"])
        self.assertEqual(7, projected["favors"]["spent_raw"])

    def test_men_accept_moves_same_amount_and_spends_favors(self):
        result = men_result()
        self.assertTrue(validate_result(result, NATIVE_ACCEPT))
        projected = project_result(result, "FRA", "SAV", NATIVE_ACCEPT)
        self.assertEqual((25, -25),
                         (projected["manpower"]["actor_change_raw"],
                          projected["manpower"]["recipient_change_raw"]))
        self.assertEqual(10, projected["favors"]["spent_raw"])
        self.assertEqual(1, projected["manpower"]["scale"])
        self.assertEqual(("SAV", "FRA"),
                         (projected["amount"]["payer"], projected["amount"]["receiver"]))

    def test_men_reject_requires_all_resource_and_favor_fields_unchanged(self):
        before = men_state(100, 50, 40, 10)
        rejected = men_result(before=before, after=copy.deepcopy(before))
        self.assertTrue(validate_result(rejected, NATIVE_REJECT))
        tampered = copy.deepcopy(rejected)
        tampered["after"]["recipient_manpower_raw"] -= 1
        self.assertFalse(validate_result(tampered, NATIVE_REJECT))
        tampered = copy.deepcopy(rejected)
        tampered["after"]["cost_raw"] += 1
        self.assertFalse(validate_result(tampered, NATIVE_REJECT))

    def test_trust_reject_is_unchanged_and_tampered_verified_flag_is_not_enough(self):
        before = trust_state(50, 20, 7)
        rejected = trust_result(amount=10, before=before,
                                after=copy.deepcopy(before))
        self.assertTrue(validate_result(rejected, NATIVE_REJECT))
        tampered = copy.deepcopy(rejected)
        tampered["after"]["recipient_trust_raw"] = 60
        self.assertFalse(validate_result(tampered, NATIVE_REJECT))
        unverified = copy.deepcopy(tampered)
        unverified["verified"] = False
        self.assertTrue(validate_result(unverified, NATIVE_REJECT))
        projected = project_result(unverified, "FRA", "PAP", NATIVE_REJECT)
        self.assertFalse(projected["verified"])
        self.assertEqual("unknown", projected["native_outcome"])

    def test_men_insufficient_recipient_and_int32_overflow_are_rejected(self):
        insufficient = men_result(
            before=men_state(100, 20, 40, 10),
            after=men_state(125, 0, 30, 10),
        )
        self.assertFalse(validate_result(insufficient, NATIVE_ACCEPT))
        no_favors = trust_result(
            before=trust_state(50, 6, 7),
            after=trust_state(60, -1, 7),
        )
        self.assertFalse(validate_result(no_favors, NATIVE_ACCEPT))
        already_max = trust_result(
            before=trust_state(100, 20, 7),
            after=trust_state(100, 13, 7),
        )
        self.assertFalse(validate_result(already_max, NATIVE_ACCEPT))
        overflow = men_result(
            before=men_state(INT32_MAX, 50, 40, 10),
            after=men_state(INT32_MIN, 25, 30, 10),
        )
        self.assertFalse(validate_result(overflow, NATIVE_ACCEPT))
        favor_underflow = trust_result(
            before=trust_state(10, INT32_MIN, 1),
            after=trust_state(20, INT32_MAX, 1), amount=10,
        )
        self.assertFalse(validate_result(favor_underflow, NATIVE_ACCEPT))

    def test_cross_kind_and_bool_result_fields_are_rejected(self):
        crossed = men_result()
        crossed["kind"] = "trust"
        self.assertFalse(validate_result(crossed, NATIVE_ACCEPT))
        invalid_trust = trust_result(before=trust_state(101, 20, 7))
        self.assertFalse(validate_result(invalid_trust, NATIVE_ACCEPT))
        bool_amount = trust_result()
        bool_amount["amount_raw"] = True
        self.assertFalse(validate_result(bool_amount, NATIVE_ACCEPT))
        bool_state = men_result()
        bool_state["before"]["actor_manpower_raw"] = False
        self.assertFalse(validate_result(bool_state, NATIVE_ACCEPT))
        self.assertFalse(validate_result(trust_result(), True))

    def test_incomplete_or_unverified_result_is_unknown_until_proof_is_complete(self):
        result = trust_result(complete=False, verified=False,
                              before=trust_state(95, 20, 7, complete=False),
                              after=trust_state(100, 13, 7, complete=False))
        self.assertTrue(validate_result(result, NATIVE_ACCEPT))
        projected = project_result(result, "FRA", "PAP", NATIVE_ACCEPT)
        self.assertEqual("unknown", projected["native_outcome"])
        self.assertIsNone(projected["trust"]["change_raw"])
        self.assertFalse(projected["favors"]["available"])


if __name__ == "__main__":
    unittest.main()
