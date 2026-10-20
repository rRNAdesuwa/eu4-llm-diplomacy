"""Revalidate retained R65 family events after Python fixes; no game access."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools
from bridge.native_text import EU4_ESCAPE_CODEC
from bridge.peace_consequences import project_event_consequences, validate_native_consequences
from work import run_peace_consequence_family_queries as family


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    report = json.loads(source.read_text(encoding="utf-8"))
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=False)
    evidence = output.parent / "report-evidence"
    evidence.mkdir()
    report.update(mode="offline_reproject_retained_native_family_events",
                  source_report=str(source), source_status=report["status"],
                  live_query_replayed=False, runtime_query_call_count=report["query_call_count"],
                  query_call_count=0)
    cases = []
    for prior in report["cases"]:
        row = copy.deepcopy(prior)
        raw_path = Path(row["native_event_path"])
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        request = json.loads((raw_path.parent / "input.json").read_text(encoding="utf-8"))
        parameters = request["parameters"]
        context = parameters["peace_context"]
        action = row["action_id"]
        ids = request["expected_province_ids"] or None
        beneficiary = request["expected_beneficiary"]
        expected = family._selection_for_parameters(
            action, report["war_id"], "demand", report["recipient"], parameters,
            province_ids=ids, beneficiary=beneficiary)
        # Validate the unchanged producer record, including optional fields,
        # through the fixed production validator. No normalization is needed.
        native_valid = family._native_valid(
            raw, action, report["actor"], report["recipient"], "demand",
            report["war_id"], raw["date_raw"], report["session"]["session_id"],
            ids, beneficiary, expected)
        projector = family._semantic_projector(raw["event"])
        semantic = projector(raw, EU4_ESCAPE_CODEC)
        public = json.loads(Path(prior["public_path"]).read_text(encoding="utf-8"))
        public = DiplomacyTools._apply_peace_execution_inspection(public, semantic, parameters)
        public = family._strip_public_private(public)
        path = evidence / f'{row["name"]}.json'
        family._write(path, public)
        contract = family._public_base(public, action, report["actor"],
                                      report["recipient"], report["war_id"],
                                      "demand", context["terms"])
        projected = project_event_consequences(raw, EU4_ESCAPE_CODEC)
        native_contract = validate_native_consequences(raw.get("native_consequences"))
        parity = projected == public.get("peace_consequences")
        unchanged = raw.get("object_unchanged") is True and public.get("object_unchanged") is True
        private_absent = not family._has_private_fields(public)
        header = family._raw_header_contract(
            raw, action_id=action, actor=report["actor"], recipient=report["recipient"],
            direction="demand", war_id=report["war_id"],
            expected_date=report["before"]["health"]["date_raw"],
            session_id=report["session"]["session_id"])
        ok = all(value is True for value in (
            header, native_valid, native_contract, parity, unchanged, contract, private_absent))
        applied = projected.get("requested_terms_applied") if projected else None
        row.update(public_path=str(path), source_public_path=prior["public_path"],
                   public_projection_recovered=True, validator_normalization=None,
                   native_validator=native_valid, consequence_contract=native_contract,
                   raw_header_contract=header, public_contract=contract,
                   raw_public_parity=parity, object_unchanged=unchanged,
                   private_fields_absent=private_absent, native_public_parity=ok,
                   requested_terms_applied=applied,
                   consequence_reason_code=projected.get("reason_code") if projected else None,
                   availability=("invalid" if not ok else "unavailable" if applied is False
                                 or row["native_parameter_state"] is False else "available"),
                   legality_status=public.get("legality", {}).get("status", "unknown"))
        cases.append(row)
    report["cases"] = cases
    required = [row for row in cases if not row.get("optional")]
    report["availability"] = {
        state: [row["name"] for row in cases if row["availability"] == state]
        for state in ("available", "unavailable", "unknown", "invalid")}
    checks = report["checks"]
    checks["all_required_native_public_parity"] = all(row["native_public_parity"] for row in required)
    checks["no_required_unknown_or_invalid"] = all(row["availability"] not in ("unknown", "invalid") for row in required)
    checks["public_results_no_private_fields"] = all(row["private_fields_absent"] for row in cases)
    report["required_checks"] = {key: checks[key] for key in report["required_checks"]}
    count = sum(row["native_public_parity"] for row in required)
    report["required_cases_with_native_public_parity"] = count
    report["api_projection_recovery_cases"] = [row["name"] for row in cases]
    report["coverage"].update(required_cases_with_native_public_parity=count,
        availability=report["availability"], unknown_or_invalid_cases=(
            report["availability"]["unknown"] + report["availability"]["invalid"]),
        optional_cases=[{key: row.get(key) for key in (
            "name", "action_id", "availability", "native_parameter_state",
            "native_public_parity", "not_applied")} for row in cases if row.get("optional")])
    report["status_reason"] = dict(report["availability"])
    report["status"] = "passed" if all(report["required_checks"].values()) and all(
        row["native_public_parity"] for row in cases) else "failed"
    family._write(output, report)
    print(json.dumps({"status":report["status"], "required_parity":count,
                      "required_count":len(required), "report":str(output)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
