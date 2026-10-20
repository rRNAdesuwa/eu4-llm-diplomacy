"""Disk and synthetic counterexamples only; no process/native execution."""
import copy
import importlib.util
import json
from pathlib import Path
import struct
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("offered_fleet_static_trace", HERE / "trace.py")
trace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trace)


class StaticReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((HERE / "report.json").read_text(encoding="ascii"))
        cls.pe = trace.PE(trace.ROOT.parent / "eu4.exe")

    def test_complete_bounded_recomputation(self):
        self.assertEqual((HERE / "report.json").read_bytes(), trace.encoded(trace.make_report()))

    def test_every_instruction_and_fact_boundary_matches_exact_pe(self):
        unique = {}
        for function in self.report["functions"]:
            self.assertLessEqual(len(function["instructions"]), function["max_instructions"])
            for row in function["instructions"]:
                rva = int(row["rva"], 16)
                raw = bytes.fromhex(row["bytes"])
                self.assertEqual(self.pe.bytes_at(rva, len(raw)), raw)
                unique[row["rva"]] = row
        self.assertEqual(len(unique), 3973)
        for fact in self.report["facts"].values():
            self.assertIs(fact["runtime_verified"], False)
            self.assertTrue(set(fact["evidence_rvas"]).issubset(unique))

    def test_pointer_slots_distinguish_own_score_from_reverse_ask(self):
        slots = self.report["offered_fleet_vtable"]["slots"]
        self.assertEqual(slots["0x120"]["rva"], "0x534990")
        self.assertEqual(slots["0xc8"]["rva"], "0x534be0")
        self.assertNotEqual(slots["0x120"], slots["0xc8"])
        for offset, row in slots.items():
            actual = struct.unpack("<Q", self.pe.bytes_at(0x1c7f1f0 + int(offset, 16), 8))[0]
            self.assertEqual(actual - self.pe.base, int(row["rva"], 16))

    def test_score_flag_alone_is_insufficient_and_false_is_not_flag_zero(self):
        self.assertEqual(trace.predicted_score(0, 122, 122), -1000)
        self.assertEqual(trace.predicted_score(1, 122, 122), 99999)
        self.assertEqual(trace.predicted_score(1, 122, 189), -1000)
        self.assertEqual(trace.predicted_score(255, 122, 122), 99999)
        for args in ((False, 122, 122), (1, 122.0, 122), (256, 122, 122), (1, -1, 122)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                trace.predicted_score(*args)

    def test_empty_argument_vector_is_not_a_zero_length_arbitrary_span(self):
        good = {"begin": 0, "end": 0, "capacity": 0}
        trace.require_canonical_empty_vector(good)
        bad = [dict(begin=4096, end=4096, capacity=4096),
               dict(begin=4096, end=0, capacity=0), dict(begin=0, end=32, capacity=32),
               dict(begin=0, end=0, capacity=4096), dict(begin=False, end=0, capacity=0),
               dict(begin=0.0, end=0, capacity=0), {}, (0, 0, 0),
               dict(begin=0, end=0, capacity=0, command="yesman")]
        for val in bad:
            with self.subTest(value=val), self.assertRaises(ValueError):
                trace.require_canonical_empty_vector(val)

    def test_zero_args_abi_and_normal_cleanup_are_distinct(self):
        facts = self.report["facts"]
        abi = facts["normal_zero_argument_abi"]
        self.assertEqual(abi["result"]["size_bytes"], 40)
        self.assertEqual(abi["arguments"]["size_bytes"], 24)
        self.assertEqual(abi["result"]["message_offset"], 8)
        self.assertEqual(facts["normal_result_ownership"]["normal_message_destructor_rva"], "0x95660")
        self.assertIs(facts["normal_result_ownership"]["delete_result_storage"], False)
        self.assertIs(facts["handler_side_effect_and_result"]["write_precedes_message_allocation"], True)
        self.assertIs(facts["exception_boundary"]["retry_allowed"], False)
        self.assertIs(facts["exception_boundary"]["seh_recovery_verified"], False)

    def test_shared_message_key_does_not_classify_reply_or_invert_roles(self):
        facts = self.report["facts"]
        self.assertIs(facts["rejection_and_message"]["key_is_rejection_specific"], False)
        self.assertEqual(facts["accepted_effect_direction"]["holder"], "target")
        self.assertEqual(facts["accepted_effect_direction"]["grantor"], "actor")
        self.assertEqual(facts["reply_transition"]["rejection_state"], 1)
        self.assertEqual(facts["reply_transition"]["acceptance_state"], 2)

    def test_duplicate_registration_rows_are_both_bound_to_actual_handler(self):
        registration = self.report["console_registration"]
        self.assertEqual(registration["row_stride"], 160)
        self.assertEqual(registration["row_count"], 378)
        self.assertEqual(len(registration["yesman_rows"]), 2)
        for row in registration["yesman_rows"]:
            self.assertEqual(row["handler_rva"], "0xe50180")
            self.assertEqual(self.pe.bytes_at(int(row["row_rva"], 16), 160).hex(), row["row_bytes"])

    def test_no_runtime_or_production_promotion(self):
        for key in ("runtime_verified", "production_ready", "process_accessed", "native_called", "control_implemented"):
            self.assertIs(self.report[key], False)
        self.assertIsNone(self.report["facts"]["yesman_score_branch"]["current_runtime_value"])
        self.assertIs(self.report["facts"]["dispatcher_guards_not_production_sp"]["strict_single_player_proven"], False)


if __name__ == "__main__":
    unittest.main()
