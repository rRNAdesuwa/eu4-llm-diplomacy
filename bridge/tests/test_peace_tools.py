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


FIXTURE = (Path(__file__).parent / "fixtures" /
           "peace_context_inspection.json")
EMPTY_FIXTURE = (Path(__file__).parent / "fixtures" /
                 "peace_context_empty_inspection.json")
REAL_FIXTURE = (Path(__file__).parent / "fixtures" /
                "peace_context_r38a_real_inspections.json")
EMPTY_OFFER_FIXTURE = (Path(__file__).parent / "fixtures" /
                       "peace_empty_offer_inspection.json")
EVALUATION_FIXTURE = (Path(__file__).parent / "fixtures" /
                      "peace_empty_offer_evaluation.json")
REAL_EMPTY_OFFER_FIXTURE = (Path(__file__).parent / "fixtures" /
                            "peace_empty_offer_r38b_real_inspections.json")
REAL_EVALUATION_FIXTURE = (Path(__file__).parent / "fixtures" /
                           "peace_empty_offer_r38c_real_evaluations.json")
REAL_R46A_OFFER_FIXTURE = (Path(__file__).parent / "fixtures" /
                           "peace_r46a_offer_white_inspection.json")
REAL_MONEY_FIXTURE = (Path(__file__).parent / "fixtures" /
                      "peace_money_offer_r39d_real_inspections.json")
REAL_FACTOR_IDS_FIXTURE = (Path(__file__).parent / "fixtures" /
                           "peace_factor_identifiers_r39e_real_inspections.json")
MONEY_FIXTURE = (Path(__file__).parent / "fixtures" /
                 "peace_money_offer_inspection.json")


