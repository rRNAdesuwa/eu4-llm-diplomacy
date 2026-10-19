"""V31 transport checks: no process access and no game function calls."""
import unittest

from bridge.tag_command_backend import (ACTIONS, DEFAULT_MANIFEST, ROOT,
    TagCommandBackend, decode, encode, read, validate_command, wire)
from bridge.tests import test_tag_command_backend as fixtures


class TagCommandV31Tests(unittest.TestCase):
    event = fixtures.TagCommandTests.event

    def setUp(self):
        fixtures.TagCommandTests.setUp(self)
        manifest_path = self.path / "build.json"
        manifest = decode(read(manifest_path, 1024 * 1024))
        self.config = decode(read(ROOT / "bridge/tag_actions_1375_v31.json", 1024 * 1024))
        manifest.update(purpose=self.config["purpose"], actions=self.config["actions"])
        config_name = "bridge/tag_actions_1375_v31.json"
        from bridge.tag_command_backend import digest
        raw = read(ROOT / config_name, 1024 * 1024)
        manifest["source_pins"][config_name] = {"bytes": len(raw), "sha256": digest(raw)}
        manifest_path.write_bytes(encode(manifest))
        self.backend = TagCommandBackend(manifest_path, runtime=self.runtime,
                                         test_history_dir=self.path/"isolated-development-history")
        self.identity["manifest_sha256"] = self.backend.manifest_sha
        self.directory = self.backend.session(self.identity)
        self.directory.mkdir()
        self.rows = []
        self.event("bootstrap_verified", 0, native_environment_initialized=True)
        self.event("hook_installed", 0)

    def test_all_120_actions_publish_in_one_batch(self):
        commands = [dict(request_id="v31-" + action, actor="ENG", target="POR", action=action)
                    for action in self.config["actions"]]
        result = self.backend.publish(self.identity, commands)
        self.assertEqual(len(result["published"]), 120)
        for sequence, command in enumerate(commands, 1):
            packet = (self.directory / f"{sequence}.request").read_bytes()
            self.assertEqual(packet, wire(self.identity, sequence, 1230100, command,
                             purpose=self.backend.purpose, actions=self.backend.actions, limit=128))
        self.assertEqual(len(list(self.directory.glob("key-*.json"))), 120)
        self.assertFalse(result["gameplay_effects_verified"])

    def test_batch_deadline_is_bounded_and_explicit_ttl_is_respected(self):
        with self.assertRaisesRegex(ValueError, "TTL bound"):
            self.backend.publish(self.identity, [self.command], ttl_ms=1800001)
        self.assertFalse(list(self.directory.glob("key-*.json")))
        result = self.backend.publish(self.identity, [self.command], ttl_ms=60000)
        self.assertEqual(result["expires"], 60100)

    def test_unknown_final_action_cannot_be_retested_in_new_session(self):
        command = dict(request_id="different-id-abandon-union", actor="BUR",
                       target="BRB", action="abandon_union")
        with self.assertRaisesRegex(ValueError, "Dispatched or uncertain final action"):
            self.backend.publish(self.identity, [command], test_only=True)
        self.assertEqual(self.runtime.checks, [])
        self.assertFalse(list(self.directory.glob("*.request")))

    def test_dispatched_unverified_action_is_not_made_retestable(self):
        command = dict(request_id="new-id-pronoia", actor="FRA", target="AMG", action="create_pronoia")
        with self.assertRaisesRegex(ValueError, "Dispatched or uncertain final action"):
            self.backend.publish(self.identity, [command], test_only=True)
        self.assertEqual(self.runtime.checks, [])
        self.assertFalse(list(self.directory.glob("*.request")))

    def test_128_bound_and_legacy_version_isolation(self):
        command = dict(self.command, action="select_rival")
        wire(self.identity, 128, 60100, command, purpose=self.backend.purpose,
             actions=self.backend.actions, limit=128)
        with self.assertRaisesRegex(ValueError, "Sequence bound"):
            wire(self.identity, 129, 60100, command, purpose=self.backend.purpose,
                 actions=self.backend.actions, limit=128)
        with self.assertRaisesRegex(ValueError, "no native binding"):
            validate_command(command, ACTIONS)
        too_many = [dict(command, request_id=f"bound-{i}") for i in range(129)]
        with self.assertRaisesRegex(ValueError, "Batch size bound"):
            self.backend.publish(self.identity, too_many)
        self.assertFalse(list(self.directory.glob("*.request")))

    def test_deferred_actions_and_parameters_cannot_enter_transport(self):
        for excluded in self.config["excluded"]:
            with self.assertRaisesRegex(ValueError, "no native binding"):
                validate_command(dict(self.command, action=excluded["action"]), self.backend.actions)
        for parameters in ({"province_id": 1}, {"amount": 100}, {"third_country": "FRA"}):
            with self.assertRaisesRegex(ValueError, "exactly"):
                self.backend.publish(self.identity, [dict(self.command, parameters=parameters)])
        self.assertFalse(list(self.directory.glob("*.request")))

    def test_compiled_registry_and_explicit_capability_limits(self):
        actual = TagCommandBackend(DEFAULT_MANIFEST)
        caps = actual.capabilities()
        self.assertEqual(len(caps["actions"]), 120)
        self.assertEqual(len(set(caps["actions"])), 120)
        self.assertEqual(len(caps["excluded"]), 27)
        self.assertEqual(caps["request_limit"], 128)
        self.assertEqual(caps["batch_expiry"]["maximum_ttl_ms"], 1800000)
        self.assertEqual([b["action"] for b in caps["bindings"]], caps["actions"])
        self.assertEqual(len(caps["categories"]), 8)
        self.assertEqual(caps["command_fields"], ["request_id", "action", "actor", "target"])
        self.assertTrue(caps["requires_explicit_manual_pause"])
        self.assertFalse(caps["automatic_retry"])
        self.assertFalse(caps["production_ready"])
        self.assertEqual(actual.actions[:len(ACTIONS)], ACTIONS)


if __name__ == "__main__":
    unittest.main()
