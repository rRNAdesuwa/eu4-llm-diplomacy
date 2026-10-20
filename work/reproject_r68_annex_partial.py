"""Reproject retained R68 peace-family raw events; never access the game."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomat_availability import (
    apply_diplomat_legality,
    project_native_diplomat_context,
)
from bridge.diplomacy import DiplomacyTools
from bridge.native_text import EU4_ESCAPE_CODEC
from bridge.peace_consequences import (
    project_event_consequences,
    validate_native_consequences,
)
from work import run_peace_consequence_family_queries as family


def _read(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def _public_projection(raw: dict, parameters: dict) -> dict | None:
    """Use the production semantic projector and attach the native resource."""
    public = family._recover_public_projection(
        raw, parameters, EU4_ESCAPE_CODEC)
    if not isinstance(public, dict):
        return None
    context = project_native_diplomat_context(raw)
    if context is not None:
        public.setdefault("resources", {})["diplomats"] = context
        apply_diplomat_legality(public)
    # ``peace_context`` is the caller-facing proposal.  The semantic
    # projector's terms describe the native copy and may contain normalized
    # fields (or be empty for an unmatched request); keep that distinction in
    # ``parameters.actual`` while preserving the public request contract.
    requested_context = parameters.get("peace_context")
    if isinstance(requested_context, dict):
        public_context = dict(requested_context)
        public_context["complete"] = (
            isinstance(public.get("parameters"), dict)
            and public["parameters"].get("complete") is True)
        public["peace_context"] = public_context
    return public


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
                        help="existing R68 report.json")
    parser.add_argument("--output", type=Path, required=True,
                        help="new report.json; its directory must not exist")
    args = parser.parse_args(argv)

    source_report_path = args.source.resolve(strict=True)
    output_report_path = args.output.resolve()
    if output_report_path.exists() or output_report_path.parent.exists():
        raise RuntimeError("REFUSE_OVERWRITE_OR_REUSE_OUTPUT")
    source_report = _read(source_report_path)
    if not isinstance(source_report, dict):
        raise RuntimeError("SOURCE_REPORT_NOT_OBJECT")
    source_root = source_report_path.parent
    output_root = output_report_path.parent
    output_root.mkdir(parents=True, exist_ok=False)
    evidence_root = output_root / "report-evidence"
    evidence_root.mkdir()

    report = copy.deepcopy(source_report)
    report.update({
        "mode": "offline_reproject_r68_retained_native_family_events",
        "source_report": str(source_report_path),
        "source_status": source_report.get("status"),
        "live_query_replayed": False,
        "runtime_query_call_count": source_report.get("query_call_count", 0),
        "query_call_count": 0,
    })
    cases = []
    source_public_missing = []
    for prior in source_report.get("cases", []):
        if not isinstance(prior, dict):
            raise RuntimeError("CASE_NOT_OBJECT")
        name = prior["name"]
        source_native_path = Path(prior["native_event_path"])
        source_input_path = source_native_path.parent / "input.json"
        source_public_path = Path(prior["public_path"])
        raw = _read(source_native_path)
        request = _read(source_input_path)
        old_public = _read(source_public_path)
        if not isinstance(raw, dict) or not isinstance(request, dict):
            raise RuntimeError("CASE_RAW_OR_INPUT_INVALID:" + name)
        parameters = request["parameters"]
        context = parameters["peace_context"]
        action = prior["action_id"]
        ids = request.get("expected_province_ids") or None
        beneficiary = request.get("expected_beneficiary")
        expected = family._selection_for_parameters(
            action, source_report["war_id"], "demand", source_report["recipient"],
            parameters, province_ids=ids, beneficiary=beneficiary)
        native_valid = family._native_valid(
            raw, action, source_report["actor"], source_report["recipient"],
            "demand", source_report["war_id"], raw["date_raw"],
            source_report["session"]["session_id"], ids, beneficiary, expected)
        native_consequences = raw.get("native_consequences")
        consequence_contract = validate_native_consequences(native_consequences)
        projected = (project_event_consequences(raw, EU4_ESCAPE_CODEC)
                     if consequence_contract else None)
        public = _public_projection(raw, parameters)
        if public is None:
            raise RuntimeError("PUBLIC_PROJECTION_FAILED:" + name)
        public_path = evidence_root / "cases" / name / "public.json"
        native_path = evidence_root / "cases" / name / "native-event.json"
        input_path = evidence_root / "cases" / name / "input.json"
        _write(native_path, raw)
        _write(input_path, request)
        _write(public_path, public)

        public_nc = public.get("peace_consequences")
        parity = (projected == public_nc
                  if consequence_contract and isinstance(public_nc, dict)
                  else None)
        native_object = raw.get("object_unchanged") \
            if isinstance(raw.get("object_unchanged"), bool) else None
        public_object = public.get("object_unchanged") \
            if isinstance(public.get("object_unchanged"), bool) else None
        source_public_object = old_public.get("object_unchanged") \
            if isinstance(old_public, dict) and isinstance(
                old_public.get("object_unchanged"), bool) else None
        if source_public_object is None:
            source_public_missing.append(name)
        unchanged = (native_object is True and public_object is True)
        private_absent = not family._has_private_fields(public)
        header = family._raw_header_contract(
            raw, action_id=action, actor=source_report["actor"],
            recipient=source_report["recipient"], direction="demand",
            war_id=source_report["war_id"],
            expected_date=source_report["before"]["health"]["date_raw"],
            session_id=source_report["session"]["session_id"])
        public_contract = family._public_base(
            public, action, source_report["actor"], source_report["recipient"],
            source_report["war_id"], "demand", context["terms"])
        native_state = family._native_parameter_state(action, raw)
        native_public_parity = all(value is True for value in (
            header, native_valid, consequence_contract, parity, unchanged,
            public_contract, private_absent))
        if native_public_parity:
            availability = ("unavailable" if native_state is False
                            else "available")
        else:
            availability = "invalid"
        not_applied = False
        if name == "cede_province_88_ORL":
            native_provinces = raw.get("native_provinces")
            selected_ids = (native_provinces.get("selected_province_ids", [])
                            if isinstance(native_provinces, dict) else None)
            parameters_matched = (native_provinces.get("parameters_matched")
                                  if isinstance(native_provinces, dict) else None)
            not_applied = (
                parameters_matched is False and selected_ids == []
                and family._empty_consequence_projection(public_nc))
            if not_applied:
                availability = "unavailable"
        row = copy.deepcopy(prior)
        row.update({
            "public_path": str(public_path),
            "source_public_path": str(source_public_path),
            "native_event_path": str(native_path),
            "source_native_event_path": str(source_native_path),
            "public_projection_recovered": True,
            "validator_normalization": None,
            "native_validator": native_valid,
            "consequence_contract": consequence_contract,
            "raw_header_contract": header,
            "public_contract": public_contract,
            "raw_public_parity": parity,
            "native_object_unchanged": native_object,
            "source_public_object_unchanged": source_public_object,
            "public_object_unchanged": public_object,
            "object_unchanged": unchanged,
            "private_fields_absent": private_absent,
            "native_public_parity": native_public_parity,
            "requested_terms_applied": (
                projected.get("requested_terms_applied")
                if isinstance(projected, dict) else None),
            "consequence_reason_code": (
                projected.get("reason_code") if isinstance(projected, dict)
                else None),
            "availability": availability,
            "legality_status": public.get("legality", {}).get(
                "status", "unknown") if isinstance(public.get("legality"), dict)
                else "unknown",
            "not_applied": not_applied,
        })
        cases.append(row)

    report["cases"] = cases
    required = [row for row in cases if not row.get("optional")]
    availability = {
        state: [row["name"] for row in cases if row["availability"] == state]
        for state in ("available", "unavailable", "unknown", "invalid")
    }
    report["availability"] = availability
    checks = report.setdefault("checks", {})
    checks["all_required_native_public_parity"] = all(
        row["native_public_parity"] for row in required)
    checks["no_required_unknown_or_invalid"] = all(
        row["availability"] not in ("unknown", "invalid") for row in required)
    checks["public_results_no_private_fields"] = all(
        row["private_fields_absent"] for row in cases)
    report["required_checks"] = {
        key: checks[key] for key in report.get("required_checks", {})
    }
    parity_count = sum(row["native_public_parity"] for row in required)
    report["required_cases_with_native_public_parity"] = parity_count
    report["api_projection_recovery_cases"] = [row["name"] for row in cases]
    coverage = report.setdefault("coverage", {})
    coverage.update({
        "availability": availability,
        "unknown_or_invalid_cases": (
            availability["unknown"] + availability["invalid"]),
        "required_cases_with_native_public_parity": parity_count,
        "optional_cases": [{key: row.get(key) for key in (
            "name", "action_id", "availability", "native_parameter_state",
            "native_public_parity", "not_applied")} for row in cases
            if row.get("optional")],
    })
    report["object_unchanged_provenance"] = {
        "native_true_cases": [row["name"] for row in cases
                              if row.get("native_object_unchanged") is True],
        "source_public_missing_cases": source_public_missing,
        "reprojected_public_true_cases": [row["name"] for row in cases
                                           if row.get(
                                               "public_object_unchanged") is True],
    }
    report["status_reason"] = {
        "available_cases": availability["available"],
        "unavailable_cases": availability["unavailable"],
        "unknown_cases": availability["unknown"],
        "invalid_cases": availability["invalid"],
    }
    report["status"] = (
        "passed" if all(report["required_checks"].values())
        and all(row["native_public_parity"] for row in cases)
        else "failed")
    _write(output_report_path, report)
    print(json.dumps({
        "status": report["status"],
        "required_parity": parity_count,
        "required_count": len(required),
        "source_public_object_unchanged_missing": source_public_missing,
        "report": str(output_report_path),
    }, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
