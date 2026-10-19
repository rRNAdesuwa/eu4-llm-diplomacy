"""Exercise the real publisher preflight with bounded fake memory; no OS calls."""
from pathlib import Path
from types import SimpleNamespace
import struct
import unittest

from bridge.tag_command_backend import WindowsRuntime


class TagCommandPauseTests(unittest.TestCase):
    def runtime(self, pause):
        build = Path("offline-build")
        manifest = {"DLL": "eu4_tag_command_pause_fixture.dll", "PE_timestamp": 1, "SizeOfImage": 4096}
        memory = {
            (0x100000, 8192): b"offline PE fixture",
            (0x200000 + 0x233fe78, 8): struct.pack("<Q", 0x300000),
            (0x300000 + 0x1e00, 8): struct.pack("<Q", 0x400000),
            (0x400000 + 0x418, 8): struct.pack("<Q", 0x500000),
            (0x500000 + 0x48, 1): pause,
        }
        held = SimpleNamespace(closed=False, reads=[], checked=0)
        def close():
            held.closed = True
        def identity_check():
            held.checked += 1
        def read(address, size):
            held.reads.append((address, size))
            return memory[(address, size)]
        held.injector = SimpleNamespace(GAME=Path("eu4.exe"), _canonical=lambda p: str(p))
        held.identity_check, held.close, held.memory = identity_check, close, read
        held.modules = lambda: [(0x200000, Path("eu4.exe")), (0x100000, build / manifest["DLL"])]
        held.window_thread = lambda: 12
        disk_checks = []
        runtime = object.__new__(WindowsRuntime)
        runtime.readonly = SimpleNamespace(Held=lambda _: held,
            pe_header=lambda _: {"timestamp": 1, "size_of_image": 4096}, disk_identity=disk_checks.append)
        return runtime, held, build, manifest, disk_checks

    def test_explicit_manual_pause_is_required_and_handle_is_closed(self):
        runtime, held, build, manifest, disks = self.runtime(b"\x00")
        with self.assertRaisesRegex(ValueError, "Explicit manual pause required"):
            runtime.check({}, build, manifest, 12)
        self.assertTrue(held.closed)
        self.assertEqual(len(held.reads), 5)
        self.assertEqual(sum(size for _, size in held.reads), 8217)
        self.assertFalse(disks)

    def test_explicit_manual_pause_reaches_remaining_identity_checks(self):
        runtime, held, build, manifest, disks = self.runtime(b"\x01")
        runtime.check({}, build, manifest, 12)
        self.assertEqual(held.checked, 2)
        self.assertEqual(disks, [Path("eu4.exe")])
        self.assertTrue(held.closed)

    def test_wrong_owner_still_refuses_after_manual_pause(self):
        runtime, held, build, manifest, _ = self.runtime(b"\x01")
        with self.assertRaisesRegex(ValueError, "Owner thread changed"):
            runtime.check({}, build, manifest, 99)
        self.assertTrue(held.closed)


if __name__ == "__main__":
    unittest.main()
