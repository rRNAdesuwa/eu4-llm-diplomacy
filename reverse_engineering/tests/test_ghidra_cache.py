from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from reverse_engineering.ghidra_cache import (
    CacheError,
    _CacheLock,
    _complete_evidence,
    _project_save_evidence,
    _target_from_cache,
    _status_payload,
)


def make_cache(root: Path) -> Path:
    cache = root / "cache"
    project = cache / "project"
    rep = project / "EU4Full.rep"
    (rep / "idata").mkdir(parents=True)
    (rep / "project.prp").write_text("saved", encoding="utf-8")
    project.joinpath("EU4Full.gpr").write_text("", encoding="utf-8")
    (cache / "input").mkdir()
    (cache / "input" / "eu4.exe").write_bytes(b"fixture")
    digest = hashlib.sha256(b"fixture").hexdigest()
    report = {
        "target_sha256": digest,
        "program": "eu4.exe",
        "stage": "analysis",
        "analysis_timed_out": False,
        "default_auto_analysis_completed": True,
    }
    (cache / "analysis-status.json").write_text(json.dumps(report), encoding="utf-8")
    save_line = "INFO REPORT: Save succeeded for: /eu4.exe (EU4Full:/eu4.exe)\n"
    (cache / "analysis.log").write_text(save_line, encoding="utf-8")
    (cache / "analysis-console.log").write_text(save_line, encoding="utf-8")
    (cache / "analysis-scripts.log").write_text("", encoding="utf-8")
    (cache / "build.json").write_text(
        json.dumps(
            {
                "directory": str(cache),
                "project_name": "EU4Full",
                "program": "eu4.exe",
                "target_sha256": digest,
                "status": "complete",
                "analysis_report": report,
                "stages": [
                    {
                        "stage": "analysis",
                        "attempt": 1,
                        "exit_code": 0,
                        "reason": "completed",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return cache


class GhidraCacheSafetyTests(unittest.TestCase):
    def test_process_mode_save_message_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = make_cache(Path(temporary))
            for name in ("analysis.log", "analysis-console.log"):
                (cache / name).write_text("INFO REPORT: Save succeeded for processed file: /eu4.exe (HeadlessAnalyzer)\n", encoding="utf-8")
            metadata = json.loads((cache / "build.json").read_text(encoding="utf-8"))
            self.assertTrue(_complete_evidence(cache, metadata))

    def test_lock_is_exclusive_and_released_only_by_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            first = _CacheLock(cache)
            first.acquire()
            try:
                with self.assertRaisesRegex(CacheError, "不会自动删除"):
                    _CacheLock(cache).acquire()
            finally:
                first.release()
            self.assertFalse((cache / "cache.lock").exists())

    def test_completion_requires_saved_project_and_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = make_cache(Path(temporary))
            metadata = json.loads((cache / "build.json").read_text(encoding="utf-8"))
            evidence = _project_save_evidence(cache, metadata)
            self.assertTrue(evidence["saved"])
            self.assertTrue(_complete_evidence(cache, metadata))
            (cache / "project" / "EU4Full.lock").write_text("live", encoding="utf-8")
            self.assertFalse(_complete_evidence(cache, metadata))

    def test_status_reports_incomplete_when_cache_lock_is_present(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = make_cache(Path(temporary))
            lock = _CacheLock(cache)
            lock.acquire()
            try:
                payload = _status_payload(cache)
                self.assertTrue(payload["project_save_evidence"]["saved"])
                self.assertFalse(payload["complete"])
                self.assertTrue(payload["lock"]["present"])
            finally:
                lock.release()

    def test_nonempty_save_failure_log_cannot_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = make_cache(Path(temporary))
            (cache / "analysis.log").write_text(
                "REPORT: Save failed for: /eu4.exe\nERROR OOM while saving\n",
                encoding="utf-8",
            )
            metadata = json.loads((cache / "build.json").read_text(encoding="utf-8"))
            evidence = _project_save_evidence(cache, metadata)
            self.assertFalse(evidence["saved"])
            self.assertFalse(_complete_evidence(cache, metadata))

    def test_report_target_mismatch_cannot_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = make_cache(Path(temporary))
            report = json.loads((cache / "analysis-status.json").read_text(encoding="utf-8"))
            report["target_sha256"] = "1" * 64
            (cache / "analysis-status.json").write_text(json.dumps(report), encoding="utf-8")
            metadata = json.loads((cache / "build.json").read_text(encoding="utf-8"))
            self.assertFalse(_complete_evidence(cache, metadata))

    def test_second_failed_attempt_does_not_inherit_first_success(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = make_cache(Path(temporary))
            failed_report = {
                "target_sha256": json.loads((cache / "build.json").read_text(encoding="utf-8"))["target_sha256"],
                "program": "eu4.exe",
                "stage": "analysis",
                "analysis_timed_out": False,
                "default_auto_analysis_completed": False,
            }
            (cache / "analysis-2-status.json").write_text(json.dumps(failed_report), encoding="utf-8")
            (cache / "analysis-2.log").write_text(
                "REPORT: Save failed for: /eu4.exe\nERROR OOM\n", encoding="utf-8"
            )
            (cache / "analysis-2-console.log").write_text(
                "REPORT: Save failed for: /eu4.exe\nERROR OOM\n", encoding="utf-8"
            )
            (cache / "analysis-2-scripts.log").write_text("", encoding="utf-8")
            metadata = json.loads((cache / "build.json").read_text(encoding="utf-8"))
            metadata["analysis_report"] = failed_report
            metadata["stages"].append(
                {
                    "stage": "analysis",
                    "attempt": 2,
                    "exit_code": 1,
                    "reason": "provider_failed",
                    "report_path": str(cache / "analysis-2-status.json"),
                    "log_path": str(cache / "analysis-2.log"),
                    "console_path": str(cache / "analysis-2-console.log"),
                    "script_log_path": str(cache / "analysis-2-scripts.log"),
                }
            )
            self.assertFalse(_complete_evidence(cache, metadata))

    def test_cache_metadata_rejects_program_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            (cache / "input").mkdir()
            (cache / "build.json").write_text(
                json.dumps(
                    {
                        "program": "..\\outside.exe",
                        "project_name": "EU4Full",
                        "target_sha256": "0" * 64,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(CacheError, "program"):
                _target_from_cache(cache)

    def test_cache_metadata_rejects_project_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            (cache / "build.json").write_text(
                json.dumps(
                    {
                        "program": "eu4.exe",
                        "project_name": "..\\outside-project",
                        "target_sha256": "0" * 64,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(CacheError, "project_name"):
                _target_from_cache(cache)


if __name__ == "__main__":
    unittest.main()

