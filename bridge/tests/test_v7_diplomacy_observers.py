"""v7 target/profile tests using byte-memory fixtures only, never a process."""
from copy import deepcopy
from unittest.mock import patch
import struct
import unittest

from bridge.tests import test_core_relation_probe as relation_fixture
from bridge.tests import test_diplomacy_replies_probe as reply_fixture
from work import probe_diplomacy_relations_1375 as old_relations
from work import probe_diplomacy_replies_1375 as old_replies
from work import probe_diplomacy_relations_v7_1375 as relations
from work import probe_diplomacy_replies_v7_1375 as replies


def relation_memory(action, target, **kwargs):
    # Reuse independently established graph fixtures, changing their observer
    # dependency only. The original production modules are never patched.
    with patch.object(relation_fixture, "probe", relations):
        return relation_fixture.fixture(action, target, **kwargs)


def relation_report(memory, action, target, *, after=False):
    with patch.object(relation_fixture, "probe", relations):
        return relation_fixture.report(memory, action, target, after=after)


def reply_memory(messages=(), **kwargs):
    with patch.object(reply_fixture, "probe", replies):
        return reply_fixture.fixture(messages, **kwargs)


def reply_report(memory, target="all", *, after=False):
    targets = replies.selected_targets(target)
    stamp = "2026-10-08T12:00:01+00:00" if after else "2026-10-08T12:00:00+00:00"
    return {"schema_version": 1, "kind": "diplomatic_reply_snapshot", "profile": replies.PROFILE,
        "static_evidence_sha256": replies.EVIDENCE_SHA256, "read_only": True, "targets": targets,
        "build": {"sha256": replies.base.LOCAL_SHA256}, "capture_started_at": stamp, "capture_finished_at": stamp,
        "source": {"kind": "live_process", "pid": 123, "process_creation_filetime": 134358500000000000,
            "process_exit_filetime": 0, "module_base": hex(reply_fixture.BASE), "access_rights": "QUERY_INFORMATION | VM_READ",
            "verified_executable_path": "D:\\Games\\eu4.exe"},
        "observation": replies.capture(memory, reply_fixture.BASE, targets)}


class V7RelationTests(unittest.TestCase):
    def test_exact_new_identities_and_unchanged_native_layout(self):
        for module in (relations, replies):
            self.assertEqual(module.HANDLES["NAV"], 0x010000BC0056414E)
            self.assertEqual(module.HANDLES["FOI"], 0x0100007900494F46)
            self.assertEqual((module.HANDLES["NAV"] >> 32) & 0xFFFF, 188)
            self.assertEqual((module.HANDLES["FOI"] >> 32) & 0xFFFF, 121)
        self.assertEqual(relations.TOKENS, old_relations.TOKENS)
        self.assertEqual(relations.RELATIONS, old_relations.RELATIONS)
        self.assertEqual(relations.SPY_TASK_VTABLE, old_relations.SPY_TASK_VTABLE)
        self.assertEqual(relations.MAX_TASKS, old_relations.MAX_TASKS)
        self.assertEqual(replies.PINS, old_replies.PINS)
        self.assertEqual(replies.MAX_HISTORY_NODES, old_replies.MAX_HISTORY_NODES)
        self.assertEqual(replies.MESSAGE_VTABLES, old_replies.MESSAGE_VTABLES)
        self.assertNotEqual(relations.PROFILE, old_relations.PROFILE)
        self.assertNotEqual(replies.PROFILE, old_replies.PROFILE)

    def test_all_five_actions_four_targets_add_and_cancel(self):
        for target in relations.TARGETS:
            for action in relations.TOKENS:
                with self.subTest(action=action, target=target):
                    absent = relation_report(relation_memory(action, target), action, target)
                    active = relation_report(relation_memory(action, target, active=True), action, target, after=True)
                    result = relations.compare_reports(absent, active)
                    self.assertTrue(result["observed_effect"], result)
                    self.assertFalse(result["request_causality_verified"])
                    self.assertFalse(result["ai_acceptance_verified"])
                    self.assertFalse(result["execution_verified"])
                    before = relation_report(relation_memory(action, target, active=True), action, target)
                    after = relation_report(relation_memory(action, target), action, target, after=True)
                    result = relations.compare_reports(before, after, "cancel")
                    self.assertTrue(result["observed_effect"], result)
                    self.assertFalse(result["rejection_observed"])

    def test_new_target_full_generation_handle_and_array_slot_are_required(self):
        for target in ("NAV", "FOI"):
            for generation_change in (False, True):
                memory = relation_memory("royal_marriage", target)
                if generation_change:
                    memory.write_fixture(relation_fixture.TARGET + 0x20, relations.HANDLES[target] ^ (1 << 56))
                else:
                    slot = (relations.HANDLES[target] >> 32) & 0xFFFF
                    memory.write_fixture(relation_fixture.COUNTRIES + slot * 8, 0)
                result = relations.capture(memory, relation_fixture.BASE, target, "royal_marriage")
                self.assertEqual(result["status"], "unknown", result)

    def test_v6_profile_and_missing_relation_cannot_prove_success(self):
        before = relation_report(relation_memory("vassalaction", "NAV"), "vassalaction", "NAV")
        after = relation_report(relation_memory("vassalaction", "NAV"), "vassalaction", "NAV", after=True)
        result = relations.compare_reports(before, after)
        self.assertFalse(result["observed_effect"])
        self.assertFalse(result["rejection_observed"])
        after["profile"] = old_relations.PROFILE
        self.assertTrue(relations.compare_reports(before, after)["errors"])
        for original in (before, after):
            self.assertFalse(old_relations.compare_reports(original, original)["observed_effect"])

    def test_new_target_mission_identity_cannot_be_substituted(self):
        for target, substituted in (("NAV", "FOI"), ("FOI", "NAV")):
            memory = relation_memory("spy_network", target, active=True)
            memory.write_fixture(relation_fixture.MISSION + 0x88, relations.HANDLES[substituted])
            observed = relations.capture(memory, relation_fixture.BASE, target, "spy_network")
            self.assertEqual(observed["status"], "unknown")


