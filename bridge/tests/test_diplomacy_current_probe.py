"""Synthetic memory/minidump tests; no game process access or native calls."""
import io
from pathlib import Path
import struct
import tempfile
import unittest

from work.probe_diplomacy_current import (
    DATABASE_POINTER_RVA, GAME_POINTER_RVA, MAX_READ, DumpReader, MemoryReader,
    MissingMemory, ProbeError, country_identity, inspect_state, partial_dump_state,
    pe_signature, verified_executable, verify_module_signature,
)


class FixtureMemory(MemoryReader):
    def __init__(self):
        self.memory = {}
        self.bytes_read = 0

    def write_fixture(self, address, value, size=8):
        body = value.to_bytes(size, "little") if isinstance(value, int) else value
        self.memory.update((address + index, byte) for index, byte in enumerate(body))

    def read(self, address, size):
        self._check_read(address, size)
        try:
            return bytes(self.memory[address + index] for index in range(size))
        except KeyError:
            raise MissingMemory(f"Fixture does not capture {address:#x}") from None


def build_memory():
    memory = FixtureMemory()
    base, database, game, array = 0x140000000, 0x100000, 0x200000, 0x300000
    memory.write_fixture(base + DATABASE_POINTER_RVA, database)
    memory.write_fixture(base + GAME_POINTER_RVA, game)
    memory.write_fixture(database + 0x118, array)
    memory.write_fixture(game + 0x1DD0, 56463336, 4)
    memory.write_fixture(array, b"\0" * (256 * 8))
    for slot, tag in ((2, "FRA"), (6, "ENG"), (189, "POR")):
        address = 0x400000 + slot * 0x1000
        handle = slot << 32 | int.from_bytes(tag.encode("ascii"), "little")
        memory.write_fixture(array + slot * 8, address)
        memory.write_fixture(address + 0x20, handle)
        if tag == "POR":
            memory.write_fixture(game + 0x1E60, handle)
    actor = 0x402000
    memory.write_fixture(actor + 0x1480, 0x700000)
    memory.write_fixture(0x700018, 0x710000)
    memory.write_fixture(0x710020, 0x720000)
    memory.write_fixture(0x710028, 0x720010)
    memory.write_fixture(0x720000, 0x730000)
    memory.write_fixture(0x720008, 0x740000)
    memory.write_fixture(0x730018, 0, 1)
    memory.write_fixture(0x740018, 2, 1)
    memory.write_fixture(actor + 0x1510, 0x800000)
    memory.write_fixture(0x800000 + 6 * 0x48 + 0x30, 56463312, 4)
    return memory, base, array


def make_dump(path):
    """Minimal x64-ish dump with module ownership and captured data, no register guesses."""
    data = bytearray(32 + 5 * 12)
    data[:4] = b"MDMP"
    struct.pack_into("<II", data, 8, 5, 32)

    def append(body):
        offset = len(data)
        data.extend(body)
        return offset

    names = []
    for name in (r"D:\game\eu4.exe", r"D:\game\plugins\plugin64.dll"):
        encoded = name.encode("utf-16le")
        names.append(append(struct.pack("<I", len(encoded)) + encoded))
    modules = bytearray(4 + 2 * 108)
    struct.pack_into("<I", modules, 0, 2)
    struct.pack_into("<QIIII", modules, 4, 0x140000000, 0x3000000, 0, 1234, names[0])
    struct.pack_into("<QIIII", modules, 112, 0x7FFF00000000, 0x80000, 0, 4321, names[1])
    module_offset = append(modules)
    captured = append(b"abcdefgh")
    memory = struct.pack("<IQII", 1, 0x100000, 8, captured)
    memory_offset = append(memory)
    exception = bytearray(168)
    struct.pack_into("<I", exception, 0, 7)
    struct.pack_into("<I", exception, 8, 0xC0000005)
    struct.pack_into("<Q", exception, 24, 0x7FFF00003456)
    struct.pack_into("<I", exception, 32, 2)
    struct.pack_into("<QQ", exception, 40, 0, 0xBAD)
    exception_offset = append(exception)
    for index, descriptor in enumerate(((4, len(modules), module_offset), (5, len(memory), memory_offset),
                                        (6, len(exception), exception_offset), (0, 0, 0), (0, 0, 0))):
        struct.pack_into("<III", data, 32 + index * 12, *descriptor)
    path.write_bytes(data)
    return data, memory_offset


