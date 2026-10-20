import copy
import hashlib
import json
import unittest
from pathlib import Path

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.native_text import EU4_ESCAPE_CODEC
from bridge.peace_rejection import (
    project_native_peace_rejection,
    validate_native_peace_rejection,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "bridge/tests/fixtures/r67_ally_peace_real.json"


class TestR67AllyPeaceReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    @staticmethod
    def _file_sha256(path):
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(131072), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _selected_candidate(public):
        candidates = public["native_provinces"].get("candidates", [])
        selected = [row for row in candidates if row.get("selected")]
        if len(selected) != 1:
            return None
        return selected[0]

    def test_fixture_is_bounded_and_source_metadata_is_preserved(self):
        self.assertLessEqual(FIXTURE_PATH.stat().st_size, 300 * 1024)
        self.assertEqual("r67_ally_peace_real_v1", self.fixture["schema"])
        self.assertEqual("passed", self.fixture["queries"]["status"])
        self.assertFalse(self.fixture["queries"]["business_submission"])
        self.assertTrue(all(self.fixture["queries"]["checks"].values()))

        for case in self.fixture["queries"]["cases"].values():
            for source_key in ("input", "native_event_json", "public"):
                source = case["source"][source_key]
                path = ROOT / source["path"]
                self.assertTrue(path.is_file(), source["path"])
                self.assertEqual(source["bytes"], path.stat().st_size)
                self.assertEqual(source["sha256"], self._file_sha256(path))
            stream = case["source"]["native_event_stream"]
            line_no = stream["line"]
            self.assertGreater(line_no, 0)
            with (ROOT / stream["path"]).open("rb") as handle:
                line = next(
                    line for no, line in enumerate(handle, 1) if no == line_no
                )
            self.assertEqual(stream["line_bytes"], len(line))
            self.assertEqual(stream["line_sha256"], hashlib.sha256(line).hexdigest())

        for section in ("blocked_execution", "outbound_execution"):
            self.assertEqual("passed", self.fixture[section]["status"])
            self.assertTrue(all(self.fixture[section]["checks"].values()))

    def test_four_real_queries_validate_and_keep_third_beneficiary_effects(self):
        expected_status = {
            "actor_94_FRA": "unavailable",
            "subject_88_ORL": "available",
            "ally_193_SAV": "unavailable",
            "ally_91_SAV": "unavailable",
        }
        for name, case in self.fixture["queries"]["cases"].items():
            event = case["native_event"]
            context = case["input"]["peace_context"]
            term = context["terms"][0]
            selection = {
                "war_id": context["war_id"],
                "direction": context["direction"],
                "province_ids": list(term["province_ids"]),
                "beneficiary": term["beneficiary"],
            }
            self.assertTrue(
                ObserverSession._valid_native_peace_province_offer_inspection(
                    event,
                    event["action_id"],
                    event["actor"],
                    event["recipient"],
                    event["phase"],
                    event["date_raw"],
                    selection,
                    event["query_id"],
                    event["session_id"],
                ),
                name,
            )
            self.assertTrue(
                ObserverSession._valid_native_selected_rules(
                    event["native_selected_rules"],
                    event["native_payload"],
                    minimum_selected_terms=1,
                ),
            )
            self.assertTrue(case["expected"]["native_validator"])
            self.assertTrue(case["expected"]["native_beneficiary_matches"])

            semantic = ObserverSession._semantic_peace_province_offer_inspection(
                event, EU4_ESCAPE_CODEC
            )
            actual = DiplomacyTools._apply_peace_execution_inspection(
                {
                    "interface_support": {},
                    "session": {"date_raw": event["date_raw"]},
                    "acceptance": {},
                    "costs": {},
                },
                semantic,
                case["input"],
            )
            expected = case["public_snapshot"]
            self.assertEqual(expected_status[name], actual["legality"]["status"])
            self.assertEqual(
                case["expected"]["legality_complete"],
                actual["legality"]["complete"],
            )
            self.assertEqual(
                case["expected"]["selection_delta_raw"],
                actual["native_provinces"]["selection_delta_raw"],
            )
            self.assertEqual(
                case["expected"]["aggregate_score_raw"],
                actual["costs"]["native_evaluation"]["aggregate_score_raw"],
            )
            self.assertIs(actual["peace_consequences"]["requested_terms_applied"], True)
            self.assertEqual(
                expected["peace_consequences"], actual["peace_consequences"]
            )
            selected = self._selected_candidate(actual)
            self.assertIsNotNone(selected)
            self.assertEqual(term["beneficiary"], selected["beneficiary"])
            self.assertEqual(term["province_ids"][0], selected["province_id"])

            factor_items = actual["acceptance"]["items"]
            self.assertGreaterEqual(len(factor_items), 7)
            self.assertTrue(all(item.get("text") for item in factor_items))
            if name == "subject_88_ORL":
                self.assertIn(
                    "盟友的相对实力",
                    "\n".join(item["text"] for item in factor_items),
                )
                self.assertEqual(
                    1000,
                    actual["peace_consequences"]["overextension"]
                    ["countries"][0]["scale"],
                )
                overextension = next(
                    row
                    for row in actual["peace_consequences"]["overextension"][
                        "countries"
                    ]
                    if row["country"] == "ORL"
                )
                self.assertEqual(120, overextension["delta_raw"])
                self.assertEqual(120, overextension["projected_raw"])
                territorial = next(
                    row
                    for row in actual["peace_consequences"]["territorial"]
                    if row["country"] == "ORL"
                )
                self.assertEqual(120, territorial["overextension_added_raw"])
                self.assertEqual("FRA", actual["peace_consequences"][
                    "diplomatic_power"]["country"])
            elif name == "actor_94_FRA":
                self.assertIn("核心化", actual["legality"]["reasons"][0]["text"])
            else:
                reason = actual["legality"]["reasons"][0]["text"]
                self.assertIn("不想要", reason)
                self.assertIn("核心化", reason)

            rendered = json.dumps(actual, ensure_ascii=False)
            self.assertNotIn("term_pointer", rendered)
            self.assertNotIn("province_pointer", rendered)

    def test_blocked_native_ally_rejection_is_bound_and_classified(self):
        section = self.fixture["blocked_execution"]
        event = section["native_rejection"]
        kwargs = {
            "request_id": event["request_id"],
            "session_id": event["session_id"],
            "action_id": event["action_id"],
            "actor": event["actor"],
            "recipient": event["recipient"],
            "phase": event["phase"],
            "date_raw": event["date_raw"],
            "war_id": event["war_id"],
            "direction": event["direction"],
        }
        self.assertTrue(validate_native_peace_rejection(event, **kwargs))
        public = project_native_peace_rejection(event, EU4_ESCAPE_CODEC)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertEqual(
            "NATIVE_PEACE_SELECTED_TERM_RULE_UNAVAILABLE", public["reason_code"]
        )
        self.assertEqual("selected_rules", public["reason"]["stage"])
        self.assertEqual("native_rule", public["reason"]["source"])
        self.assertIs(public["reason"]["complete"], False)
        self.assertEqual("unavailable", public["legality"]["status"])
        self.assertIn("不想要", public["diagnostic"]["text"])
        self.assertIn("核心化", public["diagnostic"]["text"])
        self.assertFalse(
            validate_native_peace_rejection(
                event, **dict(kwargs, request_id="r67_wrong_request")
            )
        )

    def test_real_outbound_receipt_and_rejected_result_keep_roles(self):
        section = self.fixture["outbound_execution"]
        request = section["request"]
        params = request["parameters"]["execute"]
        submission = section["submission_event"]
        execution = section["execution_event"]
        common = {
            "request_id": request["request_id"],
            "session_id": execution["session_id"],
            "actor": request["actor"],
            "recipient": request["recipient"],
            "phase": request["phase"],
            "expected_date": request["expected_date_raw"],
            "action_id": request["action_id"],
            "parameters": params,
        }
        self.assertTrue(
            ObserverSession._valid_native_peace_submission_result(
                submission, **common
            )
        )
        self.assertTrue(
            ObserverSession._valid_native_peace_execution_result(
                execution, **common
            )
        )
        receipt = ObserverSession._public_native_peace_submission_receipt(
            submission,
            request["request_id"],
            request["actor"],
            request["recipient"],
            request["phase"],
            request["expected_date_raw"],
            request["action_id"],
            params,
        )
        self.assertIsNotNone(receipt)
        assert receipt is not None
        self.assertTrue(receipt["submitted"])
        self.assertEqual("ORL", receipt["beneficiary"])
        self.assertEqual(1000, receipt["amount_raw"])
        self.assertEqual([88], receipt["province_ids"])

        public = ObserverSession._public_native_peace_execution_result(
            execution,
            request["request_id"],
            execution["session_id"],
            request["actor"],
            request["recipient"],
            request["phase"],
            request["expected_date_raw"],
            request["action_id"],
            params,
        )
        self.assertIsNotNone(public)
        assert public is not None
        self.assertEqual("rejected", public["outcome"])
        self.assertEqual("ORL", public["beneficiary"])
        self.assertEqual(1000, public["amount_raw"])
        self.assertTrue(public["war_after"])
        self.assertEqual("BUR", public["effects"]["money"]["payer"])
        self.assertEqual(0, public["effects"]["money"]["paid_raw"])
        province = public["effects"]["provinces"][0]
        self.assertEqual("ORL", province["beneficiary"])
        self.assertEqual("BUR", province["owner_before"])
        self.assertEqual("BUR", province["owner_after"])
        self.assertFalse(province["verified"])

        expected_result = section["result"]["result"]
        self.assertEqual("ORL", expected_result["beneficiary"])
        self.assertEqual(1000, expected_result["amount_raw"])
        self.assertEqual("BUR", expected_result["effects"]["money"]["payer"])
        self.assertEqual("BUR", expected_result["effects"]["provinces"][0]["owner_after"])

        bad = copy.deepcopy(execution)
        bad["beneficiary"] = "FRA"
        self.assertFalse(
            ObserverSession._valid_native_peace_execution_result(
                bad, **common
            )
        )

        selected = section["selected_inspection"]
        self.assertEqual("ORL", selected["native_provinces"]["selected_beneficiary"])
        self.assertEqual(10, selected["native_provinces"]["selection_delta_raw"])
        self.assertEqual(1000, selected["native_money"]["requested_amount_raw"])
        self.assertTrue(selected["native_selected_rules"]["available"])


if __name__ == "__main__":
    unittest.main()
