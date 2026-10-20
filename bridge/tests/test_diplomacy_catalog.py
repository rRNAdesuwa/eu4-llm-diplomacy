"""Structural source enumeration and evidence/status separation, without EU4."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.build_diplomacy_catalog import (Builder, DEFAULT_SPECIAL_REPORT, SHOGUNATE_SOURCE,
    SPECIAL_REPORT_SHA256, STATIC_MAPPING_FIELDS, DEFAULT_PEACE_REPORT, DEFAULT_PEACE_EVIDENCE_REPORT,
    PEACE_REPORT_SHA256, PEACE_EVIDENCE_SHA256, DEFAULT_MODES_REPORT, MODES_REPORT_SHA256, parse_script, render_docs)
from bridge.diplomacy_api import APIError, validate_value


ROOT = Path(__file__).resolve().parents[2]


class ClausewitzScannerTests(unittest.TestCase):
    def test_comments_quoted_braces_and_bare_list_tokens(self):
        nodes = parse_script('''# hidden = { bad }
real = { text = "brace } and # inside a string" # fake = {
    options = { one two value = yes }
    quoted = "escaped \\" quote and {"
}
''')
        self.assertEqual([node.key for node in nodes], ["real"])
        self.assertEqual(nodes[0].line, 2)
        self.assertEqual(nodes[0].children[0].value, "brace } and # inside a string")
        self.assertEqual([child.key for child in nodes[0].children[1].children], ["one", "two", "value"])
        self.assertEqual(nodes[0].children[1].children[2].value, "yes")

    def test_truncated_and_unbalanced_syntax_is_rejected(self):
        for text in ("a = { b = yes", "a = yes }", "a =", "a = }", "a = = b", "= bad", "{ key = value }", 'a = "unterminated', '"'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_script(text)


class CatalogBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.game = Path(self.temporary.name) / "game"
        files = {
            "common/diplomatic_actions/00.txt": """# DIPLOMATIC ACTIONS
# declarewar
# royal_marriage
# break_marriage
# guaranteeaction
# improve_relation
# spy_network
# vassalaction
# break_alliance

declarewar = { }
royal_marriage = { condition = { allow = { always = yes } } }
""",
            "common/new_diplomatic_actions/00.txt": """static_actions = {
royal_marriage = { alert_index = 1 }
vassalaction = { alert_index = 6 }
}
custom_action = { category = influence require_acceptance = yes is_visible = { always = yes } }
""",
            "common/subject_types/00.txt": """vassal = {}
march = {}
default = {
# Subject Interactions:
# (continuous)
subsidize_armies = no
scutage = yes
# (immediate)
placate_rulers = yes
# Modifiers:
modifier_subject = clear
}
vassal = { copy_from = default }
march = { copy_from = vassal subsidize_armies = yes placate_rulers = no }
""",
            "common/peace_treaties/00.txt": """make_dummy = { is_visible = { always = no } }
test_treaty = { is_visible = { always = yes } }
""",
            "common/wargoal_types/00.txt": """war = { attacker = { peace_options = {
po_gold po_demand_provinces # po_fake
} } }
""",
            "common/cb_types/00.txt": """test_cb = { allowed_peace_options = { po_demand_provinces } }
""",
            "interface/countrydiplomacyview.gui": 'guiTypes = { windowType = { name = "diploactionentry" } }',
            "interface/countrydiplomacyview.gfx": 'spriteTypes = { spriteType = { name = "GFX_diplomacy_action_relation" } }',
            "interface/countrysubjectsview.gui": 'guiTypes = { windowType = { name = "subjectview" } }',
            "interface/peaceview.gui": 'guiTypes = { windowType = { name = "peaceview" } }',
            "localisation/fixture_l_english.yml": """l_english:
 royal_marriage:0 "Royal Marriage"
 CANCELALIANCETITLE:0 "Dissolve this Alliance"
 REVOKEGUARANTTITLE:0 "Revoke Guarantee"
 COUNTERESPIONAGETITLE:0 "Counterespionage"
 DOMESTIC_CREATE_VASSALLS:0 "Create Vassals"
