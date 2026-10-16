"""Read-only discovery: static catalog, gated lab entrypoints, reviewed history.

No process access, queue/database writes, native dispatch or backend registration.
Evidence is a manually reviewed historical index, never an execution whitelist.
"""
from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
import re

from .diplomacy_api import DEFAULT_CATALOG, canonical, decode_json
from .native_build import LOCAL_SHA256
from .native_pair_backend import ACTIONS, _no_links, read_bounded

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = Path(__file__).with_name("diplomacy_research_evidence.json")
MAX_CATALOG = 2 * 1024 * 1024
MAX_INDEX = 512 * 1024
MAX_ARTIFACT = 8 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
MAX_ARTIFACTS = 1024
# Independent review pin: canonical({record, artifacts: all 37 descriptors}).
# Editing scope or dropping/replacing a dependency requires a fresh manual review;
# matching whichever files remain is insufficient to preserve the old claim.
V12_PREFLIGHT_REVIEW_SHA256 = "ef2f802621e164db05a74a377378d7f47876f65f0f2b65222414510ae3fcc4b1"
# Separate review pin for the six finalized effects and every dependency.
# The earlier no-send prefix above retains its own immutable contract.
V12_EFFECT_REVIEW_SHA256 = "a282f0d319ed0e689c1f6eb282940836b6f1621204ad4654aec0fa5cd13f2fa0"
V12_EFFECT_CASES = {3: "request_trade_power", 10: "cancel_trade_power_transfer",
                    13: "steer_trade", 16: "send_gift", 19: "cancel_steer_trade", 22: "warn"}
V14_EFFECT_REVIEW_SHA256 = "dc9b75959265c3fbaf4d48e346fa130ccc28563afa489d4aaa201b2a2559156c"
V14_PERSISTENCE_REVIEW_SHA256 = "5fb2a2c92845ff24215865acad1e9d9a9f8c5979ffc52607cf8b1c3efbc94771"
V14_EFFECT_CASES = {3: "embargo", 7: "revoke_embargo", 10: "give_subsidies",
                    13: "offer_fleet_basing_rights", 19: "cancel_fleet_basing_rights",
                    31: "revoke_military_access", 37: "cancel_military_access",
                    40: "cancel_subsidies", 43: "dissolve_alliance"}
V10_ADDITIONAL_ACTIONS = frozenset(("offer_alliance", "dissolve_alliance", "ask_military_access", "cancel_military_access",
    "offer_military_access", "revoke_military_access", "ask_fleet_basing_rights", "cancel_fleet_basing_rights",
    "offer_fleet_basing_rights", "revoke_fleet_basing_rights", "embargo", "revoke_embargo", "give_subsidies", "cancel_subsidies"))
RESEARCH_ACTIONS = frozenset(ACTIONS) | V10_ADDITIONAL_ACTIONS
V12_ADDITIONAL_ACTIONS = frozenset(("warn", "insult", "form_coalition", "leave_coalition",
    "support_independence", "cancel_independence_support", "request_trade_power", "cancel_trade_power_transfer",
    "steer_trade", "cancel_steer_trade", "send_gift", "trade_favors_for_gold"))
