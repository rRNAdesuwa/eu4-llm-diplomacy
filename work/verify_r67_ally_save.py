"""Stream-check the R67 ally-occupation rejected save.

The checker reads only the three target province blocks and the active FRA--BUR
war from each plain EU4 save.  It compares those fields with the prepared R67
scene and records the already-produced native query/submission evidence.  It
does not hash or rewrite either save, and it never loads a complete gamestate
into memory.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from work import inspect_dissolve_save_pair as bounded
from work.inspect_declare_war_save_pair import scan_active_wars


TARGET_IDS = (88, 91, 193)
TARGET_KEYS = {f"-{province_id}" for province_id in TARGET_IDS}
MAX_PROVINCE_BYTES = 4 * 1024 * 1024
PROVINCES_RE = re.compile(r"^\s*provinces\s*=\s*\{")
PROVINCE_RE = re.compile(r"^\s*(?P<key>-[0-9]+)\s*=\s*\{")
SCALAR_RE = re.compile(
    r"^\s*(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>[^{}#]*?)\s*$"
)
TAG_RE = re.compile(r"^\s*([A-Z0-9_]{2,6})\s*$")


def _scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


class ProvinceScanner:
    """Capture only direct fields of the requested province blocks."""

    def __init__(self, targets: Iterable[int] = TARGET_IDS) -> None:
        self.targets = {f"-{province_id}" for province_id in targets}
        self.depth = 0
        self.line_count = 0
        self.provinces_depth: int | None = None
        self.provinces_found = False
        self.provinces_closed = False
        self.current: dict[str, Any] | None = None
        self.target_depth: int | None = None
        self.cores_depth: int | None = None
        self.states: dict[str, dict[str, Any]] = {}
        self.unknown: list[str] = []

    def _new_state(self, key: str, line_number: int) -> dict[str, Any]:
        return {
            "serialized_key": key,
            "province_id": int(key[1:]),
            "line_start": line_number,
            "line_end": None,
            "bytes_captured": 0,
            "complete": False,
            "direct_fields": {},
            "owner": None,
            "controller": None,
            "cores": [],
        }

    def _capture_line(self, line: str) -> None:
        if self.current is None:
            return
        self.current["bytes_captured"] += len(line.encode("utf-8", "replace"))
        if self.current["bytes_captured"] > MAX_PROVINCE_BYTES:
            self.unknown.append(
                f"province_{self.current['province_id']}_over_{MAX_PROVINCE_BYTES}_bytes"
            )

    def consume_line(self, line: str) -> None:
        self.line_count += 1
        before = self.depth

        if not self.provinces_found and before == 0 and PROVINCES_RE.match(line):
            self.provinces_found = True
            self.provinces_depth = before + bounded.brace_delta(line)

        if (
            self.provinces_found
            and not self.provinces_closed
            and self.current is None
            and self.provinces_depth is not None
            and before == self.provinces_depth
        ):
            match = PROVINCE_RE.match(line)
            if match and match.group("key") in self.targets:
                key = match.group("key")
                self.current = self._new_state(key, self.line_count)
                self.target_depth = before + bounded.brace_delta(line)
                self.cores_depth = None

        self._capture_line(line)
        if self.current is not None and self.target_depth is not None:
            if before == self.target_depth:
                scalar = SCALAR_RE.match(line)
                if scalar:
                    key = scalar.group("key")
                    value = _scalar(scalar.group("value"))
                    self.current["direct_fields"].setdefault(key, value)
                    if key in {"owner", "controller"}:
                        self.current[key] = value
                if re.match(r"^\s*cores\s*=\s*\{", line):
                    self.cores_depth = before + bounded.brace_delta(line)
            elif self.cores_depth is not None and before == self.cores_depth:
                tag = TAG_RE.match(line)
                if tag:
                    self.current["cores"].append(tag.group(1))

        self.depth += bounded.brace_delta(line)
        if (
            self.cores_depth is not None
            and self.depth < self.cores_depth
            and before >= self.cores_depth
        ):
            self.cores_depth = None
        if (
            self.current is not None
            and self.target_depth is not None
            and self.depth < self.target_depth
            and before >= self.target_depth
        ):
            self.current["line_end"] = self.line_count
            self.current["complete"] = not any(
                item.startswith(f"province_{self.current['province_id']}_over_")
                for item in self.unknown
            )
            self.states[self.current["serialized_key"]] = self.current
            self.current = None
            self.target_depth = None
            self.cores_depth = None
        if (
            self.provinces_found
            and not self.provinces_closed
            and self.provinces_depth is not None
            and self.depth < self.provinces_depth
            and before >= self.provinces_depth
        ):
            self.provinces_closed = True

    def finish(self) -> dict[str, Any]:
        if self.current is not None:
            self.unknown.append(
                f"province_{self.current['province_id']}_unclosed"
            )
        if not self.provinces_found:
            self.unknown.append("provinces_block_not_found")
        elif not self.provinces_closed:
            self.unknown.append("provinces_block_unclosed")
        if self.depth != 0:
            self.unknown.append(f"final_brace_depth_{self.depth}")
        for key in sorted(self.targets):
            if key not in self.states:
                self.unknown.append(f"target_province_{key[1:]}_not_found")
        return {
            "line_count": self.line_count,
            "provinces_block_found": self.provinces_found,
            "provinces_block_complete": self.provinces_closed,
            "final_brace_depth": self.depth,
            "targets": {
                key[1:]: self.states[key]
                for key in sorted(self.states, key=lambda item: int(item[1:]))
            },
            "unknown": self.unknown,
        }


def scan_provinces(path: Path, source: dict[str, Any]) -> dict[str, Any]:
    scanner = ProvinceScanner()
    with bounded.open_gamestate(path, source) as stream:
        for line in stream:
            scanner.consume_line(line)
    return scanner.finish()


def _war_summary(scan: dict[str, Any]) -> dict[str, Any]:
    records = scan.get("matching_active_wars", [])
    if len(records) != 1:
        return {
            "matching_count": len(records),
            "records": [],
            "scan_complete": scan.get("brace_balance_ok") and not scan.get("unknown"),
            "unknown": scan.get("unknown", []),
        }
    record = records[0]
    fields = record.get("serialized_fields", {})
    participants = {
        item.get("tag"): {
            "fields": item.get("fields", {}),
            "blocks": item.get("blocks", []),
        }
        for item in record.get("participants", [])
        if item.get("tag") in {"FRA", "BUR", "ORL", "SAV"}
    }
    return {
        "matching_count": 1,
        "scan_complete": scan.get("brace_balance_ok") and not scan.get("unknown"),
        "unknown": scan.get("unknown", []),
        "line_start": record.get("line_start"),
        "line_end": record.get("line_end"),
        "pair_currently_active": record.get("pair_currently_active"),
        "original_attacker": record.get("original_sides", {}).get("original_attacker"),
        "original_defender": record.get("original_sides", {}).get("original_defender"),
        "current_attackers": record.get("current_sides", {}).get("attackers", []),
        "current_defenders": record.get("current_sides", {}).get("defenders", []),
        "persistent_attackers": record.get("current_sides", {}).get("persistent_attackers", []),
        "persistent_defenders": record.get("current_sides", {}).get("persistent_defenders", []),
        "action": fields.get("action"),
        "war_goal": {
            "casus_belli": fields.get("take_province.casus_belli"),
            "type": fields.get("take_province.type"),
            "province": fields.get("take_province.province"),
            "subjects": fields.get("take_province.subjects"),
        },
        "participants": participants,
    }


def scan_save(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve(strict=True)
    source = bounded.detect_container(path)
    metadata: dict[str, Any] = {"date": None, "player": None}
    with bounded.open_gamestate(path, source) as stream:
        for index, line in enumerate(stream):
            if index >= 32:
                break
            date_match = re.match(r"^\s*date\s*=\s*(.*?)\s*$", line)
            player_match = re.match(r"^\s*player\s*=\s*(.*?)\s*$", line)
            if date_match and metadata["date"] is None:
                metadata["date"] = _scalar(date_match.group(1))
            if player_match and metadata["player"] is None:
                metadata["player"] = _scalar(player_match.group(1))
    provinces = scan_provinces(path, source)
    active_war = scan_active_wars(path, source, "FRA", "BUR")
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "container": source.get("container"),
        "header": source.get("header"),
        "metadata": metadata,
        "provinces": provinces,
        "active_war": _war_summary(active_war),
        "active_war_blocks_seen": active_war.get("active_war_blocks_seen"),
        "active_war_line_count": active_war.get("line_count"),
    }


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _query_evidence(path: Path, execution_path: Path, blocked_path: Path) -> dict[str, Any]:
    query = _load_json(path)
    case = next(
        item for item in query.get("cases", [])
        if item.get("name") == "subject_88_ORL"
    )
    outbound = _load_json(execution_path)
    final_result = outbound.get("poll", {}).get("final", {}).get("result", {})
    blocked = _load_json(blocked_path)
    return {
        "query": {
            "path": str(path),
            "status": query.get("status"),
            "case": {
                "name": case.get("name"),
                "province_id": case.get("province_id"),
                "beneficiary": case.get("beneficiary"),
                "legality_status": case.get("legality", {}).get("status"),
                "native_beneficiary_matches": case.get("native_beneficiary_matches"),
                "requested_terms_applied": case.get("requested_terms_applied"),
                "native_validator": case.get("native_validator"),
                "object_unchanged": case.get("object_unchanged"),
            },
        },
        "outbound_rejection": {
            "path": str(execution_path),
            "request_id": outbound.get("request_id"),
            "status": outbound.get("status"),
            "business_submission": outbound.get("business_submission"),
            "native_state": final_result.get("native_state"),
            "native_outcome": final_result.get("native_outcome"),
            "outcome": final_result.get("outcome"),
            "war_before": final_result.get("war_before"),
            "war_after": final_result.get("war_after"),
            "terms_verified": final_result.get("terms_verified"),
            "execution_verified": final_result.get("execution_verified"),
            "request_binding_verified": final_result.get("request_binding_verified"),
            "effects": final_result.get("effects"),
        },
        "ally_negative_control": {
            "path": str(blocked_path),
            "status": blocked.get("status"),
            "reason_code": blocked.get("native_reason_code"),
            "business_submission": blocked.get("business_submission"),
            "checks": blocked.get("checks", {}),
        },
    }


def build_report(
    before_path: Path,
    after_path: Path,
    scene_report_path: Path,
    query_report_path: Path,
    execution_report_path: Path,
    blocked_report_path: Path,
    save_observer_report_path: Path,
    after_sha256: str,
) -> dict[str, Any]:
    scene = _load_json(scene_report_path)
    save_observer = _load_json(save_observer_report_path)
    before = scan_save(before_path)
    after = scan_save(after_path)
    before_targets = before["provinces"]["targets"]
    after_targets = after["provinces"]["targets"]
    scene_targets = scene.get("targets", {})
    target_rows: dict[str, Any] = {}
    for province_id in sorted((str(item) for item in TARGET_IDS), key=int):
        source_scene = scene_targets.get(f"-{province_id}", {})
        source_save = before_targets.get(province_id, {})
        final_save = after_targets.get(province_id, {})
        direct_scene = source_scene.get("direct_fields", {})
        direct_source = source_save.get("direct_fields", {})
        direct_after = final_save.get("direct_fields", {})
        expected_controller = source_scene.get("controller_after")
        target_rows[province_id] = {
            "scene_source": {
                "owner": source_scene.get("owner"),
                "controller_before": source_scene.get("controller_before"),
                "controller_after": expected_controller,
                "cores": source_scene.get("cores", []),
                "development_raw": {
                    key: direct_scene.get(key)
                    for key in ("base_tax", "base_production", "base_manpower")
                },
            },
            "source_save": {
                "line_start": source_save.get("line_start"),
                "line_end": source_save.get("line_end"),
                "owner": source_save.get("owner"),
                "controller": source_save.get("controller"),
                "cores": source_save.get("cores", []),
                "development_raw": {
                    key: direct_source.get(key)
                    for key in ("base_tax", "base_production", "base_manpower")
                },
            },
            "after_save": {
                "line_start": final_save.get("line_start"),
                "line_end": final_save.get("line_end"),
                "owner": final_save.get("owner"),
                "controller": final_save.get("controller"),
                "cores": final_save.get("cores", []),
                "development_raw": {
                    key: direct_after.get(key)
                    for key in ("base_tax", "base_production", "base_manpower")
                },
            },
        }
        row = target_rows[province_id]
        row["checks"] = {
            "source_matches_scene": (
                row["source_save"]["owner"] == row["scene_source"]["owner"]
                and row["source_save"]["controller"] == row["scene_source"]["controller_after"]
                and row["source_save"]["cores"] == row["scene_source"]["cores"]
                and row["source_save"]["development_raw"] == row["scene_source"]["development_raw"]
            ),
            "after_owner_still_bur": row["after_save"]["owner"] == "BUR",
            "after_controller_matches_fixture": row["after_save"]["controller"] == expected_controller,
            "after_core_unchanged": row["after_save"]["cores"] == row["scene_source"]["cores"],
            "after_development_unchanged": row["after_save"]["development_raw"] == row["scene_source"]["development_raw"],
            "rejected_peace_did_not_transfer_owner": row["after_save"]["owner"] == "BUR" and expected_controller != "BUR",
        }

    war = after["active_war"]
    scene_war = scene.get("war_context", {}).get("active_war", {})
    war_checks = {
        "active_fra_bur_war_complete": war.get("scan_complete") is True,
        "active_pair_is_current": war.get("pair_currently_active") is True,
        "original_attacker_fra": war.get("original_attacker") == "FRA",
        "original_defender_bur": war.get("original_defender") == "BUR",
        "fra_orl_sav_attackers": all(tag in war.get("current_attackers", []) for tag in ("FRA", "ORL", "SAV")),
        "bur_defender": "BUR" in war.get("current_defenders", []),
        "participant_fields_present": set(war.get("participants", {})) == {"FRA", "BUR", "ORL", "SAV"},
        "war_role_matches_scene": (
            war.get("original_attacker") == scene_war.get("original_attacker") == "FRA"
            and war.get("original_defender") == scene_war.get("original_defender") == "BUR"
        ),
    }
    province_checks = {
        f"province_{province_id}_{name}": all(row["checks"].values())
        for province_id, row in target_rows.items()
        for name in ("fields_match",)
    }
    all_province_checks = all(row["checks"][name] for row in target_rows.values() for name in row["checks"])
    query = _query_evidence(query_report_path, execution_report_path, blocked_report_path)
    observer_save = save_observer.get("save", {})
    observer_binding = {
        "path": str(save_observer_report_path),
        "status": save_observer.get("status"),
        "reported_name": observer_save.get("path", "").split("\\")[-1]
        if observer_save.get("path") else None,
        "reported_sha256": observer_save.get("sha256"),
        "name_matches_after": observer_save.get("path") == str(after_path.resolve()),
        "sha256_matches_supplied": observer_save.get("sha256") == after_sha256,
    }
    query_checks = {
        "or_l_88_query_available": query["query"]["case"]["legality_status"] == "available",
        "or_l_88_native_beneficiary_matches": query["query"]["case"]["native_beneficiary_matches"] is True,
        "or_l_88_requested_term_applied": query["query"]["case"]["requested_terms_applied"] is True,
        "outbound_rejection_bound_to_request": query["outbound_rejection"]["request_binding_verified"] is True,
        "outbound_native_rejected": query["outbound_rejection"]["native_outcome"] == "rejected" and query["outbound_rejection"]["outcome"] == "rejected",
        "outbound_war_continued": query["outbound_rejection"]["war_before"] is True and query["outbound_rejection"]["war_after"] is True,
        "outbound_owner_transition_unverified_after_rejection": (
            query["outbound_rejection"]["effects"].get("provinces", [{}])[0].get("owner_before") == "BUR"
            and query["outbound_rejection"]["effects"].get("provinces", [{}])[0].get("owner_after") == "BUR"
            and query["outbound_rejection"]["effects"].get("provinces", [{}])[0].get("verified") is False
        ),
        "ally_negative_control_reason_bound": query["ally_negative_control"]["reason_code"] == "NATIVE_PEACE_SELECTED_TERM_RULE_UNAVAILABLE",
    }
    checks = {
        "before_after_plain_save_stream_complete": (
            before["provinces"]["provinces_block_complete"]
            and after["provinces"]["provinces_block_complete"]
            and before["provinces"]["final_brace_depth"] == 0
            and after["provinces"]["final_brace_depth"] == 0
        ),
        "three_target_blocks_present_in_both": (
            set(before_targets) == {str(item) for item in TARGET_IDS}
            and set(after_targets) == {str(item) for item in TARGET_IDS}
        ),
        "all_target_fields_match_scene_and_rejection": all_province_checks,
        "after_active_war_role_matches_scene": all(war_checks.values()),
        "after_sha_is_supplied_known_value": bool(after_sha256),
        "save_observer_report_binds_after_save": (
            observer_binding["status"] == "success"
            and observer_binding["name_matches_after"]
            and observer_binding["sha256_matches_supplied"]
        ),
        "query_and_rejection_evidence_bound": all(query_checks.values()),
    }
    return {
        "schema": "r67_ally_save_fields_v1",
        "status": "passed" if all(checks.values()) else "failed",
        "business_submitted_by_checker": False,
        "source_scene_report": str(scene_report_path),
        "source_scene": {
            "path": scene.get("destination", {}).get("path"),
            "sha256": scene.get("destination", {}).get("sha256"),
            "size_bytes": scene.get("destination", {}).get("size_bytes"),
        },
        "before_save": before,
        "after_save": {
            **after,
            "sha256_supplied_from_save_observer_report": after_sha256,
            "save_observer_report": observer_binding,
        },
        "targets": target_rows,
        "war": war,
        "query_execution_evidence": query,
        "checks": {
            **checks,
            **{f"war_{key}": value for key, value in war_checks.items()},
            **{f"query_{key}": value for key, value in query_checks.items()},
            **province_checks,
        },
        "interpretation": [
            "终态保存保留了三个省份的 owner=BUR、核心和发展度；88 的 controller=ORL，91/193 的 controller=SAV。拒绝议和没有把省份所有权转给 ORL 或 SAV。",
            "FRA--BUR active_war 仍处于当前战争，original_attacker=FRA、original_defender=BUR，ORL 与 SAV 仍在攻击方；FRA 的盟主判断沿用保存的 original_attacker 字段。",
            "ORL 省份 88 的原生查询为 available，受益国匹配且 selected term 已应用；随后一次实际提交返回 native_outcome=rejected，战争继续，省份 owner 前后均为 BUR。",
        ],
        "limitations": [
            "after 保存 SHA 使用已提供的 save-observer-report 值，没有重新计算 43MB 存档哈希。",
            "controller 是占领状态；本报告将其与 owner 分开记录，不把拒绝后的 controller 保持误写成所有权转移。",
            "本核对没有启动游戏、重载或再次提交业务请求。",
        ],
    }


def _render_markdown(report: dict[str, Any]) -> str:
    rows = []
    for province_id in sorted(report["targets"], key=int):
        target = report["targets"][province_id]
        source = target["source_save"]
        after = target["after_save"]
        rows.append(
            f"- 省份 {province_id}：场景存档 owner/controller=`{source['owner']}/{source['controller']}`，"
            f"终态保存 owner/controller=`{after['owner']}/{after['controller']}`，"
            f"cores=`{source['cores']}`，development=`{source['development_raw']}`；"
            f"字段检查 `{all(target['checks'].values())}`。"
        )
    war = report["war"]
    query = report["query_execution_evidence"]
    return "\n".join([
        "# R67 盟友占领拒绝保存字段核对",
        "",
        "本报告按行读取 R67 场景源存档和一次实际拒绝后的终态保存，只保留三个目标省份与 FRA–BUR 当前 active_war。",
        "",
        f"源场景：`{report['source_scene']['path']}`，SHA `{report['source_scene']['sha256']}`。",
        f"终态保存：`{report['after_save']['path']}`，日期 `{report['after_save']['metadata']['date']}`，玩家 `{report['after_save']['metadata']['player']}`；SHA 使用已提供值 `{report['after_save']['sha256_supplied_from_save_observer_report']}`，大小 `{report['after_save']['size_bytes']}` bytes。",
        f"保存观测报告：`{report['after_save']['save_observer_report']['path']}`；报告中的路径和 SHA 与终态保存一致。",
        "",
        "## 目标省份",
        "",
        *rows,
        "",
        "## 战争与请求证据",
        "",
        f"终态保存扫描到唯一当前 FRA–BUR 战争，active_war 行 `{war.get('line_start')}-{war.get('line_end')}`；`original_attacker={war.get('original_attacker')}`、`original_defender={war.get('original_defender')}`。攻击方包含 FRA、ORL、SAV，防守方包含 BUR；FRA 的盟主判断使用保存的 original_attacker 字段。",
        f"participant 记录保留 FRA/BUR/ORL/SAV：`{war.get('participants')}`。",
        f"ORL 88 查询状态为 `{query['query']['case']['legality_status']}`，native beneficiary 匹配和 selected term 应用均为 `{query['query']['case']['native_beneficiary_matches']}` / `{query['query']['case']['requested_terms_applied']}`。",
        f"实际提交 `{query['outbound_rejection']['request_id']}` 返回 `native_outcome={query['outbound_rejection']['native_outcome']}`、`war_before/after={query['outbound_rejection']['war_before']}/{query['outbound_rejection']['war_after']}`；原生效果记录 owner BUR→BUR，verified=false。",
        "",
        f"检查状态：`{report['status']}`；顶层检查 `{sum(value is True for value in report['checks'].values())}/{len(report['checks'])}`。",
        "",
        "本次核对没有重新计算终态保存 SHA，没有启动游戏、重载或再次提交请求。",
        "",
    ])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--scene-report", required=True, type=Path)
    parser.add_argument("--query-report", required=True, type=Path)
    parser.add_argument("--execution-report", required=True, type=Path)
    parser.add_argument("--blocked-report", required=True, type=Path)
    parser.add_argument("--save-observer-report", required=True, type=Path)
    parser.add_argument("--after-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    output = args.output.expanduser().resolve()
    if output.exists():
        unexpected = {
            item.name for item in output.iterdir()
            if item.name not in {"report.json", "report.md"}
        }
        if unexpected:
            raise FileExistsError(
                f"OUTPUT_DIRECTORY_CONTAINS_UNEXPECTED_FILES:{sorted(unexpected)}"
            )
    else:
        output.mkdir(parents=True, exist_ok=False)
    try:
        report = build_report(
            args.before,
            args.after,
            args.scene_report,
            args.query_report,
            args.execution_report,
            args.blocked_report,
            args.save_observer_report,
            args.after_sha256.strip(),
        )
    except (OSError, ValueError, KeyError, bounded.SaveParseError) as exc:
        # Do not leave a misleading partial report when a bounded parser fails.
        try:
            output.rmdir()
        except OSError:
            pass
        parser.error(str(exc))
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "report.md").write_text(_render_markdown(report), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "output": str(output),
        "target_checks": [all(item["checks"].values()) for item in report["targets"].values()],
        "war_active": report["war"]["pair_currently_active"],
        "top_level_checks": f"{sum(value is True for value in report['checks'].values())}/{len(report['checks'])}",
    }, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
