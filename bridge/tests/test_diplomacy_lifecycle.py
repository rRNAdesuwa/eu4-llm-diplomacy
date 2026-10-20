"""Synthetic evidence tests; no process access, DLL loading or native calls."""
import contextlib
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import verify_diplomacy_lifecycle as verifier


class LifecycleVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.log = self.root / "research.jsonl"
        self.before = self.root / "before.json"
        self.after = self.root / "after.json"
        self.manifest = self.root / "build.json"
        self.pid, self.thread = 1234, 5678
        self.events = self.session()
        handle = (1 << 56) | (122 << 32) | int.from_bytes(b"FRA", "little")
        self.snapshot = {
            "schema_version": 1, "read_only": True, "captured_at_utc": "2026-10-07T12:00:00+00:00",
            "build": {"sha256": verifier.LOCAL_SHA256, "executable_sha256": verifier.LOCAL_SHA256},
            "source": {"kind": "live_process", "pid": self.pid, "module_base": "0x140000000", "atomic_snapshot": False},
            "state": {"status": "bounded_snapshot", "country_identities_verified": True, "actor": "FRA", "target": "ENG",
                      "current_raw_date": 56456976,
                      "player": {"slot": 122, "tag": "FRA", "address": "0x20010000", "handle": hex(handle), "identity_valid": True},
                      "snapshot_consistency": {"globals_unchanged": True, "player_unchanged": True, "date_unchanged": True, "atomic": False},
                      "actor_diplomats": {"manager": "0x20020000", "vector_begin": "0x20030000", "vector_end": "0x20030008",
                                          "entry_count": 1, "state_zero_count": 1,
                                          "entries": [{"index": 0, "address": "0x20040000", "state_raw_18": 0, "state_zero_available_candidate": True}]},
                      "relation_cooldown": {"address": "0x20050000", "threshold_raw": 43808760,
                                            "current_raw_date": 56456976, "strict_date_comparison": True}},
        }
        self.after_snapshot = deepcopy(self.snapshot)
        self.after_snapshot["captured_at_utc"] = "2026-10-07T12:01:00+00:00"
        self.build = {"purpose": "lifecycle_only_no_send", "game_sha256": verifier.LOCAL_SHA256,
                      "built_at_utc": "2026-10-07T11:59:00+00:00", "dll_sha256": "D" * 64,
                      "source_sha256": {source: "A" * 64 for source in verifier.SOURCES}, "runtime_verified": False}
        self.write_inputs()

    def tearDown(self):
        self.temporary.cleanup()

    def session(self, pid=None):
        pid = self.pid if pid is None else pid
        result = [{"event": "research_hook_installed", "pid": pid, "window_thread": self.thread,
                   "frame_rva": verifier.FRAME_RVA, "send_enabled": False, "selftest_automatic": False},
                  {"event": "research_frame", "pid": pid, "thread": self.thread, "frames": 100,
                   "thread_changed": False, "world_ready": True, "send_enabled": False},
                  {"event": "pair_selftest_begin", "send_enabled": False}]
        for action, size in verifier.ACTIONS.items():
            result.append({"event": "pair_lifecycle", "action": action, "size": size, "thread_id": self.thread,
                           "factory_fields_ok": True, "clone_fields_ok": True, "original_destroyed": True,
                           "clone_destroyed": True, "exception": 0, "submitted": False})
        result.extend([{"event": "pair_lifecycle_complete", "passed": 5, "submitted": False},
                       {"event": "pair_selftest_complete", "passed": True, "submitted": False},
                       {"event": "research_frame", "pid": pid, "thread": self.thread, "frames": 200,
                        "thread_changed": False, "world_ready": True, "send_enabled": False}])
        return result

    def write_inputs(self):
        self.log.write_text("".join(json.dumps(event) + "\n" for event in self.events), encoding="utf-8")
        self.before.write_text(json.dumps(self.snapshot), encoding="utf-8")
        self.after.write_text(json.dumps(self.after_snapshot), encoding="utf-8")
        self.manifest.write_text(json.dumps(self.build), encoding="utf-8")

    def verify(self):
        return verifier.verify(self.log, self.pid, self.before, self.after, self.manifest)

    def assert_failed(self, result=None):
        result = self.verify() if result is None else result
        self.assertEqual(result["status"], "failed", result)
        self.assertFalse(result["runtime_verified"])
        self.assertFalse(result["execution_verified"])
        self.assertFalse(result["all_game_state_unchanged_verified"])
        self.assertTrue(result["errors"])
        return result

    def test_complete_lifecycle_only_passes_with_healthy_later_frame(self):
        result = self.verify()
        self.assertEqual(result["status"], "passed", result)
        self.assertTrue(result["runtime_verified"])
        self.assertEqual(result["verification_scope"], "lifecycle_only")
        self.assertFalse(result["execution_verified"])
        self.assertFalse(result["diplomatic_submission_verified"])
        self.assertFalse(result["preview_verified"])
        self.assertFalse(result["all_game_state_unchanged_verified"])
        self.assertFalse(result["build"]["loaded_dll_identity_verified"])
        self.assertEqual(set(result["session"]["lifecycle"]), set(verifier.ACTIONS))
        self.assertTrue(result["snapshot_comparison"]["all_compared_fields_equal"])

    def test_empty_log_and_missing_requested_pid_never_pass(self):
        self.log.write_bytes(b"")
        self.assert_failed()
        self.events = self.session(self.pid + 1)
        self.write_inputs()
        self.assert_failed()

    def test_latest_requested_pid_session_wins_even_when_incomplete(self):
        self.events += self.session()[:2]
        self.write_inputs()
        result = self.assert_failed()
        self.assertEqual(result["session"]["install_line"], 12)
        self.assertEqual(result["session"]["lifecycle"], {})

    def test_prior_failures_and_later_other_pid_sessions_are_excluded(self):
        failed = self.session()
        failed[3]["exception"] = 0xC0000005
        self.events = failed + self.session() + self.session(self.pid + 1)
        self.events[-1]["thread_changed"] = True
        self.write_inputs()
        result = self.verify()
        self.assertTrue(result["runtime_verified"], result)
        self.assertEqual(result["session"]["install_line"], 12)
        self.assertEqual(result["session"]["session_end_line"], 22)

    def test_every_frame_and_lifecycle_record_must_match_window_thread(self):
        for index, field, value in ((1, "thread", self.thread + 1), (-1, "thread_changed", True),
                                    (3, "thread_id", self.thread + 1), (-1, "pid", self.pid + 1),
                                    (-1, "frames", 100), (0, "window_thread", False)):
            with self.subTest(index=index, field=field):
                self.events = self.session()
                self.events[index][field] = value
                self.write_inputs()
                self.assert_failed()

    def test_factory_clone_destroy_exception_and_boolean_flags_are_strict(self):
        cases = [(key, False) for key in ("factory_fields_ok", "clone_fields_ok", "original_destroyed", "clone_destroyed")]
        cases += [("exception", 0xC0000005), ("exception", False), ("submitted", True),
                  ("submitted", 0), ("factory_fields_ok", 1), ("size", 104)]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                self.events = self.session()
                self.events[3][key] = value
                self.write_inputs()
                self.assert_failed()

    def test_missing_duplicate_unknown_and_unstarted_actions_fail(self):
        base = self.session()
        cases = [base[:3] + base[4:], base[:4] + [base[3]] + base[4:], base[:2] + base[3:]]
        unknown = self.session()
        unknown[3]["action"] = "unverified_action"
        cases.append(unknown)
        for events in cases:
            with self.subTest(events=events):
                self.events = events
                self.write_inputs()
                self.assert_failed()

    def test_completion_and_final_post_test_healthy_frame_are_required(self):
        base = self.session()
        cases = [base[:-1], base[:8] + base[9:], base[:9] + base[10:]]
        for index, key, value in ((8, "passed", 4), (9, "passed", False), (-1, "world_ready", False), (9, "passed", 1)):
            changed = self.session()
            changed[index][key] = value
            cases.append(changed)
        for events in cases:
            with self.subTest(events=events):
                self.events = events
                self.write_inputs()
                self.assert_failed()

    def test_preview_build_and_events_never_count_as_lifecycle_proof(self):
        self.build["purpose"] = "lifecycle_and_preview_no_send"
        self.build["source_sha256"]["work/native/preview-1375.cpp"] = "B" * 64
        preview = {"event": "pair_preview_case", "allowed": True, "exception": 0, "submitted": False}
        self.events.insert(-1, preview)
        self.write_inputs()
        result = self.verify()
        self.assertTrue(result["runtime_verified"], result)
        self.assertFalse(result["preview_verified"])
        self.assertEqual(result["session"]["ignored_preview_events"], 1)
        self.events = [self.events[0], self.events[1], preview, self.events[-1]]
        self.write_inputs()
        self.assert_failed()
        self.events = self.session()
        self.events.insert(-1, dict(preview, submitted=True))
        self.write_inputs()
        self.assert_failed()

    def test_compared_state_changes_are_detected_without_claiming_global_immutability(self):
        changes = [lambda s: s["player"].update(address="0x20010008"),
                   lambda s: (s.update(current_raw_date=56456977), s["relation_cooldown"].update(current_raw_date=56456977)),
                   lambda s: s["relation_cooldown"].update(threshold_raw=43808761),
                   lambda s: (s["actor_diplomats"]["entries"][0].update(state_raw_18=2, state_zero_available_candidate=False), s["actor_diplomats"].update(state_zero_count=0))]
        for change in changes:
            with self.subTest(change=change):
                self.after_snapshot = deepcopy(self.snapshot)
                self.after_snapshot["captured_at_utc"] = "2026-10-07T12:01:00+00:00"
                change(self.after_snapshot["state"])
                self.write_inputs()
                self.assert_failed()
        self.after_snapshot = deepcopy(self.snapshot)
        self.after_snapshot["captured_at_utc"] = "2026-10-07T12:01:00+00:00"
        self.after_snapshot["state"]["uncompared_treasury_example"] = 123
        self.write_inputs()
        result = self.verify()
        self.assertTrue(result["runtime_verified"])
        self.assertFalse(result["all_game_state_unchanged_verified"])

    def test_missing_inconsistent_stale_or_foreign_snapshots_fail(self):
        baseline = deepcopy(self.after_snapshot)
        changes = [lambda r: r["source"].update(pid=self.pid + 1),
                   lambda r: r["source"].update(kind="minidump"),
                   lambda r: r.update(captured_at_utc=self.snapshot["captured_at_utc"]),
                   lambda r: r["state"]["snapshot_consistency"].update(date_unchanged=False),
                   lambda r: r["state"].update(actor_diplomats={"status": "unavailable"}),
                   lambda r: r["state"].update(relation_cooldown={"status": "unavailable"}),
                   lambda r: r["state"]["actor_diplomats"].update(state_zero_count=0),
                   lambda r: r["state"]["player"].update(handle="0x1"),
                   lambda r: r.update(state=[]), lambda r: r["source"].update(module_base="0x150000000")]
        for change in changes:
            with self.subTest(change=change):
                self.after_snapshot = deepcopy(baseline)
                change(self.after_snapshot)
                self.write_inputs()
                self.assert_failed()
        self.assert_failed(verifier.verify(self.log, self.pid, self.before, self.before, self.manifest))

    def test_build_hash_purpose_and_source_hash_checks_fail_closed(self):
        for key, value in (("game_sha256", "0" * 64), ("dll_sha256", "bad"), ("purpose", "send_enabled"),
                           ("source_sha256", {}), ("built_at_utc", "2026-10-07T13:00:00+00:00")):
            with self.subTest(key=key):
                original = deepcopy(self.build)
                self.build[key] = value
                self.write_inputs()
                self.assert_failed()
                self.build = original
        self.after_snapshot["build"]["sha256"] = "0" * 64
        self.write_inputs()
        self.assert_failed()

    def test_malformed_duplicate_key_and_truncated_records_fail_selected_session(self):
        good = self.log.read_bytes()
        for bad in (b'{"event":"research_frame",}\n', b'{"event":"research_frame","event":"pair_selftest_complete"}\n',
                    b'{"event":"research_frame"}', b'{"value":NaN}\n'):
            with self.subTest(bad=bad):
                self.log.write_bytes(good + bad)
                self.assert_failed()
        self.log.write_bytes(b"historical malformed line\n" + good)
        self.assertTrue(self.verify()["runtime_verified"])

    def test_byte_and_line_limits_are_enforced(self):
        with patch.object(verifier, "MAX_LOG_BYTES", 10):
            self.assert_failed()
        self.log.write_bytes(self.log.read_bytes() + b"x" * 200 + b"\n")
        with patch.object(verifier, "MAX_LINE_BYTES", 100):
            self.assert_failed()
        with patch.object(verifier, "MAX_JSON_BYTES", 10):
            self.assert_failed()

    def test_cli_writes_failure_for_empty_log_and_never_overwrites_input(self):
        self.log.write_bytes(b"")
        output = self.root / "result.json"
        output.write_text('{"status":"passed","runtime_verified":true}')
        args = ["--log", str(self.log), "--pid", str(self.pid), "--before", str(self.before), "--after", str(self.after),
                "--build-manifest", str(self.manifest), "--output", str(output)]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(verifier.main(args), 2)
        self.assert_failed(json.loads(output.read_text(encoding="utf-8")))
        before_bytes = self.before.read_bytes()
        args[-1] = str(self.before)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(verifier.main(args), 2)
        self.assertEqual(self.before.read_bytes(), before_bytes)
        linked = self.root / "hardlinked-input.json"
        os.link(self.before, linked)
        args[-1] = str(linked)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(verifier.main(args), 2)
        self.assertEqual(self.before.read_bytes(), before_bytes)


if __name__ == "__main__":
    unittest.main()
