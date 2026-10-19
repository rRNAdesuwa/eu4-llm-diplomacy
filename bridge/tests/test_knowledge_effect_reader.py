"""Synthetic memory graphs only; no real process or game operation."""
from copy import deepcopy
import json
import struct
import unittest
from unittest.mock import patch

from bridge import knowledge_effect_reader as reader

BASE, GAME, DB, ARRAY, SERVER, PAUSE = 0x140000000, 0x1000000, 0x1100000, 0x1200000, 0x1300000, 0x1400000
FRA, JOL = 0x0100007A00415246, 0x010000D2004C4F4A
FRA_ADDRESS, JOL_ADDRESS = 0x2000000, 0x2100000
PVECTOR, RVECTOR, BUCKETS, NODE, TASK = 0x3000000, 0x3100000, 0x4000000, 0x6000000, 0x7000000
LEFT_ARRAY, RIGHT_ARRAY = 0x8000000, 0x8100000
NOW = 56461512
IDENTITY = {"pid": 1234, "creation": "1"*16, "session": "2"*32, "dll_sha256": "3"*64, "manifest_sha256": "4"*64}


class Memory:
    def __init__(self):
        self.data = {}
        self.reads = []
        self.hook = None

    def put(self, address, raw):
        self.data.update({address+i: value for i, value in enumerate(raw)})

    def q(self, address, value):
        self.put(address, struct.pack("<Q", value))

    def i(self, address, value):
        self.put(address, struct.pack("<i", value))

    def read(self, address, size):
        self.reads.append((address, size))
        if self.hook:
            self.hook(self, address, size)
        try:
            return bytes(self.data[address+i] for i in range(size))
        except KeyError as exc:
            raise OSError(f"Synthetic unreadable address {address:#x}/{size}") from exc


def graph(active=True):
    m = Memory()
    m.q(BASE+0x233FE78, GAME)
    m.q(BASE+0x233D8D0, DB)
    m.q(GAME, BASE+0x1CB00C8)
    m.q(DB+0x118, ARRAY)
    m.put(DB+0x120, struct.pack("<ii", 1380, 1380))
    m.q(GAME+0x1E00, SERVER)
    m.q(SERVER, BASE+0x1CB8460)
    m.q(SERVER+0x418, PAUSE)
    m.q(PAUSE+0x50, SERVER)
    m.put(PAUSE+0x48, b"\1")
    m.i(GAME+0x1DD0, NOW)
    m.q(GAME+0x1E60, FRA)
    m.q(GAME+0x1E68, 0x2D2D2D)
    for offset in (0x7485, 0x2521, 0x24D0): m.put(GAME+offset, b"\0")
    m.q(GAME+0x74C8, 0)
    for handle, address in ((FRA, FRA_ADDRESS), (JOL, JOL_ADDRESS)):
        slot = (handle>>32)&65535
        m.q(ARRAY+slot*8, address)
        raw = bytearray(0x28)
        struct.pack_into("<QI", raw, 0, BASE+0x1C574A0, 357)
        struct.pack_into("<Q", raw, 0x20, handle)
        m.put(address, raw)
    for address, own, other, vector in ((FRA_ADDRESS, FRA, JOL, PVECTOR), (JOL_ADDRESS, JOL, FRA, RVECTOR)):
        root = address+0x14F8
        raw = bytearray(0x30)
        struct.pack_into("<QI", raw, 0, BASE+0x1C4F5F8, 357)
        struct.pack_into("<Q", raw, 0x10, address)
        struct.pack_into("<QQQ", raw, 0x18, vector, vector+1380*0x48, vector+1380*0x48)
        m.put(root, raw)
        record = bytearray(0x48)
        struct.pack_into("<QQQ", record, 0, root, own, other)
        m.put(vector+((other>>32)&65535)*0x48, record)
    for address, offset, array, counterpart in ((FRA_ADDRESS, 0x2D0, LEFT_ARRAY, JOL), (JOL_ADDRESS, 0x2B8, RIGHT_ARRAY, FRA)):
        raw = bytearray(24)
        struct.pack_into("<Qii", raw, 8, array if active else 0, int(active), int(active))
        m.put(address+0x14F8+offset, raw)
        if active: m.put(array, struct.pack("<i4xQ", (counterpart>>32)&65535, TASK))
    m.put(GAME+0x1BB8+0x10, struct.pack("<QQ", BUCKETS, BUCKETS+1380*24))
    m.put(BUCKETS+122*24, struct.pack("<QQIB", NODE if active else 0, NODE if active else 0, int(active), 0))
    if active:
        m.put(NODE, struct.pack("<QQQB", TASK, 0, 0, 0))
        raw = bytearray(0x48)
        struct.pack_into("<QI", raw, 0, BASE+reader.TASK_VT, 357)
        struct.pack_into("<QQii", raw, 0x10, FRA, JOL, NOW, NOW+8760)
        struct.pack_into("<i", raw, 0x38, -1)
        m.put(TASK, raw)
    m.q(BASE+reader.TASK_VT+0x40, BASE+0xA70470)
    m.q(BASE+reader.TASK_VT+0x48, BASE+0x529FA0)
    m.put(BASE+0x529FA0, bytes.fromhex("b876370000c3"))
    m.put(BASE+0xA70470, bytes.fromhex("488b0501fa8c018b90d01d00003951240f9ec0c3"))
    return m


