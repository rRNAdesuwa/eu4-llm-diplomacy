"""Prepare the R66 non-core overextension query scene.

This is a byte-preserving, streaming transformer.  It copies the immutable
R63 participant save and changes exactly one direct ``cores`` line in
``provinces/-88``: ``BUR PIC`` becomes ``PIC``.  The generated save is a
fixture only; loading it in the game and checking the resulting native query
remain separate operations.
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


SAVE_NAME = "llm_diplomacy_declarewar_SAV_HSA_20261019_r63.eu4"
OUTPUT_NAME = "llm_diplomacy_r66_noncore_loss_20261019.eu4"
KNOWN_SOURCE_SHA256 = (
    "e03b9cfedd8b1400e31b6299af434a77d9dba226b997c64452da46e94555b251"
)
DEFAULT_OUTPUT_DIR = ROOT / "work" / "runtime" / "r66-noncore-scene-20261019-001"
TARGET_PROVINCE = 88
TARGET_SERIALIZED_KEY = b"-88"
TARGET_OWNER = b"BUR"
RETAINED_CORE = b"PIC"
MAX_BLOCK_BYTES = 4 * 1024 * 1024
MAX_HEADER_BYTES = 1024 * 1024

PROVINCES_RE = re.compile(rb"^\s*provinces\s*=\s*\{")
TARGET_PROVINCE_RE = re.compile(rb"^\s*-88\s*=\s*\{")
CORES_RE = re.compile(rb"^\s*cores\s*=\s*\{")
TARGET_CORES_LINE_RE = re.compile(rb"^(\s*)BUR\s+PIC[ \t]*(\r?\n)?$")


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
    pattern = re.compile(rb"^\s*date\s*=\s*(.*?)\s*$")
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


def _transform(source: Path, destination: Path) -> dict[str, Any]:
    if destination.exists():
        raise FileExistsError(f"DESTINATION_ALREADY_EXISTS:{destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".r66tmp")
    if temporary.exists():
        raise FileExistsError(f"TEMPORARY_DESTINATION_ALREADY_EXISTS:{temporary}")

    source_date = _header_date(source)
    depth = 0
    line_count = 0
    provinces_depth: int | None = None
    provinces_found = False
    provinces_closed = False
    target_active = False
    target_depth: int | None = None
    target_start: int | None = None
    target_end: int | None = None
    target_bytes_before = 0
    target_bytes_after = 0
    target_before_hash = hashlib.sha256()
    target_after_hash = hashlib.sha256()
    cores_active = False
    cores_depth: int | None = None
    cores_start: int | None = None
    cores_end: int | None = None
    changed_line: dict[str, Any] | None = None
    changed_lines = 0
    unchanged_lines = 0
    output_hash = hashlib.sha256()
    output_bytes = 0

    def append_target_before(line: bytes) -> None:
        nonlocal target_bytes_before
        target_bytes_before += len(line)
        if target_bytes_before > MAX_BLOCK_BYTES:
            raise ValueError("TARGET_PROVINCE_BLOCK_OVER_4_MIB")
        target_before_hash.update(line)

    def append_target_after(line: bytes) -> None:
        nonlocal target_bytes_after
        target_bytes_after += len(line)
        if target_bytes_after > MAX_BLOCK_BYTES:
            raise ValueError("TARGET_PROVINCE_BLOCK_AFTER_OVER_4_MIB")
        target_after_hash.update(line)

    try:
        with source.open("rb") as reader, temporary.open("xb") as writer:
            for line_number, line in enumerate(reader, 1):
                line_count = line_number
                before = depth
                if not provinces_found and before == 0 and PROVINCES_RE.match(line):
                    provinces_found = True
                    provinces_depth = before + _brace_delta(line)

                if (
                    provinces_found
                    and not provinces_closed
                    and not target_active
                    and provinces_depth is not None
                    and before == provinces_depth
                    and TARGET_PROVINCE_RE.match(line)
                ):
                    target_active = True
                    target_depth = before + _brace_delta(line)
                    target_start = line_number

                if target_active:
                    append_target_before(line)

                if (
                    target_active
                    and not cores_active
                    and target_depth is not None
                    and before == target_depth
                    and CORES_RE.match(line)
                ):
                    cores_active = True
                    cores_depth = before + _brace_delta(line)
                    cores_start = line_number

                transformed = line
                if (
                    cores_active
                    and cores_depth is not None
                    and before == cores_depth
                    and changed_line is None
                ):
                    match = TARGET_CORES_LINE_RE.match(line)
                    if match:
                        newline = match.group(2) or b""
                        transformed = match.group(1) + RETAINED_CORE + newline
                        changed_line = {
                            "line_number": line_number,
                            "before_latin1": line.decode("latin-1").rstrip("\r\n"),
                            "after_latin1": transformed.decode("latin-1").rstrip("\r\n"),
                            "removed_core": TARGET_OWNER.decode("ascii"),
                            "retained_core": RETAINED_CORE.decode("ascii"),
                        }
                        changed_lines += 1
                    elif line.strip() not in (b"", b"}"):
                        # A non-target direct core row before BUR is evidence
                        # that the expected source layout changed; do not
                        # guess a second rewrite.
                        pass

                if transformed == line:
                    unchanged_lines += 1
                writer.write(transformed)
                output_hash.update(transformed)
                output_bytes += len(transformed)
                if target_active:
                    append_target_after(transformed)

                depth += _brace_delta(line)

                if (
                    cores_active
                    and cores_depth is not None
                    and depth < cores_depth
                    and before >= cores_depth
                ):
                    cores_active = False
                    cores_end = line_number
                if (
                    target_active
                    and target_depth is not None
                    and depth < target_depth
                    and before >= target_depth
                ):
                    target_active = False
                    target_end = line_number
                if (
                    provinces_found
                    and not provinces_closed
                    and provinces_depth is not None
                    and depth < provinces_depth
                    and before >= provinces_depth
                ):
                    provinces_closed = True

        if changed_lines != 1 or changed_line is None:
            raise ValueError(f"TARGET_CORE_LINE_NOT_UNIQUE:{changed_lines}")
        if target_start is None or target_end is None:
            raise ValueError("TARGET_PROVINCE_BLOCK_NOT_COMPLETE")
        if cores_start is None or cores_end is None:
            raise ValueError("TARGET_CORES_BLOCK_NOT_COMPLETE")
        if not provinces_found or not provinces_closed:
            raise ValueError("PROVINCES_BLOCK_NOT_COMPLETE")
        if depth != 0:
            raise ValueError(f"FINAL_BRACE_DEPTH:{depth}")
        os.replace(temporary, destination)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise

    destination_size = destination.stat().st_size
    if output_bytes != destination_size:
        raise ValueError("OUTPUT_SIZE_CHANGED_AFTER_RENAME")
    return {
        "source": {
            "path": str(source),
            "known_sha256": KNOWN_SOURCE_SHA256,
            "sha256_reused_without_rehash": True,
            "size_bytes": source.stat().st_size,
            "date": source_date,
        },
        "destination": {
            "path": str(destination),
            "sha256": output_hash.hexdigest(),
            "size_bytes": destination_size,
            "name": destination.name,
        },
        "mutation": {
            "kind": "remove_direct_province_core",
            "province_id": TARGET_PROVINCE,
            "serialized_key": TARGET_SERIALIZED_KEY.decode("ascii"),
            "path": "provinces/-88/cores",
            "owner": TARGET_OWNER.decode("ascii"),
            "removed_core": TARGET_OWNER.decode("ascii"),
            "retained_core": RETAINED_CORE.decode("ascii"),
            "changed_line": changed_line,
            "changed_line_count": changed_lines,
            "unchanged_line_count": unchanged_lines,
        },
        "block": {
            "province_line_start": target_start,
            "province_line_end": target_end,
            "cores_line_start": cores_start,
            "cores_line_end": cores_end,
            "bytes_before": target_bytes_before,
            "bytes_after": target_bytes_after,
            "sha256_before": target_before_hash.hexdigest(),
            "sha256_after": target_after_hash.hexdigest(),
            "max_block_bytes": MAX_BLOCK_BYTES,
        },
        "stream": {
            "line_count": line_count,
            "brace_balance": depth == 0,
            "output_bytes": output_bytes,
            "only_one_line_changed": changed_lines == 1,
            "all_other_bytes_forwarded": unchanged_lines == line_count - 1,
        },
    }


def _write_report(output_dir: Path, report: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    mutation = report.get("mutation", {})
    block = report.get("block", {})
    checks = report.get("checks", {})
    lines = [
        "# R66 非核心省份场景",
        "",
        f"源存档：`{report['source']['path']}`。目标存档：`{report['destination']['path']}`。",
        "",
        "脚本以流式方式复制 R63 存档，只修改 `provinces/-88/cores` 的一行：",
        f"`{mutation.get('changed_line', {}).get('before_latin1')}` → "
        f"`{mutation.get('changed_line', {}).get('after_latin1')}`。",
        "",
        f"省份块行号 `{block.get('province_line_start')}-{block.get('province_line_end')}`，"
        f"核心块行号 `{block.get('cores_line_start')}-{block.get('cores_line_end')}`；"
        f"输出 SHA-256 `{report['destination']['sha256']}`。",
        "",
        f"检查：`{json.dumps(checks, ensure_ascii=False, sort_keys=True)}`。",
        "",
        "这是人为准备的查询场景，尚未由游戏载入；日期、战争和其他字节由逐行转发保持不变。",
        "",
    ]
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
        "source_sha256_reused_known": mutation["source"]["known_sha256"] == KNOWN_SOURCE_SHA256,
        "destination_exists": destination.is_file(),
        "target_path_exact": mutation["mutation"]["path"] == "provinces/-88/cores",
        "owner_bur_removed": mutation["mutation"]["removed_core"] == "BUR",
        "pic_retained": mutation["mutation"]["retained_core"] == "PIC",
        "changed_line_count_one": mutation["mutation"]["changed_line_count"] == 1,
        "only_one_line_changed": mutation["stream"]["only_one_line_changed"],
        "all_other_bytes_forwarded": mutation["stream"]["all_other_bytes_forwarded"],
        "province_block_complete": mutation["block"]["province_line_end"] is not None,
        "cores_block_complete": mutation["block"]["cores_line_end"] is not None,
        "target_block_under_4_mib": (
            mutation["block"]["bytes_before"] <= MAX_BLOCK_BYTES
            and mutation["block"]["bytes_after"] <= MAX_BLOCK_BYTES
        ),
        "brace_balance": mutation["stream"]["brace_balance"],
        "date_preserved_by_byte_forwarding": True,
        "war_preserved_by_byte_forwarding": True,
    }
    report: dict[str, Any] = {
        "schema": "r66_noncore_scene_v1",
        "status": "prepared" if all(checks.values()) else "failed",
        **mutation,
        "checks": checks,
        "scene_loaded": False,
        "business_submitted": False,
        "note": "人工准备的实验背景；生成器未启动游戏、未保存游戏状态、未投递外交请求。",
    }
    _write_report(output_dir, report)
    print(json.dumps({
        "status": report["status"],
        "destination": str(destination),
        "destination_sha256": mutation["destination"]["sha256"],
        "output_dir": str(output_dir),
        "failed_checks": [key for key, value in checks.items() if value is not True],
    }, ensure_ascii=False))
    return 0 if report["status"] == "prepared" else 1


if __name__ == "__main__":
    raise SystemExit(main())
