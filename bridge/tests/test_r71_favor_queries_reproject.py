"""Small offline checks for the real R71 favor-query fixture."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from bridge.diplomacy import DiplomacyTools
from bridge.diplomacy_journal import DurableJournal
from bridge.favor_trade import SUBMISSION_CAPABILITY
from work.reproject_r71_favor_queries import (
    ACTION_ID,
    ACTOR,
    COOLDOWN_TEXT,
    PHASE,
    PAP_CASH_TEXT,
    _case_checks,
    reproject_case,
    ReplaySession,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "bridge/tests/fixtures/r71_favor_queries_real.json"


class R71FavorQueriesReprojectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.cases = {case["recipient"]: case for case in cls.fixture["cases"]}

    def test_all_eight_events_use_full_tools_and_keep_specific_legality(self) -> None:
        self.assertEqual(len(self.cases), 8)
        capabilities = frozenset(self.fixture["capabilities"])
        for case in self.fixture["cases"]:
            raw = case["raw"]
            projected = reproject_case(
                raw, case["actor"], case["recipient"], self.fixture["health"],
                capabilities, self.fixture["session_id"])
            checks = _case_checks(
                raw, projected["public"], projected["semantic"],
                self.fixture["health"], projected["session"],
                case["actor"], case["recipient"])
            self.assertTrue(all(checks.values()), (case["name"], checks))
            self.assertEqual(
                projected["public"]["legality"]["status"],
                case["expected"]["legality_status"],
            )
            self.assertEqual(
                projected["public"]["legality"]["complete"],
                case["expected"]["legality_complete"],
            )
            self.assertEqual(
                projected["public"]["native_diagnostic"]["text"],
                case["expected"]["native_diagnostic_text"],
            )
            self.assertIn(COOLDOWN_TEXT, case["expected"]["native_diagnostic_text"])
            if case["recipient"] == "PAP":
                self.assertIn(PAP_CASH_TEXT, case["expected"]["native_diagnostic_text"])
                self.assertIn("12", case["expected"]["native_diagnostic_text"])
            self.assertEqual(projected["session"].native_query_calls, 0)
            self.assertEqual(projected["session"].submit_calls, 0)
            self.assertEqual(len(case["source_raw_sha256"]), 64)
            self.assertEqual(
                raw["action_id"], ACTION_ID)
            self.assertEqual(raw["phase"], PHASE)

    def test_pap_execute_is_blocked_with_specific_native_reason(self) -> None:
        case = self.cases["PAP"]
        capabilities = frozenset(
            set(self.fixture["capabilities"]) | {SUBMISSION_CAPABILITY})
        session = ReplaySession(
            case["raw"], self.fixture["health"], capabilities,
            self.fixture["session_id"], ACTOR, "PAP")
        journal = DurableJournal(":memory:", "r71-reproject-test", session.session_id)
        try:
            result = DiplomacyTools(journal, session).execute_diplomatic_action(
                "r71_pap_blocked", ACTION_ID, ACTOR, "PAP")
        finally:
            journal.close()

        self.assertEqual(result["status"], "invalidated")
        self.assertFalse(result["submitted"])
        self.assertEqual(session.native_query_calls, 0)
        self.assertEqual(session.submit_calls, 0)
        stored = result["result"]
        self.assertEqual(stored["reason"]["code"], "NATIVE_LEGALITY_UNAVAILABLE")
        self.assertIn(COOLDOWN_TEXT, stored["reason"]["text"])
        self.assertIn(PAP_CASH_TEXT, stored["reason"]["text"])
        self.assertIn("12", stored["reason"]["text"])
        self.assertEqual(
            stored["legality_reasons"][0]["code"], "NATIVE_VALIDITY_FALSE")
        self.assertEqual(
            stored["legality_reasons"][0]["text"], stored["reason"]["text"].split(
                "游戏规则禁止本次操作：", 1)[-1])


if __name__ == "__main__":
    unittest.main()