class CurrentStateProbeTests(unittest.TestCase):
    def test_validated_identity_precedes_diplomat_and_relation_interpretation(self):
        memory, base, array = build_memory()
        report = inspect_state(memory, base)
        self.assertEqual(report["player"]["tag"], "POR")
        self.assertEqual({country["tag"] for country in report["countries"]}, {"FRA", "ENG", "POR"})
        self.assertEqual(report["actor_diplomats"]["state_zero_count"], 1)
        self.assertTrue(report["relation_cooldown"]["strict_date_comparison"])
        self.assertFalse(report["game_legality_checked"])
        self.assertFalse(report["execution_supported"])

    def test_full_player_handle_mismatch_rejected_even_when_slot_matches(self):
        memory, base, array = build_memory()
        handle = memory.qword(0x200000 + 0x1E60)
        memory.write_fixture(0x200000 + 0x1E60, handle | 1 << 56)
        with self.assertRaises(ProbeError):
            inspect_state(memory, base)

    def test_invalid_country_handle_is_not_interpreted_as_actor(self):
        memory, base, array = build_memory()
        memory.write_fixture(0x402020, 8 << 32 | int.from_bytes(b"FRA", "little"))
        report = inspect_state(memory, base)
        self.assertEqual(report["actor_diplomats"]["status"], "unavailable")
        self.assertEqual(report["relation_cooldown"]["status"], "unavailable")
        self.assertTrue(any(item["slot"] == 2 for item in report["skipped_slots"]))

    def test_vector_and_slot_bounds_fail_closed(self):
        memory, base, array = build_memory()
        memory.write_fixture(0x710028, 0x720000 + 257 * 8)
        report = inspect_state(memory, base)
        self.assertEqual(report["actor_diplomats"]["status"], "unavailable")
        with self.assertRaises(ProbeError):
            inspect_state(memory, base, slots=4097)
        with self.assertRaises(ProbeError):
            country_identity(memory, array, 4096)
        with self.assertRaises(ProbeError):
            memory.read(0x100000, MAX_READ + 1)

    def test_partial_dump_does_not_invent_zero_game_state(self):
        memory = FixtureMemory()
        base = 0x140000000
        memory.write_fixture(base + DATABASE_POINTER_RVA, 0x100000)
        memory.write_fixture(base + GAME_POINTER_RVA, 0x200000)
        result = partial_dump_state(memory, base, MissingMemory("heap absent"))
        self.assertEqual(result["status"], "partial_capture")
        self.assertEqual(result["fields"]["current_raw_date"]["status"], "unavailable")
        self.assertNotIn("value", result["fields"]["current_raw_date"])
        self.assertFalse(result["country_identities_verified"])

    def test_module_signature_mismatch_rejected(self):
        verify_module_signature({"timestamp": 1, "size": 2}, {"timestamp": 1, "size": 2})
        for module in ({"timestamp": 3, "size": 2}, {"timestamp": 1, "size": 3}):
            with self.assertRaises(ProbeError):
                verify_module_signature(module, {"timestamp": 1, "size": 2})

    def test_unsupported_executable_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "eu4.exe"
            path.write_bytes(b"not the audited game")
            with self.assertRaises(ProbeError):
                verified_executable(path)

    def test_pe_header_reader_bounds(self):
        data = bytearray(256)
        data[:2] = b"MZ"
        struct.pack_into("<I", data, 60, 0x200000)
        with self.assertRaises(ProbeError):
            pe_signature(io.BytesIO(data))


class MinidumpTests(unittest.TestCase):
    def test_exception_is_attributed_to_its_own_module_not_eu4_base(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.dmp"
            make_dump(path)
            reader = DumpReader(path)
            try:
                fault = reader.fault()
                self.assertTrue(fault["module"].endswith(r"plugins\plugin64.dll"))
                self.assertEqual(fault["module_relative_offset"], "0x3456")
                self.assertEqual(reader.read(0x100002, 3), b"cde")
                with self.assertRaises(MissingMemory):
                    reader.read(0x100008, 1)
            finally:
                reader.close()

    def test_truncated_memory_descriptor_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.dmp"
            data, memory_offset = make_dump(path)
            struct.pack_into("<I", data, memory_offset + 16, len(data) + 4096)
            path.write_bytes(data)
            with self.assertRaises(ProbeError):
                DumpReader(path)


if __name__ == "__main__":
    unittest.main()
