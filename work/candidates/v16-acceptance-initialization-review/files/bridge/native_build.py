"""Read-only PE identity. A recognised image is not evidence of a live backend."""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct

LEGACY_SHA256 = "B23FA0E1F698D31B01CDD1C3817A675805D8C6286CB66F9C231E6E2A42544D77"
LOCAL_SHA256 = "9AD3EFE1AF169F40EE577F9DAE5DEBBC87AF6FB8B5450FB345EBF110DC4D771A"
KNOWN_BUILDS = {
    LEGACY_SHA256: {"version": "1.37.4", "status": "legacy_experiments_verified"},
    LOCAL_SHA256: {"version": "1.37.5", "status": "static_analysis_only"},
}


def inspect_build(executable: Path) -> dict:
    """Hash in chunks, validate bounded PE headers, never open a game process."""
    executable = Path(executable)
    result = {"executable": str(executable.resolve()), "executable_sha256": None,
              "legacy_v9_compatible": False, "backend_ready": False,
              "execution_supported": False, "status": "unavailable"}
    try:
        size = executable.stat().st_size
        if size < 256:
            raise ValueError("file is too short for PE headers")
        with executable.open("rb") as file:
            dos = file.read(64)
            if dos[:2] != b"MZ":
                raise ValueError("not a PE executable")
            pe_offset = struct.unpack_from("<I", dos, 60)[0]
            if pe_offset > min(size - 24, 1024 * 1024):
                raise ValueError("PE header offset is out of bounds")
            file.seek(pe_offset)
            header = file.read(24)
            if header[:4] != b"PE\0\0":
                raise ValueError("invalid PE signature")
            machine, count, timestamp = struct.unpack_from("<HHI", header, 4)
            optional_size = struct.unpack_from("<H", header, 20)[0]
            if machine != 0x8664 or not 1 <= count <= 96 or not 112 <= optional_size <= 4096:
                raise ValueError("not a bounded x64 PE image")
            optional = file.read(optional_size)
            if len(optional) != optional_size or struct.unpack_from("<H", optional)[0] != 0x20B:
                raise ValueError("not PE32+")
            image_base = struct.unpack_from("<Q", optional, 24)[0]
            sections = []
            for _ in range(count):
                section = file.read(40)
                if len(section) != 40:
                    raise ValueError("truncated section table")
                virtual_size, rva, raw_size, raw_offset = struct.unpack_from("<IIII", section, 8)
                if raw_offset + raw_size > size:
                    raise ValueError("section extends beyond file")
                sections.append({"name": section[:8].rstrip(b"\0").decode("ascii", "replace"),
                                 "rva": rva, "virtual_size": virtual_size, "raw_size": raw_size,
                                 "raw_offset": raw_offset})
            file.seek(0)
            digest = hashlib.file_digest(file, "sha256").hexdigest().upper()
        profile = KNOWN_BUILDS.get(digest)
        result.update({"executable_sha256": digest, "sha256": digest, "size": size,
                       "machine": "x64", "image_base": image_base, "pe_timestamp": timestamp,
                       "sections": sections, "version": profile["version"] if profile else None,
                       "status": profile["status"] if profile else "unknown_build",
                       "legacy_v9_compatible": digest == LEGACY_SHA256,
                       "reason": "No current-process backend has been verified by this read-only check."})
    except (OSError, ValueError, struct.error) as error:
        result["reason"] = str(error)
    return result
