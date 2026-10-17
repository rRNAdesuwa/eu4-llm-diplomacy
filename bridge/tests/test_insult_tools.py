from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from bridge.native_text import EU4_ESCAPE_CODEC


FIXTURE = Path(__file__).with_name("fixtures") / "insult_r33_events.json"
WIRE_FIXTURE = Path(__file__).with_name("fixtures") / "insult_r33_execution_wire.txt"
REAL_QUERY_FIXTURE = Path(__file__).with_name("fixtures") / "insult_r33_real_queries.json"
REAL_EXECUTION_FIXTURE = Path(__file__).with_name("fixtures") / "insult_r33_real_execution.json"
COST_QUERY_FIXTURE = Path(__file__).with_name("fixtures") / "insult_r33_cost_events.json"


class InsultExecutionSession:
    def __init__(self):
        self.session_id = "insult-session"
        self.record = {"controlled_countries": ["FRA"]}
        self.capabilities = frozenset({"native_insult_query", "native_insult_submission"})
        self.submit_calls: list[tuple[str, int]] = []

    def health(self) -> dict:
        return {"status": "ready", "state_id": "ready", "date_raw": 1,
                "reasons": [], "complete": True}

    def installation_capabilities(self) -> frozenset[str]:
        return self.capabilities

    def inspect_insult(self, action_id: str, actor: str, recipient: str,
                       phase: str, insult_id: int | None = None) -> dict:
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))["query_insult"]
        raw.update({"action_id": action_id, "actor": actor, "recipient": recipient})
        if action_id == "scornful_insult":
            raw.update({"insult_id": insult_id if insult_id is not None else -2,
                        "insult_parameter_selected": insult_id is not None})
        return ObserverSession._semantic_inspection(raw, {}) | {
            "parameters": {
                "requested": ({"insult_id": insult_id} if insult_id is not None else {}),
                "actual": {"insult_id": raw["insult_id"]},
                "candidates": {"insult_id": [3, 7], "items": [], "complete": True},
                "complete": True,
            }
        }

    def submit_scornful_insult(self, request_id: str, actor: str,
                               recipient: str, phase: str, date_raw: int,
                               insult_id: int, timeout: float = 10.0) -> dict:
        self.submit_calls.append((request_id, insult_id))
        event = json.loads(FIXTURE.read_text(encoding="utf-8"))["execution"]
        event.update({"request_id": request_id, "session_id": self.session_id,
                      "actor": actor, "recipient": recipient, "phase": phase,
                      "date_raw": date_raw})
        return {"status": "submitted", "receipt": {
            "event": "native_alliance_submission_result",
            "request_id": request_id, "action_id": "scornful_insult",
            "actor": actor, "recipient": recipient, "phase": phase,
            "date_raw": date_raw, "submitted": True,
            "native_queue_verified": True, "transport_ring_receipt": True,
            "native_sequence": 7, "native_origin": 65535, "native_flags": 0,
        }}

    def submit_send_insult(self, request_id: str, actor: str,
                           recipient: str, phase: str, date_raw: int,
                           timeout: float = 10.0) -> dict:
        self.submit_calls.append((request_id, -1))
        return {"status": "submitted", "receipt": {
            "event": "native_alliance_submission_result",
            "request_id": request_id, "action_id": "send_insult",
            "actor": actor, "recipient": recipient, "phase": phase,
            "date_raw": date_raw, "submitted": True,
            "native_queue_verified": True, "transport_ring_receipt": True,
            "native_sequence": 8, "native_origin": 65535, "native_flags": 0,
        }}

    def read_native_insult_execution(self, request_id: str, actor: str,
                                     recipient: str, phase: str, date_raw: int,
                                     action_id: str = "scornful_insult",
                                     insult_id: int = 3) -> dict:
        event = json.loads(FIXTURE.read_text(encoding="utf-8"))["execution"]
        event.update({"request_id": request_id, "session_id": self.session_id,
                      "action_id": action_id, "actor": actor, "recipient": recipient,
                      "phase": phase, "date_raw": date_raw, "insult_id": insult_id})
        result = ObserverSession._public_native_insult_execution_result(
            event, request_id, self.session_id, actor, recipient, phase, date_raw,
            action_id, insult_id)
        return {"status": result["native_outcome"], "result": result}


