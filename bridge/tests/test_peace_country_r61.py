from __future__ import annotations

import unittest

from bridge.diplomacy_catalog import ACTIONS
from bridge.diplomacy import ObserverSession
from bridge.peace_country import (
    COUNTRY_SELECTION_KEYS,
    COUNTRY_TERM_ACTIONS,
    COUNTRY_TERM_CANONICAL_ORDER,
    COUNTRY_TERM_MASKS,
    PEACE_TERM_CANONICAL_ORDER,
    PEACE_TERM_MASK_ORDER,
    country_mask_for_terms,
    extract_country_selection,
    normalize_country_term,
)
from bridge.peace_execution import normalize_peace_execution_parameters


WAR_ID = "war_0123456789abcdef_01234567"
ACTOR = "FRA"
RECIPIENT = "ENG"


def _parameters(action_id: str, terms: list[dict[str, object]],
                direction: str = "demand") -> dict[str, object]:
    return normalize_peace_execution_parameters(
        action_id, ACTOR, RECIPIENT, "initiate", {
            "peace_context": {
                "war_id": WAR_ID,
                "direction": direction,
                "terms": terms,
            },
        })


class PeaceCountryR61Tests(unittest.TestCase):
    def test_selected_rules_complete_rejection_is_valid_native_rule_state(self) -> None:
        selected_rules = {
            "checked": True,
            "cost_checked": True,
            "available": False,
            "anchor_identity_verified": True,
            "payload_unchanged": True,
            "diagnostic_readable": True,
            "diagnostic_truncated": False,
            "selected_term_count": 1,
            "checked_term_count": 1,
            "diagnostic_hex": "",
            "complete": True,
        }
        payload = {"selected_term_count": 1}
        self.assertTrue(ObserverSession._valid_native_selected_rules(
            selected_rules, payload, 1))
        self.assertFalse(ObserverSession._valid_native_selected_rules(
            {**selected_rules, "payload_unchanged": False}, payload, 1))
        # A complete native rejection is still a complete observation; the
        # public legality layer must classify it as unavailable rather than
        # turning it into an adapter-format error.
        self.assertFalse(selected_rules["available"])

    def test_selected_rules_incomplete_does_not_authorize_country_terms(self) -> None:
        selected_rules = {
            "checked": False,
            "cost_checked": False,
            "available": False,
            "anchor_identity_verified": False,
            "payload_unchanged": False,
            "diagnostic_readable": False,
            "diagnostic_truncated": False,
            "selected_term_count": 0,
            "checked_term_count": 0,
            "diagnostic_hex": "",
            "complete": False,
        }
        self.assertTrue(ObserverSession._valid_native_selected_rules(
            selected_rules, {"selected_term_count": 0}, 0))
        self.assertFalse(selected_rules["complete"])

    def test_canonical_masks_and_selection_keys(self) -> None:
        self.assertEqual(PEACE_TERM_MASK_ORDER, "mprtcahsfbvlxnzuie")
        self.assertEqual(
            COUNTRY_TERM_CANONICAL_ORDER,
            ("release_nation", "force_vassalization",
             "form_personal_union", "grant_independence",
             "full_annexation"),
        )
        self.assertEqual(
            tuple(COUNTRY_TERM_MASKS[action]
                  for action in COUNTRY_TERM_CANONICAL_ORDER),
            ("n", "z", "u", "i", "e"),
        )
        self.assertEqual(
            COUNTRY_SELECTION_KEYS,
            ("release_nation_country", "release_nation_source",
             "vassal_country", "union_country", "independence_country",
             "annex_country", "vassal_beneficiary", "union_beneficiary",
             "annex_beneficiary"),
        )

    def test_defaults_follow_direction_and_grant_has_no_public_country(self) -> None:
        self.assertEqual(
            normalize_country_term(
                {"action_id": "release_nation", "country": "TYR"},
                "release_nation", ACTOR, RECIPIENT, "demand"),
            {"action_id": "release_nation", "country": "TYR",
             "source": RECIPIENT},
        )
        self.assertEqual(
            normalize_country_term(
                {"action_id": "release_nation", "country": "TYR"},
                "release_nation", ACTOR, RECIPIENT, "offer"),
            {"action_id": "release_nation", "country": "TYR",
             "source": ACTOR},
        )
        self.assertEqual(
            normalize_country_term(
                {"action_id": "force_vassalization", "country": "TYR"},
                "force_vassalization", ACTOR, RECIPIENT, "demand"),
            {"action_id": "force_vassalization", "country": "TYR",
             "beneficiary": ACTOR},
        )
        self.assertEqual(
            normalize_country_term(
                {"action_id": "grant_independence"},
                "grant_independence", ACTOR, RECIPIENT, "demand"),
            {"action_id": "grant_independence"},
        )

    def test_explicit_third_country_roles_are_preserved(self) -> None:
        terms = [
            {"action_id": "release_nation", "country": "TYR",
             "source": "AMG"},
            {"action_id": "force_vassalization", "country": "AUV",
             "beneficiary": "SCO"},
            {"action_id": "form_personal_union", "country": "PRO",
             "beneficiary": "SAV"},
            {"action_id": "grant_independence"},
            {"action_id": "full_annexation", "country": "ULS",
             "beneficiary": "GEN"},
        ]
        normalized = _parameters("full_annexation", terms)
        self.assertEqual(
            normalized["peace_context"]["terms"],
            [
                terms[0], terms[1], terms[2], terms[3], terms[4],
            ],
        )
        self.assertEqual(
            country_mask_for_terms(terms), "nzuie")
        self.assertEqual(
            extract_country_selection(terms, ACTOR, RECIPIENT, "demand"),
            {
                "release_nation_country": "TYR",
                "release_nation_source": "AMG",
                "vassal_country": "AUV",
                "union_country": "PRO",
                "independence_country": RECIPIENT,
                "annex_country": "ULS",
                "vassal_beneficiary": "SCO",
                "union_beneficiary": "SAV",
                "annex_beneficiary": "GEN",
            },
        )

    def test_empty_terms_are_candidate_discovery_only(self) -> None:
        for action_id in COUNTRY_TERM_ACTIONS:
            normalized = _parameters(action_id, [])
            self.assertEqual(normalized["peace_context"]["terms"], [])
            self.assertEqual(country_mask_for_terms([], primary_action=action_id),
                             COUNTRY_TERM_MASKS[action_id])
        self.assertEqual(
            extract_country_selection([], ACTOR, RECIPIENT, "demand"),
            {key: "-" for key in COUNTRY_SELECTION_KEYS},
        )

    def test_self_roles_and_extra_public_fields_are_rejected(self) -> None:
        invalid = [
            ({"action_id": "release_nation", "country": "TYR",
              "source": "TYR"}, "PEACE_EXECUTION_RELEASE_NATION_PARTIES_INVALID"),
            ({"action_id": "full_annexation", "country": "TYR",
              "beneficiary": "TYR"}, "PEACE_EXECUTION_COUNTRY_PARTIES_INVALID"),
            ({"action_id": "grant_independence", "country": "TYR"},
             "PEACE_EXECUTION_TERM_INVALID"),
            ({"action_id": "full_annexation", "country": "tyr"},
             "PEACE_EXECUTION_COUNTRY_INVALID"),
        ]
        for term, code in invalid:
            with self.assertRaisesRegex(ValueError, code):
                normalize_country_term(term, term["action_id"],
                                       ACTOR, RECIPIENT, "demand")

    def test_country_actions_are_included_in_mixed_normalization(self) -> None:
        terms = [
            {"action_id": "demand_ducats", "amount": "10.0",
             "payer": RECIPIENT, "claimant": ACTOR},
            {"action_id": "release_nation", "country": "TYR"},
            {"action_id": "full_annexation", "country": "ULS"},
        ]
        normalized = _parameters("demand_ducats", terms)
        self.assertEqual(
            [term["action_id"] for term in normalized["peace_context"]["terms"]],
            ["demand_ducats", "release_nation", "full_annexation"],
        )
        self.assertEqual(
            normalized["peace_context"]["terms"][1]["source"], RECIPIENT)

    def test_more_than_eighteen_terms_is_rejected_before_term_details(self) -> None:
        terms = [{"action_id": "grant_independence"} for _ in range(19)]
        with self.assertRaisesRegex(ValueError, "PEACE_EXECUTION_TERMS_INVALID"):
            _parameters("grant_independence", terms)

    def test_catalog_describes_country_parameters_and_full_contract(self) -> None:
        expected_parameters = {
            "full_annexation": ("country", "beneficiary"),
            "release_nation": ("country", "source"),
            "force_vassalization": ("country", "beneficiary"),
            "form_personal_union": ("country", "beneficiary"),
            "grant_independence": (),
        }
        for action_id, expected in expected_parameters.items():
            self.assertEqual(ACTIONS[action_id].parameters[1:], expected)
            description = ACTIONS[action_id].describe()
            terms = description["parameter_definitions"]["peace_context.terms"]
            self.assertEqual(terms["min_length"], 0)
            self.assertEqual(terms["max_length"], 18)
            self.assertEqual(terms["allowed_action_ids"],
                             list(PEACE_TERM_CANONICAL_ORDER))
            self.assertEqual(terms["canonical_order"],
                             list(PEACE_TERM_CANONICAL_ORDER))
            self.assertEqual(terms["required_action_ids"], [action_id])
            self.assertIn("candidate_discovery", {
                form["name"] for form in description["inspection_parameter_forms"]
            })


if __name__ == "__main__":
    unittest.main()
