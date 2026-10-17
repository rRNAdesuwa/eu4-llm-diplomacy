"""Stream fixed diplomacy GUI names and bounded RIP-reference candidates.

Offline evidence only. An encoded reference is not proof of a callable ABI.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
from pathlib import Path
import re
import struct

from local_config import game_exe


EXPECTED_HASH = "b23fa0e1f698d31b01cdd1c3817a675805d8c6286cb66f9c231e6e2a42544d77"
LABELS = (b"diploactionentry", b"diploaction_list", b"button_diploaction",
          b"countrydiplomacyview", b"show_diploactions")
CHUNK = 1024 * 1024
RIP = re.compile(rb"[\x48-\x4f][\x8d\x8b][\x05\x0d\x15\x1d\x25\x2d\x35\x3d]....", re.DOTALL)


def trace(direct_targets: tuple[int, ...] = ()) -> dict:
    game = game_exe()
    digest = hashlib.sha256()
    with game.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b""):
            digest.update(chunk)
        if digest.hexdigest() != EXPECTED_HASH:
            raise ValueError("Unsupported executable hash")
        stream.seek(0x3c)
        pe = struct.unpack("<I", stream.read(4))[0]
        if pe > CHUNK:
            raise ValueError("PE header out of bounds")
        stream.seek(pe)
        header = stream.read(24)
        if header[:4] != b"PE\0\0" or struct.unpack_from("<H", header, 4)[0] != 0x8664:
            raise ValueError("Expected x64 PE")
        count = struct.unpack_from("<H", header, 6)[0]
        optional_size = struct.unpack_from("<H", header, 20)[0]
        if count > 64 or optional_size > 4096:
            raise ValueError("PE header shape")
        optional = stream.read(optional_size)
        image_base = struct.unpack_from("<Q", optional, 24)[0]
        sections = []
        for _ in range(count):
            raw = stream.read(40)
            name, _, rva, size, offset = struct.unpack_from("<8sIIII", raw)
            flags = struct.unpack_from("<I", raw, 36)[0]
            sections.append((name.rstrip(b"\0"), rva, size, offset, flags))

        functions = []
        for name, _, size, offset, _ in sections:
            if name != b".pdata":
                continue
            stream.seek(offset)
            remaining = size
            carry = b""
            while remaining:
                chunk = stream.read(min(CHUNK, remaining))
                if not chunk:
                    raise ValueError("Short .pdata")
                remaining -= len(chunk)
                block = carry + chunk
                complete = len(block) // 12 * 12
                for start, end, _ in struct.iter_unpack("<III", block[:complete]):
                    if 0 < start < end:
                        functions.append((start, end))
                carry = block[complete:]
        functions.sort()
        starts = [start for start, _ in functions]

        found = {}
        overlap = max(map(len, LABELS))
        for name, rva, size, offset, flags in sections:
            if flags & 0x20000000:
                continue
            cursor = 0
            carry = b""
            stream.seek(offset)
            while cursor < size:
                chunk = stream.read(min(CHUNK, size - cursor))
                if not chunk:
                    raise ValueError("Short string section")
                block = carry + chunk
                start_rva = rva + cursor - len(carry)
                for label in LABELS:
                    for match in re.finditer(re.escape(label + b"\0"), block):
                        address = start_rva + match.start()
                        found.setdefault(address, {"label": label.decode("ascii"),
                                                  "rva": hex(address), "references": []})
                cursor += len(chunk)
                carry = block[-overlap:]

        seen = set()
        direct = {target: [] for target in direct_targets}
        direct_seen = set()
        for _, rva, size, offset, flags in sections:
            if not flags & 0x20000000:
                continue
            cursor = 0
            carry = b""
            stream.seek(offset)
            while cursor < size:
                chunk = stream.read(min(CHUNK, size - cursor))
                if not chunk:
                    raise ValueError("Short code section")
                block = carry + chunk
                start_rva = rva + cursor - len(carry)
                for match in RIP.finditer(block):
                    address = start_rva + match.start()
                    destination = address + 7 + struct.unpack_from("<i", match.group(), 3)[0]
                    if destination not in found or (destination, address) in seen:
                        continue
                    seen.add((destination, address))
                    index = bisect.bisect_right(starts, address) - 1
                    bounds = functions[index] if index >= 0 and address < functions[index][1] else None
                    found[destination]["references"].append({
                        "instruction_rva": hex(address),
                        "function_bounds": [hex(value) for value in bounds] if bounds else None,
                        "disassembly_verified": False})
                for match in re.finditer(rb"\xe8....", block, re.DOTALL):
                    address = start_rva + match.start()
                    destination = address + 5 + struct.unpack_from("<i", match.group(), 1)[0]
                    if destination not in direct or (destination, address) in direct_seen:
                        continue
                    direct_seen.add((destination, address))
                    index = bisect.bisect_right(starts, address) - 1
                    bounds = functions[index] if index >= 0 and address < functions[index][1] else None
                    direct[destination].append({"call_rva": hex(address),
                        "function_bounds": [hex(value) for value in bounds] if bounds else None,
                        "disassembly_verified": False})
                cursor += len(chunk)
                carry = block[-6:]
    return {"game_sha256": EXPECTED_HASH, "image_base": hex(image_base),
            "read_only": True, "max_stream_chunk": CHUNK,
            "references_are_byte_candidates": True,
            "targets": [found[key] for key in sorted(found)],
            "direct_call_candidates": {hex(key): value for key, value in direct.items()}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--direct-call", action="append", type=lambda value: int(value, 0), default=[])
    args = parser.parse_args()
    if len(args.direct_call) > 8 or any(not 0x1000 <= value < 0x1b66000 for value in args.direct_call):
        parser.error("At most eight .text direct-call targets")
    report = trace(tuple(args.direct_call))
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
