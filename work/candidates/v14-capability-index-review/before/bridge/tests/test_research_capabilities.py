"""Offline discovery contract tests; no native process, mailbox, or API ledger."""
import contextlib
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bridge import diplomacy_research_capabilities as cap
from tools import request_diplomacy_lab as cli
from tools import request_diplomacy_lab_v7 as cli_v7
from tools import request_diplomacy_lab_v8 as cli_v8
from tools import request_diplomacy_lab_v9 as cli_v9


class ResearchCapabilitiesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.catalog = self.root / "catalog.json"
        self.index = self.root / "history.json"
        actions = [{"action_id": name, "name_zh": name, "category": "synthetic",
                    "parameters": {"type":"object","properties":{},"additionalProperties":False},
                    "parameter_status":"specified", "native_mapping":{"exe_sha256":cap.LOCAL_SHA256,
                        "evidence_level":"static_only", "runtime_verified":False,"variants":[{"name":name}]}}
                   for name in sorted(cap.DISCOVERY_CATALOG_ACTIONS)]
        actions.append({"action_id":"unknown_diplomacy", "parameters":{}, "parameter_status":"unresolved"})
        self.catalog.write_text(json.dumps({"schema_version":1,"game_build":{"exe_sha256":cap.LOCAL_SHA256},"actions":actions}), encoding="utf-8")
        self.data = json.loads(cap.DEFAULT_EVIDENCE.read_text(encoding="utf-8"))
        self.original_artifacts = deepcopy(self.data["artifacts"])
        artifact = b"Reviewed fixture bytes only; never native proof.\n"
        (self.root / "fixture.txt").write_bytes(artifact)
        immutable = set(self.data["historical_preflights"][0]["evidence"]) | set(self.data["observations"][-1]["evidence"])
        for number,key in enumerate(self.data["artifacts"]):
            path = f"preflight-{number}.txt" if key in immutable else "fixture.txt"
            if key in immutable:
                (self.root/path).write_bytes(artifact)
            self.data["artifacts"][key] = {"path":path,"size_bytes":len(artifact),
                                            "sha256":hashlib.sha256(artifact).hexdigest(),"read_mode":"whole"}
        record = self.data["historical_preflights"][0]
        self.production_review_pin = cap.V12_PREFLIGHT_REVIEW_SHA256
        # Test-only fixed synthetic review. Later write() must never repin edits.
        synthetic_pin = hashlib.sha256(cap.canonical({"record": record,
            "artifacts": {key:self.data["artifacts"][key] for key in record["evidence"]}}).encode("utf-8")).hexdigest()
        self.enterContext(patch.object(cap,"V12_PREFLIGHT_REVIEW_SHA256",synthetic_pin))
        effect_rows = [r for r in self.data["observations"] if r["scope"].get("version") == "v12"]
        self.production_effect_pin = cap.V12_EFFECT_REVIEW_SHA256
        synthetic_effect_pin = hashlib.sha256(cap.canonical({"observations": effect_rows,
            "artifacts": {key:self.data["artifacts"][key] for key in effect_rows[0]["evidence"]}}).encode("utf-8")).hexdigest()
        self.enterContext(patch.object(cap,"V12_EFFECT_REVIEW_SHA256",synthetic_effect_pin))
        self.write()

    def write(self):
        self.index.write_text(json.dumps(self.data),encoding="utf-8")

    def describe(self, **kwargs):
        return cap.capabilities(root=self.root,catalog_path=self.catalog,evidence_path=self.index,**kwargs)

    def test_four_layers_are_distinct_and_production_remains_unsupported(self):
        result = self.describe()
        self.assertEqual(result["summary"]["catalogued_actions"],38)
        self.assertEqual(result["summary"]["laboratory_entrypoints"],36)
        self.assertEqual(result["summary"]["production_executable_actions"],0)
        self.assertIsNone(result["current_session_ready"])
        self.assertFalse(result["live_process_inspected"])
        self.assertTrue(all(a["production"]["status"]=="unsupported" and a["production"]["ready"] is False for a in result["actions"]))
        unknown = next(a for a in result["actions"] if a["action_id"]=="unknown_diplomacy")
        self.assertEqual(unknown["static"]["status"],"catalog_only")
        self.assertFalse(unknown["laboratory"]["entrypoint_available"])

    def test_mapping_never_implies_effect_and_cancel_does_not_borrow_positive_evidence(self):
        cancel = self.describe(action_id="cancel_vassalization")["actions"][0]
        self.assertTrue(cancel["static"]["mapped"])
        self.assertTrue(cancel["laboratory"]["entrypoint_available"])
        self.assertTrue(cancel["observed_effects"]["available"])
        self.assertTrue(cancel["observed_effects"]["experiments"][0]["claims"]["native_legality_checked"])
        self.assertFalse(cancel["observed_effects"]["experiments"][0]["claims"]["native_dispatch_returned"])
        self.assertIsNone(cancel["laboratory"]["runtime_ready"])
        guarantee = self.describe(action_id="guarantee")["actions"][0]
        self.assertTrue(guarantee["observed_effects"]["available"])
        self.assertEqual(guarantee["observed_effects"]["experiments"][0]["scope"]["target"],"POR")

    def test_subject_abi_mapping_counts_separately_without_lab_enablement(self):
        catalog=json.loads(self.catalog.read_text(encoding="utf-8"))
        catalog["actions"][-1]["native_subject_mapping"]={"exe_sha256":cap.LOCAL_SHA256,"evidence_level":"static_only",
            "runtime_verified":False,"interaction":{"name":"fixture_subject"},"command":{"token_id":12760}}
        self.catalog.write_text(json.dumps(catalog),encoding="utf-8")
        result=self.describe()
        self.assertEqual(result["summary"]["ordinary_static_mapped_actions"],37)
        self.assertEqual(result["summary"]["subject_static_mapped_actions"],1)
        self.assertEqual(result["summary"]["static_mapped_actions"],38)
        subject=result["actions"][-1]
        self.assertTrue(subject["static"]["subject_mapped"])
        self.assertFalse(subject["laboratory"]["entrypoint_available"])
        self.assertFalse(subject["production"]["ready"])

    def test_special_mapping_is_separate_and_union_does_not_double_count(self):
        catalog=json.loads(self.catalog.read_text(encoding="utf-8"))
        catalog["actions"][0]["native_special_mapping"]={"exe_sha256":cap.LOCAL_SHA256,"evidence_level":"static_only",
            "command":{"name":"fixture_special"},"source_report":{"path":"synthetic.json","sha256":"a"*64}}
        self.catalog.write_text(json.dumps(catalog),encoding="utf-8")
        result=self.describe()
        self.assertEqual(result["summary"]["special_static_mapped_actions"],1)
        self.assertEqual(result["summary"]["static_mapped_actions"],37)
        self.assertTrue(result["actions"][0]["static"]["special_mapped"])
        self.assertFalse(result["actions"][0]["production"]["ready"])

    def test_rejection_legality_and_persistence_are_not_conflated(self):
        marriage = self.describe(action_id="royal_marriage")["actions"][0]["observed_effects"]
        self.assertTrue(marriage["available"])
        row = marriage["experiments"][0]
        self.assertTrue(row["claims"]["native_dispatch_returned"])
        self.assertTrue(row["claims"]["reply_rejection_correlated"])
        self.assertFalse(row["claims"]["ai_acceptance_verified"])
        vassal = self.describe(action_id="offer_vassalization")["actions"][0]["observed_effects"]["experiments"][0]
        self.assertFalse(vassal["findings"]["native_legality_allowed"])
        self.assertFalse(vassal["claims"]["native_dispatch_returned"])
        improve = self.describe(action_id="improve_relations")["actions"][0]["observed_effects"]["experiments"][0]
        self.assertTrue(improve["claims"]["saved_state_verified"] and improve["claims"]["reload_verified"])
        self.assertFalse(improve["claims"]["request_causality_verified"])

    def test_peace_components_count_independently_and_never_enable_laboratory(self):
        catalog=json.loads(self.catalog.read_text(encoding="utf-8"))
        catalog["actions"][-1]["native_peace_mapping"]={"exe_sha256":cap.LOCAL_SHA256,"evidence_level":"static_only",
            "component":{"name":"po_synthetic"},"source_report":{"path":"synthetic.json","sha256":"a"*64},
            "public_parameter_binding_verified":False,"execution_verified":False}
        self.catalog.write_text(json.dumps(catalog),encoding="utf-8")
        result=self.describe()
        self.assertEqual(result["summary"]["peace_static_mapped_actions"],1)
        self.assertEqual(result["summary"]["static_mapped_actions"],38)
        row=result["actions"][-1]
        self.assertFalse(row["laboratory"]["entrypoint_available"])
        self.assertFalse(row["static"]["execution_proven"])
        self.assertFalse(row["production"]["ready"])

    def test_v7_saved_reload_consistency_does_not_claim_request_causality_or_loaded_path(self):
        for action in ("royal_marriage","offer_vassalization"):
            row=next(r for r in self.describe(action_id=action)["actions"][0]["observed_effects"]["experiments"]
                     if r["scope"]["version"]=="v7")
            self.assertTrue(row["claims"]["reply_acceptance_correlated"])
            self.assertTrue(row["claims"]["observed_state_change"])
            self.assertTrue(row["findings"]["serialized_state_observed"])
            self.assertEqual(row["scope"]["target"],"NAV")
            self.assertTrue(row["scope"]["test_fixture_active"])
            self.assertFalse(row["claims"]["ai_acceptance_verified"])
            self.assertFalse(row["claims"]["request_causality_verified"])
            self.assertTrue(row["claims"]["saved_state_verified"])
            self.assertTrue(row["claims"]["reload_verified"])
            self.assertTrue(row["findings"]["saved_reload_state_consistent"])
            self.assertFalse(row["findings"]["exact_loaded_file_path_verified"])
            self.assertFalse(row["findings"]["whole_world_unchanged_verified"])
            self.assertFalse(row["generalized_to_other_pairs"])

    def test_missing_reload_review_withholds_persistence_instead_of_using_submit_return(self):
        self.data["artifacts"]["v7-positive-save-reload-review"]["path"]="missing-reload-review.json"
        self.write()
        row=next(r for r in self.describe(action_id="royal_marriage")["actions"][0]["observed_effects"]["experiments"]
                 if r["scope"]["version"]=="v7")
        self.assertFalse(row["claims"]["reload_verified"])
        self.assertFalse(row["claims"]["native_dispatch_returned"])
        self.assertEqual(row["findings"],{})
        self.assertTrue(row["recorded_claims"]["reload_verified"])

    def test_v6_closeout_and_v7_cancellation_have_their_own_evidence(self):
        guarantee=self.describe(action_id="revoke_guarantee")["actions"][0]["observed_effects"]["experiments"][0]
        marriage=self.describe(action_id="break_marriage")["actions"][0]["observed_effects"]["experiments"][0]
        for row,version,sequence in ((guarantee,"v6",65),(marriage,"v7",10)):
            self.assertEqual((row["scope"]["version"],row["scope"]["sequence"]),(version,sequence))
            self.assertTrue(row["claims"]["observed_state_change"])
            self.assertEqual(row["findings"]["transition"],"removed_active_state")

    def test_missing_v7_evidence_withholds_only_that_profile_and_observation(self):
        self.data["artifacts"]["v7-build"]["path"]="missing-v7-build.json"
        self.write()
        row=self.describe(action_id="royal_marriage")["actions"][0]
        v6,v7,v8,v9,v10,v12=row["laboratory"]["profiles"]
        self.assertTrue(v6["historical_preflight_evidence_available"])
        self.assertFalse(v7["historical_preflight_evidence_available"])
        self.assertTrue(v8["historical_preflight_evidence_available"])
        self.assertTrue(v9["historical_preflight_evidence_available"])
        self.assertEqual(v6["parameters"]["target_tags"],["FRA","ENG","POR"])
        self.assertIn("NAV",v7["parameters"]["target_tags"])
        self.assertFalse(row["observed_effects"]["available"])
        histories=row["observed_effects"]["experiments"]
        self.assertTrue(next(r for r in histories if r["scope"]["version"]=="v6")["claims"]["reply_rejection_correlated"])
        self.assertFalse(any(next(r for r in histories if r["scope"]["version"]=="v7")["claims"].values()))

    def test_missing_or_modified_evidence_withholds_claims(self):
        (self.root/"fixture.txt").write_bytes(b"different content")
        result = self.describe(action_id="improve_relations")
        row = result["actions"][0]
        self.assertFalse(row["observed_effects"]["available"])
        experiment = row["observed_effects"]["experiments"][0]
        self.assertFalse(any(experiment["claims"].values()))
        self.assertEqual(experiment["evidence_status"],"unavailable_or_changed")
        self.assertTrue(experiment["recorded_claims"]["reload_verified"])
        self.assertFalse(row["laboratory"]["historical_preflight_evidence_available"])

    def test_v8_saved_cancellation_is_independent_from_reload_and_fixture_pool(self):
        result=self.describe(action_id="break_marriage")
        row=next(r for r in result["actions"][0]["observed_effects"]["experiments"] if r["scope"]["version"]=="v8")
        self.assertEqual((row["scope"]["pid"],row["scope"]["sequence"]),(39216,5))
        self.assertTrue(row["claims"]["native_dispatch_returned"])
        self.assertTrue(row["claims"]["observed_state_change"])
        self.assertTrue(row["claims"]["saved_state_verified"])
        self.assertFalse(row["claims"]["reload_verified"])
        self.assertFalse(row["claims"]["request_causality_verified"])
        self.assertEqual(row["findings"]["pair_submits_in_reviewed_session"],1)
        self.assertEqual(row["findings"]["observed_diplomat_count_after_off"],103)
        self.assertFalse(row["findings"]["fixture_off_diplomat_pool_shrink_verified"])
        self.assertEqual(result["summary"]["actions_with_reviewed_state_effects"],20)
        self.assertEqual(result["reviewed_history_versions"],["v5","v6","v7","v8","v9","v10","v12"])
        self.assertEqual(result["runtime_unreviewed_versions"],["v11","v13"])

    def test_v8_reload_is_separate_supplement_and_missing_proof_preserves_old_snapshot(self):
        rows=self.describe(action_id="break_marriage")["actions"][0]["observed_effects"]["experiments"]
        saved=next(r for r in rows if r["experiment_id"]=="v8-break-marriage-fra-nav-saved")
        reload=next(r for r in rows if r["experiment_id"]=="v8-break-marriage-fra-nav-reloaded")
        self.assertFalse(saved["claims"]["reload_verified"])
        self.assertTrue(reload["claims"]["reload_verified"])
        self.assertEqual(reload["scope"]["reload_pid"],20276)
        self.assertTrue(reload["findings"]["original_summary_unchanged"])
        self.assertFalse(reload["findings"]["exact_loaded_file_path_verified"])
        self.data["artifacts"]["v8-reload-review"]["path"]="missing-v8-reload.json"
        self.write()
        rows=self.describe(action_id="break_marriage")["actions"][0]["observed_effects"]["experiments"]
        self.assertFalse(any(next(r for r in rows if r["experiment_id"]==reload["experiment_id"])["claims"].values()))
        self.assertTrue(next(r for r in rows if r["experiment_id"]==saved["experiment_id"])["claims"]["saved_state_verified"])

    def test_v9_cancel_owns_saved_reload_proof_and_final_date_without_generalizing(self):
        result=self.describe(action_id="cancel_vassalization")
        rows=result["actions"][0]["observed_effects"]["experiments"]
        old,new=rows
        self.assertFalse(old["claims"]["native_dispatch_returned"])
        self.assertFalse(old["claims"]["observed_state_change"])
        self.assertEqual((new["scope"]["pid"],new["scope"]["sequence"],new["scope"]["reload_pid"]),(60888,3,54232))
        self.assertTrue(new["claims"]["saved_state_verified"] and new["claims"]["reload_verified"])
        self.assertTrue(new["findings"]["nav_independent_after"] and new["findings"]["bilateral_truce_after"])
        self.assertEqual(new["findings"]["final_raw_date"],56457192)
        self.assertFalse(new["scope"]["world_generation_verified"])
        self.assertFalse(new["findings"]["strict_live_single_player_verified"])
        self.assertFalse(new["claims"]["request_causality_verified"])
        self.assertFalse(new["generalized_to_other_pairs"])
        self.assertFalse(new["production_ready"])

    def test_missing_v9_proof_removes_tenth_effect_and_only_v9_preflight(self):
        self.data["artifacts"]["v9-summary"]["path"]="missing-v9-summary.json"
        self.write()
        result=self.describe(action_id="cancel_vassalization")
        self.assertEqual(result["summary"]["actions_with_reviewed_state_effects"],19)
        row=result["actions"][0]
        self.assertFalse(row["observed_effects"]["available"])
        self.assertFalse(any(row["observed_effects"]["experiments"][-1]["claims"].values()))
        profiles={p["version"]:p for p in row["laboratory"]["profiles"]}
        self.assertFalse(profiles["v9"]["historical_preflight_evidence_available"])
        self.assertTrue(all(profiles[v]["historical_preflight_evidence_available"] for v in ("v6","v7","v8")))

    def test_artifact_count_budget_remains_bounded(self):
        sample=next(iter(self.data["artifacts"].values()))
        self.data["artifacts"]={str(i):sample for i in range(cap.MAX_ARTIFACTS+1)}
        self.write()
        with self.assertRaisesRegex(ValueError,"Too many evidence artifacts"):
            self.describe()

    def test_v10_four_positive_effects_are_unsaved_and_keep_aborted_session_boundary(self):
        for action in ("offer_alliance","ask_military_access","offer_military_access","ask_fleet_basing_rights"):
            row=self.describe(action_id=action)["actions"][0]
            self.assertEqual([p["version"] for p in row["laboratory"]["profiles"]],["v10", "v12"])
            observation=row["observed_effects"]["experiments"][0]
            self.assertTrue(observation["claims"]["observed_state_change"])
            self.assertFalse(observation["claims"]["saved_state_verified"])
            self.assertFalse(observation["claims"]["reload_verified"])
            self.assertTrue(observation["findings"]["session_aborted"])
            self.assertFalse(observation["findings"]["specific_failure_cause_verified"])
            self.assertFalse(observation["findings"]["all_planned_fourteen_effects_verified"])
            self.assertEqual(observation["findings"]["unclaimed_published_sequence"],13)
            self.assertIsNone(row["laboratory"]["runtime_ready"])
        for action in ("dissolve_alliance","cancel_military_access","revoke_military_access","cancel_fleet_basing_rights"):
            row=self.describe(action_id=action)["actions"][0]
            self.assertTrue(row["laboratory"]["entrypoint_available"])
            self.assertFalse(row["observed_effects"]["available"])
            self.assertEqual(row["observed_effects"]["experiments"],[])

    def test_missing_v10_summary_does_not_promote_candidate_or_borrow_prior_effects(self):
        self.data["artifacts"]["v10-summary"]["path"]="missing-v10.json"
        self.write()
        result=self.describe()
        self.assertEqual(result["summary"]["actions_with_reviewed_state_effects"],16)
        row=next(r for r in result["actions"] if r["action_id"]=="offer_alliance")
        self.assertFalse(row["observed_effects"]["available"])
        self.assertFalse(row["laboratory"]["historical_preflight_evidence_available"])
        self.assertTrue(row["observed_effects"]["experiments"][0]["recorded_claims"]["observed_state_change"])

    def test_missing_v8_proof_withholds_only_v8_claims_and_profile(self):
        self.data["artifacts"]["v8-summary"]["path"]="missing-v8-summary.json"
        self.write()
        result=self.describe(action_id="break_marriage")["actions"][0]
        rows=result["observed_effects"]["experiments"]
        v8=next(r for r in rows if r["scope"]["version"]=="v8")
        self.assertFalse(any(v8["claims"].values()))
        self.assertEqual(v8["findings"],{})
        self.assertTrue(v8["recorded_claims"]["saved_state_verified"])
        self.assertTrue(next(r for r in rows if r["scope"]["version"]=="v7")["claims"]["observed_state_change"])
        profiles={p["version"]:p for p in result["laboratory"]["profiles"]}
        self.assertFalse(profiles["v8"]["historical_preflight_evidence_available"])
        self.assertTrue(profiles["v7"]["historical_preflight_evidence_available"])

    def test_static_sp_navigation_never_promotes_production_or_research_readiness(self):
        result=self.describe()
        self.assertTrue(all(r["evidence_available"] for r in result["research_references"]))
        self.assertTrue(all(r["production_ready"] is False and r["live_readiness"] is None for r in result["research_references"]))
        self.assertFalse(result["catalog_review"]["matches_current_catalog"])
        self.data["artifacts"]["strict-sp-context-report"]["path"]="missing-sp.json"
        self.write()
        result=self.describe()
        sp=next(r for r in result["research_references"] if r["reference_id"]=="strict-single-player-static-research")
        self.assertFalse(sp["evidence_available"])
        self.assertEqual(result["summary"]["actions_with_reviewed_state_effects"],20)
        self.assertEqual(result["summary"]["production_executable_actions"],0)

    def test_prefix_snapshot_tolerates_only_appends_not_changed_reviewed_bytes(self):
        immutable = set(self.data["historical_preflights"][0]["evidence"]) | set(self.data["observations"][-1]["evidence"])
        for key, descriptor in self.data["artifacts"].items():
            if key not in immutable:
                descriptor["read_mode"]="prefix"
        self.write()
        with (self.root/"fixture.txt").open("ab") as stream:
            stream.write(b"Later unreviewed events, never automatically promote.\n")
        self.assertTrue(self.describe(action_id="improve_relations")["actions"][0]["observed_effects"]["available"])
        with (self.root/"fixture.txt").open("r+b") as stream:
            stream.write(b"X")
        self.assertFalse(self.describe(action_id="improve_relations")["actions"][0]["observed_effects"]["available"])

    def test_v12_preflight_is_36_protocol_ids_but_not_effect_or_live_authorization(self):
        result = self.describe(action_id="form_coalition")
        proof = result["historical_preflights"][0]
        self.assertTrue(proof["historical_preflight_passed"])
        self.assertEqual(proof["phase_cases"], {"lifecycle":20, "preview":72, "command":72})
        self.assertEqual(len(proof["action_ids"]),36)
        self.assertEqual(proof["scope"]["targets"],["ENG","POR"])
        self.assertFalse(proof["diplomatic_submission_verified"])
        self.assertFalse(proof["observed_state_change"])
        self.assertFalse(proof["native_legality_allowed_for_all_cases"])
        self.assertFalse(proof["strict_single_player_verified"])
        self.assertFalse(proof["world_epoch_verified"])
        self.assertIsNone(proof["live_readiness"])
        row = result["actions"][0]
        self.assertFalse(row["observed_effects"]["available"])
        self.assertEqual([p["version"] for p in row["laboratory"]["profiles"]],["v12"])
        self.assertEqual(result["summary"]["actions_with_reviewed_state_effects"],20)
        self.assertEqual(result["summary"]["production_executable_actions"],0)

    def test_preflight_aliases_navigate_existing_catalog_roles_without_creating_actions(self):
        trade = self.describe(action_id="request_trade_power")
        self.assertEqual([r["action_id"] for r in trade["actions"]],["transfer_trade_power"])
        cancel = self.describe(action_id="cancel_independence_support")
        self.assertEqual({r["action_id"] for r in cancel["actions"]},
            {"cancel_requested_independence_support","cancel_offered_independence_support"})
        for row in cancel["actions"]:
            p = row["laboratory"]["profiles"][0]
            self.assertEqual(p["research_action_ids"],["cancel_independence_support"])
            self.assertFalse(p["alias_binding_is_role_coverage_proof"])
            self.assertFalse(row["observed_effects"]["available"])

    def test_missing_v12_preflight_artifact_withholds_preflight_and_dependent_final_effects(self):
        key = self.data["historical_preflights"][0]["evidence"][0]
        (self.root/self.data["artifacts"][key]["path"]).unlink()
        result = self.describe(action_id="warn")
        proof = result["historical_preflights"][0]
        self.assertFalse(proof["historical_preflight_passed"])
        self.assertTrue(proof["recorded_historical_preflight_passed"])
        self.assertFalse(result["actions"][0]["laboratory"]["historical_preflight_evidence_available"])
        self.assertEqual(result["summary"]["actions_with_reviewed_state_effects"],14)

    def test_v12_preflight_rejects_scope_inflation_or_mutable_evidence(self):
        original = deepcopy(self.data)
        edits = [lambda r:r.update(version="v11"),lambda r:r.update(purpose="restricted_pair_lab_1375_v11"),
            lambda r:r["scope"].update(diplomatic_submit_count=1),lambda r:r["scope"].update(request_count=False),
            lambda r:r["scope"].update(targets=["ENG","POR","NAV"]),lambda r:r["phase_cases"].update(lifecycle=True),
            lambda r:r["action_ids"].append("arbitrary_native_call"),lambda r:r["catalog_bindings"].update(warn=["unknown_diplomacy"])]
        for edit in edits:
            self.data = deepcopy(original)
            edit(self.data["historical_preflights"][0]);self.write()
            with self.assertRaises(ValueError):self.describe()
        self.data = deepcopy(original)
        key = self.data["historical_preflights"][0]["evidence"][0]
        self.data["artifacts"][key]["read_mode"] = "prefix"
        self.write()
        with self.assertRaises(ValueError):self.describe()

    def test_review_pin_rejects_dropped_dependencies_changed_identity_and_rebound_files(self):
        original = deepcopy(self.data)
        edits = [lambda r:r["historical_preflights"][0].update(evidence=r["historical_preflights"][0]["evidence"][:1]),
            lambda r:r["historical_preflights"][0]["scope"].update(pid=17677),
            lambda r:r["historical_preflights"][0]["scope"].update(creation="01dd56989186135d"),
            lambda r:r["historical_preflights"][0]["scope"].update(prefix_sha256="a"*64),
            lambda r:r["artifacts"][r["historical_preflights"][0]["evidence"][0]].update(path="fixture.txt")]
        for edit in edits:
            self.data = deepcopy(original);edit(self.data);self.write()
            with self.assertRaisesRegex(ValueError,"independent review"):
                self.describe()

    def test_artifact_count_total_and_per_file_limits_remain_bounded(self):
        descriptor = deepcopy(next(iter(self.data["artifacts"].values())))
        for artifacts in ({str(n):descriptor for n in range(cap.MAX_ARTIFACTS+1)},
                          {str(n):{**descriptor,"size_bytes":cap.MAX_ARTIFACT} for n in range(5)},
                          {"oversize":{**descriptor,"size_bytes":cap.MAX_ARTIFACT+1}},
                          {"boolean-size":{**descriptor,"size_bytes":True}}):
            with self.assertRaises(ValueError):
                cap.verify_artifacts({"artifacts":artifacts},self.root)

    def test_v12_six_fixed_effects_keep_five_relation_reloads_and_same_day_gift_separate(self):
        result = self.describe()
        self.assertEqual(result["summary"]["actions_with_reviewed_state_effects"],20)
        reviewed = result["historical_effect_reviews"][0]
        self.assertEqual((reviewed["selected_effect_count"],reviewed["saved_reload_relation_count"]),(6,5))
        self.assertTrue(reviewed["session_stopped"])
        self.assertIsNone(reviewed["live_readiness"])
        for sequence, action in cap.V12_EFFECT_CASES.items():
            row=self.describe(action_id=action)["actions"][0]
            observation=row["observed_effects"]["experiments"][-1]
            self.assertEqual((observation["scope"]["sequence"],observation["scope"]["pid"]),(sequence,17676))
            self.assertTrue(observation["claims"]["native_dispatch_returned"])
            self.assertTrue(observation["claims"]["observed_state_change"])
            self.assertEqual(observation["claims"]["saved_state_verified"],action!="send_gift")
            self.assertEqual(observation["claims"]["reload_verified"],action!="send_gift")
            self.assertFalse(observation["claims"]["request_causality_verified"])
            self.assertFalse(observation["claims"]["ai_acceptance_verified"])
            self.assertFalse(observation["findings"]["strict_live_single_player_verified"])
            self.assertFalse(observation["findings"]["whole_world_unchanged_verified"])
            self.assertFalse(observation["findings"]["exact_loaded_file_path_verified"])
            self.assertFalse(row["production"]["ready"])
        gift=self.describe(action_id="send_gift")["actions"][0]["observed_effects"]["experiments"][0]
        self.assertEqual(gift["findings"]["treasury_delta_milli"],{"FRA":-25000,"POR":25000})
        self.assertEqual(gift["findings"]["favors_delta_milli"],{"FRA":0,"POR":0})
        self.assertEqual(gift["findings"]["same_raw_date"],56457408)
        self.assertIsNone(gift["findings"]["persistence"])

    def test_v12_trade_alias_exposes_one_effect_without_borrowing_cancel_support_roles(self):
        alias=self.describe(action_id="request_trade_power")["actions"]
        direct=self.describe(action_id="transfer_trade_power")["actions"]
        self.assertEqual(alias,direct)
        self.assertEqual(len(alias),1)
        self.assertEqual(alias[0]["observed_effects"]["experiments"][0]["action_id"],"request_trade_power")
        for row in self.describe(action_id="cancel_independence_support")["actions"]:
            self.assertFalse(row["observed_effects"]["available"])
            self.assertEqual(row["observed_effects"]["experiments"],[])

    def test_missing_final_summary_log_or_reload_withdraws_six_effects_but_not_preflight(self):
        names=("experiment-summary-17676.json","research-1375.jsonl","warn-positive-reload-13252.json")
        for name in names:
            key=next(k for k,d in self.original_artifacts.items() if Path(d["path"]).name==name
                and k.startswith("v12-final-"))
            path=self.root/self.data["artifacts"][key]["path"]
            raw=path.read_bytes();path.unlink()
            result=self.describe()
            self.assertEqual(result["summary"]["actions_with_reviewed_state_effects"],14)
            self.assertTrue(result["historical_preflights"][0]["historical_preflight_passed"])
            self.assertEqual(result["historical_effect_reviews"][0]["selected_effect_count"],0)
            new=[e for a in result["actions"] for e in a["observed_effects"]["experiments"] if e["scope"]["version"]=="v12"]
            self.assertEqual(len(new),6)
            self.assertTrue(all(e["recorded_claims"]["observed_state_change"] for e in new))
            self.assertTrue(all(not any(e["claims"].values()) and not e["findings"] for e in new))
            path.write_bytes(raw)

    def test_v12_final_review_pin_rejects_omitted_case_dependency_changed_scope_or_gift_persistence(self):
        original=deepcopy(self.data)
        edits=[lambda rows:rows[0]["evidence"].pop(),lambda rows:rows[0]["scope"].update(pid=17677),
            lambda rows:rows[0]["scope"].update(purpose="restricted_pair_lab_1375_v13"),
            lambda rows:rows[3]["claims"].update(reload_verified=True),
            lambda rows:rows[3]["findings"].update(fixed_amount_milli=26000)]
        for edit in edits:
            self.data=deepcopy(original)
            rows=[r for r in self.data["observations"] if r["scope"].get("version")=="v12"]
            edit(rows);self.write()
            with self.assertRaises(ValueError):self.describe()
        self.data=deepcopy(original);self.data["observations"].pop();self.write()
        with self.assertRaisesRegex(ValueError,"Unexpected finalized v12"):self.describe()

    def test_v12_final_whole_file_pins_reject_appending_and_unreviewed_version_promotion(self):
        key="v12-final-summary"
        path=self.root/self.data["artifacts"][key]["path"]
        with path.open("ab") as stream:stream.write(b"new result")
        self.assertEqual(self.describe()["summary"]["actions_with_reviewed_state_effects"],14)
        self.assertFalse(any(r["scope"]["version"]=="v13" for r in self.data["observations"]))
        self.assertNotIn("v13",self.describe()["reviewed_history_versions"])

    def test_real_final_review_retains_all_203_inputs_and_separate_37_input_preflight(self):
        data=json.loads(cap.DEFAULT_EVIDENCE.read_text(encoding="utf-8"))
        summary=json.loads((cap.ROOT/"work/runtime/native1375-v12/experiment-summary-17676.json").read_text(encoding="utf-8"))
        rows=[r for r in data["observations"] if r["scope"].get("version")=="v12"]
        descriptors=[data["artifacts"][key] for key in rows[0]["evidence"]]
        self.assertEqual(len(summary["input_artifacts"]),203)
        for descriptor in summary["input_artifacts"].values():
            self.assertIn({**descriptor,"read_mode":"whole"},descriptors)
        self.assertEqual(len(data["historical_preflights"][0]["evidence"]),37)
        self.assertEqual(len(data["artifacts"]),463)
        self.assertLess(cap.DEFAULT_EVIDENCE.stat().st_size,cap.MAX_INDEX)
        self.assertLess(sum(a["size_bytes"] for a in data["artifacts"].values()),cap.MAX_TOTAL)

    def test_no_unreviewed_actions_or_production_whitelist_can_be_enabled(self):
        original = deepcopy(self.data)
        for change in (lambda: self.data.update(production_whitelist=["guarantee"]),
                       lambda: self.data["observations"][0].update(action_id="arbitrary_native_call"),
                       lambda: self.data["observations"][0]["claims"].update(request_causality_verified=True)):
            self.data=deepcopy(original);change();self.write()
            with self.assertRaises(ValueError):
                self.describe()

    def test_research_filter_separates_protocol_ids_catalog_bindings_and_control(self):
        result = self.describe(research_only=True)
        self.assertEqual(len(result["actions"]),37)
        self.assertEqual(len(result["laboratory_protocol_action_ids"]),36)
        self.assertEqual(result["controls"][0]["action_id"],"control.speed")
        self.assertFalse(result["controls"][0]["catalogued_diplomacy_action"])
        self.assertEqual(self.describe(action_id="control.speed")["actions"],[])
        with self.assertRaises(ValueError):
            self.describe(action_id="missing")

    def test_paths_and_resource_limits_never_read_outside_reviewed_bounds(self):
        key=next(iter(self.data["artifacts"]))
        self.data["artifacts"][key]["path"]="../outside.txt"
        self.write()
        self.assertFalse(self.describe()["artifacts"][key]["available"])
        self.data["artifacts"][key]["size_bytes"]=cap.MAX_ARTIFACT+1
        self.write()
        with self.assertRaises(ValueError):
            self.describe()

    def test_cli_capabilities_never_opens_game_build_or_publishes(self):
        with patch.object(cap,"capabilities",return_value={"read_only":True}) as describe, \
             patch.object(cli.lab,"LiveLabProcess") as live, patch.object(cli.lab,"verify_build") as build, \
             patch.object(cli.lab,"publish_research") as publish, contextlib.redirect_stdout(io.StringIO()) as stdout, \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["capabilities","--action","improve_relations"]),0)
            self.assertEqual(json.loads(stdout.getvalue()),{"read_only":True})
            describe.assert_called_once_with(action_id="improve_relations",research_only=False)
            self.assertEqual(cli.main(["--pid","1","--creation","01da123456789abc","capabilities"]),2)
            live.assert_not_called();build.assert_not_called();publish.assert_not_called()

    def test_new_cli_discovery_uses_reviewed_versioned_history_without_process_access(self):
        for entry,readiness in ((cli_v7,"v7_live_readiness"),(cli_v8,"v8_live_readiness"),(cli_v9,"v9_live_readiness")):
            with self.subTest(entry=entry.__name__),patch.object(cap,"capabilities",return_value={"read_only":True,
                    "discovery_source":"v5_v6_v7_v8_v9_v10_v12_reviewed_history_with_v12_no_send_preflight"}), \
                 patch.object(entry.lab,"LiveLabProcess") as live,patch.object(entry.lab,"verify_build") as build, \
                 patch.object(entry.lab,"publish_research") as publish,contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(entry.main(["capabilities","--action","royal_marriage"]),0)
            value=json.loads(stdout.getvalue())
            self.assertEqual(value["invoked_cli_protocol"],"EU4LAB/2")
            self.assertEqual(value["discovery_source"],"v5_v6_v7_v8_v9_v10_v12_reviewed_history_with_v12_no_send_preflight")
            self.assertIsNone(value[readiness])
            live.assert_not_called();build.assert_not_called();publish.assert_not_called()

    def test_current_catalog_union_and_reviewed_snapshot_are_consistent(self):
        with patch.object(cap,"V12_PREFLIGHT_REVIEW_SHA256",self.production_review_pin), \
             patch.object(cap,"V12_EFFECT_REVIEW_SHA256",self.production_effect_pin):
            result=cap.capabilities(research_only=True)
        self.assertEqual({key:value for key,value in result["summary"].items() if key != "actions_with_reviewed_state_effects"},
            {"catalogued_actions":274,"static_mapped_actions":270,
            "ordinary_static_mapped_actions":167,"subject_static_mapped_actions":41,
            "special_static_mapped_actions":9,"peace_static_mapped_actions":53,
            "laboratory_entrypoints":36,"catalog_actions_with_laboratory_binding":37,"production_executable_actions":0})
        self.assertTrue(result["catalog_review"]["matches_current_catalog"])
        self.assertEqual(result["production_whitelist"],[])
        self.assertIsNone(result["current_session_ready"])


if __name__=="__main__":
    unittest.main()
