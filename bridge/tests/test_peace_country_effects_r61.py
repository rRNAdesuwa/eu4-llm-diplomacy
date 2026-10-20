from __future__ import annotations

import copy
import unittest

from bridge.diplomacy import ObserverSession


DATE_RAW = 56549088


def _territory(*, country: str, other_key: str, other: str,
               owner_before: str, owner_after: str,
               owned_before: int, owned_after: int,
               other_before: int, other_after: int) -> dict:
    return {
        "country": country,
        other_key: other,
        "owned_count_before": owned_before,
        "owned_count_after": owned_after,
        f"{other_key}_owned_count_before": other_before,
        f"{other_key}_owned_count_after": other_after,
        "province_rows": [{
            "province_id": 1,
            "owner_before": owner_before,
            "owner_after": owner_after,
            "controller_before": owner_before,
            "controller_after": owner_after,
            "complete": True,
        }],
        "complete": True,
        "values_readable": True,
        "unchanged": False,
        "verified": True,
    }


def _relation(*, country: str, beneficiary: str,
              before: bool, after: bool,
              before_overlord: bool, after_overlord: bool,
              before_type: str | None, after_type: str | None) -> dict:
    return {
        "country": country,
        "beneficiary": beneficiary,
        "relation_active_before": before,
        "relation_active_after": after,
        "is_overlord_before": before_overlord,
        "is_overlord_after": after_overlord,
        "subject_type_before": before_type,
        "subject_type_after": after_type,
        "complete": True,
        "values_readable": True,
        "unchanged": False,
        "verified": True,
    }


def _grant() -> dict:
    return {
        "country": "FRA",
        "overlord": "ENG",
        "relation_active_before": True,
        "relation_active_after": False,
        "is_overlord_before": True,
        "is_overlord_after": False,
        "subject_type_before": "vassal",
        "subject_type_after": None,
        "overlord_count_before": 1,
        "overlord_count_after": 0,
        "overlord_scan_complete_before": True,
        "overlord_scan_complete_after": True,
        "no_other_overlords_before": False,
        "no_other_overlords_after": True,
        "complete": True,
        "values_readable": True,
        "unchanged": False,
        "verified": True,
        "reason_code": None,
    }


def _accepted_effects() -> dict:
    return {
        "complete": True,
        "date_unchanged": True,
        "currency_scale": 1000,
        "money": None,
        "provinces": [],
        "country_terms": {
            "release_nation": _territory(
                country="TYR", other_key="source", other="ENG",
                owner_before="ENG", owner_after="TYR",
                owned_before=1, owned_after=2, other_before=5, other_after=4),
            "force_vassalization": _relation(
                country="AUV", beneficiary="FRA", before=False, after=True,
                before_overlord=False, after_overlord=True,
                before_type=None, after_type="vassal"),
            "form_personal_union": _relation(
                country="PRO", beneficiary="FRA", before=False, after=True,
                before_overlord=False, after_overlord=True,
                before_type=None, after_type="personal_union"),
            "grant_independence": _grant(),
            "full_annexation": _territory(
                country="ULS", other_key="beneficiary", other="FRA",
                owner_before="ULS", owner_after="FRA",
                owned_before=1, owned_after=0, other_before=2, other_after=3),
        },
    }


