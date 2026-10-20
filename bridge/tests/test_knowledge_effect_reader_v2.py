"""Allocation and type counterexamples to R1; synthetic bytes only."""
import struct
import unittest
from unittest.mock import patch

from bridge import knowledge_effect_reader_v2 as reader
from bridge.tests.test_knowledge_effect_reader import (graph as r1_graph, receipt,
    BASE, FRA, JOL, FRA_ADDRESS, JOL_ADDRESS, LEFT_ARRAY, IDENTITY)


def graph(active=True):
    memory = r1_graph(active)
    for address, offset in ((FRA_ADDRESS, 0x2D0), (JOL_ADDRESS, 0x2B8)):
        memory.q(address+0x14F8+offset, BASE+reader.INDEX_VT)
    return memory


def capture(memory, action="knowledge_sharing"):
    actor, target = (JOL, FRA) if action == "ask_knowledge_sharing" else (FRA, JOL)
    return reader.read_knowledge_pair(memory, BASE, action, actor, target, IDENTITY)


class TypedIndexGuardTests(unittest.TestCase):
    def test_active_and_absent_have_typed_allocation_evidence(self):
        for active, expected in ((True, "active_pair_observed"), (False, "pair_absent_observed")):
            with self.subTest(active=active):
                value = capture(graph(active))
                self.assertEqual(value["status"], expected)
                self.assertTrue(value["snapshot"]["typed_index_allocation_guards_verified"])
                for index in value["snapshot"]["indexes"].values():
                    self.assertEqual(index["vtable_rva"], "0x1c3a538")
                    self.assertEqual(index["capacity_signed"], int(active))

    def test_used_over_capacity_is_unknown_before_payload_read(self):
        memory = graph()
        memory.i(FRA_ADDRESS+0x14F8+0x2D0+0x10, 0)
        result = capture(memory)
        self.assertEqual(result["status"], "unknown")
        self.assertNotIn((LEFT_ARRAY, 16), memory.reads)
        self.assertIn("count/capacity", result["failure"]["message"])

    def test_wrong_vtable_is_unknown_even_for_empty_pair(self):
        memory = graph(False)
        memory.q(JOL_ADDRESS+0x14F8+0x2B8, BASE+reader.INDEX_VT+8)
        self.assertEqual(capture(memory)["status"], "unknown")

    def test_negative_or_excess_capacity_is_unknown(self):
        for capacity in (-1, 4097):
            with self.subTest(capacity=capacity):
                memory = graph(False)
                memory.i(FRA_ADDRESS+0x14F8+0x2D0+0x10, capacity)
                self.assertEqual(capture(memory)["status"], "unknown")

    def test_allocation_pointer_capacity_mismatch_and_overflow_are_unknown(self):
        for array, capacity in ((0, 1), (LEFT_ARRAY, 0), (2**47-8, 1)):
            with self.subTest(array=array, capacity=capacity):
                memory = graph(False)
                memory.put(FRA_ADDRESS+0x14F8+0x2D0+8, struct.pack("<Qii", array, capacity, 0))
                self.assertEqual(capture(memory)["status"], "unknown")

    def test_empty_index_with_retained_valid_allocation_remains_absent(self):
        memory = graph(False)
        memory.put(FRA_ADDRESS+0x14F8+0x2D0+8, struct.pack("<Qii", LEFT_ARRAY, 8, 0))
        self.assertEqual(capture(memory)["status"], "pair_absent_observed")
        self.assertNotIn((LEFT_ARRAY, 16), memory.reads)

    def test_new_exact_task_still_requires_full_receipt_and_roles(self):
        for action in reader.ACTIONS:
            with self.subTest(action=action):
                result = reader.evaluate_knowledge_effect(action, capture(graph(False), action), capture(graph(), action), receipt(action))
                self.assertTrue(result["selected_effect_verified"])
                self.assertFalse(result["institution_completion_verified"])
                self.assertFalse(result["native_known_cleanup_complete"])

    def test_old_reader_evidence_without_allocation_guard_cannot_pass(self):
        from bridge import knowledge_effect_reader as old
        before = old.read_knowledge_pair(r1_graph(False), BASE, "knowledge_sharing", FRA, JOL, IDENTITY)
        result = reader.evaluate_knowledge_effect("knowledge_sharing", before, capture(graph()), receipt())
        self.assertEqual(result["status"], "unknown")

    def test_v2_manifest_is_file_only(self):
        with patch.object(reader, "read_knowledge_pair", side_effect=AssertionError("No capture permitted")):
            self.assertIn("bridge/knowledge_effect_reader_v2.py", reader.verify_manifest())


if __name__ == "__main__":
    unittest.main()
