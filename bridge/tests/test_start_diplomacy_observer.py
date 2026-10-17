from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import start_diplomacy_observer as subject


class ObserverStartTests(unittest.TestCase):
    def _setup(self, version=10):
        temp = tempfile.TemporaryDirectory()
        directory = Path(temp.name)
        dll = directory / f"eu4_bridge_diplomacy_observer_v{version}.dll"
        dll.write_bytes(b"reviewed observer")
        manifest = directory / "build-manifest.json"
        manifest.write_text(json.dumps({
            "version": version,
            "experiment_id": "observer-test",
            "game_sha256": "game",
            "dll_sha256": "dll",
        }), encoding="utf-8")
        return temp, directory, manifest, dll

    @staticmethod
    def _identity(installed=False):
        return {
            "pid": 52544,
            "creation_filetime": 9988,
            "session_id": "52544-2704",
            "game_sha256": "game",
            "modules": ([{"name": "observer.dll", "sha256": "dll"}] if installed else []),
        }

    def test_delayed_preflight_then_injection_error_is_single_attempt(self):
        temp, directory, manifest, _dll = self._setup()
        self.addCleanup(temp.cleanup)
        calls = {"preflight": 0, "inject": 0}

        def fake_run(command, **_kwargs):
            if any("probe_native_state.py" in str(part) for part in command):
                calls["preflight"] += 1
                output = Path(command[command.index("--output") + 1])
                if calls["preflight"] == 1:
                    return subprocess.CompletedProcess(command, 17, "countryDB only", "")
                output.write_text(json.dumps({"player_tag": "POR"}), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")
            if any("inject_probe.py" in str(part) for part in command):
                calls["inject"] += 1
                return subprocess.CompletedProcess(command, 9, "loader failed", "")
            raise AssertionError(f"unexpected child command: {command}")

        output = io.StringIO()
        with patch.object(subject, "file_hash", lambda _path: "dll"), \
             patch.object(subject, "game_exe", lambda: directory / "eu4.exe"), \
             patch.object(subject, "get_value", lambda _name: "python"), \
             patch.object(subject, "probe_identity", lambda _pid, _exe: self._identity()), \
             patch.object(subject.subprocess, "run", fake_run), \
             patch.object(subject.time, "sleep", lambda _seconds: None), \
             contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as raised:
                subject.main(["--pid", "52544", "--manifest", str(manifest), "--wait-ready", "5"])

        self.assertEqual(str(raised.exception), "INSTALLATION_FAILED_NO_RETRY_IN_THIS_PROCESS")
        self.assertEqual(calls, {"preflight": 2, "inject": 1})
        attempts = sorted(directory.glob("ready-attempt-*") )
        self.assertEqual(len(attempts), 2)
        self.assertTrue((attempts[0] / "preflight.error.txt").is_file())
        installation = json.loads((directory / "installation.json").read_text(encoding="utf-8"))
        self.assertEqual(installation["installation_returncode"], 9)
        self.assertEqual(len(installation["ready_attempts"]), 2)
        waiting_lines = [json.loads(line) for line in output.getvalue().splitlines() if line]
        self.assertEqual(waiting_lines[0]["state"], "waiting")
        self.assertEqual(waiting_lines[0]["reason"], "PREFLIGHT_RETURN_17")

    def test_startup_error_scan_is_bounded_to_one_check_per_five_seconds(self):
        temp, directory, _manifest, _dll = self._setup()
        self.addCleanup(temp.cleanup)
        clock = [0.0]
        preflight_calls = [0]
        scan_times: list[float] = []

        def fake_preflight(_pid, _python, attempt_directory, _deadline):
            preflight_calls[0] += 1
            if preflight_calls[0] <= 6:
                return None, {"reason": "PREFLIGHT_RETURN_17", "preflight": str(attempt_directory / "preflight.json")}
            return {"player_tag": "---"}, {"reason": "PREFLIGHT_READY", "preflight": "ready"}

        def fake_acknowledge(_pid, _attempt_directory):
            scan_times.append(clock[0])
            return None

        with patch.object(subject, "probe_identity", lambda _pid, _exe: self._identity()), \
             patch.object(subject, "game_exe", lambda: directory / "eu4.exe"), \
             patch.object(subject, "_preflight_once", fake_preflight), \
             patch.object(subject, "acknowledge_startup_error", fake_acknowledge), \
             patch.object(subject.time, "monotonic", lambda: clock[0]), \
             patch.object(subject.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds)):
            _identity, state, confirmation, reason, attempts = subject._wait_until_ready(
                52544, {"game_sha256": "game"}, directory, False, 10)

        self.assertEqual(state["player_tag"], "---")
        self.assertIsNone(confirmation)
        self.assertEqual(reason, "unloaded_no_confirmation_requested")
        self.assertEqual(len(attempts), 7)
        self.assertEqual(scan_times, [0.0, 5.0])

    def test_delayed_load_warning_uses_independent_attempts_then_queues_once(self):
        temp, directory, manifest, _dll = self._setup()
        self.addCleanup(temp.cleanup)
        calls = {"preflight": 0, "inject": 0}
        installed = [False]

        def fake_identity(_pid, _exe):
            return self._identity(installed[0])

        def fake_run(command, **_kwargs):
            if any("probe_native_state.py" in str(part) for part in command):
                calls["preflight"] += 1
                output = Path(command[command.index("--output") + 1])
                output.write_text(json.dumps({"player_tag": "---", "module_base": "0x100000"}), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")
            if any("inject_probe.py" in str(part) for part in command):
                calls["inject"] += 1
                installed[0] = True
                return subprocess.CompletedProcess(command, 0, "installed", "")
            raise AssertionError(f"unexpected child command: {command}")

        confirmation_calls = []

        def fake_confirmation(_pid, _state, attempt_directory, _resume_address=0):
            confirmation_calls.append(attempt_directory)
            if len(confirmation_calls) == 1:
                raise RuntimeError("UNIQUE_VERIFIED_LOAD_CONFIRMATION_NOT_FOUND")
            return "TEST_ONLY 52544 100 200 300\n"

        output = io.StringIO()
        with patch.object(subject, "file_hash", lambda _path: "dll"), \
             patch.object(subject, "game_exe", lambda: directory / "eu4.exe"), \
             patch.object(subject, "get_value", lambda _name: "python"), \
             patch.object(subject, "probe_identity", fake_identity), \
             patch.object(subject, "confirmation_request", fake_confirmation), \
             patch.object(subject.subprocess, "run", fake_run), \
             patch.object(subject.time, "sleep", lambda _seconds: None), \
             contextlib.redirect_stdout(output):
            subject.main([
                "--pid", "52544", "--manifest", str(manifest),
                "--confirm-load-warning", "--wait-ready", "5",
            ])

        self.assertEqual(calls, {"preflight": 2, "inject": 1})
        self.assertEqual(len(confirmation_calls), 2)
        popup = directory / "popup-confirm.request"
        self.assertEqual(popup.read_text(encoding="ascii"), "TEST_ONLY 52544 100 200 300\n")
        installation = json.loads((directory / "installation.json").read_text(encoding="utf-8"))
        self.assertEqual(installation["ready_reason"], "verified_load_confirmation")
        self.assertEqual(len(installation["ready_attempts"]), 2)
        waiting_lines = [json.loads(line) for line in output.getvalue().splitlines() if line]
        self.assertEqual(waiting_lines[0]["reason"], "UNIQUE_VERIFIED_LOAD_CONFIRMATION_NOT_FOUND")
        final = json.loads(output.getvalue().splitlines()[-1])
        self.assertTrue(final["installed"])
        self.assertTrue(final["confirmation_queued"])

    def test_startup_dialog_scan_contract_is_bounded_and_resumable(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            report = directory / "startup-dialogs.json"
            report.write_text(json.dumps({"scanned_bytes": 3 * 1024**3,
                "scan_complete": False, "next_scan_address": "0x123400000"}), encoding="utf-8")
            # Exhausting one slice preserves the cursor for the next attempt.
            self.assertEqual(subject._read_scan_cursor(directory, 0), 0x123400000)
            report.write_text(json.dumps({"scan_complete": True,
                "next_scan_address": "0x7fffffffffff"}), encoding="utf-8")
            self.assertEqual(subject._read_scan_cursor(directory, 123), 0)

    def test_hung_startup_error_stops_wait_without_install_or_restart(self):
        temp, directory, _manifest, _dll = self._setup()
        self.addCleanup(temp.cleanup)
        ack_calls = []

        def fake_preflight(_pid, _python, attempt_directory, _deadline):
            return None, {"reason": "PREFLIGHT_RETURN_17",
                          "preflight": str(attempt_directory / "preflight.json")}

        def fake_acknowledge(_pid, attempt_directory):
            ack_calls.append(attempt_directory)
            return {
                "attempted": True,
                "acknowledged": False,
                "terminal": True,
                "reason": "STARTUP_ERROR_DIALOG_HUNG_NO_RETRY",
            }

        with patch.object(subject, "probe_identity", lambda _pid, _exe: self._identity()), \
             patch.object(subject, "game_exe", lambda: directory / "eu4.exe"), \
             patch.object(subject, "_preflight_once", fake_preflight), \
             patch.object(subject, "acknowledge_startup_error", fake_acknowledge), \
             patch.object(subject.time, "sleep", lambda _seconds: None):
            with self.assertRaises(SystemExit) as raised:
                subject._wait_until_ready(
                    52544, {"game_sha256": "game"}, directory, False, 10)

        self.assertEqual(str(raised.exception), "STARTUP_ERROR_DIALOG_HUNG_NO_RETRY")
        self.assertEqual(len(ack_calls), 1)
        self.assertFalse((directory / "installation.json").exists())

    def test_responsive_startup_error_is_not_reposted(self):
        temp, directory, _manifest, _dll = self._setup()
        self.addCleanup(temp.cleanup)
        preflight_calls = [0]
        ack_calls = []

        def fake_preflight(_pid, _python, attempt_directory, _deadline):
            preflight_calls[0] += 1
            if preflight_calls[0] < 3:
                return None, {"reason": "PREFLIGHT_RETURN_17",
                              "preflight": str(attempt_directory / "preflight.json")}
            return {"player_tag": "---"}, {"reason": "PREFLIGHT_READY",
                                             "preflight": "ready"}

        def fake_acknowledge(_pid, attempt_directory):
            ack_calls.append(attempt_directory)
            return {
                "attempted": True,
                "acknowledged": False,
                "terminal": False,
                "reason": "STARTUP_ERROR_DIALOG_NOT_DISMISSED",
            }

        with patch.object(subject, "probe_identity", lambda _pid, _exe: self._identity()), \
             patch.object(subject, "game_exe", lambda: directory / "eu4.exe"), \
             patch.object(subject, "_preflight_once", fake_preflight), \
             patch.object(subject, "acknowledge_startup_error", fake_acknowledge), \
             patch.object(subject.time, "sleep", lambda _seconds: None):
            _identity, state, confirmation, reason, attempts = subject._wait_until_ready(
                52544, {"game_sha256": "game"}, directory, False, 10)

        self.assertEqual(state["player_tag"], "---")
        self.assertIsNone(confirmation)
        self.assertEqual(reason, "unloaded_no_confirmation_requested")
        self.assertEqual(len(ack_calls), 1)
        self.assertEqual(len(attempts), 3)

    def test_current_build_versions_select_their_own_dll(self):
        for version in (21, 22):
            with self.subTest(version=version):
                temp, directory, manifest, dll = self._setup(version)
                self.addCleanup(temp.cleanup)
                with patch.object(subject, "file_hash", return_value="dll"), \
                        patch.object(subject, "_wait_until_ready", return_value=(
                            self._identity(), {}, None, "ready", [])), \
                        patch.object(subject, "_install_once") as install, \
                        patch.object(subject, "get_value", return_value="python"), \
                        contextlib.redirect_stdout(io.StringIO()):
                    subject.main(["--pid", "52544", "--manifest", str(manifest)])
                self.assertEqual(install.call_args.args[3], dll.resolve())
                self.assertEqual(install.call_count, 1)


if __name__ == "__main__":
    unittest.main()
