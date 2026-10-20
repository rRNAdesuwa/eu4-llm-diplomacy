from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from bridge.diplomat_availability import (
    apply_diplomat_legality,
    project_native_diplomat_context,
    validate_native_diplomat_context,
)
from bridge.native_text import EU4_ESCAPE_CODEC
from bridge.peace_rejection import (
    project_native_peace_rejection,
    validate_native_peace_rejection,
)


FIXTURE = Path(__file__).parent / "fixtures" / "r68_diplomat_real.json"


class R68DiplomatRealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def _read_source(self, key: str) -> object:
        meta = self.fixture["sources"][key]
        record = self.fixture["records"][key]
        canonical = json.dumps(
            record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        self.assertEqual(meta["record_sha256"], hashlib.sha256(canonical).hexdigest(), key)
        return record

    def test_fixture_is_bounded_and_records_real_r68_runs(self):
        self.assertLessEqual(FIXTURE.stat().st_size, 1 * 1024 * 1024)
        self.assertEqual("r68_diplomat_real_v1", self.fixture["schema"])
        capture = self.fixture["capture"]
        self.assertEqual("passed", capture["status"])
        self.assertTrue(capture["business_submission"])
        self.assertFalse(capture["real_game_replayed_by_tests"])
        self.assertEqual("passed", capture["runs"]["occupy"]["status"])
        self.assertEqual("passed", capture["runs"]["zero"]["status"])
        self.assertEqual("passed", capture["runs"]["recall"]["status"])
        self.assertGreaterEqual(len(self.fixture["sources"]), 20)
        self.assertEqual(set(self.fixture["sources"]), set(self.fixture["records"]))
        for key in self.fixture["sources"]:
            self.assertTrue(self.fixture["sources"][key]["path"])
            self.assertGreater(self.fixture["sources"][key]["bytes"], 0)
            self.assertRegex(self.fixture["sources"][key]["sha256"], r"^[0-9a-f]{64}$")
            self._read_source(key)

    def test_generic_insult_mor_and_zero_diplomat_recall_are_projected(self):
        expected = self.fixture["expected"]

        generic_cases = (
            ("mlo", "mlo_native", "mlo_inspection", "improve_relations"),
            ("mor", "mor_native", "mor_inspection", "improve_relations"),
            ("recall", "stop_native", "stop_inspection", "stop_improving_relations"),
        )
        for name, native_key, public_key, action_id in generic_cases:
            with self.subTest(action=name):
                event = self._read_source(native_key)
                target = expected[name]
                self.assertTrue(validate_native_diplomat_context(event))
                self.assertTrue(
                    ObserverSession._valid_native_inspection(
                        event,
                        action_id,
                        expected["actor"],
                        target["recipient"],
                        "initiate",
                        expected["date_raw"],
                        event["query_id"],
                        event["session_id"],
                    )
                )
                projected = project_native_diplomat_context(event)
                self.assertEqual(target["available"], projected["available_count"])
                self.assertEqual(target["required"], projected["native_requirement"])
                public = self._read_source(public_key)
                self.assertEqual(target["available"], public["resources"]["diplomats"]["available_count"])
                self.assertEqual(target["required"], public["resources"]["diplomats"]["native_requirement"])
                self.assertEqual(target["legality"], public["legality"]["status"])

        insult = self._read_source("insult_native")
        insult_expected = expected["insult"]
        self.assertTrue(
            ObserverSession._valid_native_insult_inspection(
                insult,
                "send_insult",
                expected["actor"],
                insult_expected["recipient"],
                "initiate",
                expected["date_raw"],
                insult_expected["insult_id"],
            )
        )
        self.assertTrue(insult_expected["raw_valid"])
        insult_public = self._read_source("insult_inspection")
        self.assertEqual(insult_expected["available"], insult_public["resources"]["diplomats"]["available_count"])
        self.assertEqual(insult_expected["legality"], insult_public["legality"]["status"])

        mlo_result = self._read_source("mlo_result")
        self.assertEqual("executed", mlo_result["status"])
        self.assertTrue(mlo_result["submitted"])
        self.assertEqual("executed", mlo_result["game_outcome"])
        stop_result = self._read_source("stop_result")
        self.assertEqual("executed", stop_result["status"])
        self.assertTrue(stop_result["submitted"])
        self.assertEqual("executed", stop_result["game_outcome"])

        for key, wanted in (("diplomats_occupy", 0), ("diplomats_recall", 0)):
            snapshot = self._read_source(key)
            fra = next(row for row in snapshot["countries"] if row["tag"] == "FRA")
            self.assertEqual(wanted, fra["available_diplomat_count"])

    def test_declare_and_peace_raw_validation_keep_resource_and_rule_projection(self):
        expected = self.fixture["expected"]
        declare_event = self._read_source("declare_native")
        declare = expected["declare"]
        selection = declare["selection"]
        self.assertTrue(
            ObserverSession._valid_native_declare_war_inspection(
                declare_event,
                "declare_war",
                expected["actor"],
                declare["recipient"],
                "initiate",
                expected["date_raw"],
                declare_event["query_id"],
                declare_event["session_id"],
                selection,
                [],
            )
        )
        self.assertTrue(validate_native_diplomat_context(declare_event))
        declare_public = self._read_source("declare_inspection")
        self.assertEqual(declare["available"], declare_public["resources"]["diplomats"]["available_count"])
        self.assertEqual(declare["required"], declare_public["resources"]["diplomats"]["native_requirement"])
        self.assertEqual(declare["legality"], declare_public["legality"]["status"])
        self.assertEqual(selection["casus_belli"], declare_public["parameters"]["actual"]["casus_belli"])
        self.assertEqual(selection["beneficiary"], declare_public["parameters"]["actual"]["war_goal"]["beneficiary"])

        discovery_event = self._read_source("peace_discovery_native")
        peace = expected["peace"]
        self.assertTrue(
            ObserverSession._valid_native_peace_context_inspection(
                discovery_event,
                "white_peace",
                expected["actor"],
                peace["recipient"],
                "initiate",
                expected["date_raw"],
                discovery_event["query_id"],
                discovery_event["session_id"],
            )
        )
        discovery_public = self._read_source("peace_discovery_inspection")
        self.assertEqual("unknown", discovery_public["legality"]["status"])
        self.assertEqual(
            peace["war_id"],
            discovery_public["parameters"]["candidates"][0]["war_id"],
        )

        selected_event = self._read_source("peace_selected_native")
        self.assertTrue(
            ObserverSession._valid_native_peace_empty_offer_inspection(
                selected_event,
                "white_peace",
                expected["actor"],
                peace["recipient"],
                "initiate",
                expected["date_raw"],
                peace["war_id"],
                selected_event["query_id"],
                selected_event["session_id"],
                require_wrapper_rule=True,
                expected_direction=peace["direction"],
            )
        )
        selected_public = self._read_source("peace_selected_inspection")
        self.assertEqual(peace["available"], selected_public["resources"]["diplomats"]["available_count"])
        self.assertEqual(peace["required"], selected_public["resources"]["diplomats"]["native_requirement"])
        self.assertEqual(peace["legality"], selected_public["legality"]["status"])
        self.assertEqual(peace["war_id"], selected_public["peace_context"]["war_id"])
        self.assertEqual(peace["evaluation_score_raw"], selected_public["native_evaluation"]["score_raw"])
        self.assertIn("你没有外交官", "\n".join(item["text"] for item in selected_public["legality"]["reasons"]))

        parameters = {"peace_context": {
            "war_id": peace["war_id"], "direction": peace["direction"], "terms": [],
        }}
        semantic = ObserverSession._semantic_peace_empty_offer_inspection(
            selected_event, EU4_ESCAPE_CODEC
        )
        projected = {
            "contract_version": 1,
            "action_id": "white_peace",
            "native_identifier": "peace",
            "actor": "FRA",
            "recipient": "BUR",
            "phase": "initiate",
            "decision_country": None,
            "decision_country_verified": False,
            "requested_decision_country": "FRA",
            "interface_support": {"query": "catalog_only", "execute": "unimplemented", "complete": False},
            "session": {"status": "ready", "state_id": "r68-recorded", "date_raw": expected["date_raw"], "reasons": [], "complete": True},
            "visibility": {"status": "unknown", "complete": False},
            "legality": {"status": "unknown", "reasons": [], "complete": False},
            "authorization": {"status": "available", "reasons": [], "complete": True},
            "parameters": {"requested": parameters, "actual": None, "candidates": None, "complete": False},
            "costs": {"status": "unknown", "items": [], "complete": False},
            "acceptance": {"applicability": "applicable", "complete": False, "details_available": False,
                            "items": [], "native_total": None, "predicted_response": "unknown",
                            "prediction_available": False, "scale_verified": False, "unit": "unknown"},
            "resources": {"diplomats": project_native_diplomat_context(selected_event)},
        }
        actual = DiplomacyTools._apply_peace_execution_inspection(
            projected, semantic, parameters
        )
        apply_diplomat_legality(actual)
        self.assertEqual(selected_public["legality"], actual["legality"])
        self.assertEqual(selected_public["resources"], actual["resources"])
        self.assertEqual(selected_public["peace_context"], actual["peace_context"])
        self.assertEqual(
            selected_public["native_evaluation"]["score_raw"],
            actual["native_evaluation"]["score_raw"],
        )

    def test_full_diplomacy_tools_path_persists_diplomat_reason_without_submit(self):
        native = self._read_source("mor_native")
        semantic = ObserverSession._semantic_inspection(native, {}, EU4_ESCAPE_CODEC)

        class RecordedSession:
            def __init__(self, event: dict):
                self.event = event
                self.record = {"controlled_countries": ["FRA"]}
                self.session_id = "r68-recorded-session"
                self.submit_calls: list[tuple] = []

            def health(self) -> dict:
                return {"status": "ready", "state_id": "r68-recorded", "date_raw": 56552592,
                        "reasons": [], "complete": True}

            def installation_capabilities(self):
                return frozenset({
                    "native_improve_relations_query",
                    "native_improve_relations_submission",
                })

            def inspect_improve_relations(self, *args):
                return copy.deepcopy(self.event)

            def submit_improve_relations(self, *args):
                self.submit_calls.append(args)
                return {"status": "submitted"}

        session = RecordedSession(semantic)
        journal = DurableJournal(":memory:", "r68-recorded", session.session_id)
        try:
            api = DiplomacyTools(journal, session)
            inspection = api.inspect_diplomatic_action(
                "improve_relations", "FRA", "MOR"
            )
            self.assertEqual("unavailable", inspection["legality"]["status"])
            self.assertEqual(0, inspection["resources"]["diplomats"]["available_count"])
            self.assertEqual("native_rule", inspection["resources"]["diplomats"]["source"])

            request_id = "r68-recorded-invalid"
            result = api.execute_diplomatic_action(
                request_id, "improve_relations", "FRA", "MOR"
            )
            self.assertEqual("invalidated", result["status"])
            self.assertFalse(result["submitted"])
            self.assertEqual([], session.submit_calls)
            self.assertEqual("NATIVE_DIPLOMAT_UNAVAILABLE", result["result"]["reason"]["code"])
            self.assertEqual("native_rule", result["result"]["reason"]["source"])

            reopened = api.get_diplomatic_result(request_id)
            self.assertEqual("invalidated", reopened["status"])
            self.assertFalse(reopened["submitted"])
            self.assertEqual(result["result"], reopened["result"])
            self.assertEqual("NATIVE_DIPLOMAT_UNAVAILABLE", reopened["result"]["reason"]["code"])
        finally:
            journal.close()

    @staticmethod
    def _write_replay_installation(root: Path, session_id: str) -> Path:
        installation = root / "installation.json"
        installation.write_text(json.dumps({
            "experiment_id": "r68-diplomat-replay",
            "session_id": session_id,
            "pid": 1,
            "creation_filetime": 116444736000000000,
            "dll_sha256": "fixture",
        }), encoding="utf-8")
        (root / "control-probe.jsonl").write_text(json.dumps({
            "event": "diplomacy_observer_installed",
            "session_id": session_id,
            "native_insult_submission": True,
            "native_declare_war_submission": True,
        }) + "\n", encoding="utf-8")
        return installation

    def _replay_alliance_rejection(self, source_key: str, action_id: str) -> dict:
        event = self._read_source(source_key)
        errors: list[str] = []
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            session = ObserverSession(
                self._write_replay_installation(root, event["session_id"]),
                root / "recorded-game.exe",
            )
            log = root / "control-probe.jsonl"

            def publish_rejection() -> None:
                deadline = time.monotonic() + 2.0
                request = root / "diplomacy-execute.req"
                while time.monotonic() < deadline and not request.exists():
                    time.sleep(0.002)
                if not request.exists():
                    errors.append("request was not published")
                    return
                request.unlink(missing_ok=True)
                with log.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(event, ensure_ascii=False) + "\n")

            worker = threading.Thread(target=publish_rejection)
            worker.start()
            started = time.monotonic()
            if action_id == "send_insult":
                result = session.submit_send_insult(
                    event["request_id"], event["actor"], event["recipient"],
                    event["phase"], event["date_raw"], timeout=1.5,
                )
            else:
                parameters = self._read_source("declare_inspection")["parameters"]["actual"]
                result = session.submit_declare_war(
                    event["request_id"], event["actor"], event["recipient"],
                    event["phase"], event["date_raw"], parameters, timeout=1.5,
                )
            elapsed = time.monotonic() - started
            worker.join(2.0)
            self.assertFalse(worker.is_alive())
            self.assertEqual([], errors)
            self.assertLess(elapsed, 1.0)
            self.assertFalse((root / "diplomacy-execute.req").exists())
            return result

    def test_generic_and_declare_native_rejections_are_immediate_and_bound(self):
        for action_id, native_key, public_key, result_key in (
            ("send_insult", "blocked_insult_native", "blocked_insult_public", "blocked_insult_result"),
            ("declare_war", "blocked_declare_native", "blocked_declare_public", "blocked_declare_result"),
        ):
            with self.subTest(action=action_id):
                event = self._read_source(native_key)
                public = self._read_source(public_key)
                result_file = self._read_source(result_key)
                self.assertEqual("failed", public["status"])
                self.assertFalse(public["submitted"])
                self.assertTrue(public["binding_complete"])
                self.assertEqual("NATIVE_DIPLOMAT_UNAVAILABLE", public["reason"]["code"])
                self.assertEqual("unavailable", public["legality"]["status"])
                self.assertEqual("invalidated", result_file["status"])
                self.assertFalse(result_file["submitted"])
                self.assertEqual(action_id, result_file["action_id"])
                self.assertEqual("NATIVE_DIPLOMAT_UNAVAILABLE", result_file["result"]["reason"]["code"])

                replay = self._replay_alliance_rejection(native_key, action_id)
                self.assertEqual("failed", replay["status"])
                self.assertFalse(replay["submitted"])
                self.assertTrue(replay["binding_complete"])
                self.assertEqual("NATIVE_DIPLOMAT_UNAVAILABLE", replay["reason_code"])
                self.assertEqual("native_rule", replay["reason"]["source"])
                self.assertEqual("unavailable", replay["legality"]["status"])

    def test_peace_rejection_has_explicit_chinese_diplomat_reason(self):
        event = self._read_source("blocked_peace_native")
        public = self._read_source("blocked_peace_public")
        recorded = self._read_source("blocked_peace_result")
        expected = self.fixture["expected"]["peace"]
        self.assertTrue(validate_native_peace_rejection(
            event,
            request_id=event["request_id"],
            session_id=event["session_id"],
            action_id=event["action_id"],
            actor=event["actor"],
            recipient=event["recipient"],
            phase=event["phase"],
            date_raw=event["date_raw"],
            war_id=expected["war_id"],
            direction=expected["direction"],
        ))
        projected = project_native_peace_rejection(event, EU4_ESCAPE_CODEC)
        self.assertIsNotNone(projected)
        assert projected is not None
        self.assertEqual("NATIVE_DIPLOMAT_UNAVAILABLE", projected["reason_code"])
        self.assertEqual("diplomat_availability", projected["reason"]["stage"])
        self.assertEqual("native_rule", projected["reason"]["source"])
        self.assertEqual("unavailable", projected["legality"]["status"])
        self.assertFalse(projected["submitted"])
        self.assertTrue(projected["binding_complete"])
        self.assertIn("空闲外交官", projected["reason"]["text"])
        self.assertIn("0", projected["reason"]["text"])
        self.assertNotIn("session_id", json.dumps(projected, ensure_ascii=False))
        self.assertNotIn("native_diagnostic_hex", json.dumps(projected, ensure_ascii=False))
        self.assertEqual("failed", public["status"])
        self.assertEqual("NATIVE_DIPLOMAT_UNAVAILABLE", public["reason"]["code"])
        self.assertEqual("invalidated", recorded["status"])
        self.assertEqual("NATIVE_DIPLOMAT_UNAVAILABLE", recorded["result"]["reason"]["code"])


if __name__ == "__main__":
    unittest.main()