""",
            "launcher-settings.json": json.dumps({"rawVersion": "fixture", "version": "Synthetic test fixture"}),
        }
        for relative, content in files.items():
            path = self.game / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        (self.game / "eu4.exe").write_bytes(b"Not a real executable: offline catalog test only")
        self.sha256 = hashlib.sha256((self.game / "eu4.exe").read_bytes()).hexdigest().upper()

    def tearDown(self):
        self.temporary.cleanup()

    def report(self, binary_hash=None):
        path = self.game.parent / "native.json"
        path.write_text(json.dumps({
            "binary": {"sha256": binary_hash or self.sha256},
            "native_actions": {
                "factory_rva": "0x100", "unclassified_script_names": [],
                "actions": [
                    {"name": "royal_marriage", "token_id": 11, "accessor_rva": "0x200", "vtable_rva": "0x300", "runtime_verified": False},
                    {"name": "counterespionage", "token_id": 12, "accessor_rva": "0x400", "vtable_rva": "0x500", "runtime_verified": False},
                    {"name": "scriptable_diplomatic_action", "token_id": 13, "accessor_rva": "0x600", "vtable_rva": "0x700", "runtime_verified": False},
                    {"name": "guaranteeaction", "token_id": 14, "accessor_rva": "0x800", "vtable_rva": "0x900", "runtime_verified": False},
                ],
                "static_variants": [
                    {"source_key": "royal_marriage", "native_action_name": "royal_marriage", "value": True, "evidence": [{"rva": "0x210", "kind": "fixture_branch"}], "runtime_verified": False},
                    {"source_key": "break_marriage", "native_action_name": "royal_marriage", "value": False, "evidence": [{"rva": "0x220", "kind": "fixture_branch"}], "runtime_verified": False},
                    {"source_key": "unresolved_direction", "native_action_name": "royal_marriage", "value": False, "direction_verified": False, "evidence": [], "runtime_verified": False},
                    {"source_key": "revoke_guarantee", "native_action_name": "guaranteeaction", "value": False, "evidence": [], "runtime_verified": False},
                    {"source_key": "guaranteeaction", "native_action_name": "guaranteeaction", "value": True, "evidence": [], "runtime_verified": False},
                ],
            },
        }), encoding="utf-8")
        return path

    def test_deduplication_inheritance_and_disabled_examples(self):
        catalog = Builder(self.game).build()
        actions = {action["action_id"]: action for action in catalog["actions"]}
        self.assertEqual(len(actions), len(catalog["actions"]))
        self.assertEqual(actions["subject.subsidize_armies"]["subject_types_enabled_by_source"], ["march"])
        self.assertEqual(actions["subject.placate_rulers"]["subject_types_enabled_by_source"], ["vassal"])
        self.assertEqual(actions["subject.scutage"]["subject_types_enabled_by_source"], ["march", "vassal"])
        self.assertIn("enabled", actions["subject.scutage"]["parameters"]["required"])
        self.assertNotIn("peace.make_dummy", actions)
        self.assertNotIn("peace.po_fake", actions)
        self.assertEqual(len(actions["royal_marriage"]["evidence"]), 4)
        self.assertEqual(actions["peace.po_demand_provinces"]["parameter_status"], "partial")

    def test_actual_alliance_dissolution_is_not_great_power_demand(self):
        actions = {action["action_id"]: action for action in Builder(self.game).build()["actions"]}
        self.assertIn("third_country", actions["break_alliance"]["parameters"]["required"])
        self.assertNotIn("third_country", actions["dissolve_alliance"]["parameters"]["properties"])
        self.assertEqual(actions["break_alliance"]["game_key"], "break_alliance")
        self.assertIsNone(actions["dissolve_alliance"]["game_key"])

    def test_selected_percentage_and_province_are_not_dropped_from_requests(self):
        with (self.game / "common/diplomatic_actions/00.txt").open("a", encoding="utf-8") as stream:
            stream.write("\ntransfer_trade_power = {}\n")
        (self.game / "interface/countrydiplomacyview.gui").write_text('''guiTypes = {
            windowType = { name = "UnrelatedDialog"
                scrollbarType = { name = "trade_power_slider" minValue = 9 maxValue = 9 stepSize = 9 }
            }
            eu3dialogtype = { name = "TransferTradePowerDialog"
                scrollbarType = { name = "trade_power_slider" minValue = 0 maxValue = 100 stepSize = 1 }
            }
        }''', encoding="utf-8")
        subject_path = self.game / "common/subject_types/00.txt"
        subject_path.write_text(subject_path.read_text(encoding="utf-8").replace("placate_rulers = yes", "placate_rulers = yes\nfortify_march = yes"), encoding="utf-8")
        with (self.game / "localisation/fixture_l_english.yml").open("a", encoding="utf-8") as stream:
            stream.write('\n FORTIFY_MARCH_EFFECT:0 "They build a fort in $PROVINCE$."\n')
        actions = {action["action_id"]: action for action in Builder(self.game).build()["actions"]}
        trade = actions["transfer_trade_power"]
        self.assertEqual(trade["parameters"]["properties"]["trade_power_percent"], {"type": "integer", "minimum": 0, "maximum": 100})
        self.assertIn("trade_power_percent", trade["parameters"]["required"])
        evidence = [e for e in trade["evidence"] if e["kind"] == "parameter_gui_control"]
        self.assertEqual(len(evidence), 1)
        self.assertIn("minValue=0, maxValue=100, stepSize=1", evidence[0]["detail"])
        fort = actions["subject.fortify_march"]
        self.assertIn("province_id", fort["parameters"]["required"])
        self.assertTrue(any(e["kind"] == "parameter_localization" for e in fort["evidence"]))
        for action in (trade, fort):
            self.assertEqual(action["parameter_status"], "partial")
            self.assertEqual(action["execution"]["status"], "unimplemented")
            self.assertNotIn("native_mapping", action)

    def test_core_action_keys_and_contracts_are_distinct(self):
        actions = {action["action_id"]: action for action in Builder(self.game).build()["actions"]}
        keys = {
            "offer_vassalization": "vassalaction", "royal_marriage": "royal_marriage",
            "improve_relations": "improve_relation", "guarantee": "guaranteeaction", "build_spy_network": "spy_network",
        }
        for action_id, key in keys.items():
            self.assertEqual(actions[action_id]["game_key"], key)
            self.assertEqual(actions[action_id]["parameters"]["required"], ["actor", "target"])
            self.assertEqual(actions[action_id]["execution"]["status"], "unimplemented")
        self.assertEqual(actions["whitepeace"]["parameters"]["properties"]["actor"]["const"], "FRA")
        self.assertEqual(actions["whitepeace"]["parameter_status"], "specified")

    def test_shogunate_source_changes_scope_without_any_native_report(self):
        path = self.game / SHOGUNATE_SOURCE
        path.parent.mkdir(parents=True)
        path.write_text('''shogunate_mechanic = { interactions = {
            expel_ronin = { effect = { hidden_effect = { every_subject_country = {
                limit = { is_subject_of_type = daimyo_vassal } add_adm_power = 1
            } } } }
            sankin_kotai = { effect = { every_subject_country = {
                limit = { is_subject_of_type = daimyo_vassal } add_dip_power = 1
            } } }
            sword_hunt = { effect = { every_subject_country = {
                limit = { is_subject_of_type = daimyo_vassal } add_mil_power = 1
            } } }
        } }''', encoding="utf-8")
        catalog = Builder(self.game).build()
        actions = {a["action_id"]: a for a in catalog["actions"]}
        for key in ("expel_ronin", "sankin_kotai", "sword_hunt"):
            action = actions["subject." + key]
            self.assertEqual(action["surface"], "government_interaction")
            self.assertEqual(action["parameter_status"], "partial")
            self.assertFalse(action["scope"]["single_target_supported"])
            validate_value({"actor": "JAP"}, action["parameters"])
            # A historically accepted target must now fail, not be ignored and
            # accidentally affect every daimyo when one was requested.
            with self.assertRaises(APIError):
                validate_value({"actor": "JAP", "target": "UES"}, action["parameters"])
            self.assertNotIn("native_special_mapping", action)
            self.assertEqual(action["execution"]["status"], "unimplemented")
        first = json.dumps(catalog, ensure_ascii=False)
        self.assertEqual(first, json.dumps(Builder(self.game).build(), ensure_ascii=False))
        path.write_text(path.read_text(encoding="utf-8").replace("daimyo_vassal", "different_scope"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "scope changed"):
            Builder(self.game).build()

    def test_mismatched_native_report_hash_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            Builder(self.game, self.report("0" * 64)).build()

    def test_native_evidence_never_enables_execution(self):
        catalog = Builder(self.game, self.report()).build()
        actions = {action["action_id"]: action for action in catalog["actions"]}
        self.assertNotIn("scriptable_diplomatic_action", actions)
        self.assertEqual(actions["counterespionage"]["game_key"], "counterespionage")
        self.assertTrue(actions["custom_action"]["native_mapping"]["variants"][0]["requires_script_definition_binding"])
        for action_id in ("royal_marriage", "counterespionage", "custom_action"):
            self.assertEqual(actions[action_id]["native_mapping"]["exe_sha256"], self.sha256)
            self.assertFalse(actions[action_id]["native_mapping"]["runtime_verified"])
            self.assertEqual(actions[action_id]["execution"]["status"], "unimplemented")
            self.assertEqual(actions[action_id]["execution"]["supported_builds"], [])
        self.assertFalse(catalog["coverage"]["complete_native_coverage"])

    def test_same_sources_generate_identical_catalog_and_docs(self):
        first = Builder(self.game, self.report()).build()
        second = Builder(self.game, self.report()).build()
        self.assertEqual(json.dumps(first, ensure_ascii=False), json.dumps(second, ensure_ascii=False))
        self.assertEqual(render_docs(first), render_docs(second))
        self.assertNotIn(str(self.game), render_docs(first))
        source_paths = {source["path"] for source in first["sources"]}
        self.assertIn("common/subject_types/00.txt", source_paths)
        self.assertEqual(first["coverage"]["counts"]["subject_types"], 2)

    def test_cancel_mode_shares_native_family_without_assuming_unknown_direction(self):
        catalog = Builder(self.game, self.report()).build()
        actions = {action["action_id"]: action for action in catalog["actions"]}
        offer = actions["royal_marriage"]["native_mapping"]["variants"][0]
        revoke = actions["break_marriage"]["native_mapping"]["variants"][0]
        self.assertEqual(offer["token_id"], revoke["token_id"])
        self.assertEqual(offer["vtable_rva"], revoke["vtable_rva"])
        self.assertTrue(offer["value"])
        self.assertFalse(revoke["value"])
        self.assertEqual(actions["break_marriage"]["game_key"], "break_marriage")
        self.assertEqual(actions["break_marriage"]["execution"]["status"], "unimplemented")
        self.assertNotIn("unresolved_direction", actions)
        self.assertEqual(catalog["coverage"]["native_reconciliation"]["unresolved_native_variants"][0]["source_key"], "unresolved_direction")
        self.assertFalse(actions["revoke_guarantee"]["native_mapping"]["variants"][0]["value"])
        self.assertTrue(actions["guarantee"]["native_mapping"]["variants"][0]["value"])
        self.assertEqual(catalog["coverage"]["counts"]["public_actions_with_native_mode_evidence"], 4)


class PublishedCatalogTests(unittest.TestCase):
    def test_remaining_mode_report_full_hash_build_and_sources_precede_mutation(self):
        raw = DEFAULT_MODES_REPORT.read_bytes()
        report = json.loads(raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest().upper(), MODES_REPORT_SHA256)
        baseline = next(s for s in report["inputs"] if "baseline" in s["path"])
        baseline_raw = (ROOT / baseline["path"]).read_bytes()
        self.assertEqual(hashlib.sha256(baseline_raw).hexdigest(), baseline["sha256"])
        frozen = json.loads(baseline_raw)
        self.assertEqual(len(frozen["rows"]), 39)
        self.assertEqual({r["action_id"] for r in frozen["rows"]}, {r["action_id"] for r in report["actions"]})
        self.assertNotEqual(frozen["source_catalog_sha256"].upper(), hashlib.sha256((ROOT / "bridge/diplomacy_catalog.json").read_bytes()).hexdigest().upper())
        self.assertFalse(any(s["path"] == "bridge/diplomacy_catalog.json" for s in report["inputs"]))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "modes.json"
            path.write_bytes(raw)
            builder = Builder(Path(temporary), modes_report=path)
            with self.assertRaisesRegex(ValueError, "binary SHA-256"):
                builder.reconcile_modes({"exe_sha256": "0" * 64})
            with self.assertRaisesRegex(ValueError, "source SHA-256"):
                builder.reconcile_modes({"exe_sha256": report["game_sha256"].upper()})
            self.assertEqual(builder.actions, {})
            changed = dict(report, execution_verified=True, runtime_verified=True)
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "full SHA-256"):
                builder.reconcile_modes({"exe_sha256": report["game_sha256"].upper()})
            self.assertEqual(builder.actions, {})

    def test_remaining_modes_preserve_roles_and_do_not_turn_ui_names_into_effects(self):
        catalog = json.loads((ROOT / "bridge/diplomacy_catalog.json").read_text(encoding="utf-8"))
        actions = {a["action_id"]: a for a in catalog["actions"]}
        modes = catalog["coverage"]["modes_reconciliation"]
        self.assertEqual(len(modes["mapped_action_ids"]), 38)
        self.assertEqual(modes["direction_rejected_action_ids"], ["break_vassalization"])
        self.assertEqual(len(modes["ui_mode_only_action_ids"]), 4)
        for key in modes["mapped_action_ids"]:
            self.assertEqual(actions[key]["execution"]["status"], "unimplemented")
            self.assertEqual(actions[key]["execution"]["supported_builds"], [])
        for key in modes["ui_mode_only_action_ids"]:
            action = actions[key]
            self.assertEqual(action["availability"], "native_ui_cancel_mode_effect_unverified")
            self.assertEqual(action["parameter_status"], "partial")
            self.assertFalse(action["native_mapping"]["effect_semantics_verified"])
            self.assertFalse(action["native_mapping"]["variants"][0]["value"])
        def variant(key):
            return actions[key]["native_mapping"]["variants"][0]
        self.assertEqual(variant("dissolve_alliance")["name"], "allianceaction")
        self.assertNotEqual(variant("dissolve_alliance")["name"], variant("break_alliance")["name"])
        self.assertEqual(variant("cancel_military_access")["name"], "milaccess")
        self.assertEqual(variant("revoke_military_access")["name"], "offermilaccess")
        for key in ("ask_support_independence", "cancel_requested_independence_support", "cancel_offered_independence_support",
                    "kick_from_trade_league", "leave_trade_league", "cancel_condottieri", "revoke_condottieri", "cancel_tributary"):
            self.assertIn("state_predicate", variant(key)["mode_constraints"])
        self.assertEqual(variant("leave_trade_league")["name"], "invite_to_trade_league")
        self.assertTrue(variant("ask_support_independence")["value"])
        self.assertFalse(variant("cancel_requested_independence_support")["value"])
        self.assertEqual(actions["join_coalition"]["state_selected_alias_of"], "form_coalition")
        self.assertNotIn("alias_of", actions["join_coalition"])
        self.assertNotIn("value", variant("scornful_insult"))
        self.assertEqual(variant("scornful_insult")["mode_constraints"]["signed_index_at_0x40"], {"minimum": 0})
        self.assertEqual(actions["scornful_insult"]["parameter_status"], "partial")
        # No generic factory branch was found for these families; do not invent
        # one from the shared factory address or from a different family.
        self.assertNotIn("factory_branch", variant("cancel_condottieri"))
        self.assertFalse(any(k in actions["break_vassalization"] for k in STATIC_MAPPING_FIELDS))
        self.assertEqual(actions["break_vassalization"]["availability"], "native_label_present_but_requested_direction_rejected")

    def test_rival_and_release_commands_keep_abi_and_identity_distinct(self):
        catalog = json.loads((ROOT / "bridge/diplomacy_catalog.json").read_text(encoding="utf-8"))
        actions = {a["action_id"]: a for a in catalog["actions"]}
        for key, token in (("select_rival", 0x2fae), ("remove_rival", 0x2faf), ("create_vassal", 0x2991)):
            action = actions[key]
            self.assertNotIn("native_mapping", action)
            self.assertNotIn("native_subject_mapping", action)
            mapping = action["native_special_mapping"]
            self.assertEqual(mapping["command"]["token_id"], token)
            self.assertEqual(mapping["source_report"]["sha256"], MODES_REPORT_SHA256)
            self.assertNotIn("factory_rva", mapping["command"])
            self.assertFalse(mapping["execution_verified"])
            self.assertFalse(mapping["ownership_verified"])
            self.assertEqual(action["parameter_status"], "partial")
        rival = actions["select_rival"]["native_special_mapping"]
        replace = rival["alternative_commands"][0]
        self.assertEqual(replace["size_bytes"], 0x68)
        self.assertEqual(replace["token_id"], 0x3005)
        self.assertEqual(replace["fields"][-1]["source"], "replaced_rival")
        self.assertFalse(replace["replacement_parameter_binding_verified"])
        release = actions["create_vassal"]["native_special_mapping"]
        self.assertEqual([(f["source"], f["offset"]) for f in release["fields"]], [("target", "0x50"), ("actor", "0x58")])
        self.assertTrue(release["requires_landless_country_identity"])
        self.assertNotIn("play_as_released", {f["source"] for f in release["fields"]})
        self.assertFalse(release["conditional_commands"][0]["atomic_with_primary"])
        self.assertTrue(release["conditional_commands"][0]["requires_player_identity_rebind"])
        self.assertEqual(set(catalog["coverage"]["unmapped_action_ids"]), {"break_vassalization", "whitepeace", "gold", "peace.full_annexation"})
        self.assertEqual(catalog["coverage"]["counts"]["actions_with_any_static_native_mapping"], 270)

    def test_peace_merge_requires_both_full_reviewed_reports_and_current_sources(self):
        fields_raw = DEFAULT_PEACE_REPORT.read_bytes()
        proof_raw = DEFAULT_PEACE_EVIDENCE_REPORT.read_bytes()
        self.assertEqual(hashlib.sha256(fields_raw).hexdigest().upper(), PEACE_REPORT_SHA256)
        self.assertEqual(hashlib.sha256(proof_raw).hexdigest().upper(), PEACE_EVIDENCE_SHA256)
        proof = json.loads(proof_raw)
        build = {"exe_sha256": proof["game_sha256"].upper()}
        with tempfile.TemporaryDirectory() as temporary:
            game = Path(temporary)
            fields_path, proof_path = game / "fields.json", game / "proof.json"
            fields_path.write_bytes(fields_raw)
            proof_path.write_bytes(proof_raw)
            incomplete = Builder(game, peace_report=fields_path)
            with self.assertRaisesRegex(ValueError, "both reviewed reports"):
                incomplete.reconcile_peace(build)
            builder = Builder(game, peace_report=fields_path, peace_evidence_report=proof_path)
            with self.assertRaisesRegex(ValueError, "binary SHA-256"):
                builder.reconcile_peace({"exe_sha256": "0" * 64})
            # A matching executable cannot reuse definitions/localization from
            # a different installation. Failure precedes all catalog mutation.
            with self.assertRaisesRegex(ValueError, "source SHA-256"):
                builder.reconcile_peace(build)
            self.assertEqual(builder.actions, {})
            changed = dict(proof, runtime_verified=True, execution_verified=True)
            proof_path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "full SHA-256"):
                builder.reconcile_peace(build)
            proof_path.write_bytes(proof_raw)
            fields = json.loads(fields_raw)
            fields["peace_components"][0]["fields"][0]["object_offset"] = "0x38"
            fields_path.write_text(json.dumps(fields), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "full SHA-256"):
                builder.reconcile_peace(build)
            self.assertEqual(builder.actions, {})

    def test_peace_component_fields_do_not_become_ordinary_diplomatic_requests(self):
        catalog = json.loads((ROOT / "bridge/diplomacy_catalog.json").read_text(encoding="utf-8"))
        actions = {a["action_id"]: a for a in catalog["actions"]}
        mapped = [a for a in actions.values() if "native_peace_mapping" in a]
        self.assertEqual(len(mapped), 53)
        self.assertEqual(len({a["native_peace_mapping"]["component"]["name"] for a in mapped}), 40)
        for action in mapped:
            self.assertEqual(action["surface"], "peace_term")
            self.assertFalse(any(k in action for k in STATIC_MAPPING_FIELDS if k != "native_peace_mapping"))
            mapping = action["native_peace_mapping"]
            self.assertEqual(mapping["component"]["factory_rva"], "0x99ff90")
            self.assertEqual(mapping["source_report"]["sha256"], PEACE_EVIDENCE_SHA256)
            self.assertEqual(mapping["fields_report"]["sha256"], PEACE_REPORT_SHA256)
            self.assertFalse(mapping["runtime_verified"])
            self.assertFalse(mapping["execution_verified"])
            self.assertFalse(mapping["public_parameter_binding_verified"])
            self.assertTrue(mapping["offer_context"]["requires_owned_peace_offer"])
            self.assertFalse(mapping["offer_context"]["standalone_diplomatic_request"])
            self.assertFalse(mapping["offer_context"]["direction_binding_verified"])
            self.assertFalse(mapping["offer_context"]["ownership_verified"])
            self.assertEqual(action["parameter_status"], "partial")
            self.assertEqual(action["execution"]["status"], "unimplemented")
            self.assertEqual(action["execution"]["supported_builds"], [])
            base = {f["token_name"]: f for f in mapping["base_fields"]}
            self.assertEqual(base["giver"]["object_offset"], "0x22")
            self.assertEqual(base["giver"]["width_bytes"], 8)
            self.assertNotEqual(base["giver"]["object_offset"], base["offer_giver"]["object_offset"])
            self.assertFalse(any(f["parser_rva"] == "0x99b400" for f in mapping["fields"]))
        gold = actions["peace.po_gold"]["native_peace_mapping"]["fields"]
        self.assertEqual([(f["token_name"], f["width_bytes"], f["representation"]) for f in gold],
                         [("value", 4, "signed_fixed_point_1000")])
        for name in ("po_demand_provinces", "po_revoke_cores", "po_return_cores"):
            province = next(f for f in actions["peace." + name]["native_peace_mapping"]["fields"] if f["token_name"] == "province_id")
            self.assertEqual(province["width_bytes"], 8)
            self.assertEqual(province["representation"], "province_object_pointer")
        self.assertEqual(catalog["coverage"]["peace_reconciliation"]["unmapped_action_ids"], ["peace.full_annexation"])
        self.assertNotIn("native_peace_mapping", actions["whitepeace"])
        self.assertNotIn("native_peace_mapping", actions["gold"])

    def test_peace_scripted_registry_is_separate_and_fixed_definition_only(self):
        catalog = json.loads((ROOT / "bridge/diplomacy_catalog.json").read_text(encoding="utf-8"))
        scripted = [a for a in catalog["actions"] if a.get("native_peace_mapping", {}).get("script_definition")]
        self.assertEqual(len(scripted), 13)
        for action in scripted:
            mapping = action["native_peace_mapping"]
            component = mapping["component"]
            self.assertEqual(component["name"], "scriptable_diplomatic_action")
            self.assertEqual(component["factory_case_index"], 39)
            self.assertEqual(component["vtable_rva"], "0x1cd21b0")
            definition = mapping["script_definition"]
            self.assertEqual(definition["name"], action["game_key"])
            self.assertEqual(definition["registry_rva"], "0x242bd80")
            self.assertFalse(definition["public_arbitrary_definition_allowed"])
            self.assertFalse(definition["explicitly_hidden"])
            self.assertNotIn("type", action["parameters"]["properties"])
            self.assertEqual(mapping["fields"][0]["representation"], "scripted_peace_definition_pointer")
        ordinary = [a for a in catalog["actions"] if a["surface"] == "diplomacy" and a["game_key_kind"] == "scripted_action"]
        self.assertTrue(ordinary)
        for action in ordinary:
            self.assertNotIn("native_peace_mapping", action)
        proof = json.loads(DEFAULT_PEACE_EVIDENCE_REPORT.read_text(encoding="utf-8"))
        self.assertEqual(proof["source_audit"]["selected_files"], 18)
        self.assertEqual(proof["source_audit"]["archive_files_in_selected_directories"], 0)
        self.assertFalse(proof["source_audit"]["load_order_resolved"])
        self.assertEqual(proof["facts"]["peace_definition_loader"]["path_literal"]["literal"], "/peace_treaties")

    def test_peace_names_and_unsupported_province_array_are_corrected(self):
        catalog = json.loads((ROOT / "bridge/diplomacy_catalog.json").read_text(encoding="utf-8"))
        actions = {a["action_id"]: a for a in catalog["actions"]}
        strength = actions["peace.po_humiliate"]
        alias = actions["peace.show_strength"]
        self.assertEqual(alias["alias_of"], strength["action_id"])
        self.assertEqual(alias["native_peace_mapping"]["component"], strength["native_peace_mapping"]["component"])
        self.assertEqual(strength["name_zh"], "展现力量")
        self.assertEqual(strength["localization_key"], "PEACE_SHOW_STRENGTH")
        rival = actions["peace.po_humiliate_rival"]["native_peace_mapping"]
        self.assertEqual(rival["display_binding"]["label_key"], "PEACE_HUMILIATE")
        self.assertNotEqual(rival["component"]["vtable_rva"], strength["native_peace_mapping"]["component"]["vtable_rva"])
        claims = actions["peace.give_up_claims"]
        validate_value({"actor": "FRA", "target": "ENG", "claims_against": "POR"}, claims["parameters"])
        with self.assertRaises(APIError):
            validate_value({"actor": "FRA", "target": "ENG", "province_ids": [177]}, claims["parameters"])
        self.assertEqual([f["representation"] for f in claims["native_peace_mapping"]["fields"]], ["country_handle"])
        for public_id in ("peace.po_transfer_vassals", "peace.po_enforce_military_access", "peace.revoke_reform"):
            action = actions[public_id]
            self.assertIn("native_peace_mapping", action)
            self.assertEqual(action["parameter_status"], "partial")
            self.assertTrue(any(e["kind"] == "native_peace_component_localization" for e in action["evidence"]))
        transfer = actions["peace.po_transfer_vassals"]
        refs = [e for e in transfer["evidence"] if e["kind"] == "peace_option_reference"]
        self.assertEqual(len(refs), 7)
        self.assertEqual({e["detail"] for e in refs}, {"attacker_disabled_po"})

    def test_special_report_requires_reviewed_full_hash_build_and_script_identity(self):
        raw = DEFAULT_SPECIAL_REPORT.read_bytes()
        original = json.loads(raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest().upper(), SPECIAL_REPORT_SHA256)
        with tempfile.TemporaryDirectory() as temporary:
            game = Path(temporary)
            path = game / "special.json"
            path.write_bytes(raw)
            builder = Builder(game, special_report=path)
            with self.assertRaisesRegex(ValueError, "binary SHA-256"):
                builder.reconcile_special({"exe_sha256": "0" * 64})
            build = {"exe_sha256": original["game_sha256"].upper()}
            # Same EXE alone is insufficient: changed/missing script definitions
            # must not reuse actor-wide scope evidence or definition identities.
            with self.assertRaisesRegex(ValueError, "source SHA-256"):
                builder.reconcile_special(build)
            changed = dict(original, runtime_verified=True, execution_verified=True)
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "full SHA-256"):
                builder.reconcile_special(build)
            self.assertEqual(builder.actions, {})

    def test_six_special_rows_keep_ids_but_use_distinct_command_abis(self):
        catalog = json.loads((ROOT / "bridge/diplomacy_catalog.json").read_text(encoding="utf-8"))
        mapped = [a for a in catalog["actions"] if a.get("native_special_mapping", {}).get("source_report", {}).get("sha256") == SPECIAL_REPORT_SHA256]
        self.assertEqual(len(mapped), 6)
        self.assertEqual(len({a["native_special_mapping"]["command"]["name"] for a in mapped}), 4)
        for action in mapped:
            mapping = action["native_special_mapping"]
            self.assertNotIn("native_mapping", action)
            self.assertNotIn("native_subject_mapping", action)
            self.assertEqual(mapping["command"]["size_bytes"], 0x60)
            self.assertEqual(mapping["exe_sha256"], catalog["game_build"]["exe_sha256"])
            self.assertEqual(mapping["source_report"]["sha256"], SPECIAL_REPORT_SHA256)
            self.assertFalse(mapping["runtime_verified"])
            self.assertFalse(mapping["execution_verified"])
            self.assertFalse(mapping["public_parameter_binding_verified"])
            self.assertEqual(action["execution"]["status"], "unimplemented")
            self.assertEqual(action["execution"]["supported_builds"], [])
        by_id = {a["action_id"]: a for a in mapped}
        focus = by_id["subject.set_military_focus"]
        # Native 1 means aggressive, although the old public enum listed
        # supportive before aggressive. Lists are not integer encodings.
        self.assertEqual(focus["native_special_mapping"]["enum_mappings"]["focus"], {
            "no_focus": 0, "aggressive": 1, "supportive": 2, "passive": 3, "defensive": 4, "siege": 5})
        validate_value({"actor": "FRA", "target": "ENG", "focus": "supportive"}, focus["parameters"])
        with self.assertRaises(APIError):
            validate_value({"actor": "FRA", "target": "ENG", "focus": 2}, focus["parameters"])
        release = by_id["subject.release_colony"]
        self.assertEqual(release["parameter_status"], "partial")
        self.assertNotIn("play_as_released", {f["source"] for f in release["native_special_mapping"]["fields"]})
        follow = release["native_special_mapping"]["conditional_commands"][0]
        self.assertEqual(follow["when"], {"play_as_released": True})
        self.assertEqual(follow["name"], "set_controller")
        self.assertFalse(follow["atomic_with_primary"])
        self.assertTrue(follow["requires_player_identity_rebind"])
        for key in ("expel_ronin", "sankin_kotai", "sword_hunt"):
            action = by_id["subject." + key]
            self.assertEqual(action["parameters"]["required"], ["actor"])
            self.assertEqual(action["surface"], "government_interaction")
            self.assertEqual(action["native_special_mapping"]["script_definition"]["interaction_key"], key)
            self.assertNotIn("subject_types_enabled_by_source", action)
            self.assertIn("legacy_subject_types_enabled_by_source", action)
            with self.assertRaises(APIError):
                validate_value({"actor": "JAP", "target": "UES"}, action["parameters"])
        mapped_ids = {a["action_id"] for a in catalog["actions"] if any(k in a for k in STATIC_MAPPING_FIELDS)}
        missing = {a["action_id"] for a in catalog["actions"]} - mapped_ids
        self.assertEqual(catalog["coverage"]["counts"]["actions_with_any_static_native_mapping"], len(mapped_ids))
        self.assertEqual(catalog["coverage"]["counts"]["actions_without_static_native_mapping"], len(missing))
        self.assertEqual(set(catalog["coverage"]["unmapped_action_ids"]), missing)
        self.assertEqual(len(missing), 4)

    def test_subject_evidence_uses_separate_abi_and_never_enables_execution(self):
        catalog = json.loads((ROOT / "bridge/diplomacy_catalog.json").read_text(encoding="utf-8"))
        report = json.loads((ROOT / "work/reports/native-subject-interactions-1375.json").read_text(encoding="utf-8"))
        mapped = [a for a in catalog["actions"] if "native_subject_mapping" in a]
        self.assertEqual(len(mapped), 41)
        self.assertEqual({a["game_key"] for a in mapped}, {a["name"] for a in report["actions"]})
        for action in mapped:
            self.assertEqual(action["surface"], "subject_interaction")
            self.assertNotIn("native_mapping", action)
            mapping = action["native_subject_mapping"]
            self.assertFalse(mapping["runtime_verified"])
            self.assertFalse(mapping["public_parameter_binding_verified"])
            self.assertEqual(mapping["command"]["token_id"], 0x31d8)
            self.assertEqual(mapping["command"]["size_bytes"], 0xa0)
            self.assertEqual(action["execution"]["supported_builds"], [])
            self.assertEqual(action["execution"]["status"], "unimplemented")

    def test_subject_merge_rejects_wrong_binary_and_duplicate_registration(self):
        original = json.loads((ROOT / "work/reports/native-subject-interactions-1375.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "subject.json"
            path.write_text(json.dumps(original), encoding="utf-8")
            builder = Builder(Path(temporary), subject_report=path)
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                builder.reconcile_subjects({"exe_sha256": "0" * 64})
            original["actions"].append(original["actions"][0])
            path.write_text(json.dumps(original), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                builder.reconcile_subjects({"exe_sha256": original["binary"]["sha256"].upper()})

    def test_shipped_catalog_does_not_claim_current_build_execution(self):
        catalog = json.loads((ROOT / "bridge/diplomacy_catalog.json").read_text(encoding="utf-8"))
        digest = catalog["game_build"]["exe_sha256"]
        self.assertEqual(catalog["schema_version"], 1)
        self.assertFalse(catalog["coverage"]["complete_native_coverage"])
        self.assertEqual(catalog["coverage"]["executable_on_scanned_build"], 0)
        for action in catalog["actions"]:
            self.assertNotIn(digest, action["execution"]["supported_builds"])
            self.assertTrue(action["evidence"])
            self.assertFalse(action["parameters"]["additionalProperties"])
            if "native_mapping" in action:
                self.assertFalse(action["native_mapping"]["runtime_verified"])
                self.assertEqual(action["native_mapping"]["exe_sha256"], digest)

    def test_published_cancel_modes_are_not_overwritten_by_positive_modes(self):
        catalog = json.loads((ROOT / "bridge/diplomacy_catalog.json").read_text(encoding="utf-8"))
        if catalog["coverage"].get("native_reconciliation", {}).get("status") != "static_only_hash_matched":
            self.skipTest("Catalog was generated without the optional native report")
        actions = {action["action_id"]: action for action in catalog["actions"]}
        for identifier in ("offer_vassalization", "royal_marriage", "guarantee", "improve_relations", "build_spy_network"):
            self.assertTrue(actions[identifier]["native_mapping"]["variants"][0]["value"])
        for identifier in ("break_marriage", "revoke_guarantee", "stop_improving_relations", "stop_building_spy_network", "cancel_vassalization"):
            self.assertFalse(actions[identifier]["native_mapping"]["variants"][0]["value"])
        cancel_vassal = actions["cancel_vassalization"]["native_mapping"]["variants"][0]
        self.assertTrue(cancel_vassal["direction_verified"])
        self.assertEqual(cancel_vassal["token_id"], actions["offer_vassalization"]["native_mapping"]["variants"][0]["token_id"])
        self.assertEqual(actions["cancel_vassalization"]["execution"]["status"], "unimplemented")
        self.assertNotIn("native_mapping", actions["break_vassalization"])
        self.assertFalse(actions["dissolve_alliance"]["native_mapping"]["variants"][0]["value"])


if __name__ == "__main__":
    unittest.main()
