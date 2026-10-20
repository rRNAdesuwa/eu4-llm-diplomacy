"""Offline preview evidence boundary tests; no native calls or process access."""
import contextlib
from copy import deepcopy
import io
import json
import os
import unittest
from unittest.mock import patch

from bridge.tests import test_diplomacy_lifecycle as fixtures
from tools import verify_diplomacy_preview as verifier


class PreviewVerificationTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.LifecycleVerificationTests()
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.f.build["purpose"] = "lifecycle_and_preview_no_send"
        self.f.build["source_sha256"][verifier.PREVIEW_SOURCE] = "B" * 64
        self.handles = {tag: hex((1 << 56) | (slot << 32) | int.from_bytes(tag.encode(), "little"))
                        for tag, slot in (("FRA", 122), ("ENG", 46), ("POR", 189))}
        countries = [{"tag": tag, "slot": (int(handle, 16) >> 32) & 0xFFFF,
                      "handle": handle, "identity_valid": True} for tag, handle in self.handles.items()]
        self.f.snapshot["state"]["countries"] = countries
        self.f.after_snapshot["state"]["countries"] = deepcopy(countries)
        self.f.events = self.session()
        self.f.write_inputs()

    def session(self, pid=None, allowed_count=3):
        pid = self.f.pid if pid is None else pid
        events = self.f.session(pid)
        events[0]["preview_automatic"] = False
        events.append({"event": "pair_preview_begin", "send_enabled": False, "submitted": False})
        index = 0
        for target in verifier.TARGETS:
            for action in verifier.lifecycle.ACTIONS:
                for value in (True, False):
                    index += 1
                    events.append({"event": "pair_preview_case", "case_index": index, "action": action,
                                   "mode": "positive" if value else "cancel", "value": value,
                                   "actor": "FRA", "target": target, "actor_handle": self.handles["FRA"], "target_handle": self.handles[target],
                                   "current_raw_date": 56456976, "state_verified": True, "initialized": True,
                                   "allowed": index <= allowed_count, "exception": 0, "destroyed": True,
                                   "thread_id": self.f.thread, "submitted": False})
        events.extend([{"event": "pair_preview_all_cases_complete", "cases": 20, "accepted": allowed_count,
                        "rejected": 20 - allowed_count, "thread_id": self.f.thread, "submitted": False},
                       {"event": "pair_preview_complete", "passed": True, "submitted": False},
                       {"event": "research_frame", "pid": pid, "thread": self.f.thread, "frames": 300,
                        "thread_changed": False, "world_ready": True, "send_enabled": False}])
        return events

    def verify(self):
        return verifier.verify(self.f.log, self.f.pid, self.f.before, self.f.after, self.f.manifest)

    def failed(self):
        self.f.write_inputs()
        result = self.verify()
        self.assertEqual(result["status"], "failed", result)
        self.assertFalse(result["runtime_verified"])
        self.assertFalse(result["execution_verified"])
        self.assertFalse(result["ai_acceptance_verified"])
        self.assertTrue(result["errors"])
        return result

    def test_allowed_and_rejected_are_legality_results_not_ai_acceptance(self):
        for legal in (0, 3, 20):
            with self.subTest(legal=legal):
                self.f.events = self.session(allowed_count=legal)
                self.f.write_inputs()
                result = self.verify()
                self.assertEqual(result["status"], "passed", result)
                self.assertTrue(result["runtime_verified"])
                self.assertEqual(result["verification_scope"], "native_legality_preview")
                self.assertEqual(result["session"]["legal_count"], legal)
                self.assertEqual(result["session"]["rejected_count"], 20 - legal)
                for field in ("execution_verified", "diplomatic_submission_verified", "ai_acceptance_verified", "settlement_verified", "all_game_state_unchanged_verified"):
                    self.assertFalse(result[field])
                self.assertFalse(result["build"]["loaded_dll_identity_verified"])

    def test_lifecycle_must_pass_in_the_same_latest_session(self):
        for change in (lambda e: e[3].update(clone_fields_ok=False),
                       lambda e: e[9].update(passed=False),
                       lambda e: e.pop(8), lambda e: e.pop(10)):
            self.f.events = self.session()
            change(self.f.events)
            self.failed()
        good = self.session()
        self.f.events = good + [good[0], good[1]]
        self.failed()
        self.f.events = good + [good[0], good[1]] + good[11:]
        self.failed()  # Preview cannot borrow the old session's lifecycle.
        self.f.events = self.session(self.f.pid + 1)
        self.failed()
        self.f.log.write_bytes(b"")
        self.assertFalse(self.verify()["runtime_verified"])

    def test_prior_or_later_other_pid_evidence_is_not_mixed_in(self):
        failed = self.session()
        failed[3]["destroyed"] = False
        failed[3]["clone_destroyed"] = False
        self.f.events = failed + self.session() + self.session(self.f.pid + 1)[:2]
        self.f.write_inputs()
        result = self.verify()
        self.assertTrue(result["runtime_verified"], result)
        self.assertEqual(result["session"]["install_line"], len(failed) + 1)

    def test_exact_twenty_unique_combinations_and_matching_mode_are_required(self):
        changes = [lambda e: e.pop(12), lambda e: e.insert(13, deepcopy(e[12])),
                   lambda e: e[13].update(value=True, mode="positive"),
                   lambda e: e[12].update(value=1), lambda e: e[12].update(mode="cancel"),
                   lambda e: e[12].update(action="allianceaction"), lambda e: e[12].update(target="CAS"),
                   lambda e: e[12].update(actor="POR"), lambda e: e[12].update(case_index=True),
                   lambda e: e[12].update(case_index=20)]
        for change in changes:
            self.f.events = self.session()
            change(self.f.events)
            self.failed()

    def test_object_safety_thread_and_no_submission_flags_are_strict(self):
        changes = [("state_verified", False), ("initialized", False), ("destroyed", False), ("destroyed", 1),
                   ("exception", False), ("exception", 0xC0000005), ("thread_id", self.f.thread + 1),
                   ("submitted", True), ("submitted", 0), ("allowed", 1), ("allowed", None)]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                self.f.events = self.session()
                self.f.events[12][key] = value
                self.failed()
        self.f.events = self.session()
        del self.f.events[12]["initialized"]
        self.failed()

    def test_begin_completion_counts_and_final_healthy_frame_are_required(self):
        changes = [lambda e: e[0].update(preview_automatic=True), lambda e: e.pop(11),
                   lambda e: e.insert(12, deepcopy(e[11])), lambda e: e[32].update(accepted=7),
                   lambda e: e[32].update(rejected=0), lambda e: e[32].update(cases=19),
                   lambda e: e[32].update(thread_id=1), lambda e: e[33].update(passed=1),
                   lambda e: e.pop(32), lambda e: e.pop(33), lambda e: e.pop(),
                   lambda e: e[-1].update(world_ready=False), lambda e: e[1].update(thread_changed=True),
                   lambda e: e[1].update(thread=1), lambda e: e[1].update(pid=1),
                   lambda e: e.insert(-1, {"event": "pair_preview_rejected", "submitted": False})]
        for change in changes:
            self.f.events = self.session()
            change(self.f.events)
            self.failed()

    def test_case_dates_and_handles_must_bind_to_unchanged_snapshot_identities(self):
        for key, value in (("current_raw_date", 56456977), ("actor_handle", "0x1"),
                           ("target_handle", self.handles["POR"]),
                           ("actor_handle", hex(int(self.handles["FRA"], 16) + (1 << 56)))):
            self.f.events = self.session()
            self.f.events[12][key] = value
            self.failed()
        self.f.events = self.session()
        for case in self.f.events:
            if case["event"] == "pair_preview_case":
                case["current_raw_date"] += 1
        self.failed()  # Even twenty mutually consistent but stale dates fail.

    def test_snapshot_changes_and_missing_country_identity_fail(self):
        baseline = deepcopy(self.f.after_snapshot)
        changes = [lambda r: r["state"]["countries"].pop(),
                   lambda r: r["state"]["countries"].append(deepcopy(r["state"]["countries"][0])),
                   lambda r: r["state"]["countries"][1].update(identity_valid=False),
                   lambda r: r["state"]["relation_cooldown"].update(threshold_raw=43808761),
                   lambda r: r["state"]["player"].update(address="0x20010008"),
                   lambda r: r["state"]["actor_diplomats"]["entries"][0].update(state_raw_18=2),
                   lambda r: r["source"].update(pid=1)]
        for change in changes:
            self.f.after_snapshot = deepcopy(baseline)
            change(self.f.after_snapshot)
            self.failed()
        self.f.after_snapshot = deepcopy(baseline)
        self.f.after_snapshot["state"]["uncompared_treasury"] = 1
        self.f.write_inputs()
        self.assertTrue(self.verify()["runtime_verified"])

    def test_manifest_requires_preview_source_and_exact_build(self):
        baseline = deepcopy(self.f.build)
        for change in (lambda b: b.update(purpose="lifecycle_only_no_send"),
                       lambda b: b["source_sha256"].pop(verifier.PREVIEW_SOURCE),
                       lambda b: b.update(game_sha256="0" * 64),
                       lambda b: b.update(dll_sha256="not-a-hash"),
                       lambda b: b.update(built_at_utc="2026-10-07T13:00:00+00:00")):
            self.f.build = deepcopy(baseline)
            change(self.f.build)
            self.failed()

    def test_malformed_and_oversize_evidence_cannot_pass(self):
        good = self.f.log.read_bytes()
        for bad in (b'{"event":"pair_preview_complete","event":"research_frame"}\n', b'{"bad":NaN}\n', b'{}'):
            self.f.log.write_bytes(good + bad)
            self.assertFalse(self.verify()["runtime_verified"])
        self.f.log.write_bytes(good)
        with patch.object(verifier, "MAX_LOG_BYTES", 16), patch.object(verifier, "MAX_LINE_BYTES", 10):
            self.assertFalse(self.verify()["runtime_verified"])
        with patch.object(verifier, "MAX_LINE_BYTES", 10):
            self.assertFalse(self.verify()["runtime_verified"])

    def test_cli_writes_failure_and_cannot_overwrite_or_hardlink_inputs(self):
        self.f.log.write_bytes(b"")
        output = self.f.root / "preview.json"
        output.write_text('{"status":"passed","runtime_verified":true}')
        args = ["--log", str(self.f.log), "--pid", str(self.f.pid), "--before", str(self.f.before), "--after", str(self.f.after),
                "--build-manifest", str(self.f.manifest), "--output", str(output)]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(verifier.main(args), 2)
        self.assertFalse(json.loads(output.read_text())["runtime_verified"])
        original = self.f.before.read_bytes()
        for path in (self.f.before, self.f.root / "linked.json"):
            if path != self.f.before:
                os.link(self.f.before, path)
            args[-1] = str(path)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(verifier.main(args), 2)
        self.assertEqual(self.f.before.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
