"""Bounded PE string and RIP-relative LEA candidate scanner.

This tool stops at byte-level candidates. An ASCII/NUL match and an x64
RIP-relative LEA shape do not prove a live UI reference or Declare War
semantics. The executable is streamed in chunks no larger than CHUNK_SIZE.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Iterable, Iterator


CHUNK_SIZE = 1024 * 1024
EXPECTED_SHA256 = "b23fa0e1f698d31b01cdd1c3817a675805d8c6286cb66f9c231e6e2a42544d77"
DEFAULT_TARGETS = (
    "DeclareWarDialog",
    "CONFIRM_DECLARE_WAR_TITLE",
    "GFX_diplomacy_action_declarewar",
)
MAX_CANDIDATES = 4096


class ScanError(RuntimeError):
    """Raised when the target is not the bounded PE shape this tool expects."""


def _read_at(stream, file_size: int, offset: int, length: int) -> bytes:
    if offset < 0 or length < 0 or offset + length > file_size:
        raise ScanError(f"read outside file: offset={offset:#x} length={length:#x}")
    stream.seek(offset)
    value = stream.read(length)
    if len(value) != length:
        raise ScanError("short PE metadata read")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _section_for_rva(sections: list[dict], rva: int, *, file_backed: bool = False) -> dict | None:
    for section in sections:
        limit = section["virtual_address"] + max(section["virtual_size"], section["raw_size"])
        if section["virtual_address"] <= rva < limit:
            if file_backed and rva >= section["virtual_address"] + section["raw_size"]:
                continue
            return section
    return None


def _section_for_file_offset(sections: list[dict], offset: int) -> dict | None:
    for section in sections:
        if section["raw_pointer"] <= offset < section["raw_pointer"] + section["raw_size"]:
            return section
    return None


def _rva_for_file_offset(sections: list[dict], offset: int) -> int | None:
    section = _section_for_file_offset(sections, offset)
    if section is None:
        return None
    return section["virtual_address"] + offset - section["raw_pointer"]


def _file_offset_for_rva(sections: list[dict], rva: int) -> int | None:
    section = _section_for_rva(sections, rva, file_backed=True)
    if section is None:
        return None
    offset = section["raw_pointer"] + rva - section["virtual_address"]
    if offset >= section["raw_pointer"] + section["raw_size"]:
        return None
    return offset


def parse_pe(path: Path) -> dict:
    """Read bounded PE headers, sections, and executable unwind ranges."""

    file_size = path.stat().st_size
    with path.open("rb") as stream:
        dos = _read_at(stream, file_size, 0, 64)
        if dos[:2] != b"MZ":
            raise ScanError("target is not an MZ PE")
        pe_offset = struct.unpack_from("<I", dos, 60)[0]
        if not 64 <= pe_offset <= 1024 * 1024:
            raise ScanError("PE header offset is outside the bounded range")
        coff = _read_at(stream, file_size, pe_offset, 24)
        if coff[:4] != b"PE\0\0":
            raise ScanError("missing PE signature")
        machine, section_count = struct.unpack_from("<HH", coff, 4)
        optional_size = struct.unpack_from("<H", coff, 20)[0]
        if machine != 0x8664:
            raise ScanError(f"expected x64 PE, got machine {machine:#x}")
        if not 1 <= section_count <= 96 or not 144 <= optional_size <= 4096:
            raise ScanError("section count or optional header size is outside bounds")
        optional_offset = pe_offset + 24
        optional = _read_at(stream, file_size, optional_offset, optional_size)
        if struct.unpack_from("<H", optional, 0)[0] != 0x20B:
            raise ScanError("expected PE32+ optional header")
        image_base = struct.unpack_from("<Q", optional, 24)[0]
        directory_count = struct.unpack_from("<I", optional, 108)[0]
        if directory_count < 4:
            raise ScanError("PE has no exception data directory")
        exception_rva, exception_size = struct.unpack_from("<II", optional, 112 + 3 * 8)
        if not exception_rva or not exception_size or exception_size % 12:
            raise ScanError("invalid exception directory")
        if exception_size > 8 * 1024 * 1024:
            raise ScanError("exception directory exceeds bounded size")

        section_table = optional_offset + optional_size
        sections: list[dict] = []
        for index in range(section_count):
            raw = _read_at(stream, file_size, section_table + index * 40, 40)
            name = raw[:8].split(b"\0", 1)[0].decode("ascii", errors="replace")
            virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from("<IIII", raw, 8)
            characteristics = struct.unpack_from("<I", raw, 36)[0]
            if raw_pointer + raw_size > file_size:
                raise ScanError(f"section {name!r} exceeds file bounds")
            sections.append({
                "name": name,
                "virtual_size": virtual_size,
                "virtual_address": virtual_address,
                "raw_size": raw_size,
                "raw_pointer": raw_pointer,
                "characteristics": characteristics,
                "executable": bool(characteristics & 0x20000000),
            })

        exception_offset = _file_offset_for_rva(sections, exception_rva)
        exception_section = _section_for_rva(sections, exception_rva, file_backed=True)
        if exception_offset is None or exception_section is None:
            raise ScanError("exception directory is not file-backed")

        functions: list[tuple[int, int]] = []
        stream.seek(exception_offset)
        for _ in range(exception_size // 12):
            row = stream.read(12)
            if len(row) != 12:
                raise ScanError("short RUNTIME_FUNCTION row")
            begin, end, _unwind = struct.unpack("<III", row)
            if begin >= end:
                continue
            owner = _section_for_rva(sections, begin, file_backed=True)
            if owner is not None and owner["executable"]:
                functions.append((begin, end))
        functions.sort()

    return {
        "file_size": file_size,
        "image_base": image_base,
        "pe_offset": pe_offset,
        "machine": machine,
        "sections": sections,
        "exception_directory": {
            "rva": exception_rva,
            "size": exception_size,
            "file_offset": exception_offset,
            "section": exception_section["name"],
        },
        "runtime_functions": functions,
    }


def _iter_file_chunks(path: Path, start: int, size: int) -> Iterator[tuple[int, bytes]]:
    """Yield file chunks with a hard one MiB read ceiling."""

    remaining = size
    offset = start
    with path.open("rb") as stream:
        stream.seek(start)
        while remaining:
            amount = min(CHUNK_SIZE, remaining)
            data = stream.read(amount)
            if len(data) != amount:
                raise ScanError("short section read")
            yield offset, data
            offset += amount
            remaining -= amount


def _find_pattern_offsets(path: Path, pattern: bytes, *, start: int = 0, size: int | None = None) -> list[int]:
    file_size = path.stat().st_size
    if size is None:
        size = file_size - start
    if start < 0 or size < 0 or start + size > file_size:
        raise ScanError("pattern scan range is outside file")
    found: set[int] = set()
    tail = b""
    for chunk_offset, data in _iter_file_chunks(path, start, size):
        block = tail + data
        block_base = chunk_offset - len(tail)
        cursor = 0
        while True:
            position = block.find(pattern, cursor)
            if position < 0:
                break
            absolute = block_base + position
            if start <= absolute < start + size:
                found.add(absolute)
            cursor = position + 1
        tail = block[-(len(pattern) - 1):] if len(pattern) > 1 else b""
    return sorted(found)


def _file_offset_for_function(functions: list[tuple[int, int]], begin: int, sections: list[dict]) -> int | None:
    return _file_offset_for_rva(sections, begin)


def _find_lea_candidates(
    path: Path,
    text: dict,
    all_sections: list[dict],
    string_by_rva: dict[int, list[dict]],
    functions: list[tuple[int, int]],
    max_candidates: int,
) -> tuple[list[dict], bool, int]:
    """Find direct x64 LEA byte shapes whose target is a matched string."""

    starts = [begin for begin, _end in functions]
    candidates: list[dict] = []
    total = 0
    tail = b""
    for chunk_offset, data in _iter_file_chunks(path, text["raw_pointer"], text["raw_size"]):
        block = tail + data
        block_base = chunk_offset - len(tail)
        for index in range(max(0, len(tail) - 8), len(block) - 5):
            if block[index] != 0x8D:
                continue
            modrm = block[index + 1]
            if modrm & 0xC7 != 0x05:
                continue
            opcode_file_offset = block_base + index
            if not text["raw_pointer"] <= opcode_file_offset < text["raw_pointer"] + text["raw_size"]:
                continue
            opcode_rva = text["virtual_address"] + opcode_file_offset - text["raw_pointer"]
            displacement = struct.unpack_from("<i", block, index + 2)[0]
            has_address_prefix = index > 0 and block[index - 1] == 0x67
            instruction_length = 7 if has_address_prefix else 6
            target_rva = opcode_rva + instruction_length + displacement
            matches = string_by_rva.get(target_rva)
            if not matches:
                continue
            total += len(matches)
            function_index = bisect.bisect_right(starts, opcode_rva) - 1
            function = (
                functions[function_index]
                if function_index >= 0 and functions[function_index][0] <= opcode_rva < functions[function_index][1]
                else None
            )
            instruction_start = index - (1 if has_address_prefix else 0)
            instruction_bytes = block[instruction_start:index + instruction_length].hex()
            for match in matches:
                if len(candidates) >= max_candidates:
                    break
                candidates.append({
                    "string": match["string"],
                    "string_file_offset": match["file_offset"],
                    "string_rva": target_rva,
                    "lea_file_offset": opcode_file_offset - (1 if has_address_prefix else 0),
                    "lea_opcode_file_offset": opcode_file_offset,
                    "lea_rva": opcode_rva - (1 if has_address_prefix else 0),
                    "instruction_hex": instruction_bytes,
                    "displacement": displacement,
                    "function_begin_rva": function[0] if function else None,
                    "function_end_rva": function[1] if function else None,
                    "function_entry_file_offset": _file_offset_for_function(functions, function[0], all_sections) if function else None,
                    "candidate_basis": "direct_rip_relative_lea_byte_shape",
                })
        tail = block[-8:]
    return candidates, total > len(candidates), total


def scan(path: Path, targets: Iterable[str], max_candidates: int = MAX_CANDIDATES) -> dict:
    if max_candidates < 1 or max_candidates > MAX_CANDIDATES:
        raise ScanError(f"max_candidates must be between 1 and {MAX_CANDIDATES}")
    if not path.is_file():
        raise ScanError(f"binary does not exist: {path}")
    binary_hash = _sha256(path)
    if binary_hash != EXPECTED_SHA256:
        raise ScanError(f"binary SHA-256 mismatch: expected {EXPECTED_SHA256}, got {binary_hash}")
    pe = parse_pe(path)
    text_sections = [section for section in pe["sections"] if section["name"] == ".text" and section["executable"]]
    if len(text_sections) != 1:
        raise ScanError(f"expected one executable .text section, found {len(text_sections)}")
    text = text_sections[0]

    target_names = tuple(dict.fromkeys(targets))
    target_occurrences: dict[str, list[dict]] = {}
    string_by_rva: dict[int, list[dict]] = {}
    for name in target_names:
        if not name or "\0" in name or any(ord(char) > 0x7F for char in name):
            raise ScanError(f"target must be non-empty ASCII without NUL: {name!r}")
        pattern = name.encode("ascii") + b"\0"
        occurrences = []
        for file_offset in _find_pattern_offsets(path, pattern):
            rva = _rva_for_file_offset(pe["sections"], file_offset)
            section = _section_for_file_offset(pe["sections"], file_offset)
            row = {
                "file_offset": file_offset,
                "rva": rva,
                "section": section["name"] if section else None,
                "length_with_nul": len(pattern),
            }
            occurrences.append(row)
            if rva is not None:
                string_by_rva.setdefault(rva, []).append({"string": name, **row})
        target_occurrences[name] = occurrences

    candidates, candidate_truncated, candidate_total = _find_lea_candidates(
        path, text, pe["sections"], string_by_rva, pe["runtime_functions"], max_candidates
    )
    sections = [
        {key: section[key] for key in (
            "name", "virtual_address", "virtual_size", "raw_pointer", "raw_size", "characteristics", "executable"
        )}
        for section in pe["sections"]
    ]
    return {
        "scanner": {
            "name": "find_native_string_references",
            "version": 1,
            "chunk_size": CHUNK_SIZE,
            "max_candidates": max_candidates,
            "candidate_basis": "ASCII/NUL occurrence plus direct RIP-relative LEA byte shape; not disassembly proof",
        },
        "binary": {
            "path": str(path.resolve()),
            "size": pe["file_size"],
            "sha256": binary_hash,
            "expected_sha256": EXPECTED_SHA256,
            "verified": True,
            "machine": f"0x{pe['machine']:x}",
            "image_base": f"0x{pe['image_base']:x}",
        },
        "pe": {
            "pe_header_file_offset": pe["pe_offset"],
            "sections": sections,
            "exception_directory": pe["exception_directory"],
            "runtime_function_count": len(pe["runtime_functions"]),
            "text_section": {key: text[key] for key in (
                "name", "virtual_address", "virtual_size", "raw_pointer", "raw_size", "characteristics", "executable"
            )},
        },
        "targets": target_occurrences,
        "rip_relative_lea_candidates": candidates,
        "summary": {
            "target_count": len(target_names),
            "string_occurrence_count": sum(len(rows) for rows in target_occurrences.values()),
            "candidate_count": len(candidates),
            "candidate_match_count_before_limit": candidate_total,
            "candidate_truncated": candidate_truncated,
        },
        "limitations": [
            "A byte match is not proof of a live reference, UI selector, factory, or Declare War semantic callsite.",
            "The detector recognizes direct x64 LEA byte shapes only; indirect references, MOV/address tables, UTF-16 strings and data-driven UI references are outside this pass.",
            "RUNTIME_FUNCTION/.pdata containment supplies a shipped unwind range and function entry candidate; it does not establish a complete semantic function body or callable ABI.",
            "Every candidate requires disassembly or REA confirmation before use in a native integration.",
        ],
    }


def _format_hex(value: int | None) -> str:
    return "unknown" if value is None else f"0x{value:x}"


def write_markdown(result: dict, path: Path) -> None:
    lines = [
        "# Declare War 字符串引用候选扫描",
        "",
        "本报告只记录已核对 PE 中的 ASCII/NUL 字符串位置和 .text 内直接 RIP-relative LEA 字节形状。候选需要后续反汇编或 REA 确认，不能把本报告当作 UI selector、工厂或业务语义证据。扫描过程分块读取，单次读取不超过 1 MiB。",
        "",
        f"- 二进制 SHA-256：{result['binary']['sha256']}（与已验证 EU4 版本一致）",
        f"- 二进制大小：{result['binary']['size']} bytes",
        f"- .text：RVA {_format_hex(result['pe']['text_section']['virtual_address'])}，文件偏移 {_format_hex(result['pe']['text_section']['raw_pointer'])}，大小 {result['pe']['text_section']['raw_size']} bytes",
        f"- .pdata：RVA {_format_hex(result['pe']['exception_directory']['rva'])}，包含 {result['pe']['runtime_function_count']} 个可执行 RUNTIME_FUNCTION 范围",
        f"- 候选总数：{result['summary']['candidate_count']}（限额前匹配数 {result['summary']['candidate_match_count_before_limit']}）",
        "",
        "## 字符串位置",
        "",
        "| 字符串 | 文件偏移 | RVA | 节 |",
        "| --- | ---: | ---: | --- |",
    ]
    for name, occurrences in result["targets"].items():
        if not occurrences:
            lines.append(f"| {name} | 未找到 | — | — |")
        else:
            for row in occurrences:
                lines.append(f"| {name} | {_format_hex(row['file_offset'])} | {_format_hex(row['rva'])} | {row['section']} |")
    lines.extend(["", "## 直接 RIP-relative LEA 候选", "", "| 字符串 | 字符串 RVA | LEA RVA | 所在函数范围 | 指令字节 |", "| --- | ---: | ---: | --- | --- |"])
    if not result["rip_relative_lea_candidates"]:
        lines.append("| 无直接候选 | — | — | — | — |")
    else:
        for row in result["rip_relative_lea_candidates"]:
            function = f"{_format_hex(row['function_begin_rva'])}–{_format_hex(row['function_end_rva'])}"
            lines.append(f"| {row['string']} | {_format_hex(row['string_rva'])} | {_format_hex(row['lea_rva'])} | {function} | {row['instruction_hex']} |")
    lines.extend([
        "",
        "## 使用边界",
        "",
        "- 字符串重复位置全部保留；本轮目标是字节级候选，不判断字符串是否被代码使用。",
        "- .pdata 范围只提供函数入口候选和 unwind 范围；它不证明调用约定、函数完整语义或 UI 行为。",
        "- 本报告没有执行游戏、没有注入进程、没有修改 native/REA/production 文件。",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, help="verified EU4 eu4.exe; defaults to local.env EU4_GAME_ROOT")
    parser.add_argument("--target", action="append", dest="targets", help="ASCII string to find; repeatable")
    parser.add_argument("--max-candidates", type=int, default=MAX_CANDIDATES)
    parser.add_argument("--output", type=Path, default=Path("work/runtime/declarewar-string-references-20261016-001"))
    args = parser.parse_args(argv)
    if args.binary is None:
        work_directory = Path(__file__).resolve().parent
        sys.path.insert(0, str(work_directory))
        from local_config import game_exe
        binary = game_exe()
    else:
        binary = args.binary.expanduser()
    targets = tuple(args.targets) if args.targets else DEFAULT_TARGETS
    result = scan(binary, targets, args.max_candidates)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(result, args.output / "report.md")
    print(json.dumps({
        "output": str(args.output.resolve()),
        "binary_sha256": result["binary"]["sha256"],
        "string_occurrences": result["summary"]["string_occurrence_count"],
        "rip_relative_lea_candidates": result["summary"]["candidate_count"],
        "candidate_truncated": result["summary"]["candidate_truncated"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
