"""Offline checks only: no game process, requests, or successful-action retests."""
from pathlib import Path
import tempfile
import unittest

from tools.build_diplomacy_catalog import parse_script
from tools.build_diplomacy_unlock_mod import ROOT, DEFAULT_BASE, NAME, build, spans, patch
from tools.install_diplomacy_unlock_mod import verify_source


def signature(nodes):
    return [(n.key, n.value, signature(n.children)) for n in nodes]


class UnlockModTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = ROOT / "mod" / NAME
        cls.manifest = verify_source(cls.mod)

    def read(self, rel):
        return (self.mod / rel).read_text(encoding="utf-8-sig")

    def test_original_action_effects_and_registration_unchanged(self):
        for rel, keys in (
            ("common/new_diplomatic_actions/00_diplomatic_actions.txt", {"static_actions"}),
            ("common/diplomatic_actions/00_diplomatic_actions.txt", set()),
        ):
            original = parse_script((DEFAULT_BASE / rel).read_text(encoding="utf-8-sig"))
            changed = parse_script(self.read(rel))
            self.assertEqual([n.key for n in original], [n.key for n in changed])
            for a, b in zip(original, changed):
                if a.key in keys:
                    self.assertEqual(signature([a]), signature([b]))
                else:
                    effects = {"effect", "pre_effect", "on_accept", "on_decline", "require_acceptance"}
                    self.assertEqual(signature([n for n in a.children if n.key in effects]),
                                     signature([n for n in b.children if n.key in effects]))
        self.assertFalse(self.manifest["all_native_conditions_bypassed"])

    def test_every_scripted_action_is_exposed_with_unchanged_acceptance_flow(self):
        nodes = parse_script(self.read("common/new_diplomatic_actions/00_diplomatic_actions.txt"))
        count = 0
        for n in nodes:
            if n.key == "static_actions":
                continue
            fields = {c.key: c for c in n.children}
            for key in ("is_visible", "is_allowed"):
                self.assertEqual(signature(fields[key].children), [("always", "yes", [])])
            if fields["require_acceptance"].value == "yes":
                self.assertIn("ai_acceptance", fields)
            count += 1
        self.assertEqual(count, 40)

    def test_subject_inheritance_overrides_cannot_relock_switches(self):
        nodes = parse_script(self.read("common/subject_types/00_subject_types.txt"))
        default = next(n for n in nodes if n.key == "default")
        keys = [n.key for n in default.children]
        switches = keys[keys.index("embargo_rivals"):keys.index("expel_ronin") + 1]
        self.assertEqual(len(switches), 44)
        for n in nodes:
            if n.children:
                fields = {c.key: c for c in n.children}
                self.assertTrue(all(fields[k].value == "yes" for k in switches), n.key)
                for key in ("can_fight", "can_rival", "can_ally", "can_marry"):
                    self.assertEqual({c.key for c in fields[key].children},
                                     {"independent_nations", "other_overlord", "same_overlord"})
                    self.assertEqual(len([c for c in fields[key].children if c.key == "same_overlord"]), 27)

    def test_generation_is_reproducible_and_new_fixture_effects_are_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = build(DEFAULT_BASE, Path(tmp))
            self.assertEqual(result, self.manifest)
        n = parse_script(self.read("common/new_diplomatic_actions/zzzz_llm_unlock_fixtures.txt"))
        self.assertEqual([v.key for v in n], self.manifest["fixture_actions_excluded_from_success"])
        self.assertFalse(self.manifest["runtime_verified"])

    def test_special_subject_fallback_is_disabled_without_changing_other_helpers(self):
        rel = "common/scripted_effects/01_scripted_effects_for_diplomacy.txt"
        original = (DEFAULT_BASE / rel).read_text(encoding="utf-8-sig")
        changed = self.read(rel)
        before, after = spans(original), spans(changed)
        self.assertEqual([n.key for n in before], [n.key for n in after])
        for old, new in zip(before, after):
            if old.key != "convert_special_subject_to_vassal":
                self.assertEqual(original[old.start:old.end], changed[new.start:new.end])
                continue
            old_guard = next(n for n in old.children[0].children if n.key == "limit")
            new_guard = next(n for n in new.children[0].children if n.key == "limit")
            self.assertEqual(signature(parse_script(changed[new_guard.start:new_guard.end])),
                             [("limit", None, [("always", "no", [])])])
            self.assertEqual(original[old.start:old_guard.start], changed[new.start:new_guard.start])
            self.assertEqual(original[old_guard.end:old.end], changed[new_guard.end:new.end])
        self.assertTrue(self.manifest["special_subject_fallback_disabled"])
        self.assertEqual(self.manifest["counts"]["special_subject_normalization_guards_disabled"], 1)

    def test_span_patching_handles_quoted_braces_comments_and_inline_fields(self):
        text = '# ignored = {\na = { desc = "} # {" allow = { no = yes } keep = yes }\n'
        node = spans(text)[0]
        allow = next(n for n in node.children if n.key == "allow")
        result = patch(text, [(allow.start, allow.end, "allow = { always = yes }")])
        self.assertIn('desc = "} # {"', result)
        self.assertIn("keep = yes", result)
        with self.assertRaises(ValueError):
            patch(text, [(0, 6, ""), (4, 7, "")])

    def test_opinion_fixtures_do_not_force_every_pair_to_the_same_cap(self):
        nodes = parse_script(self.read("common/static_modifiers/00_static_modifiers.txt"))
        base = next(n for n in nodes if n.key == "base_values")
        self.assertFalse(any(n.key.startswith("relation_with_") for n in base.children))
        fixture_text = self.read("common/new_diplomatic_actions/zzzz_llm_unlock_fixtures.txt")
        self.assertIn("llm_unlock_prepare_friendly_target", fixture_text)
        self.assertIn("llm_unlock_prepare_hostile_target", fixture_text)
        self.assertIn("llm_unlock_clear_pair_opinion = yes", fixture_text)


if __name__ == "__main__":
    unittest.main()
