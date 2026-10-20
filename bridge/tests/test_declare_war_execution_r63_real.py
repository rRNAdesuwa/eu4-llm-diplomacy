from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from bridge.diplomacy import ObserverSession


FIXTURE = (Path(__file__).parent / "fixtures"
           / "declare_war_r63_execution_real.json")


class DeclareWarExecutionR63RealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def _submission_args(self) -> tuple:
        f = self.fixture
        return (f["request_id"], f["session_id"], f["actor"],
                f["recipient"], f["phase"], f["date_raw"], f["parameters"])

    def test_real_submission_and_execution_project_all_three_lists(self) -> None:
        f = self.fixture
        request_id, session_id, actor, recipient, phase, date_raw, parameters = (
            self._submission_args())
        submission = f["submission"]
        execution = f["execution"]
        self.assertTrue(ObserverSession._valid_native_declare_war_submission_result(
            submission, request_id, session_id, actor, recipient, phase,
            date_raw, parameters))
        receipt = ObserverSession._public_native_declare_war_submission_receipt(
            submission, request_id, actor, recipient, phase, date_raw,
            parameters)
        self.assertIsNotNone(receipt)
        assert receipt is not None
        for field in ("call_allies", "promise_land_to", "co_belligerents"):
            self.assertEqual(f["expected"][field], receipt[field])

        result = ObserverSession._public_native_declare_war_execution_result(
            execution, request_id, session_id, actor, recipient, phase,
            date_raw, parameters)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual("executed", result["outcome"])
        self.assertTrue(result["execution_verified"])
        self.assertFalse(result["war_before"])
        self.assertTrue(result["war_after"])
        for field in ("call_allies", "promise_land_to", "co_belligerents"):
            self.assertEqual(f["expected"][field], result[field])

    def test_real_csv_echo_tampering_is_rejected_at_both_layers(self) -> None:
        f = self.fixture
        request_id, session_id, actor, recipient, phase, date_raw, parameters = (
            self._submission_args())
        submission = copy.deepcopy(f["submission"])
        submission["co_belligerents_csv"] = "SAV"
        self.assertFalse(ObserverSession._valid_native_declare_war_submission_result(
            submission, request_id, session_id, actor, recipient, phase,
            date_raw, parameters))
        self.assertIsNone(ObserverSession._public_native_declare_war_submission_receipt(
            submission, request_id, actor, recipient, phase, date_raw,
            parameters))

        execution = copy.deepcopy(f["execution"])
        execution["promise_land_to_csv"] = "-"
        self.assertIsNone(ObserverSession._public_native_declare_war_execution_result(
            execution, request_id, session_id, actor, recipient, phase,
            date_raw, parameters))


if __name__ == "__main__":
    unittest.main()
