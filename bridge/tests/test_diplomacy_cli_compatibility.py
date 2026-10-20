"""Exercise both public CLI protocols without an operator session or game."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class DiplomacyCLICompatibilityTests(unittest.TestCase):
    def run_cli(self, *arguments, body=""):
        return subprocess.run(
            [sys.executable, "-B", str(ROOT / "tools/diplomacy.py"), *arguments],
            input=body, capture_output=True, text=True, encoding="utf-8",
            cwd=ROOT, timeout=15,
        )

    def test_json_lines_survives_invalid_request_and_lists_actions_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_cli(
                "--journal", str(root / "requests.sqlite3"),
                "--offline-directory", str(root / "offline"),
                body='{"tool":"no_such_tool","arguments":{}}\n'
                     '{"tool":"list_diplomatic_actions","arguments":{}}\n',
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            invalid, catalog = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(invalid["error"]["code"], "INVALID_TOOL_REQUEST")
            self.assertFalse(invalid["submitted"])
            self.assertTrue(catalog["actions"])
            self.assertTrue(root.joinpath("requests.sqlite3").exists())

    def test_json_lines_input_filename_matching_legacy_command_stays_json_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "preview"
            source.write_text('{"tool":"list_diplomatic_actions","arguments":{}}\n', encoding="utf-8")
            result = self.run_cli("--input-file", str(source), "--journal", str(root / "journal.sqlite3"),
                                  "--offline-directory", str(root / "offline"))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)["actions"])

    def test_legacy_command_without_version_still_uses_research_api(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_cli("--queue-db", str(Path(directory) / "queue.sqlite3"), "capabilities")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsInstance(json.loads(result.stdout), dict)

    def test_help_exposes_both_protocols(self):
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--operator-session", result.stdout)
        self.assertIn("--legacy --help", result.stdout)
        result = self.run_cli("--legacy", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--api-version", result.stdout)


if __name__ == "__main__":
    unittest.main()
