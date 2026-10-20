from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest

from bridge.declarewar_details import valid_declare_war_details
from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.native_text import EU4_ESCAPE_CODEC


FIXTURE = (Path(__file__).parent / "fixtures" /
           "declarewar_details_r62_real.json")


class _SemanticSession:
    """Small read-only session double for the public DiplomacyTools layer."""

    def __init__(self, event: dict):
        self._event = event

    def health(self) -> dict:
        return {
            "status": "ready",
            "state_id": "r62-real-fixture",
            "date_raw": self._event["date_raw"],
            "reasons": [],
            "complete": True,
        }

    def installation_capabilities(self) -> frozenset[str]:
        return frozenset({"native_declare_war_query"})

    def inspect_declare_war(self, action_id: str, actor: str,
                            recipient: str, phase: str,
                            parameters: dict | None = None) -> dict:
        self._last = (action_id, actor, recipient, phase, parameters)
        return ObserverSession._semantic_declare_war_inspection(
            self._event, EU4_ESCAPE_CODEC)


class DeclareWarDetailsR62RealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.repo = Path(__file__).resolve().parents[2]
        source_info = cls.payload["source"]
        cls.source = cls.repo / source_info["events_path"]
        cls.source_bytes = cls.source.read_bytes()
        cls.lines = cls.source_bytes.decode("utf-8").splitlines()
        cls.source_cache = {source_info["events_path"]: (
            source_info, cls.source_bytes, cls.lines)
        }
        for extra in cls.payload.get("additional_sources", []):
            path = cls.repo / extra["events_path"]
            data = path.read_bytes()
            cls.source_cache[extra["events_path"]] = (
                extra, data, data.decode("utf-8").splitlines())

    def _records(self) -> list[dict]:
        return self.payload["events"]

    @staticmethod
    def _selection(event: dict) -> dict | None:
        if event.get("selection_requested") is not True:
            return None
        return {
            "casus_belli": event["requested_casus_belli"],
            "province_id": event["requested_province_id"],
            "beneficiary": event["requested_beneficiary"],
        }

    def _assert_provenance(self, record: dict) -> dict:
        provenance = record.get("provenance")
        source_key = (provenance or self.payload["source"])["events_path"]
        source_info, source_bytes, lines = self.source_cache[source_key]
        self.assertEqual(source_info["events_bytes"], len(source_bytes))
        self.assertEqual(source_info["events_sha256"],
                         hashlib.sha256(source_bytes).hexdigest())
        line_no = record["line"]
        raw = lines[line_no - 1]
        self.assertEqual(record["line_bytes"], len(raw.encode("utf-8")))
        self.assertEqual(record["line_sha256"],
                         hashlib.sha256(raw.encode("utf-8")).hexdigest())
        if provenance is not None:
            self.assertEqual(provenance["line"], line_no)
            self.assertEqual(provenance["line_bytes"], record["line_bytes"])
            self.assertEqual(provenance["line_sha256"], record["line_sha256"])
        event = record["event"]
        self.assertEqual(record["line_sha256"],
                         hashlib.sha256(json.dumps(
                             event, ensure_ascii=False, separators=(",", ":")
                         ).encode("utf-8")).hexdigest())
        return event

    def test_real_source_provenance_and_three_native_validators(self):
        source_info = self.payload["source"]
        self.assertEqual(source_info["events_bytes"], len(self.source_bytes))
        self.assertEqual(source_info["events_sha256"],
                         hashlib.sha256(self.source_bytes).hexdigest())
        self.assertEqual(8, len(self._records()))
        for record in self._records():
            event = self._assert_provenance(record)
            self.assertEqual("native_declare_war_inspection", event["event"])
            self.assertTrue(valid_declare_war_details(event["native_details"]))
            self.assertTrue(ObserverSession._valid_native_declare_war_inspection(
                event, "declare_war", "FRA", event["recipient"], "initiate",
                event["date_raw"], event["query_id"], event["session_id"],
                self._selection(event)))

    def test_semantic_projection_keeps_real_chinese_details_and_cost_scale(self):
        for record in self._records():
            event = record["event"]
            semantic = ObserverSession._semantic_declare_war_inspection(
                event, EU4_ESCAPE_CODEC)
            expected_details = copy.deepcopy(record["expected"]["details"])
            expected_details.pop("context", None)
            self.assertEqual(expected_details, semantic["declaration_details"])
            details = semantic["declaration_details"]
            self.assertTrue(details["complete"])
            self.assertTrue(details["description_complete"])
            self.assertTrue(any("\u4e00" <= char <= "\u9fff"
                                for char in details["description"]))
            self.assertEqual(record["expected"]["goal_applicable"],
                             details["war_goal"]["applicable"])
            costs = semantic["costs"]
            expected_costs = record["expected"]["costs"]
            raw = costs["raw_components"]
            self.assertEqual(expected_costs["scale"], raw["stability_scale"])
            self.assertEqual(1000, raw["stability_scale"])
            self.assertEqual(expected_costs["stability_hit_raw"],
                             raw["stability_hit_raw"])
            self.assertEqual(expected_costs["warex_display_raw"],
                             raw["warex_display_raw"])
            self.assertEqual(len(expected_costs["items"]), len(costs["items"]))
            for expected, actual in zip(expected_costs["items"], costs["items"]):
                for key, value in expected.items():
                    self.assertEqual(value, actual[key],
                                     f"{record['name']} cost {key}")
            self.assertIn(costs["context"],
                          {"default_parameters_unselected", "selected_parameters"})
            self.assertEqual(record["expected"]["legal_status"] == "available",
                             event["selection_matched"] is True)
            if event.get("requested_casus_belli") == "cb_trade_war_triggered":
                self.assertEqual("展现霸权", details["war_goal"]["name"])
                self.assertTrue(details["war_goal"]["applicable"])
                disabled = details["peace_conditions"][
                    "disabled_terms_description"]
                for line in (
                        "征服省份", "废除核心", "归还核心省份",
                        "解放附庸", "转移附庸", "解放国家",
                        "建立联合统治", "强迫附庸", "强迫成为朝贡国"):
                    self.assertIn(line, disabled)
                self.assertEqual(5000, raw["stability_hit_raw"])
                self.assertEqual(5000, raw["warex_display_raw"])

    def test_public_diplomacy_tools_inspect_adds_parameter_context(self):
        for record in self._records():
            event = record["event"]
            session = _SemanticSession(event)
            public = DiplomacyTools(None, session).inspect_diplomatic_action(
                "declare_war", "FRA", event["recipient"],
                parameters=record["parameters"])
            expected = record["expected"]
            self.assertEqual(expected["legal_status"],
                             public["legality"]["status"], record["name"])
            self.assertEqual(expected["details"],
                             public["declaration_details"], record["name"])
            self.assertEqual(expected["costs"]["context"],
                             public["costs"]["context"])
            self.assertEqual(1000,
                             public["costs"]["raw_components"]["stability_scale"])
            if expected["selection_matched"]:
                self.assertTrue(public["parameters"]["complete"])
                self.assertEqual("selected_parameters",
                                 public["declaration_details"]["context"])
            else:
                self.assertFalse(public["parameters"]["complete"])
                self.assertEqual("default_parameters_unselected",
                                 public["declaration_details"]["context"])
            self.assertNotIn("native_details", public)
            self.assertNotIn("frame_thread", json.dumps(public, ensure_ascii=False))
            self.assertNotIn("native_metadata_hex", json.dumps(public, ensure_ascii=False))
            if event.get("requested_casus_belli") == "cb_trade_war_triggered":
                details = public["declaration_details"]
                self.assertTrue(details["war_goal"]["applicable"])
                self.assertEqual("展现霸权", details["war_goal"]["name"])
                disabled = details["peace_conditions"][
                    "disabled_terms_description"]
                self.assertEqual(9, len([line for line in disabled.splitlines()
                                        if line.startswith("- ")]))
                self.assertEqual(5000, public["costs"][
                    "raw_components"]["stability_hit_raw"])
                self.assertEqual(5000, public["costs"][
                    "raw_components"]["warex_display_raw"])


if __name__ == "__main__":
    unittest.main()