V12_ACTIONS = RESEARCH_ACTIONS | V12_ADDITIONAL_ACTIONS
# Protocol aliases are not additional catalog entries or proof of role coverage.
V12_CATALOG_BINDINGS = {action: [action] for action in sorted(V12_ACTIONS)}
V12_CATALOG_BINDINGS["request_trade_power"] = ["transfer_trade_power"]
V12_CATALOG_BINDINGS["cancel_independence_support"] = ["cancel_offered_independence_support", "cancel_requested_independence_support"]
DISCOVERY_CATALOG_ACTIONS = frozenset(name for names in V12_CATALOG_BINDINGS.values() for name in names)
GATES = ["verified_game_and_loaded_lab_build", "matching_pid_and_creation_time", "matching_world_and_player",
         "recent_healthy_main_thread_frame", "three_completed_preflight_phases", "paused_pair_world",
         "strict_next_sequence", "unexpired_request", "no_unknown_ownership_or_pending_request", "explicit_publish"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def artifact_path(root, relative):
    require(isinstance(relative, str) and "\\" not in relative and ":" not in relative, "Evidence path must be repository-relative")
    parts = PurePosixPath(relative).parts
    require(parts and not PurePosixPath(relative).is_absolute() and all(part not in (".", "..") for part in parts),
            "Evidence path escapes the repository")
    path = Path(root).joinpath(*parts)
    _no_links(path)
    return path


def verify_artifacts(index, root):
    """Bounded fixed-prefix hashes remain stable while a native log appends."""
    artifacts = index["artifacts"]
    require(isinstance(artifacts, dict) and len(artifacts) <= MAX_ARTIFACTS, "Too many evidence artifacts")
    result, total = {}, 0
    for key, artifact in artifacts.items():
        require(isinstance(key, str) and isinstance(artifact, dict)
                and set(artifact) == {"path", "size_bytes", "sha256", "read_mode"}, "Invalid artifact descriptor")
        count = artifact["size_bytes"]
        require(type(count) is int and 0 < count <= MAX_ARTIFACT, "Artifact exceeds bounded read limit")
        require(artifact["read_mode"] in ("whole", "prefix") and isinstance(artifact["sha256"], str)
                and re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"]), "Invalid artifact hash/mode")
        total += count
        require(total <= MAX_TOTAL, "Evidence index exceeds total read budget")
        try:
            path = artifact_path(root, artifact["path"])
            digest, remaining = hashlib.sha256(), count
            with path.open("rb") as stream:
                while remaining:
                    raw = stream.read(min(65536, remaining))
                    require(raw, "Evidence was truncated")
                    remaining -= len(raw)
                    digest.update(raw)
                require(artifact["read_mode"] == "prefix" or not stream.read(1), "Evidence grew after review")
            require(digest.hexdigest() == artifact["sha256"], "Evidence hash differs from reviewed bytes")
            result[key] = dict(artifact, available=True, verification="reviewed_bytes_match")
        except (OSError, ValueError) as error:
            result[key] = dict(artifact, available=False, verification="unavailable_or_changed", reason=str(error))
    return result


def observation(record, artifacts):
    require(isinstance(record, dict) and set(record) == {"experiment_id", "action_id", "scope", "claims", "findings", "evidence", "limitations"},
            "Invalid reviewed observation schema")
    require(record["action_id"] in RESEARCH_ACTIONS or record["action_id"] == "control.speed"
            or (record["action_id"] in V12_EFFECT_CASES.values() and record.get("scope", {}).get("version") == "v12"),
            "Observation is outside the reviewed lab profile")
    claims = record["claims"]
    required = {"native_dispatch_returned", "observed_state_change", "saved_state_verified", "reload_verified",
                "request_causality_verified", "ai_acceptance_verified", "reply_rejection_correlated",
                "reply_acceptance_correlated", "native_legality_checked"}
    require(isinstance(claims, dict) and set(claims) == required and all(type(value) is bool for value in claims.values()),
            "Observation claim fields must be explicit booleans")
    require(claims["request_causality_verified"] is False and claims["ai_acceptance_verified"] is False,
            "This historical profile does not establish request causality or AI acceptance")
    refs = record["evidence"]
    require(isinstance(refs, list) and refs and len(set(refs)) == len(refs) and all(key in artifacts for key in refs),
            "Observation evidence is incomplete")
    available = all(artifacts[key]["available"] for key in refs)
    return {**record, "evidence_status": "reviewed_bytes_match" if available else "unavailable_or_changed",
            "findings": record["findings"] if available else {}, "recorded_findings": record["findings"],
            "recorded_claims": claims, "claims": claims if available else {key: False for key in required},
            "production_ready": False, "generalized_to_other_pairs": False}


def historical_preflight(record, artifacts):
    """A reviewed, immutable no-send session prefix; never a live authorization."""
    require(isinstance(record, dict) and set(record) == {"version", "protocol", "purpose", "scope", "action_ids",
            "catalog_bindings", "phase_cases", "evidence", "limitations"}, "Invalid historical preflight schema")
    require(record["version"] == "v12" and record["protocol"] == "EU4LAB/2"
            and record["purpose"] == "restricted_pair_lab_1375_v12", "Unknown historical preflight profile")
    require(record["action_ids"] == sorted(V12_ACTIONS) and record["catalog_bindings"] == V12_CATALOG_BINDINGS,
            "Preflight action/alias scope differs from the reviewed v12 contract")
    require(record["phase_cases"] == {"lifecycle": 20, "preview": 72, "command": 72}
            and all(type(n) is int for n in record["phase_cases"].values()), "Wrong preflight phase matrix")
    scope = record["scope"]
    require(isinstance(scope, dict) and set(scope) == {"pid", "creation", "world_cookie", "window_thread", "raw_date",
            "dll_sha256", "manifest_sha256", "fixture_profile_sha256", "actor", "targets", "request_count",
            "diplomatic_submit_count", "fixture_submit_count", "prefix_sha256", "prefix_bytes"}, "Invalid preflight session scope")
    require(all(type(scope[k]) is int and scope[k] > 0 for k in ("pid", "window_thread", "raw_date", "prefix_bytes"))
            and isinstance(scope["creation"], str) and re.fullmatch(r"[0-9a-f]{16}", scope["creation"])
            and isinstance(scope["world_cookie"], str) and re.fullmatch(r"0x[0-9a-f]+", scope["world_cookie"]),
            "Invalid preflight identity")
    require(all(isinstance(scope[k], str) and re.fullmatch(r"[0-9a-f]{64}", scope[k])
                for k in ("dll_sha256", "manifest_sha256", "fixture_profile_sha256", "prefix_sha256")), "Invalid preflight hashes")
    require(scope["actor"] == "FRA" and scope["targets"] == ["ENG", "POR"]
            and all(type(scope[k]) is int and scope[k] == 0
                    for k in ("request_count", "diplomatic_submit_count", "fixture_submit_count")),
            "Historical preflight must be the no-send FRA/ENG/POR matrix")
    refs = record["evidence"]
    require(isinstance(refs, list) and refs and len(set(refs)) == len(refs) and all(key in artifacts for key in refs),
            "Historical preflight evidence is incomplete")
    require(all(artifacts[key]["read_mode"] == "whole" for key in refs), "Historical preflight requires immutable whole-file evidence")
    descriptors = {key: {name: artifacts[key][name] for name in ("path", "size_bytes", "sha256", "read_mode")} for key in refs}
    digest = hashlib.sha256(canonical({"record": record, "artifacts": descriptors}).encode("utf-8")).hexdigest()
    require(digest == V12_PREFLIGHT_REVIEW_SHA256, "Historical preflight scope or dependency set differs from the independent review")
    available = all(artifacts[key]["available"] for key in refs)
    return {**record, "historical_preflight_passed": available, "recorded_historical_preflight_passed": True,
            "review_binding_sha256": digest,
            "evidence_status": "reviewed_bytes_match" if available else "unavailable_or_changed",
            "runtime_ready": None, "live_readiness": None, "live_process_inspected": False,
            "native_legality_allowed_for_all_cases": False, "diplomatic_submission_verified": False,
            "observed_state_change": False, "strict_single_player_verified": False, "world_epoch_verified": False,
            "request_causality_verified": False, "production_ready": False, "generalized_to_other_sessions": False}


def historical_v12_effect_review(records, artifacts):
    """Fixed stopped-session review, independently pinned from the no-send prefix."""
    rows = [row for row in records if row.get("scope", {}).get("version") == "v12"
            or str(row.get("experiment_id", "")).startswith("v12-")]
    require(len(rows) == 6 and [(row["scope"].get("sequence"), row["action_id"]) for row in rows]
            == list(V12_EFFECT_CASES.items()), "Unexpected finalized v12 effect cases")
    refs = rows[0]["evidence"]
    require(all(row["evidence"] == refs for row in rows)
            and all(artifacts[key]["read_mode"] == "whole" for key in refs),
            "Finalized v12 effects require the complete immutable dependency set")
    descriptors = {key: {name: artifacts[key][name] for name in ("path", "size_bytes", "sha256", "read_mode")} for key in refs}
    digest = hashlib.sha256(canonical({"observations": rows, "artifacts": descriptors}).encode("utf-8")).hexdigest()
    require(digest == V12_EFFECT_REVIEW_SHA256, "Finalized v12 effects differ from the independent review")
    available = all(artifacts[key]["available"] for key in refs)
    return {"version": "v12", "protocol": "EU4LAB/2", "purpose": "restricted_pair_lab_1375_v12",
            "pid": 17676, "creation": "01dd56989186135c", "session_stopped": True,
            "review_binding_sha256": digest, "evidence": refs,
            "evidence_status": "reviewed_bytes_match" if available else "unavailable_or_changed",
            "recorded_selected_effect_count": 6, "selected_effect_count": 6 if available else 0,
            "saved_reload_relation_count": 5 if available else 0,
            "live_readiness": None, "production_ready": False, "request_causality_verified": False,
            "strict_single_player_verified": False, "world_epoch_verified": False,
             "exact_loaded_file_path_verified": False, "whole_world_unchanged_verified": False}


def historical_v14_effect_review(records, artifacts):
    """Eight effects and one unknown; independent from selected persistence."""
    rows = [row for row in records if row.get("scope", {}).get("version") == "v14"
            or str(row.get("experiment_id", "")).startswith("v14-")]
    require(len(rows) == 9 and [(row["scope"].get("sequence"), row["action_id"]) for row in rows]
            == list(V14_EFFECT_CASES.items()), "Unexpected finalized v14 effect cases")
    refs = rows[0]["evidence"]
    require(all(row["evidence"] == refs for row in rows)
            and all(artifacts[key]["read_mode"] == "whole" for key in refs),
            "Finalized v14 effects require the complete immutable dependency set")
    descriptors = {key: {name: artifacts[key][name] for name in ("path", "size_bytes", "sha256", "read_mode")} for key in refs}
    digest = hashlib.sha256(canonical({"observations": rows, "artifacts": descriptors}).encode("utf-8")).hexdigest()
    require(digest == V14_EFFECT_REVIEW_SHA256, "Finalized v14 effects differ from the independent review")
    available = all(artifacts[key]["available"] for key in refs)
    return {"version": "v14", "protocol": "EU4LAB/2", "purpose": "restricted_pair_lab_1375_v14",
            "pid": 18356, "creation": "01dd56aa6f724ea8", "session_stopped": True,
            "review_binding_sha256": digest, "evidence": refs,
            "evidence_status": "reviewed_bytes_match" if available else "unavailable_or_changed",
            "recorded_selected_effect_count": 8, "selected_effect_count": 8 if available else 0,
            "recorded_unknown_selected_effect_count": 1,
            "unknown_actions": ["offer_fleet_basing_rights"], "inventoried_requests": 43,
            "phase_case_counts": {"lifecycle": 20, "owned_peace": 1, "preview": 72, "command": 72},
            "experimental_summary_save_reload_verified": False,
            "live_readiness": None, "production_ready": False, "request_causality_verified": False,
            "native_ai_acceptance_verified": False, "strict_single_player_verified": False, "world_epoch_verified": False}


def historical_v14_persistence_review(record, artifacts):
    """Separate selected-state review; discovery never rereads the large saves."""
    require(type(record) is dict and set(record) == {"version", "purpose", "scope", "source_summary_sha256",
            "results", "evidence", "large_save_hashes_recorded", "large_saves_rehashed_in_discovery", "limitations"}
            and record["version"] == "v14" and record["purpose"] == "v14_selected_directional_persistence_review",
            "Invalid independent v14 persistence profile")
    refs = record["evidence"]
    require(type(refs) is list and refs and len(set(refs)) == len(refs)
            and all(key in artifacts and artifacts[key]["read_mode"] == "whole" for key in refs),
            "Independent persistence evidence is incomplete")
    descriptors = {key: {name: artifacts[key][name] for name in ("path", "size_bytes", "sha256", "read_mode")} for key in refs}
    digest = hashlib.sha256(canonical({"record": record, "artifacts": descriptors}).encode("utf-8")).hexdigest()
    require(digest == V14_PERSISTENCE_REVIEW_SHA256, "Independent v14 persistence differs from its review")
    available = all(artifacts[key]["available"] for key in refs)
    return {**record, "results": record["results"] if available else [], "recorded_results": record["results"],
            "review_binding_sha256": digest,
            "evidence_status": "reviewed_bytes_match" if available else "unavailable_or_changed",
            "selected_state_count": 9 if available else 0,
            "serialized_and_typed_reload_count": 7 if available else 0,
            "typed_reload_only_count": 2 if available else 0,
            "live_readiness": None, "production_ready": False, "request_causality_verified": False,
            "normal_ai_acceptance_verified": False, "strict_single_player_verified": False, "world_epoch_verified": False,
            "exact_loaded_file_path_verified": False, "whole_world_unchanged_verified": False,
            "settlement_verified": False, "experimental_summary_save_reload_verified": False}


def capabilities(*, root=ROOT, catalog_path=DEFAULT_CATALOG, evidence_path=DEFAULT_EVIDENCE, action_id=None, research_only=False):
    """Historical capability description, deliberately not a live readiness check."""
    raw = read_bounded(Path(catalog_path), MAX_CATALOG)
    catalog = decode_json(raw.decode("utf-8-sig"))
    require(catalog.get("schema_version") == 1 and isinstance(catalog.get("actions"), list), "Unsupported catalog schema")
    require(catalog.get("game_build", {}).get("exe_sha256") == LOCAL_SHA256, "Catalog belongs to a different game build")
    registry_raw = read_bounded(Path(evidence_path), MAX_INDEX)
    registry = decode_json(registry_raw.decode("utf-8"))
    require(registry.get("schema_version") == 1 and registry.get("kind") == "reviewed_research_history"
            and registry.get("game_sha256") == LOCAL_SHA256 and registry.get("production_whitelist") == [],
            "Unsupported research index; it must not enable production execution")
    artifacts = verify_artifacts(registry, root)
    require(isinstance(registry.get("observations"), list) and len(registry["observations"]) <= 64, "Too many reviewed observations")
    observations = [observation(row, artifacts) for row in registry["observations"]]
    effect_reviews = [historical_v12_effect_review(registry["observations"], artifacts),
                      historical_v14_effect_review(registry["observations"], artifacts)]
    persistence = registry.get("historical_persistence_reviews")
    require(type(persistence) is list and len(persistence) == 1, "Missing independent v14 persistence review")
    persistence_reviews = [historical_v14_persistence_review(persistence[0], artifacts)]
    records = registry.get("historical_preflights")
    require(isinstance(records, list) and len(records) == 1, "Missing reviewed v12 preflight")
    preflights = [historical_preflight(row, artifacts) for row in records]
    experiment_ids = [row["experiment_id"] for row in observations]
    require(len(set(experiment_ids)) == len(experiment_ids), "Duplicate research experiment")
    profile_refs = registry["lab_preflight_evidence_by_version"]
    require(isinstance(profile_refs, dict) and set(profile_refs) == {"v6", "v7", "v8", "v9", "v10"}, "Missing versioned lab preflight evidence")
    history_versions = sorted({row["scope"].get("version") for row in observations
                               if isinstance(row.get("scope"), dict) and isinstance(row["scope"].get("version"), str)},
                              key=lambda version: int(version[1:]) if re.fullmatch(r"v[0-9]+", version) else -1)
    require(history_versions == ["v5", "v6", "v7", "v8", "v9", "v10", "v12", "v14"], "Unexpected reviewed history versions")
    profiles = []
    for version, protocol, tags in (("v6", "EU4LAB/1", ["FRA", "ENG", "POR"]),
                                    ("v7", "EU4LAB/2", ["FRA", "ENG", "POR", "NAV", "FOI"]),
                                    ("v8", "EU4LAB/2", ["FRA", "ENG", "POR", "NAV", "FOI"]),
                                    ("v9", "EU4LAB/2", ["FRA", "ENG", "POR", "NAV", "FOI"]),
                                    ("v10", "EU4LAB/2", ["FRA", "ENG", "POR", "NAV", "FOI"])):
        refs = profile_refs[version]
        require(isinstance(refs, list) and refs and all(key in artifacts for key in refs), "Missing lab preflight evidence")
        profiles.append({"version": version, "protocol": protocol, "runtime_ready": None,
                         "live_process_inspected": False,
                         "historical_preflight_evidence_available": all(artifacts[key]["available"] for key in refs),
                         "historical_preflight_scope": ("twelve_families_and_forty_eight_positive_cancel_pair_cases_FRA_to_ENG_POR"
                             if version == "v10" else "five_families_and_twenty_positive_cancel_pair_cases_FRA_to_ENG_POR"),
                         "parameters": {"actor_tags": tags, "target_tags": tags,
                                        "actor_must_differ_from_target": True, "submit_actor": "FRA"},
                         "required_gates": GATES, "evidence": refs})
    actions, seen = [], set()
    for original in catalog["actions"]:
        identifier = original.get("action_id")
        require(isinstance(identifier, str) and identifier not in seen, "Missing or duplicate catalog action")
        seen.add(identifier)
        mapping = original.get("native_mapping", {})
        subject_mapping = original.get("native_subject_mapping", {})
        special_mapping = original.get("native_special_mapping", {})
        peace_mapping = original.get("native_peace_mapping", {})
        ordinary_mapped = mapping.get("exe_sha256") == LOCAL_SHA256 and mapping.get("evidence_level") == "static_only" and bool(mapping.get("variants"))
        subject_mapped = subject_mapping.get("exe_sha256") == LOCAL_SHA256 and subject_mapping.get("evidence_level") == "static_only" \
            and bool(subject_mapping.get("interaction")) and bool(subject_mapping.get("command"))
        special_mapped = special_mapping.get("exe_sha256") == LOCAL_SHA256 and special_mapping.get("evidence_level") == "static_only" \
            and bool(special_mapping.get("command")) and bool(special_mapping.get("source_report"))
        peace_mapped = peace_mapping.get("exe_sha256") == LOCAL_SHA256 and peace_mapping.get("evidence_level") == "static_only" \
            and bool(peace_mapping.get("component")) and bool(peace_mapping.get("source_report"))
        mapped = ordinary_mapped or subject_mapped or special_mapped or peace_mapped
        in_lab = identifier in DISCOVERY_CATALOG_ACTIONS
        lab_profiles = [profile for profile in profiles if identifier in ACTIONS or profile["version"] == "v10"] if identifier in RESEARCH_ACTIONS else []
        matching = [record for record in preflights if any(identifier in names for names in record["catalog_bindings"].values())]
        for record in matching:
            lab_profiles.append({"version": record["version"], "protocol": record["protocol"], "runtime_ready": None,
                "live_process_inspected": False, "historical_preflight_passed": record["historical_preflight_passed"],
                "historical_preflight_evidence_available": record["historical_preflight_passed"],
                "historical_preflight_scope": "twenty_families_and_seventy_two_positive_cancel_pair_cases_FRA_to_ENG_POR_no_send",
                "research_action_ids": [key for key, names in record["catalog_bindings"].items() if identifier in names],
                "alias_binding_is_role_coverage_proof": False, "parameters": {"actor_tags": ["FRA", "ENG", "POR", "NAV", "FOI"],
                    "target_tags": ["FRA", "ENG", "POR", "NAV", "FOI"], "actor_must_differ_from_target": True, "submit_actor": "FRA"},
                "reviewed_case_targets": ["ENG", "POR"], "required_gates": GATES, "evidence": record["evidence"]})
        original_profile = identifier in ACTIONS
        historical = [row for row in observations if identifier in V12_CATALOG_BINDINGS.get(row["action_id"], [row["action_id"]])]
        actions.append({"action_id": identifier, "name_zh": original.get("name_zh"), "category": original.get("category"),
                        "parameter_status": original.get("parameter_status"), "parameters": original.get("parameters"),
                        "static": {"status": "mapped" if mapped else "catalog_only", "mapped": mapped,
                                   "ordinary_mapped": ordinary_mapped, "subject_mapped": subject_mapped,
                                   "special_mapped": special_mapped, "peace_mapped": peace_mapped,
                                   "native_mapping": mapping or None, "native_subject_mapping": subject_mapping or None,
                                   "native_special_mapping": special_mapping or None,
                                   "native_peace_mapping": peace_mapping or None,
                                   "execution_proven": False},
                        "laboratory": {"status": "gated_entrypoint" if in_lab else "not_implemented",
                                       "entrypoint_available": in_lab, "protocol": ("EU4LAB/1" if original_profile else "EU4LAB/2") if in_lab else None,
                                       "profiles": lab_profiles,
                                       "protocol_field_scope": ("original_v6_entrypoint" if original_profile else "v10_entrypoint" if identifier in RESEARCH_ACTIONS else "v12_entrypoint_or_role_alias") if in_lab else None,
                                       "modes": ["legality_only", "submit"] if in_lab else [],
                                       "runtime_ready": None, "live_process_inspected": False,
                                       "historical_preflight_evidence_available": lab_profiles[0]["historical_preflight_evidence_available"] if in_lab else False,
                                       "historical_preflight_scope": lab_profiles[0]["historical_preflight_scope"] if in_lab else None,
                                       "parameters": lab_profiles[0]["parameters"] if in_lab else None,
                                       "required_gates": GATES if in_lab else []},
                        "observed_effects": {"available": any(row["claims"]["observed_state_change"] for row in historical),
                                             "scope": "fixed_reviewed_experiments_only", "experiments": historical,
                                             "absence_means": "not_verified_in_this_history_not_impossible"},
                        "production": {"status": "unsupported", "ready": False, "backend_registered": False,
                                       "reason": "No production sender is registered; historical research does not enable execution"}})
    require(DISCOVERY_CATALOG_ACTIONS <= seen, "Catalog lacks a laboratory action or alias binding")
    controls = [{"action_id": "control.speed", "catalogued_diplomacy_action": False,
                 "laboratory": {"status": "gated_entrypoint", "protocol": "EU4LAB/1", "runtime_ready": None,
                                "protocols": ["EU4LAB/1", "EU4LAB/2"],
                                "speed_range": [0, 5], "positive_speed_requires_external_watchdog": True,
                                "lease_duration_ms": 5000, "lease_max_raw_date_delta": 48},
                 "observed_effects": [row for row in observations if row["action_id"] == "control.speed"],
                 "production": {"status": "unsupported", "ready": False, "backend_registered": False}}]
    summary = {"catalogued_actions": len(actions), "static_mapped_actions": sum(row["static"]["mapped"] for row in actions),
               "ordinary_static_mapped_actions": sum(row["static"]["ordinary_mapped"] for row in actions),
               "subject_static_mapped_actions": sum(row["static"]["subject_mapped"] for row in actions),
               "special_static_mapped_actions": sum(row["static"]["special_mapped"] for row in actions),
               "peace_static_mapped_actions": sum(row["static"]["peace_mapped"] for row in actions),
               "laboratory_entrypoints": len(V12_ACTIONS),
               "catalog_actions_with_laboratory_binding": sum(row["laboratory"]["entrypoint_available"] for row in actions),
               "actions_with_reviewed_state_effects": sum(row["observed_effects"]["available"] for row in actions),
               "production_executable_actions": 0}
    if action_id is not None:
        require(action_id in seen or action_id in V12_CATALOG_BINDINGS or action_id == "control.speed", "Unknown action identifier")
        selected = V12_CATALOG_BINDINGS.get(action_id, [action_id])
        actions = [row for row in actions if row["action_id"] in selected]
        controls = [row for row in controls if row["action_id"] == action_id]
    elif research_only:
        actions = [row for row in actions if row["laboratory"]["entrypoint_available"]]
    references = []
    for reference in registry.get("references", []):
        require(isinstance(reference, dict) and set(reference) == {"reference_id", "document", "evidence", "scope"},
                "Invalid research reference")
        refs = reference["evidence"]
        require(isinstance(refs, list) and refs and all(key in artifacts for key in refs), "Missing reference evidence")
        artifact_path(root, reference["document"])
        references.append({**reference, "evidence_available": all(artifacts[key]["available"] for key in refs),
                           "production_ready": False, "live_readiness": None})
    reviewed_catalog = registry.get("reviewed_catalog", {})
    require(isinstance(reviewed_catalog, dict) and set(reviewed_catalog) == {"sha256", "counts", "evidence"}
            and isinstance(reviewed_catalog["sha256"], str)
            and re.fullmatch(r"[0-9a-f]{64}", reviewed_catalog["sha256"]), "Invalid reviewed catalog snapshot")
    require(isinstance(reviewed_catalog["evidence"], list) and reviewed_catalog["evidence"]
            and all(key in artifacts for key in reviewed_catalog["evidence"]), "Missing catalog review evidence")
    catalog_review = {**reviewed_catalog, "matches_current_catalog": hashlib.sha256(raw).hexdigest() == reviewed_catalog["sha256"],
                      "evidence_available": all(artifacts[key]["available"] for key in reviewed_catalog["evidence"]),
                      "production_ready": False}
    return {"schema_version": 1, "kind": "diplomacy_research_capabilities", "read_only": True,
            "discovery_scope": "offline_catalog_and_reviewed_history", "game_sha256": LOCAL_SHA256,
            "discovery_source": "_".join(history_versions) + "_reviewed_history_with_v12_no_send_preflight",
            "reviewed_history_versions": history_versions, "runtime_unreviewed_versions": ["v11", "v13"],
            "historical_effect_reviews": effect_reviews,
            "historical_persistence_reviews": persistence_reviews,
            "historical_preflights": preflights, "laboratory_protocol_action_ids": sorted(V12_ACTIONS),
            "catalog_sha256": hashlib.sha256(raw).hexdigest(), "research_index_sha256": hashlib.sha256(registry_raw).hexdigest(),
            "evidence_cutoff": registry["cutoff"], "summary": summary, "actions": actions, "controls": controls,
            "artifacts": artifacts, "production_backend_registered": False, "production_whitelist": [],
            "live_process_inspected": False, "current_session_ready": None,
            "catalog_review": catalog_review, "research_references": references,
            "semantics": {"static": "Evidence of mapping only", "laboratory": "Implemented gated research entrypoint; not current legality or readiness",
                          "observed_effects": "Historical state difference in named exact experiments; never inferred from submit return",
                          "production": "Current shipped HTTP/CLI sender remains unsupported"}}
