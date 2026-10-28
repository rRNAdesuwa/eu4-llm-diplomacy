"""Offline contract regressions; run by the DeepSeek handoff."""
import json
import tempfile
import unittest
from pathlib import Path

from bridge.diplomacy_operations import catalog, query, response
from eu4harness.diplomacy_owner_v1_20261022 import OwnerV1Adapter
from eu4harness.v32_diplomacy_tools_20261020 import QUERY_TOOL, RESPONSE_TOOL, PREVIEW_TOOL, build_connects_no_send


class SourceAPI:
    def capabilities(self):
        return {"parameterized_actions": {"offer_loan": ["amount", "interest_percent", "duration_months"]},
                "typed_rebels": {"parameter_fields_by_action": {
                    "support_rebels": ["actor", "target", "faction_id"],
                    "stop_supporting_rebels": ["actor", "target"]}}}

    def list_actions(self, **kwargs):
        return [{"action": "offer_loan", "category": "economy"},
                {"action": "support_rebels", "category": "covert", "route": "typed_rebels"},
                {"action": "stop_supporting_rebels", "category": "covert", "route": "typed_rebels"},
                {"action": "select_rival", "category": "relations", "route": "independent_command"}]

    def validate(self, request):
        return request


class OperationsTests(unittest.TestCase):
    def test_rebel_parameters_are_action_specific(self):
        rows = {row["action"]: row for row in catalog(SourceAPI())["actions"]}
        self.assertIn("faction_id", rows["support_rebels"]["parameter_fields"])
        self.assertNotIn("faction_id", rows["stop_supporting_rebels"]["parameter_fields"])
        self.assertFalse(rows["support_rebels"]["native_preview"])
        self.assertTrue(rows["offer_loan"]["native_preview"])
        self.assertEqual(rows["offer_loan"]["route"], "ordinary_tag")
        self.assertEqual(rows["support_rebels"]["route"], "typed_rebels")
        self.assertFalse(rows["select_rival"]["native_preview"])

    def test_query_needs_no_publisher(self):
        request = {"request_id": "query-1", "action": "offer_loan", "parameters": {}}
        result = query(SourceAPI(), request)
        self.assertEqual(result["requests_published"], 0)
        self.assertEqual(result["contract"]["action"], "offer_loan")

    def test_missing_action_is_explicit(self):
        with self.assertRaises(ValueError):
            catalog(SourceAPI(), action="missing_action")

    def test_response_retains_delivery_separately(self):
        value = response({"request_id": "r1", "status": "native_observation", "observation_summary": {
            "acceptance": "unknown", "factories": [{"slot_index": 0, "decision": {
                "decision_observed": True, "pre_verified": True, "clone_verified": True,
                "unknown": False, "fault": 0, "decision_state": 2, "generated_decision": "accept",
                "reply_delivery": "unknown", "full_payload": "unknown"}}]}})
        self.assertEqual(value["generated_decisions"][0]["generated_decision"], "accept")
        self.assertEqual(value["acceptance"], "unknown")

    def test_preview_requires_loaded_build_no_send(self):
        class Backend:
            def __init__(self, build):
                self.build = Path(build)
        with tempfile.TemporaryDirectory() as root:
            Path(root, "build.json").write_text(json.dumps({"no_send": False}), encoding="utf-8")
            self.assertFalse(build_connects_no_send(Backend(root)))
            Path(root, "build.json").write_text(json.dumps({"no_send": True}), encoding="utf-8")
            self.assertTrue(build_connects_no_send(Backend(root)))
        self.assertFalse(build_connects_no_send(Backend("missing-build")))

    def test_http_query_response_and_preview_policy(self):
        self.assertEqual(OwnerV1Adapter._route("POST", "/v1/diplomacy/query", {"request": {}}),
                         (QUERY_TOOL, {"request": {}}, False))
        self.assertEqual(OwnerV1Adapter._route("GET", "/v1/requests/r1/response", None),
                         (RESPONSE_TOOL, {"request_id": "r1"}, False))
        self.assertEqual(OwnerV1Adapter._route("POST", "/v1/diplomacy/preview",
                         {"request": {}, "ttl_ms": 1000, "allow_writes": True})[0], PREVIEW_TOOL)
        with self.assertRaises(RuntimeError):
            OwnerV1Adapter._route("POST", "/v1/diplomacy/preview", {"request": {}, "ttl_ms": 1000})


if __name__ == "__main__":
    unittest.main()
