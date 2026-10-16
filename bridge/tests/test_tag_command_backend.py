"""Transport tests never open EU4, inject a DLL, or issue a diplomacy action."""
import json
from pathlib import Path
import tempfile
import unittest

from bridge.tag_command_backend import (ACTIONS, GAME_SHA, PURPOSE, ROOT, SCHEMA,
    TagCommandBackend, boot, digest, encode, validate_command, wire)


class FakeRuntime:
    def __init__(self):
        self.checks = []
    def now(self):
        return 100
    def check(self, identity, build, manifest, owner=None):
        self.checks.append((identity,owner))


class TagCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        dll = b"offline DLL fixture"
        (self.path/"fixture.dll").write_bytes(dll)
        source = ROOT/"bridge/tag_command_backend.py"
        raw = source.read_bytes()
        manifest = {"schema":"EU4TAGBUILD/1","purpose":PURPOSE,"DLL":"fixture.dll",
                    "game_sha256":GAME_SHA,"no_send":False,"dll":{"bytes":len(dll),"sha256":digest(dll)},
                    "source_pins":{source.relative_to(ROOT).as_posix():{"bytes":len(raw),"sha256":digest(raw)}},
                    "PE_timestamp":1,"SizeOfImage":4096}
        (self.path/"build.json").write_bytes(encode(manifest))
        self.runtime = FakeRuntime()
        self.backend = TagCommandBackend(self.path/"build.json",runtime=self.runtime,
                                         test_history_dir=self.path/"isolated-development-history")
        self.identity = {"pid":77,"creation":"0000000000000001","session":"1"*32,
                         "dll_sha256":digest(dll),"manifest_sha256":self.backend.manifest_sha}
        self.directory = self.backend.session(self.identity)
        self.directory.mkdir()
        self.rows = []
        self.event("bootstrap_verified",0,native_environment_initialized=True)
        self.event("hook_installed",0)
        self.command = {"request_id":"ai-por-bri-1","actor":"POR","target":"BRI","action":"trade_favors_for_gold"}

    def event(self,name,sequence,**extra):
        row = {"schema":SCHEMA,"event":name,**self.identity,"ordinal":len(self.rows)+1,
               "production_ready":False,"no_send":False,"owner_thread":12,"thread":12,
               "sequence":sequence,**extra}
        self.rows.append(row)
        (self.directory/"events.jsonl").write_text("".join(json.dumps(r)+"\n" for r in self.rows))

    def publish(self):
        return self.backend.publish(self.identity,[self.command])

    def claim(self):
        self.publish()
        (self.directory/"1.claim").write_bytes((self.directory/"1.request").read_bytes())
        self.event("request_claimed",1,action=self.command["action"],actor="POR",target="BRI",expires=60100)
        actor = (1<<56)|(189<<32)|int.from_bytes(b"POR","little")
        target = (1<<56)|(116<<32)|int.from_bytes(b"BRI","little")
        human = (1<<56)|(122<<32)|int.from_bytes(b"FRA","little")
        self.event("pair_bound",1,actor_handle=actor,target_handle=target,human_player_handle=human,actor_is_human_player=False)

    def test_wire_preserves_arbitrary_tags_and_native_protocol(self):
        data = wire(self.identity,1,60100,self.command)
        self.assertTrue(data.startswith(b"EU4TAGCOMMAND/1\n"))
        self.assertIn(b"actor=POR\ntarget=BRI\n",data)
        self.assertNotIn(b"actor=FRA",data)
        self.assertTrue(boot(self.identity).startswith(b"EU4TAGBOOT/1\n"))

    def test_publication_creates_real_request_and_intent(self):
        result = self.publish()
        self.assertFalse(result["reused"])
        self.assertEqual((self.directory/"1.request").read_bytes(),wire(self.identity,1,60100,self.command))
        self.assertEqual(self.backend.status(self.identity,self.command["request_id"])["state"],"published")
        self.assertEqual(len(self.runtime.checks),2)

    def test_idempotent_repeat_does_not_publish_again(self):
        self.publish()
        before = (self.directory/"1.request").read_bytes()
        result = self.publish()
        self.assertTrue(result["reused"])
        self.assertEqual(len(list(self.directory.glob("*.request"))),1)
        self.assertEqual((self.directory/"1.request").read_bytes(),before)
        self.assertEqual(len(self.runtime.checks),2)

    def test_conflicting_request_id_is_rejected(self):
        self.publish()
        changed = dict(self.command,target="ENG")
        with self.assertRaisesRegex(ValueError,"Idempotency conflict"):
            self.backend.publish(self.identity,[changed])

    def test_nonplayer_dispatch_receipt_keeps_effect_unverified(self):
        self.claim()
        self.event("dispatch_intent",1)
        self.event("native_call_return",1,call=7,normal=True,boolean=True,slot_consumed=True,exception=0)
        self.event("request_result",1,submitted=True,status=4,reason="normal_dispatch_slot_consumed",
                   ownership_closed=True,owned_live=0,quarantined=0,adapter_fault=0)
        result = self.backend.status(self.identity,self.command["request_id"])
        self.assertEqual(result["state"],"dispatched")
        self.assertFalse(result["binding"]["actor_is_human_player"])
        self.assertFalse(result["gameplay_effects_verified"])

    def test_false_submission_claim_without_consumed_slot_rejected(self):
        self.claim()
        self.event("dispatch_intent",1)
        self.event("native_call_return",1,call=7,normal=True,boolean=True,slot_consumed=False,exception=0)
        self.event("request_result",1,submitted=True,status=4,reason="normal_dispatch_slot_consumed",
                   ownership_closed=True,owned_live=0,quarantined=0,adapter_fault=0)
        with self.assertRaisesRegex(ValueError,"Unproven native dispatch"):
            self.backend.status(self.identity,self.command["request_id"])

    def test_normal_native_rejection_is_not_success(self):
        self.claim()
        self.event("request_result",1,submitted=False,status=2,reason="full88_normal_false")
        self.assertEqual(self.backend.status(self.identity,self.command["request_id"])["state"],"native_rejected")

    def test_test_publisher_rejects_historically_successful_action(self):
        command = dict(self.command,action="improve_relations")
        with self.assertRaisesRegex(ValueError,"Previously successful"):
            self.backend.publish(self.identity,[command],test_only=True)
        self.assertFalse(list(self.directory.glob("*.request")))

    def test_clean_rejections_allow_new_test_ids_without_replaying_original_requests(self):
        for action in ("trade_favors_for_gold", "trade_favors_for_war_prep"):
            with self.subTest(action=action):
                command = dict(self.command, action=action, request_id="new-id-"+action)
                # Eligibility does not automatically resume an unfinished
                # prior publication in the same fixture session.
                if action == "trade_favors_for_gold":
                    result = self.backend.publish(self.identity, [command], test_only=True)
                    self.assertEqual(len(result["published"]), 1)
                else:
                    with self.assertRaisesRegex(ValueError, "Prior commands not finished"):
                        self.backend.publish(self.identity, [command], test_only=True)

    def test_original_rejected_request_id_cannot_be_republished(self):
        command = dict(self.command, request_id="tag31-final-022-trade_favors_for_gold")
        with self.assertRaisesRegex(ValueError, "Original final-integration request"):
            self.backend.publish(self.identity, [command], test_only=True)
        self.assertEqual(self.runtime.checks, [])
        self.assertFalse(list(self.directory.glob("*.request")))

    def test_batch_can_address_distinct_actor_tags(self):
        second = {"request_id":"ai-eng-por-1","actor":"ENG","target":"POR","action":"trade_favors_for_men"}
        self.backend.publish(self.identity,[self.command,second])
        self.assertIn(b"actor=ENG\ntarget=POR",(self.directory/"2.request").read_bytes())

    def test_pointer_or_unknown_action_rejected(self):
        for changed in (dict(self.command,actor="0x1234"),dict(self.command,actor="por"),
                        dict(self.command,target="POR"),dict(self.command,action="unknown"),
                        dict(self.command,parameters={"pointer":123})):
            with self.assertRaises(ValueError):
                validate_command(changed)

    def test_caps_do_not_claim_274_executable_actions(self):
        self.assertEqual(len(self.backend.capabilities()["actions"]),len(ACTIONS))
        self.assertFalse(self.backend.capabilities()["production_ready"])


if __name__ == "__main__":
    unittest.main()
