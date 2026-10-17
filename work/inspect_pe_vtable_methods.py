"""Bounded inspection of the receiver vtable and selected virtual methods.

This helper reads only PE headers, the vtable's 20 qwords, .pdata, and bounded
function ranges through objdump.  It is intentionally not a whole-binary
disassembly tool.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    from work.inspect_pe_receiver_dispatch import _pdata_records, _pe_layout
    from work.local_config import game_exe
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from work.inspect_pe_receiver_dispatch import _pdata_records, _pe_layout
    from work.local_config import game_exe


IMAGE_BASE = 0x140000000
VTABLE_RVA = 0x1D95FD8
ENTRY_COUNT = 20  # slots 0 through +0x98
DISASSEMBLY_CAP = 4096
TARGET_SLOTS = (0x28, 0x30, 0x38, 0x40, 0x48, 0x50, 0x58)


def _rva_to_file_offset(sections: list[dict[str, int | str]], rva: int) -> int:
    for section in sections:
        begin = int(section["virtual_address"])
        size = max(int(section["virtual_size"]), int(section["raw_size"]))
        if begin <= rva < begin + size:
            return int(section["raw_pointer"]) + rva - begin
    raise ValueError(f"RVA 0x{rva:x} is not in a PE section")


def _read_vtable(path: Path, sections: list[dict[str, int | str]]) -> list[dict[str, object]]:
    with path.open("rb") as stream:
        stream.seek(_rva_to_file_offset(sections, VTABLE_RVA))
        result = []
        for index in range(ENTRY_COUNT):
            value = int.from_bytes(stream.read(8), "little")
            result.append(
                {
                    "slot": hex(index * 8),
                    "target_va": hex(value),
                    "target_rva": hex(value - IMAGE_BASE) if value >= IMAGE_BASE else None,
                }
            )
        return result


def _find_pdata(records: list[dict[str, int]], rva: int) -> dict[str, int] | None:
    for record in records:
        if record["begin_rva"] <= rva < record["end_rva"]:
            return record
    return None


def _bounded_objdump(path: Path, begin_rva: int, end_rva: int | None) -> tuple[str, bool, int]:
    if end_rva is None:
        end_rva = begin_rva + 128
        size = 128
        truncated = True
    else:
        size = max(0, end_rva - begin_rva)
        truncated = size > DISASSEMBLY_CAP
    stop_rva = begin_rva + min(size, DISASSEMBLY_CAP)
    command = [
        "objdump",
        "-d",
        "-Mintel",
        f"--start-address={IMAGE_BASE + begin_rva:#x}",
        f"--stop-address={IMAGE_BASE + stop_rva:#x}",
        str(path),
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return completed.stdout, truncated, stop_rva


def _interesting_lines(disassembly: str) -> list[str]:
    lines = []
    for line in disassembly.splitlines():
        lowered = line.lower()
        if any(token in lowered for token in ("+0xc8", "+0xd0", "+0xd8", "+0x48")):
            lines.append(line.rstrip())
    return lines


def run(path: Path) -> dict[str, object]:
    image_base, sections = _pe_layout(path)
    if image_base != IMAGE_BASE:
        raise ValueError(f"unexpected image base 0x{image_base:x}")
    pdata_section = next(section for section in sections if section["name"] == ".pdata")
    records, _ = _pdata_records(path, pdata_section, 0)
    entries = _read_vtable(path, sections)
    for entry in entries:
        target_rva_text = entry["target_rva"]
        target_rva = int(target_rva_text, 16) if target_rva_text else None
        entry["pdata"] = _find_pdata(records, target_rva) if target_rva is not None else None
        entry["selected_for_disassembly"] = int(entry["slot"], 16) in TARGET_SLOTS

    selected = []
    for entry in entries:
        if not entry["selected_for_disassembly"]:
            continue
        pdata = entry["pdata"]
        target_rva = int(entry["target_rva"], 16)
        begin_rva = pdata["begin_rva"] if pdata is not None else target_rva
        end_rva = pdata["end_rva"] if pdata is not None else None
        disassembly, truncated, window_end_rva = _bounded_objdump(path, begin_rva, end_rva)
        selected.append(
            {
                "slot": entry["slot"],
                "target_rva": entry["target_rva"],
                "pdata": pdata,
                "no_pdata_bounded_window": pdata is None,
                "window_end_rva": hex(window_end_rva),
                "disassembly_bytes_cap": DISASSEMBLY_CAP,
                "disassembly_truncated": truncated,
                "interesting_lines": _interesting_lines(disassembly),
            }
        )

    return {
        "schema": "pe_receiver_vtable_methods_v1",
        "image": {"path": str(path), "image_base": hex(image_base)},
        "vtable": {"rva": hex(VTABLE_RVA), "entry_count": ENTRY_COUNT, "entries": entries},
        "selected_methods": selected,
        "selection_rule": "slots +0x28 through +0x58, focusing on +0x40 and neighbors",
        "decoder": "bounded objdump -Mintel; capstone unavailable in local Python environment",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run((args.exe or game_exe()).resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
