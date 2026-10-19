"""Synthetic sparse-memory and saved-report tests; never access a game process."""
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
from work import probe_pair_effects_1375 as probe

BASE, DATABASE, GAME, COUNTRIES = 0x140000000, 0x100000, 0x200000, 0x300000
FRANCE, ENGLAND = 0x400000, 0x410000
FRA_RECORDS, ENG_RECORDS, OUT_ROOT, IN_ROOT = 0x500000, 0x510000, 0x520000, 0x530000
OUT_ARRAY, IN_ARRAY, RELATION = 0x540000, 0x550000, 0x560000
HOLDER, MANAGER, VECTOR, ENTRY, MISSION = 0x600000, 0x610000, 0x620000, 0x630000, 0x640000
DATE = 56463336


def fixture(*, active=False, mission_only=False):
    memory = FixtureMemory()
    put = memory.write_fixture
    put(BASE + probe.DATABASE_POINTER_RVA, DATABASE)
    put(BASE + probe.GAME_POINTER_RVA, GAME)
    put(DATABASE + 0x118, COUNTRIES)
    put(GAME + 0x1DD0, DATE, 4)
    put(GAME + 0x1E60, probe.PAIR["FRA"])
    for tag, country, records in (("FRA", FRANCE, FRA_RECORDS), ("ENG", ENGLAND, ENG_RECORDS)):
        handle = probe.PAIR[tag]
        put(COUNTRIES + ((handle >> 32) & 0xFFFF) * 8, country)
        put(country + 0x20, handle)
        put(country + 0x1510, records)
    for records, other, root, array, array_offset, count_offset in (
        (FRA_RECORDS, "ENG", OUT_ROOT, OUT_ARRAY, 0x1D0, 0x1DC),
        (ENG_RECORDS, "FRA", IN_ROOT, IN_ARRAY, 0x1E8, 0x1F4),
    ):
        handle = probe.PAIR[other]
        slot = (handle >> 32) & 0xFFFF
        put(records + slot * 0x48, struct.pack("<QQQ", root, 0, handle))
        put(root + array_offset, array if active else 0)
        put(root + count_offset, 1 if active else 0, 4)
        if active:
            put(array, struct.pack("<I4xQ", slot, RELATION))
    put(FRANCE + 0x1480, HOLDER)
    put(HOLDER + 0x18, MANAGER)
    put(MANAGER + 0x20, struct.pack("<QQ", VECTOR, VECTOR + 8))
    put(VECTOR, ENTRY)
    entry = bytearray(0x48)
    struct.pack_into("<I", entry, 0x44, 17)
    if active or mission_only:
        struct.pack_into("<Q", entry, 0x10, MISSION)
        entry[0x18] = 2
        body = bytearray(0xF8)
        struct.pack_into("<Q", body, 0, BASE + probe.MISSION_VTABLE)
        struct.pack_into("<ii", body, 0x20, DATE, DATE + 24)
        struct.pack_into("<Q", body, 0x48, ENTRY)
        struct.pack_into("<I", body, 0x50, 17)
        struct.pack_into("<QQ", body, 0x80, probe.PAIR["FRA"], probe.PAIR["ENG"])
        struct.pack_into("<I", body, 0xA8, probe.IMPROVE_TOKEN)
        put(MISSION, body)
    put(ENTRY, entry)
    if active:
        body = bytearray(0x48)
        struct.pack_into("<Q", body, 0, BASE + probe.RELATION_VTABLE)
        struct.pack_into("<QQi", body, 0x10, probe.PAIR["FRA"], probe.PAIR["ENG"], DATE)
        struct.pack_into("<Q", body, 0x30, MISSION)
        put(RELATION, body)
    return memory


def report(memory, *, after=False):
    stamp = "2026-10-07T10:00:01+00:00" if after else "2026-10-07T10:00:00+00:00"
    return {"schema_version": 1, "kind": "pair_effect_snapshot", "profile": probe.PROFILE,
            "static_evidence_sha256": probe.EVIDENCE_SHA256, "read_only": True,
            "capture_started_at": stamp, "capture_finished_at": stamp,
            "build": {"sha256": probe.LOCAL_SHA256},
            "source": {"kind": "live_process", "pid": 123, "process_creation_filetime": 134358500000000000,
                       "process_exit_filetime": 0, "module_base": hex(BASE), "access_rights": "QUERY_INFORMATION | VM_READ"},
            "observation": probe.capture(memory, BASE)}


