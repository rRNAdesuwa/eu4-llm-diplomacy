"""Boundaries that must fail before starting a native analysis process."""
from pathlib import Path
import struct
import tempfile
import unittest

from reverse_engineering.pe_ranges import unwind_ranges


def fixture(records):
    image = bytearray(0x600)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 60, 0x80)
    image[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HH", image, 0x84, 0x8664, 2)
    struct.pack_into("<H", image, 0x94, 240)
    optional = 0x98
    struct.pack_into("<H", image, optional, 0x20B)
    struct.pack_into("<I", image, optional + 108, 16)
    struct.pack_into("<II", image, optional + 136, 0x2000, 12 * len(records))
    for number, (name, rva, raw, flags) in enumerate([
            (b".text", 0x1000, 0x200, 0x60000020),
            (b".pdata", 0x2000, 0x400, 0x40000040)]):
        section = optional + 240 + number * 40
        image[section:section + len(name)] = name
        struct.pack_into("<IIII", image, section + 8, 0x200, rva, 0x200, raw)
        struct.pack_into("<I", image, section + 36, flags)
    for number, (begin, end) in enumerate(records):
        struct.pack_into("<III", image, 0x400 + number * 12, begin, end, 0x2010)
    return image


class PeRangesTests(unittest.TestCase):
    def analyze(self, records, entries):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.exe"
            path.write_bytes(fixture(records))
            return unwind_ranges(path, entries)

    def test_only_exact_selected_entries_are_admitted(self):
        self.assertEqual(self.analyze([(0x1000, 0x1006), (0x1010, 0x1020)], [0x1010]),
                         {0x1010: (0x1010, 0x1020)})
        with self.assertRaisesRegex(ValueError, "No exact unwind entry"):
            self.analyze([(0x1000, 0x1006)], [0x1001])

    def test_ambiguous_metadata_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            self.analyze([(0x1000, 0x1006), (0x1000, 0x1008)], [0x1000])

    def test_non_executable_or_cross_section_ranges_are_rejected(self):
        for begin, end in [(0x2000, 0x2006), (0x1000, 0x2001), (0x1000, 0x1000)]:
            with self.subTest(begin=begin, end=end), self.assertRaisesRegex(ValueError, "Invalid/unbounded"):
                self.analyze([(begin, end)], [begin])

    def test_exception_directory_cannot_read_past_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.exe"
            image = fixture([(0x1000, 0x1006)])
            struct.pack_into("<II", image, 0x98 + 136, 0x21F8, 12)
            path.write_bytes(image)
            with self.assertRaisesRegex(ValueError, "uniquely file-backed"):
                unwind_ranges(path, [0x1000])


if __name__ == "__main__":
    unittest.main()