class V7ReplyTests(unittest.TestCase):
    def test_target_selection_and_pair_type_filtering(self):
        self.assertEqual(replies.selected_targets("all"), ["ENG", "POR", "NAV", "FOI"])
        self.assertEqual(replies.selected_targets("both"), ["ENG", "POR"])
        messages = [("ROYMARREJECT", t, reply_fixture.DATE) for t in replies.TARGETS]
        messages += [("VASALLACCEPT", "NAV", reply_fixture.DATE)]
        for selection, expected in (("all", set(replies.TARGETS)), ("both", {"ENG", "POR"}), ("NAV", {"NAV"}), ("FOI", {"FOI"})):
            before = reply_report(reply_memory(), selection)
            after = reply_report(reply_memory(messages), selection, after=True)
            result = replies.compare_reports(before, after, "royal_marriage")
            self.assertEqual(result["status"], "reply_notifications_correlated", result)
            self.assertEqual({m["target"] for m in result["correlated_messages"]}, expected)
            self.assertTrue(result["rejected_correlated"])
            self.assertFalse(result["accepted_correlated"])
            self.assertFalse(result["request_id_causality_verified"])
            self.assertFalse(result["applied_verified"])
            self.assertFalse(result["execution_verified"])

    def test_all_known_reply_keys_include_new_pairs(self):
        for target in ("NAV", "FOI"):
            for key, (action, outcome) in replies.KEYS.items():
                with self.subTest(target=target, key=key):
                    before = reply_report(reply_memory(), target)
                    after = reply_report(reply_memory([(key, target, reply_fixture.DATE)]), target, after=True)
                    result = replies.compare_reports(before, after, action)
                    self.assertEqual(result["correlated_messages"][0]["outcome"], outcome, result)

    def test_changed_target_set_or_old_profile_refuses_comparison(self):
        before = reply_report(reply_memory())
        good = reply_report(reply_memory([("ROYMARREJECT", "FOI", reply_fixture.DATE)]), after=True)
        for change in (lambda r: r.update(profile=old_replies.PROFILE),
                       lambda r: r.update(targets=["ENG", "POR"]),
                       lambda r: r["build"].update(sha256="0" * 64),
                       lambda r: r["source"].update(process_creation_filetime=1)):
            after = deepcopy(good)
            change(after)
            result = replies.compare_reports(before, after)
            self.assertEqual(result["status"], "unknown")
            self.assertTrue(result["errors"])
        different_scope = reply_report(reply_memory([("ROYMARREJECT", "FOI", reply_fixture.DATE)]), "FOI", after=True)
        self.assertEqual(replies.compare_reports(before, different_scope)["status"], "unknown")

    def test_missing_removed_or_reverse_message_is_not_a_reply(self):
        before = reply_report(reply_memory(), "FOI")
        for variant in ("missing", "removed", "reverse"):
            memory = reply_memory([] if variant == "missing" else [("ROYMARREJECT", "FOI", reply_fixture.DATE)], removed=variant == "removed")
            if variant == "reverse":
                memory.write_fixture(reply_fixture.MESSAGE + 0x28, struct.pack("<QQ", replies.HANDLES["FOI"], replies.HANDLES["FRA"]))
            after = reply_report(memory, "FOI", after=True)
            result = replies.compare_reports(before, after)
            self.assertEqual(result["status"], "unknown", result)
            self.assertFalse(result["rejected_correlated"])
            self.assertFalse(result["accepted_correlated"])

    def test_two_pass_disagreement_and_bounds_remain_fail_closed(self):
        first = replies.sample_once(reply_memory(), reply_fixture.BASE, list(replies.TARGETS))
        second = replies.sample_once(reply_memory([("VASALLREJECT", "NAV", reply_fixture.DATE)]), reply_fixture.BASE, list(replies.TARGETS))
        with patch.object(replies, "sample_once", side_effect=[first, second]):
            self.assertEqual(replies.capture(None, reply_fixture.BASE, list(replies.TARGETS))["status"], "unknown")
        memory = reply_memory()
        memory.write_fixture(reply_fixture.MANAGER + 0x20, replies.MAX_HISTORY_NODES + 1, 4)
        self.assertEqual(reply_report(memory)["observation"]["status"], "unknown")
        with self.assertRaises(replies.base.ProbeError):
            replies.selected_targets("arbitrary")
        for target_set in (["NAV", "FOI"], ["NAV", "NAV"], ["FRA"], []):
            changed = deepcopy(first)
            changed["targets"] = target_set
            with self.assertRaises(replies.base.ProbeError):
                replies.inspect_sample(changed)


if __name__ == "__main__":
    unittest.main()
