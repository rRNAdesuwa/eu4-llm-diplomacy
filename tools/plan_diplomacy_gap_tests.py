"""File-only gap planner; historical successes are excluded across all versions.

This never opens EU4 or publishes requests. Being a gap does not mean an action
is legal in the current campaign. Use suitable conditions/fixtures first.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "bridge/diplomacy_research_evidence.json"
SPY = ROOT / "work/runtime/v19-selected-comparison-60864.json"
SPY_REVIEW = ROOT / "work/review-results/v19-journal-r2-external-20261008a/review.json"
CURRY = ROOT / "work/runtime/v26-gap-curry-selected-55236.json"
CURRY_AUDIT = ROOT / "work/runtime/v26-gap-curry-send-audit-55236.json"
INSULT = ROOT / "work/runtime/v27-gap-final-selected-53332.json"
INSULT_AUDIT = ROOT / "work/runtime/v27-gap-send-audit-53332.json"
GAP28_AUDIT = ROOT / "work/runtime/v28-gap-send-audit-53368.json"
GAP28_SAVE = ROOT / "work/runtime/v28-gap-save-final-53368.json"
GAP28_COALITION = ROOT / "work/runtime/v28-gap-coalition-save-53368.json"
GAP28_STOP = ROOT / "work/runtime/v28-gap-stop-curry-selected-53368.json"
GAP27_SAVE = ROOT / "work/runtime/v27-gap-save-final-53332.json"
# Reviewed lab-to-catalog binding, diplomacy_research_capabilities.py:48.
ALIASES = {"request_trade_power": "transfer_trade_power"}


def success_ledger():
    history = json.loads(HISTORY.read_text(encoding="utf-8-sig"))
    catalog = json.loads((ROOT / "bridge/diplomacy_catalog.json").read_text(encoding="utf-8-sig"))
    ids = {a["action_id"] for a in catalog["actions"]}
    blocked = {}
    for observation in history["observations"]:
        original_action = observation["action_id"]
        if not observation["claims"].get("observed_state_change") or original_action == "control.speed":
            continue
        action = ALIASES.get(original_action, original_action)
        if action not in ids:
            raise ValueError(f"historical success requires a catalog/alias binding: {original_action}")
        if action in ids:
            blocked.setdefault(action, []).append({"source": str(HISTORY.relative_to(ROOT)),
                                                  "experiment": observation["experiment_id"],
                                                  "historical_action_id": original_action,
                                                  "scope": "historical_selected_state_change"})
    spy = json.loads(SPY.read_text(encoding="utf-8-sig"))
    review = json.loads(SPY_REVIEW.read_text(encoding="utf-8-sig"))
    if not spy["selected_state_observed"] or not review["passed"]:
        raise ValueError("stopped spy evidence/review unavailable")
    for row in spy["rows"]:
        if not row["initial_selected_matching"] and any(x["active_by_expiry_comparison"] for x in row["final_selected_matching"]):
            blocked.setdefault(row["family"], []).append({"source": str(SPY.relative_to(ROOT)),
                                                         "experiment": "v19-spy5-selected-comparison",
                                                         "scope": "selected_state_observed_not_request_causality"})
    curry = json.loads(CURRY.read_text(encoding="utf-8-sig"))
    curry_audit = json.loads(CURRY_AUDIT.read_text(encoding="utf-8-sig"))
    if (curry["state"]["active_graph_observed"] is not True or curry["two_pass_equal"] is not True
            or curry["process"]["identity"]["pid"] != curry_audit["identity"]["pid"]
            or curry["process"]["identity"]["creation_filetime"] != curry_audit["identity"]["creation"]
            or curry_audit["complete"] is not True or curry_audit["dispatched"] != 1):
        raise ValueError("stopped curry evidence/audit unavailable")
    blocked.setdefault("curry_favors", []).append({"source": str(CURRY.relative_to(ROOT)),
        "experiment": "v26-gap-curry-55236", "scope": "active_selected_relation_mission_graph_after_native_dispatch"})
    insult = json.loads(INSULT.read_text(encoding="utf-8-sig"))
    insult_audit = json.loads(INSULT_AUDIT.read_text(encoding="utf-8-sig"))
    selected = insult["observations"]["insult_NAV"]
    if (selected["state"]["status"] != "present"
            or selected["passes"][0]["snapshot"] != selected["passes"][1]["snapshot"]
            or insult["process"]["pid"] != insult_audit["identity"]["pid"]
            or insult["process"]["creation"] != insult_audit["identity"]["creation"]
            or insult_audit["dispatched"] != 2
            or not any(r["sequence"] == 2 and r["submitted"] is True for r in insult_audit["results"])):
        raise ValueError("stopped insult evidence/audit unavailable")
    blocked.setdefault("insult", []).append({"source": str(INSULT.relative_to(ROOT)),
        "experiment": "v27-gap-insult-53332", "scope": "selected_insulted_modifier_present_after_native_dispatch"})
    gap28_audit = json.loads(GAP28_AUDIT.read_text(encoding="utf-8-sig"))
    gap28_save = json.loads(GAP28_SAVE.read_text(encoding="utf-8-sig"))
    coalition = json.loads(GAP28_COALITION.read_text(encoding="utf-8-sig"))
    stop = json.loads(GAP28_STOP.read_text(encoding="utf-8-sig"))
    before = json.loads(GAP27_SAVE.read_text(encoding="utf-8-sig"))
    def pair_present(save, key, actor, target):
        return any(r["key"] == key and {e["key"]: e.get("value") for e in r["entries"]}.get("first") == actor
                   and {e["key"]: e.get("value") for e in r["entries"]}.get("second") == target
                   for r in save["global_diplomacy"]["records"])
    if (not gap28_audit["complete"] or gap28_audit["terminal"] or gap28_audit["dispatched"] != 3
            or any(not gap28_audit["results"][i - 1]["submitted"] for i in (1, 3, 4))
            or not all(x["parsed_complete"] for x in (before, gap28_save, coalition))
            or coalition["source"]["sha256"] != gap28_save["source"]["sha256"]
            or not pair_present(gap28_save, "support_independence", "FRA", "HOL")
            or pair_present(before, "support_independence", "FRA", "HOL")
            or not pair_present(before, "curry_favors", "FRA", "POR")
            or pair_present(gap28_save, "curry_favors", "FRA", "POR")
            or stop["two_pass_equal"] is not True or stop["state"]["relation_index_present"] is not False
            or stop["process"]["identity"]["pid"] != gap28_audit["identity"]["pid"]
            or stop["process"]["identity"]["creation_filetime"] != gap28_audit["identity"]["creation"]
            or not any(e["key"] == "coalition_target" and e.get("value") == "SAV" for e in coalition["countries"]["FRA"]["fields"])):
        raise ValueError("V28 stopped selected-state evidence unavailable")
    for action, source, scope in (("support_independence", GAP28_SAVE, "new_serialized_support_independence_pair"),
                                  ("stop_currying_favors", GAP28_STOP, "selected_relation_removed_envoy_returning_and_save_record_removed"),
                                  ("form_coalition", GAP28_COALITION, "serialized_coalition_target_SAV_after_dispatch")):
        blocked.setdefault(action, []).append({"source": str(source.relative_to(ROOT)), "experiment": "v28-gap-53368", "scope": scope})
    pins = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (HISTORY, SPY, SPY_REVIEW, CURRY, CURRY_AUDIT, INSULT, INSULT_AUDIT, GAP28_AUDIT, GAP28_SAVE, GAP28_COALITION, GAP28_STOP, GAP27_SAVE, ROOT / "bridge/diplomacy_research_capabilities.py")}
    return {"schema_version": 1, "purpose": "user_required_no_repeat_test_policy",
            "game_version": "1.37.5", "formal_capabilities_promoted": False,
            "policy": "Skip an action after any historical successful selected-state observation; changing sender/version/country is not an exception. One final integration run only after all actions are complete.",
            "source_pins": pins, "aliases": ALIASES, "blocked_count": len(blocked), "blocked_actions": dict(sorted(blocked.items()))}, ids


def plan(requested=None):
    ledger, ids = success_ledger()
    requested = sorted(ids) if requested is None else requested
    requested = [ALIASES.get(x, x) for x in requested]
    if len(set(requested)) != len(requested) or set(requested) - ids:
        raise ValueError("unknown or duplicated action ID")
    blocked = ledger["blocked_actions"]
    return {"phase": "gap_only", "game_accessed": False,
            "skipped_successful": [x for x in requested if x in blocked],
            "unverified_candidates": [x for x in requested if x not in blocked],
            "preconditions_and_fixture_required": True, "requests_published": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("actions", nargs="*")
    parser.add_argument("--write-ledger", type=Path)
    args = parser.parse_args()
    if args.write_ledger:
        ledger, _ = success_ledger()
        args.write_ledger.parent.mkdir(parents=True, exist_ok=True)
        args.write_ledger.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(plan(args.actions or None), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
