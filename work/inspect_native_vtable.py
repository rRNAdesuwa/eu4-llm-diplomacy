"""Bounded PE vtable read: no game attach, code calls, or whole disassembly."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from local_config import game_exe


def inspect(rva: int, slots: int) -> dict:
    if rva < 0 or not 1 <= slots <= 64:
        raise ValueError("Expected a positive RVA and 1..64 slots")
    game = game_exe()
    digest = hashlib.sha256()
    with game.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    sha = digest.hexdigest()
    if sha != "b23fa0e1f698d31b01cdd1c3817a675805d8c6286cb66f9c231e6e2a42544d77":
        raise ValueError("Unsupported PE hash")
    with game.open("rb") as stream:
        stream.seek(0x3c)
        pe = struct.unpack("<I", stream.read(4))[0]
        if pe > 1024 * 1024:
            raise ValueError("PE header out of bounds")
        stream.seek(pe)
        header = stream.read(24)
        signature, machine, count = struct.unpack_from("<4sHH", header)
        optional_size = struct.unpack_from("<H", header, 20)[0]
        if signature != b"PE\0\0" or machine != 0x8664 or count > 64 or optional_size > 4096:
            raise ValueError("Invalid x64 PE header")
        optional = stream.read(optional_size)
        if struct.unpack_from("<H", optional)[0] != 0x20b:
            raise ValueError("Expected PE32+")
        image_base = struct.unpack_from("<Q", optional, 24)[0]
        size_of_image = struct.unpack_from("<I", optional, 56)[0]
        sections = stream.read(count * 40)
        raw = None
        section_name = None
        for index in range(count):
            name, _, section_rva, raw_size, raw_offset = struct.unpack_from("<8sIIII", sections, index * 40)
            if section_rva <= rva and rva + slots * 8 <= section_rva + raw_size:
                raw = raw_offset + rva - section_rva
                section_name = name.rstrip(b"\0").decode("ascii")
                break
        if raw is None or section_name != ".rdata":
            raise ValueError("Vtable range is not fully within .rdata")
        stream.seek(raw)
        data = stream.read(slots * 8)
        if len(data) != slots * 8:
            raise ValueError("Short vtable read")
    result = []
    for index in range(slots):
        value = struct.unpack_from("<Q", data, index * 8)[0]
        inside = image_base <= value < image_base + size_of_image
        result.append({"slot": hex(index * 8), "target_rva": hex(value - image_base) if inside else None,
                       "in_image": inside})
    return {"game_sha256": sha, "vtable_rva": hex(rva), "slots": result,
            "runtime_verified": False, "callable_abi_verified": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rva", type=lambda value: int(value, 0))
    parser.add_argument("output", type=Path)
    parser.add_argument("--slots", type=int, default=32)
    args = parser.parse_args()
    report = inspect(args.rva, args.slots)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2)
    print(json.dumps(report))
