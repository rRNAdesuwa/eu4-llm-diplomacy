"""Synthetic command-lifecycle evidence tests; no engine or process access."""
import contextlib
from copy import deepcopy
import io
import json
import os
import unittest
from unittest.mock import patch

from bridge.tests import test_diplomacy_preview as fixtures
from tools import verify_diplomacy_command as verifier


class CommandVerificationTests(unittest.TestCase):
    def setUp(self):
        self.p = fixtures.PreviewVerificationTests()
        self.p.setUp()
        self.addCleanup(self.p.doCleanups)
        self.f = self.p.f
        self.f.build["purpose"] = verifier.lifecycle.PIPELINE_PURPOSE
        self.f.build["source_sha256"] = {source: "C" * 64 for source in verifier.lifecycle.PIPELINE_SOURCES}
        self.f.events = self.session()
        self.f.write_inputs()

    def session(self, pid=None, legal=4):
        events = self.p.session(pid)
        events[0]["command_automatic"] = False
        command = self.p.session(pid, allowed_count=legal)[11:]
        for row in command:
            if row["event"].startswith("pair_preview_"):
                row["event"] = row["event"].replace("pair_preview_", "pair_command_", 1)
            if row["event"] == "pair_command_case":
                row.pop("destroyed")
                row.update({flag: True for flag in verifier.TRUE_FIELDS})
                row.update(ownership_uncertain=False, clone_lifetime_observation=verifier.CLONE_OBSERVATION)
            if row["event"] == "research_frame":
                row["frames"] = 400
        return events + command

    def row(self, name, occurrence=0):
        return [row for row in self.f.events if row["event"] == name][occurrence]

    def verify(self):
        return verifier.verify(self.f.log, self.f.pid, self.f.before, self.f.after, self.f.manifest)

    def failed(self):
        self.f.write_inputs()
        result = self.verify()
        self.assertEqual(result["status"], "failed", result)
        self.assertFalse(result["runtime_verified"])
        self.assertFalse(result["execution_verified"])
        self.assertTrue(result["errors"])
        return result

    def test_success_requires_twenty_command_cases_and_false_gate_is_normal(self):
        for legal in (0, 4, 20):
            self.f.events = self.session(legal=legal)
            self.f.write_inputs()
            result = self.verify()
            self.assertTrue(result["runtime_verified"], result)
            self.assertEqual(result["verification_scope"], "command_lifecycle_only")
            self.assertEqual(result["summary"]["legal_count"], legal)
            self.assertEqual(result["summary"]["rejected_count"], 20 - legal)
            self.assertEqual(result["session"]["prior_lifecycle_and_preview"]["legal_count"], 3)
            self.assertEqual(len(result["session"]["command_phase"]["cases"]), 20)
            self.assertNotIn("destroyed", result["session"]["command_phase"]["cases"][0])
            for flag in ("execution_verified", "diplomatic_submission_verified", "ai_acceptance_verified", "settlement_verified",
                         "clone_deallocation_independently_observed", "entire_dll_no_send_verified", "all_game_state_unchanged_verified"):
                self.assertFalse(result[flag])

    def test_each_wrapper_ownership_and_destructor_flag_is_required_and_strict(self):
        for field in (*verifier.TRUE_FIELDS, "initialized", "state_verified"):
            for invalid in (False, 1, None):
                with self.subTest(field=field, value=invalid):
                    self.f.events = self.session()
                    self.row("pair_command_case")[field] = invalid
                    self.failed()
        for field, value in (("ownership_uncertain", True), ("ownership_uncertain", 0),
                             ("clone_lifetime_observation", "directly_freed"), ("exception", 0xC0000005),
                             ("exception", False), ("allowed", 1), ("submitted", True), ("submitted", 0),
                             ("thread_id", self.f.thread + 1)):
            self.f.events = self.session()
            self.row("pair_command_case")[field] = value
            self.failed()

    def test_prior_lifecycle_and_preview_cannot_substitute_for_command_or_be_borrowed(self):
        for name, field in (("pair_lifecycle", "clone_fields_ok"), ("pair_selftest_complete", "passed"),
                            ("pair_preview_case", "initialized"), ("pair_preview_complete", "passed")):
            self.f.events = self.session()
            self.row(name)[field] = False
            self.failed()
        self.f.events = self.session()[:35]
        self.failed()  # Twenty preview records never prove command behavior.
        self.f.events = self.session()
        hook = deepcopy(self.f.events[0])
        self.f.events.insert(35, hook)
        self.failed()
        self.f.events = self.session() + [hook]
        self.failed()  # Latest incomplete installation wins.
        self.f.events = self.session(self.f.pid + 1)
        self.failed()
        self.f.log.write_bytes(b"")
        self.assertFalse(self.verify()["runtime_verified"])

    def test_all_twenty_combinations_mode_and_indices_are_unique(self):
        for field, value in (("action", "allianceaction"), ("target", "CAS"), ("actor", "POR"),
                             ("value", 1), ("mode", "cancel"), ("case_index", True), ("case_index", 20)):
            self.f.events = self.session()
            self.row("pair_command_case")[field] = value
            self.failed()
        self.f.events = self.session()
        self.row("pair_command_case", 1).update(value=True, mode="positive")
        self.failed()
        self.f.events = self.session()
        self.f.events.remove(self.row("pair_command_case"))
        self.failed()
        self.f.events = self.session()
        self.f.events.insert(37, deepcopy(self.row("pair_command_case")))
        self.failed()

    def test_explicit_marker_completion_order_counts_and_post_command_frame(self):
        changes = [lambda: self.f.events[0].update(command_automatic=True),
                   lambda: self.f.events.remove(self.row("pair_command_begin")),
                   lambda: self.row("pair_command_all_cases_complete").update(accepted=7),
                   lambda: self.row("pair_command_all_cases_complete").update(cases=19),
                   lambda: self.row("pair_command_all_cases_complete").update(thread_id=1),
                   lambda: self.row("pair_command_complete").update(passed=1),
                   lambda: self.f.events.remove(self.row("pair_command_all_cases_complete")),
                   lambda: self.f.events.pop(), lambda: self.f.events[-1].update(world_ready=False),
                   lambda: self.f.events[34].update(world_ready=False),
                   lambda: self.f.events.insert(-1, {"event": "pair_command_rejected", "submitted": False})]
        for change in changes:
            self.f.events = self.session()
            change()
            self.failed()

    def test_country_identity_and_date_bind_to_both_snapshots(self):
        for field, value in (("target_handle", self.p.handles["POR"]), ("actor_handle", "0x1"), ("current_raw_date", 56456977)):
            self.f.events = self.session()
            self.row("pair_command_case")[field] = value
            self.failed()
        self.f.events = self.session()
        for row in self.f.events:
            if row["event"] == "pair_command_case":
                row["current_raw_date"] += 1
        self.failed()
        self.f.events = self.session()
        self.f.after_snapshot["state"]["relation_cooldown"]["threshold_raw"] += 1
        self.failed()

    def test_known_pipeline_purpose_allows_phase_checks_but_actual_send_is_never_ignored(self):
        self.f.write_inputs()
        for tool in (verifier.lifecycle, verifier.preview, verifier):
            result = tool.verify(self.f.log, self.f.pid, self.f.before, self.f.after, self.f.manifest)
            self.assertTrue(result["runtime_verified"], result)
            self.assertFalse(result["entire_dll_no_send_verified"])
        for event in ({"event": "pair_submit_case", "submitted": True},
                      {"event": "pair_submit_begin", "submitted": False},
                      {"event": "pair_command_unknown", "submitted": False}):
            self.f.events = self.session()
            self.f.events.insert(-1, event)
            self.f.write_inputs()
            for tool in (verifier.lifecycle, verifier.preview, verifier):
                result = tool.verify(self.f.log, self.f.pid, self.f.before, self.f.after, self.f.manifest)
                self.assertFalse(result["runtime_verified"], result)
        self.f.events = self.session()
        del self.row("pair_command_case")["submitted"]
        self.f.write_inputs()
        for tool in (verifier.lifecycle, verifier.preview, verifier):
            self.assertFalse(tool.verify(self.f.log, self.f.pid, self.f.before, self.f.after, self.f.manifest)["runtime_verified"])

    def test_manifest_source_purpose_and_build_pin_fail_closed(self):
        baseline = deepcopy(self.f.build)
        for change in (lambda b: b.update(purpose="lifecycle_and_preview_no_send"),
                       lambda b: b["source_sha256"].pop(verifier.COMMAND_SOURCE),
                       lambda b: b.update(game_sha256="0" * 64),
                       lambda b: b.update(dll_sha256="bad")):
            self.f.build = deepcopy(baseline)
            change(self.f.build)
            self.failed()

    def test_pipeline_requires_every_source_in_all_three_phase_verifiers(self):
        baseline = deepcopy(self.f.build)
        for source in verifier.lifecycle.PIPELINE_SOURCES:
            self.f.build = deepcopy(baseline)
            self.f.build["source_sha256"].pop(source)
            self.f.write_inputs()
            for tool in (verifier.lifecycle, verifier.preview, verifier):
                result = tool.verify(self.f.log, self.f.pid, self.f.before, self.f.after, self.f.manifest)
                self.assertFalse(result["runtime_verified"], (source, result))

    def test_bounded_malformed_inputs_and_other_pid_boundaries(self):
        self.f.events = self.session() + self.session(self.f.pid + 1)[:2]
        self.f.write_inputs()
        self.assertTrue(self.verify()["runtime_verified"])
        self.f.events = self.session()
        self.f.write_inputs()
        good = self.f.log.read_bytes()
        for bad in (b'{"event":"pair_command_case","event":"research_frame"}\n', b'{"x":NaN}\n', b'{"event":'):
            self.f.log.write_bytes(good + bad)
            self.assertFalse(self.verify()["runtime_verified"])
        self.f.log.write_bytes(good)
        with patch.object(verifier, "MAX_LOG_BYTES", 16):
            self.assertFalse(self.verify()["runtime_verified"])
        with patch.object(verifier, "MAX_LINE_BYTES", 16):
            self.assertFalse(self.verify()["runtime_verified"])

    def test_cli_never_replaces_input_or_another_phase_report(self):
        output = self.f.root / "command.json"
        args = ["--log", str(self.f.log), "--pid", str(self.f.pid), "--before", str(self.f.before), "--after", str(self.f.after),
                "--build-manifest", str(self.f.manifest), "--output", str(output)]
        self.f.log.write_bytes(b"")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(verifier.main(args), 2)
        self.assertFalse(json.loads(output.read_text())["runtime_verified"])
        for scope in ("lifecycle_only", "native_legality_preview"):
            output.write_text(json.dumps({"verification_scope": scope, "status": "passed", "runtime_verified": True}))
            original = output.read_bytes()
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(verifier.main(args), 2)
            self.assertEqual(output.read_bytes(), original)
        linked = self.f.root / "linked.json"
        os.link(self.f.before, linked)
        for target in (self.f.before, linked):
            args[-1] = str(target)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(verifier.main(args), 2)


if __name__ == "__main__":
    unittest.main()