class PairEffectMemoryTests(unittest.TestCase):
    def test_relation_vtable_uses_corrected_rip_relative_target(self):
        # 5730e4: LEA rcx,[RIP+170e56d], next RIP=5730eb.
        # Keep this numeric evidence independent of the fixture's shared constant.
        self.assertEqual(probe.RELATION_VTABLE, 0x5730EB + 0x170E56D)
        memory = fixture(active=True)
        memory.write_fixture(RELATION, BASE + 0x1C81558)
        self.assertEqual(probe.capture(memory, BASE)["status"], "unknown")

    def test_new_matching_two_sided_relation_and_envoy_are_required_for_observed_effect(self):
        before, after = report(fixture()), report(fixture(active=True), after=True)
        result = probe.compare_reports(before, after)
        self.assertTrue(result["observed_effect"], result)
        self.assertEqual(result["matching_mission"]["envoy_id"], 17)
        self.assertEqual(result["matching_mission"]["mission"]["action_token"], probe.IMPROVE_TOKEN)
        for key in ("execution_verified", "request_causality_verified", "ai_acceptance_verified", "whole_world_unchanged_verified", "rejection_observed"):
            self.assertFalse(result[key])

    def test_absence_and_existing_relation_never_imply_rejection_or_new_effect(self):
        for active in (False, True):
            result = probe.compare_reports(report(fixture(active=active)), report(fixture(active=active), after=True))
            self.assertFalse(result["observed_effect"])
            self.assertFalse(result["rejection_observed"])
            self.assertEqual(result["status"], "unknown")
        result = probe.compare_reports(report(fixture(mission_only=True)), report(fixture(active=True), after=True))
        self.assertFalse(result["observed_effect"])
        self.assertIn("already existed", result["errors"][0])

    def test_relation_and_mission_field_corruption_fail_closed(self):
        corruptions = (
            (RELATION, BASE + probe.MISSION_VTABLE, 8),
            (RELATION + 0x10, probe.PAIR["FRA"] ^ (1 << 56), 8),
            (RELATION + 0x18, probe.PAIR["FRA"], 8),
            (RELATION + 0x28, 1, 1),
            (RELATION + 0x30, MISSION + 8, 8),
            (MISSION, BASE + probe.RELATION_VTABLE, 8),
            (MISSION + 0xA8, 0x3378, 4),
            (MISSION + 0x80, probe.PAIR["ENG"], 8),
            (MISSION + 0x88, probe.PAIR["FRA"], 8),
            (MISSION + 0x48, ENTRY + 8, 8),
            (MISSION + 0x50, 18, 4),
            (ENTRY + 0x18, 0, 1),
        )
        for location, value, size in corruptions:
            with self.subTest(location=hex(location)):
                memory = fixture(active=True)
                memory.write_fixture(location, value, size)
                sample = report(memory, after=True)
                self.assertEqual(sample["observation"]["status"], "unknown")
                self.assertFalse(probe.compare_reports(report(fixture()), sample)["observed_effect"])

    def test_full_handle_and_counterpart_are_checked_not_only_country_slot(self):
        for location in (FRANCE + 0x20, FRA_RECORDS + 46 * 0x48 + 0x10):
            memory = fixture()
            old = memory.qword(location)
            memory.write_fixture(location, old ^ (1 << 56))
            self.assertEqual(probe.capture(memory, BASE)["status"], "unknown")

    def test_disagreeing_indexes_do_not_follow_possibly_removed_relation(self):
        memory = fixture(active=True)
        memory.write_fixture(IN_ARRAY + 8, RELATION + 0x1000)
        for location in range(RELATION, RELATION + 0x48):
            del memory.memory[location]
        result = probe.capture(memory, BASE)
        self.assertEqual(result["status"], "unknown")
        self.assertIn("indexes disagree", result["errors"][0])
        self.assertNotIn("Fixture does not capture", result["errors"][0])

    def test_count_pointer_and_total_read_limits(self):
        for location, value, size in ((OUT_ROOT + 0x1DC, probe.MAX_RELATION_ENTRIES + 1, 4),
                                      (MANAGER + 0x28, VECTOR + (probe.MAX_DIPLOMATS + 1) * 8, 8),
                                      (OUT_ROOT + 0x1D0, 3, 8)):
            memory = fixture(active=True)
            memory.write_fixture(location, value, size)
            self.assertEqual(probe.capture(memory, BASE)["status"], "unknown")
        memory = fixture()
        memory.bytes_read = probe.MAX_TOTAL_READ
        self.assertIn("budget", probe.capture(memory, BASE)["errors"][0])

    def test_duplicate_entries_ids_and_missing_memory_are_unknown(self):
        for mode in ("relation", "envoy", "mission_unreadable"):
            memory = fixture(active=True)
            if mode == "relation":
                memory.write_fixture(OUT_ROOT + 0x1DC, 2, 4)
                memory.write_fixture(OUT_ARRAY + 16, struct.pack("<I4xQ", 46, RELATION))
            elif mode == "envoy":
                memory.write_fixture(MANAGER + 0x28, VECTOR + 16)
                memory.write_fixture(VECTOR + 8, ENTRY)
            else:
                del memory.memory[MISSION + 0xA8]
            self.assertEqual(probe.capture(memory, BASE)["status"], "unknown")

    def test_two_pass_race_is_unknown_and_old_pointer_is_not_reused(self):
        memory = fixture(active=True)
        original = probe.sample_once
        calls = []

        def changing(reader, base):
            result = original(reader, base)
            calls.append(result)
            if len(calls) == 1:
                memory.write_fixture(OUT_ROOT + 0x1DC, 0, 4)
                memory.write_fixture(IN_ROOT + 0x1F4, 0, 4)
                memory.write_fixture(ENTRY + 0x10, 0)
                memory.write_fixture(ENTRY + 0x18, 0, 1)
                for location in range(RELATION, RELATION + 0x48):
                    del memory.memory[location]
            return result

        with patch.object(probe, "sample_once", side_effect=changing):
            result = probe.capture(memory, BASE)
        self.assertEqual(len(calls), 2)
        self.assertIsNone(calls[1]["relation"])
        self.assertIn("Repeated samples differ", result["errors"][0])