class RealInsultQuerySession:
    """Project the bounded first A-run native events through the public API."""

    def __init__(self):
        source = json.loads(REAL_QUERY_FIXTURE.read_text(encoding="utf-8"))
        self.source = source
        self.session_id = source["queries"]["bur_send_insult"]["event"]["session_id"]
        self.date_raw = source["queries"]["bur_send_insult"]["event"]["date_raw"]
        self.record = {"controlled_countries": ["FRA"]}
        self.capabilities = frozenset({"native_insult_query", "native_insult_submission"})

    def health(self) -> dict:
        return {"status": "ready", "state_id": "real-r33", "date_raw": self.date_raw,
                "reasons": [], "complete": True}

    def installation_capabilities(self) -> frozenset[str]:
        return self.capabilities

    def inspect_insult(self, action_id: str, actor: str, recipient: str,
                       phase: str, insult_id: int | None = None) -> dict:
        if action_id == "send_insult":
            name = f"{recipient.lower()}_send_insult"
            candidate_events = []
        else:
            name = f"{recipient.lower()}_scornful_discovery"
            candidate_events = [
                candidate for item in self.source["candidate_sample"]
                if (candidate := ObserverSession._public_native_insult_candidate(
                    item["event"], EU4_ESCAPE_CODEC)) is not None
            ]
        raw = dict(self.source["queries"][name]["event"])
        native = ObserverSession._semantic_inspection(
            raw, {}, EU4_ESCAPE_CODEC, candidate_events=candidate_events)
        candidate_complete = (
            raw["candidates_complete"] is True
            and len(candidate_events) == raw["candidate_count"])
        native["parameters"]["candidates"]["complete"] = candidate_complete
        native["parameters"] = {
            "requested": ({"insult_id": insult_id} if insult_id is not None else {}),
            "actual": {"insult_id": raw["insult_id"]},
            "candidates": native["parameters"]["candidates"],
            "complete": raw["insult_id"] != -2 or candidate_complete,
        }
        return native


class RealInsultCostQuerySession:
    """Project the bounded real B inspection events used for cost evidence."""

    def __init__(self):
        source = json.loads(COST_QUERY_FIXTURE.read_text(encoding="utf-8"))
        self.source = source
        self.session_id = source["queries"]["bur_send_insult"]["event"]["session_id"]
        self.date_raw = source["queries"]["bur_send_insult"]["event"]["date_raw"]
        self.record = {"controlled_countries": ["FRA"]}
        self.capabilities = frozenset({"native_insult_query", "native_insult_submission"})

    def health(self) -> dict:
        return {"status": "ready", "state_id": "real-r33-cost", "date_raw": self.date_raw,
                "reasons": [], "complete": True}

    def installation_capabilities(self) -> frozenset[str]:
        return self.capabilities

    def inspect_insult(self, action_id: str, actor: str, recipient: str,
                       phase: str, insult_id: int | None = None) -> dict:
        key = "bur_send_insult" if action_id == "send_insult" else "gen_scornful_insult"
        raw = dict(self.source["queries"][key]["event"])
        native = ObserverSession._semantic_inspection(raw, {}, EU4_ESCAPE_CODEC)
        native["parameters"] = {
            "requested": ({"insult_id": insult_id} if insult_id is not None else {}),
            "actual": {"insult_id": raw["insult_id"]},
            "candidates": native["parameters"]["candidates"],
            "complete": True,
        }
        return native


