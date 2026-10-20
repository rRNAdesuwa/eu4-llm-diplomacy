"""Development history tests use only temporary files and FakeRuntime."""
import copy
import json
from pathlib import Path
import threading
import types
import unittest
from unittest.mock import patch

from bridge.tag_command_backend import (PublicationUnknownError, SCHEMA, TagCommandBackend,
                                       decode, digest, encode, write_new)
from bridge.tag_test_policy import DevelopmentTestHistory, clean_rejection
from bridge.tests import test_tag_command_backend as fixtures


class DevelopmentTestPolicyTests(unittest.TestCase):
    event = fixtures.TagCommandTests.event

    def setUp(self):
        fixtures.TagCommandTests.setUp(self)
        self.history_dir = self.path/"isolated-development-history"
        self.history = DevelopmentTestHistory(self.history_dir)
        self.first = self.new_session("2")

    def new_session(self, marker, *, different_manifest=False):
        manifest = self.path/"build.json"
        if different_manifest:
            directory = self.path/("build-"+marker)
            directory.mkdir()
            data = decode(manifest.read_bytes())
            data["PE_timestamp"] += int(marker,16)
            (directory/data["DLL"]).write_bytes((self.path/data["DLL"]).read_bytes())
            manifest = directory/"build.json"
            manifest.write_bytes(encode(data))
        runtime = fixtures.FakeRuntime()
        backend = TagCommandBackend(manifest,runtime=runtime,test_history_dir=self.history_dir)
        identity = dict(self.identity,session=marker*32,manifest_sha256=backend.manifest_sha)
        directory = backend.session(identity)
        directory.mkdir()
        session = types.SimpleNamespace(backend=backend,identity=identity,directory=directory,
                                        runtime=runtime,rows=[])
        self.add_event(session,"bootstrap_verified",0)
        self.add_event(session,"hook_installed",0)
        return session

    def add_event(self, session, event, sequence, **fields):
        row = {"schema":SCHEMA,"event":event,**session.identity,"ordinal":len(session.rows)+1,
               "production_ready":False,"no_send":False,"owner_thread":12,"thread":12,
               "sequence":sequence,**fields}
        session.rows.append(row)
        self.rewrite_events(session)

    def rewrite_events(self, session):
        (session.directory/"events.jsonl").write_text("".join(json.dumps(row)+"\n" for row in session.rows))

    def make_command(self, request_id="development-first"):
        return dict(self.command_fixture,request_id=request_id)

    @property
    def command_fixture(self):
        return {"request_id":"fixture", "actor":"POR", "target":"BRI", "action":"trade_favors_for_gold"}

    def publish(self, session, request_id="development-first"):
        command = self.make_command(request_id)
        session.backend.publish(session.identity,[command],test_only=True)
        return command

    def claim(self, session, command):
        (session.directory/"1.claim").write_bytes((session.directory/"1.request").read_bytes())
        self.add_event(session,"request_claimed",1,action=command["action"],actor=command["actor"],
                       target=command["target"],expires=60100)
        actor = (1<<56)|(189<<32)|int.from_bytes(command["actor"].encode("ascii"),"little")
        target = (1<<56)|(116<<32)|int.from_bytes(command["target"].encode("ascii"),"little")
        human = (1<<56)|(122<<32)|int.from_bytes(b"FRA","little")
        self.add_event(session,"pair_bound",1,actor_handle=actor,target_handle=target,
                       human_player_handle=human,actor_is_human_player=False)

    def reject(self, session, command, *, gate=False):
        self.claim(session,command)
        calls = [0,1,2,3,4,5,6] if gate else [0,1,2,5]
        for call in calls:
            self.add_event(session,"native_call_begin",1,call=call)
            self.add_event(session,"native_call_return",1,call=call,normal=True,exception=0,
                           boolean=call not in ([4] if gate else [2]))
        self.add_event(session,"request_result",1,status=3 if gate else 2,
                       reason="command_gate_normal_false" if gate else "full88_normal_false",
                       known_cleanup_complete=True,ownership_closed=True,owned_live=0,quarantined=0,
                       adapter_fault=0,submitted=False,submit_attempted=False,submit_returned=False,
                       submit_value=False,slot_consumed=False,transfer_outcome=0,submit_exception=0,
                       adapter_call_attempts=len(calls))

    def assert_blocked_in_new_session(self, marker="3"):
        second = self.new_session(marker,different_manifest=True)
        command = dict(self.make_command("development-blocked-next-"+marker),actor="ENG",target="POR")
        with self.assertRaisesRegex(ValueError,"Development action reserved, dispatched or uncertain"):
            second.backend.publish(second.identity,[command],test_only=True)
        self.assertEqual(second.runtime.checks,[])
        self.assertFalse(list(second.directory.glob("key-*.json")))
        self.assertFalse((second.directory/"publisher.lock").exists())

    def test_published_attempt_blocks_changed_session_manifest_tags_and_id(self):
        self.publish(self.first)
        self.assertEqual(len(list(self.history_dir.glob("attempt-*.json"))),1)
        self.assertFalse((self.history_dir/"test-policy.lock").exists())
        self.assert_blocked_in_new_session()

    def test_claimed_attempt_without_outcome_remains_blocked(self):
        command = self.publish(self.first)
        self.claim(self.first,command)
        self.assert_blocked_in_new_session()

    def test_dispatch_or_native_unknown_never_becomes_retestable(self):
        command = self.publish(self.first)
        self.claim(self.first,command)
        self.add_event(self.first,"dispatch_intent",1)
        self.add_event(self.first,"native_call_return",1,call=7,normal=True,boolean=True,
                       slot_consumed=True,exception=0)
        self.add_event(self.first,"request_result",1,submitted=True,status=4,
                       reason="normal_dispatch_slot_consumed",ownership_closed=True,
                       owned_live=0,quarantined=0,adapter_fault=0)
        self.assert_blocked_in_new_session()
        self.first.rows[-1].update(submitted=False,status=5,reason="dispatch_outcome_unknown_no_retry")
        self.rewrite_events(self.first)
        self.assert_blocked_in_new_session("4")

    def test_clean_rejection_allows_new_id_and_old_source_pins_need_not_be_runnable(self):
        command = self.publish(self.first)
        self.reject(self.first,command)
        second = self.new_session("3",different_manifest=True)
        # A file audit must not reconstruct the old runnable backend.
        with patch.object(TagCommandBackend,"verify",side_effect=AssertionError("No old execution check")):
            self.history.check([self.make_command("development-next")])
        result = second.backend.publish(second.identity,[self.make_command("development-next")],test_only=True)
        self.assertEqual(len(result["published"]),1)
        self.assertEqual(len(list(self.history_dir.glob("attempt-*.json"))),2)
        self.assert_blocked_in_new_session("4")

    def test_normal_gate_rejection_with_all_destructors_allows_another_attempt(self):
        command = self.publish(self.first)
        self.reject(self.first,command,gate=True)
        self.history.check([self.make_command("development-next")])

    def test_development_request_id_cannot_be_reused_even_after_clean_rejection(self):
        command = self.publish(self.first)
        self.reject(self.first,command)
        second = self.new_session("3")
        with self.assertRaisesRegex(ValueError,"Development request_id already reserved"):
            second.backend.publish(second.identity,[command],test_only=True)
        self.assertEqual(second.runtime.checks,[])

    def test_missing_cleanup_fields_or_unproven_calls_do_not_unlock(self):
        command = self.publish(self.first)
        self.reject(self.first,command)
        original = copy.deepcopy(self.first.rows)
        for field in ("ownership_closed","known_cleanup_complete","owned_live","quarantined",
                      "submit_attempted","transfer_outcome"):
            with self.subTest(field=field):
                self.first.rows = copy.deepcopy(original)
                self.first.rows[-1].pop(field)
                self.rewrite_events(self.first)
                with self.assertRaisesRegex(ValueError,"Development action reserved"):
                    self.history.check([self.make_command("development-next")])
        self.first.rows = copy.deepcopy(original)
        self.first.rows[-2]["normal"] = False
        self.rewrite_events(self.first)
        with self.assertRaisesRegex(ValueError,"Development action reserved"):
            self.history.check([self.make_command("development-next")])

    def test_partial_tail_changed_prefix_or_retained_publisher_lock_blocks_clean_receipt(self):
        command = self.publish(self.first)
        self.reject(self.first,command)
        audit = self.first.directory/"events.jsonl"
        complete = audit.read_bytes()
        audit.write_bytes(complete+b'{"event":"native_call_begin"')
        with self.assertRaisesRegex(ValueError,"Development action reserved"):
            self.history.check([self.make_command("development-next")])
        audit.write_bytes(complete)
        self.first.rows[0]["extra_field"] = "Changed old audit prefix"
        self.rewrite_events(self.first)
        with self.assertRaisesRegex(ValueError,"Development action reserved"):
            self.history.check([self.make_command("development-next")])
        audit.write_bytes(complete)
        (self.first.directory/"publisher.lock").write_bytes(b"Retain for audit")
        with self.assertRaisesRegex(ValueError,"Development action reserved"):
            self.history.check([self.make_command("development-next")])
        self.assertTrue((self.first.directory/"publisher.lock").exists())

    def test_publication_unknown_preserves_both_reservation_and_publisher_evidence(self):
        original_check = self.first.runtime.check
        def fail_second_check(*args):
            original_check(*args)
            if len(self.first.runtime.checks) == 2:
                raise ValueError("Manual pause changed")
        self.first.runtime.check = fail_second_check
        with self.assertRaises(PublicationUnknownError) as caught:
            self.publish(self.first)
        self.assertEqual(caught.exception.result["state"],"publication_unknown")
        self.assertEqual(caught.exception.result["results"][0]["publication_stage"],"pending_retained")
        self.assertFalse(caught.exception.result["automatic_retry"])
        self.assertTrue((self.first.directory/"publisher.lock").exists())
        self.assertEqual(len(list(self.history_dir.glob("attempt-*.json"))),1)
        self.assert_blocked_in_new_session()

    def test_interrupted_development_reservation_retains_mutex_and_reports_unknown(self):
        def fail_after_record(path, data):
            write_new(path,data)
            if Path(path).name.startswith("attempt-"):
                raise OSError("Reservation fsync outcome unavailable")
        with patch("bridge.tag_test_policy.write_new",side_effect=fail_after_record):
            with self.assertRaises(PublicationUnknownError) as caught:
                self.publish(self.first)
        self.assertEqual(caught.exception.result["results"][0]["publication_stage"],
                         "development_reservation_started")
        self.assertTrue((self.history_dir/"test-policy.lock").exists())
        self.assertTrue((self.first.directory/"publisher.lock").exists())
        self.assertEqual(len(list(self.history_dir.glob("attempt-*.json"))),1)
        self.assertFalse(list(self.first.directory.glob("*.request")))

    def test_central_mutex_prevents_concurrent_same_action_reservations(self):
        second = self.new_session("3",different_manifest=True)
        barrier = threading.Barrier(2)
        outcomes = []
        def attempt(session, request_id):
            barrier.wait(timeout=2)
            try:
                self.publish(session,request_id)
                outcomes.append("published")
            except (ValueError,OSError):
                outcomes.append("blocked")
        threads = [threading.Thread(target=attempt,args=(self.first,"concurrent-first")),
                   threading.Thread(target=attempt,args=(second,"concurrent-second"))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(3)
            self.assertFalse(thread.is_alive())
        self.assertCountEqual(outcomes,["published","blocked"])
        self.assertEqual(len(list(self.history_dir.glob("attempt-*.json"))),1)
        self.assertEqual(sum(len(list(session.directory.glob("*.request")))
                             for session in (self.first,second)),1)

    def test_ordinary_commands_do_not_consult_or_clear_development_history(self):
        self.history_dir.mkdir()
        lock = self.history_dir/"test-policy.lock"
        lock.write_bytes(b"Unresolved development reservation")
        result = self.first.backend.publish(self.first.identity,[self.make_command()])
        self.assertEqual(len(result["published"]),1)
        self.assertEqual(lock.read_bytes(),b"Unresolved development reservation")
        self.assertFalse(list(self.history_dir.glob("attempt-*.json")))

    def test_sparse_lease_rejection_and_boolean_zero_are_not_clean_proofs(self):
        self.assertFalse(clean_rejection({"status":1,"reason":"lease_precondition_rejected",
                                          "adapter_call_attempts":0,"submitted":False}))
        command = self.publish(self.first)
        self.reject(self.first,command)
        result = dict(self.first.rows[-1])
        self.assertTrue(clean_rejection(result))
        result["owned_live"] = False
        self.assertFalse(clean_rejection(result))


if __name__ == "__main__":
    unittest.main()
