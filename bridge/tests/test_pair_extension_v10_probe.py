"""Sparse synthetic memory only: no real process opening or game calls."""
from copy import deepcopy
import contextlib
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from bridge.tests.test_diplomacy_current_probe import FixtureMemory
from work import probe_pair_extension_v10_1375 as probe

BASE, DB, GAME, ARRAY = 0x140000000, 0x100000, 0x200000, 0x300000
FRA, TARGET = 0x400000, 0x410000
RECORDS_A, RECORDS_B, ROOT_A, ROOT_B = 0x500000, 0x510000, 0x520000, 0x530000
INDEX_A, INDEX_B, OBJ = 0x540000, 0x550000, 0x560000
DATE = 56463336


def fixture(action="milaccess", *, active=False, target="ENG"):
    mem = FixtureMemory()
    put = mem.write_fixture
    put(BASE + probe.base.DATABASE_POINTER_RVA, DB)
    put(BASE + probe.base.GAME_POINTER_RVA, GAME)
    put(DB + 0x118, ARRAY)
    put(GAME + 0x1DD0, DATE, 4)
    put(GAME + 0x1E60, probe.HANDLES["FRA"])
    for tag, country, records, root, other in (("FRA", FRA, RECORDS_A, ROOT_A, target), (target, TARGET, RECORDS_B, ROOT_B, "FRA")):
        handle = probe.HANDLES[tag]
        put(ARRAY + ((handle >> 32) & 0xFFFF) * 8, country)
        put(country + 0x20, handle)
        put(country + 0x1510, records)
        record = bytearray(0x48)
        struct.pack_into("<QQQ", record, 0, root, 0, probe.HANDLES[other])
        put(records + ((probe.HANDLES[other] >> 32) & 0xFFFF) * 0x48, record)
        put(root, bytes(0x300))
    if action == "embargoaction":
        put(RECORDS_A + ((probe.HANDLES[target] >> 32) & 0xFFFF) * 0x48 + 0x46, 2 if active else 0, 1)
    elif active:
        aoff, acount, boff, bcount, vt, direction = probe.RELATIONS[action]
        for root, index, other, off, count in ((ROOT_A, INDEX_A, target, aoff, acount), (ROOT_B, INDEX_B, "FRA", boff, bcount)):
            put(root + off, index)
            put(root + count, 1, 4)
            put(index, struct.pack("<I4xQ", (probe.HANDLES[other] >> 32) & 0xFFFF, OBJ))
        body = bytearray(0x48)
        pair = [probe.HANDLES["FRA"], probe.HANDLES[target]]
        if direction == "reverse":
            pair.reverse()
        struct.pack_into("<Q", body, 0, BASE + vt)
        struct.pack_into("<I", body, 8, 0x165)
        struct.pack_into("<QQi", body, 0x10, *pair, DATE)
        if action == "warsubsidy":
            struct.pack_into("<ii", body, 0x40, 1000, 10)
        put(OBJ, body)
    return mem


def report(mem, action="milaccess", *, target="ENG", after=False):
    stamp = "2026-10-08T10:00:01+00:00" if after else "2026-10-08T10:00:00+00:00"
    return {"schema_version": 1, "kind": "pair_extension_snapshot", "profile": probe.PROFILE,
            "static_effect_evidence_sha256": probe.EVIDENCE_SHA256, "static_extension_evidence_sha256": probe.EXTENSION_SHA256,
            "read_only": True, "capture_started_at": stamp, "capture_finished_at": stamp,
            "build": {"sha256": probe.base.LOCAL_SHA256}, "actor": "FRA", "target": target, "action": action,
            "source": {"kind": "live_process", "pid": 123, "process_creation_filetime": 134358500000000000,
                       "process_exit_filetime": 0, "module_base": hex(BASE), "access_rights": "QUERY_INFORMATION | VM_READ"},
            "observation": probe.capture(mem, BASE, target, action)}


