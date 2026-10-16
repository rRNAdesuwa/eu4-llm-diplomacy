from copy import deepcopy
import importlib.util
import io
from pathlib import Path
import sqlite3
import subprocess
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("candidate_contract_catalog", HERE / "catalog.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def sample(schema, key=""):
    if "const" in schema:
        return deepcopy(schema["const"])
    if "enum" in schema:
        return deepcopy(schema["enum"][0])
    kind = schema["type"]
    if kind == "object":
        return {k: sample(schema["properties"][k], k) for k in schema["required"]}
    if kind == "array":
        return [sample(schema["items"])] * schema.get("minItems", 0)
    if kind in ("integer", "number"):
        return schema.get("minimum", 1)
    if kind == "boolean":
        return True
    if kind == "string":
        if schema.get("pattern") == "^[A-Z0-9]{3}$":
            return "FRA" if key == "actor" else "ENG"
        return "a" * max(schema.get("minLength", 1), 1)
    if kind == "null":
        return None
    raise AssertionError(kind)


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = c.ContractCatalog()

    def req(self, action="corrupt_officials", **params):
        fields = sample(self.api.describe(action)["parameters"])
        fields.update(params)
        return {"protocol": c.PROTOCOL, "request_id": "sample-1", "action": action, "parameters": fields}

    def rejected(self, payload):
        with self.assertRaises(c.ContractError):
            self.api.request(payload)

    def test_274_catalog_inventory_and_readiness(self):
        d = self.api.describe()
        self.assertEqual((d["catalog_actions"], d["static_mapped"], d["typed_binding_extensions"]), (274, 270, 15))
        self.assertEqual(len({a["action"] for a in d["actions"]}), 274)
        self.assertFalse(d["native_ready"])
        self.assertIsNone(d["live_readiness"])

    def test_every_action_structural_request_remains_unsupported(self):
        for item in self.api.describe()["actions"]:
            with self.subTest(action=item["action"]):
                p = self.req(item["action"])
                r = self.api.request(p)
                self.assertEqual(r["status"], "unsupported")
                for key in ("production_supported", "request_written", "native_called", "queued"):
                    self.assertIs(r[key], False)
                self.assertEqual(r["idempotency_scope"], "not_reserved_contract_only")

    def test_only_two_schema_migrations(self):
        changed = []
        for item in self.api.describe()["actions"]:
            d = self.api.describe(item["action"])
            if d["parameters"] != d["legacy_parameters"]:
                changed.append(item["action"])
        self.assertEqual(changed, ["steal_maps", "support_rebels"])

    def test_region_index_strict_range_and_legacy_rejection(self):
        for value in (0, 2147483647):
            r = self.api.request(self.req("steal_maps", region_index=value))
            self.assertEqual(r["symbolic_binding"]["region_index"], value)
        for value in (-1, 2147483648, True, False, 0.0, "0", None):
            self.rejected(self.req("steal_maps", region_index=value))
        p = self.req("steal_maps")
        p["parameters"].pop("region_index")
        p["parameters"]["region_id"] = "europe"
        self.rejected(p)

    def test_rebel_identity_exact_unsigned_pair(self):
        for lo, hi in ((0, 0), (0xffffffff, 0xffffffff), (1, 123)):
            r = self.api.request(self.req("support_rebels", faction_identity={"low": lo, "high": hi}))
            self.assertFalse(r["symbolic_binding"]["faction_resolved"])
        for field in ("low", "high"):
            for bad in (-1, 1 << 32, True, False, 1.0, "1", None):
                value = {"low": 1, "high": 2}; value[field] = bad
                self.rejected(self.req("support_rebels", faction_identity=value))
        for value in ({"low": 1}, {"low": 1, "high": 2, "pointer": "0x123"}, [1, 2], "faction"):
            self.rejected(self.req("support_rebels", faction_identity=value))
        self.rejected(self.req("support_rebels", rebel_faction_id="pretenders"))

    def test_all_six_focus_values_are_fixed_command_enum(self):
        names = ["no_focus", "aggressive", "supportive", "passive", "defensive", "siege"]
        for number, name in enumerate(names):
            binding = self.api.request(self.req("subject.set_military_focus", focus=name))["symbolic_binding"]
            self.assertEqual(binding["focus_enum"], number)
            self.assertEqual(binding["kind"], "already_command")
        for bad in (0, 5, 6, False, "6", "aggressive\n", "Aggressive"):
            self.rejected(self.req("subject.set_military_focus", focus=bad))

    def test_toggles_never_invent_current_state_or_cancel(self):
        for name, mask in (("embargo_rivals", 2), ("scutage", 16), ("divert_trade", 64)):
            for enabled in (False, True):
                binding = self.api.request(self.req(f"subject.{name}", enabled=enabled))["symbolic_binding"]
                self.assertIs(binding["desired_enabled"], enabled)
                self.assertIsNone(binding["cancel"])
                self.assertIsNone(binding["current_enabled"])
                self.assertEqual(binding["flag_mask"], mask)
            for bad in (0, 1, "false", None):
                self.rejected(self.req(f"subject.{name}", enabled=bad))
            self.rejected(self.req(f"subject.{name}", cancel=True))

    def test_five_spy_modes_and_preview_roles_are_not_caller_parameters(self):
        for action in ("corrupt_officials", "sabotage_reputation", "sow_discontent", "slander_merchants", "sabotage_recruitment"):
            d = self.api.describe(action)
            self.assertTrue(d["readiness"]["source_mock_only"])
            self.assertFalse(d["readiness"]["native_ready"])
            self.assertEqual(d["binding"]["fixed_fields"], {"value": True, "state": 0, "envoy_id": -1})
            self.assertIn("+88", " ".join(d["readiness"]["blockers"]))
            for key, value in (("value", False), ("state", 2), ("envoy_id", 5), ("cost", 0), ("submit", True)):
                self.rejected(self.req(action, **{key: value}))

    def test_curry_stop_keeps_minus_one_envoy(self):
        for action, value in (("curry_favors", True), ("stop_currying_favors", False)):
            binding = self.api.request(self.req(action))["symbolic_binding"]
            self.assertEqual(binding["native_token"], 0x3acc)
            self.assertEqual(binding["fixed_fields"], {"value": value, "state": 0, "envoy_id": -1})

    def test_rebel_false_is_not_exposed(self):
        d = self.api.describe("stop_supporting_rebels")
        self.assertEqual(d["binding"]["binding_kind"], "unsupported_false_mode")
        self.assertIsNone(self.api.request(self.req("stop_supporting_rebels"))["symbolic_binding"]["fixed_fields"])
        self.assertIn("full family preview rejects false", " ".join(d["readiness"]["blockers"]))

    def test_scripted_modernization_not_generic_tech(self):
        p = self.req("steal_modern_ideas")
        r = self.api.request(p)
        self.assertEqual(r["symbolic_binding"]["fixed_fields"]["definition_name"], "steal_modern_ideas")
        self.assertIn("not technology levels", " ".join(self.api.describe("steal_modern_ideas")["binding"]["semantics"]))
        for key in ("definition_name", "script", "event", "technology"):
            q = deepcopy(p); q["parameters"][key] = "anything"; self.rejected(q)
        p["action"] = "steal_technology"; self.rejected(p)

    def test_describe_and_validate_never_imply_legality(self):
        d = self.api.describe("support_rebels")
        self.assertEqual(d["parameter_validation"], "structural_only")
        self.assertFalse(d["native_binding_complete"])
        for key in ("legality", "ai_acceptance", "effect", "live_readiness"):
            self.assertIsNone(d["readiness"][key])
        self.assertFalse(self.api.validate(self.req("support_rebels"))["native_binding_resolved"])

    def test_unextended_partial_schema_preserved(self):
        d = self.api.describe("cancel_sow_discontent")
        self.assertEqual(d["legacy_parameter_status"], "partial")
        self.assertIsNone(d["binding"])
        self.assertIsNone(self.api.request(self.req("cancel_sow_discontent"))["symbolic_binding"])

    def test_unknown_fields_and_raw_native_selectors_rejected(self):
        for key, value in (("rva", 0x123), ("pointer", "0x123"), ("dll", "test.dll"), ("backend", "native"),
                           ("pid", 1), ("actor_handle", "0x100"), ("command", "yesman")):
            p = self.req(); p[key] = value; self.rejected(p)
            self.rejected(self.req(**{key: value}))

    def test_request_envelope_and_identity_strict(self):
        for key in ("protocol", "request_id", "action", "parameters"):
            p = self.req(); del p[key]; self.rejected(p)
        for value in ("EU4DIPLOMACY-CONTRACT/1", "EU4LAB/2", True, None):
            p = self.req(); p["protocol"] = value; self.rejected(p)
        for value in ("", "x" * 65, "name\n", "/tmp/file", "中文", 1):
            p = self.req(); p["request_id"] = value; self.rejected(p)
        for value in ([], {}, None, "UNKNOWN"):
            p = self.req(); p["action"] = value; self.rejected(p)

    def test_country_tags_strict_and_not_native_handles(self):
        for bad in ("fra", "FRA\n", "FR", "FRAX", "0x100007a00415246", 123, None):
            self.rejected(self.req(actor=bad))

    def test_canonical_wire_roundtrip_duplicates_and_nan(self):
        p = self.req("support_rebels")
        wire = c.canonical(p)
        self.assertEqual(self.api.decode(wire), p)
        self.assertEqual(self.api.request(p)["request_sha256"], self.api.request(dict(reversed(list(p.items()))))["request_sha256"])
        for bad in (b'{"action":"a","action":"b"}', b'{"a":NaN}', b'{"a":Infinity}', b'\xff', b'[]', wire + b'{}'):
            with self.assertRaises(c.ContractError): self.api.decode(bad)

    def test_budget_limits_raw_and_in_memory(self):
        with self.assertRaises(c.ContractError): self.api.decode(b' ' * (c.MAX_REQUEST + 1))
        for value in ("x" * 4097, 1 << 300, [0] * 65, float("nan"), float("inf")):
            p = self.req(); p["parameters"]["target"] = value; self.rejected(p)
        deep = {}; child = deep
        for _ in range(10): child["x"] = {}; child = child["x"]
        p = self.req(); p["parameters"] = deep; self.rejected(p)
        p = self.req(); p["parameters"]["target"] = {1: "x"}; self.rejected(p)

    def test_in_memory_non_json_subclasses_are_rejected(self):
        class Other(dict): pass
        self.rejected(Other(self.req()))
        p = self.req(); p["parameters"] = Other(p["parameters"]); self.rejected(p)
        p = self.req(); p["parameters"]["target"] = (1, 2); self.rejected(p)

    def test_mutating_returned_descriptor_does_not_change_contract(self):
        d = self.api.describe("subject.set_military_focus")
        d["binding"]["enum_binding"]["siege"] = 123
        d["parameters"]["additionalProperties"] = True
        d["readiness"]["blockers"].clear()
        self.assertEqual(self.api.request(self.req("subject.set_military_focus", focus="siege"))["symbolic_binding"]["focus_enum"], 5)
        self.rejected(self.req("subject.set_military_focus", pointer="raw"))

    def test_binding_uses_validated_canonical_snapshot(self):
        p = self.req("subject.set_military_focus", focus="siege")
        original = self.api.validate
        def changed_after_validation(payload):
            result = original(payload)
            payload["parameters"]["focus"] = "no_focus"
            return result
        with patch.object(self.api, "validate", changed_after_validation):
            result = self.api.request(p)
        self.assertEqual(result["symbolic_binding"]["focus_enum"], 5)
        self.assertIn('"focus":"siege"', result["canonical_request"])

    def test_no_backend_sqlite_or_subprocess_side_effect(self):
        with patch.object(sqlite3, "connect", side_effect=AssertionError("DB side effect")), \
             patch.object(subprocess, "Popen", side_effect=AssertionError("Process side effect")):
            api = c.ContractCatalog()
            first = api.request(self.req())
            second = api.request(self.req())
        self.assertEqual(first, second)
        self.assertEqual(first["idempotency_scope"], "not_reserved_contract_only")

    def test_source_mutation_rejected_before_validator_use(self):
        original = c.read_bounded
        def modified(path, limit):
            data = original(path, limit)
            return data[:-1] + b'!' if path.as_posix().endswith("bridge/diplomacy_api.py") else data
        with patch.object(c, "read_bounded", modified), self.assertRaisesRegex(c.ContractError, "Pinned source changed"):
            c.ContractCatalog()

    def test_candidate_binding_or_pin_changes_rejected(self):
        original = c.read_bounded
        for suffix in ("bindings.json", "input-pins.json"):
            def changed(path, limit):
                data = original(path, limit)
                return data[:-1] + b' ' if path.name == suffix else data
            with patch.object(c, "read_bounded", changed), self.assertRaisesRegex(c.ContractError, "Candidate pin/binding"):
                c.ContractCatalog()

    def test_actual_read_bound_without_stat_race(self):
        class FakePath:
            name = "growing"
            def open(self, mode):
                return io.BytesIO(b'x' * 101)
        with self.assertRaises(c.ContractError): c.read_bounded(FakePath(), 100)
        self.assertEqual(len(c.read_bounded(FakePath(), 101)), 101)

    def test_pinned_evidence_and_candidate_resource_bounds(self):
        self.assertEqual(len(self.api._pins), 23)
        self.assertLess(self.api.verified_source_bytes, c.MAX_TOTAL)
        for entry in self.api.describe()["actions"]:
            d = self.api.describe(entry["action"])
            for evidence in d["source_evidence"]:
                self.assertEqual(len(evidence["sha256"]), 64)
                self.assertLessEqual(evidence["bytes"], c.MAX_SOURCE)


if __name__ == "__main__":
    unittest.main()
