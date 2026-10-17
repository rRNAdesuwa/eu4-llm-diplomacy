from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from tools import save_observer_experiment as subject


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _make_save(path: Path, *, date: str = "1445.2.5", seed: int = 0) -> None:
    payload = bytes(((index * 37 + seed) % 251 for index in range(125_000)))
    meta = f'date="{date}"\nplayer="POR"\n'.encode("utf-8")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("meta", meta)
        archive.writestr("gamestate", payload)


class _FakeSession:
    def __init__(self, installation: Path, executable: Path):
        self.health_calls = 0

    def health(self) -> dict:
        self.health_calls += 1
        return {"status": "ready", "state_id": f"state-{self.health_calls}", "date_raw": 56459040}


class ObserverSaveExperimentTests(unittest.TestCase):
    def _setup(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        experiment = root / "observer-r3"
        experiment.mkdir()
        saves = root / "save games"
        saves.mkdir()
        installation = experiment / "installation.json"
        installation.write_text(json.dumps({
            "pid": 1234,
            "creation_filetime": 5678,
            "session_id": "1234-162e",
            "game_sha256": "game",
            "dll_sha256": "dll",
            "installation_returncode": 0,
        }), encoding="utf-8")
        (experiment / "control-probe.jsonl").write_text(
            '{"event":"diplomacy_observer_health","session_id":"1234-162e",'
            '"thread_changed":false,"state_readable":true,"player":"POR",'
            '"frames":1,"date_raw":56459040}\n', encoding="utf-8")
        return temp, root, experiment, saves, installation

    @staticmethod
    def _identity(_pid, _exe):
        return {
            "pid": 1234,
            "creation_filetime": 5678,
            "session_id": "1234-162e",
            "game_sha256": "game",
            "modules": [{"name": "observer.dll", "sha256": "dll"}],
        }

    @staticmethod
    def _probe(_pid, output, _deadline):
        state = {"date_raw": 56459040, "player_slot": 189, "paused_flag": 1}
        output.write_text(json.dumps(state), encoding="utf-8")
        return state

    def test_console_success_alone_cannot_archive_and_original_is_restored(self):
        temp, root, experiment, saves, installation = self._setup()
        self.addCleanup(temp.cleanup)
        autosave = saves / "autosave.eu4"
        _make_save(autosave, seed=1)
        before_hash = _sha(autosave)
        clock = [0.0]
        request_seen: list[bytes] = []

        def fake_sleep(_seconds):
            clock[0] += 0.5
            request = experiment / "game-control.request"
            if request.exists():
                request_seen.append(request.read_bytes())
                request.unlink()
                with (experiment / "control-probe.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write('{"event":"control_console_result","command":"autosave","success":true}\n')

        with patch.object(subject, "ObserverSession", _FakeSession), \
             patch.object(subject, "probe_identity", self._identity), \
             patch.object(subject, "game_exe", lambda: root / "eu4.exe"), \
             patch.object(subject, "user_data", lambda: root), \
             patch.object(subject.time, "monotonic", lambda: clock[0]), \
             patch.object(subject.time, "sleep", fake_sleep), \
             patch.object(subject, "_probe_control_state", self._probe), \
             patch.object(subject, "_emit"):
            with self.assertRaises(subject.ExperimentError) as raised:
                subject.run_experiment(installation, "llm_diplomacy_no_file.eu4", timeout=1)

        self.assertEqual(str(raised.exception), "AUTOSAVE_FILE_NOT_VERIFIED")
        self.assertEqual(request_seen, [subject.AUTOSAVE_TOKEN])
        self.assertFalse((saves / "llm_diplomacy_no_file.eu4").exists())
        self.assertEqual(_sha(autosave), before_hash)
        reports = list(experiment.glob("save-observer-report-*.json"))
        self.assertEqual(len(reports), 1)
        report = json.loads(reports[0].read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "failure")
        self.assertEqual(report["console_events"][0]["offset"],
                         report["log_offsets"]["start"])

    def test_success_archives_stable_save_and_restores_native_changes_without_deleting_unknown(self):
        temp, root, experiment, saves, installation = self._setup()
        self.addCleanup(temp.cleanup)
        autosave = saves / "autosave.eu4"
        old_autosave = saves / "old_autosave.eu4"
        older_autosave = saves / "older_autosave.eu4"
        _make_save(autosave, seed=2)
        _make_save(old_autosave, seed=3)
        _make_save(older_autosave, seed=4)
        originals = {path.name: _sha(path) for path in (autosave, old_autosave, older_autosave)}
        clock = [0.0]
        acted = [False]

        def fake_sleep(_seconds):
            clock[0] += 0.5
            request = experiment / "game-control.request"
            if request.exists() and not acted[0]:
                self.assertEqual(request.read_bytes(), subject.AUTOSAVE_TOKEN)
                request.unlink()
                _make_save(autosave, seed=9)
                _make_save(old_autosave, seed=10)
                _make_save(older_autosave, seed=11)
                (saves / "native_unknown.eu4").write_text("leave me", encoding="utf-8")
                with (experiment / "control-probe.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write('{"event":"control_console_result","command":"autosave","success":true}\n')
                acted[0] = True

        with patch.object(subject, "ObserverSession", _FakeSession), \
             patch.object(subject, "probe_identity", self._identity), \
             patch.object(subject, "game_exe", lambda: root / "eu4.exe"), \
             patch.object(subject, "user_data", lambda: root), \
             patch.object(subject.time, "monotonic", lambda: clock[0]), \
             patch.object(subject.time, "sleep", fake_sleep), \
             patch.object(subject, "_probe_control_state", self._probe), \
             patch.object(subject, "_emit"):
            report = subject.run_experiment(installation, "llm_diplomacy_ok.eu4", timeout=10)

        target = saves / "llm_diplomacy_ok.eu4"
        self.assertEqual(report["status"], "success")
        self.assertTrue(target.is_file())
        self.assertEqual(report["save"]["inspection"]["player"], "POR")
        self.assertGreater(report["save"]["inspection"]["payload_size"], 100_000)
        self.assertEqual({path.name: _sha(path) for path in (autosave, old_autosave, older_autosave)}, originals)
        self.assertTrue((saves / "native_unknown.eu4").is_file())
        backup = experiment / "save-backup"
        self.assertEqual(_sha(backup / "autosave.eu4"), originals["autosave.eu4"])
        self.assertEqual(_sha(backup / "old_autosave.eu4"), originals["old_autosave.eu4"])
        self.assertEqual(_sha(backup / "older_autosave.eu4"), originals["older_autosave.eu4"])
        self.assertEqual(set(report["backup"]["rotating_autosaves"]), {
            "autosave.eu4", "old_autosave.eu4", "older_autosave.eu4",
        })
        self.assertEqual(report["restore"]["unknown_new_save_files"], ["native_unknown.eu4"])

    def test_named_save_is_metadata_only_and_never_backed_up_or_overwritten(self):
        temp, root, experiment, saves, installation = self._setup()
        self.addCleanup(temp.cleanup)
        autosave = saves / "autosave.eu4"
        old_autosave = saves / "old_autosave.eu4"
        older_autosave = saves / "older_autosave.eu4"
        named = saves / "llm_diplomacy_named.eu4"
        _make_save(autosave, seed=2)
        _make_save(old_autosave, seed=3)
        _make_save(older_autosave, seed=4)
        _make_save(named, seed=77)
        named_hash = _sha(named)
        hashed_paths: list[str] = []
        original_hash = subject._sha256_stream

        def tracking_hash(path: Path) -> str:
            hashed_paths.append(path.name)
            return original_hash(path)

        clock = [0.0]
        acted = [False]

        def fake_sleep(_seconds):
            clock[0] += 0.5
            request = experiment / "game-control.request"
            if request.exists() and not acted[0]:
                request.unlink()
                _make_save(autosave, seed=9)
                with (experiment / "control-probe.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write('{"event":"control_console_result","command":"autosave","success":true}\n')
                acted[0] = True

        with patch.object(subject, "ObserverSession", _FakeSession), \
             patch.object(subject, "probe_identity", self._identity), \
             patch.object(subject, "game_exe", lambda: root / "eu4.exe"), \
             patch.object(subject, "user_data", lambda: root), \
             patch.object(subject.time, "monotonic", lambda: clock[0]), \
             patch.object(subject.time, "sleep", fake_sleep), \
             patch.object(subject, "_probe_control_state", self._probe), \
             patch.object(subject, "_sha256_stream", tracking_hash), \
             patch.object(subject, "_emit"):
            report = subject.run_experiment(installation, "llm_diplomacy_new.eu4", timeout=10)

        self.assertEqual(report["status"], "success")
        self.assertEqual(_sha(named), named_hash)
        self.assertNotIn(named.name, hashed_paths)
        self.assertFalse((Path(report["backup"]["path"]) / named.name).exists())
        named_record = report["backup"]["metadata_only_saves"][named.name.casefold()]
        self.assertNotIn("sha256", named_record)
        self.assertNotIn(named.name, {
            item["name"] for item in report["restore"]["metadata_changes"]
        })

    def test_restore_reports_size_and_mtime_changes_without_hashing_named_save(self):
        temp, _root, experiment, saves, _installation = self._setup()
        self.addCleanup(temp.cleanup)
        rotating = [saves / name for name in subject.ROTATING_AUTOSAVE_NAMES]
        for index, path in enumerate(rotating):
            _make_save(path, seed=index + 1)
        named = saves / "llm_diplomacy_named.eu4"
        _make_save(named, seed=88)
        baseline = subject._snapshot_saves(saves)
        backup = experiment / "save-backup"
        backup.mkdir()
        for record in subject._rotating_baseline(baseline).values():
            subject.shutil.copy2(saves / str(record["name"]), backup / str(record["name"]))

        before_named = baseline[named.name.casefold()]
        named.write_bytes(b"changed named save with a different size")
        changed_mtime = int(before_named["mtime_ns"]) + 10_000_000
        os.utime(named, ns=(changed_mtime, changed_mtime))
        hashed_paths: list[str] = []
        original_hash = subject._sha256_stream

        def tracking_hash(path: Path) -> str:
            hashed_paths.append(path.name)
            return original_hash(path)

        with patch.object(subject, "_sha256_stream", tracking_hash), \
             patch.object(subject, "_emit"):
            restore = subject._restore_originals(
                saves, backup, baseline, "llm_diplomacy_target.eu4", emit=subject._emit
            )

        self.assertEqual(restore["errors"], [])
        self.assertNotIn(named.name, hashed_paths)
        self.assertEqual(restore["restored"], [])
        self.assertEqual(len(restore["metadata_changes"]), 1)
        change = restore["metadata_changes"][0]
        self.assertEqual(change["name"], named.name)
        self.assertEqual(change["before"]["size"], before_named["size"])
        self.assertNotEqual(change["after"]["size"], before_named["size"])
        self.assertEqual(change["after"]["mtime_ns"], changed_mtime)

    def test_second_save_uses_report_stamped_backup_without_restarting_session(self):
        temp, root, experiment, saves, installation = self._setup()
        self.addCleanup(temp.cleanup)
        autosave = saves / "autosave.eu4"
        old_autosave = saves / "old_autosave.eu4"
        older_autosave = saves / "older_autosave.eu4"
        _make_save(autosave, seed=2)
        _make_save(old_autosave, seed=3)
        _make_save(older_autosave, seed=4)
        clock = [0.0]
        save_count = [0]

        def fake_sleep(_seconds):
            clock[0] += 0.5
            request = experiment / "game-control.request"
            if request.exists():
                request.unlink()
                save_count[0] += 1
                _make_save(autosave, seed=9 + save_count[0])
                with (experiment / "control-probe.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write('{"event":"control_console_result","command":"autosave","success":true}\n')

        patches = [
            patch.object(subject, "ObserverSession", _FakeSession),
            patch.object(subject, "probe_identity", self._identity),
            patch.object(subject, "game_exe", lambda: root / "eu4.exe"),
            patch.object(subject, "user_data", lambda: root),
            patch.object(subject.time, "monotonic", lambda: clock[0]),
            patch.object(subject.time, "sleep", fake_sleep),
            patch.object(subject, "_probe_control_state", self._probe),
            patch.object(subject, "_emit"),
        ]
        for context in patches:
            context.start()
        try:
            first = subject.run_experiment(installation, "llm_diplomacy_first.eu4", timeout=10)
            second = subject.run_experiment(installation, "llm_diplomacy_second.eu4", timeout=10)
        finally:
            for context in reversed(patches):
                context.stop()

        self.assertEqual(2, save_count[0])
        self.assertEqual("save-backup", Path(first["backup"]["path"]).name)
        second_backup = Path(second["backup"]["path"])
        self.assertTrue(second_backup.is_dir())
        self.assertNotEqual(Path(first["backup"]["path"]), second_backup)
        report_stamp = Path(second["report"]).stem.removeprefix("save-observer-report-")
        self.assertIn(report_stamp, second_backup.name)
        self.assertTrue((saves / "llm_diplomacy_first.eu4").is_file())
        self.assertTrue((saves / "llm_diplomacy_second.eu4").is_file())

    def test_existing_control_request_still_blocks_with_legacy_backup_present(self):
        temp, root, experiment, saves, installation = self._setup()
        self.addCleanup(temp.cleanup)
        legacy_backup = experiment / "save-backup"
        legacy_backup.mkdir()
        request = experiment / "game-control.request"
        request.write_bytes(subject.AUTOSAVE_TOKEN)
        with patch.object(subject, "ObserverSession", _FakeSession), \
             patch.object(subject, "probe_identity", self._identity), \
             patch.object(subject, "game_exe", lambda: root / "eu4.exe"), \
             patch.object(subject, "user_data", lambda: root), \
             patch.object(subject, "_emit"):
            with self.assertRaises(subject.ExperimentError) as raised:
                subject.run_experiment(installation, "llm_diplomacy_pending.eu4", timeout=1)
        self.assertEqual(str(raised.exception), "CONTROL_REQUEST_ALREADY_EXISTS")
        self.assertEqual(subject.AUTOSAVE_TOKEN, request.read_bytes())
        self.assertEqual([legacy_backup], [path for path in experiment.iterdir()
                                           if path.name == "save-backup"])
        self.assertEqual([], list(experiment.glob("save-backup-*")))

    def test_name_and_timeout_are_rejected_before_any_request(self):
        with self.assertRaises(subject.ExperimentError):
            subject.run_experiment(Path("missing.json"), "bad.eu4", timeout=301)
        with self.assertRaises(subject.ExperimentError):
            subject.run_experiment(Path("missing.json"), "llm_diplomacy_x.eu4", timeout=301)

    def test_existing_target_is_never_overwritten(self):
        temp, root, experiment, saves, installation = self._setup()
        self.addCleanup(temp.cleanup)
        target = saves / "llm_diplomacy_existing.eu4"
        target.write_bytes(b"keep this archive")
        original = target.read_bytes()
        with patch.object(subject, "ObserverSession", _FakeSession), \
             patch.object(subject, "probe_identity", self._identity), \
             patch.object(subject, "game_exe", lambda: root / "eu4.exe"), \
             patch.object(subject, "user_data", lambda: root), \
             patch.object(subject, "_emit"):
            with self.assertRaises(subject.ExperimentError) as raised:
                subject.run_experiment(installation, target.name, timeout=1)
        self.assertEqual(str(raised.exception), "TARGET_ALREADY_EXISTS_NO_OVERWRITE")
        self.assertEqual(target.read_bytes(), original)
        self.assertFalse((experiment / "game-control.request").exists())
        self.assertFalse((experiment / "save-backup").exists())

    def test_autosave_rotation_and_invalid_candidate_restart_stability_window(self):
        temp, _root, experiment, saves, _installation = self._setup()
        self.addCleanup(temp.cleanup)
        candidate = saves / "autosave.eu4"
        log = experiment / "control-probe.jsonl"
        baseline = {"autosave.eu4": {"signature": [1, 1]}}
        clock = [0.0]
        stat_calls = [0]
        inspection_calls = [0]
        emitted: list[dict[str, object]] = []

        def fake_stat(_path: Path) -> tuple[int, int]:
            stat_calls[0] += 1
            if stat_calls[0] == 2:
                raise FileNotFoundError("rotated during stat")
            if stat_calls[0] == 3:
                return (1, 1)
            return (2, 2) if stat_calls[0] == 1 else (3, 3)

        def fake_inspect(_path: Path) -> dict[str, object]:
            inspection_calls[0] += 1
            if inspection_calls[0] == 2:
                return {"valid": False, "reason": "FILE_ROTATED"}
            return {"valid": True, "date": "1445.2.5", "player": "POR"}

        def fake_log_events(_path: Path, _offset: int):
            yield 0, 1, {
                "event": "control_console_result",
                "command": "autosave",
                "success": True,
            }

        def fake_sleep(seconds: float) -> None:
            clock[0] += seconds

        def capture(state: str, **details: object) -> None:
            emitted.append({"state": state, **details})

        with patch.object(subject, "_find_casefold", lambda _directory, _name: candidate), \
             patch.object(subject, "_stat_signature", fake_stat), \
             patch.object(subject, "_inspect_save", fake_inspect), \
             patch.object(subject, "_read_log_events", fake_log_events), \
             patch.object(subject.time, "monotonic", lambda: clock[0]), \
             patch.object(subject.time, "sleep", fake_sleep):
            result = subject._wait_for_autosave(
                saves, baseline, log, 0, deadline=10.0, emit=capture
            )

        self.assertEqual(result[0], candidate)
        self.assertEqual(result[1]["valid"], True)
        self.assertGreaterEqual(stat_calls[0], 4)
        self.assertGreaterEqual(inspection_calls[0], 3)
        valid_events = [item for item in emitted if item["state"] == "autosave_candidate_valid"]
        self.assertEqual([item["signature"] for item in valid_events], [[2, 2], [3, 3]])
        stable_events = [item for item in emitted if item["state"] == "autosave_stable"]
        self.assertEqual(len(stable_events), 1)
        self.assertEqual(stable_events[0]["signature"], [3, 3])

    def test_snapshot_metadata_treats_rotating_file_disappearance_as_absent(self):
        class VanishingPath:
            name = "autosave.eu4"

            def stat(self):
                raise FileNotFoundError("rotated after enumeration")

        with patch.object(subject, "_save_paths", lambda _directory: [VanishingPath()]):
            self.assertEqual(subject._snapshot_metadata(Path("unused")), {})

        class InaccessiblePath:
            name = "autosave.eu4"

            def stat(self):
                raise PermissionError("permission denied")

        with patch.object(subject, "_save_paths", lambda _directory: [InaccessiblePath()]):
            with self.assertRaises(PermissionError):
                subject._snapshot_metadata(Path("unused"))


if __name__ == "__main__":
    unittest.main()
