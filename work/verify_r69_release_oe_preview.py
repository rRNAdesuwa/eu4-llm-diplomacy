#!/usr/bin/env python3
"""Independently verify R69 Release Nation OE preview rows against an EU4 save.

The query report is treated as evidence only.  For every applied
``release_nation`` case this verifier obtains source/target tags from the
request parameters, then reuses the bounded R66 province scanner.  The scanner
reads the save line by line and retains only provinces owned by those tags;
the expected lost set is derived independently as ``owner == source`` and
``target in cores``.  Native province lists are never used to decide what to
scan, so a missing province cannot hide a native list error.

The verifier does not hash or rewrite the save, does not load the complete
gamestate, and records discovery/negative/unapplied cases as skipped reasons.
The output path is write-once.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from work.verify_r66_overextension_save import scan_save as bounded_scan_save


RELEASE_ACTION = "release_nation"
TAG_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,5}$")
MAX_PUBLIC_BYTES = 4 * 1024 * 1024


def _canonical_tag(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] == '"':
        text = text[1:-1]
    text = text.upper()
    return text if TAG_RE.fullmatch(text) else None


def _int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not decimal.is_finite() or decimal != decimal.to_integral_value():
        return None
    try:
        return int(decimal)
    except (OverflowError, ValueError):
        return None


def _resolve_path(raw: Any, base: Path) -> Path | None:
    if not raw:
        return None
    candidate = Path(str(raw)).expanduser()
    options = [candidate]
    if not candidate.is_absolute():
        options.append(base / candidate)
    for option in options:
        try:
            resolved = option.resolve()
        except OSError:
            continue
        if resolved.is_file():
            return resolved
    return None


def _public_overextension(
    case: dict[str, Any], report_path: Path
) -> tuple[dict[str, Any] | None, str | None]:
    direct = case.get("overextension")
    if isinstance(direct, dict):
        return direct, None
    public_path = _resolve_path(case.get("public_path"), report_path.parent)
    if public_path is None:
        return None, "public_path_missing"
    try:
        if public_path.stat().st_size > MAX_PUBLIC_BYTES:
            return None, "public_path_over_4_mib"
        public = json.loads(public_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, "public_path_unreadable"
    consequences = public.get("peace_consequences")
    overextension = consequences.get("overextension") if isinstance(consequences, dict) else None
    return (
        overextension if isinstance(overextension, dict) else None,
        None if isinstance(overextension, dict) else "overextension_missing",
    )


def _release_terms(case: dict[str, Any]) -> list[dict[str, str | None]]:
    parameters = case.get("parameters")
    context = parameters.get("peace_context") if isinstance(parameters, dict) else None
    terms = context.get("terms") if isinstance(context, dict) else None
    found: list[dict[str, str | None]] = []
    if isinstance(terms, list):
        for term in terms:
            if not isinstance(term, dict) or term.get("action_id") != RELEASE_ACTION:
                continue
            found.append(
                {
                    "source": _canonical_tag(term.get("source")),
                    "target": _canonical_tag(term.get("country")),
                }
            )

    # Keep the verifier useful if a future query report carries only the
    # normalized native request.  This fallback is still gated by the case's
    # action id and selection flag; discovery rows remain unselected.
    if not found and case.get("action_id") == RELEASE_ACTION:
        native = case.get("native")
        if isinstance(native, dict) and native.get("selection_applied") is True:
            target = _canonical_tag(native.get("requested_country"))
            source = _canonical_tag(native.get("requested_source"))
            if target or source:
                found.append({"source": source, "target": target})
    return found


def _load_query_reports(paths: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cases: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    for path in paths:
        path = path.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"QUERY_REPORT_NOT_FOUND:{path}")
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"QUERY_REPORT_UNREADABLE:{path}:{exc}") from exc
        if not isinstance(report, dict):
            raise ValueError(f"QUERY_REPORT_NOT_OBJECT:{path}")
        raw_cases = report.get("cases")
        if not isinstance(raw_cases, list):
            raw_cases = [report]
        report_meta = {
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "status": report.get("status"),
            "schema": report.get("schema"),
            "case_count": len(raw_cases),
        }
        reports.append(report_meta)
        for raw_case in raw_cases:
            if isinstance(raw_case, dict):
                cases.append({"case": raw_case, "report_path": path})
    return cases, reports


def _query_ids(row: Any, key: str) -> tuple[list[int] | None, bool]:
    if not isinstance(row, dict):
        return None, False
    values = row.get(key)
    if not isinstance(values, list):
        return None, False
    result: list[int] = []
    valid = True
    for value in values:
        number = _int(value)
        if number is None or number < 0:
            valid = False
            continue
        result.append(number)
    return result, valid


def _country_rows(overextension: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], bool]:
    raw_rows = overextension.get("countries")
    if not isinstance(raw_rows, list):
        return {}, False
    rows: dict[str, list[dict[str, Any]]] = {}
    for raw_row in raw_rows:
        if not isinstance(raw_row, dict):
            continue
        country = _canonical_tag(raw_row.get("country"))
        if country is None:
            continue
        rows.setdefault(country, []).append(raw_row)
    return rows, True


def _oe_relations(overextension: dict[str, Any]) -> dict[str, Any]:
    rows = overextension.get("countries")
    if not isinstance(rows, list):
        return {"rows": [], "all_passed": False, "reason": "countries_missing"}
    checks: list[dict[str, Any]] = []
    for raw_row in rows:
        if not isinstance(raw_row, dict):
            continue
        country = _canonical_tag(raw_row.get("country"))
        current = _int(raw_row.get("current_raw"))
        gained = _int(raw_row.get("gained_raw"))
        lost = _int(raw_row.get("lost_raw"))
        delta = _int(raw_row.get("delta_raw"))
        projected = _int(raw_row.get("projected_raw"))
        current_relation = (
            None
            if None in {current, delta, projected}
            else current + delta == projected
        )
        net_relation = (
            None
            if None in {gained, lost, delta}
            else gained - lost == delta
        )
        checks.append(
            {
                "country": country,
                "current_raw": current,
                "gained_raw": gained,
                "lost_raw": lost,
                "delta_raw": delta,
                "projected_raw": projected,
                "current_plus_delta_equals_projected": current_relation,
                "gained_minus_lost_equals_delta": net_relation,
            }
        )
    all_passed = bool(checks) and all(
        item["current_plus_delta_equals_projected"] is True
        and item["gained_minus_lost_equals_delta"] is True
        for item in checks
    )
    return {"rows": checks, "all_passed": all_passed}


def _scan_is_complete(scan: dict[str, Any]) -> bool:
    checks = scan.get("checks") if isinstance(scan, dict) else None
    details = scan.get("scan") if isinstance(scan, dict) else None
    if not isinstance(checks, dict) or not isinstance(details, dict):
        return False
    return bool(
        checks.get("source_exists")
        and checks.get("provinces_block_found")
        and checks.get("provinces_block_complete")
        and checks.get("brace_balance_ok")
        and checks.get("per_block_cap_4_mib")
        and checks.get("streaming_only")
        and details.get("parse_failures", 0) == 0
        and not details.get("duplicate_province_ids")
        and not details.get("unknown")
    )


def _expected_lost_ids(
    scan: dict[str, Any], source: str, target: str
) -> tuple[list[int], int]:
    records = scan.get("provinces")
    if not isinstance(records, dict):
        return [], 0
    expected: list[int] = []
    source_owned = 0
    for key, record in records.items():
        if not isinstance(record, dict):
            continue
        province_id = _int(record.get("province_id", key))
        owner = _canonical_tag(record.get("owner"))
        if province_id is None or owner != source:
            continue
        source_owned += 1
        cores = {
            tag
            for tag in (_canonical_tag(item) for item in (record.get("cores") or []))
            if tag is not None
        }
        if target in cores:
            expected.append(province_id)
    return sorted(set(expected)), source_owned


def _base_case_row(
    case: dict[str, Any], report_path: Path, overextension: dict[str, Any] | None
) -> dict[str, Any]:
    return {
        "name": case.get("name"),
        "action_id": case.get("action_id"),
        "parameters": case.get("parameters"),
        "overextension": overextension,
        "public_path": case.get("public_path"),
        "query_report_path": str(report_path),
    }


def _compare_release_case(
    case: dict[str, Any],
    report_path: Path,
    overextension: dict[str, Any],
    scan: dict[str, Any],
    terms: list[dict[str, str | None]],
) -> dict[str, Any]:
    output = _base_case_row(case, report_path, overextension)
    output["selected_release_nation"] = terms
    output["skip_reason"] = None
    output["comparisons"] = []
    query_rows, rows_readable = _country_rows(overextension)
    scan_complete = _scan_is_complete(scan)

    for term in terms:
        source = term.get("source")
        target = term.get("target")
        comparison: dict[str, Any] = {
            "source": source,
            "target": target,
            "expected_lost_province_ids": [],
            "expected_gained_province_ids": [],
            "query_lost_province_ids": None,
            "query_gained_province_ids": None,
            "source_owned_records_scanned": 0,
            "checks": {},
            "oe_relations": _oe_relations(overextension),
            "reasons": [],
        }
        if source is None or target is None or source == target:
            comparison["reasons"].append("invalid_source_or_target_tag")
            output["comparisons"].append(comparison)
            continue

        expected, source_owned = _expected_lost_ids(scan, source, target)
        comparison["expected_lost_province_ids"] = expected
        comparison["expected_gained_province_ids"] = expected
        comparison["source_owned_records_scanned"] = source_owned

        source_rows = query_rows.get(source, [])
        target_rows = query_rows.get(target, [])
        source_row = source_rows[0] if len(source_rows) == 1 else None
        target_row = target_rows[0] if len(target_rows) == 1 else None
        native_lost, lost_values_valid = _query_ids(source_row, "lost_province_ids")
        native_gained, gained_values_valid = _query_ids(target_row, "gained_province_ids")
        comparison["query_lost_province_ids"] = native_lost
        comparison["query_gained_province_ids"] = native_gained
        comparison["query_source_row"] = source_row
        comparison["query_target_row"] = target_row

        duplicate_lost = native_lost is not None and len(native_lost) != len(set(native_lost))
        duplicate_gained = native_gained is not None and len(native_gained) != len(set(native_gained))
        over_complete = overextension.get("complete") is True
        unsupported = overextension.get("unsupported_territorial_terms") is True
        source_complete = source_row is not None and source_row.get("complete") is True
        target_complete = target_row is not None and target_row.get("complete") is True
        lost_exact = native_lost is not None and sorted(native_lost) == expected
        gained_exact = native_gained is not None and sorted(native_gained) == expected
        relation_passed = comparison["oe_relations"].get("all_passed") is True
        comparison["checks"] = {
            "save_scan_stream_complete": scan_complete,
            "query_countries_readable": rows_readable,
            "query_overextension_complete": over_complete,
            "query_overextension_not_unsupported": not unsupported,
            "source_country_row_unique": len(source_rows) == 1,
            "target_country_row_unique": len(target_rows) == 1,
            "source_country_row_complete": source_complete,
            "target_country_row_complete": target_complete,
            "query_lost_ids_valid": lost_values_valid,
            "query_gained_ids_valid": gained_values_valid,
            "query_lost_ids_unique": not duplicate_lost,
            "query_gained_ids_unique": not duplicate_gained,
            "lost_ids_exact": lost_exact,
            "gained_ids_exact": gained_exact,
            "oe_internal_relations_passed": relation_passed,
        }
        if not scan_complete:
            comparison["reasons"].append("save_scan_incomplete")
        if not rows_readable:
            comparison["reasons"].append("query_countries_missing")
        if not over_complete:
            comparison["reasons"].append("query_overextension_incomplete")
        if unsupported:
            comparison["reasons"].append("query_overextension_unsupported")
        if len(source_rows) != 1:
            comparison["reasons"].append("source_country_row_not_unique")
        if len(target_rows) != 1:
            comparison["reasons"].append("target_country_row_not_unique")
        if duplicate_lost or duplicate_gained:
            comparison["reasons"].append("duplicate_query_province_ids")
        if not lost_exact:
            comparison["reasons"].append("lost_ids_mismatch")
        if not gained_exact:
            comparison["reasons"].append("gained_ids_mismatch")
        if not relation_passed:
            comparison["reasons"].append("oe_internal_relation_mismatch")
        comparison["reasons"] = sorted(set(comparison["reasons"]))

        difference_keys = {
            "lost_ids_exact",
            "gained_ids_exact",
            "query_lost_ids_unique",
            "query_gained_ids_unique",
        }
        if any(comparison["checks"].get(key) is False for key in difference_keys):
            comparison["status"] = "difference"
        elif not all(value is True for value in comparison["checks"].values()):
            comparison["status"] = "incomplete"
        else:
            comparison["status"] = "passed"
        output["comparisons"].append(comparison)

    statuses = [item.get("status") for item in output["comparisons"]]
    if any(status == "difference" for status in statuses):
        output["status"] = "difference"
    elif any(status == "incomplete" for status in statuses):
        output["status"] = "incomplete"
    elif statuses and all(status == "passed" for status in statuses):
        output["status"] = "passed"
    else:
        output["status"] = "incomplete"
    return output


def _skip_case(
    case: dict[str, Any], report_path: Path, overextension: dict[str, Any] | None,
    reason: str, terms: list[dict[str, str | None]], detail: str | None = None,
) -> dict[str, Any]:
    output = _base_case_row(case, report_path, overextension)
    output.update(
        {
            "selected_release_nation": terms,
            "status": "skipped",
            "skip_reason": reason,
            "skip_detail": detail,
            "comparisons": [],
        }
    )
    return output


def _pic_bur_check(case_rows: list[dict[str, Any]]) -> dict[str, Any]:
    relevant: list[dict[str, Any]] = []
    for case_row in case_rows:
        if case_row.get("status") == "skipped":
            continue
        for comparison in case_row.get("comparisons", []):
            if comparison.get("source") == "BUR" and comparison.get("target") == "PIC":
                relevant.append(
                    {
                        "case": case_row.get("name"),
                        "comparison": comparison,
                    }
                )
    if not relevant:
        return {
            "status": "unavailable",
            "reason": "release_PIC_source_BUR_case_not_applied",
            "cases": [],
        }

    checks: list[dict[str, Any]] = []
    for item in relevant:
        comparison = item["comparison"]
        source_row = comparison.get("query_source_row") or {}
        target_row = comparison.get("query_target_row") or {}
        current = _int(source_row.get("current_raw"))
        projected = _int(source_row.get("projected_raw"))
        lost_raw = _int(source_row.get("lost_raw"))
        delta = _int(source_row.get("delta_raw"))
        gained_raw = _int(target_row.get("gained_raw"))
        query_lost = comparison.get("query_lost_province_ids") or []
        query_gained = comparison.get("query_gained_province_ids") or []
        expected = comparison.get("expected_lost_province_ids") or []
        case_checks = {
            "bur_current_raw_120": current == 120,
            "bur_projected_raw_0": projected == 0,
            "bur_lost_raw_nonzero": lost_raw is not None and lost_raw > 0,
            "bur_delta_negative": delta is not None and delta < 0,
            "pic_core_provinces_add_zero_oe": gained_raw == 0,
            "province_88_in_independent_expected_set": 88 in expected,
            "province_88_in_query_lost": 88 in query_lost,
            "province_88_in_query_gained": 88 in query_gained,
        }
        checks.append(
            {
                "case": item["case"],
                "checks": case_checks,
                "all_passed": all(case_checks.values()),
            }
        )
    return {
        "status": "passed" if all(item["all_passed"] for item in checks) else "failed",
        "cases": checks,
    }


def build_report(save_path: Path, query_paths: list[Path]) -> dict[str, Any]:
    query_cases, query_reports = _load_query_reports(query_paths)
    selected_tags: set[str] = set()
    parsed_cases: list[dict[str, Any]] = []
    for item in query_cases:
        case = item["case"]
        terms = _release_terms(case)
        for term in terms:
            if term.get("source"):
                selected_tags.add(str(term["source"]))
            if term.get("target"):
                selected_tags.add(str(term["target"]))
        parsed_cases.append({**item, "release_terms": terms})

    if not save_path.is_file():
        raise FileNotFoundError(f"SAVE_NOT_FOUND:{save_path}")
    # Only source/target tags are passed to the reused bounded scanner.  Native
    # province lists and the special case 88 never influence retention.
    save_scan = bounded_scan_save(save_path, selected_tags, set(), None)

    case_rows: list[dict[str, Any]] = []
    for item in parsed_cases:
        case = item["case"]
        report_path = item["report_path"]
        terms = item["release_terms"]
        overextension, over_reason = _public_overextension(case, report_path)
        if case.get("action_id") != RELEASE_ACTION:
            case_rows.append(
                _skip_case(case, report_path, overextension, "action_not_release_nation", terms)
            )
            continue
        if not terms:
            case_rows.append(
                _skip_case(case, report_path, overextension, "no_selected_release_nation_term", terms)
            )
            continue
        if case.get("requested_terms_applied") is not True:
            case_rows.append(
                _skip_case(
                    case,
                    report_path,
                    overextension,
                    "requested_terms_not_applied",
                    terms,
                    detail=str(case.get("requested_terms_applied")),
                )
            )
            continue
        if overextension is None:
            case_rows.append(
                _skip_case(
                    case,
                    report_path,
                    overextension,
                    over_reason or "overextension_missing",
                    terms,
                )
            )
            continue
        case_rows.append(
            _compare_release_case(case, report_path, overextension, save_scan, terms)
        )

    applicable = [item for item in case_rows if item.get("status") != "skipped"]
    passed = sum(item.get("status") == "passed" for item in applicable)
    differences = sum(item.get("status") == "difference" for item in applicable)
    incomplete = sum(item.get("status") == "incomplete" for item in applicable)
    pic_bur = _pic_bur_check(case_rows)
    save_source = save_scan.get("source") if isinstance(save_scan, dict) else {}
    save_checks = save_scan.get("checks") if isinstance(save_scan, dict) else {}
    save_details = save_scan.get("scan") if isinstance(save_scan, dict) else {}
    scan_summary = {
        "checks": save_checks,
        "scan": save_details,
        "source": save_source,
        "retained_province_ids": sorted(
            _int(key) for key in (save_scan.get("provinces") or {}).keys()
            if _int(key) is not None
        ),
        "retained_province_count": len(save_scan.get("provinces") or {}),
        "retention_rule": "owner in selected source/target tags; target_ids passed empty",
    }
    scan_complete = _scan_is_complete(save_scan)
    top_checks = {
        "query_reports_read": bool(query_reports)
        and all(item.get("status") != "missing" for item in query_reports),
        "query_cases_present": bool(query_cases),
        "save_provinces_stream_complete": scan_complete,
        "save_scanner_streaming_only": bool(save_checks.get("streaming_only")),
        "save_hash_not_recomputed": save_source.get("sha256_recomputed") is False,
        "native_province_lists_not_used_for_scan": True,
        "applicable_release_case_present": bool(applicable),
        "all_applicable_release_cases_verified": bool(applicable) and not differences and not incomplete,
        "release_PIC_BUR_12pp_to_zero": pic_bur.get("status") == "passed",
        "no_full_gamestate_load": True,
        "no_game_operation": True,
    }
    if differences:
        status = "differences"
    elif incomplete or not applicable or pic_bur.get("status") != "passed":
        status = "incomplete"
    elif all(top_checks.values()):
        status = "passed"
    else:
        status = "incomplete"
    return {
        "schema": "r69_release_oe_preview_verification_v1",
        "status": status,
        "save": {"path": str(save_path), "scan": scan_summary},
        "queries": {"reports": query_reports, "case_count": len(query_cases)},
        "cases": case_rows,
        "counts": {
            "cases_total": len(case_rows),
            "cases_skipped": len(case_rows) - len(applicable),
            "cases_applicable": len(applicable),
            "cases_passed": passed,
            "cases_differences": differences,
            "cases_incomplete": incomplete,
        },
        "pic_bur_check": pic_bur,
        "checks": top_checks,
        "limitations": [
            "Save-side expected IDs use only direct province owner and cores fields; native candidate lists are not used.",
            "Skipped discovery or unapplied requests are recorded and do not count as verified coverage.",
            "OE numeric equality is checked from query raw fields; this verifier does not infer a missing modifier or development value.",
        ],
    }


def _output_file(raw: Path) -> Path:
    raw = raw.expanduser().resolve()
    if raw.suffix.lower() == ".json":
        return raw
    return raw / "report.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, action="append", nargs="+", required=True)
    parser.add_argument("--save", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    output = _output_file(args.output)
    if output.exists():
        raise FileExistsError(f"REFUSE_OVERWRITE_OUTPUT:{output}")
    query_paths = [path.expanduser().resolve() for group in args.queries for path in group]
    save_path = args.save.expanduser().resolve()
    report = build_report(save_path, query_paths)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "output": str(output),
                "counts": report["counts"],
                "pic_bur_check": report["pic_bur_check"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
