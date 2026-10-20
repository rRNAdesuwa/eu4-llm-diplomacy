"""Synthetic selected-effect assertions; no game/process/request/ledger access."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from bridge.diplomacy_effect_profiles import SCHEMA, evaluate_profile, profile_catalog

SENTINEL = "0x2d2d2d"


def handle(tag, slot):
    return hex((1 << 56) | (slot << 32) | int.from_bytes(tag.encode("ascii"), "little"))


def case(action, actor="FRA", target="ORL"):
    slots = {"FRA": 122, "ORL": 126, "SAV": 210, "SCO": 189, "JOL": 374, "MAL": 385}
    actor_h, target_h = handle(actor, slots[actor]), handle(target, slots[target])
    before = {"identity": {"pid": 1234, "creation": "01dd5bf010accac6"}, "now_raw": 56461512,
              "world_epoch_proven": False,
              "pair": {"actor_tag": actor, "target_tag": target, "actor_handle": actor_h,
                       "target_handle": target_h, "actor_overlord_handle": SENTINEL,
                       "target_overlord_handle": actor_h, "dependency_present": True,
                       "dependency_type": "vassal", "annex_index_count": 0,
                       "annex_target_member": False, "annex_object_pointer": None,
                       "coalition_actor_handle": target_h},
              "actor": {"resources": {"treasury_milli": 10000, "manpower_milli": 20000, "sailors_milli": 30000}},
              "target": {"resources": {"treasury_milli": 9000, "manpower_milli": 10000, "sailors_milli": 11000}},
              "incoming": {"trust": 55, "favors": 10000},
              "target_war_prep": {"actor_handle": SENTINEL, "deadline": 56460000}}
    if action == "ask_for_march":
        before["pair"].update(actor_overlord_handle=target_h, target_overlord_handle=SENTINEL)
    if action == "cancel_annexation":
        before["pair"].update(annex_index_count=1, annex_target_member=True, annex_object_pointer="0x200000")
    if action == "revoke_march":
        before["pair"]["dependency_type"] = "march"
    if action == "release_soyurghal":
        before["pair"]["dependency_type"] = "soyurghal"
    if action == "dissolve_protectorate":
        before["pair"]["dependency_type"] = "trade_protectorate"
    receipt = {"command": {"action": action, "actor": actor, "target": target, "request_id": "synthetic-only"},
               "identity": dict(before["identity"], session="a"*32),
               "binding": {"actor_handle": int(actor_h, 16), "target_handle": int(target_h, 16)},
               "state": "dispatched", "native_result": {"status": 4, "submitted": True, "slot_consumed": True,
                   "ownership_closed": True, "owned_live": 0, "quarantined": 0, "adapter_fault": 0,
                   "submit_exception": 0, "known_cleanup_complete": False}}
    return before, copy.deepcopy(before), receipt


def observed_case(action):
    actor, target = ("ORL", "FRA") if action == "ask_for_march" else ("FRA", "SAV") if action == "leave_coalition" else ("FRA", "ORL")
    before, after, receipt = case(action, actor, target)
    if action == "annex_vassal":
        after["pair"].update(annex_index_count=1, annex_target_member=True, annex_object_pointer="0x210000")
    elif action == "cancel_annexation":
        after["pair"].update(annex_index_count=0, annex_target_member=False, annex_object_pointer=None)
    elif action == "leave_coalition":
        after["pair"]["coalition_actor_handle"] = SENTINEL
    elif action in ("designate_march", "ask_for_march"):
        after["pair"]["dependency_type"] = "march"
    elif action == "revoke_march":
        after["pair"]["dependency_type"] = "vassal"
    elif action in ("release_soyurghal", "dissolve_protectorate"):
        after["pair"].update(dependency_present=False, dependency_type=None, target_overlord_handle=SENTINEL)
    elif action == "trade_favors_for_trust":
        after["incoming"].update(trust=60, favors=9000)
    elif action in ("trade_favors_for_gold", "trade_favors_for_men", "trade_favors_for_sailors"):
        field = {"trade_favors_for_gold": "treasury_milli", "trade_favors_for_men": "manpower_milli", "trade_favors_for_sailors": "sailors_milli"}[action]
        after["actor"]["resources"][field] += 1200
        after["target"]["resources"][field] -= 1200
        after["incoming"]["favors"] -= 1000
    elif action == "trade_favors_for_war_prep":
        after["target_war_prep"].update(actor_handle=after["pair"]["actor_handle"], deadline=56470000)
    return before, after, receipt


class EffectProfileTests(unittest.TestCase):
    def test_thirteen_selected_positive_effects_and_truthful_completion_stage(self):
        actions = [row["action"] for row in profile_catalog() if row["completion_stage"] != "diagnostic_only"]
        self.assertEqual(len(actions), 13)
        for action in actions:
            with self.subTest(action=action):
                result = evaluate_profile(action, *observed_case(action))
                self.assertEqual(result["status"], "observed")
                self.assertTrue(result["selected_effect_verified"])
                self.assertTrue(result["native_dispatch_verified"])
                self.assertFalse(result["AI_acceptance_verified"])
                self.assertFalse(result["annexation_finished"])
                self.assertFalse(result["world_epoch_proven"])
                self.assertFalse(result["exclusive_causality_proven"])
                self.assertEqual(result["completion_stage"], "in_progress" if action == "annex_vassal" else "selected_effect_observed")

    def test_dispatch_without_state_change_is_not_effect(self):
        for action in ("annex_vassal", "cancel_annexation", "ask_for_march", "leave_coalition", "trade_favors_for_gold"):
            with self.subTest(action=action):
                inputs = case(action, "ORL", "FRA") if action == "ask_for_march" else case(action)
                result = evaluate_profile(action, *inputs)
                self.assertEqual(result["status"], "not_observed")
                self.assertEqual(result["completion_stage"], "unverified")
                self.assertTrue(result["native_dispatch_verified"])
                self.assertFalse(result["selected_effect_verified"])

    def test_no_baseline_is_unknown_even_with_effect_looking_after(self):
        _, after, receipt = observed_case("annex_vassal")
        result = evaluate_profile("annex_vassal", None, after, receipt)
        self.assertEqual(result["status"], "unknown")
        self.assertIn("before.pair.annex_target_member", result["missing_fields"])

    def test_same_process_identity_and_exact_pair_are_required(self):
        for path, value in (("pid", 1235), ("creation", "01dd5bf010accac7")):
            before, after, receipt = observed_case("annex_vassal")
            after["identity"][path] = value
            self.assertEqual(evaluate_profile("annex_vassal", before, after, receipt)["status"], "unknown")
        before, after, receipt = observed_case("leave_coalition")
        after["pair"]["target_handle"] = handle("SAV", 211)
        self.assertEqual(evaluate_profile("leave_coalition", before, after, receipt)["status"], "unknown")

    def test_handle_tag_encoding_and_selector_cannot_be_assumed(self):
        before, after, receipt = observed_case("annex_vassal")
        bad_handle = handle("SAV", 126)
        before["pair"]["target_handle"] = after["pair"]["target_handle"] = bad_handle
        receipt["binding"]["target_handle"] = int(bad_handle, 16)
        result = evaluate_profile("annex_vassal", before, after, receipt)
        self.assertEqual(result["status"], "unknown")
        self.assertFalse(result["baseline_comparable"])

    def test_receipt_must_match_action_tags_handles_and_session_process(self):
        mutations = (lambda r: r["command"].update(action="cancel_annexation"),
                     lambda r: r["command"].update(target="SAV"),
                     lambda r: r["binding"].update(actor_handle=int(handle("SAV", 210), 16)),
                     lambda r: r["identity"].update(pid=999))
        for mutate in mutations:
            before, after, receipt = observed_case("annex_vassal")
            mutate(receipt)
            result = evaluate_profile("annex_vassal", before, after, receipt)
            self.assertEqual(result["status"], "unknown")
            self.assertFalse(result["native_dispatch_verified"])

    def test_rejected_unknown_or_unclosed_receipt_cannot_attribute_effect(self):
        for changed in ({"submitted": False, "status": 2}, {"owned_live": 1}, {"ownership_closed": False},
                        {"quarantined": 1}, {"adapter_fault": 5}, {"submit_exception": 7}, {"slot_consumed": False}):
            before, after, receipt = observed_case("annex_vassal")
            receipt["native_result"].update(changed)
            result = evaluate_profile("annex_vassal", before, after, receipt)
            self.assertEqual(result["status"], "unknown")
            self.assertFalse(result["native_dispatch_verified"])

    def test_transport_consumption_does_not_require_or_claim_local_destructors(self):
        result = evaluate_profile("annex_vassal", *observed_case("annex_vassal"))
        self.assertEqual(result["status"], "observed")
        self.assertIs(result["native_known_cleanup_complete"], False)
        self.assertTrue(any("local destructors" in line for line in result["limitations"]))

    def test_annex_requires_exact_member_and_nonnull_object_and_consistent_count(self):
        for changed in ({"annex_object_pointer": None}, {"annex_object_pointer": "0x0"},
                        {"annex_index_count": 0}, {"annex_target_member": False}):
            before, after, receipt = observed_case("annex_vassal")
            after["pair"].update(changed)
            self.assertEqual(evaluate_profile("annex_vassal", before, after, receipt)["status"], "not_observed")
        before, after, receipt = observed_case("annex_vassal")
        del after["pair"]["annex_object_pointer"]
        self.assertEqual(evaluate_profile("annex_vassal", before, after, receipt)["status"], "unknown")

    def test_annex_membership_is_pair_specific_not_an_all_targets_count_delta(self):
        before, after, receipt = observed_case("annex_vassal")
        before["pair"]["annex_index_count"] = after["pair"]["annex_index_count"] = 2
        result = evaluate_profile("annex_vassal", before, after, receipt)
        self.assertEqual(result["status"], "observed")
        self.assertFalse(result["exclusive_causality_proven"])

    def test_cancel_needs_a_real_observed_before_target_index(self):
        before, after, receipt = observed_case("cancel_annexation")
        before["pair"].update(annex_target_member=False, annex_object_pointer=None)
        self.assertEqual(evaluate_profile("cancel_annexation", before, after, receipt)["status"], "unknown")

    def test_ask_march_direction_is_subject_to_overlord(self):
        before, after, receipt = observed_case("ask_for_march")
        self.assertEqual(evaluate_profile("ask_for_march", before, after, receipt)["status"], "observed")
        before["pair"]["actor_overlord_handle"] = after["pair"]["actor_overlord_handle"] = SENTINEL
        self.assertEqual(evaluate_profile("ask_for_march", before, after, receipt)["status"], "unknown")

    def test_type_change_still_requires_same_overlord(self):
        before, after, receipt = observed_case("designate_march")
        after["pair"]["target_overlord_handle"] = handle("SAV", 210)
        self.assertEqual(evaluate_profile("designate_march", before, after, receipt)["status"], "not_observed")

    def test_release_requires_both_index_absence_and_overlord_sentinel(self):
        for action in ("release_soyurghal", "dissolve_protectorate"):
            before, after, receipt = observed_case(action)
            after["pair"]["target_overlord_handle"] = before["pair"]["actor_handle"]
            self.assertEqual(evaluate_profile(action, before, after, receipt)["status"], "not_observed")
            del after["pair"]["dependency_present"]
            self.assertEqual(evaluate_profile(action, before, after, receipt)["status"], "unknown")

    def test_clear_type_null_is_distinct_from_missing_type(self):
        before, after, receipt = observed_case("release_soyurghal")
        self.assertEqual(evaluate_profile("release_soyurghal", before, after, receipt)["status"], "observed")
        del after["pair"]["dependency_type"]
        self.assertEqual(evaluate_profile("release_soyurghal", before, after, receipt)["status"], "unknown")

    def test_leave_coalition_needs_matching_before_target_and_exact_native_sentinel(self):
        before, after, receipt = observed_case("leave_coalition")
        after["pair"]["coalition_actor_handle"] = "0x0"
        self.assertEqual(evaluate_profile("leave_coalition", before, after, receipt)["status"], "not_observed")
        before["pair"]["coalition_actor_handle"] = SENTINEL
        self.assertEqual(evaluate_profile("leave_coalition", before, after, receipt)["status"], "unknown")

    def test_resource_transfers_require_conservation_and_positive_actor_delta(self):
        for action, field in (("trade_favors_for_gold", "treasury_milli"), ("trade_favors_for_men", "manpower_milli"),
                              ("trade_favors_for_sailors", "sailors_milli")):
            before, after, receipt = observed_case(action)
            after["target"]["resources"][field] += 1
            self.assertEqual(evaluate_profile(action, before, after, receipt)["status"], "not_observed")
            after["actor"]["resources"][field] = before["actor"]["resources"][field]-1
            after["target"]["resources"][field] = before["target"]["resources"][field]+1
            self.assertEqual(evaluate_profile(action, before, after, receipt)["status"], "not_observed")

    def test_monthly_or_daily_change_cannot_be_attributed_to_instant_action(self):
        for action in ("trade_favors_for_gold", "trade_favors_for_men", "trade_favors_for_sailors",
                       "trade_favors_for_trust", "trade_favors_for_war_prep"):
            before, after, receipt = observed_case(action)
            after["now_raw"] += 24
            result = evaluate_profile(action, before, after, receipt)
            self.assertEqual(result["status"], "unknown")
            self.assertFalse(result["baseline_comparable"])

    def test_structural_effect_can_be_matched_across_dates_with_explicit_causality_limit(self):
        before, after, receipt = observed_case("annex_vassal")
        after["now_raw"] += 24
        result = evaluate_profile("annex_vassal", before, after, receipt)
        self.assertEqual(result["status"], "observed")
        self.assertFalse(result["exclusive_causality_proven"])

    def test_optional_favor_observation_does_not_invent_fee_or_block_primary_transfer(self):
        before, after, receipt = observed_case("trade_favors_for_gold")
        del before["incoming"]["favors"]
        del after["incoming"]["favors"]
        result = evaluate_profile("trade_favors_for_gold", before, after, receipt)
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["diagnostics"][0]["state"], "unknown")
        self.assertFalse(result["diagnostics"][0]["per_request_cost_attribution_proven"])

    def test_boolean_float_or_out_of_native_range_values_are_unknown(self):
        for invalid in (True, 1200.0, 2**40):
            before, after, receipt = observed_case("trade_favors_for_gold")
            after["actor"]["resources"]["treasury_milli"] = invalid
            result = evaluate_profile("trade_favors_for_gold", before, after, receipt)
            self.assertEqual(result["status"], "unknown")
            self.assertIn("after.actor.resources.treasury_milli", result["invalid_fields"])
        before, after, receipt = observed_case("annex_vassal")
        receipt["native_result"]["slot_consumed"] = 1
        self.assertEqual(evaluate_profile("annex_vassal", before, after, receipt)["status"], "unknown")

    def test_trust_cap_and_no_change_are_handled(self):
        before, after, receipt = observed_case("trade_favors_for_trust")
        before["incoming"]["trust"], after["incoming"]["trust"] = 98, 100
        self.assertEqual(evaluate_profile("trade_favors_for_trust", before, after, receipt)["status"], "observed")
        before["incoming"]["trust"] = 100
        self.assertEqual(evaluate_profile("trade_favors_for_trust", before, after, receipt)["status"], "not_observed")

    def test_war_prep_requires_correct_actor_and_new_future_deadline(self):
        before, after, receipt = observed_case("trade_favors_for_war_prep")
        after["target_war_prep"]["deadline"] = after["now_raw"]
        self.assertEqual(evaluate_profile("trade_favors_for_war_prep", before, after, receipt)["status"], "not_observed")
        after["target_war_prep"].update(deadline=56470000, actor_handle=handle("SAV", 210))
        self.assertEqual(evaluate_profile("trade_favors_for_war_prep", before, after, receipt)["status"], "not_observed")

    def test_knowledge_counts_and_unverified_active_flags_never_prove_pair_effect(self):
        for action, actor, target in (("knowledge_sharing", "FRA", "JOL"), ("ask_knowledge_sharing", "MAL", "FRA")):
            before, after, receipt = case(action, actor, target)
            before["knowledge"] = {"provider_count": 0, "recipient_count": 0, "active_for_pair": False}
            after["knowledge"] = {"provider_count": 1, "recipient_count": 1, "active_for_pair": True,
                                  "typed_pair_claimed_verified": True}
            result = evaluate_profile(action, before, after, receipt)
            self.assertEqual(result["status"], "unknown")
            self.assertEqual(result["completion_stage"], "diagnostic_only")
            self.assertTrue(result["native_dispatch_verified"])
            self.assertFalse(result["selected_effect_verified"])

    def test_unsupported_action_and_nonstring_are_explicit(self):
        for action in ("declare_war", "unknown_action", None, {"action": "annex_vassal"}):
            result = evaluate_profile(action, {}, {}, {})
            self.assertEqual(result["schema"], SCHEMA)
            self.assertEqual(result["status"], "unsupported")
            self.assertFalse(result["supported"])

    def test_evaluation_is_pure_and_json_safe_for_64bit_handles(self):
        inputs = observed_case("release_soyurghal")
        snapshot = copy.deepcopy(inputs)
        with patch("builtins.open", side_effect=AssertionError("Evaluator must perform no file I/O")):
            result = evaluate_profile("release_soyurghal", *inputs)
            catalog = profile_catalog()
        self.assertEqual(inputs, snapshot)
        self.assertEqual(result["changes"]["target_overlord_handle"]["before"], inputs[0]["pair"]["actor_handle"])
        json.dumps(result)
        self.assertEqual(len(catalog), 15)

    def test_catalog_has_contract_provenance_and_is_defensively_copied(self):
        catalog = profile_catalog()
        first = catalog[0]
        self.assertIn("pair.annex_target_member", first["required_fields"])
        self.assertIn("native_result.ownership_closed", first["required_native_receipt_fields"])
        self.assertEqual(first["completion_stage"], "in_progress")
        path = next(iter(first["source_pins"]))
        first["source_pins"][path]["sha256"] = "0"*64
        first["required_fields"].clear()
        self.assertNotEqual(profile_catalog()[0]["source_pins"][path]["sha256"], "0"*64)
        self.assertTrue(profile_catalog()[0]["required_fields"])

    def test_fixed_profile_pins_match_the_frozen_evidence_files(self):
        root = Path(__file__).resolve().parents[2]
        pins = {name: pin for row in profile_catalog() for name, pin in row["source_pins"].items()}
        self.assertEqual(len(pins), 8)
        for name, pin in pins.items():
            with self.subTest(path=name):
                raw = (root/name).read_bytes()
                self.assertEqual(len(raw), pin["bytes"])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), pin["sha256"])


if __name__ == "__main__":
    unittest.main()