def capture(memory, action="knowledge_sharing"):
    actor, target = (JOL, FRA) if action == "ask_knowledge_sharing" else (FRA, JOL)
    return reader.read_knowledge_pair(memory, BASE, action, actor, target, IDENTITY)


def receipt(action="knowledge_sharing"):
    actor, target = (JOL, FRA) if action == "ask_knowledge_sharing" else (FRA, JOL)
    return {"identity": deepcopy(IDENTITY), "state": "dispatched",
        "command": {"action": action, "actor": "JOL" if actor == JOL else "FRA", "target": "FRA" if target == FRA else "JOL"},
        "binding": {"actor_handle": actor, "target_handle": target},
        "native_result": {"status": 4, "submitted": True, "slot_consumed": True, "ownership_closed": True,
            "owned_live": 0, "quarantined": 0, "adapter_fault": 0, "submit_exception": 0, "known_cleanup_complete": False}}


class KnowledgeReaderTests(unittest.TestCase):
    def test_offer_exact_pair_requires_bilateral_indexes_global_node_and_typed_header(self):
        result = capture(graph())
        self.assertEqual(result["status"], "active_pair_observed")
        self.assertTrue(result["exact_pair_active_verified"])
        self.assertEqual(result["snapshot"]["object"]["provider_handle"], hex(FRA))
        self.assertEqual(result["snapshot"]["object"]["recipient_handle"], hex(JOL))
        self.assertFalse(result["institution_completion_verified"])

    def test_ask_reverses_original_actor_and_target_roles(self):
        result = capture(graph(), "ask_knowledge_sharing")
        self.assertEqual(result["status"], "active_pair_observed")
        self.assertEqual(result["snapshot"]["pair"]["actor_tag"], "JOL")
        self.assertEqual(result["snapshot"]["provider"]["tag"], "FRA")

    def test_absent_pair_requires_both_indexes_and_global_absence(self):
        result = capture(graph(False))
        self.assertEqual(result["status"], "pair_absent_observed")
        self.assertFalse(result["exact_pair_active_verified"])

    def test_nonzero_totals_for_other_pair_cannot_prove_selected_pair(self):
        m = graph(False)
        for address, offset, array in ((FRA_ADDRESS, 0x2D0, LEFT_ARRAY), (JOL_ADDRESS, 0x2B8, RIGHT_ARRAY)):
            m.put(address+0x14F8+offset+8, struct.pack("<Qii", array, 1, 1))
            m.put(array, struct.pack("<i4xQ", 300, TASK+0x1000))
        result = capture(m)
        self.assertEqual(result["status"], "pair_absent_observed")
        self.assertFalse(result["snapshot"]["aggregate_counts_used_as_pair_proof"])

    def test_one_sided_or_disagreeing_indexes_are_unknown(self):
        for missing in (True, False):
            with self.subTest(missing=missing):
                m = graph()
                if missing: m.i(JOL_ADDRESS+0x14F8+0x2B8+0x14, 0)
                else: m.q(RIGHT_ARRAY+8, TASK+0x1000)
                self.assertEqual(capture(m)["status"], "unknown")

    def test_indexed_pair_without_global_membership_is_unknown(self):
        m = graph()
        m.put(BUCKETS+122*24, struct.pack("<QQIB", 0, 0, 0, 0))
        self.assertEqual(capture(m)["status"], "unknown")

    def test_global_pair_without_bilateral_indexes_is_unknown(self):
        m = graph()
        for address, offset in ((FRA_ADDRESS, 0x2D0), (JOL_ADDRESS, 0x2B8)):
            m.i(address+0x14F8+offset+0x14, 0)
        self.assertEqual(capture(m)["status"], "unknown")

    def test_wrong_type_or_marker_is_never_accepted(self):
        for offset, raw in ((0, struct.pack("<Q", BASE+reader.TASK_VT+8)), (8, struct.pack("<I", 358))):
            with self.subTest(offset=offset):
                m = graph()
                m.put(TASK+offset, raw)
                self.assertEqual(capture(m)["status"], "unknown")

    def test_complete_provider_generation_mismatch_is_unknown(self):
        m = graph()
        m.q(TASK+0x10, FRA+(1<<56))
        self.assertEqual(capture(m)["status"], "unknown")

    def test_endpoint_swap_cannot_match_original_direction(self):
        m = graph()
        m.put(TASK+0x10, struct.pack("<QQ", JOL, FRA))
        self.assertEqual(capture(m)["status"], "unknown")

    def test_removed_or_failed_object_is_not_active(self):
        for offset in (0x28, 0x29):
            with self.subTest(offset=offset):
                m = graph()
                m.put(TASK+offset, b"\1")
                self.assertEqual(capture(m)["status"], "unknown")

    def test_deadline_equal_now_is_expired_and_never_active(self):
        m = graph()
        m.i(TASK+0x24, NOW)
        result = capture(m)
        self.assertEqual(result["status"], "expired_pair_observed")
        self.assertFalse(result["exact_pair_active_verified"])

    def test_special_flag_has_unclosed_termination_context_and_stays_unknown(self):
        m = graph()
        m.put(TASK+0x40, b"\1")
        result = capture(m)
        self.assertEqual(result["status"], "unknown")
        self.assertTrue(result["snapshot"]["special_flag_40_termination_context_unresolved"])

    def test_global_node_limit_refuses_before_payload_traversal(self):
        m = graph()
        m.put(BUCKETS+122*24+16, struct.pack("<I", 513))
        self.assertEqual(capture(m)["status"], "unknown")
        self.assertTrue(all(address != NODE for address, _ in m.reads))

    def test_deleted_global_node_never_dereferences_payload(self):
        m = graph()
        m.put(NODE+0x18, b"\1")
        self.assertEqual(capture(m)["status"], "unknown")
        self.assertTrue(all(a != TASK for a, _ in m.reads))

    def test_unknown_global_type_reads_only_vtable(self):
        m = graph()
        m.q(TASK, BASE+0x123456)
        self.assertEqual(capture(m)["status"], "unknown")
        self.assertTrue(all(size == 8 for a, size in m.reads if a == TASK))

    def test_global_iteration_or_bad_links_are_unknown(self):
        for address, raw in ((BUCKETS+122*24+20, b"\1"), (NODE+8, struct.pack("<Q", NODE))):
            with self.subTest(address=address):
                m = graph()
                m.put(address, raw)
                self.assertEqual(capture(m)["status"], "unknown")

    def test_duplicate_index_slot_is_unknown(self):
        m = graph()
        m.i(FRA_ADDRESS+0x14F8+0x2D0+0x14, 2)
        m.put(LEFT_ARRAY+16, struct.pack("<i4xQ", 210, TASK+0x1000))
        self.assertEqual(capture(m)["status"], "unknown")

    def test_changed_state_across_two_passes_is_unknown(self):
        m = graph()
        reads = 0
        def mutate(port, address, size):
            nonlocal reads
            if address == TASK and size == 0x48:
                reads += 1
                if reads == 2: port.i(TASK+0x24, NOW+9000)
        m.hook = mutate
        self.assertEqual(capture(m)["status"], "unknown")

    def test_pause_and_typed_country_identity_are_guarded(self):
        for address, raw in ((PAUSE+0x48, b"\0"), (FRA_ADDRESS+0x20, struct.pack("<Q", JOL))):
            with self.subTest(address=address):
                m = graph()
                m.put(address, raw)
                self.assertEqual(capture(m)["status"], "unknown")

    def test_unavailable_memory_is_unknown_not_pair_absent(self):
        m = graph()
        del m.data[LEFT_ARRAY]
        result = capture(m)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["failure"]["type"], "OSError")


