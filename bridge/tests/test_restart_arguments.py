"""Run only pure argument helpers, never the restart script or game processes."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")


@unittest.skipUnless(POWERSHELL, "PowerShell is needed for Windows argument fixtures")
class RestartArgumentsTests(unittest.TestCase):
    def run_helper(self, arguments):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "inputs.json").write_text(json.dumps(arguments), encoding="utf-8")
            helper = str(ROOT / "work/native/restart-arguments-1375.ps1").replace("'", "''")
            script = root / "pure-test.ps1"
            script.write_text("$ErrorActionPreference='Stop'\n. '" + helper + "'\n"
                "$cases = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'inputs.json') -Raw | ConvertFrom-Json\n"
                "$outcomes = @(foreach ($item in $cases) { try { "
                "$result = ConvertTo-TestRestartArguments -Arguments $item -SaveName 'llm_target.eu4'; "
                "@{ok=$true;result=$result} } catch { @{ok=$false;error=$_.Exception.Message} } })\n"
                "ConvertTo-Json -InputObject $outcomes -Compress\n", encoding="utf-8")
            result = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-File", str(script)],
                                    capture_output=True, text=True, timeout=15, check=True)
            return json.loads(result.stdout)

    def test_quoted_values_and_secret_like_tokens_remain_byte_identical(self):
        arguments = ['--opaque="keep -continue=old.eu4 keep" -pdx=synthetic-fixture',
                     r'--token="abc\"quoted -continue=inside.eu4 xyz" --path="C:\some dir\\"',
                     r'--token="a""b -continuelastsave c" ""']
        for original, result in zip(arguments, self.run_helper(arguments)):
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["result"], original + " -continue=llm_target.eu4")

    def test_only_top_level_continue_options_are_replaced(self):
        arguments = ['"-continue=old.eu4" -pdx=fixture', '-continue old.eu4 -pdx=fixture',
                     '--continue="old test.eu4" -pdx=fixture --continuelastsave',
                     '-pdx=fixture -CONTINUELASTSAVE', '--continue-mode=normal -continue=old.eu4']
        expected = ['-pdx=fixture -continue=llm_target.eu4'] * 4 + ['--continue-mode=normal -continue=llm_target.eu4']
        for result, target in zip(self.run_helper(arguments), expected):
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["result"], target)

    def test_empty_arguments_work_and_ambiguous_input_is_refused(self):
        outcomes = self.run_helper(['', '-continue', '-continue -pdx=fixture', '--opaque="unterminated', 'x\ny'])
        self.assertEqual(outcomes[0], {"ok": True, "result": "-continue=llm_target.eu4"})
        self.assertTrue(all(not outcome["ok"] for outcome in outcomes[1:]))


if __name__ == "__main__":
    unittest.main()
