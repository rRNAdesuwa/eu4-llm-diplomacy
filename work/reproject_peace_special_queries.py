"""Project retained H/S/F query events after a display fix; never contact the game."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.peace_execution import normalize_peace_execution_parameters
from work.run_peace_empty_offer_queries import _has_private_fields


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    original, output = args.original.resolve(), args.output.resolve()
    if output.exists():
        raise SystemExit("OUTPUT_ALREADY_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=False)
    prior_bytes = original.read_bytes()
    prior = json.loads(prior_bytes)
    source = Path(prior["native_events"]["path"])
    if source.stat().st_size > 4 * 1024 * 1024:
        raise SystemExit("SOURCE_EVENT_SLICE_TOO_LARGE")
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != prior["native_events"]["sha256"]:
        raise SystemExit("SOURCE_EVENT_SLICE_HASH_MISMATCH")
    native = [event for line in raw.splitlines() if line.strip()
              for event in [json.loads(line)]
              if event.get("event") == "native_peace_special_offer_inspection"
              and event.get("session_id") == prior["session_id"]]
    if len(native) != len(prior["cases"]):
        raise SystemExit("SOURCE_QUERY_COUNT_MISMATCH")
    evidence = original.parent / "report-evidence"
    report = {"mode": "offline_reprojection", "game_contact": False,
              "execute_call_count": 0, "original": str(original),
              "original_sha256": hashlib.sha256(prior_bytes).hexdigest(),
              "native_events_sha256": hashlib.sha256(raw).hexdigest(), "cases": []}
    for case, event in zip(prior["cases"], native):
        spec = json.loads((evidence / (case["name"] + "-input.json")).read_text(encoding="utf-8"))
        public = json.loads((evidence / (case["name"] + ".json")).read_text(encoding="utf-8"))
        parameters = normalize_peace_execution_parameters(
            spec["action_id"], "FRA", "ENG", "initiate", spec["parameters"])
        semantic = ObserverSession._semantic_peace_special_offer_inspection(event, "eu4_escape")
        public = DiplomacyTools._apply_peace_execution_inspection(public, semantic, parameters)
        path = output.parent / (case["name"] + ".json")
        path.write_text(json.dumps(public, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        diagnostic = public.get("diagnostics", {}).get("selected_term_gate", {})
        text = diagnostic.get("text")
        unavailable = public["legality"]["status"] == "unavailable"
        report["cases"].append({"name": case["name"], "public_path": str(path),
            "legality": public["legality"], "diagnostic": diagnostic,
            "status_preserved": public["legality"]["status"] == case["legality"]["status"],
            "native_rule_reason_readable": (not unavailable or (
                diagnostic.get("text_decoded") is True and isinstance(text, str) and bool(text)
                and public["legality"]["reasons"][0]["text"] == text)),
            "private_fields_absent": not _has_private_fields(public)})
    report["checks"] = {"original_runtime_checks_passed": all(prior["checks"].values()),
        "status_preserved": all(row["status_preserved"] for row in report["cases"]),
        "native_rule_reasons_readable": all(row["native_rule_reason_readable"] for row in report["cases"]),
        "private_fields_absent": all(row["private_fields_absent"] for row in report["cases"])}
    report["status"] = "passed" if all(report["checks"].values()) else "failed"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(output)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
