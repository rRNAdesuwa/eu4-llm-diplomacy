"""Independent synthetic graphs only; no game process, engine or live probe."""
import contextlib
from copy import deepcopy
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from bridge.tests.test_diplomacy_current_probe import FixtureMemory
from work import probe_diplomacy_relations_1375 as probe

BASE, DB, GAME, COUNTRIES = 0x140000000, 0x100000, 0x200000, 0x300000
FRANCE, TARGET = 0x400000, 0x410000
FRA_RECORDS, TARGET_RECORDS, ROOT_A, ROOT_B = 0x500000, 0x510000, 0x520000, 0x530000
ARRAY_A, ARRAY_B, RELATION = 0x540000, 0x550000, 0x560000
HOLDER, MANAGER, VECTOR, ENTRY, MISSION = 0x600000, 0x610000, 0x620000, 0x630000, 0x640000
OWNER, NODE, TASK, DEFINITION, NAME_HEAP = 0x650000, 0x660000, 0x670000, 0x680000, 0x690000
DATE = 56463336


def fixture(action, target="ENG", *, active=False, removed_task=False, reverse=False, dependency="vassal"):
    memory = FixtureMemory()
    put = memory.write_fixture
    put(BASE + probe.base.DATABASE_POINTER_RVA, DB)
    put(BASE + probe.base.GAME_POINTER_RVA, GAME)
    put(DB + 0x118, COUNTRIES)
    put(GAME + 0x1DD0, DATE, 4)
    put(GAME + 0x1E60, probe.HANDLES["FRA"])
    for tag, country, records in (("FRA", FRANCE, FRA_RECORDS), (target, TARGET, TARGET_RECORDS)):
        handle = probe.HANDLES[tag]
        put(COUNTRIES + ((handle >> 32) & 0xFFFF) * 8, country)
        put(country + 0x20, handle)
        put(country + 0x1510, records)
        put(country + 0x18F0, 0)
    for records, other, root in ((FRA_RECORDS, target, ROOT_A), (TARGET_RECORDS, "FRA", ROOT_B)):
        handle = probe.HANDLES[other]
        row = bytearray(0x48)
        struct.pack_into("<Q", row, 0, root)
        struct.pack_into("<Q", row, 0x10, handle)
        put(records + ((handle >> 32) & 0xFFFF) * 0x48, row)
    if action in probe.RELATIONS:
        aoff, acount, boff, bcount, size, vt = probe.RELATIONS[action]
        for root, array, off, countoff, other in ((ROOT_A, ARRAY_A, aoff, acount, target), (ROOT_B, ARRAY_B, boff, bcount, "FRA")):
            put(root + off, array if active else 0)
            put(root + countoff, int(active), 4)
            if active:
                put(array, struct.pack("<I4xQ", (probe.HANDLES[other] >> 32) & 0xFFFF, RELATION))
        if active:
            body = bytearray(size)
            actor, recipient = probe.HANDLES["FRA"], probe.HANDLES[target]
            if reverse:
                actor, recipient = recipient, actor
            struct.pack_into("<Q", body, 0, BASE + vt)
            struct.pack_into("<QQi", body, 0x10, actor, recipient, DATE)
            if action == "improve_relation":
                struct.pack_into("<Q", body, 0x30, MISSION)
            if action == "vassalaction":
                struct.pack_into("<Q", body, 0x40, DEFINITION)
                string = bytearray(32)
                encoded = dependency.encode("ascii")
                if len(encoded) < 16:
                    string[:len(encoded)] = encoded
                    capacity = 15
                else:
                    capacity = 31
                    struct.pack_into("<Q", string, 0, NAME_HEAP)
                    put(NAME_HEAP, encoded + b"\0" * (capacity + 1 - len(encoded)))
                struct.pack_into("<Q", string, 0x10, len(encoded))
                struct.pack_into("<Q", string, 0x18, capacity)
                put(DEFINITION + 0x10, string)
                put((FRANCE if reverse else TARGET) + 0x18F0, actor)
            put(RELATION, body)
    else:
        target_slot = (probe.HANDLES[target] >> 32) & 0xFFFF
        put(FRA_RECORDS + target_slot * 0x48 + 0x46, 8 if active else 0, 1)
        put(FRA_RECORDS + target_slot * 0x48 + 0x18, 1250, 2)
        put(TARGET + 0x14B0, OWNER)
        has_node = active or removed_task
        put(OWNER + 0x4F0, struct.pack("<QQI", NODE if has_node else 0, NODE if has_node else 0, int(has_node)))
        if has_node:
            node = bytearray(32)
            struct.pack_into("<Q", node, 0, TASK)
            node[0x18] = int(removed_task)
            put(NODE, node)
            if active:
                task = bytearray(0x50)
                struct.pack_into("<Q", task, 0, BASE + probe.SPY_TASK_VTABLE)
                struct.pack_into("<QQQ", task, 0x10, OWNER, probe.HANDLES["FRA"], probe.HANDLES[target])
                struct.pack_into("<I", task, 0x2C, 17)
                put(TASK, task)
    put(FRANCE + 0x1480, HOLDER)
    put(HOLDER + 0x18, MANAGER)
    put(MANAGER + 0x20, struct.pack("<QQ", VECTOR, VECTOR + 8))
    put(VECTOR, ENTRY)
    entry = bytearray(0x48)
    struct.pack_into("<I", entry, 0x44, 17)
    if active and action in ("improve_relation", "spy_network"):
        struct.pack_into("<Q", entry, 0x10, MISSION)
        entry[0x18] = 2
        mission = bytearray(0xF8)
        struct.pack_into("<Q", mission, 0, BASE + probe.base.MISSION_VTABLE)
        struct.pack_into("<ii", mission, 0x20, DATE, DATE + 24)
        struct.pack_into("<Q", mission, 0x48, ENTRY)
        struct.pack_into("<I", mission, 0x50, 17)
        struct.pack_into("<QQ", mission, 0x80, probe.HANDLES["FRA"], probe.HANDLES[target])
        struct.pack_into("<I", mission, 0xA8, probe.TOKENS[action])
        if action == "spy_network":
            struct.pack_into("<Q", mission, 0xA0, TASK)
        put(MISSION, mission)
    put(ENTRY, entry)
    return memory