class PeaceCountryEffectsR61Tests(unittest.TestCase):
    def _inbound_full_annex_context(self, proof: dict | None = None) -> dict:
        value = {
            "war_id": "war_0123456789abcdef_01234567",
            "direction": "offer",
            "original_actor": "ENG",
            "original_recipient": "FRA",
            "terms": [{
                "action_id": "full_annexation",
                "country": "TYR",
                "beneficiary": "FRA",
            }],
            "complete": True,
            "selected_terms_complete": True,
        }
        if proof is not None:
            value["full_annex_proof"] = proof
        return value

    def test_inbound_full_annex_proof_binds_derived_term(self) -> None:
        proof = {
            "live_offer_present": True,
            "live_snapshot_complete": True,
            "sealed_snapshot_equal": True,
            "selected_cede_complete": True,
            "selected_cede_unique": True,
            "owner_owned_ids_complete": True,
            "native_check_called": True,
            "native_check_result": True,
            "preflight_proof_reused": False,
            "request_identity_matches": True,
            "derived": True,
            "owner": "TYR",
            "beneficiary": "FRA",
            "selected_cede_count": 2,
            "owned_count": 2,
            "reason": "LIVE_NATIVE_FULL_ANNEX_PROVEN",
        }
        fields = ObserverSession._inbound_peace_context_fields(
            self._inbound_full_annex_context(proof), "ENG", "FRA")
        self.assertIsNotNone(fields)
        self.assertTrue(fields["full_annex_proof_verified"])

    def test_inbound_full_annex_proof_mismatch_is_rejected_and_legacy_absent_is_allowed(self) -> None:
        proof = {
            "live_offer_present": True,
            "live_snapshot_complete": True,
            "sealed_snapshot_equal": True,
            "selected_cede_complete": True,
            "selected_cede_unique": True,
            "owner_owned_ids_complete": True,
            "native_check_called": True,
            "native_check_result": True,
            "preflight_proof_reused": False,
            "request_identity_matches": True,
            "derived": True,
            "owner": "SCO",
            "beneficiary": "FRA",
            "selected_cede_count": 2,
            "owned_count": 2,
            "reason": "LIVE_NATIVE_FULL_ANNEX_PROVEN",
        }
        self.assertIsNone(ObserverSession._inbound_peace_context_fields(
            self._inbound_full_annex_context(proof), "ENG", "FRA"))
        self.assertIsNotNone(ObserverSession._inbound_peace_context_fields(
            self._inbound_full_annex_context(), "ENG", "FRA"))

    def test_all_five_country_effects_require_real_before_after_contract(self) -> None:
        effects = _accepted_effects()
        self.assertTrue(ObserverSession._valid_native_peace_effects(
            effects, "demand", -1, [], None, "FRA", "ENG", DATE_RAW,
            True,
            release_nation_country="TYR", release_nation_source="ENG",
            release_nation_requested=True,
            force_vassalization_country="AUV",
            force_vassalization_beneficiary="FRA",
            force_vassalization_requested=True,
            form_personal_union_country="PRO",
            form_personal_union_beneficiary="FRA",
            form_personal_union_requested=True,
            grant_independence_country="FRA",
            grant_independence_overlord="ENG",
            grant_independence_requested=True,
            full_annexation_country="ULS",
            full_annexation_beneficiary="FRA",
            full_annexation_requested=True,
            settled=True))

    def test_tampered_country_effect_is_rejected_even_with_verified_flag(self) -> None:
        effects = _accepted_effects()
        effects["country_terms"]["full_annexation"]["province_rows"][0][
            "owner_after"] = "SCO"
        self.assertFalse(ObserverSession._valid_native_peace_effects(
            effects, "demand", -1, [], None, "FRA", "ENG", DATE_RAW,
            True,
            full_annexation_country="ULS",
            full_annexation_beneficiary="FRA",
            full_annexation_requested=True,
            settled=True))

    def test_grant_requires_complete_global_overlord_scan(self) -> None:
        effects = _accepted_effects()
        effects["country_terms"]["grant_independence"][
            "overlord_scan_complete_after"] = False
        self.assertFalse(ObserverSession._valid_native_peace_effects(
            effects, "demand", -1, [], None, "FRA", "ENG", DATE_RAW,
            True,
            grant_independence_country="FRA",
            grant_independence_overlord="ENG",
            grant_independence_requested=True,
            settled=True))

    def test_rejected_country_effect_may_be_unchanged_but_verified_true_is_invalid(self) -> None:
        effects = _accepted_effects()
        release = effects["country_terms"]["release_nation"]
        release["owned_count_after"] = release["owned_count_before"]
        release["source_owned_count_after"] = release["source_owned_count_before"]
        row = release["province_rows"][0]
        row["owner_after"] = row["owner_before"]
        row["controller_after"] = row["controller_before"]
        release["unchanged"] = True
        release["verified"] = False
        effects["country_terms"] = {
            "release_nation": release,
            "force_vassalization": None,
            "form_personal_union": None,
            "grant_independence": None,
            "full_annexation": None,
        }
        self.assertTrue(ObserverSession._valid_native_peace_effects(
            effects, "demand", -1, [], None, "FRA", "ENG", DATE_RAW,
            False,
            release_nation_country="TYR", release_nation_source="ENG",
            release_nation_requested=True,
            settled=False))
        bad = copy.deepcopy(effects)
        bad["country_terms"]["release_nation"]["verified"] = True
        self.assertFalse(ObserverSession._valid_native_peace_effects(
            bad, "demand", -1, [], None, "FRA", "ENG", DATE_RAW,
            False,
            release_nation_country="TYR", release_nation_source="ENG",
            release_nation_requested=True,
            settled=False))

    def test_public_projection_keeps_country_terms_and_removes_private_shape(self) -> None:
        public = ObserverSession._public_native_peace_effects(_accepted_effects())
        self.assertEqual(set(public["country_terms"]), {
            "release_nation", "force_vassalization", "form_personal_union",
            "grant_independence", "full_annexation"})
        self.assertEqual(
            public["country_terms"]["release_nation"]["source"], "ENG")
        self.assertEqual(
            public["country_terms"]["grant_independence"]["overlord_count_after"], 0)
        self.assertNotIn("country_terms", public["country_terms"]["release_nation"][
            "province_rows"][0])


if __name__ == "__main__":
    unittest.main()