class KnowledgeTransitionTests(unittest.TestCase):
    def setUp(self):
        self.before, self.after = capture(graph(False)), capture(graph())

    def test_new_exact_active_pair_and_closed_dispatch_is_selected_effect(self):
        value = reader.evaluate_knowledge_effect("knowledge_sharing", self.before, self.after, receipt())
        self.assertEqual(value["status"], "observed")
        self.assertTrue(value["selected_effect_verified"])
        for key in ("AI_acceptance_verified", "exact_external_request_id_causality_verified", "institution_completion_verified", "cold_reload_verified"):
            self.assertFalse(value[key])
        self.assertFalse(value["native_known_cleanup_complete"])

    def test_ask_direction_uses_same_exact_provider_recipient_pair(self):
        before, after = capture(graph(False), "ask_knowledge_sharing"), capture(graph(), "ask_knowledge_sharing")
        value = reader.evaluate_knowledge_effect("ask_knowledge_sharing", before, after, receipt("ask_knowledge_sharing"))
        self.assertTrue(value["selected_effect_verified"])

    def test_existing_active_pair_is_not_new_request_effect(self):
        self.assertEqual(reader.evaluate_knowledge_effect("knowledge_sharing", self.after, self.after, receipt())["status"], "not_observed")

    def test_missing_baseline_or_unclosed_dispatch_is_unknown(self):
        self.assertEqual(reader.evaluate_knowledge_effect("knowledge_sharing", None, self.after, receipt())["status"], "unknown")
        bad = receipt()
        bad["native_result"]["ownership_closed"] = False
        self.assertEqual(reader.evaluate_knowledge_effect("knowledge_sharing", self.before, self.after, bad)["status"], "unknown")

    def test_wrong_receipt_binding_and_boolean_integer_are_refused(self):
        for key, value in (("binding", {"actor_handle": JOL, "target_handle": FRA}), ("native_result", {**receipt()["native_result"], "submitted": 1})):
            with self.subTest(key=key):
                bad = receipt()
                bad[key] = value
                self.assertEqual(reader.evaluate_knowledge_effect("knowledge_sharing", self.before, self.after, bad)["status"], "unknown")


class KnowledgeSourceTests(unittest.TestCase):
    def test_manifest_verifies_using_files_only(self):
        self.assertTrue(reader.verify_manifest())

    def test_changed_decoder_source_is_refused(self):
        actual = reader.read
        source = reader.ROOT / "bridge/knowledge_effect_reader.py"
        with patch.object(reader, "read", side_effect=lambda path, limit: b"changed" if path == source else actual(path, limit)):
            with self.assertRaisesRegex(ValueError, "Knowledge source/evidence changed"):
                reader.verify_manifest()

    def test_manifest_cannot_escape_workspace(self):
        actual = reader.read
        manifest = json.loads(actual(reader.SOURCE_MANIFEST, 65536))
        manifest["source_pins"] = {"../outside": {"bytes": 0, "sha256": "a"*64}}
        with patch.object(reader, "read", side_effect=lambda path, limit: json.dumps(manifest).encode() if path == reader.SOURCE_MANIFEST else actual(path, limit)):
            with self.assertRaisesRegex(ValueError, "Invalid knowledge source path"):
                reader.verify_manifest()


if __name__ == "__main__":
    unittest.main()
