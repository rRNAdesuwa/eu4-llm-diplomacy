"""Safety checks for research extraction and preservation of launcher state."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


unpacker = load_tool("unpack_game")
installer = load_tool("install_diplomacy_test_mod")


class ResearchToolsTests(unittest.TestCase):
    def test_archive_traversal_rejected(self):
        for name in ("../escape.txt", "/common/evil.txt", "C:\\common\\evil.txt", "common/../../evil.txt"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                unpacker.safe_member(name)

    def test_loose_and_archive_sources_are_never_overlaid(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            game = root / "game"
            (game / "common").mkdir(parents=True)
            (game / "eu4.exe").write_bytes(b"test fixture")
            (game / "common" / "test.txt").write_text("base")
            (game / "dlc").mkdir()
            with zipfile.ZipFile(game / "dlc" / "test.zip", "w") as archive:
                archive.writestr("common/test.txt", "dlc")
                archive.writestr("gfx/unused.dds", b"not needed")
            output = root / "unpacked"
            summary = unpacker.unpack(game, output)
            self.assertEqual(summary["files"], 2)
            self.assertEqual((output / "base/common/test.txt").read_text(), "base")
            self.assertEqual((output / "archives/dlc/test/common/test.txt").read_text(), "dlc")
            self.assertEqual((game / "common/test.txt").read_text(), "base")
            with self.assertRaises(ValueError):
                unpacker.unpack(game, output)

    def test_enable_disable_preserves_other_mods_and_unknown_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            game, data, project = root / "game", root / "userdata", root / "project"
            (game / "common").mkdir(parents=True)
            (game / "common/defines.lua").write_text("DIPLOMAT_COOLDOWN_TIME = 1,")
            data.mkdir()
            config = {"enabled_mods": ["mod/other.mod"], "disabled_dlcs": ["test"], "extra": {"preserve": True}}
            settings = data / "dlc_load.json"
            settings.write_text(json.dumps(config))
            import shutil
            shutil.copytree(ROOT / "mod/llm_diplomacy_test", project / "mod/llm_diplomacy_test")
            with patch.object(installer, "ROOT", project):
                installed = installer.install(data, game, ["FRA", "ENG"], enable=True)
                self.assertTrue(installed["enabled"])
                first = json.loads(settings.read_text())
                self.assertEqual(first["extra"], config["extra"])
                installer.install(data, game, ["FRA", "ENG"], enable=True)
                self.assertEqual(json.loads(settings.read_text())["enabled_mods"].count(installer.ENTRY), 1)
                installer.install(data, game, ["FRA", "ENG"], disable=True)
                self.assertEqual(json.loads(settings.read_text()), config)
                self.assertEqual(json.loads((Path(installed["backup"]) / "dlc_load.json").read_text()), config)

    def test_missing_build_fails_closed(self):
        from bridge.native_build import inspect_build
        with tempfile.TemporaryDirectory() as temporary:
            identity = inspect_build(Path(temporary) / "eu4.exe")
            self.assertFalse(identity["execution_supported"])
            self.assertFalse(identity["legacy_v9_compatible"])
            self.assertEqual(identity["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
