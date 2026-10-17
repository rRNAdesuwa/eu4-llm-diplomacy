"""Read selected x64 PE unwind ranges without loading the executable into RAM."""
from pathlib import Path
import struct


def unwind_ranges(path: Path, entries: list[int]) -> dict[int, tuple[int, int]]:
    """Return exact-entry [begin, end) ranges; reject missing/ambiguous records.

    A RUNTIME_FUNCTION range is a shipped unwind-metadata observation. It does
    not establish all semantic C++ function chunks or an externally callable ABI.
    """
    wanted = set(entries)
    found = {}
    file_size = path.stat().st_size
    with path.open("rb") as stream:
        def read_at(offset, length):
            if offset < 0 or length < 0 or offset + length > file_size:
                raise ValueError("PE metadata exceeds file bounds")
            stream.seek(offset)
            data = stream.read(length)
            if len(data) != length:
                raise ValueError("Incomplete PE metadata read")
            return data

        dos = read_at(0, 64)
        header = struct.unpack_from("<I", dos, 60)[0]
        if dos[:2] != b"MZ" or not 64 <= header <= 1024 * 1024:
            raise ValueError("Unsupported DOS/PE header")
        coff = read_at(header, 24)
        machine, count = struct.unpack_from("<HH", coff, 4)
        optional_size = struct.unpack_from("<H", coff, 20)[0]
        if coff[:4] != b"PE\0\0" or machine != 0x8664 or not 1 <= count <= 96:
            raise ValueError("Expected a bounded x64 PE")
        if not 144 <= optional_size <= 4096:
            raise ValueError("Invalid PE32+ optional header size")
        optional = read_at(header + 24, optional_size)
        if struct.unpack_from("<H", optional)[0] != 0x20B or struct.unpack_from("<I", optional, 108)[0] < 4:
            raise ValueError("Missing PE32+ exception data directory")
        table_rva, table_size = struct.unpack_from("<II", optional, 136)
        if not table_rva or not table_size or table_size > 8 * 1024**2 or table_size % 12:
            raise ValueError("Invalid/budget-exceeding RUNTIME_FUNCTION table")
        sections = []
        for number in range(count):
            section = read_at(header + 24 + optional_size + number * 40, 40)
            virtual_size, rva, raw_size, offset = struct.unpack_from("<IIII", section, 8)
            flags = struct.unpack_from("<I", section, 36)[0]
            sections.append((rva, virtual_size, raw_size, offset, flags))
        mappings = [offset + table_rva - rva for rva, _, raw_size, offset, _ in sections
                    if rva <= table_rva and table_rva + table_size <= rva + raw_size]
        if len(mappings) != 1 or mappings[0] + table_size > file_size:
            raise ValueError("Exception directory is not uniquely file-backed")
        stream.seek(mappings[0])
        for _ in range(table_size // 12):
            record = stream.read(12)
            if len(record) != 12:
                raise ValueError("Truncated RUNTIME_FUNCTION table")
            begin, end, _ = struct.unpack("<III", record)
            if begin not in wanted:
                continue
            if begin in found:
                raise ValueError(f"Ambiguous unwind entry {begin:#x}")
            executable = any(flags & 0x20000000 and rva <= begin < end <= rva + min(size, raw_size)
                             for rva, size, raw_size, _, flags in sections)
            if not executable or end - begin > 0x8000:
                raise ValueError(f"Invalid/unbounded executable unwind range {begin:#x}..{end:#x}")
            found[begin] = (begin, end)
    missing = wanted - found.keys()
    if missing:
        raise ValueError("No exact unwind entry: " + ", ".join(f"{entry:#x}" for entry in sorted(missing)))
    return found
