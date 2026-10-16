"""Byte-layout tests for read-only observation; never open EU4 or publish.

The graph uses native embedded relation roots and both indexed views of one
dependency. Malformed fields corrupt that graph rather than mock a validator's
answer. RuntimeCapture's held-reader boundary is supplied only synthetic bytes.
"""
import contextlib
import copy
import ctypes
from pathlib import Path
import struct
import tempfile
import types
import unittest
from unittest.mock import patch

from bridge import diplomacy_effect_observer as observer


BASE = 0x140000000
GAME, DB, COUNTRIES = 0x100000, 0x200000, 0x210000
ACTOR, TARGET, SERVER, PAUSE = 0x300000, 0x400000, 0x500000, 0x510000
RECORDS_A, RECORDS_B = 0x600000, 0x620000
DEPS_A, DEPS_B, ANNEX, ANNEX_B = 0x700000, 0x710000, 0x720000, 0x730000
DEPENDENCY, DEFINITION, STRING = 0x800000, 0x810000, 0x820000
OTHER_DEPENDENCY, ANNEX_OBJECT = 0x830000, 0x840000
COUNT = 1380
DATE = 56468208


def handle(tag, slot, *, valid=1, kind=0):
    return int.from_bytes(tag.encode("ascii"), "little") | (slot << 32) | (kind << 48) | (valid << 56)


FRA, SCO = handle("FRA", 1), handle("SCO", 2)
IDENTITY = dict(pid=77, creation="0000000000000001", session="1"*32,
                dll_sha256="2"*64, manifest_sha256="3"*64)
COMMAND = dict(request_id="memory-observer-1", actor="FRA", target="SCO", action="trade_favors_for_trust")


class Memory:
    """Mapped byte ranges with exact short-read/fault and mutation injection."""
    def __init__(self):
        self.regions = []
        self.reads = []
        self.hook = None
        self.short = set()

    def map(self, address, size):
        assert not any(address < start+len(data) and start < address+size for start, data in self.regions)
        self.regions.append((address, bytearray(size)))

    def raw(self, address, data):
        for start, region in self.regions:
            if start <= address and address+len(data) <= start+len(region):
                region[address-start:address-start+len(data)] = data
                return
        raise AssertionError(f"Unmapped fixture write {address:#x}")

    def put(self, address, fmt, *values):
        self.raw(address, struct.pack("<"+fmt, *values))

    def read(self, address, size):
        self.reads.append((address, size))
        if self.hook:
            self.hook(self, address, size)
        for start, region in self.regions:
            if start <= address and address+size <= start+len(region):
                value = bytes(region[address-start:address-start+size])
                return value[:-1] if address in self.short else value
        raise OSError(f"Synthetic unmapped read {address:#x}/{size}")