class PeaceToolsTests(unittest.TestCase):
    """Contract tests for read-only peace-war context discovery."""

    @staticmethod
    def _event(path: Path = FIXTURE) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def test_r46a_real_offer_white_event_uses_recipient_war_side(self):
        """Replay the failed R46A offer query through the real reader contract.

        The native event selected the recipient's war side for an offer.  The
        fixture binds the bounded source slice and keeps ``frame_thread`` in
        the input, while the public projection must omit that private field.
        """
        fixture = json.loads(REAL_R46A_OFFER_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(1, fixture["event_count"])
        self.assertEqual(
            "9da124c270f527c695c4c970aad8559c464cdd5344b68ca8b36a461639380328",
            fixture["source"]["native_events_sha256"])
        self.assertEqual(
            "4ed8a4bc77a0a2a1d0d16bb4289f15bce3241752a2044a3a3381bb29f2b90d40",
            fixture["events"][0]["event_sha256"])
        event = fixture["events"][0]["event"]
        self.assertEqual("offer", event["direction"])
        self.assertEqual("side_b", event["native_war_context"]["selected_side"])
        self.assertTrue(ObserverSession._valid_native_peace_empty_offer_inspection(
            event, "white_peace", "FRA", "ENG", "initiate", event["date_raw"],
            event["war_id"], event["query_id"], event["session_id"],
            require_wrapper_rule=True, expected_direction="offer"))
        projected = ObserverSession._semantic_peace_empty_offer_inspection(event)
        self.assertEqual("offer", projected["peace_context"]["direction"])
        self.assertEqual("side_b", projected["native_war_context"]["selected_side"])

        private_keys = {"frame_thread", "native_ref", "native_pointer",
                        "term_pointer", "pointer", "private"}

        def assert_no_private_keys(value):
            if isinstance(value, dict):
                self.assertTrue(private_keys.isdisjoint(value))
                for child in value.values():
                    assert_no_private_keys(child)
            elif isinstance(value, list):
                for child in value:
                    assert_no_private_keys(child)

        assert_no_private_keys(projected)

    def test_r46a_real_offer_white_reader_replay(self):
        """Exercise inspect_alliance's offer-direction validation path."""
        fixture = json.loads(REAL_R46A_OFFER_FIXTURE.read_text(encoding="utf-8"))
        event = fixture["events"][0]["event"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(
                self._installation(root, ack=None, empty_offer_ack=True,
                                   evaluation_ack=True), root / "eu4.exe")
            request = root / "diplomacy-query.request"
            log = root / "control-probe.jsonl"
            errors: list[BaseException] = []

            def writer() -> None:
                try:
                    deadline = time.monotonic() + 2
                    while not request.exists() and time.monotonic() < deadline:
                        time.sleep(0.001)
                    self.assertTrue(request.exists())
                    fields = request.read_text(encoding="ascii").strip().split()
                    self.assertEqual("EU4DIP_QUERY7", fields[0])
                    self.assertEqual("white_peace", fields[3])
                    self.assertEqual("FRA", fields[4])
                    self.assertEqual("ENG", fields[5])
                    self.assertEqual(event["war_id"], fields[8])
                    self.assertEqual("offer", fields[9])
                    self.assertEqual(["-1", "-", "-"], fields[10:13])
                    self.assertEqual(13, len(fields))
                    request.unlink(missing_ok=True)
                    actual = dict(event)
                    actual["query_id"] = fields[2]
                    actual["session_id"] = session.session_id
                    with log.open("a", encoding="utf-8", newline="\n") as stream:
                        stream.write(json.dumps(actual) + "\n")
                except BaseException as exc:
                    errors.append(exc)

            thread = threading.Thread(target=writer)
            thread.start()
            ready = {"status": "ready", "state_id": "ready",
                     "date_raw": event["date_raw"], "reasons": [],
                     "complete": True}
            parameters = {"peace_context": {
                "war_id": event["war_id"], "direction": "offer", "terms": []}}
            with patch.object(session, "health", return_value=ready), \
                 patch.object(session, "installation_capabilities", return_value=frozenset({
                     "native_peace_submission", "native_peace_empty_offer_query",
                     "native_peace_offer_evaluation_query",
                     "native_peace_wrapper_rule_query"})), \
                 patch("bridge.diplomacy.probe_identity",
                       return_value={"session_id": session.session_id}):
                result = DiplomacyTools(self.journal, session).inspect_diplomatic_action(
                    "white_peace", "FRA", "ENG", parameters=parameters)
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual([], errors)
            self.assertEqual("native_peace_execution_inspection",
                             result["interface_support"]["query"])
            self.assertEqual("offer", result["peace_context"]["direction"])
            self.assertEqual("side_b", result["native_war_context"]["selected_side"])
            self.assertNotIn("QUERY_NATIVE_RESULT_INVALID", {
                item["code"] for item in result["legality"]["reasons"]})


    @staticmethod
    def _installation(root: Path, *, ack: object = True,
                      empty_offer_ack: object = None,
                      evaluation_ack: object = None,
                      money_offer_ack: object = None,
                      caps: list[str] | None = None,
                      native_text_codec: str | None = None) -> Path:
        session_id = "peace-session"
        installation = root / "installation.json"
        installation_record = {
            "experiment_id": "peace-contract",
            "session_id": session_id,
            "pid": 1,
            "creation_filetime": 2,
            "dll_sha256": "dll",
            "controlled_countries": ["FRA"],
            "installation_returncode": 0,
        }
        if native_text_codec is not None:
            installation_record["native_text_codec"] = native_text_codec
        installation.write_text(json.dumps(installation_record), encoding="utf-8")
        installed = {"event": "diplomacy_observer_installed",
                     "session_id": session_id}
        if ack is not None:
            installed["native_peace_context_query"] = ack
        if empty_offer_ack is not None:
            installed["native_peace_empty_offer_query"] = empty_offer_ack
        if evaluation_ack is not None:
            installed["native_peace_offer_evaluation_query"] = evaluation_ack
        if money_offer_ack is not None:
            installed["native_peace_money_offer_query"] = money_offer_ack
        if caps is not None:
            installed["caps"] = caps
        (root / "control-probe.jsonl").write_text(
            json.dumps(installed) + "\n", encoding="utf-8")
        return installation

    def setUp(self) -> None:
        self.journal = DurableJournal(":memory:", "peace-contract", "peace-session")

    def tearDown(self) -> None:
        self.journal.close()

    def test_catalog_keeps_nineteen_terms_and_ack_only_query(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = self._installation(root)
            session = ObserverSession(installation, root / "eu4.exe")
            ready = {"status": "ready", "state_id": "ready", "date_raw": 1,
                     "reasons": [], "complete": True}
            with patch.object(session, "health", return_value=ready):
                catalog = DiplomacyTools(self.journal, session).list_diplomatic_actions()
            peace = [item for item in catalog["actions"]
                     if item["category"] == "peace_term"]
            self.assertEqual(19, len(peace))
            by_id = {item["action_id"]: item for item in peace}
            self.assertEqual("peace", by_id["white_peace"]["native_identifier"])
            self.assertEqual(
                "peace_context.war_id",
                by_id["white_peace"]["parameter_definitions"][
                    "peace_context.war_id"]["path"])
            self.assertEqual(
                {}, by_id["white_peace"]["inspection_parameter_forms"][0][
                    "parameters"])
            self.assertEqual(
                [], by_id["white_peace"]["inspection_parameter_forms"][1][
                    "parameters"]["peace_context"]["terms"])
            self.assertEqual("native_peace_context_inspection",
                             by_id["white_peace"]["phases"]["initiate"]["query"])
            self.assertEqual("unimplemented",
                             by_id["white_peace"]["phases"]["initiate"]["execute"])

            copied = self._installation(root, ack=None,
                                        caps=["native_peace_context_query"])
            copied_session = ObserverSession(copied, root / "eu4.exe")
            self.assertNotIn("native_peace_context_query",
                             copied_session.installation_capabilities())

            money_installation = self._installation(
                root, ack=None, money_offer_ack=True)
            money_session = ObserverSession(money_installation, root / "eu4.exe")
            with patch.object(money_session, "health", return_value=ready):
                money_catalog = DiplomacyTools(
                    self.journal, money_session).list_diplomatic_actions()
            money_action = next(item for item in money_catalog["actions"]
                                if item["action_id"] == "demand_ducats")
            self.assertEqual(
                "native_peace_money_offer_inspection",
                money_action["phases"]["initiate"]["selected_query"])
            money_definitions = money_action["parameter_definitions"]
            self.assertEqual(
                "peace_context.terms[0].amount",
                money_definitions["peace_context.terms[0].amount"]["path"])
            self.assertEqual(
                "ducats",
                money_definitions["peace_context.terms[0].amount"]["unit"])
            self.assertEqual(
                0.1,
                money_definitions["peace_context.terms[0].amount"]["precision"])
            listed_form = money_action["inspection_parameter_forms"][1][
                "parameters"]
            selected_form = {
                "peace_context": {
                    **listed_form["peace_context"],
                    "war_id": "war_0123456789abcdef_01234567",
                    "terms": [{
                        **listed_form["peace_context"]["terms"][0],
                        "payer": "ENG",
                        "claimant": "FRA",
                    }],
                },
            }
            normalized = DiplomacyTools._normalize_peace_money_offer_parameters(
                selected_form, "FRA", "ENG")
            self.assertEqual(10000, normalized["amount_raw"])
            self.assertEqual("ENG", normalized["payer"])
            self.assertEqual("FRA", normalized["claimant"])
            self.assertEqual(
                "recipient",
                money_definitions["peace_context.terms[0].payer"]["equals"])
            self.assertEqual(
                "actor",
                money_definitions["peace_context.terms[0].claimant"]["equals"])

    def _run_query(self, session: ObserverSession, event: dict,
                   *, recipient: str = "ENG") -> dict:
        request = session.directory / "diplomacy-query.request"
        log = session.directory / "control-probe.jsonl"
        errors: list[BaseException] = []

        def writer() -> None:
            try:
                deadline = time.monotonic() + 2
                while not request.exists() and time.monotonic() < deadline:
                    time.sleep(0.001)
                if not request.exists():
                    raise AssertionError("query request was not published")
                fields = request.read_text(encoding="ascii").strip().split()
                self.assertEqual("EU4DIP_QUERY1", fields[0])
                self.assertEqual(event["action_id"], fields[3])
                self.assertEqual("FRA", fields[4])
                self.assertEqual(recipient, fields[5])
                self.assertEqual(8, len(fields))
                request.unlink(missing_ok=True)
                actual = dict(event)
                actual["query_id"] = fields[2]
                actual["session_id"] = session.session_id
                actual["recipient"] = recipient
                with log.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(actual) + "\n")
            except BaseException as exc:
                errors.append(exc)

        thread = threading.Thread(target=writer)
        thread.start()
        ready = {"status": "ready", "state_id": "ready",
                 "date_raw": event["date_raw"], "reasons": [], "complete": True}
        with patch.object(session, "health", return_value=ready), \
             patch("bridge.diplomacy.probe_identity",
                   return_value={"session_id": session.session_id}):
            result = DiplomacyTools(self.journal, session).inspect_diplomatic_action(
                event["action_id"], "FRA", recipient, parameters={})
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], errors)
        return result

    def test_query_projects_safe_war_context_and_keeps_offer_unknown(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(self._installation(root), root / "eu4.exe")
            result = self._run_query(session, self._event())
        self.assertEqual("peace", result["family"])
        self.assertTrue(result["context_discovery"])
        self.assertTrue(result["query_complete"])
        self.assertTrue(result["war_context_enumeration_complete"])
        self.assertEqual({}, result["parameters"]["requested"])
        self.assertEqual("unknown", result["legality"]["status"])
        self.assertEqual("unknown", result["costs"]["status"])
        self.assertEqual("unknown", result["acceptance"]["predicted_response"])
        self.assertEqual("unimplemented", result["interface_support"]["execute"])
        self.assertEqual(1, len(result["war_contexts"]))
        war = result["war_contexts"][0]
        self.assertEqual("war_0123456789abcdef_01234567", war["war_id"])
        self.assertNotIn("native_ref", war)
        self.assertIsNone(war["actor_war_role"])
        self.assertFalse(war["context_complete"])

    def test_empty_war_enumeration_is_valid(self):
        event = self._event(EMPTY_FIXTURE)
        self.assertTrue(ObserverSession._valid_native_peace_context_inspection(
            event, "white_peace", "FRA", "ENG", "initiate", 56550000,
            "peace-query-empty", "peace-session"))
        projected = ObserverSession._semantic_peace_context_inspection(event)
        self.assertEqual([], projected["war_contexts"])
        self.assertTrue(projected["context_discovery"])

    def test_peace_event_identity_and_row_contract_are_strict(self):
        event = self._event()
        self.assertFalse(ObserverSession._valid_native_peace_context_inspection(
            {**event, "session_id": "other"}, "white_peace", "FRA", "ENG",
            "initiate", 56550000, "peace-query-001", "peace-session"))
        malformed = {**event, "wars": [dict(event["wars"][0],
                                               roles_verified=True)]}
        self.assertFalse(ObserverSession._valid_native_peace_context_inspection(
            malformed, "white_peace", "FRA", "ENG", "initiate", 56550000,
            "peace-query-001", "peace-session"))
        malformed_id = {**event, "wars": [dict(event["wars"][0],
                                                  war_id="native-0x1234")]}
        self.assertFalse(ObserverSession._valid_native_peace_context_inspection(
            malformed_id, "white_peace", "FRA", "ENG", "initiate", 56550000,
            "peace-query-001", "peace-session"))

    def test_r38a_real_events_validate_and_project_without_private_fields(self):
        payload = json.loads(REAL_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(6, payload["event_count"])
        for event in payload["events"]:
            self.assertTrue(ObserverSession._valid_native_peace_context_inspection(
                event, event["action_id"], event["actor"], event["recipient"],
                event["phase"], event["date_raw"], event["query_id"],
                event["session_id"]))
            projected = ObserverSession._semantic_peace_context_inspection(event)
            self.assertEqual("peace", projected["family"])
            self.assertTrue(projected["context_discovery"])
            self.assertTrue(projected["query_complete"])
            self.assertNotIn("frame_thread", projected)
            for war in projected["war_contexts"]:
                self.assertNotIn("native_ref", war)
                self.assertNotIn("native_war_reference", war)

    def test_r38a_real_event_uses_public_inspect_reader(self):
        event = next(item for item in json.loads(
            REAL_FIXTURE.read_text(encoding="utf-8"))["events"]
                     if item["action_id"] == "white_peace"
                     and item["recipient"] == "ENG")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(self._installation(root), root / "eu4.exe")
            result = self._run_query(session, event, recipient="ENG")
        self.assertEqual("native_peace_context_inspection",
                         result["interface_support"]["query"])
        self.assertEqual("peace", result["family"])
        self.assertEqual(event["wars"][0]["war_id"],
                         result["war_contexts"][0]["war_id"])
        self.assertEqual("unknown", result["legality"]["status"])

    def test_execute_still_requires_complete_peace_context(self):
        api = DiplomacyTools(self.journal)
        with self.assertRaisesRegex(ValueError, "PEACE_CONTEXT_REQUIRED"):
            api.execute_diplomatic_action(
                "peace-execute-001", "white_peace", "FRA", "ENG",
                parameters={})

    def _run_empty_offer_query(self, session: ObserverSession,
                               event: dict, *, recipient: str = "ENG",
                               direction: str | None = None) -> dict:
        request = session.directory / "diplomacy-query.request"
        log = session.directory / "control-probe.jsonl"
        errors: list[BaseException] = []

        def writer() -> None:
            try:
                deadline = time.monotonic() + 2
                while not request.exists() and time.monotonic() < deadline:
                    time.sleep(0.001)
                if not request.exists():
                    raise AssertionError("QUERY4 request was not published")
                fields = request.read_text(encoding="ascii").strip().split()
                self.assertEqual("EU4DIP_QUERY4", fields[0])
                self.assertEqual("white_peace", fields[3])
                self.assertEqual("FRA", fields[4])
                self.assertEqual(recipient, fields[5])
                self.assertEqual(event["war_id"], fields[8])
                self.assertEqual(9, len(fields))
                request.unlink(missing_ok=True)
                actual = dict(event)
                actual["query_id"] = fields[2]
                actual["session_id"] = session.session_id
                actual["recipient"] = recipient
                with log.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(actual) + "\n")
            except BaseException as exc:
                errors.append(exc)

        thread = threading.Thread(target=writer)
        thread.start()
        ready = {"status": "ready", "state_id": "ready",
                 "date_raw": event["date_raw"], "reasons": [], "complete": True}
        context = {"war_id": event["war_id"], "terms": []}
        if direction is not None:
            context["direction"] = direction
        with patch.object(session, "health", return_value=ready), \
             patch("bridge.diplomacy.probe_identity",
                   return_value={"session_id": session.session_id}):
            result = DiplomacyTools(self.journal, session).inspect_diplomatic_action(
                "white_peace", "FRA", recipient,
                parameters={"peace_context": context})
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], errors)
        return result

    def test_white_peace_inspect_accepts_the_execute_direction(self):
        event = json.loads(EMPTY_OFFER_FIXTURE.read_text(encoding="utf-8"))["event"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(
                self._installation(root, empty_offer_ack=True), root / "eu4.exe")
            result = self._run_empty_offer_query(session, event, direction="demand")
        self.assertEqual(event["war_id"], result["selected_war_id"])
        self.assertEqual("native_peace_empty_offer_inspection",
                         result["interface_support"]["query"])

    def _run_money_query(self, session: ObserverSession, event: dict,
                         *, amount: str, recipient: str = "ENG",
                         direction: str = "demand") -> dict:
        request = session.directory / "diplomacy-query.request"
        log = session.directory / "control-probe.jsonl"
        errors: list[BaseException] = []

        def writer() -> None:
            try:
                deadline = time.monotonic() + 2
                while not request.exists() and time.monotonic() < deadline:
                    time.sleep(0.001)
                if not request.exists():
                    raise AssertionError("money query request was not published")
                fields = request.read_text(encoding="ascii").strip().split()
                self.assertEqual(
                    "EU4DIP_QUERY7" if direction == "offer" else "EU4DIP_QUERY5",
                    fields[0])
                self.assertEqual("demand_ducats", fields[3])
                self.assertEqual("FRA", fields[4])
                self.assertEqual(recipient, fields[5])
                self.assertEqual(event["war_id"], fields[8])
                if direction == "offer":
                    self.assertEqual("offer", fields[9])
                    self.assertEqual(
                        str(DiplomacyTools._normalize_peace_money_amount(amount)),
                        fields[10])
                    self.assertEqual("-", fields[11])
                    self.assertEqual("-", fields[12])
                    self.assertEqual(13, len(fields))
                else:
                    self.assertEqual(10, len(fields))
                    self.assertEqual(
                        DiplomacyTools._normalize_peace_money_amount(amount),
                        int(fields[9]))
                request.unlink(missing_ok=True)
                actual = dict(event)
                actual["query_id"] = fields[2]
                actual["session_id"] = session.session_id
                actual["recipient"] = recipient
                with log.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(actual) + "\n")
            except BaseException as exc:
                errors.append(exc)

        thread = threading.Thread(target=writer)
        thread.start()
        ready = {"status": "ready", "state_id": "ready",
                 "date_raw": event["date_raw"], "reasons": [], "complete": True}
        payer = "FRA" if direction == "offer" else recipient
        claimant = recipient if direction == "offer" else "FRA"
        parameters = {"peace_context": {
            "war_id": event["war_id"],
            "direction": direction,
            "terms": [{"action_id": "demand_ducats", "amount": amount,
                        "payer": payer, "claimant": claimant}]}}
        with patch.object(session, "health", return_value=ready), \
             patch("bridge.diplomacy.probe_identity",
                   return_value={"session_id": session.session_id}):
            result = DiplomacyTools(self.journal, session).inspect_diplomatic_action(
                "demand_ducats", "FRA", recipient, parameters=parameters)
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], errors)
        return result

    def test_query7_money_offer_preserves_direction_and_parties(self):
        event = json.loads(MONEY_FIXTURE.read_text(
            encoding="utf-8"))["event"]
        event["direction"] = "offer"
        event["native_money"] = {
            **event["native_money"], "direction": "offer",
            "payer": "FRA", "claimant": "ENG",
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(
                self._installation(root, ack=None, money_offer_ack=True),
                root / "eu4.exe")
            result = self._run_money_query(
                session, event, amount="10.0", direction="offer")
        self.assertEqual("offer", result["parameters"]["actual"][
            "peace_context"]["direction"])
        term = result["parameters"]["actual"]["peace_context"]["terms"][0]
        self.assertEqual("FRA", term["payer"])
        self.assertEqual("ENG", term["claimant"])

    def test_query5_money_amount_normalization_is_decimal_and_bounded(self):
        self.assertEqual(10000,
                         DiplomacyTools._normalize_peace_money_amount(10))
        self.assertEqual(10000,
                         DiplomacyTools._normalize_peace_money_amount(10.0))
        self.assertEqual(10000,
                         DiplomacyTools._normalize_peace_money_amount("10.0"))
        for value in (True, 0, -1, "10.01", "NaN", "Infinity", "1e1000000"):
            with self.assertRaises(ValueError):
                DiplomacyTools._normalize_peace_money_amount(value)

    def test_query5_validates_money_copy_and_projects_actual_term(self):
        event = json.loads(MONEY_FIXTURE.read_text(
            encoding="utf-8"))["event"]
        self.assertTrue(ObserverSession._valid_native_peace_money_offer_inspection(
            event, "demand_ducats", "FRA", "ENG", "initiate",
            event["date_raw"], {
                "war_id": event["war_id"], "direction": "demand",
                "amount_raw": 10000, "payer": "ENG", "claimant": "FRA"},
            event["query_id"], event["session_id"]))
        projected = ObserverSession._semantic_peace_money_offer_inspection(event)
        self.assertEqual("native_peace_money_offer_inspection",
                         projected["event"])
        self.assertEqual(10000,
                         projected["native_money"]["requested_amount_raw"])
        self.assertEqual(1000, projected["native_money"]["currency_scale"])
        self.assertTrue(projected["native_evaluation"]["called"])
        self.assertEqual(-45, projected["native_evaluation"]["native_total"])
        self.assertEqual(2, projected["native_evaluation"]["aggregate_score_raw"])
        self.assertEqual(2, len(projected["native_evaluation"]["items"]))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(
                self._installation(root, ack=None, money_offer_ack=True),
                root / "eu4.exe")
            result = self._run_money_query(session, event, amount="10.0")
        self.assertEqual("native_peace_money_offer_inspection",
                         result["interface_support"]["query"])
        self.assertEqual("unknown", result["legality"]["status"])
        self.assertTrue(result["parameters"]["complete"])
        self.assertEqual("10.0", result["parameters"]["actual"][
            "peace_context"]["terms"][0]["amount"])
        self.assertEqual(10000, result["parameters"]["actual"][
            "peace_context"]["terms"][0]["amount_raw"])
        self.assertEqual(-45, result["native_evaluation"]["native_total"])
        self.assertEqual(-45, result["acceptance"]["native_total"])
        self.assertEqual(2, result["costs"]["native_evaluation"][
            "aggregate_score_raw"])
        self.assertNotEqual(
            result["acceptance"]["native_total"],
            result["costs"]["native_evaluation"]["aggregate_score_raw"])
        self.assertEqual(
            result["peace_context"]["terms"],
            result["parameters"]["actual"]["peace_context"]["terms"])
        self.assertFalse(result["acceptance"]["prediction_available"])

    def test_query5_overlimit_is_native_unavailable_and_actual_terms_empty(self):
        event = json.loads(MONEY_FIXTURE.read_text(
            encoding="utf-8"))["event"]
        event["native_money"] = {
            **event["native_money"],
            "requested_amount_raw": 100100,
            "amount_within_limit": False,
            "setter_called": False,
            "source_amount_raw": 0,
            "action_amount_raw": 0,
            "source_readback_matches": False,
            "parameters_matched": False,
        }
        event["native_evaluation"] = {
            **event["native_evaluation"],
            "called": False,
            "score_available": False,
            "score_raw": 0,
            "aggregate_score_available": False,
            "aggregate_score_raw": 0,
            "factor_native_count": 0,
            "factors_available": False,
            "items": [],
        }
        self.assertTrue(ObserverSession._valid_native_peace_money_offer_inspection(
            event, "demand_ducats", "FRA", "ENG", "initiate",
            event["date_raw"], {
                "war_id": event["war_id"], "direction": "demand",
                "amount_raw": 100100, "payer": "ENG", "claimant": "FRA"},
            event["query_id"], event["session_id"]))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(
                self._installation(root, ack=None, money_offer_ack=True),
                root / "eu4.exe")
            result = self._run_money_query(session, event, amount="100.1")
        self.assertEqual("unavailable", result["legality"]["status"])
        self.assertEqual(
            "NATIVE_PEACE_MONEY_AMOUNT_EXCEEDS_LIMIT",
            result["legality"]["reasons"][0]["code"])
        self.assertTrue(result["legality"]["complete"])
        self.assertFalse(result["parameters"]["complete"])
        self.assertEqual([], result["parameters"]["actual"][
            "peace_context"]["terms"])
        self.assertIsNone(result["acceptance"]["native_total"])
        self.assertFalse(result["costs"]["native_evaluation"][
            "aggregate_score_available"])

        malformed_precision = json.loads(MONEY_FIXTURE.read_text(
            encoding="utf-8"))["event"]
        malformed_precision["native_money"] = {
            **malformed_precision["native_money"],
            "requested_amount_raw": 100101,
            "amount_within_limit": False,
            "setter_called": False,
            "source_amount_raw": 0,
            "action_amount_raw": 0,
            "source_readback_matches": False,
            "parameters_matched": False,
        }
        self.assertFalse(ObserverSession._valid_native_peace_money_offer_inspection(
            malformed_precision, "demand_ducats", "FRA", "ENG", "initiate",
            malformed_precision["date_raw"], {
                "war_id": malformed_precision["war_id"], "direction": "demand",
                "amount_raw": 100101, "payer": "ENG", "claimant": "FRA"},
            malformed_precision["query_id"], malformed_precision["session_id"]))

        malformed_copy = json.loads(MONEY_FIXTURE.read_text(
            encoding="utf-8"))["event"]
        malformed_copy["native_money"] = {
            **malformed_copy["native_money"],
            "action_copy_verified": False,
        }
        self.assertFalse(ObserverSession._valid_native_peace_money_offer_inspection(
            malformed_copy, "demand_ducats", "FRA", "ENG", "initiate",
            malformed_copy["date_raw"], {
                "war_id": malformed_copy["war_id"], "direction": "demand",
                "amount_raw": 10000, "payer": "ENG", "claimant": "FRA"},
            malformed_copy["query_id"], malformed_copy["session_id"]))

    def test_query5_ack_is_required_for_minimal_selected_context(self):
        event = json.loads(MONEY_FIXTURE.read_text(
            encoding="utf-8"))["event"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(
                self._installation(root, ack=None), root / "eu4.exe")
            with self.assertRaisesRegex(ValueError, "PEACE_CONTEXT_REQUIRED"):
                DiplomacyTools(self.journal, session).inspect_diplomatic_action(
                    "demand_ducats", "FRA", "ENG", parameters={
                        "peace_context": {
                            "war_id": event["war_id"],
                            "direction": "demand",
                            "terms": [{"action_id": "demand_ducats",
                                       "amount": "10.0", "payer": "ENG",
                                       "claimant": "FRA"}]}})

    def test_query5_r39d_real_events_replay_money_evaluation_and_filter_private_fields(self):
        fixture = json.loads(REAL_MONEY_FIXTURE.read_text(
            encoding="utf-8"))
        self.assertEqual(5, fixture["event_count"])
        self.assertEqual(5, len(fixture["events"]))
        money_events = [event for event in fixture["events"]
                        if event["event"] == "native_peace_money_offer_inspection"]
        self.assertEqual(4, len(money_events))
        for event in money_events:
            amount_raw = event["native_money"]["requested_amount_raw"]
            amount = f"{amount_raw // 1000}.{(amount_raw % 1000) // 100}"
            expected = {
                "war_id": event["war_id"], "direction": "demand",
                "amount_raw": amount_raw, "payer": "ENG", "claimant": "FRA",
            }
            self.assertTrue(ObserverSession._valid_native_peace_money_offer_inspection(
                event, "demand_ducats", "FRA", "ENG", "initiate",
                event["date_raw"], expected, event["query_id"],
                event["session_id"]))
            projected = ObserverSession._semantic_peace_money_offer_inspection(
                event, "eu4_escape")
            self.assertEqual(amount_raw,
                             projected["native_money"]["requested_amount_raw"])
            self.assertEqual(event["native_evaluation"]["called"],
                             projected["native_evaluation"]["called"])
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                session = ObserverSession(
                    self._installation(root, ack=None, money_offer_ack=True,
                                       native_text_codec="eu4_escape"),
                    root / "eu4.exe")
                result = self._run_money_query(session, event, amount=amount)
            self.assertEqual("native_peace_money_offer_inspection",
                             result["interface_support"]["query"])
            public_text = json.dumps(result, ensure_ascii=False)
            for private_key in ("frame_thread", "participantvectoroffset",
                                "native_ref", "native_caller"):
                self.assertNotIn(private_key, public_text)
            if event["native_money"]["amount_within_limit"]:
                self.assertEqual(8, event["native_evaluation"][
                    "factor_native_count"])
                self.assertEqual(8, len(result["acceptance"]["items"]))
                self.assertEqual(-100, result["acceptance"]["native_total"])
                self.assertEqual(-100, result["native_evaluation"]["native_total"])
                self.assertEqual(1, result["native_evaluation"][
                    "aggregate_score_raw"])
                self.assertEqual(
                    1, result["costs"]["native_evaluation"][
                        "aggregate_score_raw"])
                self.assertEqual(
                    result["peace_context"]["terms"],
                    result["parameters"]["actual"]["peace_context"]["terms"])
                self.assertEqual(amount_raw, result["peace_context"]["terms"][0][
                    "amount_raw"])
            else:
                self.assertEqual([], result["peace_context"]["terms"])
                self.assertEqual([], result["parameters"]["actual"][
                    "peace_context"]["terms"])
                self.assertIsNone(result["acceptance"]["native_total"])
                self.assertFalse(result["costs"]["native_evaluation"][
                    "aggregate_score_available"])
                self.assertEqual(
                    "NATIVE_PEACE_MONEY_AMOUNT_EXCEEDS_LIMIT",
                    result["legality"]["reasons"][0]["code"])

        white = next(event for event in fixture["events"]
                     if event["event"] == "native_peace_empty_offer_inspection")
        self.assertTrue(ObserverSession._valid_native_peace_empty_offer_inspection(
            white, "white_peace", "FRA", "ENG", "initiate",
            white["date_raw"], white["war_id"], white["query_id"],
            white["session_id"]))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(
                self._installation(root, empty_offer_ack=True,
                                   evaluation_ack=True,
                                   native_text_codec="eu4_escape"),
                root / "eu4.exe")
            result = self._run_empty_offer_query(session, white)
        public_text = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("frame_thread", public_text)

    def test_query4_query5_r39e_real_factor_ids_replay_complete_details(self):
        fixture = json.loads(REAL_FACTOR_IDS_FIXTURE.read_text(
            encoding="utf-8"))
        self.assertEqual(2, fixture["event_count"])
        self.assertEqual(2, len(fixture["events"]))
        expected_ids = {
            "native_peace_empty_offer_inspection": [
                "DIPLO_WAR_REBELS", "DIPLO_HOLD_CAPITAL",
                "DIPLO_WAR_TIME_PASSED", "DIPLO_MILITARY_STRENGTH",
                "DIPLO_WAR_FORCE_BALANCE",
            ],
            "native_peace_money_offer_inspection": [
                "DIPLO_WAR_INCONCLUSIVE", "DIPLO_PEACEOFFER_VALUE",
                "DIPLO_WAR_REBELS", "DIPLO_HOLD_CAPITAL",
                "DIPLO_WAR_TIME_PASSED", "DIPLO_MILITARY_STRENGTH",
                "DIPLO_WAR_FORCE_BALANCE", "DIPLO_HIGH_DEMANDS",
            ],
        }
        for event in fixture["events"]:
            evaluation = event["native_evaluation"]
            self.assertEqual(expected_ids[event["event"]], [
                item["native_identifier"] for item in evaluation["items"]])
            self.assertTrue(evaluation["factors_complete"])
            self.assertTrue(all(item["identifier_verified"]
                                and item["row_binding_verified"]
                                and item["text_readable"]
                                and not item["text_truncated"]
                                for item in evaluation["items"]))
            if event["event"] == "native_peace_empty_offer_inspection":
                self.assertTrue(ObserverSession._valid_native_peace_empty_offer_inspection(
                    event, "white_peace", "FRA", "ENG", "initiate",
                    event["date_raw"], event["war_id"], event["query_id"],
                    event["session_id"]))
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    session = ObserverSession(
                        self._installation(root, empty_offer_ack=True,
                                           evaluation_ack=True,
                                           native_text_codec="eu4_escape"),
                        root / "eu4.exe")
                    result = self._run_empty_offer_query(session, event)
            else:
                amount_raw = event["native_money"]["requested_amount_raw"]
                amount = f"{amount_raw // 1000}.{(amount_raw % 1000) // 100}"
                self.assertTrue(ObserverSession._valid_native_peace_money_offer_inspection(
                    event, "demand_ducats", "FRA", "ENG", "initiate",
                    event["date_raw"], {
                        "war_id": event["war_id"], "direction": "demand",
                        "amount_raw": amount_raw, "payer": "ENG",
                        "claimant": "FRA"}, event["query_id"],
                    event["session_id"]))
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    session = ObserverSession(
                        self._installation(root, money_offer_ack=True,
                                           native_text_codec="eu4_escape"),
                        root / "eu4.exe")
                    result = self._run_money_query(session, event, amount=amount)
            public_text = json.dumps(result, ensure_ascii=False)
            for private_key in ("frame_thread", "native_caller",
                                "native_ref", "participantvectoroffset"):
                self.assertNotIn(private_key, public_text)
            self.assertTrue(result["acceptance"]["details_complete"])
            self.assertFalse(result["acceptance"]["complete"])
            self.assertEqual("unknown", result["acceptance"]["unit"])
            self.assertFalse(result["acceptance"]["scale_verified"])
            self.assertTrue(result["native_evaluation"]["factors_complete"])
            self.assertTrue(all(item["complete"] for item in
                                result["native_evaluation"]["items"]))

    def test_query4_validates_and_projects_only_three_gates(self):
        event = json.loads(EMPTY_OFFER_FIXTURE.read_text(
            encoding="utf-8"))["event"]
        self.assertTrue(ObserverSession._valid_native_peace_empty_offer_inspection(
            event, "white_peace", "FRA", "ENG", "initiate",
            event["date_raw"], event["war_id"], event["query_id"],
            event["session_id"]))
        projected = ObserverSession._semantic_peace_empty_offer_inspection(event)
        self.assertEqual("native", projected["diagnostics"]["validity"]["text"])
        self.assertEqual("common", projected["diagnostics"]["common_action_gate"]["text"])
        self.assertEqual("send", projected["diagnostics"]["initiation_gate"]["text"])
        self.assertNotIn("frame_thread", projected)
        self.assertNotIn("participantvectoroffset", projected)
        malformed = {**event, "participant_copy_verified": False}
        self.assertFalse(ObserverSession._valid_native_peace_empty_offer_inspection(
            malformed, "white_peace", "FRA", "ENG", "initiate",
            event["date_raw"], event["war_id"], event["query_id"],
            event["session_id"]))

    def test_query4_optional_evaluation_projects_raw_score_and_verified_factors(self):
        event = json.loads(EVALUATION_FIXTURE.read_text(
            encoding="utf-8"))["event"]
        self.assertTrue(ObserverSession._valid_native_peace_empty_offer_inspection(
            event, "white_peace", "FRA", "ENG", "initiate",
            event["date_raw"], event["war_id"], event["query_id"],
            event["session_id"]))
        projected = ObserverSession._semantic_peace_empty_offer_inspection(event)
        evaluation = projected["native_evaluation"]
        self.assertEqual(-45, evaluation["native_total"])
        self.assertTrue(evaluation["score_available"])
        self.assertEqual(-45, evaluation["score_raw"])
        self.assertTrue(evaluation["aggregate_score_available"])
        self.assertEqual(0, evaluation["aggregate_score_raw"])
        self.assertEqual(2, evaluation["factor_native_count"])
        self.assertTrue(evaluation["items"][0]["native_value_verified"])
        self.assertEqual("DIPLO_SCORE_FACTOR",
                         evaluation["items"][0]["native_identifier"])
        self.assertFalse(evaluation["items"][1]["identifier_verified"])
        self.assertIsNone(evaluation["items"][1]["native_identifier"])
        self.assertFalse(evaluation["items"][1]["native_value_verified"])
        complete_event = json.loads(EVALUATION_FIXTURE.read_text(
            encoding="utf-8"))["event"]
        complete_evaluation = {
            **complete_event["native_evaluation"],
            "factors_complete": True,
        }
        complete_items = []
        for index, raw in enumerate(complete_evaluation["items"]):
            item = {**raw,
                    "native_identifier": f"COMPLETE_FACTOR_{index}",
                    "identifier_verified": True,
                    "row_binding_verified": True,
                    "text_readable": True,
                    "text_truncated": False}
            complete_items.append(item)
        complete_evaluation["items"] = complete_items
        complete_event["native_evaluation"] = complete_evaluation
        self.assertTrue(ObserverSession._valid_native_peace_empty_offer_inspection(
            complete_event, "white_peace", "FRA", "ENG", "initiate",
            complete_event["date_raw"], complete_event["war_id"],
            complete_event["query_id"], complete_event["session_id"]))
        complete_projected = ObserverSession._semantic_peace_empty_offer_inspection(
            complete_event)
        self.assertTrue(complete_projected["native_evaluation"]["factors_complete"])
        self.assertTrue(all(item["complete"] for item in
                            complete_projected["native_evaluation"]["items"]))
        invalid = {**event, "native_evaluation": {
            **event["native_evaluation"], "score_raw": True}}
        self.assertFalse(ObserverSession._valid_native_peace_empty_offer_inspection(
            invalid, "white_peace", "FRA", "ENG", "initiate",
            event["date_raw"], event["war_id"], event["query_id"],
            event["session_id"]))
        missing_aggregate = {**event, "native_evaluation": {
            key: value for key, value in event["native_evaluation"].items()
            if key != "aggregate_score_raw"}}
        self.assertFalse(ObserverSession._valid_native_peace_empty_offer_inspection(
            missing_aggregate, "white_peace", "FRA", "ENG", "initiate",
            event["date_raw"], event["war_id"], event["query_id"],
            event["session_id"]))

    def test_query4_evaluation_ack_exposes_score_without_claiming_response_or_cost_unit(self):
        event = json.loads(EVALUATION_FIXTURE.read_text(
            encoding="utf-8"))["event"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(
                self._installation(root, empty_offer_ack=True,
                                   evaluation_ack=True), root / "eu4.exe")
            result = self._run_empty_offer_query(session, event)
        self.assertEqual(-45, result["native_evaluation"]["native_total"])
        self.assertEqual(-45, result["acceptance"]["native_total"])
        self.assertFalse(result["acceptance"]["prediction_available"])
        self.assertEqual("unknown", result["acceptance"]["predicted_response"])
        self.assertEqual("unknown", result["acceptance"]["unit"])
        self.assertFalse(result["acceptance"]["scale_verified"])
        self.assertEqual(0, result["costs"]["native_evaluation"][
            "aggregate_score_raw"])
        self.assertTrue(result["costs"]["native_evaluation"][
            "aggregate_score_available"])
        self.assertNotEqual(
            result["acceptance"]["native_total"],
            result["costs"]["native_evaluation"]["aggregate_score_raw"])
        self.assertEqual("factor one",
                         result["acceptance"]["items"][0]["text"])

    def test_query4_evaluation_field_without_ack_keeps_r38b_projection(self):
        event = json.loads(EVALUATION_FIXTURE.read_text(
            encoding="utf-8"))["event"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(
                self._installation(root, empty_offer_ack=True), root / "eu4.exe")
            result = self._run_empty_offer_query(session, event)
        self.assertNotIn("native_evaluation", result)
        self.assertNotIn("native_evaluation", result["costs"])
        self.assertIsNone(result["acceptance"]["native_total"])

    def test_query4_unavailable_evaluation_placeholder_is_not_a_zero_score(self):
        event = json.loads(EMPTY_OFFER_FIXTURE.read_text(
            encoding="utf-8"))["event"]
        event["native_validity"] = False
        event["native_evaluation"] = {
            "called": False,
            "score_available": False,
            "score_raw": 0,
            "aggregate_score_available": False,
            "aggregate_score_raw": 0,
            "score_representation": "signed_int32",
            "factor_native_count": 0,
            "factor_capture_truncated": False,
            "factors_available": False,
            "factors_complete": False,
            "items": [],
            "complete": False,
        }
        self.assertTrue(ObserverSession._valid_native_peace_empty_offer_inspection(
            event, "white_peace", "FRA", "ENG", "initiate",
            event["date_raw"], event["war_id"], event["query_id"],
            event["session_id"]))
        projected = ObserverSession._semantic_peace_empty_offer_inspection(event)
        self.assertEqual(0, projected["native_evaluation"]["score_raw"])
        self.assertFalse(projected["native_evaluation"]["score_available"])
        self.assertIsNone(projected["native_evaluation"]["native_total"])
        invalid = {**event, "native_evaluation": {
            **event["native_evaluation"], "called": True,
            "score_available": True}}
        self.assertFalse(ObserverSession._valid_native_peace_empty_offer_inspection(
            invalid, "white_peace", "FRA", "ENG", "initiate",
            event["date_raw"], event["war_id"], event["query_id"],
            event["session_id"]))

    def test_query4_public_inspect_requires_ack_and_keeps_legality_unknown(self):
        event = json.loads(EMPTY_OFFER_FIXTURE.read_text(
            encoding="utf-8"))["event"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = ObserverSession(
                self._installation(root, empty_offer_ack=True), root / "eu4.exe")
            result = self._run_empty_offer_query(session, event)
        self.assertEqual("native_peace_empty_offer_inspection",
                         result["interface_support"]["query"])
        self.assertEqual("white_peace", result["action_id"])
        self.assertEqual(event["war_id"], result["selected_war_id"])
        self.assertEqual("unknown", result["legality"]["status"])
        self.assertEqual("unknown", result["costs"]["status"])
        self.assertEqual("unknown", result["acceptance"]["predicted_response"])
        self.assertEqual("unimplemented", result["interface_support"]["execute"])
        self.assertEqual([], result["parameters"]["requested"]["peace_context"]["terms"])
        self.assertTrue(result["native_rule_components"]["common_action_gate"])
        self.assertTrue(result["native_rule_components"]["initiation_gate"])
        self.assertNotIn("native_evaluation", result)
        self.assertNotIn("native_evaluation", result["costs"])

    def test_query4_minimal_context_is_not_an_execute_context(self):
        api = DiplomacyTools(self.journal)
        with self.assertRaisesRegex(ValueError, "PEACE_CONTEXT_REQUIRED"):
            api.execute_diplomatic_action(
                "peace-empty-execute-001", "white_peace", "FRA", "ENG",
                parameters={"peace_context": {
                    "war_id": "war_0123456789abcdef_01234567", "terms": []}})

    def test_query4_r38b_real_events_replay_native_diagnostics_and_filter_private_fields(self):
        fixture = json.loads(REAL_EMPTY_OFFER_FIXTURE.read_text(
            encoding="utf-8"))
        self.assertEqual(3, fixture["event_count"])
        self.assertEqual(3, len(fixture["events"]))
        for event in fixture["events"]:
            recipient = event["recipient"]
            self.assertTrue(ObserverSession._valid_native_peace_empty_offer_inspection(
                event, "white_peace", "FRA", recipient, "initiate",
                event["date_raw"], event["war_id"], event["query_id"],
                event["session_id"]))
            expected = ObserverSession._semantic_peace_empty_offer_inspection(
                event, "eu4_escape")
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                session = ObserverSession(
                    self._installation(root, empty_offer_ack=True,
                                       native_text_codec="eu4_escape"),
                    root / "eu4.exe")
                result = self._run_empty_offer_query(
                    session, event, recipient=recipient)
            self.assertEqual("native_peace_empty_offer_inspection",
                             result["interface_support"]["query"])
            self.assertEqual("unavailable", result["legality"]["status"])
            self.assertEqual(expected["diagnostics"], result["diagnostics"])
            self.assertFalse(result["diagnostics"]["common_action_gate"]["truncated"])
            self.assertTrue(result["diagnostics"]["common_action_gate"]["text_decoded"])
            public_text = json.dumps(result, ensure_ascii=False)
            for private_key in (
                    "frame_thread", "participantvectoroffset",
                    "native_war_reference", "native_ref"):
                self.assertNotIn(private_key, public_text)
            if recipient == "TYR":
                self.assertFalse(result["native_validity"])
                self.assertIn("附庸国或被联合统治的国家无法签订和平条约",
                              result["native_diagnostic_text"])
                codes = {item["code"] for item in result["legality"]["reasons"]}
                self.assertIn("NATIVE_PEACE_EMPTY_OFFER_VALIDITY_FALSE", codes)
            else:
                self.assertTrue(result["native_validity"])
                self.assertIsNone(result["native_diagnostic_text"])
                self.assertIn("外交官",
                              result["diagnostics"]["common_action_gate"]["text"])
                codes = {item["code"] for item in result["legality"]["reasons"]}
                self.assertIn("NATIVE_PEACE_EMPTY_OFFER_COMMON_GATE_FALSE", codes)

    def test_query4_r38c_real_evaluation_replays_dynamic_factors_without_ids(self):
        fixture = json.loads(REAL_EVALUATION_FIXTURE.read_text(
            encoding="utf-8"))
        self.assertEqual(3, fixture["event_count"])
        self.assertEqual(3, len(fixture["events"]))
        expected_text = [
            "英格兰国内的起义：",
            "英格兰控制着首都伦敦：",
            "战争持续时间：",
            "英格兰的军事实力：",
            "盟友的相对实力：",
        ]
        for event in fixture["events"]:
            recipient = event["recipient"]
            self.assertTrue(ObserverSession._valid_native_peace_empty_offer_inspection(
                event, "white_peace", "FRA", recipient, "initiate",
                event["date_raw"], event["war_id"], event["query_id"],
                event["session_id"]))
            projected = ObserverSession._semantic_peace_empty_offer_inspection(
                event, "eu4_escape")
            evaluation = projected["native_evaluation"]
            if recipient == "ENG":
                self.assertTrue(evaluation["called"])
                self.assertEqual(-45, evaluation["score_raw"])
                self.assertEqual(-45, evaluation["native_total"])
                self.assertTrue(evaluation["score_available"])
                self.assertEqual(0, evaluation["aggregate_score_raw"])
                self.assertTrue(evaluation["aggregate_score_available"])
                self.assertEqual([1, -5, -45, 5, -1], [
                    item["native_value"] for item in evaluation["items"]])
                self.assertEqual([True, False, False, True, False], [
                    item["native_flag"] for item in evaluation["items"]])
                self.assertEqual(expected_text, [
                    item["text"] for item in evaluation["items"]])
                self.assertEqual([None] * 5, [
                    item["native_identifier"] for item in evaluation["items"]])
                self.assertTrue(all(
                    item["native_value_verified"]
                    and item["native_flag_verified"]
                    and not item["identifier_verified"]
                    for item in evaluation["items"]))
            else:
                self.assertFalse(evaluation["called"])
                self.assertFalse(evaluation["score_available"])
                self.assertIsNone(evaluation["native_total"])
                self.assertFalse(evaluation["aggregate_score_available"])
                self.assertEqual([], evaluation["items"])

            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                session = ObserverSession(
                    self._installation(root, empty_offer_ack=True,
                                       evaluation_ack=True,
                                       native_text_codec="eu4_escape"),
                    root / "eu4.exe")
                result = self._run_empty_offer_query(
                    session, event, recipient=recipient)
            public_text = json.dumps(result, ensure_ascii=False)
            for private_key in ("frame_thread", "_source_line", "native_ref"):
                self.assertNotIn(private_key, public_text)
            if recipient == "ENG":
                self.assertEqual(expected_text, [
                    item["text"] for item in result["acceptance"]["items"]])
                self.assertEqual(-45, result["acceptance"]["native_total"])
                self.assertEqual(0, result["costs"]["native_evaluation"][
                    "aggregate_score_raw"])


if __name__ == "__main__":
    unittest.main()
