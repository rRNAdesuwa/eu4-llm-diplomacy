"""Reproject saved Annul query events without contacting the running game."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.peace_execution import normalize_peace_execution_parameters
from work.run_peace_empty_offer_queries import _has_private_fields


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    original = args.original.resolve()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=False)
    prior = json.loads(original.read_text(encoding="utf-8"))
    evidence = original.parent / "report-evidence"
    raw = (evidence / "native-events-slice.jsonl").read_bytes()
    native = [event for line in raw.splitlines() if line.strip()
              for event in [json.loads(line)]
              if event.get("event") == "native_peace_annul_treaties_offer_inspection"
              and event.get("session_id") == prior["session_id"]]
    assert len(native) == len(prior["cases"]) == 9
    report = {"status": "unknown", "original_report": str(original),
              "original_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
              "native_slice_sha256": hashlib.sha256(raw).hexdigest(),
              "mode": "offline_reprojection", "game_contact": False,
              "execute_call_count": 0, "cases": []}
    for case, event in zip(prior["cases"], native):
        name = case["name"]
        spec = json.loads((evidence / (name + "-input.json")).read_text(encoding="utf-8"))
        public = json.loads((evidence / (name + ".json")).read_text(encoding="utf-8"))
        expected = "unknown"
        selection = event["native_annul_treaties"]
        if spec["parameters"]["peace_context"]["terms"]:
            parameters = normalize_peace_execution_parameters(
                spec["action_id"], "FRA", "ENG", "initiate", spec["parameters"])
            semantic = ObserverSession._semantic_peace_annul_treaties_offer_inspection(
                event, "eu4_escape")
            public = DiplomacyTools._apply_peace_execution_inspection(
                copy.deepcopy(public), semantic, parameters)
            if selection.get("parameters_matched") is True:
                expected = "available" if selection["rule_available"] else "unavailable"
        path = output.parent / (name + ".json")
        path.write_text(json.dumps(public, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        actual = public["parameters"].get("actual")
        terms = actual.get("peace_context", {}).get("terms", []) if isinstance(actual, dict) else []
        matched = any(term.get("action_id") == "annul_treaties"
                      and term.get("country") == selection.get("country")
                      and term.get("treaty_partners") == selection.get("treaty_partners")
                      for term in terms)
        report["cases"].append({"name": name, "expected_legality": expected,
            "legality": public["legality"], "parameters_complete": public["parameters"]["complete"],
            "selection_matches": matched if selection.get("parameters_matched") else actual is None,
            "private_fields_absent": not _has_private_fields(public), "public_path": str(path)})
    report["checks"] = {
        "original_native_slice_hash": hashlib.sha256(raw).hexdigest() == prior["native_events"]["sha256"],
        "original_seven_other_checks_passed": all(value for key, value in prior["checks"].items()
                                                if key != "public_selection_matches_native"),
        "all_nine_legalities": all(case["legality"]["status"] == case["expected_legality"]
                                  for case in report["cases"]),
        "all_selections": all(case["selection_matches"] for case in report["cases"]),
        "private_fields_absent": all(case["private_fields_absent"] for case in report["cases"]),
        "multi_partner_complete": all(case["parameters_complete"] for case in report["cases"]
                                      if case["name"] in ("demand-multiple", "offer-multiple")),
    }
    report["status"] = "passed" if all(report["checks"].values()) else "failed"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": report["checks"], "report": str(output)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