def graph():
    m = Memory()
    for address, size in ((BASE+0x233FE78, 8), (BASE+0x233D8D0, 8),
                          (GAME, 0x7518), (DB, 0x800), (COUNTRIES, COUNT*8),
                          (ACTOR, 0x9B78), (TARGET, 0x9B78), (SERVER, 0x1000), (PAUSE, 0x60),
                          (RECORDS_A, COUNT*0x48), (RECORDS_B, COUNT*0x48),
                          (DEPS_A, 64), (DEPS_B, 64), (ANNEX, 64), (ANNEX_B, 64),
                          (DEPENDENCY, 0x90), (OTHER_DEPENDENCY, 0x90), (ANNEX_OBJECT, 0x80),
                          (DEFINITION, 0x40), (STRING, 128)):
        m.map(address, size)
    m.put(BASE+0x233FE78, "Q", GAME)
    m.put(BASE+0x233D8D0, "Q", DB)
    m.put(GAME, "Q", BASE+0x1CB00C8)
    m.put(DB+0x118, "Qii", COUNTRIES, COUNT, COUNT)
    m.put(GAME+0x1DD0, "i", DATE)
    m.put(GAME+0x1E60, "Q", FRA)
    m.put(GAME+0x1E68, "Q", observer.SENTINEL)
    m.put(GAME+0x1E00, "Q", SERVER)
    m.put(SERVER, "Q", BASE+0x1CB8460)
    m.put(SERVER+0x418, "Q", PAUSE)
    m.put(PAUSE+0x50, "Q", SERVER)
    m.put(PAUSE+0x48, "B", 1)
    m.put(COUNTRIES+8, "Q", ACTOR)
    m.put(COUNTRIES+16, "Q", TARGET)
    for address, own, other, slot, records, deps in (
            (ACTOR, FRA, SCO, 2, RECORDS_A, DEPS_A),
            (TARGET, SCO, FRA, 1, RECORDS_B, DEPS_B)):
        m.put(address, "QI", BASE+0x1C574A0, 357)
        m.put(address+0x20, "Q", own)
        root = address+0x14F8
        m.put(root, "QI", BASE+0x1C4F5F8, 357)
        m.put(root+0x10, "Q", address)
        m.put(root+0x18, "QQQ", records, records+COUNT*0x48, records+COUNT*0x48)
        m.put(records+slot*0x48, "QQQ", root, own, other)
        m.put(records+slot*0x48+0x1E, "B", 25 if address == ACTOR else 67)
        m.put(records+slot*0x48+0x20, "i", 8000 if address == ACTOR else 9000)
        m.put(records+slot*0x48+0x30, "i", DATE-1)
        m.put(root+0x128, "Qii", deps, 4, 1)
        m.put(deps, "i4xQ", slot, DEPENDENCY)
        m.put(root+0x200, "Qii", 0, 0, 0)
        m.put(address+0x18F0, "Q", observer.SENTINEL if address == ACTOR else FRA)
        m.put(address+0x18F8, "Q", observer.SENTINEL)
        m.put(address+0xBB0, "i", 500000 if address == ACTOR else 300000)
        m.put(address+0xDB8, "i", 120000 if address == ACTOR else 80000)
        m.put(address+0xDC0, "i", 90000 if address == ACTOR else 60000)
        m.put(address+0x17DC, "i", 1 if address == ACTOR else 0)
        m.put(address+0x17C4, "i", 0 if address == ACTOR else 1)
    m.put(DEPENDENCY, "QI", BASE+0x1C81758, 357)
    m.put(DEPENDENCY+0x10, "QQ", FRA, SCO)
    m.put(DEPENDENCY+0x40, "Q", DEFINITION)
    m.raw(DEFINITION+0x10, b"vassal\0")
    m.put(DEFINITION+0x20, "QQ", 6, 15)
    m.put(TARGET+0x272C, "Q", observer.SENTINEL)
    m.put(TARGET+0x2728, "i", DATE-1)
    return m


def add_annex_task(m):
    """One native task reachable through both countries' embedded indexes."""
    m.put(ACTOR+0x14F8+0x200, "Qii", ANNEX, 4, 1)
    m.put(TARGET+0x14F8+0x200, "Qii", ANNEX_B, 4, 1)
    m.put(ANNEX, "i4xQ", 2, ANNEX_OBJECT)
    m.put(ANNEX_B, "i4xQ", 1, ANNEX_OBJECT)
    m.put(ANNEX_OBJECT, "QI", BASE+0x1CDE020, 357)
    m.put(ANNEX_OBJECT+0x10, "QQi", FRA, SCO, DATE-10)
    m.put(ANNEX_OBJECT+0x28, "H", 0x100)
    return m


def sample(m, command=None, handles=(FRA, SCO)):
    return observer.sample_pair(observer.BudgetReader(m), BASE, IDENTITY, command or COMMAND, handles)


class HeldMemory:
    def __init__(self, memory):
        self.graph = memory
        self.checks = 0
        self.header_calls = self.header_bytes = self.rpm_calls = 0
        self.handle = 123
        self.kernel = types.SimpleNamespace(ReadProcessMemory=self.read_process_memory)

    def memory(self, address, size):
        # The pinned readonly.Held.memory is a PE-header reader, not a bulk
        # observation port. Keep its real limits to catch wrong integration.
        if not 0 < size <= 8192 or self.header_calls >= 16 or self.header_bytes+size > 32768:
            raise ValueError("RO header budget")
        self.header_calls += 1
        self.header_bytes += size
        return self.graph.read(address, size)

    def read_process_memory(self, held_handle, address, buffer, size, actual):
        assert held_handle == self.handle
        self.rpm_calls += 1
        raw = self.graph.read(address.value, size)
        ctypes.memmove(buffer, raw, len(raw))
        ctypes.cast(actual, ctypes.POINTER(ctypes.c_size_t))[0] = len(raw)
        return True

    def identity_check(self):
        self.checks += 1

    def modules(self):
        return [(BASE, "synthetic/eu4.exe")]


