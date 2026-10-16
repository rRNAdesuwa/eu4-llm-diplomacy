"""Real native-layout byte graphs; no game process or native function access."""
import copy
import struct
import unittest
from unittest.mock import patch

from bridge import diplomacy_effect_observer as r1
from bridge import war_peace_memory_observer as candidate
from bridge.tests.test_effect_observer_memory import (BASE, GAME, DB, COUNTRIES,
    ACTOR, TARGET, RECORDS_A, RECORDS_B, COUNT, DATE, FRA, SCO, graph, handle)

INDEX_A, INDEX_B, GLOBAL = 0x900000, 0x910000, 0x920000
WAR, ATTACKERS, DEFENDERS, GOAL = 0x930000, 0x940000, 0x950000, 0x960000
WAR2, ATTACKERS2, DEFENDERS2 = 0x970000, 0x980000, 0x990000
ALLY, FOE = 0xA00000, 0xA10000
AUV, BRG = handle("AUV", 3), handle("BRG", 4)


def fixture():
    m = graph()
    for at, size in ((INDEX_A, 1024), (INDEX_B, 1024), (GLOBAL, 4096),
                     (WAR, 0x218), (ATTACKERS, 512), (DEFENDERS, 512),
                     (WAR2, 0x218), (ATTACKERS2, 512), (DEFENDERS2, 512),
                     (ALLY, 0x9B78), (FOE, 0x9B78)):
        m.map(at, size)
    # GOAL is deliberately not mapped: this projection never follows a shared
    # noCB backpointer or claims that a goal definition has been validated.
    for at, full in ((ALLY, AUV), (FOE, BRG)):
        m.put(at, "QI", BASE+0x1C574A0, 357)
        m.put(at+0x20, "Q", full)
        m.put(COUNTRIES+((full >> 32) & 65535)*8, "Q", at)
    m.put(GAME+0x1E28, "QQii", BASE+0x1C38348, GLOBAL, 8, 1)
    m.put(GLOBAL, "Q", WAR)
    for owner, storage, other_slot, records in ((ACTOR, INDEX_A, 2, RECORDS_A),
                                               (TARGET, INDEX_B, 1, RECORDS_B)):
        m.put(owner+0x14F8+0x48, "QQii", BASE+0x1C3A538, storage, 4, 1)
        m.put(storage, "i4xQ", other_slot, WAR)
        m.put(records+other_slot*0x48+0x46, "B", 4)
    fill_war(m, WAR, ATTACKERS, DEFENDERS, (FRA,), (SCO,))
    return m


def fill_war(m, at, left, right, attackers, defenders):
    m.put(at, "QI", BASE+0x1D1F768, 357)
    m.put(at+0x24, "i", DATE-1)
    m.put(at+0x48, "QQQ", left, left+len(attackers)*8, left+512)
    m.put(at+0x78, "QQQ", right, right+len(defenders)*8, right+512)
    m.put(at+0x150, "QQQ", attackers[0], defenders[0], GOAL)
    m.put(left, "Q"*len(attackers), *attackers)
    m.put(right, "Q"*len(defenders), *defenders)


def views(m):
    reader = r1.BudgetReader(m)
    root = r1.roots(reader, BASE)
    actor = r1.country(reader, BASE, root, FRA, "FRA")
    target = r1.country(reader, BASE, root, SCO, "SCO")
    return root, actor, target


def capture(m, inputs=None, reverse=False):
    root, actor, target = inputs or views(m)
    if reverse: actor, target = target, actor
    return candidate.capture_war_pair(r1.BudgetReader(m), BASE, root, actor, target)


def remove_pair_indexes(m):
    for owner, storage, other_slot, records in ((ACTOR, INDEX_A, 2, RECORDS_A),
                                               (TARGET, INDEX_B, 1, RECORDS_B)):
        m.put(owner+0x14F8+0x48, "QQii", BASE+0x1C3A538, storage, 4, 0)
        m.put(records+other_slot*0x48+0x46, "B", 0)


