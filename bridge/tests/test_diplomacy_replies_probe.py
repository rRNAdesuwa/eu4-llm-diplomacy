"""Synthetic byte-memory and saved-report fixtures only; no process/native use."""
from copy import deepcopy
import struct
import unittest
from unittest.mock import patch

from bridge.tests.test_diplomacy_current_probe import FixtureMemory
from work import probe_diplomacy_replies_1375 as probe

BASE, DB, GAME, ARRAY = 0x140000000, 0x100000, 0x200000, 0x300000
SERVER, UI, MANAGER = 0x500000, 0x510000, 0x520000
NODE, MESSAGE, OWNER, DEFINITION, HEAP = 0x600000, 0x700000, 0x800000, 0x900000, 0xA00000
DATE = 56463336


def fixture(messages=(), *, date=DATE, unknown=False, removed=False):
    memory = FixtureMemory()
    put = memory.write_fixture
    put(BASE + probe.base.DATABASE_POINTER_RVA, DB)
    put(BASE + probe.base.GAME_POINTER_RVA, GAME)
    put(DB + 0x118, ARRAY)
    put(GAME + 0x1DD0, date, 4)
    put(GAME + 0x1E60, probe.HANDLES["FRA"])
    for index, (tag, handle) in enumerate(probe.HANDLES.items()):
        country = 0x400000 + index * 0x10000
        put(ARRAY + ((handle >> 32) & 0xFFFF) * 8, country)
        put(country + 0x20, handle)
    for rva, value in probe.PINS.items(): put(BASE + rva, bytes.fromhex(value))
    put(GAME + 0x1E00, SERVER)
    put(SERVER, BASE + probe.SERVER_VTABLE)
    put(BASE + probe.SERVER_VTABLE + 0x228, BASE + 0x80E670)
    put(SERVER + 0x1178, UI)
    put(SERVER + 0x12D0, MANAGER)
    count = len(messages)
    put(MANAGER + 0x10, struct.pack("<QQIB", NODE if count else 0, NODE + (count - 1) * 0x100 if count else 0, count, 0))
    for index, (key, target, msgdate) in enumerate(messages):
        node, message, owner = NODE + index * 0x100, MESSAGE + index * 0x100, OWNER + index * 0x100
        previous, following = (node - 0x100 if index else 0), (node + 0x100 if index + 1 < count else 0)
        put(node, struct.pack("<QQQQB", 0x123 if removed else message, 0x456 if removed else owner, previous, following, int(removed)))
        if removed: continue  # Deliberately no memory for dangling message/owner.
        put(message, BASE + (0x111110 if unknown else probe.MESSAGE_VTABLES[index % 2]))
        if unknown: continue  # Deliberately no fields beyond vtable.
        put(message + 0x28, struct.pack("<QQ", probe.HANDLES["FRA"], probe.HANDLES[target]))
        definition, heap = DEFINITION + index * 0x100, HEAP + index * 0x100
        put(message + 8, definition)
        put(message + 0x88, msgdate, 4)
        header = bytearray(32)
        encoded = key.encode("ascii")
        if len(encoded) < 16:
            header[:len(encoded)] = encoded
            capacity = 15
        else:
            struct.pack_into("<Q", header, 0, heap)
            capacity = 31
            put(heap, encoded + b"\0")
        struct.pack_into("<QQ", header, 0x10, len(encoded), capacity)
        put(definition + 0x38, header)
    return memory


def report(memory, *, after=False):
    stamp = "2026-10-08T12:00:01+00:00" if after else "2026-10-08T12:00:00+00:00"
    return {"schema_version": 1, "kind": "diplomatic_reply_snapshot", "profile": probe.PROFILE,
            "static_evidence_sha256": probe.EVIDENCE_SHA256, "read_only": True, "targets": ["ENG", "POR"],
            "build": {"sha256": probe.base.LOCAL_SHA256}, "capture_started_at": stamp, "capture_finished_at": stamp,
            "source": {"kind": "live_process", "pid": 123, "process_creation_filetime": 134358500000000000,
                       "process_exit_filetime": 0, "module_base": hex(BASE), "access_rights": "QUERY_INFORMATION | VM_READ",
                       "verified_executable_path": "D:\\Games\\eu4.exe"},
            "observation": probe.capture(memory, BASE, ["ENG", "POR"])}


