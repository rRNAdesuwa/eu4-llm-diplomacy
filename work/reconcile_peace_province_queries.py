"""Offline reconciliation for the two malformed R41 province-query events.

The native slice is immutable evidence.  This utility copies it line by line,
inserting only the two missing array terminators needed for JSON decoding.  It
then runs the bridge's real QUERY6 validator and semantic projection against
the repaired derived lines.  The original slice and report are never changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridge.diplomacy import ObserverSession


DEFAULT_ARTIFACT = Path(
    "work/runtime/diplomacy-query-20261016-r41-peace-b-provinces/"
    "peace-province-offer-queries-ae6babaa0ec8441991a94e1207b4c63d")
EVENT_NAME = "native_peace_province_offer_inspection"
REPAIR_LINES = frozenset({241, 498})


def _insert_missing_array_terminator(
        line: str, field: str, next_field: str) -> tuple[str, dict | None]:
    marker = f'"{field}":'
    start = line.find(marker)
    if start < 0:
        raise ValueError(f"missing field {field}")
    value_start = start + len(marker)
    if value_start >= len(line) or line[value_start] != "[":
        raise ValueError(f"field {field} is not an array")
    next_marker = f',"{next_field}":'
    end = line.find(next_marker, value_start + 1)
    if end < 0:
        raise ValueError(f"missing delimiter after {field}")
    if line[end - 1] == "]":
        return line, None
    repaired = line[:end] + "]" + line[end:]
    return repaired, {
        "field": field,
        "insert_offset": end,
        "next_field": next_field,
    }


def repair_event_line(line: str, line_number: int) -> tuple[str, list[dict]]:
    """Repair only the known two missing `]` delimiters on a target line."""
    if line_number not in REPAIR_LINES:
        return line, []
    repairs: list[dict] = []
    for field, next_field in (
            ("requested_province_ids", "requested_beneficiary"),
            ("selected_province_ids", "selected_beneficiary")):
        line, repair = _insert_missing_array_terminator(
            line, field, next_field)
        if repair is not None:
            repairs.append(repair)
    return line, repairs


def _selection_from_event(event: dict) -> dict:
    native = event["native_provinces"]
    return {
        "war_id": event["war_id"],
        "direction": "demand",
        "province_ids": list(native["requested_province_ids"]),
        "beneficiary": native["requested_beneficiary"],
    }


def _event_summary(event: dict, line_number: int) -> dict:
    native = event["native_provinces"]
    selection = _selection_from_event(event)
    valid = ObserverSession._valid_native_peace_province_offer_inspection(
        event, "cede_province", event["actor"], event["recipient"],
        event["phase"], event["date_raw"], selection,
        event["query_id"], event["session_id"])
    projected = (ObserverSession._semantic_peace_province_offer_inspection(event)
                 if valid else None)
    candidate_ids = [row["province_id"] for row in native["candidates"]]
    index_177 = candidate_ids.index(177) if 177 in candidate_ids else None
    public_candidates = (
        projected["native_provinces"]["candidates"] if projected else [])
    return {
        "source_line": line_number,
        "query_id": event["query_id"],
        "session_id": event["session_id"],
        "recipient": event["recipient"],
        "war_id": event["war_id"],
        "requested_province_ids": selection["province_ids"],
        "requested_beneficiary": selection["beneficiary"],
        "native_candidate_count": native["candidate_count"],
        "native_candidate_ids": candidate_ids,
        "contains_177": 177 in candidate_ids,
        "next_candidate_after_177": (
            candidate_ids[index_177 + 1]
            if index_177 is not None and index_177 + 1 < len(candidate_ids)
            else None),
        "native_selected_province_ids": native["selected_province_ids"],
        "native_reason_code": native["reason_code"],
        "validator_passed": valid,
        "projection_replayed": projected is not None,
        "public_candidate_count": len(public_candidates),
        "public_candidate_177": next((row for row in public_candidates
                                       if row.get("province_id") == 177), None),
        "public_actual_terms": (
            projected["peace_context"]["terms"] if projected else None),
    }


def reconcile(artifact: Path) -> dict:
    source = artifact / "native-events-slice.jsonl"
    derived = artifact / "native-events-reconciled.jsonl"
    report_json = artifact / "province-query-reconciliation.json"
    report_md = artifact / "province-query-reconciliation.md"
    source_hash = hashlib.sha256()
    repairs: list[dict] = []
    summaries: list[dict] = []
    parse_failures: list[dict] = []
    with source.open("rb") as src, derived.open("wb") as dst:
        for line_number, raw in enumerate(src, 1):
            source_hash.update(raw)
            text = raw.decode("utf-8")
            repaired, line_repairs = repair_event_line(text, line_number)
            for item in line_repairs:
                repairs.append({"line": line_number, **item})
            dst.write(repaired.encode("utf-8"))
            try:
                event = json.loads(repaired)
            except (UnicodeDecodeError, ValueError) as exc:
                if line_number in REPAIR_LINES:
                    parse_failures.append({
                        "line": line_number, "error": type(exc).__name__,
                    })
                continue
            if (isinstance(event, dict)
                    and event.get("event") == EVENT_NAME):
                summaries.append(_event_summary(event, line_number))
    derived_hash = hashlib.sha256(derived.read_bytes()).hexdigest()
    source_hash_hex = source_hash.hexdigest()
    if len(repairs) != 4:
        raise RuntimeError(f"expected four delimiter repairs, got {len(repairs)}")
    if parse_failures:
        raise RuntimeError(f"repaired target lines still fail JSON: {parse_failures}")
    result = {
        "status": "derived_reconciliation",
        "source_path": str(source),
        "source_sha256": source_hash_hex,
        "source_immutable": True,
        "derived_path": str(derived),
        "derived_sha256": derived_hash,
        "derived_is_native_truth": False,
        "transport_json_was_malformed": True,
        "repair_scope": {
            "target_lines": sorted(REPAIR_LINES),
            "inserted_delimiters": len(repairs),
            "repairs": repairs,
        },
        "event_count_replayed": len(summaries),
        "validator_pass_count": sum(
            item["validator_passed"] for item in summaries),
        "validator_checks": (
            "ObserverSession._valid_native_peace_province_offer_inspection; "
            "ObserverSession._semantic_peace_province_offer_inspection"),
        "events": summaries,
        "caveat": (
            "仅对两行缺失数组终止符进行派生修复；原始 native slice/report "
            "仍保留，派生 JSON 不被标记为原生传输格式正确。"),
    }
    report_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    lines = [
        "# R41B 省份查询离线 reconciliation",
        "",
        "原始 `native-events-slice.jsonl` 在第 241、498 行各有两个数组缺失 `]`。本次只在派生 JSONL 中补足四个分隔符；原始 slice、原始 report 和原始 SHA 未修改。",
        "",
        f"- 原始 SHA256：`{source_hash_hex}`",
        f"- 派生 SHA256：`{derived_hash}`",
        f"- 回放事件：{len(summaries)} 条；validator 通过：{sum(item['validator_passed'] for item in summaries)} 条",
        "- 派生文件不代表原生传输格式正确，只用于恢复字段级候选证据和验证器投影。",
        "",
    ]
    for item in summaries:
        ids = item["native_candidate_ids"]
        lines.extend([
            f"## 第 {item['source_line']} 行 / `{item['query_id']}`",
            "",
            f"请求省份：`{item['requested_province_ids']}`，beneficiary：`{item['requested_beneficiary']}`；候选数量：{item['native_candidate_count']}。",
            f"候选包含 177：`{item['contains_177']}`；177 后的下一个候选：`{item['next_candidate_after_177']}`。",
            f"实际选中省份：`{item['native_selected_province_ids']}`；原生 reason：`{item['native_reason_code']}`。",
            f"validator：`{item['validator_passed']}`；public projection：`{item['projection_replayed']}`。",
            f"候选 ID 顺序：`{ids}`。",
            "",
        ])
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    args = parser.parse_args()
    result = reconcile(args.artifact)
    print(json.dumps({
        "status": result["status"],
        "source_sha256": result["source_sha256"],
        "derived_sha256": result["derived_sha256"],
        "event_count_replayed": result["event_count_replayed"],
        "validator_pass_count": result["validator_pass_count"],
        "candidate_summaries": [
            {key: event[key] for key in (
                "source_line", "native_candidate_count", "contains_177",
                "next_candidate_after_177", "validator_passed")}
            for event in result["events"]
        ],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
