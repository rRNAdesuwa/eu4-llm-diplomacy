#!/usr/bin/env python3
"""Stream-compare the R60 subject-transfer save result with its v2 baseline.

The comparison retains only bounded diplomacy relation blocks, the directed
war-reparations records, and the optional ENG/FRA active-war records.  It does
not hash saves or load a complete gamestate into memory.  Treasury values are
intentionally not used for attribution because the two saves can span months;
money evidence must come from the native immediate-effect record.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from work import inspect_declare_war_save_pair as war_parser
from work import inspect_dissolve_save_pair as bounded
from work import inspect_peace_subject_save as subject_parser
from work import inspect_peace_treaty_save as treaty_parser


PAIR_TARGETS = {"ENG", "FRA", "LEI", "TYR"}
BASELINE_RELATIONS = {
    ("ENG", "TYR"): True,
    ("ENG", "LEI"): True,
    ("FRA", "LEI"): False,
}
FINAL_RELATIONS = {
    ("ENG", "TYR"): False,
    ("ENG", "LEI"): False,
    ("FRA", "LEI"): True,
}


def _resolve(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"{label} is not a file: {resolved}")
    return resolved


def _relation_records(path: Path) -> dict[str, Any]:
    parsed = subject_parser.scan_save(path, PAIR_TARGETS)
    records = parsed["records"]
    by_pair: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        pair = (record.get("first"), record.get("second"))
        pair_key = f"{pair[0]}->{pair[1]}"
        by_pair.setdefault(pair_key, []).append(record)
    return {
        "source": parsed["source"],
        "scan": parsed["scan"],
        "block_type_counts": parsed["block_type_counts"],
        "records": records,
        "by_pair": by_pair,
    }


def _war_reparations(path: Path) -> dict[str, Any]:
    """Use the existing bounded scanner without its optional SHA pass."""

    source = bounded.detect_container(path)
    scanner = treaty_parser.TreatySaveScanner()
    with bounded.open_gamestate(path, source) as stream:
        scanner.consume(stream)
    records = scanner.records
    matching = [
        record
        for record in records
        if record.get("complete")
        and record.get("payer") == "ENG"
        and record.get("claimant") == "FRA"
    ]
    return {
        "source": {
            "path": str(path),
            "name": path.name,
            "size_bytes": path.stat().st_size,
            "container": source.get("container"),
            "gamestate_member": source.get("gamestate_member"),
            "sha256_recomputed": False,
        },
        "metadata": {
            "date": scanner.date,
            "line_count": scanner.line_count,
            "final_brace_depth": scanner.depth,
            "brace_balance_ok": scanner.depth == 0,
            "unknown": list(scanner.unknown),
        },
        "records": records,
        "matching_eng_fra": matching,
        "total_records": scanner.total_records,
        "records_truncated": scanner.records_truncated,
    }


def _active_wars(path: Path) -> dict[str, Any]:
    source = bounded.detect_container(path)
    result = war_parser.scan_active_wars(path, source, "ENG", "FRA")
    return {
        "line_count": result.get("line_count"),
        "final_brace_depth": result.get("final_brace_depth"),
        "brace_balance_ok": result.get("brace_balance_ok"),
        "active_war_blocks_seen": result.get("active_war_blocks_seen"),
        "matching_active_wars": result.get("matching_active_wars", []),
        "unknown": result.get("unknown", []),
    }


def _pair_state(
    relation_scan: dict[str, Any],
    pair: tuple[str, str],
) -> dict[str, Any]:
    records = relation_scan["by_pair"].get(f"{pair[0]}->{pair[1]}", [])
    return {
        "pair": {"source": pair[0], "subject": pair[1]},
        "count": len(records),
        "present": bool(records),
        "records": records,
        "subject_types": sorted(
            {
                str(record.get("subject_type"))
                for record in records
                if record.get("subject_type") is not None
            }
        ),
    }


def _relation_checks(
    before: dict[str, Any], after: dict[str, Any]
) -> tuple[dict[str, bool], dict[str, Any]]:
    checks: dict[str, bool] = {}
    states: dict[str, Any] = {}
    for pair, expected_before in BASELINE_RELATIONS.items():
        key = f"before_{pair[0]}_{pair[1]}_present"
        state = _pair_state(before, pair)
        states[key] = state
        checks[key] = state["present"] is expected_before and state["count"] <= 1
    for pair, expected_after in FINAL_RELATIONS.items():
        key = f"after_{pair[0]}_{pair[1]}_present"
        state = _pair_state(after, pair)
        states[key] = state
        checks[key] = state["present"] is expected_after and state["count"] <= 1

    final_fra_lei = _pair_state(after, ("FRA", "LEI"))
    checks["after_fra_lei_type_is_readable"] = (
        final_fra_lei["count"] == 1
        and len(final_fra_lei["subject_types"]) == 1
        and final_fra_lei["subject_types"][0] not in {"", "None"}
    )
    checks["before_subject_scan_complete"] = (
        before["scan"]["diplomacy_block_found"]
        and before["scan"]["diplomacy_block_complete"]
        and before["scan"]["brace_balance_ok"]
        and not before["scan"]["unknown"]
    )
    checks["after_subject_scan_complete"] = (
        after["scan"]["diplomacy_block_found"]
        and after["scan"]["diplomacy_block_complete"]
        and after["scan"]["brace_balance_ok"]
        and not after["scan"]["unknown"]
    )
    return checks, states


def compare(before_path: Path, after_path: Path) -> dict[str, Any]:
    before_rel = _relation_records(before_path)
    after_rel = _relation_records(after_path)
    before_rep = _war_reparations(before_path)
    after_rep = _war_reparations(after_path)
    before_war = _active_wars(before_path)
    after_war = _active_wars(after_path)

    checks, relation_states = _relation_checks(before_rel, after_rel)
    before_reparations = before_rep["matching_eng_fra"]
    after_reparations = after_rep["matching_eng_fra"]
    checks["before_eng_fra_reparations_pair_at_most_one"] = len(before_reparations) <= 1
    checks["after_eng_fra_reparations_exactly_one"] = len(after_reparations) == 1
    if after_reparations:
        final_rep = after_reparations[0]
        checks["after_eng_fra_reparations_dates"] = (
            final_rep.get("start_date") == "1455.6.18"
            and final_rep.get("end_date") == "1465.6.18"
        )
    else:
        checks["after_eng_fra_reparations_dates"] = False
    checks["before_war_scan_complete"] = bool(
        before_war.get("brace_balance_ok") and not before_war.get("unknown")
    )
    checks["after_war_scan_complete"] = bool(
        after_war.get("brace_balance_ok") and not after_war.get("unknown")
    )
    before_active = [
        record
        for record in before_war["matching_active_wars"]
        if record.get("pair_currently_active") is True
    ]
    after_active = [
        record
        for record in after_war["matching_active_wars"]
        if record.get("pair_currently_active") is True
    ]
    checks["before_eng_fra_war_present"] = bool(before_active)
    checks["after_eng_fra_war_absent"] = not bool(after_active)
    before_war["currently_active_matching_wars"] = before_active
    after_war["currently_active_matching_wars"] = after_active

    return {
        "schema": "r60_subject_save_compare_v1",
        "status": "passed" if all(checks.values()) else "incomplete",
        "checks": checks,
        "baseline": {
            "path": str(before_path),
            "relations": before_rel,
            "war_reparations": before_rep,
            "active_wars": before_war,
        },
        "final": {
            "path": str(after_path),
            "relations": after_rel,
            "war_reparations": after_rep,
            "active_wars": after_war,
        },
        "relation_states": relation_states,
        "reparations_comparison": {
            "serialized_pair": {"first": "ENG", "second": "FRA"},
            "before_matching_records": before_reparations,
            "after_matching_records": after_reparations,
            "expected_after_dates": {
                "start_date": "1455.6.18",
                "end_date": "1465.6.18",
            },
        },
        "money_attribution": {
            "treasury_difference_used": False,
            "reason": "跨月存档的treasury差不能归因于该议和；金币只采信native即时效果记录。",
        },
        "streaming_contract": {
            "complete_save_loaded_into_memory": False,
            "sha256_recomputed": False,
            "parsers": [
                "work/inspect_peace_subject_save.py",
                "work/inspect_peace_treaty_save.py::TreatySaveScanner",
                "work/inspect_declare_war_save_pair.py::scan_active_wars",
            ],
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    before = _resolve(args.before, "baseline save")
    after = _resolve(args.after, "final save")
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite report: {args.output}")
    report = compare(before, after)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": report["status"], "output": str(args.output)}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