def capture_for(m):
    capture = observer.RuntimeCapture(IDENTITY, backend=types.SimpleNamespace(actions=[COMMAND["action"]]))
    capture.held = HeldMemory(m)
    capture.base = BASE
    capture.modules = capture.held.modules()
    capture.initial_pins = {"synthetic-source": {"sha256": "1"*64, "bytes": 1}}
    return capture


def dispatched_status():
    return dict(command=COMMAND, identity=IDENTITY, state="dispatched", audit_sha256="a"*64,
                binding={"actor_handle": FRA, "target_handle": SCO},
                native_result=dict(status=4, submitted=True, slot_consumed=True, ownership_closed=True,
                                   owned_live=0, quarantined=0, adapter_fault=0, submit_exception=0))


class EffectObserverMemoryTests(unittest.TestCase):
    def setUp(self):
        # Accidental process construction or transport use fails the whole test.
        self.no_runtime = patch.object(observer, "WindowsRuntime", side_effect=AssertionError("No game access"))
        self.no_runtime.start()
        self.addCleanup(self.no_runtime.stop)

    def test_forward_and_reverse_byte_graph_preserve_direction(self):
        forward = sample(graph())
        self.assertEqual(forward["pair"]["dependency_type"], "vassal")
        self.assertEqual(forward["pair"]["target_overlord_handle"], hex(FRA))
        self.assertEqual(forward["incoming"], {"trust": 67, "favors": 9000})
        self.assertEqual(forward["actor"]["resources"]["treasury_milli"], 500000)
        reverse = sample(graph(), dict(COMMAND, actor="SCO", target="FRA"), (SCO, FRA))
        self.assertEqual(reverse["pair"]["actor_overlord_handle"], hex(FRA))
        self.assertEqual(reverse["pair"]["target_overlord_handle"], hex(observer.SENTINEL))
        self.assertEqual(reverse["incoming"], {"trust": 25, "favors": 8000})
        self.assertEqual(reverse["actor"]["resources"]["treasury_milli"], 300000)

    def test_valid_byte_kind_padding_and_signed_slot_are_checked(self):
        invalid = (handle("FRA", 1, valid=0, kind=1), handle("FRA", 1, kind=7),
                   handle("FRA", 0xFFFF), handle("FRA", COUNT), handle("FRA", 0), FRA | (1 << 24))
        for value in invalid:
            with self.subTest(handle=hex(value)), self.assertRaises(ValueError):
                sample(graph(), handles=(value, SCO))
        self.assertEqual(observer.full_handle(FRA, COUNT, tag="FRA"), (1, "FRA"))

    def test_complete_country_header_and_lookup_identity_reject(self):
        for address, fmt, value in ((ACTOR, "Q", BASE+0x1234), (ACTOR+8, "I", 0),
                                    (ACTOR+0x20, "Q", FRA+(1 << 56)), (COUNTRIES+8, "Q", TARGET)):
            with self.subTest(address=hex(address)):
                m = graph(); m.put(address, fmt, value)
                with self.assertRaises(ValueError): sample(m)

    def test_selector0_and_cache_load_reset_guards(self):
        for address, fmt, value in ((GAME+0x1E66, "B", 7), (GAME+0x2521, "B", 1),
                                    (GAME+0x7485, "B", 1), (GAME+0x74C8, "Q", DEFINITION),
                                    (GAME+0x24D0, "B", 1), (PAUSE+0x48, "B", 2)):
            with self.subTest(address=hex(address)):
                m = graph(); m.put(address, fmt, value)
                with self.assertRaises(ValueError): sample(m)

    def test_country_table_signed_bounds_server_and_pause_owner_reject(self):
        for address, fmt, value in ((DB+0x124, "i", -1), (DB+0x124, "i", COUNT-1),
                                    (DB+0x120, "i", COUNT-1), (DB+0x120, "i", 4097),
                                    (SERVER, "Q", BASE+0x1234), (PAUSE+0x50, "Q", TARGET),
                                    (GAME+0x1E68, "Q", SCO)):
            with self.subTest(address=hex(address), value=value):
                m = graph(); m.put(address, fmt, value)
                with self.assertRaises(ValueError): sample(m)

    def test_root_owner_and_complete_relation_record_must_match(self):
        record = RECORDS_A+2*0x48
        for address, value in ((ACTOR+0x14F8+0x10, TARGET), (record, TARGET+0x14F8),
                               (record+8, SCO), (record+0x10, SCO+(1 << 56))):
            with self.subTest(address=hex(address)):
                m = graph(); m.put(address, "Q", value)
                with self.assertRaises(ValueError): sample(m)

    def test_relation_root_type_and_vector_extent_are_validated(self):
        root = ACTOR+0x14F8
        for address, fmt, value in ((root, "Q", BASE+0x1234), (root+8, "I", 0),
                                    (root+0x20, "Q", RECORDS_A), (root+0x28, "Q", RECORDS_A+0x48)):
            with self.subTest(address=hex(address)):
                m = graph(); m.put(address, fmt, value)
                with self.assertRaises(ValueError): sample(m)

    def test_dependency_views_require_same_object_and_endpoints(self):
        for address, fmt, value in ((DEPS_B+8, "Q", OTHER_DEPENDENCY),
                                    (DEPENDENCY+0x10, "Q", SCO),
                                    (DEPENDENCY+0x18, "Q", SCO+(1 << 56)),
                                    (DEPENDENCY, "Q", BASE+0x1234), (DEPENDENCY+0x28, "B", 1)):
            with self.subTest(address=hex(address)):
                m = graph(); m.put(address, fmt, value)
                with self.assertRaises(ValueError): sample(m)

    def test_dependency_absence_requires_both_indexes_absent(self):
        m = graph()
        m.put(ACTOR+0x14F8+0x128, "Qii", 0, 0, 0)
        with self.assertRaisesRegex(ValueError, "Bilateral"): sample(m)
        m.put(TARGET+0x14F8+0x128, "Qii", 0, 0, 0)
        m.put(TARGET+0x18F0, "Q", observer.SENTINEL)
        result = sample(m)
        self.assertIs(result["pair"]["dependency_present"], False)
        self.assertIsNone(result["pair"]["dependency_type"])

    def test_retained_allocated_empty_indexes_are_not_false_members(self):
        m = graph()
        for address, data in ((ACTOR, DEPS_A), (TARGET, DEPS_B)):
            m.put(address+0x14F8+0x128, "Qii", data, 4, 0)
        result = sample(m)
        self.assertFalse(result["pair"]["dependency_present"])

    def test_empty_index_still_requires_canonical_consistent_storage(self):
        for data, capacity in ((0, 1), (2**47, 1), (DEPS_A, 0)):
            with self.subTest(data=data, capacity=capacity):
                m = graph()
                m.put(ACTOR+0x14F8+0x128, "Qii", data, capacity, 0)
                m.put(TARGET+0x14F8+0x128, "Qii", data, capacity, 0)
                with self.assertRaises(ValueError): sample(m)

    def test_signed_index_count_capacity_and_country_slots_reject(self):
        for capacity, used in ((4, -1), (-1, 0), (1, 2), (4097, 0), (300, 257)):
            with self.subTest(capacity=capacity, used=used):
                m = graph(); m.put(ACTOR+0x14F8+0x128, "Qii", DEPS_A, capacity, used)
                with self.assertRaises(ValueError): sample(m)
        for slot in (-1, 0, COUNT, 32768):
            with self.subTest(slot=slot):
                m = graph(); m.put(DEPS_A, "i", slot)
                with self.assertRaises(ValueError): sample(m)

    def test_duplicate_indexed_country_is_ambiguous(self):
        m = graph()
        m.put(ACTOR+0x14F8+0x128, "Qii", DEPS_A, 4, 2)
        m.put(DEPS_A+16, "i4xQ", 2, DEPENDENCY)
        with self.assertRaisesRegex(ValueError, "Duplicate"): sample(m)

    def test_indexed_null_or_noncanonical_object_is_not_absence(self):
        for value in (0, 2**47):
            with self.subTest(value=value):
                m = graph(); m.put(DEPS_A+8, "Q", value)
                with self.assertRaises(ValueError): sample(m)

    def test_annex_observation_has_typed_bilateral_task_not_completion(self):
        m = add_annex_task(graph())
        result = sample(m)
        self.assertEqual(result["pair"]["annex_index_count"], 1)
        self.assertTrue(result["pair"]["annex_target_member"])
        self.assertEqual(result["pair"]["annex_object_pointer"], hex(ANNEX_OBJECT))
        self.assertTrue(result["annex_task_object_type_proven"])
        self.assertEqual(result["annex_task"]["state"], "in_progress")
        self.assertEqual(result["annex_task"]["started_raw_date"], DATE-10)
        self.assertEqual(result["annex_task"]["raw_word_28"], 0x100)
        self.assertEqual(result["annex_task"]["removed_byte_28"], 0)
        self.assertFalse(result["annex_task"]["completion_proven"])
        self.assertFalse(result["knowledge"]["pair_object_identity_proven"])
        reverse = sample(m, {**COMMAND, "actor": "SCO", "target": "FRA"}, (SCO, FRA))
        self.assertEqual(reverse["annex_task"]["address"], hex(ANNEX_OBJECT))
        self.assertTrue(reverse["pair"]["annex_target_member"])

    def test_annex_task_type_endpoints_start_date_and_removal_byte_reject(self):
        for offset, fmt, value in ((0, "Q", BASE+0x1234), (8, "I", 0),
                                   (0x10, "Q", SCO), (0x18, "Q", SCO+(1 << 56)),
                                   (0x20, "i", -1), (0x20, "i", 0), (0x20, "i", DATE+1),
                                   (0x28, "B", 1), (0x28, "B", 255)):
            with self.subTest(offset=hex(offset), value=value):
                m = add_annex_task(graph()); m.put(ANNEX_OBJECT+offset, fmt, value)
                with self.assertRaises(ValueError): sample(m)

    def test_annex_task_requires_same_pointer_from_both_country_indexes(self):
        for address, fmt, values in ((TARGET+0x14F8+0x200, "Qii", (0, 0, 0)),
                                     (ANNEX_B+8, "Q", (OTHER_DEPENDENCY,))):
            with self.subTest(address=hex(address)):
                m = add_annex_task(graph()); m.put(address, fmt, *values)
                with self.assertRaisesRegex(ValueError, "Bilateral annexation"): sample(m)

    def test_annex_task_removal_does_not_follow_retained_object_or_prove_completion(self):
        m = add_annex_task(graph())
        self.assertTrue(sample(m)["annex_task_object_type_proven"])
        for address in (ACTOR, TARGET):
            m.put(address+0x14F8+0x200, "Qii", 0, 0, 0)
        m.put(ANNEX_OBJECT+0x28, "B", 1)
        m.reads.clear()
        result = sample(m)
        self.assertFalse(result["pair"]["annex_target_member"])
        self.assertFalse(result["annex_task_object_type_proven"])
        self.assertIsNone(result["annex_task"])
        self.assertFalse(any(ANNEX_OBJECT <= address < ANNEX_OBJECT+0x80 for address, _ in m.reads))

    def test_short_annex_task_read_is_unknown(self):
        m = add_annex_task(graph()); m.short.add(ANNEX_OBJECT)
        with self.assertRaisesRegex(ValueError, "Short memory read"): sample(m)

    def test_heap_definition_key_and_corrupt_terminator(self):
        m = graph(); text = b"trade_protectorate"
        m.put(DEFINITION+0x10, "Q", STRING)
        m.put(DEFINITION+0x20, "QQ", len(text), 31)
        m.raw(STRING, text+b"\0")
        self.assertEqual(sample(m)["pair"]["dependency_type"], "trade_protectorate")
        m.raw(STRING+len(text), b"x")
        with self.assertRaisesRegex(ValueError, "terminator"): sample(m)

    def test_short_native_record_or_index_read_is_unknown_not_absence(self):
        for address in (RECORDS_A+2*0x48, DEPS_A, DEPENDENCY):
            with self.subTest(address=hex(address)):
                m = graph(); m.short.add(address)
                with self.assertRaisesRegex(ValueError, "Short memory read"): sample(m)

    def test_changed_index_header_mid_read_rejects(self):
        m = graph(); field = ACTOR+0x14F8+0x128; seen = 0
        def change(memory, address, unused):
            nonlocal seen
            if address == field:
                seen += 1
                if seen == 2: memory.put(field+8, "i", 3)
        m.hook = change
        with self.assertRaisesRegex(ValueError, "header changed"): sample(m)

    def test_cache_guard_and_identity_changed_during_projection_reject(self):
        for address, fmt, value in ((GAME+0x2521, "B", 1), (GAME+0x1DD0, "i", DATE+1),
                                    (ACTOR+0x20, "Q", FRA+(1 << 56))):
            with self.subTest(address=hex(address)):
                m = graph()
                def change(memory, read_address, unused):
                    if read_address == ACTOR+0xBB0: memory.put(address, fmt, value)
                m.hook = change
                with self.assertRaises(ValueError): sample(m)

    def test_two_pass_capture_has_external_only_evidence(self):
        capture = capture_for(graph())
        with patch.object(observer, "pins", return_value=copy.deepcopy(capture.initial_pins)):
            result = capture.capture(COMMAND, {"actor_handle": FRA, "target_handle": SCO})
        self.assertTrue(result["two_pass_equal"])
        self.assertFalse(result["atomic_main_thread_snapshot"])
        self.assertFalse(result["world_epoch_proven"])
        self.assertEqual((result["native_calls"], result["requests_published"]), (0, 0))
        self.assertLess(result["rpm_budget"]["bytes"], observer.LIMITS["bytes"])
        self.assertEqual(capture.held.header_calls, 0, "Bulk observation must preserve the frozen header-reader budget")
        self.assertGreater(capture.held.rpm_calls, 16)

    def test_default_tag_resolution_scans_real_table_and_rejects_duplicates(self):
        m = graph(); capture = capture_for(m)
        with patch.object(observer, "pins", return_value=copy.deepcopy(capture.initial_pins)):
            result = capture.capture(COMMAND)
            self.assertEqual(result["snapshot"]["pair"]["actor_handle"], hex(FRA))
            self.assertEqual(result["snapshot"]["pair"]["target_handle"], hex(SCO))
            m.put(COUNTRIES+24, "Q", ACTOR)
            with self.assertRaisesRegex(ValueError, "Duplicate selected TAG"):
                capture.capture(COMMAND)

    def test_runtime_rpm_port_rejects_short_actual_byte_count(self):
        m = graph(); m.short.add(RECORDS_A+2*0x48)
        capture = capture_for(m)
        with self.assertRaisesRegex(ValueError, "Exact VM_READ unavailable"):
            capture.capture(COMMAND, {"actor_handle": FRA, "target_handle": SCO})
        self.assertEqual(capture.held.header_calls, 0)

    def test_changed_observer_source_or_process_identity_rejects_capture(self):
        capture = capture_for(graph())
        with patch.object(observer, "pins", return_value={}):
            with self.assertRaisesRegex(ValueError, "evidence/source changed"):
                capture.capture(COMMAND, {"actor_handle": FRA, "target_handle": SCO})
        def replaced_process():
            raise ValueError("Synthetic process creation changed")
        capture.held.identity_check = replaced_process
        with self.assertRaisesRegex(ValueError, "creation changed"):
            capture.capture(COMMAND, {"actor_handle": FRA, "target_handle": SCO})

    def test_two_pass_capture_rejects_projection_change_with_stable_roots(self):
        m = graph(); seen = 0
        def change(memory, address, unused):
            nonlocal seen
            if address == ACTOR+0xBB0:
                seen += 1
                if seen == 2: memory.put(address, "i", 500001)
        m.hook = change; capture = capture_for(m)
        with patch.object(observer, "pins", return_value=copy.deepcopy(capture.initial_pins)):
            with self.assertRaisesRegex(ValueError, "Two selected state passes differ"):
                capture.capture(COMMAND, {"actor_handle": FRA, "target_handle": SCO})

    def test_budget_reader_refuses_unbounded_and_short_reads(self):
        m = graph()
        for address, size in ((0, 8), (2**47-4, 8), (GAME, 0), (GAME, 65537)):
            with self.subTest(address=address, size=size), self.assertRaises(ValueError):
                observer.BudgetReader(m).read(address, size)
        with patch.dict(observer.LIMITS, calls=2, bytes=16, single_read=8):
            reader = observer.BudgetReader(m)
            reader.q(GAME); reader.q(GAME)
            with self.assertRaisesRegex(ValueError, "budget"): reader.q(GAME)
        m.short.add(GAME)
        with self.assertRaisesRegex(ValueError, "Short memory read"): observer.BudgetReader(m).q(GAME)

    def test_without_baseline_a_supported_dispatch_never_gets_effect_attribution(self):
        # Exercise the observer/profile seam with a real supported action and
        # a real byte projection, rather than forcing evaluate_profile's answer.
        status = dispatched_status()
        capture = capture_for(graph()); calls = []
        def factory(*unused):
            calls.append(True)
            return contextlib.nullcontext(capture)
        backend = types.SimpleNamespace(manifest_path=Path("unused-offline-manifest.json"), actions=[COMMAND["action"]])
        with tempfile.TemporaryDirectory() as directory:
            tool = observer.EffectObserver(IDENTITY, backend=backend, store=directory, capture_factory=factory)
            with patch.object(observer, "recorded_snapshot", return_value=types.SimpleNamespace(status=lambda _: status)), \
                 patch.object(observer, "pins", return_value=copy.deepcopy(capture.initial_pins)):
                result = tool.observe(COMMAND["request_id"], record=False)
        self.assertEqual(len(calls), 1, "Supported profile must reach capture, not be silently called unsupported")
        self.assertIsNone(result["baseline_sha256"])
        self.assertEqual(result["effect"]["status"], "unknown")
        self.assertFalse(result["effect"]["selected_effect_verified"])
        self.assertEqual(result["completion_state"], "evidence_insufficient")
        self.assertFalse(result["persistence_verified"])
        self.assertEqual(result["requests_published"], 0)

    def test_reservation_during_capture_cannot_be_labeled_before_publication(self):
        for publisher_started in (False, True):
            with self.subTest(publisher_started=publisher_started), tempfile.TemporaryDirectory() as directory:
                session = Path(directory)/"synthetic-command-journal"
                session.mkdir()
                barrier = (session/"publisher.lock") if publisher_started else observer.TagCommandBackend.key_path(session, COMMAND["request_id"])
                m = graph()
                def reserve(memory, address, unused):
                    if address == ACTOR+0xBB0 and not barrier.exists():
                        barrier.write_text('{"synthetic_reservation":true}', encoding="ascii")
                m.hook = reserve
                capture = capture_for(m)
                backend = types.SimpleNamespace(actions=[COMMAND["action"]], session=lambda _: session,
                                                key_path=observer.TagCommandBackend.key_path)
                tool = observer.EffectObserver(IDENTITY, backend=backend, store=Path(directory)/"observations",
                                              capture_factory=lambda *args: contextlib.nullcontext(capture))
                with patch.object(observer, "pins", return_value=copy.deepcopy(capture.initial_pins)):
                    with self.assertRaises(ValueError): tool.prepare(COMMAND)
                self.assertTrue(barrier.exists())
                self.assertFalse((tool.directory(COMMAND["request_id"])/"baseline.json").exists())

    def test_unstable_sample_preserves_dispatch_and_never_means_rejection(self):
        m = graph()
        def recalculate(memory, address, unused):
            if address == ACTOR+0xBB0: memory.put(GAME+0x2521, "B", 1)
        m.hook = recalculate
        capture = capture_for(m)
        backend = types.SimpleNamespace(manifest_path=Path("unused-offline-manifest.json"), actions=[COMMAND["action"]])
        with tempfile.TemporaryDirectory() as directory:
            tool = observer.EffectObserver(IDENTITY, backend=backend, store=directory,
                                          capture_factory=lambda *args: contextlib.nullcontext(capture))
            with patch.object(observer, "recorded_snapshot", return_value=types.SimpleNamespace(status=lambda _: dispatched_status())):
                result = tool.observe(COMMAND["request_id"], record=False)
        self.assertEqual(result["transport_state"], "dispatched")
        self.assertEqual(result["effect"]["status"], "unknown")
        self.assertFalse(result["effect"]["selected_effect_verified"])
        self.assertEqual(result["effect"]["failure"]["type"], "ValueError")
        self.assertFalse(result["automatic_command_retry"])


if __name__ == "__main__":
    unittest.main()
