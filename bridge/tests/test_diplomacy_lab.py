"""Pure v6 protocol/file tests. Never opens a process or the real mailbox."""
import contextlib
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bridge.tests import test_diplomacy_command as command_fixtures
from work.native import lab_protocol_1375 as lab
from work.native import inject_lab_1375 as loader
from tools import request_diplomacy_lab as cli


class LabTests(unittest.TestCase):
    def setUp(self):
        self.fixture = command_fixtures.CommandVerificationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.session = self.fixture.f.root
        self.pid, self.thread = self.fixture.f.pid, self.fixture.f.thread
        self.creation = "01da123456789abc"
        self.metadata = dict(schema_version=1, purpose=lab.PURPOSE, pid=self.pid,
                             process_creation_filetime=self.creation, window_thread=self.thread,
                             game_sha256=lab.LOCAL_SHA256, world_generation_verified=False, runtime_verified=False)
        self.events = deepcopy(self.fixture.f.events)
        complete = set()
        for event in self.events:
            name = event["event"]
            if name.startswith("research_"):
                event["process_creation_filetime"] = self.creation
            for phase, ending in (("lifecycle", "pair_selftest_complete"), ("preview", "pair_preview_complete"), ("command", "pair_command_complete")):
                if name == ending:
                    complete.add(phase)
            if name == "research_frame":
                event.update(uptime_ms=1000+event["frames"], world_changed=False, session_frozen=False,
                             world_cookie="0x20000000", player_handle="0x0100007a00415246", raw_date=56456976,
                             paused=True, native_speed_index=0, last_sequence=0,
                             mailbox_ready=len(complete) == 3, lease_active=False, running_speed_enabled=True)
                event.update({phase + "_passed": phase in complete for phase in lab.PHASES})
        for phase, (_, claim, raw) in lab.PHASES.items():
            (self.session / claim).write_bytes(raw)
        for name in ("session.json", "install.claim"):
            (self.session / name).write_text(json.dumps(self.metadata), encoding="utf-8")
        self.write()
        self.live = dict(pid=self.pid, creation=self.creation, world_cookie="0x20000000",
                         player_handle="0x0100007a00415246", raw_date=56456976)
        self.record = dict(pid=self.pid, creation=self.creation, sequence=1, expires=6400,
                           operation="pair", mode="legality_only", action="improve_relations", actor="FRA", target="ENG", speed=0)
        self.private = patch.object(lab, "_private_root")
        self.private.start()
        self.addCleanup(self.private.stop)

    def write(self):
        (self.session / "research-1375.jsonl").write_text("".join(json.dumps(row) + "\n" for row in self.events), encoding="utf-8")

    def read(self):
        return lab.read_evidence(self.session, self.metadata)

    def bound(self, event, **fields):
        return dict(event=event, pid=self.pid, process_creation_filetime=self.creation, sequence=1, **fields)

    def claim(self, record=None):
        record = record or self.record
        (self.session / "00000000000000000001.claim").write_bytes(lab.encode_request(record))
        self.events.append(self.bound("lab_request_claimed", **{k:v for k,v in record.items() if k not in ("pid", "creation", "sequence")}, durable_claim=True, retry_allowed=False))

    def pair_events(self):
        self.claim()
        core = dict(action_id="improve_relations", actor="FRA", target="ENG", pid=self.pid, thread_id=self.thread,
                    process_creation_filetime=self.creation, world="0x20000000", raw_date=56456976,
                    status=1, reason=0, submit_entered=False, submit_returned=False, ownership_uncertain=False,
                    applied_verified=False, freeze_session=False, retry_allowed=False)
        for event in ("pair_engine_begin", "pair_engine_complete"):
            self.events.append(self.bound("lab_native_record", lease_pause=False, record=dict(event=event, **core)))
        self.events.append(self.bound("lab_request_complete", operation="pair", action="improve_relations", status=1, reason=0,
                                      submit_entered=False, submit_returned=False, ownership_uncertain=False, session_frozen=False,
                                      applied_verified=False, retry_allowed=False))

    def test_canonical_roundtrip_and_all_ten_actions(self):
        self.assertEqual(len(lab.ACTIONS), 10)
        for action in lab.ACTIONS:
            record = dict(self.record, action=action)
            raw = lab.encode_request(record)
            self.assertEqual(lab.decode_request(raw), record)
            self.assertTrue(raw.startswith(b"EU4LAB/1\npid="))
        speed = dict(self.record, operation="speed", mode="submit", action="none", target="FRA", speed=5)
        self.assertEqual(lab.decode_request(lab.encode_request(speed)), speed)

    def test_noncanonical_and_injection_inputs_rejected(self):
        raw = lab.encode_request(self.record)
        for invalid in (raw.replace(b"\n", b"\r\n"), raw+b"x\n", b"\xef\xbb\xbf"+raw, raw[:-1],
                        raw.replace(b"sequence=1", b"sequence=01"), raw.replace(b"target=ENG", b"target=ENG\naction=guarantee"),
                        raw.replace(b"actor=FRA", b"actor=../"), raw.replace(b"expires=6400", b"expires=18446744073709551616"),
                        raw.replace(b"EU4LAB/1", b"EU4PAIR/1"), raw.replace(b"creation=01da", b"creation=01DA")):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                lab.decode_request(invalid)
        for fields in (dict(sequence=True), dict(target="FRA"), dict(speed=1), dict(action="raw_pointer"), dict(pointer="0x123")):
            with self.assertRaises(ValueError):
                lab.encode_request(dict(self.record, **fields))

    def test_real_shaped_three_phase_prefix_and_claims(self):
        evidence = self.read()
        self.assertTrue(all(evidence["phases"].values()))
        self.assertEqual(evidence["phase_proofs"]["command"]["case_count"], 20)
        lab.check_ready(evidence, self.live, 1400, operation="pair")
        (self.session / "phase-preview.claim").write_bytes(b"PAIR_COMMAND_1375\n")
        with self.assertRaises(ValueError):
            self.read()

    def test_failed_or_partial_preflight_cannot_unlock_mailbox(self):
        for mutation in (lambda: self.events[3].update(clone_fields_ok=False),
                         lambda: self.events[-1].update(world_changed=True),
                         lambda: next(row for row in self.events if row["event"] == "pair_preview_begin").pop("send_enabled"),
                         lambda: self.events[-1].update(process_creation_filetime="01da000000000000")):
            original = deepcopy(self.events)
            mutation(); self.write()
            with self.assertRaises(ValueError):
                self.read()
            self.events = original
        self.events.pop(); self.write()
        evidence = self.read()
        self.assertFalse(evidence["phases"]["command"])
        with self.assertRaises(ValueError):
            lab.check_ready(evidence, self.live, 1400, operation="pair")

    def test_metadata_requires_matching_install_claim(self):
        self.assertEqual(lab.read_session_metadata(self.session, self.pid, self.creation), self.metadata)
        (self.session / "install.claim").write_text(json.dumps(dict(self.metadata, pid=99)), encoding="utf-8")
        with self.assertRaises(ValueError):
            lab.read_session_metadata(self.session, self.pid, self.creation)

    def test_stale_world_pending_and_unpaused_fail_closed(self):
        evidence = self.read()
        for changed in (dict(pending=True), dict(lease_pending=True), dict(latest_frame=dict(evidence["latest_frame"], paused=False)),
                        dict(latest_frame=dict(evidence["latest_frame"], command_passed=False))):
            with self.assertRaises(ValueError):
                lab.check_ready(dict(evidence, **changed), self.live, 1400, operation="pair")
        with self.assertRaises(ValueError):
            lab.check_ready(evidence, self.live, 4001, operation="pair")
        with self.assertRaises(ValueError):
            lab.check_ready(evidence, dict(self.live, world_cookie="0x21000000"), 1400, operation="pair")

    def test_pair_completion_is_bound_and_never_applied(self):
        self.pair_events(); self.write()
        evidence = self.read()
        self.assertFalse(evidence["pending"])
        self.assertFalse(evidence["requests"][1]["complete"]["applied_verified"])
        self.assertEqual(evidence["last_sequence"], 1)
        self.events[-1]["submit_entered"] = True; self.write()
        with self.assertRaises(ValueError):
            self.read()

    def test_foreign_core_identity_or_missing_host_creation_rejected(self):
        self.pair_events()
        original = deepcopy(self.events)
        for change in (lambda: self.events[-2]["record"].update(thread_id=999),
                       lambda: self.events[-2]["record"].update(action_id="guarantee"),
                       lambda: self.events[-1].pop("process_creation_filetime")):
            self.events = deepcopy(original); change(); self.write()
            with self.assertRaises(ValueError):
                self.read()

    def test_unknown_preserves_pending_and_prevents_republication(self):
        self.claim(); self.write()
        evidence = self.read()
        self.assertTrue(evidence["pending"])
        with self.assertRaises(ValueError):
            lab.check_ready(evidence, self.live, 1400, operation="pair")
        self.events.append(self.bound("lab_session_frozen", reason="ownership_uncertain", retry_allowed=False)); self.write()
        with self.assertRaises(ValueError):
            self.read()

    def publish(self, **kwargs):
        fields = dict(sequence=1, operation="pair", action="improve_relations", actor="FRA", target="ENG", clock=lambda:1400)
        fields.update(kwargs)
        return lab.publish_research(self.session, self.metadata, "a"*64, self.read(), self.live, **fields)

    def test_exclusive_publication_durable_intent_and_no_retry(self):
        result = self.publish()
        self.assertEqual(result["status"], "published")
        final = self.session / "00000000000000000001.request"
        raw = final.read_bytes()
        self.assertEqual(lab.decode_request(raw)["action"], "improve_relations")
        intent = json.loads((self.session / "00000000000000000001.host-intent").read_text())
        self.assertEqual(intent["request_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertFalse(intent["automatic_retry"])
        final.unlink()  # Simulate native consumer after publication.
        with self.assertRaises(OSError):
            self.publish()
        self.assertFalse(final.exists())

    def test_world_change_after_intent_retains_claim_but_never_publishes(self):
        def changed():
            evidence = self.read()
            evidence["latest_frame"]["world_cookie"] = "0x21000000"
            return evidence, dict(self.live, world_cookie="0x21000000")
        with self.assertRaises(ValueError):
            self.publish(recheck=changed)
        self.assertTrue((self.session / "00000000000000000001.host-intent").exists())
        self.assertFalse((self.session / "00000000000000000001.request").exists())

    def test_positive_speed_requires_watchdog_before_any_file(self):
        with self.assertRaises(ValueError):
            self.publish(operation="speed", action="none", target="FRA", mode="submit", speed=1)
        self.assertFalse(list(self.session.glob("*.host-intent")))
        self.publish(operation="speed", action="none", target="FRA", mode="submit", speed=1, watchdog_verified=True)

    def test_phase_marker_is_explicit_exact_and_not_reusable(self):
        self.events = self.events[:2]
        self.write()
        (self.session / "phase-lifecycle.claim").unlink()
        evidence = self.read()
        result = lab.publish_research(self.session, self.metadata, "a"*64, evidence, self.live,
                                      phase="lifecycle", clock=lambda:1100)
        self.assertEqual(result["phase"], "lifecycle")
        self.assertEqual((self.session / "pair-selftest.request").read_bytes(), b"PAIR_SELFTEST_1375\n")
        (self.session / "pair-selftest.request").unlink()
        with self.assertRaises(OSError):
            lab.publish_research(self.session, self.metadata, "a"*64, evidence, self.live,
                                 phase="lifecycle", clock=lambda:1100)

    def test_expired_publication_keeps_intent_and_cannot_retry(self):
        times = iter((1400, 1400, 8000))
        with self.assertRaises(ValueError):
            self.publish(clock=lambda:next(times))
        self.assertTrue((self.session / "00000000000000000001.host-intent").exists())
        self.assertFalse((self.session / "00000000000000000001.request").exists())

    def test_watchdog_requires_direct_parent_creation_and_liveness(self):
        kernel = unittest.mock.MagicMock()
        kernel.OpenProcess.return_value = 123
        kernel.WaitForSingleObject.return_value = 0x102
        creation = int(self.creation, 16)
        def times(handle, created, *unused):
            created._obj.dwLowDateTime = creation & 0xffffffff
            created._obj.dwHighDateTime = creation >> 32
            return True
        kernel.GetProcessTimes.side_effect = times
        with patch.object(lab.C, "WinDLL", return_value=kernel), patch.object(lab.os, "getppid", return_value=777):
            with self.assertRaises(ValueError), lab.watchdog_parent(778, self.creation):
                pass
            kernel.OpenProcess.assert_not_called()
            with lab.watchdog_parent(777, self.creation) as check:
                kernel.WaitForSingleObject.return_value = 0
                with self.assertRaises(ValueError):
                    check()
            kernel.CloseHandle.assert_called_once_with(123)
            kernel.WaitForSingleObject.return_value = 0x102
            with self.assertRaises(ValueError), lab.watchdog_parent(777, "01da000000000000"):
                pass
            self.assertEqual(kernel.CloseHandle.call_count, 2)

    def test_plan_validation_rejects_sequence_ttl_nonplayer_and_equal_pair(self):
        kwargs = dict(sequence=1, operation="pair", mode="submit", action="improve_relations", actor="FRA", target="ENG", speed=0, ttl_ms=5000, now=1400)
        for changed in (dict(sequence=2), dict(ttl_ms=60001), dict(actor="POR"), dict(target="FRA")):
            with self.assertRaises(ValueError):
                lab.prepare_request(self.metadata, self.read(), **dict(kwargs, **changed))
        self.assertFalse(list(self.session.glob("*.host-intent")))

    def test_valid_automatic_pause_chain_requires_native_readback_and_claim(self):
        record = dict(self.record, operation="speed", action="none", mode="submit", target="FRA", speed=1)
        self.claim(record)
        self.events.append(self.bound("lab_lease_armed", deadline_uptime_ms=6400, maximum_raw_date_delta=48,
                                      initial_raw_date=56456976, automatic_pause=True, reliable_generation_verified=False))
        for pause in (False, True):
            core = dict(thread_id=self.thread, requested_speed=0 if pause else 1, reason=0, write_entered=True,
                        callback_returned=True, readback_matches=True, after_paused=pause, freeze_session=False,
                        retry_allowed=False, diplomacy_submitted=False, exception_code=0)
            for event in ("test_speed_begin", "test_speed_complete"):
                self.events.append(self.bound("lab_native_record", lease_pause=pause, record=dict(event=event, **core)))
            if not pause:
                self.events.append(self.bound("lab_request_complete", operation="speed", speed=1, reason=0, write_entered=True,
                                              callback_returned=True, readback_matches=True, session_frozen=False, applied_verified=False, retry_allowed=False))
            else:
                self.events.append(self.bound("lab_lease_complete", reason=0, write_entered=True, callback_returned=True,
                                              paused_readback=True, readback_matches=True, session_frozen=False, retry_allowed=False))
        claim = dict(purpose="bounded_running_lease_pause", pid=self.pid, process_creation_filetime=self.creation,
                     origin_sequence=1, speed=0, deadline_uptime_ms=6400, maximum_raw_date_delta=48, retry_allowed=False)
        (self.session / "00000000000000000001.lease-pause.claim").write_text(json.dumps(claim), encoding="utf-8")
        self.write()
        evidence = self.read()
        self.assertFalse(evidence["pending"] or evidence["lease_pending"])
        self.assertTrue(evidence["requests"][1]["lease_complete"]["paused_readback"])
        self.events[-2]["record"]["after_paused"] = False; self.write()
        with self.assertRaises(ValueError):
            self.read()

    def test_partial_log_and_oversized_line_rejected(self):
        path = self.session / "research-1375.jsonl"
        for ending in (b'{"event":', b'x'*(lab.MAX_LINE+1)+b'\n'):
            self.write()
            with path.open("ab") as stream:
                stream.write(ending)
            with self.assertRaises(ValueError):
                self.read()

    def test_build_manifest_exact_source_dll_and_speed_gate(self):
        root, output = self.session / "build-root", self.session / "build-root/out"
        output.mkdir(parents=True)
        for name in lab.SOURCES:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic fixture", encoding="utf-8")
        source = root / "work/native/research-lab-1375.cpp"
        source.write_text("static constexpr bool running_speed_enabled = true;", encoding="utf-8")
        (output / lab.DLL_NAME).write_bytes(b"synthetic DLL fixture, never loaded")
        built = lab.record_build(root, output)
        self.assertTrue(built["running_speed_enabled"])
        self.assertTrue(built["requires_exact_process_external_watchdog"])
        self.assertEqual(lab.verify_build(root, output)[0], built)
        source.write_text("static constexpr bool running_speed_enabled = false;", encoding="utf-8")
        with self.assertRaises(ValueError):
            lab.verify_build(root, output)

    def test_loader_plan_never_calls_injector(self):
        fake = unittest.mock.MagicMock()
        fake.__enter__.return_value = fake
        fake.creation, fake.snapshot.return_value = self.creation, self.live
        with patch.object(lab, "verify_build", return_value=({"dll_sha256":"D"*64}, "a"*64)), \
             patch.object(lab, "verify_test_save", return_value={"loaded_save_identity_verified":False}), \
             patch.object(lab, "LiveLabProcess", return_value=fake), patch.object(lab, "OUTPUT", self.session), \
             patch.object(loader.inject_probe, "_run") as inject, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(loader.main(["--pid",str(self.pid),"--creation",self.creation,"--ack-test-save","--plan-only"]),0)
            inject.assert_not_called()
        self.assertFalse(list(self.session.glob("*.request")))

    def test_cli_plan_validates_without_publication(self):
        fake = unittest.mock.MagicMock()
        fake.__enter__.return_value, fake.creation, fake.snapshot.return_value = fake, self.creation, self.live
        with patch.object(lab, "verify_build", return_value=({"dll_sha256":"D"*64,"running_speed_enabled":True},"a"*64)), \
             patch.object(lab,"LiveLabProcess",return_value=fake), patch.object(lab,"session_path",return_value=self.session), \
             patch.object(lab,"uptime_ms",return_value=1400), patch.object(lab,"publish_research") as publish, \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            argv=["--pid",str(self.pid),"--creation",self.creation,"pair","improve_relations","--target","ENG","--sequence","1"]
            self.assertEqual(cli.main(argv),0)
            self.assertEqual(cli.main(argv+["--actor","POR","--mode","submit"]),2)
            publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
