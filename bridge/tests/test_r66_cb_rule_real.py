from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bridge.declarewar_peace_options import validate_native_peace_options
from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from bridge.native_text import EU4_ESCAPE_CODEC


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "r66_cb_rule_real.json"


class R66CBRuleRealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    @staticmethod
    def _source_path(meta: dict) -> Path:
        return ROOT / Path(meta["path"])

    def _read_source(self, meta: dict) -> object:
        path = self._source_path(meta)
        self.assertTrue(path.is_file(), path)
        raw_file = path.read_bytes()
        self.assertEqual(meta["bytes"], len(raw_file))
        self.assertEqual(meta["sha256"], hashlib.sha256(raw_file).hexdigest())
        if "line" in meta:
            lines = raw_file.splitlines()
            raw_line = lines[meta["line"] - 1]
            self.assertEqual(meta["line_bytes"], len(raw_line))
            self.assertEqual(meta["line_sha256"],
                             hashlib.sha256(raw_line).hexdigest())
            return json.loads(raw_line.decode("utf-8"))
        return json.loads(raw_file.decode("utf-8"))

    @staticmethod
    def _selection(case: dict) -> dict:
        event = case["event"]
        return {
            "casus_belli": event["requested_casus_belli"],
            "province_id": event["requested_province_id"],
            "beneficiary": event["requested_beneficiary"],
        }

    def test_real_source_events_bind_and_project_current_cb_tables(self):
        report = self.fixture["source_report"]
        report_path = self._source_path(report)
        self.assertTrue(report_path.is_file())
        self.assertEqual(report["sha256"],
                         hashlib.sha256(report_path.read_bytes()).hexdigest())

        for name, case in self.fixture["cases"].items():
            with self.subTest(case=name):
                event = self._read_source(case["source"]["native"])
                public_snapshot = self._read_source(case["source"]["public"])
                self.assertEqual(case["event"], event)
                self.assertEqual(case["public_snapshot"], public_snapshot)
                self.assertEqual("native_declare_war_inspection", event["event"])
                self.assertTrue(validate_native_peace_options(
                    event["native_peace_options"]))
                self.assertTrue(ObserverSession._valid_native_declare_war_inspection(
                    event, "declare_war", event["actor"], event["recipient"],
                    event["phase"], event["date_raw"], event["query_id"],
                    event["session_id"], self._selection(case)))

                projected = ObserverSession._semantic_declare_war_inspection(
                    event, EU4_ESCAPE_CODEC)
                rules = projected["peace_term_rules"]
                self.assertEqual(
                    "native_declare_war_peace_options", rules["source"])
                self.assertFalse(rules["selection_rules_evaluated"])
                self.assertEqual(
                    case["expected"]["current_target_evaluation_required"],
                    {side: rules[side]["target_evaluation_required"]
                     for side in ("disabled", "attacker_declared",
                                  "defender_declared")})
                # A non-empty declared side is only the CB/goal declaration
                # table.  It still requires target evaluation; it is not an
                # already-proven runtime legality result.
                for side in ("attacker_declared", "defender_declared"):
                    if rules[side]["records"]:
                        self.assertTrue(rules[side]["target_evaluation_required"])

    def test_full_diplomacy_inspect_retains_peace_term_rules(self):
        """Replay each real event through the complete public inspect facade."""

        for name, case in self.fixture["cases"].items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as td:
                temp = Path(td)
                event = case["event"]
                session_id = "r66-cb-inspect-" + name
                (temp / "installation.json").write_text(json.dumps({
                    "experiment_id": "r66-cb-real",
                    "session_id": session_id,
                    "pid": 1,
                    "creation_filetime": 116444736000000000,
                    "dll_sha256": "fixture",
                }), encoding="utf-8")
                (temp / "control-probe.jsonl").write_text(
                    json.dumps({
                        "event": "diplomacy_observer_installed",
                        "session_id": session_id,
                        "native_declare_war_query": True,
                    }) + "\n", encoding="utf-8")
                session = ObserverSession(temp / "installation.json",
                                          temp / "eu4.exe")
                semantic = ObserverSession._semantic_declare_war_inspection(
                    event, EU4_ESCAPE_CODEC)
                parameters = case["request"]["parameters"]
                ready = {
                    "status": "ready", "state_id": "r66-cb-fixture",
                    "date_raw": event["date_raw"], "reasons": [],
                    "complete": True,
                }
                journal = DurableJournal(":memory:", "r66-cb-real",
                                         session.session_id)
                try:
                    with patch.object(session, "health", return_value=ready), \
                            patch.object(session, "inspect_declare_war",
                                         return_value=semantic) as inspector:
                        result = DiplomacyTools(
                            journal, session).inspect_diplomatic_action(
                                "declare_war", event["actor"], event["recipient"],
                                event["phase"], parameters)
                    self.assertEqual(1, inspector.call_count)
                    self.assertEqual(
                        semantic["peace_term_rules"], result["peace_term_rules"])
                    self.assertEqual(
                        "native_declare_war_peace_options",
                        result["peace_term_rules"]["source"])
                    self.assertFalse(
                        result["peace_term_rules"]["selection_rules_evaluated"])
                    self.assertNotIn("native_peace_options",
                                     json.dumps(result, ensure_ascii=False))
                finally:
                    journal.close()


if __name__ == "__main__":
    unittest.main()