class WarPeaceMemoryObserverTests(unittest.TestCase):
    def setUp(self):
        no_runtime = patch.object(r1, "WindowsRuntime", side_effect=AssertionError("No game access"))
        no_runtime.start(); self.addCleanup(no_runtime.stop)

    def unknown(self, memory, inputs=None, reason=None):
        value = capture(memory, inputs)
        self.assertEqual(value["status"], "unknown", value)
        self.assertIsNone(value["projection"])
        self.assertFalse(value["automatic_command_retry"])
        if reason: self.assertIn(reason, value["failure"]["message"])
        return value

    def test_complete_bilateral_global_and_side_membership_has_two_passes(self):
        m = fixture(); value = capture(m)
        self.assertEqual(value["status"], "observed")
        self.assertTrue(value["two_pass_equal"])
        self.assertEqual(value["passes"][0], value["passes"][1])
        projection = value["projection"]
        self.assertEqual(projection["pair_state"], "opponents")
        self.assertEqual(projection["global_war_count"], 1)
        self.assertEqual(projection["selected_war"]["primary_attacker_handle"], hex(FRA))
        self.assertFalse(projection["selected_war"]["goal_definition_layout_validated"])
        self.assertFalse(any(GOAL <= at < GOAL+0x60 for at, _ in m.reads))
        self.assertFalse(value["atomic_main_thread_snapshot"])
        self.assertFalse(value["world_lifetime_lease_proven"])
        self.assertFalse(value["runtime_effect_verified"])
        self.assertEqual(value["native_calls"], 0)

    def test_direction_reversal_preserves_actual_native_sides(self):
        value = capture(fixture(), reverse=True)
        self.assertEqual(value["status"], "observed")
        self.assertEqual(value["projection"]["selected_war"]["actor_side"], "defender")
        self.assertEqual(value["projection"]["selected_war"]["target_side"], "attacker")

    def test_country_and_root_data_paths_are_one_physical_index_per_direction(self):
        m = fixture(); value = capture(m)
        self.assertEqual(value["projection"]["physical_pair_indexes"], 2)
        for index in value["projection"]["relation_indexes"]:
            self.assertEqual(index["data_field"], index["country_data_alias"])
            self.assertEqual(index["independent_physical_indexes"], 1)
        # The canonical 24-byte object read covers these aliases; do not vote
        # twice by separately reading country+1548 and root+50 as independent.
        self.assertFalse(any(at in (ACTOR+0x1548, TARGET+0x1548) for at, _ in m.reads))

    def test_repeated_war_pointer_for_different_opponents_is_valid(self):
        m = fixture()
        fill_war(m, WAR, ATTACKERS, DEFENDERS, (FRA,), (SCO, AUV))
        m.put(ACTOR+0x14F8+0x5C, "i", 2)
        m.put(INDEX_A+16, "i4xQ", 3, WAR)
        value = capture(m)
        self.assertEqual(value["status"], "observed", value)
        self.assertEqual(len(value["projection"]["selected_war"]["defenders"]), 2)

    def test_bilateral_removal_does_not_mean_peace_while_global_pair_remains(self):
        m = fixture(); remove_pair_indexes(m)
        self.unknown(m, reason="index/global")

    def test_current_absence_never_follows_retained_old_war_pointer(self):
        m = fixture(); remove_pair_indexes(m)
        m.put(GAME+0x1E3C, "i", 0)
        m.put(WAR, "QI", 0, 0)
        m.short.add(WAR)
        m.reads.clear()
        value = capture(m)
        self.assertEqual(value["status"], "observed", value)
        p = value["projection"]
        self.assertEqual(p["pair_state"], "not_currently_opponents")
        self.assertIsNone(p["selected_war"])
        self.assertFalse(p["war_retired_proven"])
        self.assertFalse(p["peace_completion_verified"])
        self.assertFalse(any(WAR <= at < WAR+0x218 for at, _ in m.reads))

    def test_same_side_members_are_not_opponents(self):
        m = fixture(); remove_pair_indexes(m)
        fill_war(m, WAR, ATTACKERS, DEFENDERS, (FRA, SCO), (AUV,))
        value = capture(m)
        self.assertEqual(value["status"], "observed", value)
        self.assertEqual(value["projection"]["pair_state"], "not_currently_opponents")
        self.assertIsNone(value["projection"]["selected_war"])

    def test_null_empty_global_allocation_is_valid_but_nonnull_zero_capacity_is_not(self):
        m = fixture(); remove_pair_indexes(m)
        m.put(GAME+0x1E28, "QQii", BASE+0x1C38348, 0, 0, 0)
        self.assertEqual(capture(m)["status"], "observed")
        m.put(GAME+0x1E30, "Q", GLOBAL)
        self.unknown(m, reason="allocation metadata")

    def test_indexed_pointer_missing_globally_rejects_before_dereference(self):
        m = fixture(); m.put(GAME+0x1E3C, "i", 0)
        self.unknown(m, reason="absent from current global")
        self.assertFalse(any(WAR <= at < WAR+0x218 for at, _ in m.reads))

    def test_outcome_is_diagnostic_and_never_a_retirement_flag(self):
        m = fixture(); m.put(WAR+0x210, "I", 1); m.put(GAME+0x210, "I", 1)
        value = capture(m)
        self.assertEqual(value["status"], "observed", value)
        self.assertEqual(value["projection"]["pair_state"], "opponents")
        self.assertEqual(value["projection"]["selected_war"]["raw_outcome"], 1)
        self.assertFalse(value["projection"]["war_retired_proven"])
        self.assertFalse(any(at == GAME+0x210 for at, _ in m.reads))

    def test_current_global_container_type_signed_count_and_duplicate_pointer(self):
        for offset, fmt, value in ((0, "Q", BASE+0x1234), (0x10, "i", -1),
                                   (0x14, "i", -1), (0x14, "i", 9), (0x10, "i", 513),
                                   (0x10, "i", 129), (0x14, "i", 129), (8, "Q", 0)):
            with self.subTest(offset=offset, value=value):
                m = fixture(); m.put(GAME+0x1E28+offset, fmt, value)
                if offset == 0x10 and value == 129:
                    # Retained capacity > selected scan bound is valid when
                    # used remains one; the signed used bound is independent.
                    self.assertEqual(capture(m)["status"], "observed")
                else: self.unknown(m)
        m = fixture(); m.put(GAME+0x1E3C, "i", 2); m.put(GLOBAL+8, "Q", WAR)
        self.unknown(m, reason="Duplicate global")

    def test_war_indexes_require_typed_headers_signed_counts_and_unique_keys(self):
        for offset, fmt, value in ((0, "Q", BASE+0x1234), (0x10, "i", -1),
                                   (0x14, "i", -1), (0x14, "i", 5), (0x10, "i", 65), (8, "Q", 0)):
            with self.subTest(offset=offset, value=value):
                m = fixture(); m.put(ACTOR+0x14F8+0x48+offset, fmt, value); self.unknown(m)
        m = fixture(); m.put(ACTOR+0x14F8+0x5C, "i", 2); m.put(INDEX_A+16, "i4xQ", 2, WAR)
        self.unknown(m, reason="Duplicate war-index")

    def test_signed_index_key_and_bilateral_pointer_mismatch_reject(self):
        for key in (-1, 0, COUNT, 32768):
            with self.subTest(key=key):
                m = fixture(); m.put(INDEX_A, "i", key); self.unknown(m)
        m = fixture(); m.put(INDEX_B+8, "Q", WAR2)
        self.unknown(m, reason="Bilateral")

    def test_index_unrelated_key_must_also_be_an_actual_opponent(self):
        m = fixture(); m.put(ACTOR+0x14F8+0x5C, "i", 2); m.put(INDEX_A+16, "i4xQ", 3, WAR)
        self.unknown(m, reason="not an opponent")

    def test_noncanonical_or_unaligned_native_container_ranges_reject(self):
        for at, value in ((GAME+0x1E30, 2**47), (GAME+0x1E30, GLOBAL+1),
                           (ACTOR+0x14F8+0x50, 2**47-8), (WAR+0x48, ATTACKERS+1)):
            with self.subTest(at=hex(at)):
                m = fixture(); m.put(at, "Q", value); self.unknown(m)

    def test_full_member_handle_valid_byte_selector_signed_slot_and_padding(self):
        bad = (handle("SCO", 2, valid=0), handle("SCO", 2, kind=1), handle("SCO", 2, kind=7),
               handle("SCO", 32768), SCO | (1 << 24), handle("SCO", COUNT))
        for full in bad:
            with self.subTest(full=hex(full)):
                m = fixture(); m.put(DEFENDERS, "Q", full); self.unknown(m)

    def test_member_lookup_type_marker_or_complete_handle_replacement_reject(self):
        for at, fmt, value in ((TARGET, "Q", BASE+0x1234), (TARGET+8, "I", 0),
                               (TARGET+0x20, "Q", SCO+(1 << 56)), (COUNTRIES+16, "Q", ALLY)):
            with self.subTest(at=hex(at)):
                m = fixture(); inputs = views(m); m.put(at, fmt, value); self.unknown(m, inputs)

    def test_root_owner_full_record_and_war_bit_must_agree(self):
        for at, fmt, value in ((ACTOR+0x14F8+0x10, "Q", TARGET),
                               (RECORDS_A+2*0x48+8, "Q", SCO),
                               (RECORDS_B+0x48+0x46, "B", 0)):
            with self.subTest(at=hex(at)):
                m = fixture(); m.put(at, fmt, value); self.unknown(m)

    def test_war_type_marker_date_goal_and_leaders_reject(self):
        for offset, fmt, value in ((0, "Q", BASE+0x1234), (8, "I", 0), (0x24, "i", 0),
                                   (0x24, "i", DATE+1), (0x160, "Q", 0), (0x150, "Q", SCO)):
            with self.subTest(offset=offset, value=value):
                m = fixture(); m.put(WAR+offset, fmt, value); self.unknown(m)

    def test_vector_extent_duplicate_member_and_cross_side_membership_reject(self):
        for offset, value in ((0x48, 0), (0x50, ATTACKERS), (0x50, ATTACKERS+9),
                              (0x58, ATTACKERS+520), (0x58, ATTACKERS-8)):
            with self.subTest(offset=offset):
                m = fixture(); m.put(WAR+offset, "Q", value); self.unknown(m)
        m = fixture(); m.put(WAR+0x50, "Q", ATTACKERS+16); m.put(ATTACKERS+8, "Q", FRA)
        self.unknown(m, reason="Duplicate country")
        m = fixture(); m.put(DEFENDERS, "Q", FRA)
        self.unknown(m, reason="both war sides")

    def test_short_read_in_each_current_graph_layer_is_unknown(self):
        for address in (GAME+0x1E28, GLOBAL, ACTOR+0x14F8+0x48, INDEX_A, WAR, DEFENDERS, TARGET):
            with self.subTest(address=hex(address)):
                m = fixture(); inputs = views(m); m.short.add(address); self.unknown(m, inputs)

    def test_unrelated_unsupported_global_war_is_not_skipped_for_absence(self):
        m = fixture(); remove_pair_indexes(m)
        m.put(GLOBAL, "Q", WAR2)
        fill_war(m, WAR2, ATTACKERS2, DEFENDERS2, (AUV,), (BRG,))
        self.assertEqual(capture(m)["projection"]["pair_state"], "not_currently_opponents")
        m.put(WAR2, "Q", BASE+0x1234)
        self.unknown(m, reason="war type/marker")

    def test_multiple_opposing_wars_are_ambiguous_not_arbitrarily_selected(self):
        m = fixture(); m.put(GAME+0x1E3C, "i", 2); m.put(GLOBAL+8, "Q", WAR2)
        fill_war(m, WAR2, ATTACKERS2, DEFENDERS2, (FRA,), (SCO,))
        self.unknown(m, reason="Multiple current")

    def test_global_header_and_iteration_guard_changes_are_unknown(self):
        for field, fmt, value in ((GAME+0x1E3C, "i", 0), (GAME+0x1E54, "B", 1), (GAME+0x2521, "B", 1)):
            with self.subTest(field=hex(field)):
                m = fixture(); inputs = views(m)
                def mutate(memory, at, unused):
                    if at == WAR: memory.put(field, fmt, value)
                m.hook = mutate; self.unknown(m, inputs)

    def test_matching_roots_do_not_hide_different_two_pass_war_fields(self):
        m = fixture(); inputs = views(m); reads = 0
        def mutate(memory, at, unused):
            nonlocal reads
            if at == WAR:
                reads += 1
                if reads == 3: memory.put(WAR+0x210, "I", 1)
        m.hook = mutate
        self.unknown(m, inputs, reason="Two complete selected war-graph passes differ")

    def test_shared_budget_exhaustion_is_unknown_not_pair_absence(self):
        m = fixture(); root, actor, target = views(m); reader = r1.BudgetReader(m)
        reader.calls = r1.LIMITS["calls"]
        value = candidate.capture_war_pair(reader, BASE, root, actor, target)
        self.assertEqual(value["status"], "unknown")
        self.assertIn("budget", value["failure"]["message"])

    def test_previous_root_date_is_not_accepted_as_a_current_scope(self):
        m = fixture(); inputs = views(m); m.put(GAME+0x1DD0, "i", DATE+1)
        self.unknown(m, inputs, reason="R1 world/date/health roots changed")


if __name__ == "__main__": unittest.main()
