"""Bounded PE xref scan for the native receiver clone routine.

The scanner reads section bytes in 1 MiB chunks.  It does not materialize the
executable or a disassembly dump in memory; its purpose is only to identify
direct rel32 call/jump sites and the containing .pdata entry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

try:
    from work.local_config import game_exe
except ModuleNotFoundError:  # direct ``python work/script.py`` invocation
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from work.local_config import game_exe


IMAGE_BASE_DEFAULT = 0x140000000
TARGET_RVA = 0x15800C0
GENERIC_RVA = 0x4E7C80
CHUNK = 1024 * 1024


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _u64(data: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


def _pe_layout(path: Path) -> tuple[int, list[dict[str, int | str]]]:
    with path.open("rb") as stream:
        stream.seek(0x3C)
        pe_offset = _u32(stream.read(4), 0)
        stream.seek(pe_offset)
        if stream.read(4) != b"PE\0\0":
            raise ValueError("not a PE image")
        coff = stream.read(20)
        section_count = _u16(coff, 2)
        optional_size = _u16(coff, 16)
        optional_offset = pe_offset + 24
        stream.seek(optional_offset)
        magic = _u16(stream.read(2), 0)
        if magic != 0x20B:
            raise ValueError(f"expected PE32+, got 0x{magic:x}")
        stream.seek(optional_offset + 24)
        image_base = _u64(stream.read(8), 0)
        sections_offset = optional_offset + optional_size
        sections: list[dict[str, int | str]] = []
        for index in range(section_count):
            stream.seek(sections_offset + index * 40)
            raw = stream.read(40)
            name = raw[:8].rstrip(b"\0").decode("ascii", "replace")
            virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from(
                "<IIII", raw, 8
            )
            sections.append(
                {
                    "name": name,
                    "virtual_address": virtual_address,
                    "virtual_size": virtual_size,
                    "raw_size": raw_size,
                    "raw_pointer": raw_pointer,
                }
            )
        return image_base, sections


def _stream_sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(CHUNK)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
    return digest.hexdigest(), total


def _scan_rel32(path: Path, section: dict[str, int | str], targets: dict[int, str]) -> dict[str, dict[str, list[int]]]:
    raw_size = int(section["raw_size"])
    raw_pointer = int(section["raw_pointer"])
    virtual_address = int(section["virtual_address"])
    hits: dict[str, dict[str, list[int]]] = {
        name: {"call": [], "jump": []} for name in targets.values()
    }
    with path.open("rb") as stream:
        stream.seek(raw_pointer)
        position = 0
        carry = b""
        while position < raw_size:
            chunk = stream.read(min(CHUNK, raw_size - position))
            if not chunk:
                break
            data = carry + chunk
            base = position - len(carry)
            for index in range(max(0, len(data) - 4)):
                opcode = data[index]
                if opcode not in (0xE8, 0xE9):
                    continue
                displacement = struct.unpack_from("<i", data, index + 1)[0]
                call_rva = virtual_address + base + index
                destination_rva = call_rva + 5 + displacement
                label = targets.get(destination_rva)
                if label is not None:
                    hits[label]["call" if opcode == 0xE8 else "jump"].append(call_rva)
            carry = data[-4:]
            position += len(chunk)
    return hits


def _scan_indirect_slot(path: Path, section: dict[str, int | str], slot: int) -> list[dict[str, object]]:
    """Find bounded ``call [register+slot]`` sites, including disp8/disp32 forms."""

    raw_size = int(section["raw_size"])
    raw_pointer = int(section["raw_pointer"])
    virtual_address = int(section["virtual_address"])
    hits: dict[int, dict[str, object]] = {}
    with path.open("rb") as stream:
        stream.seek(raw_pointer)
        position = 0
        carry = b""
        while position < raw_size:
            chunk = stream.read(min(CHUNK, raw_size - position))
            if not chunk:
                break
            data = carry + chunk
            base = position - len(carry)
            for index in range(max(0, len(data) - 5)):
                if data[index] != 0xFF or index + 2 >= len(data):
                    continue
                modrm = data[index + 1]
                if (modrm >> 3) & 0x7 != 2:  # /2 = CALL r/m64
                    continue
                mod = modrm >> 6
                if mod == 1:
                    if index + 2 >= len(data) or data[index + 2] != slot:
                        continue
                    length = 3
                elif mod == 2:
                    if index + 6 > len(data):
                        continue
                    displacement = struct.unpack_from("<i", data, index + 2)[0]
                    if displacement != slot:
                        continue
                    length = 6
                else:
                    continue
                rva = virtual_address + base + index
                context_start = max(0, index - 128)
                context = data[context_start : index + length]
                hits[rva] = {
                    "rva": hex(rva),
                    "instruction_hex": data[index : index + length].hex(" "),
                    "near_d0_or_d8_read": (b"\xd0\x00\x00\x00" in context[:-length]
                    or b"\xd8\x00\x00\x00" in context[:-length]),
                }
            carry = data[-5:]
            position += len(chunk)
    return [hits[key] for key in sorted(hits)]


def _scan_qword(path: Path, section: dict[str, int | str], image_base: int, target: int) -> list[int]:
    needle = struct.pack("<Q", target)
    raw_size = int(section["raw_size"])
    raw_pointer = int(section["raw_pointer"])
    virtual_address = int(section["virtual_address"])
    hits: list[int] = []
    with path.open("rb") as stream:
        stream.seek(raw_pointer)
        position = 0
        carry = b""
        while position < raw_size:
            chunk = stream.read(min(CHUNK, raw_size - position))
            if not chunk:
                break
            data = carry + chunk
            base = position - len(carry)
            start = 0
            while True:
                index = data.find(needle, start)
                if index < 0:
                    break
                hits.append(virtual_address + base + index)
                start = index + 1
            carry = data[-7:]
            position += len(chunk)
    return hits


def _pdata_records(path: Path, section: dict[str, int | str], target_rva: int) -> tuple[list[dict[str, int]], dict[str, int] | None]:
    raw_size = int(section["raw_size"])
    raw_pointer = int(section["raw_pointer"])
    virtual_address = int(section["virtual_address"])
    with path.open("rb") as stream:
        stream.seek(raw_pointer)
        data = stream.read(raw_size)
    records: list[dict[str, int]] = []
    containing: dict[str, int] | None = None
    for offset in range(0, len(data) - 11, 12):
        begin, end, unwind = struct.unpack_from("<III", data, offset)
        if begin == 0 and end == 0 and unwind == 0:
            continue
        record = {
            "file_offset": raw_pointer + offset,
            "begin_rva": begin,
            "end_rva": end,
            "unwind_rva": unwind,
        }
        if begin <= target_rva < end:
            containing = record
        records.append(record)
    return records, containing


def run(path: Path) -> dict[str, object]:
    image_base, sections = _pe_layout(path)
    sha256, file_bytes = _stream_sha256(path)
    text = next(section for section in sections if section["name"] == ".text")
    pdata = next(section for section in sections if section["name"] == ".pdata")
    targets = {TARGET_RVA: "receiver_clone", GENERIC_RVA: "generic_executor"}
    rel32 = _scan_rel32(path, text, targets)
    pdata_records, target_pdata = _pdata_records(path, pdata, TARGET_RVA)
    # The constructor at 0x157ffd0 writes the vtable at 0x1d95fd8.  In the
    # adjacent table, 0x15800c0 is therefore the +0x38 virtual slot (the
    # transport routine 0x1580270 is +0x30), not +0x40.
    indirect_slot_0x38 = _scan_indirect_slot(path, text, 0x38)

    def containing(rva_text: str) -> dict[str, int] | None:
        value = int(rva_text, 16)
        for record in pdata_records:
            if record["begin_rva"] <= value < record["end_rva"]:
                return record
        return None

    for hit in indirect_slot_0x38:
        hit["containing_pdata"] = containing(str(hit["rva"]))
    non_text_pointer_hits = []
    for section in sections:
        if section["name"] == ".text":
            continue
        for rva in _scan_qword(path, section, image_base, image_base + TARGET_RVA):
            non_text_pointer_hits.append({"section": section["name"], "rva": rva})
    return {
        "schema": "pe_receiver_dispatch_scan_v1",
        "image": {"path": str(path), "sha256": sha256, "bytes": file_bytes, "image_base": hex(image_base)},
        "bounds": {"chunk_bytes": CHUNK, "sections": sections},
        "target": {
            "rva": hex(TARGET_RVA),
            "va": hex(image_base + TARGET_RVA),
            "direct_rel32_call_hits": rel32["receiver_clone"]["call"],
            "direct_rel32_jump_hits": rel32["receiver_clone"]["jump"],
            "containing_pdata": target_pdata,
            "non_text_qword_pointer_hits": non_text_pointer_hits,
        },
        "generic_executor": {
            "rva": hex(GENERIC_RVA),
            "direct_rel32_call_hits": rel32["generic_executor"]["call"],
            "direct_rel32_jump_hits": rel32["generic_executor"]["jump"],
        },
        "indirect_dispatch_candidates": {
            "slot": "0x38",
            "call_count": len(indirect_slot_0x38),
            "near_d0_or_d8_count": sum(1 for hit in indirect_slot_0x38 if hit["near_d0_or_d8_read"]),
            "hits": indirect_slot_0x38[:128],
        },
        "interpretation": {
            "direct_caller_found": bool(rel32["receiver_clone"]["call"]),
            "list_consumer_found": False,
            "next_dispatch_rva": None,
            "scope": "static rel32 and .pdata scan only",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--exe", type=Path)
    args = parser.parse_args()
    result = run((args.exe or game_exe()).resolve())
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
