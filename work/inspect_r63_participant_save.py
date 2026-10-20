#!/usr/bin/env python3
"""Stream the serialized participant fields of one R63 Declare War save.

The reader keeps only bounded ``active_war`` blocks and direct diplomacy
records that mention one of the requested tags.  It deliberately treats the
execution receipt as the source of the request intent and the save as the
source of persisted war state.  A joined side or ``promised_land`` marker is
reported as serialized evidence; it is not relabeled as a separate
``call_allies`` or ``co_belligerent`` save key when the game did not write
one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from work import inspect_dissolve_save_pair as bounded
from work.inspect_declare_war_save_pair import scan_active_wars


MAX_DIPLOMACY_CAPTURE_BYTES = 256 * 1024
MAX_RELEVANT_DIPLOMACY_RECORDS = 512
MAX_RAW_EXCERPT_BYTES = 8192
TAG_RE = re.compile(r"\b[A-Z][A-Z0-9_]{1,5}\b")
DIPLOMACY_RE = re.compile(r"^\s*diplomacy\s*=\s*\{")
DIRECT_BLOCK_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=\s*\{")

DEFAULT_TAGS = ("FRA", "BUR", "SAV", "HSA", "ORL")
DEFAULT_EXPECTED_SHA256 = (
    "e03b9cfedd8b1400e31b6299af434a77d9dba226b997c64452da46e94555b251"
)
DEFAULT_EXECUTION_REPORT = (
    ROOT / "work" / "runtime" / "r63-participants-execution-20261019-001" / "report.json"
)


def _short_raw(text: str, limit: int = MAX_RAW_EXCERPT_BYTES) -> tuple[str, bool]:
    encoded = text.encode("utf-8", "replace")
    if len(encoded) <= limit:
        return text, False
    half = limit // 2
    clipped = encoded[:half] + b"\n...<raw excerpt truncated>...\n" + encoded[-half:]
    return clipped.decode("utf-8", "replace"), True


def _tags_in_text(text: str, target_tags: set[str]) -> list[str]:
    return sorted({token for token in TAG_RE.findall(text) if token in target_tags})


def _metadata(path: Path) -> dict[str, Any]:
    """Read only the small top-level header, never the gamestate body."""

    result: dict[str, Any] = {"date": None, "player": None, "header": None}
    source = bounded.detect_container(path)
    result["header"] = source.get("header")
    if source.get("container") == "zip":
        # The requested save is plain EU4txt.  Keep ZIP handling bounded if
        # this helper is reused for another save.
        result["date"] = None
        result["player"] = None
        return result
    with bounded.open_gamestate(path, source) as stream:
        for index, line in enumerate(stream):
            if index == 0:
                result["header"] = line.rstrip("\r\n")
            if index < 32:
                match = re.match(r"^\s*date\s*=\s*([^\r\n]+)", line)
                if match and result["date"] is None:
                    result["date"] = bounded.unquote(match.group(1).strip())
                match = re.match(r"^\s*player\s*=\s*([^\r\n]+)", line)
                if match and result["player"] is None:
                    result["player"] = bounded.unquote(match.group(1).strip())
            if index >= 31:
                break
    return result


class DiplomacyScanner:
    """Single-pass, bounded scanner for relevant direct diplomacy records."""

    def __init__(self, target_tags: tuple[str, ...]):
        self.target_tags = set(target_tags)
        self.depth = 0
        self.line_count = 0
        self.found = False
        self.complete = False
        self.base_depth: int | None = None
        self.diplomacy_depth: int | None = None
        self.current: dict[str, Any] | None = None
        self.blocks_seen = 0
        self.relevant_blocks_seen = 0
        self.records: list[dict[str, Any]] = []
        self.unknown: list[str] = []

    def _finish(self, end_line: int | None, complete: bool) -> None:
        current = self.current
        self.current = None
        if current is None:
            return
        if not complete or current["too_large"]:
            self.unknown.append(
                f"diplomacy_block_incomplete_or_over_limit_at_line_{current['line_start']}"
            )
            return
        text = "".join(current["lines"])
        tags = _tags_in_text(text, self.target_tags)
        if not tags:
            return
        self.relevant_blocks_seen += 1
        try:
            parsed = bounded.parse_structured_block(text)
            fields = parsed.get("fields", {})
            blocks = parsed.get("blocks", [])
            unknown = parsed.get("unknown", [])
        except Exception as exc:  # pragma: no cover - defensive boundary
            fields, blocks, unknown = {}, [], [f"parse_error:{exc}"]
        raw_excerpt, raw_truncated = _short_raw(text)
        record = {
            "key": current["key"],
            "line_start": current["line_start"],
            "line_end": end_line,
            "scope_depth": current["parent_depth"],
            "complete": True,
            "bytes_captured": current["bytes_captured"],
            "tags_found": tags,
            "fields": fields,
            "blocks": blocks,
            "parser_unknown": unknown,
            "raw_excerpt": raw_excerpt,
            "raw_excerpt_truncated": raw_truncated,
        }
        if len(self.records) < MAX_RELEVANT_DIPLOMACY_RECORDS:
            self.records.append(record)
        else:
            self.unknown.append("relevant_diplomacy_record_limit_reached")

    def consume(self, stream: TextIO) -> None:
        for line_number, line in enumerate(stream, 1):
            self.line_count = line_number
            before = self.depth
            if not self.found and before == 0 and DIPLOMACY_RE.match(line):
                self.found = True
                self.base_depth = before
                self.diplomacy_depth = before + bounded.brace_delta(line)

            if (
                self.found
                and not self.complete
                and self.current is None
                and self.diplomacy_depth is not None
                and before == self.diplomacy_depth
            ):
                match = DIRECT_BLOCK_RE.match(line)
                if match:
                    self.blocks_seen += 1
                    self.current = {
                        "key": match.group(1),
                        "parent_depth": before,
                        "block_depth": before + bounded.brace_delta(line),
                        "line_start": line_number,
                        "lines": [line],
                        "bytes_captured": len(line.encode("utf-8", "replace")),
                        "too_large": False,
                    }

            if self.current is not None and line_number != self.current["line_start"]:
                size = len(line.encode("utf-8", "replace"))
                self.current["bytes_captured"] += size
                if not self.current["too_large"]:
                    if self.current["bytes_captured"] <= MAX_DIPLOMACY_CAPTURE_BYTES:
                        self.current["lines"].append(line)
                    else:
                        self.current["too_large"] = True
                        self.current["lines"] = []

            self.depth += bounded.brace_delta(line)
            if (
                self.current is not None
                and self.depth == self.current["parent_depth"]
                and before >= self.current["block_depth"]
            ):
                self._finish(line_number, True)

            if (
                self.found
                and self.base_depth is not None
                and self.diplomacy_depth is not None
                and self.depth == self.base_depth
                and before >= self.diplomacy_depth
            ):
                if self.current is not None:
                    self._finish(line_number, False)
                self.complete = True
        if self.current is not None:
            self._finish(None, False)


def scan_diplomacy(path: Path, source: dict[str, Any], tags: tuple[str, ...]) -> dict[str, Any]:
    scanner = DiplomacyScanner(tags)
    with bounded.open_gamestate(path, source) as stream:
        scanner.consume(stream)
    unknown = list(scanner.unknown)
    if not scanner.found:
        unknown.append("diplomacy_block_not_found")
    elif not scanner.complete:
        unknown.append("diplomacy_block_incomplete")
    if scanner.depth != 0:
        unknown.append(f"final_brace_depth:{scanner.depth}")
    return {
        "line_count": scanner.line_count,
        "final_brace_depth": scanner.depth,
        "brace_balance_ok": scanner.depth == 0,
        "diplomacy_block_found": scanner.found,
        "diplomacy_block_complete": scanner.complete,
        "direct_blocks_seen": scanner.blocks_seen,
        "relevant_blocks_seen": scanner.relevant_blocks_seen,
        "records": scanner.records,
        "unknown": unknown,
    }


def _field(record: dict[str, Any], key: str) -> Any:
    fields = record.get("serialized_fields", {})
    return fields.get(key)


def _participants_by_tag(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("tag")): item
        for item in record.get("participants", [])
        if item.get("tag")
    }


def _has_serialized_action_key(record: dict[str, Any], key: str) -> bool:
    paths = [str(item).casefold() for item in record.get("serialized_block_paths", [])]
    fields = [str(item).casefold() for item in record.get("serialized_fields", {})]
    raw = str(record.get("raw_excerpt", "")).casefold()
    needle = key.casefold()
    return any(needle in item for item in paths + fields) or needle in raw


def _load_execution_report(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    # The execution report is a small JSON contract; it is never the save.
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_payload(
    save_path: Path,
    *,
    actor: str,
    recipient: str,
    promised_ally: str,
    co_belligerent: str,
    beneficiary: str,
    target_province: int,
    expected_sha256: str | None,
    execution_report_path: Path | None,
) -> dict[str, Any]:
    source = bounded.detect_container(save_path)
    metadata = _metadata(save_path)
    war_scan = scan_active_wars(save_path, source, actor, recipient)
    diplomacy_scan = scan_diplomacy(save_path, source, DEFAULT_TAGS)
    current_matches = [
        item for item in war_scan["matching_active_wars"]
        if item.get("pair_currently_active")
    ]
    # Prefer the only active FRA↔BUR pair.  If a future save has more than one
    # current pair, retain all candidates instead of silently selecting one.
    selected = current_matches[0] if len(current_matches) == 1 else None
    execution = _load_execution_report(execution_report_path)
    execution_result = None
    if execution:
        execution_result = (
            execution.get("result", {}).get("result")
            or execution.get("submission", {}).get("result")
            or execution.get("result")
        )

    actual: dict[str, Any] = {
        "selected": selected is not None,
        "matching_active_war_count": len(war_scan["matching_active_wars"]),
        "currently_active_pair_count": len(current_matches),
        "candidate_line_ranges": [
            [item.get("line_start"), item.get("line_end")]
            for item in war_scan["matching_active_wars"]
        ],
        "old_ended_war_excluded_by_pair_currently_active": bool(
            selected is not None
            and len(current_matches) == 1
            and selected.get("pair_currently_active") is True
        ),
    }
    checks: dict[str, bool] = {
        "save_container_supported": source.get("container") in {"plain", "zip"},
        "active_war_scan_complete": bool(war_scan.get("brace_balance_ok")),
        "diplomacy_scan_complete": bool(diplomacy_scan.get("brace_balance_ok"))
        and bool(diplomacy_scan.get("diplomacy_block_complete")),
        "one_current_actor_recipient_war": selected is not None,
    }
    unknown: list[str] = []
    if selected is None:
        unknown.append("current_actor_recipient_war_not_unique")
    if selected is not None:
        sides = selected.get("current_sides", {})
        attackers = list(sides.get("attackers", []))
        defenders = list(sides.get("defenders", []))
        participants = _participants_by_tag(selected)
        goal = next(
            (
                item
                for item in selected.get("war_goal_records", [])
                if item.get("kind") == "take_province"
            ),
            None,
        )
        goal_fields = (goal or {}).get("fields", {})
        promised_record = participants.get(promised_ally, {})
        promised_fields = promised_record.get("fields", {})
        actual.update({
            "line_start": selected.get("line_start"),
            "line_end": selected.get("line_end"),
            "current_sides": {
                "attackers": attackers,
                "defenders": defenders,
                "persistent_attackers": sides.get("persistent_attackers", []),
                "persistent_defenders": sides.get("persistent_defenders", []),
                "all_current_tags": sides.get("all_current_tags", []),
            },
            "participant_tags": sorted(participants),
            "participant_count": len(participants),
            "war_goal": {
                "serialized_kind": goal.get("kind") if goal else None,
                "casus_belli": goal_fields.get("casus_belli"),
                "type": goal_fields.get("type"),
                "province": goal_fields.get("province"),
                "subjects": goal_fields.get("subjects"),
                "line_recorded_in_active_war": bool(goal),
            },
            "promised_land": {
                "participant": promised_ally,
                "participant_present": promised_ally in participants,
                "serialized_field": promised_fields.get("promised_land"),
                "participant_fields": promised_fields,
            },
            "request_action_fields_in_active_war": {
                "call_allies": _has_serialized_action_key(selected, "call_allies"),
                "promise_land_to": _has_serialized_action_key(selected, "promise_land_to"),
                "co_belligerents": _has_serialized_action_key(selected, "co_belligerent"),
            },
            "bounded_active_war_excerpt": {
                "raw_excerpt": selected.get("raw_excerpt"),
                "raw_excerpt_truncated": selected.get("raw_excerpt_truncated"),
                "raw_excerpt_sha256": selected.get("raw_excerpt_sha256"),
            },
        })
        checks.update({
            "actor_in_attackers": actor in attackers,
            "recipient_in_defenders": recipient in defenders,
            "called_ally_in_attackers": promised_ally in attackers,
            "co_belligerent_in_defenders": co_belligerent in defenders,
            "beneficiary_in_attackers": beneficiary in attackers,
            "beneficiary_serialized_as_subjects": goal_fields.get("subjects") == f'"{beneficiary}"'
            or goal_fields.get("subjects") == beneficiary,
            "war_goal_casus_belli_matches": goal_fields.get("casus_belli") == f'"cb_conquest"'
            or goal_fields.get("casus_belli") == "cb_conquest",
            "war_goal_province_matches": str(goal_fields.get("province")) == str(target_province),
            "promise_land_saved_on_called_ally": promised_fields.get("promised_land")
            in {"yes", "true", "1", 1, True},
            "all_current_members_have_participant_records": set(attackers + defenders)
            <= set(participants),
        })
        if goal_fields.get("subjects") not in {beneficiary, f'"{beneficiary}"'}:
            unknown.append("beneficiary_subject_field_not_matching_expected")
        for tag in (actor, recipient, promised_ally, co_belligerent, beneficiary):
            if tag not in set(attackers + defenders):
                unknown.append(f"expected_tag_not_in_current_sides:{tag}")
        # These are intentionally informational: the save uses the joined
        # side and participant marker, not the transient request list.
        if not actual["request_action_fields_in_active_war"]["call_allies"]:
            unknown.append("call_allies_request_key_not_serialized; SAV side membership is saved")
        if not actual["request_action_fields_in_active_war"]["promise_land_to"]:
            unknown.append("promise_land_to_request_key_not_serialized; SAV promised_land is saved")
        if not actual["request_action_fields_in_active_war"]["co_belligerents"]:
            unknown.append("co_belligerents_request_key_not_serialized; HSA defender membership is saved")

    if expected_sha256:
        actual["expected_sha256"] = expected_sha256
        actual["sha256_verification"] = "not_recomputed_by_this_report; caller-supplied immutable SHA"
    request = {
        "actor": actor,
        "recipient": recipient,
        "casus_belli": "cb_conquest",
        "war_goal": {"province_id": target_province, "beneficiary": beneficiary},
        "call_allies": [promised_ally],
        "promise_land_to": [promised_ally],
        "co_belligerents": [co_belligerent],
    }
    execution_contract = None
    if execution_result is not None:
        execution_contract = {
            key: execution_result.get(key)
            for key in (
                "request_id", "actor", "recipient", "casus_belli", "war_goal_province",
                "war_goal_beneficiary", "call_allies", "promise_land_to",
                "co_belligerents", "war_after", "outcome", "execution_verified",
            )
            if key in execution_result
        }

    return {
        "tool": {
            "name": "work/inspect_r63_participant_save.py",
            "version": 1,
            "streaming": True,
            "whole_save_read_into_memory": False,
            "active_war_capture_limit_bytes": 2 * 1024 * 1024,
            "diplomacy_record_capture_limit_bytes": MAX_DIPLOMACY_CAPTURE_BYTES,
            "diplomacy_relevant_record_limit": MAX_RELEVANT_DIPLOMACY_RECORDS,
            "existing_helpers": [
                "work.inspect_declare_war_save_pair.scan_active_wars",
                "work.inspect_dissolve_save_pair.open_gamestate",
                "work.inspect_dissolve_save_pair.parse_structured_block",
            ],
        },
        "source": {
            **source,
            "path": str(save_path.resolve()),
            "known_sha256": expected_sha256,
            "sha256_recomputed": False,
        },
        "metadata": metadata,
        "request_contract": request,
        "execution_report": {
            "path": str(execution_report_path.resolve()) if execution_report_path else None,
            "loaded": execution is not None,
            "selected_fields": execution_contract,
        },
        "war_scan": {
            "active_war_blocks_seen": war_scan.get("active_war_blocks_seen"),
            "matching_active_wars": len(war_scan.get("matching_active_wars", [])),
            "line_count": war_scan.get("line_count"),
            "brace_balance_ok": war_scan.get("brace_balance_ok"),
            "unknown": war_scan.get("unknown", []),
        },
        "diplomacy_scan": diplomacy_scan,
        "selected_war": actual,
        "checks": checks,
        "checks_passed": sum(bool(value) for value in checks.values()),
        "checks_total": len(checks),
        "unknown_or_nonpersistent_fields": unknown,
        "interpretation": [
            "active_war 的 attackers/defenders 与 participants 是保存后的实际成员；本报告按当前 active pair 选取战争，不把旧已结束战争当作目标。",
            "take_province.subjects=ORL 是该存档中目标受益国的字段名；请求中的 beneficiary=ORL 与该保存字段一致。",
            "请求的 call_allies、promise_land_to、co_belligerents 是执行接口字段。存档实际保留 SAV 的 promised_land=yes、SAV 的攻击方成员身份和 HSA 的防守方成员身份；没有把成员身份反推成独立的请求键。",
            "战争目标保存为 take_province.type=take_claim、casus_belli=cb_conquest、province=88；类型字段按保存原文报告，不擅自改写为请求名称。",
        ],
        "limitations": [
            "本工具只证明序列化存档字段，不替代 native Declare War 执行回执。",
            "没有保存独立 call_allies/co_belligerents/promise_land_to 列表时，报告保留为未序列化，而不是推断其不存在于执行过程。",
            "known_sha256 使用调用者提供的既有值；本轮没有为43MB存档重复计算哈希。",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    source = payload["source"]
    selected = payload["selected_war"]
    lines = [
        "# R63 宣战参与者存档字段核对",
        "",
        "本报告按行读取指定 EU4txt 存档，只保留当前 FRA–BUR active_war 和涉及 FRA/BUR/SAV/HSA/ORL 的外交记录。完整 43MB gamestate 没有进入内存。",
        "",
        f"- 保存：`{source['path']}`",
        f"- 大小：{source.get('size_bytes')} bytes；调用者已核对 SHA-256：`{source.get('known_sha256')}`",
        f"- 日期/玩家：`{payload['metadata'].get('date')}` / `{payload['metadata'].get('player')}`",
        f"- active_war 块：扫描 {payload['war_scan'].get('active_war_blocks_seen')} 个；匹配 FRA/BUR {payload['war_scan'].get('matching_active_wars')} 个；当前 pair 匹配 {selected.get('currently_active_pair_count')}",
        "",
        "## 当前战争",
        "",
        f"- 保存行号：{selected.get('line_start')}–{selected.get('line_end')}；唯一当前 FRA–BUR 战争：`{selected.get('selected')}`。",
        f"- 攻击方（保存）：`{', '.join(selected.get('current_sides', {}).get('attackers', []))}`",
        f"- 防守方（保存）：`{', '.join(selected.get('current_sides', {}).get('defenders', []))}`",
        f"- 参与者记录：{selected.get('participant_count')} 个，标签：`{', '.join(selected.get('participant_tags', []))}`",
        f"- 战争目标：`{json.dumps(selected.get('war_goal'), ensure_ascii=False, sort_keys=True)}`",
        "",
        "请求对应的保存证据：",
        f"- FRA 在攻击方：`{payload['checks'].get('actor_in_attackers')}`；BUR 在防守方：`{payload['checks'].get('recipient_in_defenders')}`。",
        f"- SAV 在攻击方：`{payload['checks'].get('called_ally_in_attackers')}`；参与者记录为 `promised_land=yes`：`{payload['checks'].get('promise_land_saved_on_called_ally')}`。",
        f"- HSA 在防守方：`{payload['checks'].get('co_belligerent_in_defenders')}`。",
        f"- ORL 在攻击方且保存为 `take_province.subjects`：`{payload['checks'].get('beneficiary_in_attackers')}` / `{payload['checks'].get('beneficiary_serialized_as_subjects')}`。",
        "",
        "`call_allies`、`promise_land_to`、`co_belligerents` 是执行请求字段；当前保存没有对应的独立列表键。保存保留了 SAV 的攻击方成员身份、`promised_land=yes`，以及 HSA 的防守方成员身份。",
        "",
        "## 外交块与边界",
        "",
        f"外交顶层块完整：`{payload['diplomacy_scan'].get('diplomacy_block_complete')}`；直接块扫描：{payload['diplomacy_scan'].get('direct_blocks_seen')}；涉及目标标签的记录：{payload['diplomacy_scan'].get('relevant_blocks_seen')}。相关记录只保留有界字段和短原文片段。",
        "外交记录是保存中的独立关系数据，不能替代 active_war 的参战成员。",
        "",
        "## 核对结果",
        "",
        f"通过 {payload.get('checks_passed')}/{payload.get('checks_total')} 项结构和角色检查。未知/未持久化字段：",
    ]
    for item in payload.get("unknown_or_nonpersistent_fields", []):
        lines.append(f"- {item}")
    lines.extend([
        "",
        "本报告只证明序列化字段，执行意图仍以 `work/runtime/r63-participants-execution-20261019-001/report.json` 的 native 回执为准。",
    ])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--actor", default="FRA")
    parser.add_argument("--recipient", default="BUR")
    parser.add_argument("--promised-ally", default="SAV")
    parser.add_argument("--co-belligerent", default="HSA")
    parser.add_argument("--beneficiary", default="ORL")
    parser.add_argument("--target-province", default=88, type=int)
    parser.add_argument("--expected-sha256", default=DEFAULT_EXPECTED_SHA256)
    parser.add_argument("--execution-report", type=Path, default=DEFAULT_EXECUTION_REPORT)
    args = parser.parse_args(argv)
    output = args.output.expanduser().resolve()
    if output.exists():
        unexpected = {
            item.name for item in output.iterdir()
            if item.name not in {"report.json", "report.md"}
        }
        if unexpected:
            parser.error(f"output directory contains unexpected files: {sorted(unexpected)}")
    else:
        output.mkdir(parents=True, exist_ok=True)
    save_path = args.save.expanduser().resolve()
    try:
        payload = build_payload(
            save_path,
            actor=args.actor.strip().upper(),
            recipient=args.recipient.strip().upper(),
            promised_ally=args.promised_ally.strip().upper(),
            co_belligerent=args.co_belligerent.strip().upper(),
            beneficiary=args.beneficiary.strip().upper(),
            target_province=args.target_province,
            expected_sha256=args.expected_sha256,
            execution_report_path=(
                args.execution_report.expanduser().resolve()
                if args.execution_report else None
            ),
        )
    except (OSError, ValueError, bounded.SaveParseError) as exc:
        parser.error(str(exc))
    (output / "report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "report.md").write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "report_json": str(output / "report.json"),
        "report_md": str(output / "report.md"),
        "matching_active_wars": payload["war_scan"]["matching_active_wars"],
        "current_pair_count": payload["selected_war"]["currently_active_pair_count"],
        "checks": f"{payload['checks_passed']}/{payload['checks_total']}",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