def report(memory, action, target="ENG", *, after=False):
    stamp = "2026-10-08T10:00:01+00:00" if after else "2026-10-08T10:00:00+00:00"
    return {"schema_version": 1, "kind": "core_relation_snapshot", "profile": probe.PROFILE,
            "static_effect_evidence_sha256": probe.base.EVIDENCE_SHA256, "read_only": True,
            "static_cancel_evidence_sha256": probe.CANCEL_EVIDENCE_SHA256,
            "capture_started_at": stamp, "capture_finished_at": stamp,
            "build": {"sha256": probe.base.LOCAL_SHA256}, "actor": "FRA", "target": target, "action": action,
            "source": {"kind": "live_process", "pid": 123, "process_creation_filetime": 134358500000000000,
                       "process_exit_filetime": 0, "module_base": hex(BASE), "access_rights": "QUERY_INFORMATION | VM_READ"},
            "observation": probe.capture(memory, BASE, target, action)}


class CoreGraphTests(unittest.TestCase):
    def test_all_five_both_targets_addition_and_removal(self):
        for action in probe.TOKENS:
            for target in ("ENG", "POR"):
                with self.subTest(action=action, target=target):
                    before = report(fixture(action, target), action, target)
                    after = report(fixture(action, target, active=True), action, target, after=True)
                    result = probe.compare_reports(before, after)
                    self.assertTrue(result["observed_effect"], result)
                    self.assertFalse(result["request_causality_verified"])
                    self.assertFalse(result["execution_verified"])
                    before = report(fixture(action, target, active=True), action, target)
                    after = report(fixture(action, target), action, target, after=True)
                    result = probe.compare_reports(before, after, "cancel")
                    self.assertTrue(result["observed_effect"], result)
                    self.assertEqual(result["transition"], "removed_active_state")
                    self.assertFalse(result["rejection_observed"])

    def test_spy_deferred_removed_node_is_skipped_without_dereferencing_freed_task(self):
        before = report(fixture("spy_network", active=True), "spy_network")
        memory = fixture("spy_network", removed_task=True)
        self.assertNotIn(TASK, memory.memory)
        after = report(memory, "spy_network", after=True)
        self.assertEqual(after["observation"]["state"]["state"], "absent")
        self.assertTrue(probe.compare_reports(before, after, "cancel")["observed_effect"])
        # Spoofed decoded data on the deleted node is rejected offline too.
        for sample in after["observation"]["passes"]:
            sample["spy"]["nodes"][0]["task_vtable"] = hex(BASE + probe.SPY_TASK_VTABLE)
        self.assertFalse(probe.compare_reports(before, after, "cancel")["observed_effect"])

    def test_spy_positive_requires_all_links_and_not_only_activity_bit_or_busy_envoy(self):
        changes = ((TASK + 0x10, OWNER + 8, 8), (TASK + 0x18, probe.HANDLES["ENG"], 8),
                   (TASK + 0x20, probe.HANDLES["POR"], 8), (TASK + 0x2C, 18, 4),
                   (MISSION + 0xA0, TASK + 8, 8), (MISSION + 0xA8, probe.TOKENS["improve_relation"], 4),
                   (ENTRY + 0x18, 1, 1), (FRA_RECORDS + 46 * 0x48 + 0x46, 0, 1),
                   (TASK, BASE + 0x1CE3BA8, 8))
        for location, value, size in changes:
            with self.subTest(location=hex(location)):
                memory = fixture("spy_network", active=True)
                memory.write_fixture(location, value, size)
                observation = probe.capture(memory, BASE, "ENG", "spy_network")
                self.assertEqual(observation["status"], "unknown", observation)

    def test_spy_list_cycle_count_previous_tail_and_removed_bounds(self):
        changes = ((OWNER + 0x500, probe.MAX_TASKS + 1, 4), (NODE + 8, NODE, 8),
                   (NODE + 0x10, NODE, 8), (OWNER + 0x4F8, NODE + 8, 8), (NODE + 0x18, 2, 1))
        for location, value, size in changes:
            memory = fixture("spy_network", active=True)
            memory.write_fixture(location, value, size)
            self.assertEqual(probe.capture(memory, BASE, "ENG", "spy_network")["status"], "unknown")

    def test_spy_list_may_contain_other_task_types_without_decoding_their_layout(self):
        memory = fixture("spy_network")
        memory.write_fixture(OWNER + 0x4F0, struct.pack("<QQI", NODE, NODE, 1))
        memory.write_fixture(NODE, struct.pack("<QQQQ", TASK, 0, 0, 0))
        memory.write_fixture(TASK, BASE + 0x1ABC000)
        result = probe.capture(memory, BASE, "ENG", "spy_network")
        self.assertEqual(result["status"], "consistent_bounded_observation", result)
        self.assertEqual(result["state"]["state"], "absent")

    def test_spy_cancel_requires_original_envoy_identity_and_cleared_task_link(self):
        before = report(fixture("spy_network", active=True), "spy_network")
        after_memory = fixture("spy_network")
        after_memory.write_fixture(ENTRY + 0x44, 18, 4)
        after = report(after_memory, "spy_network", after=True)
        self.assertFalse(probe.compare_reports(before, after, "cancel")["observed_effect"])

    def test_spy_returning_mission_can_remain_after_its_task_is_removed(self):
        before_memory = fixture("spy_network", active=True)
        # The native +0x70 check is a vtable call, not an instance byte test.
        before_memory.write_fixture(MISSION + 0x70, 255, 1)
        before = report(before_memory, "spy_network")
        self.assertEqual(before["observation"]["state"]["state"], "active")
        after_memory = fixture("spy_network", removed_task=True)
        after_memory.write_fixture(MISSION, before_memory.read(MISSION, 0xF8))
        after_memory.write_fixture(MISSION + 0xA0, 0)
        after_memory.write_fixture(ENTRY + 0x10, MISSION)
        after_memory.write_fixture(ENTRY + 0x18, 1, 1)
        after = report(after_memory, "spy_network", after=True)
        self.assertTrue(probe.compare_reports(before, after, "cancel")["observed_effect"])

    def test_second_matching_spy_task_cannot_be_ignored(self):
        memory = fixture("spy_network", active=True)
        second_node, second_task = NODE + 0x100, TASK + 0x100
        memory.write_fixture(OWNER + 0x4F8, second_node)
        memory.write_fixture(OWNER + 0x500, 2, 4)
        memory.write_fixture(NODE + 0x10, second_node)
        memory.write_fixture(second_node, struct.pack("<QQQQ", second_task, NODE, 0, 0))
        memory.write_fixture(second_task, memory.read(TASK, 0x50))
        memory.write_fixture(second_task + 0x2C, 18, 4)
        result = probe.capture(memory, BASE, "ENG", "spy_network")
        self.assertEqual(result["status"], "unknown")
        self.assertIn("disagree", result["errors"][0])

    def test_guarantee_direction_and_marriage_symmetry_are_distinct(self):
        for action, expected in (("guaranteeaction", False), ("royal_marriage", True), ("vassalaction", False)):
            before = report(fixture(action), action)
            after = report(fixture(action, active=True, reverse=True), action, after=True)
            result = probe.compare_reports(before, after)
            self.assertEqual(result["observed_effect"], expected, result)
        # The relationship refresh bit is not guarantee or marriage existence.
        for action in ("guaranteeaction", "royal_marriage"):
            memory = fixture(action)
            memory.write_fixture(FRA_RECORDS + 46 * 0x48 + 0x46, 4, 1)
            self.assertEqual(probe.capture(memory, BASE, "ENG", action)["state"]["state"], "absent")

    def test_dependency_type_and_overlord_are_required(self):
        for name in ("march", "tributary_state", "some_long_subject_type"):
            before = report(fixture("vassalaction"), "vassalaction")
            after = report(fixture("vassalaction", active=True, dependency=name), "vassalaction", after=True)
            self.assertEqual(after["observation"]["state"]["state"], "other_dependency_type", after)
            self.assertFalse(probe.compare_reports(before, after)["observed_effect"])
        memory = fixture("vassalaction", active=True)
        memory.write_fixture(TARGET + 0x18F0, probe.HANDLES["POR"])
        self.assertEqual(probe.capture(memory, BASE, "ENG", "vassalaction")["status"], "unknown")

    def test_dependency_string_read_is_bounded_and_does_not_assume_pointer_storage(self):
        memory = fixture("vassalaction", active=True)
        name = probe.dependency_name(memory, DEFINITION)
        self.assertEqual(name["name"], "vassal")
        self.assertEqual(name["storage"], "inline")
        memory.write_fixture(DEFINITION + 0x10, b"x" * 16)
        with self.assertRaises(probe.base.ProbeError):
            probe.dependency_name(memory, DEFINITION)
        memory = fixture("vassalaction", active=True, dependency="some_long_subject_type")
        memory.write_fixture(NAME_HEAP, b"x" * 129)
        memory.write_fixture(DEFINITION + 0x10 + 0x18, 1 << 60)
        memory.write_fixture(DEFINITION + 0x10 + 0x10, 128)
        start = memory.bytes_read
        with self.assertRaises(probe.base.ProbeError):
            probe.dependency_name(memory, DEFINITION)
        self.assertEqual(memory.bytes_read - start, 32 + 129)
        memory.write_fixture(DEFINITION + 0x10 + 0x10, 1 << 60)
        start = memory.bytes_read
        with self.assertRaises(probe.base.ProbeError):
            probe.dependency_name(memory, DEFINITION)
        self.assertEqual(memory.bytes_read - start, 32)

    def test_repeated_snapshot_change_and_duplicate_relation_fail_closed(self):
        memory = fixture("royal_marriage", active=True)
        original = probe.sample_once
        calls = []

        def changing(*args):
            value = original(*args)
            calls.append(value)
            if len(calls) == 1:
                memory.write_fixture(GAME + 0x1DD0, DATE + 1, 4)
            return value

        with patch.object(probe, "sample_once", side_effect=changing):
            self.assertEqual(probe.capture(memory, BASE, "ENG", "royal_marriage")["status"], "unknown")
        memory = fixture("guaranteeaction", active=True)
        memory.write_fixture(ROOT_A + 0x1AC, 2, 4)
        memory.write_fixture(ARRAY_A + 16, struct.pack("<I4xQ", 46, RELATION))
        self.assertEqual(probe.capture(memory, BASE, "ENG", "guaranteeaction")["status"], "unknown")

    def test_no_missing_relation_or_preexisting_state_is_reported_as_rejection(self):
        for active in (True, False):
            before = report(fixture("royal_marriage", active=active), "royal_marriage")
            after = report(fixture("royal_marriage", active=active), "royal_marriage", after=True)
            result = probe.compare_reports(before, after)
            self.assertFalse(result["observed_effect"])
            self.assertFalse(result["rejection_observed"])

    def test_report_identity_and_raw_fields_are_revalidated(self):
        before = report(fixture("guaranteeaction"), "guaranteeaction")
        after = report(fixture("guaranteeaction", active=True), "guaranteeaction", after=True)
        for change in (lambda r: r["source"].update(process_creation_filetime=1),
                       lambda r: r["build"].update(sha256="0" * 64),
                       lambda r: r.update(target="POR"),
                       lambda r: r["observation"]["passes"][0]["relation"]["object"].update(removed=True)):
            changed = deepcopy(after)
            change(changed)
            self.assertFalse(probe.compare_reports(before, changed)["observed_effect"])

    def test_cli_compare_is_offline_and_preserves_saved_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            before, after, output = [directory / name for name in ("before.json", "after.json", "result.json")]
            before.write_text(json.dumps(report(fixture("spy_network"), "spy_network")), encoding="utf-8")
            after.write_text(json.dumps(report(fixture("spy_network", active=True), "spy_network", after=True)), encoding="utf-8")
            args = ["compare", "--before", str(before), "--after", str(after), "--direction", "positive", "--output", str(output)]
            with patch.object(probe.base, "ProcessReader", side_effect=AssertionError("must remain offline")), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(probe.main(args), 0)
                saved = output.read_bytes()
                self.assertEqual(probe.main(args), 2)
                self.assertEqual(saved, output.read_bytes())


if __name__ == "__main__":
    unittest.main()
