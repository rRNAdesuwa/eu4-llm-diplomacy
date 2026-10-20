"""Create/check a finite, offline experiment plan. Never opens a game process.

Only the frozen v14 pure encoder/decoder/build-file verifier are used. No lab
publish, LiveLabProcess, native calls, listener or request file is created.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from work.native import lab_protocol_v14_1375 as lab

OBSERVER_PATH = "work/candidates/directional-pair-observer-1375/observer.py"
OBSERVER_SHA = "acb38546adea4d1fef88803a1057e465d7e5ff297fe4959760757d3b7fce1496"
MANIFEST_SHA = "aa09084d3d1d7c9adff164b67356d72e2c511b519e79b382e7bc54a80c96ec75"
DLL_SHA = "ABFB2E343F7E7332EFA96C45B1DD2B89C00AC2B4085CBD9FC32E8F90DB299296"
MAX_INPUT = 4 * 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024
MAX_INPUTS = 32
TEN = (
    "embargo", "revoke_embargo", "offer_fleet_basing_rights", "revoke_fleet_basing_rights",
    "cancel_fleet_basing_rights", "revoke_military_access", "cancel_military_access",
    "give_subsidies", "cancel_subsidies", "dissolve_alliance",
)
SETUPS = ("ask_fleet_basing_rights", "offer_military_access", "ask_military_access", "offer_alliance")
INPUTS = (
    "work/native/lab_protocol_v14_1375.py", "tools/request_diplomacy_lab_v14.py",
    "work/native/v14/lab-request-1375.h", "work/native/v14/pair-engine-1375.cpp",
    "work/native/v14/pair-engine-1375.h", "work/native/v14/research-lab-1375.cpp",
    "work/runtime/native1375-v14/build.json",
    "work/candidates/fixture-v14-1375/mod/llm_diplomacy_test/events/llmt_fixture.txt",
    "work/candidates/fixture-v14-1375/mod/llm_diplomacy_test/common/event_modifiers/llm_diplomacy_test.txt",
    OBSERVER_PATH, "work/candidates/directional-pair-observer-1375/evidence-contract.json",
    "work/candidates/directional-pair-observer-1375/validation-strict-two-pass.json",
    "work/review-results/directional-pair-observer-fixed-action-catalog-20261008a.json",
    "work/reports/native-pair-extension-effects-v10-1375.json",
    "work/reports/native-pair-extension-v10-1375.json",
    "bridge/diplomacy_research_evidence.json", "bridge/diplomacy_catalog.json",
    "work/runtime/native1375-v14/preflight-summary-29492.json",
    "work/runtime/native1375-v14/preflight-prefix-29492/research-1375.jsonl",
    "work/runtime/native1375-v14/directional-embargo-legality-result-18356-seq2.json",
    "work/runtime/native1375-v14/directional-state-after-fixture-18356.json",
    "work/runtime/native1375-v12/experiment-summary-17676.json",
    "docs/native-pair-production-readiness-1375.md",
    "docs/native-single-player-origin-1375.md", "docs/native-single-player-context-1375.md",
    "docs/native-world-epoch-1375.md",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def bounded(path):
    with Path(path).open("rb") as stream:
        value = stream.read(MAX_INPUT + 1)
    require(len(value) <= MAX_INPUT, "Input exceeds bounded read")
    return value


def pins():
    require(len(INPUTS) <= MAX_INPUTS and len(set(INPUTS)) == len(INPUTS), "Invalid input inventory")
    result = {}
    total = 0
    for name in INPUTS:
        raw = bounded(ROOT / name)
        total += len(raw)
        require(total <= MAX_TOTAL, "Total input bound exceeded")
        result[name] = {"size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    require(result[OBSERVER_PATH]["sha256"] == OBSERVER_SHA, "Reviewed observer changed")
    require(result["work/runtime/native1375-v14/build.json"]["sha256"] == MANIFEST_SHA, "Frozen v14 manifest changed")
    return result


def observer():
    require(hashlib.sha256(bounded(ROOT / OBSERVER_PATH)).hexdigest() == OBSERVER_SHA, "Observer changed")
    spec = importlib.util.spec_from_file_location("directional_plan_observer", ROOT / OBSERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.verify_contract()
    return module


def request_template(action, mode):
    require(action in TEN + SETUPS and mode in ("legality_only", "submit"), "Outside fixed plan")
    return {"operation": "pair", "mode": mode, "action": action, "actor": "FRA", "target": "POR", "speed": 0}


def synthetic_wire(action, mode):
    # Non-live synthetic identities, never written under a mailbox or .request name.
    record, raw = lab.prepare_request(
        {"pid": 1, "process_creation_filetime": "0000000000000001"}, {"last_sequence": 0},
        sequence=1, ttl_ms=5000, now=1, **request_template(action, mode))
    require(lab.decode_request(raw) == record, "Frozen codec did not round trip")
    return record, raw


def group(name, positive, negative, *, setup=False, prerequisite, before_after):
    return {"group_id": name, "positive": positive, "negative": negative,
            "positive_is_reviewed_setup_only": setup,
            "natural_precondition": prerequisite, "selected_before_after": before_after,
            "sequence_policy": "resolve_current_pending_then_explicit_fresh_next_for_each_legality_and_submit",
            "order": [positive, negative], "skip_positive_only_when_selected_active_state_is_independently_verified": True,
            "cancel_requires_active_before": True, "automatic_retry": False,
            "same_raw_date_per_effect_comparison": True}


def groups():
    return [
        group("01_embargo", "embargo", "revoke_embargo",
              prerequisite="FRA outgoing embargo bit to POR absent for add; present for revoke. Other bits are not this state.",
              before_after="FRA record(POR)+0x46 bit 0x02: 0->1 then 1->0. POR incoming/opposite embargo remains unchanged."),
        group("02_fleet_fra_grants", "offer_fleet_basing_rights", "revoke_fleet_basing_rights",
              prerequisite="Ordinary POR-held FRA-granted fleet relation absent for offer; unique active bilateral indexed relation required for revoke.",
              before_after="holder POR / grantor FRA; FRA index f8/104 and POR e0/ec; object first POR, second FRA; absent->active->absent."),
        group("03_fleet_fra_holds", "ask_fleet_basing_rights", "cancel_fleet_basing_rights", setup=True,
              prerequisite="A unique ordinary FRA-held POR-granted fleet relation is required; use historically reviewed ask only if absent and fresh legality permits.",
              before_after="holder FRA / grantor POR; FRA e0/ec and POR f8/104; first FRA, second POR; active->absent."),
        group("04_military_fra_grants", "offer_military_access", "revoke_military_access", setup=True,
              prerequisite="A unique ordinary POR-held FRA-granted military relation is required; use historically reviewed offer only if absent and fresh legality permits.",
              before_after="holder POR / grantor FRA; FRA c8/d4 and POR b0/bc; first POR, second FRA; active->absent."),
        group("05_military_fra_holds", "ask_military_access", "cancel_military_access", setup=True,
              prerequisite="A unique ordinary FRA-held POR-granted military relation is required; use historically reviewed ask only if absent and fresh legality permits.",
              before_after="holder FRA / grantor POR; FRA b0/bc and POR c8/d4; first FRA, second POR; active->absent."),
        group("06_fixed_subsidy", "give_subsidies", "cancel_subsidies",
              prerequisite="No selected outgoing FRA->POR subsidy for add. For cancel, unique FRA payer/POR payee object with exactly 1000 milli/month and 10 years, not nominally expired. Reverse subsidy cannot be reused.",
              before_after="Both roots 110/11c; first FRA, second POR; +40=1000 and +44=10; absent->active->absent. Do not infer immediate treasury debit or future payments."),
        group("07_alliance_last", "offer_alliance", "dissolve_alliance", setup=True,
              prerequisite="Unique same alliance object on both sides. If absent, independently gate offer_alliance and wait for observed active state; target acceptance is not assumed.",
              before_after="Symmetric FRA/POR 80/8c, same object, either handle order; active->absent. Initiator, truce and whole opinion restoration are not verified."),
    ]


def historical_matrix():
    path = ROOT / "work/runtime/native1375-v14/preflight-prefix-29492/research-1375.jsonl"
    families = {"allianceaction", "milaccess", "offermilaccess", "fleet_access", "offer_fleet_access", "embargoaction", "warsubsidy"}
    result = []
    for line in bounded(path).splitlines():
        require(len(line) <= 16384, "Historical line exceeds bound")
        row = json.loads(line)
        if row.get("event") in ("pair_preview_case", "pair_command_case") and row.get("target") == "POR" and row.get("action") in families:
            require(type(row["allowed"]) is bool and row["submitted"] is False and row["exception"] == 0, "Invalid historical phase row")
            result.append({key: row[key] for key in ("event", "case_index", "action", "mode", "allowed", "submitted")})
    require(len(result) == 28 and len({(r["event"], r["action"], r["mode"]) for r in result}) == 28, "Missing finite historical matrix")
    require(all(row["allowed"] is (row["mode"] == "positive") for row in result), "Historical matrix changed")
    return result


def validate_plan(plan):
    require(plan["purpose"] == "offline_directional_experiment_plan_v14_1375" and plan["protocol"] == lab.PROTOCOL
            and plan["host_purpose"] == lab.PURPOSE, "Wrong plan version")
    require(plan["candidate_only"] is True and plan["live_readiness"] is None
            and all(plan[name] is False for name in ("production_ready", "native_calls", "requests_published", "effects_promoted")), "Overstated plan")
    require(plan["execution_order_is_future_sequence"] is False and plan["automatic_target_fallback"] is False, "Unsafe ordering/fallback")
    require(plan["direction_action_ids"] == list(TEN) and plan["setup_action_ids"] == list(SETUPS), "Direction/setup scope changed")
    require(canonical(plan["groups"]) == canonical(groups()), "Direction roles/order/preconditions changed")
    require(len(plan["cases"]) == 10, "Wrong case count")
    obs = observer()
    for case, action in zip(plan["cases"], TEN):
        require(case["action_id"] == action and case["fresh_legality_required"] is True
                and case["target_permission_verified"] is False and case["native_submit_authorized_by_this_plan"] is False,
                "Case permission cannot be inferred from plan")
        require(canonical(case["binding"]) == canonical(obs.binding(action, "POR")), "Selected role/fixed parameter changed")
        require(case["observer_sha256"] == OBSERVER_SHA and case["future_sequence"] is None, "Observer or sequence binding changed")
        for mode in ("legality_only", "submit"):
            require(canonical(case["requests"][mode]) == canonical(request_template(action, mode)), "Extra or changed public request fields")
            synthetic_wire(action, mode)
    require(plan["historical_effect_action_count"] == 20 and plan["production_executable_action_count"] == 0, "Effect/history count changed")
    require(set(plan["other_unreviewed_wire_ids"]) == {"insult", "form_coalition", "leave_coalition", "support_independence", "cancel_independence_support", "trade_favors_for_gold"}, "Other blockers incomplete")


def make_plan():
    obs = observer()
    history = json.loads(bounded(ROOT / "bridge/diplomacy_research_evidence.json"))
    observed = {row["action_id"] for row in history["observations"] if row["claims"].get("observed_state_change") is True} & lab.ACTIONS
    require(len(observed) == 20 and not set(TEN) & observed and set(SETUPS) <= observed, "Reviewed direction history changed")
    require(history["production_whitelist"] == [], "Production whitelist unexpectedly enabled")
    current = json.loads(bounded(ROOT / "work/runtime/native1375-v14/directional-embargo-legality-result-18356-seq2.json"))["report"]
    request = current["request"]["request"]
    core = current["request"]["records"][-1]
    require(request["sequence"] == 2 and request["action"] == "embargo" and request["mode"] == "legality_only"
            and core["preview_allowed"] is True and core["gate_allowed"] is True and core["submit_entered"] is False,
            "Fixed seq2 legality evidence changed")
    result = {
        "schema_version": 1, "purpose": "offline_directional_experiment_plan_v14_1375",
        "protocol": lab.PROTOCOL, "host_purpose": lab.PURPOSE, "candidate_only": True,
        "native_calls": False, "requests_published": False, "effects_promoted": False,
        "production_ready": False, "live_readiness": None, "automatic_target_fallback": False,
        "execution_order_is_future_sequence": False, "actor": "FRA", "primary_target": "POR",
        "direction_action_ids": list(TEN), "setup_action_ids": list(SETUPS),
        "frozen_manifest_sha256": MANIFEST_SHA, "frozen_dll_sha256": DLL_SHA,
        "historical_effect_action_count": len(observed), "production_executable_action_count": 0,
        "maximum_selected_direction_submits": 10, "maximum_conditional_setup_submits": 4,
        "historical_legality_cutoff": {
            "pid": current["pid"], "creation": current["creation"], "sequence": 2,
            "action": "embargo", "actor": "FRA", "target": "POR", "mode": "legality_only",
            "native_preview_allowed": True, "command_gate_allowed": True, "submit_entered": False,
            "raw_date": core["raw_date"], "world_cookie": core["world"],
            "not_a_current_permission": True, "later_session_files_not_read": True,
        },
        "historical_preflight_matrix": historical_matrix(),
        "historical_matrix_is_fresh_legality": False,
        "groups": groups(),
        "cases": [{"action_id": action, "binding": obs.binding(action, "POR"),
                   "requests": {mode: request_template(action, mode) for mode in ("legality_only", "submit")},
                   "fresh_legality_required": True, "target_permission_verified": False,
                   "native_submit_authorized_by_this_plan": False, "future_sequence": None,
                   "observer_sha256": OBSERVER_SHA} for action in TEN],
        "shared_preconditions": [
            "Exact current PID+creation, loaded DLL/build/source/fixture profile, current FRA player and world roots must pass existing frozen guards.",
            "All four current-session phases 20/1/72/72 and following healthy frame; no pending input, lease, thread/world change or frozen session.",
            "Latest native heartbeat age <=2500ms; independently read same raw date and stable pause. Completion of a prior request alone does not prove readiness.",
            "Resolve every already-published request before another. Explicit next sequence is last_sequence+1, unique per legality and submit; never reuse or infer from group ordinal.",
            "Fresh legality-only must finish with both native preview and command gate allowed, no exception/ownership uncertainty. A guard reject is not a native legality result.",
            "Submit repeats native main-thread legality, cancellation binding, player/world/thread and diplomat/cooldown checks; no caller-supplied envoy ID or manual override.",
            "Collect corrected-observer pre/post snapshots for the exact action ID and direction, with complete type-identical passes and same process identity/raw date.",
            "For cancellation collect an active-before snapshot for the cancellation action itself; do not retag positive-family snapshots or count absent->absent.",
            "If elapsed time is needed, use the existing exact-process external watchdog speed path, wait for fresh lease-inactive paused state, then reacquire both snapshots. No direct speed endpoint or scripted retry.",
        ],
        "status_boundaries": {
            "legality_only": "status1/reason0 with preview+gate true and no submit; feasibility at that observed point, not AI acceptance",
            "pre_dispatch_rejected": "Preserve status0/reason and no-submit evidence; not an applied result nor proof native preview ran",
            "dispatched": "status2/reason0 + submit returned + caller container consumed + exception0/no uncertain ownership; not applied until separate observer evidence",
            "dispatch_unknown": "Freeze and stop; do not reconstruct/retry or call destructor on uncertain transferred ownership",
            "effect": "Selected typed absent->active or active->absent only; no request-ID causal proof, AI acceptance, broad world equivalence or production promotion",
            "persistence": "Not validated by this plan. Future named save/independent reload requires its own fixed evidence reviewer.",
        },
        "target_and_fixture_limits": [
            "POR is a supported identity with positive historical legality; it is not guaranteed to agree now. No automatic fallback to other TAGs.",
            "Fixture v3 gives FRA diplomats/reputation and NAV/FOI opinions; NAV becomes FRA's vassal. It does not set POR opinion or these access/alliance/subsidy/embargo states.",
            "fixture_off removes selected modifiers/opinions but does not undo NAV's vassalage or prove diplomat pool restoration.",
            "Do not repeat fixture_on or assume independent state from a positive fixture callback. Existing independent observations and frozen fixture guards remain required.",
            "Embargo is scheduled first because seq2 already checked it; revoke before friendly proposals. The bit reversal does not restore all opinions, penalties or prior world state.",
            "Offer-alliance setup may occur earlier only if fresh legality permits and it helps the chosen test; alliance is not asserted as a native prerequisite for access. Dissolve it after access/subsidy groups.",
        ],
        "other_unreviewed_wire_ids": ["insult", "form_coalition", "leave_coalition", "support_independence", "cancel_independence_support", "trade_favors_for_gold"],
        "other_action_blockers": {
            "insult": "v12 seq28 legality allowed, fixed index -1; no reviewed selected effect observer or dispatch/persistence evidence, so not in ten-direction plan.",
            "form_coalition": "v12 seq23/25 POR native preview rejected reason17 even after a date change. Existing fixture does not establish AE/coalition eligibility; no bypass.",
            "leave_coalition": "Requires current FRA coalition membership against target and the matching bounded member structure. Positive formation is not established.",
            "support_independence": "v12 seq26 FRA/POR guard rejected status0/reason13 before preview. Both independent fails scope; FRA->NAV under fixture also fails because FRA is NAV's overlord. Another eligible subject/overlord is not proven.",
            "cancel_independence_support": "Requires a matching active support relation in one of the host's two roles; no supported positive fixture or active relation is established.",
            "trade_favors_for_gold": "v12 seq27 POR native preview rejected reason17; do not invent favor amount or derive expected economy from output. This observer does not cover that action.",
        },
        "production_blockers": [
            "Research EU4LAB/2 is separate from undeployed EU4PAIR/1 production consumer; production whitelist is empty.",
            "No strict current-world single-player provenance or reliable same-process world-generation witness is established by classifier=false/pointers/paused frame.",
            "Selected read-only observations are bounded two-pass snapshots, not engine-lifetime locks or general ownership proof. Main-thread bindings/diplomats must be rechecked per call.",
            "10 selected directions and six other wire IDs have no reviewed effects at this fixed evidence cutoff; static catalogue mappings do not authorize additional request shapes.",
            "A successful research lifecycle/command gate does not establish all-target validity, AI acceptance, complete effects, serialization or production recovery.",
        ],
    }
    validate_plan(result)
    return result


def outputs():
    pinned = pins()
    manifest, digest = lab.verify_build() # Read-only disk verification, not process inspection.
    require(digest == MANIFEST_SHA and manifest["dll_sha256"] == DLL_SHA, "Frozen build changed")
    plan = make_plan()
    checks = []
    for action in TEN + SETUPS:
        for mode in ("legality_only", "submit"):
            record, raw = synthetic_wire(action, mode)
            checks.append({"action": action, "mode": mode, "wire_bytes": len(raw), "wire_sha256": hashlib.sha256(raw).hexdigest(),
                           "synthetic_pid": record["pid"], "synthetic_creation": record["creation"], "synthetic_sequence": record["sequence"]})
    return {
        "plan.json": plan,
        "input-pins.json": {"schema_version": 1, "purpose": "offline_directional_plan_inputs", "files": pinned,
            "input_count": len(pinned), "input_bytes": sum(row["size_bytes"] for row in pinned.values()),
            "bounds": {"count": MAX_INPUTS, "per_input": MAX_INPUT, "total": MAX_TOTAL},
            "frozen_native_sources_checked": len(lab.SOURCES), "frozen_host_sources_checked": len(lab.HOST_SOURCES),
            "frozen_support_sources_checked": len(lab.SUPPORT_SOURCES), "manifest_sha256": digest},
        "offline-wire-checks.json": {"purpose": "synthetic_codec_checks_only", "protocol": lab.PROTOCOL,
            "game_process_accessed": False, "publishable": False, "requests_written": False, "checks": checks},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    result = outputs()
    for name, data in result.items():
        path = HERE / name
        if args.check:
            require(canonical(json.loads(bounded(path))) == canonical(data), "Candidate output differs: " + name)
        else:
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
    print(json.dumps({"checked": args.check, "directions": len(TEN), "conditional_setups": len(SETUPS),
                      "codec_cases": 28, "game_process_accessed": False, "requests_written": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