class InsultToolsTests(unittest.TestCase):
    @staticmethod
    def _installation(root: Path, *, query_ack: object = None,
                      submission_ack: object = None,
                      caps: list[str] | None = None) -> tuple[Path, Path]:
        installation = root / "installation.json"
        installation.write_text(json.dumps({
            "experiment_id": "insult-contract", "session_id": "insult-session",
            "pid": 1, "creation_filetime": 2, "dll_sha256": "dll",
            "controlled_countries": ["FRA"], "installation_returncode": 0,
        }), encoding="utf-8")
        ack = {"event": "diplomacy_observer_installed", "session_id": "insult-session"}
        if query_ack is not None:
            ack["native_insult_query"] = query_ack
        if submission_ack is not None:
            ack["native_insult_submission"] = submission_ack
        if caps is not None:
            ack["caps"] = caps
        log = root / "control-probe.jsonl"
        log.write_text(json.dumps(ack) + "\n", encoding="utf-8")
        return installation, log

    def test_catalog_and_parameter_contract(self):
        api = DiplomacyTools(DurableJournal(":memory:", "insult-contract", "insult-session"))
        try:
            by_id = {item["action_id"]: item for item in api.list_diplomatic_actions()["actions"]}
            self.assertEqual("insult", by_id["send_insult"]["native_identifier"])
            self.assertEqual({}, by_id["send_insult"]["parameter_definitions"])
            self.assertEqual({"insult_id": {"status": "context_required"}},
                             by_id["scornful_insult"]["parameter_definitions"])
            self.assertEqual(["initiate"], list(by_id["scornful_insult"]["phases"]))
            self.assertEqual("not_applicable",
                             api.inspect_diplomatic_action("send_insult", "FRA", "SAV")
                             ["acceptance"]["applicability"])
            with self.assertRaisesRegex(ValueError, "SCORNFUL_INSULT_ID_INVALID"):
                api.inspect_diplomatic_action("scornful_insult", "FRA", "SAV",
                                              parameters={"insult_id": True})
            with self.assertRaisesRegex(ValueError, "INSULT_INITIATE_ONLY"):
                api.inspect_diplomatic_action("send_insult", "FRA", "SAV", "accept")
        finally:
            api.journal.close()

    def test_ack_is_literal_and_query2_aggregates_candidates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, log = self._installation(root, query_ack=True,
                                                    submission_ack=False,
                                                    caps=["native_insult_query",
                                                          "native_insult_submission"])
            session = ObserverSession(installation, root / "eu4.exe")
            self.assertEqual(frozenset({"native_insult_query"}),
                             session.installation_capabilities())
            fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
            request = root / "diplomacy-query.request"
            errors: list[BaseException] = []

            def writer() -> None:
                try:
                    deadline = time.monotonic() + 2
                    while not request.exists() and time.monotonic() < deadline:
                        time.sleep(0.001)
                    self.assertTrue(request.exists())
                    wire = request.read_text(encoding="ascii")
                    self.assertTrue(wire.startswith("EU4DIP_QUERY2 "))
                    self.assertEqual("-2", wire.rstrip().split()[-1])
                    discovery = fixture["query_scornful_discovery"]
                    discovery["query_id"] = wire.split()[2]
                    discovery["session_id"] = "insult-session"
                    candidates = []
                    for key in ("candidate_a", "candidate_b"):
                        candidate = fixture[key]
                        candidate["query_id"] = discovery["query_id"]
                        candidate["session_id"] = "insult-session"
                        candidates.append(candidate)
                    with log.open("a", encoding="utf-8") as stream:
                        for event in candidates + [discovery]:
                            stream.write(json.dumps(event) + "\n")
                            stream.flush()
                except BaseException as error:
                    errors.append(error)

            with patch.object(session, "health", return_value={
                    "status": "ready", "state_id": "ready", "date_raw": 1,
                    "reasons": [], "complete": True}), \
                 patch("bridge.diplomacy.probe_identity",
                       return_value={"session_id": "insult-session"}):
                thread = threading.Thread(target=writer)
                thread.start()
                result = session.inspect_insult("scornful_insult", "FRA", "SAV", "initiate")
                thread.join(timeout=2)
            if errors:
                raise errors[0]
            self.assertEqual("insult", result["family"])
            self.assertEqual(-2, result["insult_id"])
            self.assertEqual([3, 7], result["parameters"]["candidates"]["insult_id"])
            self.assertTrue(result["parameters"]["candidates"]["complete"])

    def test_query_and_execution_family_validation(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        discovery = fixture["query_scornful_discovery"]
        self.assertTrue(ObserverSession._valid_native_insult_inspection(
            discovery, "scornful_insult", "FRA", "SAV", "initiate", 1, -2))
        self.assertFalse(ObserverSession._valid_native_insult_inspection(
            {**discovery, "family": "guarantee"}, "scornful_insult", "FRA", "SAV",
            "initiate", 1, -2))
        event = fixture["execution"]
        result = ObserverSession._public_native_insult_execution_result(
            event, "insult-execution", "insult-session", "FRA", "SAV", "initiate", 1,
            "scornful_insult", 3)
        self.assertEqual("executed", result["native_outcome"])
        unknown = ObserverSession._public_native_insult_execution_result(
            {**event, "insult_after": False}, "insult-execution", "insult-session",
            "FRA", "SAV", "initiate", 1, "scornful_insult", 3)
        self.assertEqual("unknown", unknown["native_outcome"])
        self.assertFalse(ObserverSession._public_native_insult_execution_result(
            {**event, "family": "guarantee"}, "insult-execution", "insult-session",
            "FRA", "SAV", "initiate", 1, "scornful_insult", 3))
        ordinary = ObserverSession._public_native_insult_execution_result(
            {**event, "action_id": "send_insult", "insult_id": -1},
            "insult-execution", "insult-session", "FRA", "SAV", "initiate", 1,
            "send_insult", -1)
        self.assertEqual("executed", ordinary["native_outcome"])
        self.assertEqual(-1, ordinary["insult_id"])

    def test_real_execution_fixture_round_trips_ordinary_insult_result(self):
        fixture = json.loads(REAL_EXECUTION_FIXTURE.read_text(encoding="utf-8"))
        submission = fixture["submission"]["event"]
        execution = fixture["execution"]["event"]
        self.assertTrue(ObserverSession._valid_native_submission_result(
            submission, "r33b_insult_bur_001", "34852-1dd5cb8a577c4a0",
            "FRA", "BUR", "initiate", 56464872, "send_insult"))
        result = ObserverSession._public_native_insult_execution_result(
            execution, "r33b_insult_bur_001", "34852-1dd5cb8a577c4a0",
            "FRA", "BUR", "initiate", 56464872, "send_insult", -1)
        self.assertIsNotNone(result)
        self.assertEqual("executed", result["native_outcome"])
        self.assertEqual(-50000, result["opinion_modifier_after_raw"])
        self.assertEqual(8086, result["prestige_after_raw"])

    def test_real_a_query_projection_uses_insult_full_rules_and_diagnostic(self):
        session = RealInsultQuerySession()
        journal = DurableJournal(":memory:", "insult-real-r33", session.session_id)
        try:
            api = DiplomacyTools(journal, session)
            bur = api.inspect_diplomatic_action("send_insult", "FRA", "BUR")
            self.assertEqual("available", bur["legality"]["status"])
            self.assertTrue(bur["legality"]["complete"])
            self.assertTrue(bur["native_rule_components"]["full_rules_complete"])
            self.assertEqual(1, bur["resources"]["diplomats"]["available_count"])

            sav = api.inspect_diplomatic_action("send_insult", "FRA", "SAV")
            self.assertEqual("unavailable", sav["legality"]["status"])
            self.assertTrue(sav["legality"]["complete"])
            self.assertTrue(sav["native_rule_components"]["full_rules_complete"])

            eng = api.inspect_diplomatic_action("send_insult", "FRA", "ENG")
            self.assertEqual("unavailable", eng["legality"]["status"])
            self.assertTrue(eng["legality"]["complete"])
            self.assertEqual("§R- 我国处于战争状态。§!\n",
                             eng["native_diagnostic"]["text"])
            self.assertTrue(eng["native_diagnostic"]["text_decoded"])

            discovery = api.inspect_diplomatic_action(
                "scornful_insult", "FRA", "BUR")
            self.assertEqual("unknown", discovery["legality"]["status"])
            self.assertEqual("INSULT_PARAMETER_NOT_SELECTED",
                             discovery["legality"]["reasons"][0]["code"])
            self.assertEqual(18, discovery["candidate_count"])
            self.assertEqual([0, 43],
                             discovery["parameters"]["candidates"]["insult_id"])
            self.assertTrue(discovery["parameters"]["candidates"]["items"][0]["text"])
            self.assertEqual("unknown", discovery["costs"]["status"])
            self.assertFalse(discovery["costs"]["complete"])
        finally:
            journal.close()

    def test_real_insult_costs_project_known_prestige_item_and_partial_coverage(self):
        session = RealInsultCostQuerySession()
        journal = DurableJournal(":memory:", "insult-cost-r33", session.session_id)
        try:
            api = DiplomacyTools(journal, session)
            ordinary = api.inspect_diplomatic_action("send_insult", "FRA", "BUR")
            ordinary_cost = ordinary["costs"]
            self.assertEqual("available", ordinary_cost["status"])
            self.assertFalse(ordinary_cost["complete"])
            self.assertEqual({
                "resource": "prestige",
                "amount": 0,
                "amount_raw": 0,
                "unit": "prestige",
                "unit_verified": True,
                "scale": 1000,
                "scale_verified": True,
                "source": "native_rule_and_save_effect",
                "complete": True,
            }, ordinary_cost["items"][0])
            self.assertEqual("partial", ordinary_cost["coverage"]["status"])
            self.assertEqual("unknown", ordinary_cost["coverage"]["additional_costs"])

            scornful = api.inspect_diplomatic_action(
                "scornful_insult", "FRA", "GEN", parameters={"insult_id": 0})
            scornful_cost = scornful["costs"]
            self.assertEqual("available", scornful_cost["status"])
            self.assertFalse(scornful_cost["complete"])
            self.assertEqual(5, scornful_cost["items"][0]["amount"])
            self.assertEqual(5000, scornful_cost["items"][0]["amount_raw"])
            self.assertEqual(1000, scornful_cost["items"][0]["scale"])
            self.assertTrue(scornful_cost["items"][0]["scale_verified"])
            self.assertEqual(1, scornful_cost["coverage"]["known_items"])
            self.assertFalse(scornful_cost["coverage"]["complete"])
        finally:
            journal.close()

    def test_submission_wire_uses_v2_and_selected_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation, log = self._installation(root, submission_ack=True)
            session = ObserverSession(installation, root / "eu4.exe")
            captured: list[str] = []

            def publish(wire: str, request_id: str) -> str:
                captured.append(wire)
                with log.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({
                        "event": "native_alliance_submission_result",
                        "request_id": request_id, "session_id": "insult-session",
                        "action_id": "scornful_insult", "actor": "FRA",
                        "recipient": "SAV", "phase": "initiate", "date_raw": 1,
                        "submitted": True, "native_queue_verified": True,
                        "transport_ring_receipt": True, "native_sequence": 1,
                        "native_origin": 1, "native_flags": 0,
                    }) + "\n")
                return "published"

            with patch.object(session, "_publish_execute_request", side_effect=publish):
                result = session.submit_scornful_insult(
                    "insult-wire", "FRA", "SAV", "initiate", 1, 3, timeout=1)
            self.assertEqual("submitted", result["status"])
            expected_wire = WIRE_FIXTURE.read_bytes()
            self.assertTrue(expected_wire.endswith(b"\n"))
            expected_fields = expected_wire[:-1].split(b"|")
            self.assertEqual(10, len(expected_fields))
            self.assertEqual(b"v2", expected_fields[0])
            self.assertEqual(b"scornful_insult", expected_fields[5])
            self.assertEqual(b"3", expected_fields[9])

            actual_fields = captured[0].encode("ascii").rstrip(b"\n").split(b"|")
            self.assertEqual(10, len(actual_fields))
            for index in (0, 5, 6, 7, 8, 9):
                self.assertEqual(expected_fields[index], actual_fields[index])

    def test_scornful_execute_is_idempotent_and_binds_id(self):
        session = InsultExecutionSession()
        journal = DurableJournal(":memory:", "insult-contract", session.session_id)
        try:
            api = DiplomacyTools(journal, session)
            result = api.execute_diplomatic_action(
                "insult-request", "scornful_insult", "FRA", "SAV",
                parameters={"insult_id": 3})
            self.assertEqual("executed", result["status"])
            self.assertEqual([("insult-request", 3)], session.submit_calls)
            replay = api.execute_diplomatic_action(
                "insult-request", "scornful_insult", "FRA", "SAV",
                parameters={"insult_id": 3})
            self.assertTrue(replay["idempotent"])
            self.assertEqual([("insult-request", 3)], session.submit_calls)
            conflict = api.execute_diplomatic_action(
                "insult-request", "scornful_insult", "FRA", "SAV",
                parameters={"insult_id": 7})
            self.assertEqual("conflict", conflict["status"])
            self.assertEqual("REQUEST_ID_PAYLOAD_CONFLICT", conflict["reason"]["code"])
        finally:
            journal.close()

    def test_send_insult_execute_uses_ordinary_parameter_and_result_reader(self):
        session = InsultExecutionSession()
        journal = DurableJournal(":memory:", "insult-contract", session.session_id)
        try:
            api = DiplomacyTools(journal, session)
            result = api.execute_diplomatic_action(
                "ordinary-insult-request", "send_insult", "FRA", "SAV")
            self.assertEqual("executed", result["status"])
            self.assertEqual([("ordinary-insult-request", -1)], session.submit_calls)
            self.assertEqual(-1, result["result"]["insult_id"])
        finally:
            journal.close()

    def test_empty_scornful_request_never_submits(self):
        session = InsultExecutionSession()
        journal = DurableJournal(":memory:", "insult-contract", session.session_id)
        try:
            api = DiplomacyTools(journal, session)
            result = api.execute_diplomatic_action(
                "insult-discover", "scornful_insult", "FRA", "SAV")
            self.assertEqual("INSULT_PARAMETER_NOT_SELECTED", result["result"]["reason"]["code"])
            self.assertEqual([], session.submit_calls)
        finally:
            journal.close()


if __name__ == "__main__":
    unittest.main()