class PairEffectReportTests(unittest.TestCase):
    def setUp(self):
        self.before = report(fixture())
        self.after = report(fixture(active=True), after=True)

    def test_pid_reuse_identity_build_and_date_pins(self):
        alterations = (
            lambda r: r["source"].update(pid=124),
            lambda r: r["source"].update(process_creation_filetime=134358500000000001),
            lambda r: r["source"].update(process_exit_filetime=1),
            lambda r: r["build"].update(sha256="0" * 64),
            lambda r: r.update(read_only=False),
            lambda r: r.update(capture_started_at="2026-10-06T00:00:00+00:00"),
        )
        for alteration in alterations:
            value = deepcopy(self.after)
            alteration(value)
            result = probe.compare_reports(self.before, value)
            self.assertFalse(result["observed_effect"], result)
            self.assertTrue(result["errors"])

    def test_raw_date_can_advance_but_not_roll_back_or_predate_baseline(self):
        later = fixture(active=True)
        later.write_fixture(GAME + 0x1DD0, DATE + 24, 4)
        self.assertTrue(probe.compare_reports(self.before, report(later, after=True))["observed_effect"])
        later.write_fixture(RELATION + 0x20, DATE - 24, 4)
        self.assertFalse(probe.compare_reports(self.before, report(later, after=True))["observed_effect"])
        earlier = fixture()
        earlier.write_fixture(GAME + 0x1DD0, DATE - 1, 4)
        self.assertFalse(probe.compare_reports(self.before, report(earlier, after=True))["observed_effect"])

    def test_success_flags_cannot_replace_graph_revalidation(self):
        after = deepcopy(self.after)
        for sample in after["observation"]["passes"]:
            sample["relation"]["removed"] = 1
        after["observation"]["graph"]["active_relation"]["removed"] = 1
        result = probe.compare_reports(self.before, after)
        self.assertFalse(result["observed_effect"])
        after = deepcopy(self.after)
        after["observation"]["passes"][0]["current_raw_date"] += 1
        self.assertFalse(probe.compare_reports(self.before, after)["observed_effect"])
        after = deepcopy(self.after)
        for sample in after["observation"]["passes"]:
            sample["relation"]["removed"] = False  # Python false equals zero; strict type still required.
        after["observation"]["graph"]["active_relation"]["removed"] = False
        self.assertFalse(probe.compare_reports(self.before, after)["observed_effect"])

    def test_offline_cli_never_opens_process_and_preserves_input_and_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            before, after, output = (directory / name for name in ("before.json", "after.json", "result.json"))
            before.write_text(json.dumps(self.before), encoding="utf-8")
            after.write_text(json.dumps(self.after), encoding="utf-8")
            args = ["compare", "--before", str(before), "--after", str(after), "--output", str(output)]
            with patch.object(probe, "ProcessReader", side_effect=AssertionError("must remain offline")), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(probe.main(args), 0)
                saved = output.read_bytes()
                self.assertEqual(probe.main(args), 2)
                self.assertEqual(output.read_bytes(), saved)
                args[-1] = str(before)
                self.assertEqual(probe.main(args), 2)
            self.assertEqual(json.loads(before.read_text()), self.before)
            self.assertTrue(json.loads(saved)["observed_effect"])

    def test_malformed_oversized_and_duplicate_key_reports_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            for data in (b'{"x":1,"x":2}', b'{"x":NaN}', b'[1,2]', b'{'):
                path.write_bytes(data)
                with self.assertRaises((probe.ProbeError, probe.EvidenceError)):
                    probe.read_report(path)
            path.write_bytes(b" " * 257)
            with patch.object(probe, "MAX_REPORT_BYTES", 256), self.assertRaises(probe.ProbeError):
                probe.read_report(path)


if __name__ == "__main__":
    unittest.main()
