"""Prepare a bounded Grant-Independence declaration background.

The source save already contains the intended FRA--ENG peace and vassal
relation.  This operator fixture changes only direct FRA army locations to
FRA's saved capital, so the native declaration query can run without
changing diplomacy, wars, navies, or any other country.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

try:
    from work.prepare_r61_country_scenes import (
        MAX_BLOCK_BYTES,
        brace_delta,
        child_blocks,
        fields_at_depth,
        iter_block_lines,
        line_ending,
        lines_with_depth,
        parse_assignment,
        replace_assignment,
        stripped,
    )
except ModuleNotFoundError:  # direct execution from a copied work directory
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from work.prepare_r61_country_scenes import (
        MAX_BLOCK_BYTES,
        brace_delta,
        child_blocks,
        fields_at_depth,
        iter_block_lines,
        line_ending,
        lines_with_depth,
        parse_assignment,
        replace_assignment,
        stripped,
    )


SAVE_DIR = Path(
    r"C:\Users\wangyufei\Documents\Paradox Interactive\Europa Universalis IV\save games"
)
DEFAULT_SOURCE = SAVE_DIR / (
    "llm_diplomacy_peace_country_independence_relation_retained_20261019_r61.eu4"
)
DEFAULT_OUTPUT = SAVE_DIR / (
    "llm_diplomacy_independence_declaration_home_armies_20261019_r61.eu4"
)
DEFAULT_RUNTIME = Path(__file__).resolve().parent / "runtime" / (
    "r61-independence-declaration-scene-20261019-001"
)

COUNTRY_TAG = "FRA"
EXPECTED_CAPITAL = "183"
EXPECTED_SOURCE_SHA256 = (
    "57798ff9b733a2da6dda23533475439c7c633d36e25b6f50a38deb37583e3e56"
)
MAX_COUNTRY_BLOCK_BYTES = 8 * 1024 * 1024
MOVEMENT_ASSIGNMENTS = {
    "movement",
    "movement_destination",
    "movement_progress",
    "movement_target",
    "movement_locked",
}
MOVEMENT_BLOCKS = {"movement", "movement_path", "path"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def selected(fields: dict[str, tuple[int, str]], names: set[str]) -> dict[str, str]:
    return {key: fields[key][1] for key in sorted(names) if key in fields}


def parse_army_id(army_block: list[bytes]) -> str | None:
    for child_start, child_end, child_key in child_blocks(army_block):
        if child_key != "id":
            continue
        fields = fields_at_depth(
            army_block, 2, child_start + 1, child_end
        )
        value = fields.get("id")
        if value is not None:
            return value[1]
    return None


def movement_evidence(army_block: list[bytes]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for index, line, before, _after in lines_with_depth(army_block):
        assignment = parse_assignment(line)
        if assignment is not None and assignment[0] in MOVEMENT_ASSIGNMENTS:
            found.append(
                {
                    "kind": "assignment",
                    "key": assignment[0],
                    "value": assignment[1],
                    "relative_line": index,
                }
            )
        if before == 1 and stripped(line).endswith(b"={"):
            key = stripped(line)[:-2].decode("ascii", "replace")
            if key in MOVEMENT_BLOCKS:
                found.append(
                    {
                        "kind": "block",
                        "key": key,
                        "relative_line": index,
                    }
                )
    return found


def analyze_country_block(
    block: list[bytes], start_line: int
) -> dict[str, Any]:
    direct = fields_at_depth(block, 1)
    identity = selected(
        direct,
        {"capital", "government_name", "religion", "treasury", "overlord"},
    )
    armies: list[dict[str, Any]] = []
    for child_start, child_end, child_key in child_blocks(block):
        if child_key != "army":
            continue
        army_block = block[child_start : child_end + 1]
        fields = fields_at_depth(block, 2, child_start + 1, child_end)
        location = fields.get("location")
        if location is None:
            raise ValueError(
                f"FRA direct army at line {start_line + child_start} has no direct location"
            )
        armies.append(
            {
                "id": parse_army_id(army_block),
                "block_start_line": start_line + child_start,
                "block_end_line": start_line + child_end,
                "location": location[1],
                "location_relative_line": location[0],
                "location_line": start_line + location[0],
                "movement_path_fields": movement_evidence(army_block),
            }
        )
    return {
        "path": "countries/FRA",
        "line_start": start_line,
        "line_end": start_line + len(block) - 1,
        "bytes": sum(len(line) for line in block),
        "identity": identity,
        "armies": armies,
        "army_count": len(armies),
    }


def scan_fra_country(path: Path) -> dict[str, Any]:
    """Find only countries/FRA while hashing all bytes outside that block."""

    depth = 0
    line_count = 0
    countries_depth: int | None = None
    countries_found = False
    countries_complete = False
    in_countries = False
    target_count = 0
    target: dict[str, Any] | None = None
    target_block: list[bytes] | None = None
    outside = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            line = stream.readline()
            if not line:
                break
            line_count += 1
            before = depth
            marker = stripped(line)
            if before == 0 and marker == b"countries={":
                countries_found = True
                countries_depth = before + brace_delta(line)
                in_countries = True
            if (
                in_countries
                and countries_depth is not None
                and before == countries_depth
                and marker == b"FRA={"
            ):
                block, end_line = iter_block_lines(
                    stream,
                    line,
                    line_count,
                    max_bytes=MAX_COUNTRY_BLOCK_BYTES,
                )
                target_count += 1
                if target_count > 1:
                    raise ValueError("duplicate direct countries/FRA blocks")
                target_block = block
                target = analyze_country_block(block, line_count)
                line_count = end_line
                continue
            outside.update(line)
            depth += brace_delta(line)
            if (
                in_countries
                and countries_depth is not None
                and depth == 0
                and before >= countries_depth
            ):
                countries_complete = True
                in_countries = False
    if target is None or target_block is None:
        raise ValueError("direct countries/FRA block not found")
    if not countries_found or not countries_complete or depth != 0:
        raise ValueError("countries scope is incomplete or unbalanced")
    if target["path"] != "countries/FRA":
        raise ValueError("country path scope is not countries/FRA")
    return {
        "line_count": line_count,
        "countries_found": countries_found,
        "countries_complete": countries_complete,
        "final_brace_depth": depth,
        "target_count": target_count,
        "target": target,
        "block": target_block,
        "outside_sha256": outside.hexdigest(),
        "complete": countries_complete and depth == 0 and target_count == 1,
    }


def country_non_location_sha256(
    block: list[bytes], summary: dict[str, Any]
) -> str:
    skip = {army["location_relative_line"] for army in summary["armies"]}
    digest = hashlib.sha256()
    for index, line in enumerate(block):
        if index not in skip:
            digest.update(line)
    return digest.hexdigest()


def transform_fra_country(
    block: list[bytes], start_line: int, capital: str
) -> tuple[list[bytes], dict[str, Any]]:
    before = analyze_country_block(block, start_line)
    direct = before["identity"]
    if direct.get("capital") != EXPECTED_CAPITAL:
        raise ValueError(
            f"FRA direct capital must be {EXPECTED_CAPITAL}, found {direct.get('capital')!r}"
        )
    if not direct.get("government_name") or not direct.get("treasury"):
        raise ValueError("FRA direct country identity fields are incomplete")
    if not before["armies"]:
        raise ValueError("FRA has no direct army blocks")
    movement_rows = [
        army
        for army in before["armies"]
        if army["movement_path_fields"]
    ]
    if movement_rows:
        raise ValueError(
            "FRA army movement/path fields require manual review; refusing blind rewrite: "
            + repr(movement_rows)
        )
    output = list(block)
    changes: list[dict[str, Any]] = []
    for child_start, child_end, child_key in child_blocks(block):
        if child_key != "army":
            continue
        fields = fields_at_depth(block, 2, child_start + 1, child_end)
        location = fields.get("location")
        if location is None:
            raise ValueError("direct FRA army location disappeared during transform")
        local = location[0]
        old = location[1]
        output[local] = replace_assignment(output[local], "location", capital)
        army = next(
            row
            for row in before["armies"]
            if row["location_relative_line"] == local
        )
        changes.append(
            {
                "army_id": army["id"],
                "location_line": start_line + local,
                "old_location": old,
                "new_location": capital,
                "changed": old != capital,
            }
        )
    after = analyze_country_block(output, start_line)
    if len(after["armies"]) != len(before["armies"]):
        raise ValueError("army count changed while rewriting FRA")
    if any(army["location"] != capital for army in after["armies"]):
        raise ValueError("not every direct FRA army now uses the saved capital")
    if any(army["movement_path_fields"] for army in after["armies"]):
        raise ValueError("movement/path fields appeared during FRA rewrite")
    return output, {
        "country_path": "countries/FRA",
        "capital": capital,
        "armies_count": len(changes),
        "armies": changes,
        "movement_path_fields_before": [],
        "movement_path_fields_after": [],
        "country_non_location_sha256_before": country_non_location_sha256(
            block, before
        ),
        "country_non_location_sha256_after": country_non_location_sha256(
            output, after
        ),
        "identity_before": before["identity"],
        "identity_after": after["identity"],
    }


class HashingWriter:
    def __init__(self, stream: Any) -> None:
        self.stream = stream
        self.digest = hashlib.sha256()
        self.bytes_written = 0
        self.lines_written = 0

    def write(self, data: bytes) -> None:
        self.stream.write(data)
        self.digest.update(data)
        self.bytes_written += len(data)
        self.lines_written += data.count(b"\n")


def rewrite_save(source: Path, destination: Path) -> dict[str, Any]:
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite {destination}")
    partial = destination.with_name(destination.name + ".partial")
    if partial.exists():
        raise FileExistsError(f"refusing to overwrite {partial}")
    depth = 0
    countries_depth: int | None = None
    in_countries = False
    countries_count = 0
    fra_count = 0
    line_count = 0
    rewrite: dict[str, Any] | None = None
    try:
        with source.open("rb") as source_stream, partial.open("xb") as output_stream:
            writer = HashingWriter(output_stream)
            while True:
                line = source_stream.readline()
                if not line:
                    break
                line_count += 1
                before = depth
                marker = stripped(line)
                if before == 0 and marker == b"countries={":
                    countries_count += 1
                    countries_depth = before + brace_delta(line)
                    in_countries = True
                if (
                    in_countries
                    and countries_depth is not None
                    and before == countries_depth
                    and marker == b"FRA={"
                ):
                    block, end_line = iter_block_lines(
                        source_stream,
                        line,
                        line_count,
                        max_bytes=MAX_COUNTRY_BLOCK_BYTES,
                    )
                    fra_count += 1
                    if fra_count > 1:
                        raise ValueError("duplicate direct countries/FRA blocks")
                    transformed, rewrite = transform_fra_country(
                        block, line_count, EXPECTED_CAPITAL
                    )
                    writer.write(b"".join(transformed))
                    line_count = end_line
                    continue
                writer.write(line)
                depth += brace_delta(line)
                if (
                    in_countries
                    and countries_depth is not None
                    and depth == 0
                    and before >= countries_depth
                ):
                    in_countries = False
        if countries_count != 1 or fra_count != 1 or depth != 0:
            raise ValueError(
                f"rewrite scope invalid: countries={countries_count}, FRA={fra_count}, depth={depth}"
            )
        os.replace(partial, destination)
    except Exception:
        if partial.exists():
            partial.unlink()
        raise
    if rewrite is None:
        raise ValueError("FRA rewrite metadata is missing")
    return {
        "sha256": writer.digest.hexdigest(),
        "size_bytes": destination.stat().st_size,
        "lines_written": writer.lines_written,
        "countries_blocks": countries_count,
        "fra_blocks": fra_count,
        "rewrite": rewrite,
    }


def report_markdown(report: dict[str, Any]) -> str:
    checks = report["checks"]
    failures = [key for key, value in checks.items() if not value]
    lines = [
        "# R61 独立宣战前置：法国陆军归首都场景",
        "",
        "这是操作员准备的流式保存背景，没有启动游戏、没有注入宣战请求，也没有修改附属关系。",
        "",
        f"- 源：`{report['source']['path']}`，SHA-256 `{report['source']['sha256']}`。",
        f"- 新保存：`{report['output']['path']}`，SHA-256 `{report['output']['sha256']}`。",
        "- 修改范围：严格限定 `countries/FRA` 直接块内的直接 `army` 子块 `location`；海军、战争、外交关系和其他国家均由字节保持检查覆盖。",
        f"- FRA 真实首都：`{report['transform']['capital']}`；直接陆军数：`{report['transform']['armies_count']}`。",
        "",
        "## 陆军位置",
        "",
        "| army ID | 原 location | 新 location |",
        "|---:|---:|---:|",
    ]
    for row in report["transform"]["armies"]:
        lines.append(
            f"| `{row['army_id']}` | `{row['old_location']}` | `{row['new_location']}` |"
        )
    lines.extend(
        [
            "",
            "源档 FRA 直接陆军没有 movement/path 字段，因此本次没有盲改移动路径。",
            f"检查状态：`{report['status']}`；通过 {sum(checks.values())}/{len(checks)}。",
        ]
    )
    if failures:
        lines.append(f"失败检查：{', '.join(failures)}。")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    args = parser.parse_args()
    source = args.source.resolve()
    destination = args.output.resolve()
    runtime = args.runtime.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if destination.exists() or destination.with_name(destination.name + ".partial").exists():
        raise FileExistsError(f"refusing to overwrite output {destination}")
    runtime.mkdir(parents=True, exist_ok=True)
    for name in ("report.json", "report.md", "fixture-manifest.json"):
        if (runtime / name).exists():
            raise FileExistsError(f"refusing to overwrite {runtime / name}")
    source_sha_before = sha256_file(source)
    if source_sha_before != EXPECTED_SOURCE_SHA256:
        raise ValueError(
            f"source SHA mismatch: expected {EXPECTED_SOURCE_SHA256}, found {source_sha_before}"
        )
    source_scan = scan_fra_country(source)
    source_target = source_scan["target"]
    if source_target["identity"].get("capital") != EXPECTED_CAPITAL:
        raise ValueError("source FRA capital is not the required real capital 183")
    rewrite = rewrite_save(source, destination)
    source_sha_after = sha256_file(source)
    destination_scan = scan_fra_country(destination)
    destination_target = destination_scan["target"]
    checks = {
        "source_sha_matches_declared": source_sha_before == EXPECTED_SOURCE_SHA256,
        "source_sha_stable": source_sha_before == source_sha_after,
        "source_country_path_exact": source_scan["target_count"] == 1
        and source_target["path"] == "countries/FRA",
        "source_scan_complete": source_scan["complete"],
        "source_capital_is_183": source_target["identity"].get("capital")
        == EXPECTED_CAPITAL,
        "source_armies_have_no_movement_path": all(
            not row["movement_path_fields"] for row in source_target["armies"]
        ),
        "destination_country_path_exact": destination_scan["target_count"] == 1
        and destination_target["path"] == "countries/FRA",
        "destination_scan_complete": destination_scan["complete"],
        "army_count_preserved": source_target["army_count"]
        == destination_target["army_count"]
        == rewrite["rewrite"]["armies_count"],
        "army_ids_preserved": [row["id"] for row in source_target["armies"]]
        == [row["id"] for row in destination_target["armies"]],
        "all_direct_fra_armies_at_capital": all(
            row["location"] == EXPECTED_CAPITAL
            for row in destination_target["armies"]
        ),
        "destination_armies_have_no_movement_path": all(
            not row["movement_path_fields"]
            for row in destination_target["armies"]
        ),
        "fra_identity_preserved": source_target["identity"]
        == destination_target["identity"],
        "fra_non_location_bytes_preserved": rewrite["rewrite"][
            "country_non_location_sha256_before"
        ]
        == rewrite["rewrite"]["country_non_location_sha256_after"],
        "outside_fra_country_bytes_preserved": source_scan["outside_sha256"]
        == destination_scan["outside_sha256"],
        "output_size_matches_source": source.stat().st_size
        == destination.stat().st_size,
    }
    report = {
        "schema": "r61_independence_declaration_scene_v1",
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "source": {
            "path": str(source),
            "name": source.name,
            "size_bytes": source.stat().st_size,
            "sha256": source_sha_before,
            "sha256_after": source_sha_after,
        },
        "output": {
            "path": str(destination),
            "name": destination.name,
            "size_bytes": destination.stat().st_size,
            "sha256": rewrite["sha256"],
        },
        "country_scope": {
            "path": "countries/FRA",
            "source": source_target,
            "destination": destination_target,
        },
        "transform": rewrite["rewrite"],
        "streaming": {
            "source_scan_complete": source_scan["complete"],
            "destination_scan_complete": destination_scan["complete"],
            "max_country_block_bytes": MAX_COUNTRY_BLOCK_BYTES,
        },
        "operator_prepared_fixture_only": True,
        "engine_loaded": False,
        "diplomacy_or_war_modified": False,
        "navy_modified": False,
    }
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )
    (runtime / "report.md").write_text(
        report_markdown(report), encoding="utf-8", newline=""
    )
    manifest = {
        **report,
        "generated_by": "bounded countries/FRA direct-army location transformer",
        "no_backup_or_autosave_copy": True,
    }
    (runtime / "fixture-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "output": str(destination),
                "report": str(runtime / "report.json"),
                "sha256": rewrite["sha256"],
                "checks": f"{sum(checks.values())}/{len(checks)}",
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