class ReplyProbeTests(unittest.TestCase):
    def test_all_reply_keys_both_pairs_and_no_applied_claim(self):
        for key, (action, outcome) in probe.KEYS.items():
            for target in ("ENG", "POR"):
                with self.subTest(key=key, target=target):
                    before = report(fixture())
                    after = report(fixture([(key, target, DATE)]), after=True)
                    result = probe.compare_reports(before, after, action)
                    self.assertEqual(result["status"], "reply_notifications_correlated", result)
                    self.assertEqual(result["correlated_messages"][0]["outcome"], outcome)
                    self.assertFalse(result["applied_verified"])
                    self.assertFalse(result["request_id_causality_verified"])

    def test_absent_notifications_remain_unknown(self):
        result = probe.compare_reports(report(fixture()), report(fixture(), after=True))
        self.assertEqual(result["status"], "unknown")
        self.assertFalse(result["rejected_correlated"])
        self.assertFalse(result["accepted_correlated"])

    def test_existing_and_reused_node_message_owner_not_new(self):
        before = report(fixture([("ROYMARACCEPT", "ENG", DATE)]))
        for field in (None, "address", "message_pointer", "shared_owner"):
            after = report(fixture([("ROYMARREJECT", "ENG", DATE)]), after=True)
            # Alter only one pointer: either node, message or owner is still old.
            if field:
                for sample in after["observation"]["passes"]:
                    node = sample["history"]["nodes"][0]
                    node[field] = hex(int(node[field], 16) + 0x200)
                    if field == "address": sample["history"]["head"] = sample["history"]["tail"] = node[field]
                after["observation"]["state"] = probe.inspect_sample(after["observation"]["passes"][0])
            self.assertEqual(probe.compare_reports(before, after)["status"], "unknown")

    def test_message_before_baseline_is_not_correlated(self):
        after = report(fixture([("ROYMARREJECT", "ENG", DATE - 24)]), after=True)
        self.assertEqual(probe.compare_reports(report(fixture()), after)["status"], "unknown")

    def test_future_message_date_refuses_sample(self):
        value = report(fixture([("VASALLACCEPT", "POR", DATE + 24)]))
        self.assertEqual(value["observation"]["status"], "unknown")

    def test_removed_dangling_message_is_never_read(self):
        value = report(fixture([("ROYMARREJECT", "ENG", DATE)], removed=True))
        self.assertEqual(value["observation"]["status"], "consistent_bounded_observation", value)
        self.assertEqual(value["observation"]["state"]["matches"], [])

    def test_unknown_vtable_reads_no_unverified_fields(self):
        value = report(fixture([("ROYMARREJECT", "ENG", DATE)], unknown=True))
        self.assertEqual(value["observation"]["status"], "consistent_bounded_observation", value)
        self.assertEqual(value["observation"]["state"]["unknown_vtable_nodes"], 1)

    def test_reverse_direction_not_selected(self):
        memory = fixture([("ROYMARREJECT", "ENG", DATE)])
        memory.write_fixture(MESSAGE + 0x28, struct.pack("<QQ", probe.HANDLES["ENG"], probe.HANDLES["FRA"]))
        self.assertEqual(report(memory)["observation"]["state"]["matches"], [])

    def test_total_bound_includes_removed_nodes(self):
        memory = fixture()
        memory.write_fixture(MANAGER + 0x20, 513, 4)
        value = report(memory)
        self.assertEqual(value["observation"]["status"], "unknown")
        self.assertTrue(any("512" in e for e in value["observation"]["errors"]))

    def test_exact_total_bound_removed_nodes_does_not_read_dangling_payloads(self):
        memory = fixture([("ROYMARREJECT", "ENG", DATE)] * 512, removed=True)
        value = report(memory)
        self.assertEqual(value["observation"]["status"], "consistent_bounded_observation", value)
        self.assertEqual(len(value["observation"]["passes"][0]["history"]["nodes"]), 512)
        self.assertEqual(probe.validated_report(value)[1]["matches"], [])

    def test_more_than_200_active_refuses_even_below_total_bound(self):
        memory = fixture([("ROYMARREJECT", "ENG", DATE)] * 201)
        value = report(memory)
        self.assertEqual(value["observation"]["status"], "unknown")
        self.assertTrue(any("200" in e for e in value["observation"]["errors"]))

    def test_cycle_previous_tail_and_iteration_rejected(self):
        for addr, value, size in ((NODE + 0x18, NODE, 8), (NODE + 0x10, NODE, 8),
                                  (MANAGER + 0x18, NODE + 0x100, 8), (MANAGER + 0x24, 1, 1)):
            memory = fixture([("ROYMARACCEPT", "POR", DATE)])
            memory.write_fixture(addr, value, size)
            self.assertEqual(report(memory)["observation"]["status"], "unknown")

    def test_key_bounds_and_null_ascii(self):
        changes = [(DEFINITION + 0x38 + 0x10, 97, 8), (DEFINITION + 0x38 + 0x18, 4097, 8),
                   (DEFINITION + 0x38 + 12, 65, 1), (DEFINITION + 0x38, 255, 1)]
        for location, value, size in changes:
            memory = fixture([("ROYMARREJECT", "ENG", DATE)])
            memory.write_fixture(location, value, size)
            self.assertEqual(report(memory)["observation"]["status"], "unknown")

    def test_two_pass_mismatch_is_unknown(self):
        first = probe.sample_once(fixture(), BASE, ["ENG", "POR"])
        second = probe.sample_once(fixture([("ROYMARACCEPT", "ENG", DATE)]), BASE, ["ENG", "POR"])
        with patch.object(probe, "sample_once", side_effect=[first, second]):
            self.assertEqual(probe.capture(None, BASE, ["ENG", "POR"])["status"], "unknown")

    def test_module_pin_and_current_full_handle_rejected(self):
        for location, value, size in ((BASE + 0x80E670, 0x90, 1), (SERVER, BASE + 0x100, 8),
                                      (GAME + 0x1E60, probe.HANDLES["POR"], 8)):
            memory = fixture()
            memory.write_fixture(location, value, size)
            self.assertEqual(report(memory)["observation"]["status"], "unknown")

    def test_report_tampering_identity_and_times_refused(self):
        before = report(fixture())
        good = report(fixture([("VASALLREJECT", "POR", DATE)]), after=True)
        mutations = [lambda r: r["build"].update(sha256="0" * 64),
                     lambda r: r["build"].update(sha256=123),
                     lambda r: r["source"].update(process_creation_filetime=5),
                     lambda r: r.update(capture_started_at=before["capture_started_at"], capture_finished_at=before["capture_finished_at"]),
                     lambda r: r["observation"]["state"].update(matches=[])]
        for mutation in mutations:
            after = deepcopy(good)
            mutation(after)
            result = probe.compare_reports(before, after)
            self.assertEqual(result["status"], "unknown")
            self.assertTrue(result["errors"])

    def test_history_unavailable_does_not_imply_rejection(self):
        memory = fixture()
        memory.write_fixture(SERVER + 0x12D0, 0)
        before = report(memory)
        after = deepcopy(before)
        after["capture_started_at"] = after["capture_finished_at"] = "2026-10-08T12:00:01+00:00"
        result = probe.compare_reports(before, after)
        self.assertEqual(result["status"], "unknown")
        self.assertFalse(result["rejected_correlated"])


if __name__ == "__main__": unittest.main()
