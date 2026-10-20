"""Prepare the bounded R67 ally-occupation query scene.

The transformer copies the R66 non-core save byte by byte and changes only the
direct ``controller`` scalar in provinces -88, -193, and -91.  Nested history
records are never rewritten.  The output is an experiment fixture and is not
loaded or submitted by this script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from work import local_config


SAVE_NAME = "llm_diplomacy_r66_noncore_loss_20261019.eu4"
OUTPUT_NAME = "llm_diplomacy_r67_ally_occupations_20261019.eu4"
KNOWN_SOURCE_SHA256 = (
    "7cf49a5db0e366a00a5fab38799904c05cf76ed5585821a259e783ab05ec9b15"
)
KNOWN_SOURCE_BYTES = 43_011_421
DEFAULT_OUTPUT_DIR = ROOT / "work" / "runtime" / "r67-ally-occupations-scene-20261019-001"
MAX_BLOCK_BYTES = 4 * 1024 * 1024
MAX_HEADER_BYTES = 1024 * 1024

PROVINCES_RE = re.compile(rb"^[ \t]*provinces[ \t]*=[ \t]*\{")
PROVINCE_RE = re.compile(rb"^[ \t]*(?P<key>-[0-9]+)[ \t]*=[ \t]*\{")
CONTROLLER_RE = re.compile(
    rb"^(?P<prefix>[ \t]*controller[ \t]*=[ \t]*)(?P<quote>\"?)"
    rb"(?P<old>[A-Za-z0-9_]+)(?P=quote)(?P<tail>[ \t]*(?:\r?\n)?)$"
)
SCALAR_RE = re.compile(
    rb"^[ \t]*(?P<key>[A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*"
    rb"(?P<value>[^\r\n{}#]+?)[ \t]*(?:\r?\n)?$"
)
TAG_RE = re.compile(rb"^[ \t]*([A-Z0-9_]{2,4})[ \t]*(?:\r?\n)?$")

TARGETS: dict[bytes, bytes] = {
    b"-88": b"ORL",
    b"-193": b"SAV",
    b"-91": b"SAV",
}


def _brace_delta(line: bytes) -> int:
    """Count EU4 braces outside quoted strings without decoding the save."""

    delta = 0
    quoted = False
    escaped = False
    for byte in line:
        char = chr(byte)
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "{":
            delta += 1
        elif char == "}":
            delta -= 1
    return delta


def _header_date(path: Path) -> str | None:
    pattern = re.compile(rb"^[ \t]*date[ \t]*=[ \t]*(.*?)\s*$")
    consumed = 0
    with path.open("rb") as stream:
        while consumed < MAX_HEADER_BYTES:
            line = stream.readline()
            if not line:
                break
            consumed += len(line)
            match = pattern.match(line.rstrip(b"\r\n"))
            if match:
                return match.group(1).decode("latin-1")
    return None


def _resolve_source(raw: Path | None) -> Path:
    if raw is not None:
        return raw.expanduser().resolve(strict=True)
    return (local_config.user_data() / "save games" / SAVE_NAME).resolve(strict=True)


def _new_target_state(serialized_key: bytes) -> dict[str, Any]:
    return {
        "serialized_key": serialized_key.decode("ascii"),
        "province_id": int(serialized_key[1:]),
        "controller_before": None,
        "controller_after": None,
        "owner": None,
        "direct_fields": {},
        "cores": [],
        "nested_controller_lines": 0,
        "province_line_start": None,
        "province_line_end": None,
        "bytes_before": 0,
        "bytes_after": 0,
        "hash_before": hashlib.sha256(),
        "hash_after": hashlib.sha256(),
        "changed_line": None,
    }


def _transform(source: Path, destination: Path) -> dict[str, Any]:
    if destination.exists():
        raise FileExistsError(f"DESTINATION_ALREADY_EXISTS:{destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".r67tmp")
    if temporary.exists():
        raise FileExistsError(f"TEMPORARY_DESTINATION_ALREADY_EXISTS:{temporary}")

    source_hash = hashlib.sha256()
    output_hash = hashlib.sha256()
    source_date = _header_date(source)
    depth = 0
    line_count = 0
    output_bytes = 0
    unchanged_lines = 0
    changed_lines: list[dict[str, Any]] = []
    provinces_depth: int | None = None
    provinces_found = False
    provinces_closed = False
    current: dict[str, Any] | None = None
    target_depth: int | None = None
    cores_depth: int | None = None

    states = {key: _new_target_state(key) for key in TARGETS}

    def append_before(line: bytes) -> None:
        if current is None:
            return
        current["bytes_before"] += len(line)
        if current["bytes_before"] > MAX_BLOCK_BYTES:
            raise ValueError("TARGET_PROVINCE_BLOCK_OVER_4_MIB")
        current["hash_before"].update(line)

    def append_after(line: bytes) -> None:
        if current is None:
            return
        current["bytes_after"] += len(line)
        if current["bytes_after"] > MAX_BLOCK_BYTES:
            raise ValueError("TARGET_PROVINCE_BLOCK_AFTER_OVER_4_MIB")
        current["hash_after"].update(line)

    try:
        with source.open("rb") as reader, temporary.open("xb") as writer:
            for line_number, line in enumerate(reader, 1):
                line_count = line_number
                source_hash.update(line)
                before = depth

                if not provinces_found and before == 0 and PROVINCES_RE.match(line):
                    provinces_found = True
                    provinces_depth = before + _brace_delta(line)

                if (
                    provinces_found
                    and not provinces_closed
                    and current is None
                    and provinces_depth is not None
                    and before == provinces_depth
                ):
                    match = PROVINCE_RE.match(line)
                    if match and match.group("key") in TARGETS:
                        current = states[match.group("key")]
                        target_depth = before + _brace_delta(line)
                        current["province_line_start"] = line_number
                        cores_depth = None

                if current is not None:
                    append_before(line)

                transformed = line
                if current is not None and target_depth is not None:
                    # Only direct fields at the province block depth are
                    # eligible.  A history={... controller=...} line is deeper.
                    scalar = SCALAR_RE.match(line) if before == target_depth else None
                    if scalar:
                        key = scalar.group("key").decode("ascii")
                        value = scalar.group("value").strip().decode("latin-1")
                        if len(value) >= 2 and value[0] == value[-1] == '"':
                            value = value[1:-1]
                        current["direct_fields"].setdefault(key, value)
                        if key == "owner":
                            current["owner"] = value

                    controller = CONTROLLER_RE.match(line) if before == target_depth else None
                    if controller:
                        old = controller.group("old")
                        new = TARGETS[current["serialized_key"].encode("ascii")]
                        current["controller_before"] = old.decode("ascii")
                        current["controller_after"] = new.decode("ascii")
                        quote = controller.group("quote")
                        tail = controller.group("tail")
                        transformed = controller.group("prefix") + quote + new + quote + tail
                        changed = {
                            "line_number": line_number,
                            "province_id": current["province_id"],
                            "path": f"provinces/{current['serialized_key']}/controller",
                            "before_latin1": line.decode("latin-1").rstrip("\r\n"),
                            "after_latin1": transformed.decode("latin-1").rstrip("\r\n"),
                            "old_controller": old.decode("ascii"),
                            "new_controller": new.decode("ascii"),
                            "owner": current.get("owner"),
                        }
                        current["changed_line"] = changed
                        changed_lines.append(changed)
                    elif b"controller" in line and before > target_depth:
                        current["nested_controller_lines"] += 1

                    if cores_depth is None and before == target_depth and re.match(
                        rb"^[ \t]*cores[ \t]*=[ \t]*\{", line
                    ):
                        cores_depth = before + _brace_delta(line)
                    elif cores_depth is not None and before == cores_depth:
                        tag = TAG_RE.match(line)
                        if tag:
                            current["cores"].append(tag.group(1).decode("ascii"))

                if transformed == line:
                    unchanged_lines += 1
                writer.write(transformed)
                output_hash.update(transformed)
                output_bytes += len(transformed)
                if current is not None:
                    append_after(transformed)

                depth += _brace_delta(line)
                if cores_depth is not None and depth < cores_depth and before >= cores_depth:
                    cores_depth = None
                if current is not None and target_depth is not None and depth < target_depth and before >= target_depth:
                    current["province_line_end"] = line_number
                    current = None
                    target_depth = None
                    cores_depth = None
                if provinces_found and not provinces_closed and provinces_depth is not None and depth < provinces_depth and before >= provinces_depth:
                    provinces_closed = True

        if not provinces_found or not provinces_closed:
            raise ValueError("PROVINCES_BLOCK_NOT_COMPLETE")
        if current is not None:
            raise ValueError("TARGET_PROVINCE_BLOCK_NOT_COMPLETE")
        if depth != 0:
            raise ValueError(f"FINAL_BRACE_DEPTH:{depth}")
        if len(changed_lines) != len(TARGETS):
            raise ValueError(f"TARGET_CONTROLLER_LINE_COUNT:{len(changed_lines)}")
        if any(states[key]["changed_line"] is None for key in TARGETS):
            raise ValueError("TARGET_CONTROLLER_LINE_MISSING")
        os.replace(temporary, destination)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise

    source_size = source.stat().st_size
    destination_size = destination.stat().st_size
    return {
        "source": {
            "path": str(source),
            "known_sha256": KNOWN_SOURCE_SHA256,
            "sha256": source_hash.hexdigest(),
            "sha256_matches_known": source_hash.hexdigest() == KNOWN_SOURCE_SHA256,
            "size_bytes": source_size,
            "known_size_bytes": KNOWN_SOURCE_BYTES,
            "date": source_date,
        },
        "destination": {
            "path": str(destination),
            "sha256": output_hash.hexdigest(),
            "size_bytes": destination_size,
            "name": destination.name,
        },
        "targets": {
            state["serialized_key"]: {
                key: value
                for key, value in state.items()
                if key not in {"hash_before", "hash_after"}
            }
            | {
                "sha256_before": state["hash_before"].hexdigest(),
                "sha256_after": state["hash_after"].hexdigest(),
            }
            for state in states.values()
        },
        "mutation": {
            "changed_line_count": len(changed_lines),
            "changed_lines": changed_lines,
            "target_count": len(TARGETS),
        },
        "stream": {
            "line_count": line_count,
            "output_bytes": output_bytes,
            "source_bytes_seen": source_size,
            "destination_bytes": destination_size,
            "only_three_lines_changed": len(changed_lines) == 3,
            "all_other_bytes_forwarded": unchanged_lines == line_count - 3,
            "brace_balance": depth == 0,
            "provinces_block_complete": provinces_closed,
        },
    }


def _write_report(output_dir: Path, report: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# R67 盟友占领场景",
        "",
        f"源存档：`{report['source']['path']}`。目标存档：`{report['destination']['path']}`。",
        "",
        "流式复制只修改三个省份直接块的 controller：",
    ]
    for changed in report["mutation"]["changed_lines"]:
        lines.append(
            f"- 省份 {changed['province_id']}：`{changed['before_latin1']}` → "
            f"`{changed['after_latin1']}`；owner={changed['owner']}。"
        )
    lines.extend(
        [
            "",
            f"源 SHA-256 `{report['source']['sha256']}`（与已知 R66 SHA 比对一次）；"
            f"目标 SHA-256 `{report['destination']['sha256']}`。",
            "",
            f"检查：`{json.dumps(report['checks'], ensure_ascii=False, sort_keys=True)}`。",
            "",
            "这是人为准备的实验背景；未启动游戏、未载入存档、未投递外交请求。",
            "",
        ]
    )
    (output_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    source = _resolve_source(args.source)
    destination = (
        args.destination.expanduser().resolve()
        if args.destination is not None
        else (local_config.user_data() / "save games" / OUTPUT_NAME).resolve()
    )
    output_dir = args.output_dir.expanduser().resolve()
    if output_dir.exists():
        raise FileExistsError(f"RUNTIME_OUTPUT_ALREADY_EXISTS:{output_dir}")
    mutation = _transform(source, destination)
    checks = {
        "source_exists": source.is_file(),
        "source_known_size": mutation["source"]["size_bytes"] == KNOWN_SOURCE_BYTES,
        "source_sha256_matches_known": mutation["source"]["sha256_matches_known"],
        "destination_exists": destination.is_file(),
        "target_count_three": mutation["mutation"]["target_count"] == 3,
        "changed_line_count_three": mutation["mutation"]["changed_line_count"] == 3,
        "only_three_lines_changed": mutation["stream"]["only_three_lines_changed"],
        "all_other_bytes_forwarded": mutation["stream"]["all_other_bytes_forwarded"],
        "provinces_block_complete": mutation["stream"]["provinces_block_complete"],
        "brace_balance": mutation["stream"]["brace_balance"],
        "target_blocks_under_4_mib": all(
            item["bytes_before"] <= MAX_BLOCK_BYTES and item["bytes_after"] <= MAX_BLOCK_BYTES
            for item in mutation["targets"].values()
        ),
        "controllers_changed_to_requested_tags": all(
            item["controller_after"] == TARGETS[item["serialized_key"].encode("ascii")].decode("ascii")
            for item in mutation["targets"].values()
        ),
        "owners_recorded": all(item.get("owner") for item in mutation["targets"].values()),
        "core_dev_fields_recorded": all(
            "cores" in item and "base_tax" in item["direct_fields"]
            and "base_production" in item["direct_fields"]
            and "base_manpower" in item["direct_fields"]
            for item in mutation["targets"].values()
        ),
        "date_preserved_by_byte_forwarding": True,
        "war_preserved_by_byte_forwarding": True,
    }
    report: dict[str, Any] = {
        "schema": "r67_ally_occupations_scene_v1",
        "status": "prepared" if all(checks.values()) else "failed",
        **mutation,
        "checks": checks,
        "scene_loaded": False,
        "business_submitted": False,
        "note": "人工准备的盟友占领实验背景；未启动游戏、未保存游戏状态、未投递外交请求。",
    }
    _write_report(output_dir, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "destination": str(destination),
                "destination_sha256": mutation["destination"]["sha256"],
                "output_dir": str(output_dir),
                "changed_lines": mutation["mutation"]["changed_lines"],
                "failed_checks": [key for key, value in checks.items() if value is not True],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "prepared" else 1


if __name__ == "__main__":
    raise SystemExit(main())