class ExtensionObservationTests(unittest.TestCase):
    def test_all_seven_families_four_targets_add_and_remove(self):
        for action in probe.ACTIONS:
            for target in probe.TARGETS:
                with self.subTest(action=action, target=target):
                    empty = report(fixture(action, target=target), action, target=target)
                    active = report(fixture(action, active=True, target=target), action, target=target, after=True)
                    added = probe.compare_reports(empty, active)
                    self.assertTrue(added["observed_effect"], added)
                    for field in ("execution_verified", "request_causality_verified", "ai_acceptance_verified", "rejection_observed", "whole_world_unchanged_verified"):
                        self.assertFalse(added[field])
                    before = report(fixture(action, active=True, target=target), action, target=target)
                    after = report(fixture(action, target=target), action, target=target, after=True)
                    self.assertTrue(probe.compare_reports(before, after, "cancel")["observed_effect"])

    def test_ask_and_offer_use_opposite_physical_indexes(self):
        for ask, offer in (("milaccess", "offermilaccess"), ("fleet_access", "offer_fleet_access")):
            memory = fixture(ask, active=True)
            self.assertEqual(probe.capture(memory, BASE, "ENG", ask)["state"]["state"], "active")
            # Same memory, different family: no corresponding grant to ENG.
            self.assertEqual(probe.capture(memory, BASE, "ENG", offer)["state"]["state"], "absent")
            memory.write_fixture(OBJ + 0x10, probe.HANDLES["ENG"])
            memory.write_fixture(OBJ + 0x18, probe.HANDLES["FRA"])
            self.assertEqual(probe.capture(memory, BASE, "ENG", ask)["status"], "unknown")
        self.assertEqual(probe.RELATIONS["milaccess"][:4], (0xB0, 0xBC, 0xC8, 0xD4))
        self.assertEqual(probe.RELATIONS["fleet_access"][:4], (0xE0, 0xEC, 0xF8, 0x104))

    def test_alliance_is_symmetric_but_incoming_subsidy_is_not_outgoing(self):
        for action, expected in (("allianceaction", "active"), ("warsubsidy", "reverse_relation")):
            memory = fixture(action, active=True)
            memory.write_fixture(OBJ + 0x10, probe.HANDLES["ENG"])
            memory.write_fixture(OBJ + 0x18, probe.HANDLES["FRA"])
            observed = report(memory, action, after=True)
            self.assertEqual(observed["observation"]["state"]["state"], expected)
            difference = probe.compare_reports(report(fixture(action), action), observed)
            self.assertEqual(difference["observed_effect"], action == "allianceaction")

    def test_enforce_peace_flag_is_not_an_ordinary_access_proposal(self):
        for action in probe.ACCESS:
            memory = fixture(action, active=True)
            memory.write_fixture(OBJ + 0x40, 1, 1)
            active = report(memory, action, after=True)
            self.assertEqual(active["observation"]["state"]["state"], "enforce_peace_relation")
            self.assertFalse(probe.compare_reports(report(fixture(action), action), active)["observed_effect"])
            memory.write_fixture(OBJ + 0x40, 2, 1)
            self.assertEqual(probe.capture(memory, BASE, "ENG", action)["status"], "unknown")

    def test_conditional_permission_without_explicit_protocol_is_absent(self):
        memory = fixture()
        # Other relation-index storage may permit movement under native rules;
        # no explicit b0/c8 protocol object exists and it must stay absent.
        memory.write_fixture(ROOT_A + 0x50, INDEX_A)
        memory.write_fixture(ROOT_A + 0x5C, 1, 4)
        memory.write_fixture(INDEX_A, struct.pack("<I4xQ", 46, 0x770000))
        result = probe.capture(memory, BASE, "ENG", "milaccess")
        self.assertEqual(result["state"]["state"], "absent")
        self.assertFalse(result["state"]["rejection_observed"])

    def test_embargo_uses_outgoing_mask_two_not_dirty_or_reverse(self):
        memory = fixture("embargoaction")
        out = RECORDS_A + 46 * 0x48 + 0x46
        incoming = RECORDS_B + 122 * 0x48 + 0x46
        memory.write_fixture(out, 4, 1)
        memory.write_fixture(incoming, 2, 1)
        captured = probe.capture(memory, BASE, "ENG", "embargoaction")
        self.assertEqual(captured["state"]["state"], "absent")
        self.assertTrue(captured["state"]["incoming_embargo"])
        memory.write_fixture(out, 6, 1)
        self.assertEqual(probe.capture(memory, BASE, "ENG", "embargoaction")["state"]["state"], "active")

    def test_full_handle_vtable_marker_removed_and_index_mismatch_fail_closed(self):
        mutations = ((OBJ, BASE + 0x1C7FB70, 8), (OBJ + 8, 0, 4), (OBJ + 0x28, 1, 1),
                     (OBJ + 0x18, probe.HANDLES["ENG"] ^ (1 << 56), 8),
                     (INDEX_B + 8, OBJ + 0x100, 8), (ROOT_A + 0xBC, 4097, 4),
                     (ROOT_B + 0xD4, 0, 4), (RECORDS_A + 46 * 0x48 + 0x10, probe.HANDLES["POR"], 8))
        for ptr, value, size in mutations:
            with self.subTest(ptr=hex(ptr), value=value):
                memory = fixture(active=True)
                memory.write_fixture(ptr, value, size)
                self.assertEqual(probe.capture(memory, BASE, "ENG", "milaccess")["status"], "unknown")

    def test_duplicate_slots_and_read_budget_fail_closed(self):
        memory = fixture(active=True)
        memory.write_fixture(ROOT_A + 0xBC, 2, 4)
        memory.write_fixture(INDEX_A + 16, struct.pack("<I4xQ", 46, OBJ))
        self.assertEqual(probe.capture(memory, BASE, "ENG", "milaccess")["status"], "unknown")
        memory = fixture(active=True)
        memory.bytes_read = probe.base.MAX_TOTAL_READ
        self.assertEqual(probe.capture(memory, BASE, "ENG", "milaccess")["status"], "unknown")

    def test_second_pass_date_change_and_unreadable_memory_are_unknown(self):
        memory = fixture(active=True)
        original = memory.read
        reads = 0
        def changing(location, size):
            nonlocal reads
            if location == GAME + 0x1DD0:
                reads += 1
                if reads == 3:
                    memory.write_fixture(location, DATE + 24, 4)
            return original(location, size)
        memory.read = changing
        self.assertEqual(probe.capture(memory, BASE, "ENG", "milaccess")["status"], "unknown")
        memory = fixture(active=True)
        del memory.memory[OBJ]
        self.assertEqual(probe.capture(memory, BASE, "ENG", "milaccess")["status"], "unknown")

    def test_subsidy_units_and_optional_exact_expected_parameters(self):
        before = report(fixture("warsubsidy"), "warsubsidy")
        after = report(fixture("warsubsidy", active=True), "warsubsidy", after=True)
        result = probe.compare_reports(before, after, expected_subsidy=(1000, 10))
        self.assertTrue(result["observed_effect"])
        self.assertEqual(result["after_state"]["nominal_expiry_raw_date"], DATE + 10 * 0x2238)
        for expected in ((1, 10), (1000, 120), (True, 10)):
            self.assertFalse(probe.compare_reports(before, after, expected_subsidy=expected)["observed_effect"])
        memory = fixture("warsubsidy", active=True)
        memory.write_fixture(OBJ + 0x44, 0x7FFFFFFF, 4)
        self.assertEqual(probe.capture(memory, BASE, "ENG", "warsubsidy")["status"], "unknown")

    def test_report_identity_hash_direction_and_stored_state_cannot_be_substituted(self):
        before = report(fixture())
        after = report(fixture(active=True), after=True)
        for edit in (lambda r: r["source"].update(process_creation_filetime=9),
                     lambda r: r.update(profile="1375_core_relation_observation_v7_1"),
                     lambda r: r.update(static_effect_evidence_sha256="0" * 64),
                     lambda r: r["observation"]["state"].update(state="absent"),
                     lambda r: r.update(action="offermilaccess"),
                     lambda r: r["build"].update(sha256="0" * 64)):
            changed = deepcopy(after)
            edit(changed)
            self.assertFalse(probe.compare_reports(before, changed)["observed_effect"])
        self.assertFalse(probe.compare_reports(after, before)["observed_effect"])

    def test_unchanged_or_absent_state_never_implies_rejection(self):
        for active in (False, True):
            result = probe.compare_reports(report(fixture(active=active)), report(fixture(active=active), after=True))
            self.assertFalse(result["observed_effect"])
            self.assertFalse(result["rejection_observed"])

    def test_compare_cli_is_offline_and_preserves_existing_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            before, after, output = (folder / name for name in ("before.json", "after.json", "result.json"))
            before.write_text(json.dumps(report(fixture())), encoding="utf-8")
            after.write_text(json.dumps(report(fixture(active=True), after=True)), encoding="utf-8")
            with patch.object(probe.base, "ProcessReader", side_effect=AssertionError("must not open process")), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                arguments = ["compare", "--before", str(before), "--after", str(after), "--direction", "positive", "--output", str(output)]
                self.assertEqual(probe.main(arguments), 0)
                saved = output.read_bytes()
                self.assertEqual(probe.main(arguments), 2)
                self.assertEqual(output.read_bytes(), saved)

    def test_profile_evidence_is_exact_and_never_runtime_verified(self):
        path = probe.ROOT / "work/reports/native-pair-extension-effects-v10-1375.json"
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), probe.EVIDENCE_SHA256)
        evidence = json.loads(path.read_text())
        self.assertFalse(evidence["runtime_verified"])
        self.assertFalse(evidence["execution_verified"])
        self.assertEqual(evidence["enforce_peace_token"][0]["name"], "enforce_peace")


if __name__ == "__main__":
    unittest.main()
