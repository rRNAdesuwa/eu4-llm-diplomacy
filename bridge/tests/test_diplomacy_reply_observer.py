"""Pure byte-layout tests: importing probe never opens a game process."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import struct
import tempfile
import unittest
from unittest.mock import patch

from bridge import diplomacy_reply_observer as probe


BASE, OWNER, NODE, ACTION = 0x140000000, 0x100000, 0x200000, 0x300000
ACTOR, TARGET = 0x0100007B004C524F, 0x0100007A00415246


class BytesReader:
    def __init__(self):
        self.data = {}
        self.reads = []

    def put(self, address, raw):
        self.data.update({address + i: b for i, b in enumerate(raw)})

    def read(self, address, size):
        self.reads.append((address, size))
        try:
            return bytes(self.data[address + i] for i in range(size))
        except KeyError as exc:
            raise AssertionError(f"Unexpected dereference at {address:#x}/{size}") from exc

    def q(self, address):
        return struct.unpack("<Q", self.read(address, 8))[0]

    def i(self, address):
        return struct.unpack("<i", self.read(address, 4))[0]


def inbox(*, state=0, removed=0, vt=None, original=ACTOR):
    r = BytesReader()
    r.put(OWNER + 0x18D8, struct.pack("<QQIB", NODE, NODE, 1, 0))
    r.put(NODE, struct.pack("<QQQB", ACTION, 0, 0, removed))
    if not removed:
        raw = bytearray(0x40)
        struct.pack_into("<QI", raw, 0, BASE + probe.ASK_VT if vt is None else vt, 357)
        struct.pack_into("<QQQ", raw, 0x10, ACTOR, original, TARGET)
        struct.pack_into("<iiii", raw, 0x28, 56466000, 56466024, -1, state)
        raw[0x38] = 1
        struct.pack_into("<i", raw, 0x3C, 77)
        r.put(ACTION, raw)
    return r


def history_fixture(key, endpoints, *, removed=0):
    r = BytesReader()
    server, manager, msg, definition, chars = 0x400000, 0x410000, 0x420000, 0x430000, 0x440000
    r.put(BASE + 0x1CB8460 + 0x228, struct.pack("<Q", BASE + 0x80E670))
    r.put(server + 0x1178, struct.pack("<Q", 0x450000))
    r.put(server + 0x12D0, struct.pack("<Q", manager))
    r.put(manager + 0x10, struct.pack("<QQIB", NODE, NODE, 1, 0))
    r.put(NODE, struct.pack("<QQQQB", msg, 0x460000, 0, 0, removed))
    if not removed:
        r.put(msg, struct.pack("<QQ", BASE + probe.MESSAGE_VTS[0], definition))
        r.put(msg + 0x28, struct.pack("<QQ", *endpoints))
        r.put(msg + 0x88, struct.pack("<i", 56466024))
        raw = bytearray(32)
        if len(key) < 16:
            raw[:len(key)] = key.encode()
            capacity = 15
        else:
            struct.pack_into("<Q", raw, 0, chars)
            r.put(chars, key.encode() + b"\0")
            capacity = 31
        struct.pack_into("<QQ", raw, 0x10, len(key), capacity)
        r.put(definition + 0x38, raw)
    return r, {"server": hex(server), "date": 56466024}


class ReplyLayoutTests(unittest.TestCase):
    def pending(self, reader):
        return probe.pending(reader, BASE, {"address": hex(OWNER)}, ACTOR, TARGET)

    def test_current_pending_retains_full_endpoints_token_dates_and_native_id(self):
        result = self.pending(inbox())
        match = result["selected_matches"][0]
        self.assertEqual(match["state_label"], "pending_observed")
        self.assertEqual(match["token"], 0x3021)
        self.assertEqual(match["native_request_id"], 77)
        self.assertEqual(match["actor_handle"], hex(ACTOR))
        self.assertEqual(match["original_actor_handle"], hex(ACTOR))
        self.assertEqual(match["recipient_handle"], hex(TARGET))

    def test_deleted_pending_never_dereferences_destroyed_action(self):
        reader = inbox(removed=1)
        self.assertEqual(self.pending(reader)["selected_matches"], [])
        self.assertTrue(all(a != ACTION for a, _ in reader.reads))

    def test_unknown_action_type_reads_only_its_vtable(self):
        reader = inbox(vt=BASE + 0x123456)
        self.assertEqual(self.pending(reader)["selected_matches"], [])
        self.assertEqual([n for a, n in reader.reads if a == ACTION], [8])

    def test_original_actor_is_part_of_selected_identity(self):
        result = self.pending(inbox(original=TARGET))
        self.assertEqual(result["selected_matches"], [])

    def test_nonzero_states_are_distinct_raw_reply_objects_not_applied_outcomes(self):
        for state, label in ((1, "rejected_state_object_observed"), (2, "accepted_state_object_observed")):
            with self.subTest(state=state):
                match = self.pending(inbox(state=state))["selected_matches"][0]
                self.assertEqual(match["state_label"], label)
                self.assertNotIn("applied_verified", match)

    def test_unsupported_state_is_unknown_via_error_not_interpreted(self):
        with self.assertRaises(ValueError):
            self.pending(inbox(state=3))

    def test_pending_count_and_iteration_are_checked_before_nodes(self):
        for count, iteration in ((129, 0), (1, 1)):
            with self.subTest(count=count, iteration=iteration):
                reader = inbox()
                reader.put(OWNER + 0x18D8, struct.pack("<QQIB", NODE, NODE, count, iteration))
                with self.assertRaises(ValueError):
                    self.pending(reader)
                self.assertTrue(all(a != NODE for a, _ in reader.reads))

    def test_pending_bad_previous_link_is_refused(self):
        reader = inbox()
        reader.put(NODE + 8, struct.pack("<Q", NODE))
        with self.assertRaises(ValueError):
            self.pending(reader)

    def test_rejection_notification_uses_reverse_request_direction(self):
        reader, root = history_fixture("ASK_FOR_MARCH_DENIED", (TARGET, ACTOR))
        match = probe.history(reader, BASE, root, ACTOR, TARGET)["selected_notifications"][0]
        self.assertEqual(match["outcome"], "rejection_notification_present")
        self.assertFalse(match["exact_external_request_id_causality_proven"])

    def test_designation_notification_uses_request_direction(self):
        reader, root = history_fixture("DESIGNATE_MARCH", (ACTOR, TARGET))
        match = probe.history(reader, BASE, root, ACTOR, TARGET)["selected_notifications"][0]
        self.assertEqual(match["outcome"], "march_designation_notification_present")
        self.assertFalse(match["exact_external_request_id_causality_proven"])

    def test_wrong_notification_direction_cannot_match(self):
        for key, endpoints in (("ASK_FOR_MARCH_DENIED", (ACTOR, TARGET)), ("DESIGNATE_MARCH", (TARGET, ACTOR))):
            with self.subTest(key=key):
                reader, root = history_fixture(key, endpoints)
                self.assertEqual(probe.history(reader, BASE, root, ACTOR, TARGET)["selected_notifications"], [])

    def test_removed_history_never_dereferences_destroyed_message(self):
        reader, root = history_fixture("ASK_FOR_MARCH_DENIED", (TARGET, ACTOR), removed=1)
        self.assertEqual(probe.history(reader, BASE, root, ACTOR, TARGET)["selected_notifications"], [])
        self.assertTrue(all(a != 0x420000 for a, _ in reader.reads))

    def test_missing_history_owner_is_unavailable_not_negative_outcome(self):
        reader, root = history_fixture("DESIGNATE_MARCH", (ACTOR, TARGET))
        reader.put(int(root["server"], 16) + 0x12D0, struct.pack("<Q", 0))
        value = probe.history(reader, BASE, root, ACTOR, TARGET)
        self.assertFalse(value["available"])
        self.assertEqual(value["selected_notifications"], [])


IDENTITY = {"pid": 1234, "creation": "1" * 16, "session": "2" * 32,
            "dll_sha256": "3" * 64, "manifest_sha256": "4" * 64}
COMMAND = {"request_id": "offline-ask-march", "action": "ask_for_march", "actor": "ORL", "target": "FRA"}


def snapshot_fixture():
    reader, root = history_fixture("DESIGNATE_MARCH", (ACTOR, TARGET))
    root.update(game="0x500000", database="0x510000", array="0x520000")
    actor = {"address": "0x530000", "handle": hex(ACTOR), "tag": "ORL", "slot": 123}
    recipient = {"address": hex(OWNER), "handle": hex(TARGET), "tag": "FRA", "slot": 122}
    return {"identity": deepcopy(IDENTITY), "roots": root, "actor": actor, "recipient": recipient,
        "pending": probe.pending(inbox(), BASE, recipient, ACTOR, TARGET),
        "history": probe.history(reader, BASE, root, ACTOR, TARGET)}


def new_notification(snapshot, *, denied=False, number=1):
    row = deepcopy(snapshot["history"]["selected_notifications"][0])
    row.update(node=hex(0x700000 + number * 0x100), message_raw=hex(0x800000 + number * 0x100),
        shared_owner_raw=hex(0x900000 + number * 0x100), key="ASK_FOR_MARCH_DENIED" if denied else "DESIGNATE_MARCH",
        actor_handle=hex(TARGET if denied else ACTOR), target_handle=hex(ACTOR if denied else TARGET),
        outcome="rejection_notification_present" if denied else "march_designation_notification_present")
    return row


class ReplyStateTests(unittest.TestCase):
    def setUp(self):
        self.before = snapshot_fixture()
        self.baseline = probe.reply_baseline(COMMAND, self.before, source_manifest_sha256="a" * 64)
        self.after = deepcopy(self.before)
        self.after["pending"]["selected_matches"] = []

    def test_unique_pending_is_waiting_even_with_old_designation_message(self):
        result = probe.evaluate_reply(COMMAND, self.before)
        self.assertEqual(result["request_state"], "waiting_for_recipient")
        self.assertEqual(result["native_request_id"], 77)
        self.assertFalse(result["AI_acceptance_verified"])
        self.assertFalse(result["exact_external_request_id_causality_verified"])

    def test_queue_disappearance_with_old_notifications_is_unknown(self):
        result = probe.evaluate_reply(COMMAND, self.after, self.baseline)
        self.assertEqual(result["request_state"], "unknown")
        self.assertEqual(result["correlated_notifications"], [])

    def test_no_baseline_does_not_attribute_existing_notification(self):
        self.after["history"]["selected_notifications"] = [new_notification(self.before)]
        self.assertEqual(probe.evaluate_reply(COMMAND, self.after)["request_state"], "unknown")

    def test_new_accepted_and_denied_notifications_are_correlations_only(self):
        for denied, expected in ((False, "accepted_notification"), (True, "denied_notification")):
            with self.subTest(denied=denied):
                self.after["history"]["selected_notifications"] = [new_notification(self.before, denied=denied)]
                result = probe.evaluate_reply(COMMAND, self.after, self.baseline)
                self.assertEqual(result["request_state"], expected)
                self.assertEqual(result["native_request_id"], 77)
                for key in ("exact_external_request_id_causality_verified", "AI_acceptance_verified", "applied_effect_verified", "persistence_verified", "world_epoch_proven"):
                    self.assertFalse(result[key])

    def test_any_reused_history_address_prevents_new_notification_attribution(self):
        old = self.baseline["history_addresses"][0]
        for key in ("node", "message_raw", "shared_owner_raw"):
            with self.subTest(reused=key):
                row = new_notification(self.before)
                row[key] = old[key]
                self.after["history"]["selected_notifications"] = [row]
                self.assertEqual(probe.evaluate_reply(COMMAND, self.after, self.baseline)["request_state"], "unknown")

    def test_conflicting_new_notifications_stay_unknown(self):
        self.after["history"]["selected_notifications"] = [new_notification(self.before), new_notification(self.before, denied=True, number=2)]
        result = probe.evaluate_reply(COMMAND, self.after, self.baseline)
        self.assertEqual(result["request_state"], "unknown")
        self.assertEqual(len(result["correlated_notifications"]), 2)

    def test_multiple_pending_objects_are_ambiguous(self):
        self.before["pending"]["selected_matches"] *= 2
        self.assertEqual(probe.evaluate_reply(COMMAND, self.before)["request_state"], "unknown")

    def test_baseline_identity_or_native_id_change_is_refused(self):
        bad = deepcopy(self.baseline)
        bad["identity"]["creation"] = "f" * 16
        with self.assertRaises(ValueError):
            probe.evaluate_reply(COMMAND, self.before, bad)
        bad = deepcopy(self.baseline)
        bad["native_request_id"] += 1
        with self.assertRaises(ValueError):
            probe.evaluate_reply(COMMAND, self.before, bad)

    def test_new_notification_wrong_direction_or_date_does_not_match(self):
        for field, value in (("actor_handle", hex(TARGET)), ("raw_date", self.baseline["now_raw"] - 1)):
            with self.subTest(field=field):
                row = new_notification(self.before)
                row[field] = value
                self.after["history"]["selected_notifications"] = [row]
                self.assertEqual(probe.evaluate_reply(COMMAND, self.after, self.baseline)["request_state"], "unknown")

    def test_inline_projection_excludes_unrelated_nodes_and_full_passes(self):
        value = probe.inline_reply(self.before)
        self.assertNotIn("nodes", value["pending"])
        self.assertNotIn("nodes", value["history"])
        self.assertNotIn("passes", value)
        self.assertEqual(len(value["history"]["nodes_sha256"]), 64)

    def test_maximum_selected_history_fits_http_bound(self):
        self.after["history"]["selected_notifications"] = [new_notification(self.before, number=i + 1) for i in range(200)]
        result = probe.evaluate_reply(COMMAND, self.after, self.baseline)
        self.assertLess(len(json.dumps(result).encode("ascii")), 220 * 1024)


class FakeReplyCaptureFactory:
    def __init__(self):
        self.snapshot = snapshot_fixture()
        self.calls = self.closed = 0
        self.error = None

    def __call__(self, identity, backend, **kwargs):
        factory = self
        factory.calls += 1

        class Context:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                factory.closed += 1

            def capture_reply(self, command, binding):
                if factory.error:
                    raise factory.error
                value = deepcopy(factory.snapshot)
                return {"identity": identity, "command": command, "two_pass_equal": True,
                    "snapshot": value, "passes": [deepcopy(value), deepcopy(value)], "duration_ms": 1.25,
                    "rpm_budget": {"calls": 10, "bytes": 100, "largest_read": 64}}

        return Context()


class ReplyCompositionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = Path(self.temporary.name) / "observations"
        self.manifest = Path(self.temporary.name) / "offline-source-manifest.json"
        self.manifest.write_text('{"offline": true}', encoding="ascii")
        self.status = {"command": deepcopy(COMMAND), "state": "dispatched", "binding": {"actor_handle": ACTOR, "target_handle": TARGET}, "audit_sha256": "a" * 64}
        self.original = {"schema": "EU4DIPLOMACY-OBSERVATION/1", "request_id": COMMAND["request_id"],
            "transport_state": "dispatched", "completion_state": "evidence_insufficient", "native_calls": 0,
            "requests_published": 0, "saves_written": 0, "AI_acceptance_verified": False,
            "effect": {"status": "not_observed", "selected_effect_verified": False, "changes": {}}}
        self.capture = FakeReplyCaptureFactory()
        backend = SimpleNamespace(manifest_path=Path("unused-offline-manifest.json"))
        self.observer = probe.ReplyAwareEffectObserver(IDENTITY, backend=backend, store=self.store,
            reply_capture_factory=self.capture, allow_tag_host=True)
        source_patch = patch.object(probe, "SOURCE_MANIFEST", self.manifest)
        recorded_patch = patch.object(probe, "recorded_snapshot", return_value=SimpleNamespace(status=lambda rid: deepcopy(self.status)))
        original_patch = patch.object(probe.EffectObserver, "observe", side_effect=lambda *a, **k: deepcopy(self.original))
        for patcher in (source_patch, recorded_patch, original_patch):
            value = patcher.start()
            self.addCleanup(patcher.stop)
        self.original_method = value

    def observe(self, **kwargs):
        return self.observer.observe(COMMAND["request_id"], **kwargs)

    def test_record_false_never_writes_and_preserves_original_effect(self):
        result = self.observe(record=False)
        self.assertEqual(result["request_state"], "waiting_for_recipient")
        self.assertEqual(result["completion_state"], "waiting_for_recipient")
        self.assertEqual(result["effect"], self.original["effect"])
        self.assertEqual(result["transport_state"], "dispatched")
        self.assertFalse(self.store.exists())
        self.original_method.assert_called_once_with(COMMAND["request_id"], record=False)
        self.assertEqual((self.capture.calls, self.capture.closed), (1, 1))

    def test_first_waiting_observation_retains_native_id_and_full_capture_separately(self):
        result = self.observe()
        directory = self.observer.directory(COMMAND["request_id"])
        baseline = json.loads((directory / "reply-baseline.json").read_text())
        self.assertEqual(baseline["native_request_id"], 77)
        self.assertTrue(Path(result["reply"]["capture_record"]["path"]).exists())
        self.assertTrue(Path(result["record"]).exists())
        self.assertNotIn("nodes", result["reply"]["selected"]["history"])
        self.assertEqual(result["reply"]["duration_ms"], 1.25)

    def test_later_empty_queue_without_new_notification_stays_unknown_and_baseline_is_immutable(self):
        self.observe()
        baseline_path = self.observer.directory(COMMAND["request_id"]) / "reply-baseline.json"
        before = baseline_path.read_bytes()
        self.capture.snapshot["pending"]["selected_matches"] = []
        result = self.observe()
        self.assertEqual(result["request_state"], "unknown")
        self.assertEqual(result["effect"], self.original["effect"])
        self.assertEqual(baseline_path.read_bytes(), before)

    def test_new_notification_keeps_original_effect_not_observed(self):
        self.observe()
        self.capture.snapshot["pending"]["selected_matches"] = []
        self.capture.snapshot["history"]["selected_notifications"] = [new_notification(snapshot_fixture())]
        result = self.observe(record=False)
        self.assertEqual(result["request_state"], "accepted_notification")
        self.assertEqual(result["effect"]["status"], "not_observed")
        self.assertFalse(result["effect"]["selected_effect_verified"])
        self.assertFalse(result["AI_acceptance_verified"])
        self.assertNotEqual(result["completion_state"], "selected_effect_observed")

    def test_capture_failure_preserves_dispatched_and_never_retries(self):
        self.capture.error = OSError("Read unavailable")
        result = self.observe(record=False)
        self.assertEqual(result["transport_state"], "dispatched")
        self.assertEqual(result["request_state"], "unknown")
        self.assertEqual(result["effect"], self.original["effect"])
        self.assertFalse(result["reply"]["automatic_command_retry"])
        self.assertEqual((self.capture.calls, self.capture.closed), (1, 1))

    def test_original_observation_failure_retains_recorded_transport(self):
        self.original_method.side_effect = ValueError("Invalid original baseline")
        result = self.observe(record=False)
        self.assertEqual(result["transport_state"], "dispatched")
        self.assertEqual(result["effect"]["status"], "unknown")
        self.assertEqual(result["completion_state"], "evidence_insufficient")
        self.assertEqual(result["request_state"], "waiting_for_recipient")

    def test_unsupported_or_not_dispatched_requests_do_not_capture_reply(self):
        for action, state in (("leave_coalition", "dispatched"), ("ask_for_march", "rejected")):
            with self.subTest(action=action, state=state):
                self.status["command"]["action"] = action
                self.status["state"] = state
                result = self.observe(record=False)
                self.assertEqual(result["request_state"], "unknown")
        self.assertEqual(self.capture.calls, 0)

    def test_effect_already_observed_is_never_downgraded_to_waiting(self):
        self.original["effect"].update(status="observed", selected_effect_verified=True)
        self.original["completion_state"] = "selected_effect_observed"
        result = self.observe(record=False)
        self.assertEqual(result["completion_state"], "selected_effect_observed")
        self.assertEqual(result["request_state"], "waiting_for_recipient")

    def test_corrupt_reply_baseline_keeps_transport_and_effect(self):
        self.observe()
        path = self.observer.directory(COMMAND["request_id"]) / "reply-baseline.json"
        path.write_text("invalid-json", encoding="ascii")
        result = self.observe(record=False)
        self.assertEqual(result["transport_state"], "dispatched")
        self.assertEqual(result["reply"]["status"], "unknown")
        self.assertEqual(result["effect"], self.original["effect"])

    def test_r2_cli_compact_and_waiting_exit_contract(self):
        from tools import observe_diplomacy_replies as cli
        result = self.observe(record=False)
        summary = cli.compact(result)
        self.assertEqual(cli.result_code(result), 3)
        self.assertEqual(summary["pending_requests"][0]["native_request_id"], 77)
        self.assertEqual(summary["reply_capture_duration_ms"], 1.25)
        self.assertEqual(summary["request_state"], "waiting_for_recipient")


class ReplySourceGuardTests(unittest.TestCase):
    def test_source_manifest_verifies_offline_without_runtime_construction(self):
        with patch.object(probe, "RuntimeCapture", side_effect=AssertionError("No runtime permitted")):
            self.assertTrue(probe.reply_source_pins())

    def test_changed_module_bytes_are_refused(self):
        actual = probe.read
        module = probe.ROOT / "bridge/diplomacy_reply_observer.py"

        def changed(path, limit):
            return b"changed" if Path(path) == module else actual(path, limit)

        with patch.object(probe, "read", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "Reply source/evidence changed"):
                probe.reply_source_pins()

    def test_source_manifest_cannot_escape_workspace(self):
        actual = probe.read
        manifest = json.loads(actual(probe.SOURCE_MANIFEST, 65536))
        manifest["source_pins"] = {"../outside.py": {"bytes": 1, "sha256": "a" * 64}}

        def changed(path, limit):
            return json.dumps(manifest).encode() if Path(path) == probe.SOURCE_MANIFEST else actual(path, limit)

        with patch.object(probe, "read", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "Invalid reply source path"):
                probe.reply_source_pins()


if __name__ == "__main__":
    unittest.main()



