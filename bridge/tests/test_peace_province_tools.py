from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_catalog import ACTIONS
from bridge.diplomacy_journal import DurableJournal


REAL_EMPTY = (Path(__file__).parent / "fixtures" /
              "peace_empty_offer_r38b_real_inspections.json")
REAL_R41C = (Path(__file__).parent / "fixtures" /
             "peace_province_r41c_real_inspections.json")
REAL_R41E = (Path(__file__).parent / "fixtures" /
             "peace_province_r41e_real_inspections.json")
REAL_R46D = (Path(__file__).parent / "fixtures" /
             "peace_r46d_offer_province_real_inspections.json")


class PeaceProvinceToolsTests(unittest.TestCase):
    @staticmethod
    def _event() -> dict:
        return json.loads(REAL_EMPTY.read_text(encoding="utf-8"))["events"][0]

    @staticmethod
    def _province_state(*, selected: bool = True) -> dict:
        return {
            "query_complete": True,
            "candidate_enumeration_complete": True,
            "candidate_count": 1,
            "candidates": [{
                "province_id": 177,
                "beneficiary": "FRA",
                "selected": selected,
                "name_hex": "",
                "name_readable": False,
                "name_truncated": False,
                "native_selectability_checked": False,
                "native_selectable": None,
            }],
            "selection_requested": selected,
            "requested_province_ids": [177] if selected else [],
            "requested_beneficiary": "FRA" if selected else None,
            "requested_candidates_found": selected,
            "toggle_called": selected,
            "toggle_call_count": 1 if selected else 0,
            "parameters_matched": selected,
            "selected_province_ids": [177] if selected else [],
            "selected_beneficiary": "FRA" if selected else None,
            "selection_copy_verified": selected,
            "selected_term_records_complete": selected,
            "direction": "demand",
            "direction_verified": True,
            "reason_code": None,
            "selection_delta_raw": 0 if selected else None,
        }

    def test_normalization_preserves_order_and_rejects_bad_lists(self):
        war_id = "war_5673519a7126f7e2_00000001"
        candidate = {"peace_context": {
            "war_id": war_id, "direction": "demand", "terms": []}}
        self.assertEqual([], DiplomacyTools._normalize_peace_province_offer_parameters(
            candidate, "FRA", "ENG")["province_ids"])
        selected = {"peace_context": {
            "war_id": war_id, "direction": "demand", "terms": [{
                "action_id": "cede_province", "province_ids": [177, 12],
                "beneficiary": "FRA",
            }]}}
        normalized = DiplomacyTools._normalize_peace_province_offer_parameters(
            selected, "FRA", "ENG")
        self.assertEqual([177, 12], normalized["province_ids"])
        self.assertEqual("FRA", normalized["beneficiary"])
        for bad in ([True], [177, 177], list(range(1, 18))):
            malformed = copy.deepcopy(selected)
            malformed["peace_context"]["terms"][0]["province_ids"] = bad
            with self.assertRaises(ValueError):
                DiplomacyTools._normalize_peace_province_offer_parameters(
                    malformed, "FRA", "ENG")

    def test_query6_ack_gate_and_wire_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = root / "installation.json"
            installation.write_text(json.dumps({
                "experiment_id": "province-contract", "session_id": "province-session",
                "pid": 1, "creation_filetime": 2, "dll_sha256": "dll",
                "controlled_countries": ["FRA"], "installation_returncode": 0,
            }), encoding="utf-8")
            (root / "control-probe.jsonl").write_text(json.dumps({
                "event": "diplomacy_observer_installed",
                "session_id": "province-session",
                "native_peace_province_offer_query": True,
            }) + "\n", encoding="utf-8")
            session = ObserverSession(installation, root / "eu4.exe")
            selection = {
                "war_id": "war_5673519a7126f7e2_00000001",
                "direction": "demand", "province_ids": [177, 12],
                "beneficiary": "FRA",
            }
            with patch.object(session, "inspect_alliance",
                              return_value={"event": "test"}) as inspect:
                result = session.inspect_peace_province_offer(
                    "cede_province", "FRA", "ENG", "initiate", selection)
            self.assertEqual({"event": "test"}, result)
            self.assertEqual("native_peace_province_offer_inspection",
                             inspect.call_args.kwargs["inspection_event"])
            self.assertEqual(selection,
                             inspect.call_args.kwargs["peace_province_offer"])
            self.assertIn("native_peace_province_offer_query",
                          session.installation_capabilities())

    def test_query7_offer_wire_and_projection_preserve_direction(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = root / "installation.json"
            installation.write_text(json.dumps({
                "experiment_id": "province-offer-contract",
                "session_id": "province-offer-session", "pid": 1,
                "creation_filetime": 2, "dll_sha256": "dll",
                "controlled_countries": ["FRA"],
                "installation_returncode": 0,
            }), encoding="utf-8")
            (root / "control-probe.jsonl").write_text(json.dumps({
                "event": "diplomacy_observer_installed",
                "session_id": "province-offer-session",
                "native_peace_province_offer_query": True,
            }) + "\n", encoding="utf-8")
            session = ObserverSession(installation, root / "eu4.exe")
            event = self._event()
            event.update({
                "event": "native_peace_province_offer_inspection",
                "action_id": "cede_province",
                "direction": "offer",
                "session_id": session.session_id,
            })
            event["native_provinces"] = self._province_state()
            event["native_provinces"].update({
                "direction": "offer", "requested_beneficiary": "ENG",
                "selected_beneficiary": "ENG",
            })
            request = root / "diplomacy-query.request"
            errors: list[BaseException] = []

            def writer() -> None:
                try:
                    deadline = time.monotonic() + 2
                    while not request.exists() and time.monotonic() < deadline:
                        time.sleep(0.001)
                    self.assertTrue(request.exists())
                    fields = request.read_text(encoding="ascii").strip().split()
                    self.assertEqual("EU4DIP_QUERY7", fields[0])
                    self.assertEqual("cede_province", fields[3])
                    self.assertEqual("FRA", fields[4])
                    self.assertEqual("ENG", fields[5])
                    self.assertEqual(event["war_id"], fields[8])
                    self.assertEqual("offer", fields[9])
                    self.assertEqual("-1", fields[10])
                    self.assertEqual("177", fields[11])
                    self.assertEqual("ENG", fields[12])
                    self.assertEqual(13, len(fields))
                    request.unlink(missing_ok=True)
                    actual = copy.deepcopy(event)
                    actual["query_id"] = fields[2]
                    with (root / "control-probe.jsonl").open(
                            "a", encoding="utf-8", newline="\n") as stream:
                        stream.write(json.dumps(actual) + "\n")
                except BaseException as exc:
                    errors.append(exc)

            thread = threading.Thread(target=writer)
            thread.start()
            ready = {"status": "ready", "state_id": "ready",
                     "date_raw": event["date_raw"], "reasons": [],
                     "complete": True}
            with patch.object(session, "health", return_value=ready), \
                 patch("bridge.diplomacy.probe_identity",
                       return_value={"session_id": session.session_id}):
                result = session.inspect_peace_province_offer(
                    "cede_province", "FRA", "ENG", "initiate", {
                        "war_id": event["war_id"], "direction": "offer",
                        "province_ids": [177], "beneficiary": "ENG",
                    })
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual([], errors)
            self.assertEqual("offer", result["peace_context"]["direction"])
            self.assertEqual("ENG", result["peace_context"]["terms"][0][
                "beneficiary"])

    def test_query7_empty_offer_candidate_wire_and_projection(self):
        """QUERY7 preserves an empty offer candidate request after native fix."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = root / "installation.json"
            installation.write_text(json.dumps({
                "experiment_id": "province-offer-candidate-contract",
                "session_id": "province-offer-candidate-session", "pid": 1,
                "creation_filetime": 2, "dll_sha256": "dll",
                "controlled_countries": ["FRA"],
                "installation_returncode": 0,
            }), encoding="utf-8")
            (root / "control-probe.jsonl").write_text(json.dumps({
                "event": "diplomacy_observer_installed",
                "session_id": "province-offer-candidate-session",
                "native_peace_province_offer_query": True,
            }) + "\n", encoding="utf-8")
            session = ObserverSession(installation, root / "eu4.exe")
            event = self._event()
            event.update({
                "event": "native_peace_province_offer_inspection",
                "action_id": "cede_province",
                "direction": "offer",
                "session_id": session.session_id,
                "native_provinces": self._province_state(selected=False),
            })
            event["native_provinces"].update({
                "direction": "offer", "requested_beneficiary": None,
                "selected_beneficiary": None,
                "selection_copy_verified": True,
                "selected_term_records_complete": True,
            })
            request = root / "diplomacy-query.request"
            errors: list[BaseException] = []

            def writer() -> None:
                try:
                    deadline = time.monotonic() + 2
                    while not request.exists() and time.monotonic() < deadline:
                        time.sleep(0.001)
                    self.assertTrue(request.exists())
                    fields = request.read_text(encoding="ascii").strip().split()
                    self.assertEqual("EU4DIP_QUERY7", fields[0])
                    self.assertEqual("cede_province", fields[3])
                    self.assertEqual("FRA", fields[4])
                    self.assertEqual("ENG", fields[5])
                    self.assertEqual(event["war_id"], fields[8])
                    self.assertEqual("offer", fields[9])
                    self.assertEqual(["-1", "-", "-"], fields[10:13])
                    self.assertEqual(13, len(fields))
                    request.unlink(missing_ok=True)
                    actual = copy.deepcopy(event)
                    actual["query_id"] = fields[2]
                    with (root / "control-probe.jsonl").open(
                            "a", encoding="utf-8", newline="\n") as stream:
                        stream.write(json.dumps(actual) + "\n")
                except BaseException as exc:
                    errors.append(exc)

            thread = threading.Thread(target=writer)
            thread.start()
            ready = {"status": "ready", "state_id": "ready",
                     "date_raw": event["date_raw"], "reasons": [],
                     "complete": True}
            selection = {
                "war_id": event["war_id"], "direction": "offer",
                "province_ids": [], "beneficiary": None,
            }
            with patch.object(session, "health", return_value=ready), \
                 patch("bridge.diplomacy.probe_identity",
                       return_value={"session_id": session.session_id}):
                result = session.inspect_peace_province_offer(
                    "cede_province", "FRA", "ENG", "initiate", selection)
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual([], errors)
            self.assertEqual("offer", result["peace_context"]["direction"])
            self.assertEqual([], result["peace_context"]["terms"])
            self.assertEqual([], result["native_provinces"][
                "selected_province_ids"])

    def test_public_reader_emits_query6_and_projects_actual_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = root / "installation.json"
            installation.write_text(json.dumps({
                "experiment_id": "province-query", "session_id": "province-session",
                "pid": 1, "creation_filetime": 2, "dll_sha256": "dll",
                "controlled_countries": ["FRA"], "installation_returncode": 0,
            }), encoding="utf-8")
            (root / "control-probe.jsonl").write_text(json.dumps({
                "event": "diplomacy_observer_installed",
                "session_id": "province-session",
                "native_peace_province_offer_query": True,
            }) + "\n", encoding="utf-8")
            session = ObserverSession(installation, root / "eu4.exe")
            event = self._event()
            event.update({
                "event": "native_peace_province_offer_inspection",
                "action_id": "cede_province",
                "session_id": session.session_id,
                "native_provinces": self._province_state(),
            })
            event["native_provinces"]["selected_province_ids"] = [177, 12]
            event["native_provinces"]["requested_province_ids"] = [177, 12]
            request = root / "diplomacy-query.request"
            log = root / "control-probe.jsonl"
            errors = []

            def writer() -> None:
                try:
                    deadline = time.monotonic() + 2
                    while not request.exists() and time.monotonic() < deadline:
                        time.sleep(0.001)
                    self.assertTrue(request.exists())
                    fields = request.read_text(encoding="ascii").strip().split()
                    self.assertEqual("EU4DIP_QUERY6", fields[0])
                    self.assertEqual("cede_province", fields[3])
                    self.assertEqual("177,12", fields[9])
                    self.assertEqual("FRA", fields[10])
                    self.assertEqual(11, len(fields))
                    request.unlink(missing_ok=True)
                    event["query_id"] = fields[2]
                    with log.open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps(event) + "\n")
                except BaseException as exc:
                    errors.append(exc)

            thread = threading.Thread(target=writer)
            thread.start()
            ready = {"status": "ready", "state_id": "ready",
                     "date_raw": event["date_raw"], "reasons": [], "complete": True}
            parameters = {"peace_context": {
                "war_id": event["war_id"], "direction": "demand", "terms": [{
                    "action_id": "cede_province", "province_ids": [177, 12],
                    "beneficiary": "FRA",
                }]}}
            journal = DurableJournal(":memory:", "province-query", session.session_id)
            try:
                with patch.object(session, "health", return_value=ready), \
                     patch("bridge.diplomacy.probe_identity",
                           return_value={"session_id": session.session_id}):
                    result = DiplomacyTools(journal, session).inspect_diplomatic_action(
                        "cede_province", "FRA", "ENG", parameters=parameters)
            finally:
                journal.close()
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual([], errors)
            self.assertEqual("native_peace_province_offer_inspection", result["interface_support"]["query"])
            self.assertEqual([177, 12], result["parameters"]["actual"]["peace_context"]["terms"][0]["province_ids"])
            self.assertEqual("unavailable", result["legality"]["status"])

    def test_real_common_event_and_province_projection(self):
        event = self._event()
        event.update({
            "event": "native_peace_province_offer_inspection",
            "action_id": "cede_province",
            "native_provinces": self._province_state(),
        })
        selection = {
            "war_id": event["war_id"], "direction": "demand",
            "province_ids": [177], "beneficiary": "FRA",
        }
        self.assertTrue(ObserverSession._valid_native_peace_province_offer_inspection(
            event, "cede_province", "FRA", "ENG", "initiate",
            event["date_raw"], selection, event["query_id"], event["session_id"]))
        projected = ObserverSession._semantic_peace_province_offer_inspection(event)
        self.assertEqual("native_peace_province_offer_inspection", projected["event"])
        self.assertEqual([177], projected["peace_context"]["terms"][0]["province_ids"])
        self.assertEqual("FRA", projected["native_provinces"]["selected_beneficiary"])
        self.assertNotIn("native_ref", projected["native_provinces"])

    def test_malformed_candidate_membership_is_rejected(self):
        event = self._event()
        event.update({
            "event": "native_peace_province_offer_inspection",
            "action_id": "cede_province",
            "native_provinces": self._province_state(),
        })
        event["native_provinces"]["candidates"].append(
            copy.deepcopy(event["native_provinces"]["candidates"][0]))
        selection = {
            "war_id": event["war_id"], "direction": "demand",
            "province_ids": [177], "beneficiary": "FRA",
        }
        self.assertFalse(ObserverSession._valid_native_peace_province_offer_inspection(
            event, "cede_province", "FRA", "ENG", "initiate",
            event["date_raw"], selection, event["query_id"], event["session_id"]))

    def test_copy_proof_is_independent_from_requested_match(self):
        event = self._event()
        event.update({
            "event": "native_peace_province_offer_inspection",
            "action_id": "cede_province",
        })
        empty = self._province_state(selected=False)
        empty["selection_copy_verified"] = True
        empty["selected_term_records_complete"] = True
        event["native_provinces"] = empty
        self.assertTrue(ObserverSession._valid_native_peace_province_offer_inspection(
            event, "cede_province", "FRA", "ENG", "initiate",
            event["date_raw"], {
                "war_id": event["war_id"], "direction": "demand",
                "province_ids": [], "beneficiary": None,
            }, event["query_id"], event["session_id"]))

        absent = copy.deepcopy(empty)
        absent.update({
            "selection_requested": True,
            "requested_province_ids": [999],
            "requested_beneficiary": "FRA",
            "requested_candidates_found": False,
            "reason_code": "NATIVE_PEACE_PROVINCE_CANDIDATE_ABSENT",
        })
        event["native_provinces"] = absent
        self.assertTrue(ObserverSession._valid_native_peace_province_offer_inspection(
            event, "cede_province", "FRA", "ENG", "initiate",
            event["date_raw"], {
                "war_id": event["war_id"], "direction": "demand",
                "province_ids": [999], "beneficiary": "FRA",
            }, event["query_id"], event["session_id"]))

    def test_r41c_real_inspections_validate_and_keep_actual_selection(self):
        with REAL_R41C.open(encoding="utf-8") as stream:
            fixture = json.load(stream)
        self.assertEqual(4, fixture["event_count"])
        self.assertEqual(
            "cde0d413445d6186abb390f60e1dd9f43f6d8dad8c35c8aaf5f6fb30b1fd0445",
            fixture["source"]["native_events_sha256"])
        self.assertEqual(
            "f5be048193d2ab47b2a8032eca2e6161e5103816b232696c92511467b409fb1b",
            fixture["source"]["dll_sha256"])
        self.assertEqual("41488-1dd5d38938c676e", fixture["source"]["session_id"])

        expected_deltas = {
            (): None,
            (177,): 8,
            (177, 87): 20,
            (2147483647,): None,
        }
        expected_names = {87: "加莱", 177: "曼恩", 233: "康沃尔"}
        for item in fixture["events"]:
            event = item["event"]
            native = event["native_provinces"]
            requested = tuple(native["requested_province_ids"])
            selection = {
                "war_id": event["war_id"],
                "direction": "demand",
                "province_ids": list(requested),
                "beneficiary": native["requested_beneficiary"],
            }
            self.assertTrue(ObserverSession._valid_native_peace_province_offer_inspection(
                event, "cede_province", event["actor"], event["recipient"],
                event["phase"], event["date_raw"], selection,
                event["query_id"], event["session_id"]))

            projected = ObserverSession._semantic_peace_province_offer_inspection(
                event, "eu4_escape")
            public = projected["native_provinces"]
            self.assertEqual(41, public["candidate_count"])
            self.assertEqual(41, len(public["candidates"]))
            self.assertEqual([], public["selected_province_ids"])
            self.assertFalse(public["parameters_matched"])
            self.assertTrue(public["selection_copy_verified"])
            self.assertEqual(expected_deltas[requested],
                             public["selection_delta_raw"])
            # The native action left the actual term list empty.  A request
            # that did not match must not be echoed as an actual peace term.
            self.assertEqual([], projected["peace_context"]["terms"])

            names = {row["province_id"]: row["name"]
                     for row in public["candidates"]}
            for province_id, expected_name in expected_names.items():
                self.assertEqual(expected_name, names[province_id])
            self.assertTrue(all(isinstance(row["name"], str) and row["name"]
                                for row in public["candidates"]))

            evaluation = event["native_evaluation"]
            self.assertFalse(evaluation["called"])
            self.assertFalse(evaluation["score_available"])
            self.assertFalse(evaluation["aggregate_score_available"])
            self.assertEqual([], evaluation["items"])

            private_keys = {
                "frame_thread", "native_ref", "native_pointer", "term_pointer",
                "province_pointer", "pointer", "private",
            }

            def assert_no_private_keys(value):
                if isinstance(value, dict):
                    self.assertTrue(private_keys.isdisjoint(value))
                    for child in value.values():
                        assert_no_private_keys(child)
                elif isinstance(value, list):
                    for child in value:
                        assert_no_private_keys(child)

            assert_no_private_keys(projected)

    @staticmethod
    def _r41e_installation(root: Path, *, evaluation_ack: bool) -> Path:
        session_id = "r41e-province-session"
        installation = root / "installation.json"
        installation.write_text(json.dumps({
            "experiment_id": "r41e-province-contract",
            "session_id": session_id,
            "pid": 1,
            "creation_filetime": 2,
            "dll_sha256": "dll",
            "controlled_countries": ["FRA"],
            "installation_returncode": 0,
        }), encoding="utf-8")
        installed = {
            "event": "diplomacy_observer_installed",
            "session_id": session_id,
            "native_peace_province_offer_query": True,
        }
        if evaluation_ack:
            installed["native_peace_offer_evaluation_query"] = True
        (root / "control-probe.jsonl").write_text(
            json.dumps(installed) + "\n", encoding="utf-8")
        return installation

    def _run_r41e_public_query(self, event: dict, *, evaluation_ack: bool) -> dict:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = self._r41e_installation(
                root, evaluation_ack=evaluation_ack)
            session = ObserverSession(installation, root / "eu4.exe")
            request = root / "diplomacy-query.request"
            log = root / "control-probe.jsonl"
            errors: list[BaseException] = []
            native = event["native_provinces"]

            def writer() -> None:
                try:
                    deadline = time.monotonic() + 2
                    while not request.exists() and time.monotonic() < deadline:
                        time.sleep(0.001)
                    if not request.exists():
                        raise AssertionError("QUERY6 request was not published")
                    fields = request.read_text(encoding="ascii").strip().split()
                    self.assertEqual("EU4DIP_QUERY6", fields[0])
                    self.assertEqual("cede_province", fields[3])
                    self.assertEqual("FRA", fields[4])
                    self.assertEqual(event["recipient"], fields[5])
                    self.assertEqual(event["war_id"], fields[8])
                    self.assertEqual(
                        ",".join(str(value)
                                 for value in native["requested_province_ids"])
                        or "-", fields[9])
                    self.assertEqual(native["requested_beneficiary"] or "-",
                                     fields[10])
                    self.assertEqual(11, len(fields))
                    request.unlink(missing_ok=True)
                    actual = copy.deepcopy(event)
                    actual["query_id"] = fields[2]
                    actual["session_id"] = session.session_id
                    with log.open("a", encoding="utf-8", newline="") as stream:
                        stream.write(json.dumps(actual, ensure_ascii=False) + "\n")
                except BaseException as exc:
                    errors.append(exc)

            thread = threading.Thread(target=writer)
            thread.start()
            ready = {"status": "ready", "state_id": "ready",
                     "date_raw": event["date_raw"], "reasons": [],
                     "complete": True}
            parameters = {"peace_context": {
                "war_id": event["war_id"], "direction": "demand",
                "terms": [{
                    "action_id": "cede_province",
                    "province_ids": list(native["requested_province_ids"]),
                    "beneficiary": native["requested_beneficiary"],
                }]}}
            journal = DurableJournal(":memory:", "r41e-province",
                                     session.session_id)
            try:
                with patch.object(session, "health", return_value=ready), \
                     patch("bridge.diplomacy.probe_identity",
                           return_value={"session_id": session.session_id}):
                    result = DiplomacyTools(journal, session).inspect_diplomatic_action(
                        "cede_province", "FRA", event["recipient"],
                        parameters=parameters)
            finally:
                journal.close()
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual([], errors)
            return result

    def test_r41e_real_inspections_keep_persistent_selection_and_evaluation(self):
        with REAL_R41E.open(encoding="utf-8") as stream:
            fixture = json.load(stream)
        self.assertEqual(4, fixture["event_count"])
        self.assertEqual(
            "4ef6db4509c359e5fb2bb36409ec6770efe52f34ab9f5d01347c7a6c56ee131c",
            fixture["source"]["native_events_sha256"])
        self.assertEqual(
            "81e42dad409ccc614f051b45e861d738bd60deee5f7099d6bd5659b727bd4ac2",
            fixture["source"]["dll_sha256"])
        self.assertEqual("30988-1dd5d41376255c3", fixture["source"]["session_id"])

        expected = {
            (): ([], None, False),
            (177,): ([177], 8, True),
            (177, 87): ([87, 177], 20, True),
            (2147483647,): ([], None, False),
        }
        private_keys = {
            "frame_thread", "native_ref", "native_pointer", "term_pointer",
            "province_pointer", "pointer", "private",
        }

        def assert_no_private_keys(value):
            if isinstance(value, dict):
                self.assertTrue(private_keys.isdisjoint(value))
                for child in value.values():
                    assert_no_private_keys(child)
            elif isinstance(value, list):
                for child in value:
                    assert_no_private_keys(child)

        for item in fixture["events"]:
            event = item["event"]
            native = event["native_provinces"]
            requested = tuple(native["requested_province_ids"])
            selected, delta, has_evaluation = expected[requested]
            selection = {
                "war_id": event["war_id"],
                "direction": "demand",
                "province_ids": list(requested),
                "beneficiary": native["requested_beneficiary"],
            }
            self.assertTrue(ObserverSession._valid_native_peace_province_offer_inspection(
                event, "cede_province", event["actor"], event["recipient"],
                event["phase"], event["date_raw"], selection,
                event["query_id"], event["session_id"]))
            projected = ObserverSession._semantic_peace_province_offer_inspection(
                event, "eu4_escape")
            public = projected["native_provinces"]
            self.assertEqual(selected, public["selected_province_ids"])
            self.assertEqual(delta, public["selection_delta_raw"])
            self.assertTrue(public["selection_copy_verified"])
            self.assertEqual(selected, projected["peace_context"]["terms"][0][
                "province_ids"] if selected else [])
            evaluation = projected["native_evaluation"]
            self.assertEqual(has_evaluation, evaluation["called"])
            if has_evaluation:
                self.assertEqual(-100, evaluation["native_total"])
                self.assertEqual(-100, evaluation["score_raw"])
                self.assertEqual(delta, evaluation["aggregate_score_raw"])
                self.assertEqual(9, evaluation["factor_native_count"])
                self.assertEqual(9, len(evaluation["items"]))
                self.assertTrue(evaluation["factors_complete"])
                self.assertTrue(all(
                    item["native_value_verified"]
                    and item["native_flag_verified"]
                    for item in evaluation["items"]))
            else:
                self.assertIsNone(evaluation["native_total"])
                self.assertEqual([], evaluation["items"])
            self.assertEqual(
                2 if requested == (177,) else 3 if requested == (177, 87)
                else 1, event["native_payload"]["selected_term_count"])
            assert_no_private_keys(projected)

        pair = next(item["event"] for item in fixture["events"]
                     if tuple(item["event"]["native_provinces"][
                         "requested_province_ids"]) == (177, 87))
        with_ack = self._run_r41e_public_query(
            pair, evaluation_ack=True)
        self.assertEqual([87, 177], with_ack["native_provinces"][
            "selected_province_ids"])
        self.assertEqual(-100, with_ack["acceptance"]["native_total"])
        self.assertEqual(9, len(with_ack["acceptance"]["items"]))
        self.assertEqual(20, with_ack["costs"]["native_evaluation"][
            "aggregate_score_raw"])
        self.assertEqual(20, with_ack["native_evaluation"][
            "aggregate_score_raw"])
        self.assertNotIn("frame_thread", json.dumps(with_ack, ensure_ascii=False))

        without_ack = self._run_r41e_public_query(
            pair, evaluation_ack=False)
        self.assertEqual([87, 177], without_ack["native_provinces"][
            "selected_province_ids"])
        self.assertNotIn("native_evaluation", without_ack)
        self.assertNotIn("native_evaluation", without_ack["costs"])
        self.assertIsNone(without_ack["acceptance"]["native_total"])
        self.assertNotIn("frame_thread", json.dumps(without_ack, ensure_ascii=False))

    @staticmethod
    def _r46d_installation(root: Path, *, session_id: str,
                           submission_ack: bool) -> Path:
        installation = root / "installation.json"
        installation.write_text(json.dumps({
            "experiment_id": "r46d-offer-province-replay",
            "session_id": session_id,
            "pid": 1,
            "creation_filetime": 2,
            "dll_sha256": "6b48f5bad67ee33d79f50fa16ead9d6430bc02a061cd6443be186731149a4cff",
            "native_text_codec": "eu4_escape",
            "controlled_countries": ["FRA"],
            "installation_returncode": 0,
        }), encoding="utf-8")
        installed = {
            "event": "diplomacy_observer_installed",
            "session_id": session_id,
            "native_peace_province_offer_query": True,
            "native_peace_offer_evaluation_query": True,
            "native_peace_wrapper_rule_query": True,
        }
        if submission_ack:
            installed["native_peace_submission"] = True
        (root / "control-probe.jsonl").write_text(
            json.dumps(installed) + "\n", encoding="utf-8")
        return installation

    def _run_r46d_public_query(self, event: dict, *, submission_ack: bool) -> dict:
        """Replay one R46D offer event through the public QUERY7 reader."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session_id = event["session_id"]
            installation = self._r46d_installation(
                root, session_id=session_id, submission_ack=submission_ack)
            session = ObserverSession(installation, root / "eu4.exe")
            request = root / "diplomacy-query.request"
            log = root / "control-probe.jsonl"
            errors: list[BaseException] = []
            native = event["native_provinces"]
            requested_ids = list(native["requested_province_ids"])
            requested_beneficiary = native["requested_beneficiary"]

            def writer() -> None:
                try:
                    deadline = time.monotonic() + 2
                    while not request.exists() and time.monotonic() < deadline:
                        time.sleep(0.001)
                    if not request.exists():
                        raise AssertionError("R46D QUERY7 request was not published")
                    fields = request.read_text(encoding="ascii").strip().split()
                    self.assertEqual("EU4DIP_QUERY7", fields[0])
                    self.assertEqual("cede_province", fields[3])
                    self.assertEqual("FRA", fields[4])
                    self.assertEqual(event["recipient"], fields[5])
                    self.assertEqual(event["war_id"], fields[8])
                    self.assertEqual("offer", fields[9])
                    self.assertEqual("-1", fields[10])
                    self.assertEqual(
                        ",".join(str(value) for value in requested_ids) or "-",
                        fields[11])
                    self.assertEqual(requested_beneficiary or "-", fields[12])
                    self.assertEqual(13, len(fields))
                    request.unlink(missing_ok=True)
                    actual = copy.deepcopy(event)
                    actual["query_id"] = fields[2]
                    actual["session_id"] = session.session_id
                    with log.open("a", encoding="utf-8", newline="") as stream:
                        stream.write(json.dumps(actual, ensure_ascii=False) + "\n")
                except BaseException as exc:
                    errors.append(exc)

            thread = threading.Thread(target=writer)
            thread.start()
            ready = {"status": "ready", "state_id": "ready",
                     "date_raw": event["date_raw"], "reasons": [],
                     "complete": True}
            terms = []
            if requested_ids:
                terms = [{
                    "action_id": "cede_province",
                    "province_ids": requested_ids,
                    "beneficiary": requested_beneficiary,
                }]
            parameters = {"peace_context": {
                "war_id": event["war_id"],
                "direction": "offer",
                "terms": terms,
            }}
            journal = DurableJournal(":memory:", "r46d-province",
                                     session.session_id)
            try:
                with patch.object(session, "health", return_value=ready), \
                     patch("bridge.diplomacy.probe_identity",
                           return_value={"session_id": session.session_id}):
                    result = DiplomacyTools(journal, session).inspect_diplomatic_action(
                        "cede_province", "FRA", event["recipient"],
                        parameters=parameters)
            finally:
                journal.close()
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual([], errors)
            return result

    def test_r46d_real_offer_candidate_and_selected_4111_replay(self):
        """Replay D's offer candidate and 4111 selection through the readers."""
        with REAL_R46D.open(encoding="utf-8") as stream:
            fixture = json.load(stream)
        self.assertEqual(2, fixture["event_count"])
        self.assertEqual(
            "ae6e1d49fd93b24c49cc142f43f6dbe01e8c1413d5130c3eeae1f18abaafa1cd",
            fixture["source"]["native_events_sha256"])
        self.assertEqual(
            "6b48f5bad67ee33d79f50fa16ead9d6430bc02a061cd6443be186731149a4cff",
            fixture["source"]["dll_sha256"])
        self.assertEqual("46996-1dd5d80a65e2e1b", fixture["source"]["session_id"])
        self.assertEqual(1031, fixture["events"][0]["source_line"])
        self.assertEqual(3621, fixture["events"][1]["source_line"])
        self.assertEqual(
            "c32358e178539e3175d552c24447ed04531742898068a8aa9bd944221f712eb6",
            fixture["events"][0]["event_sha256"])
        self.assertEqual(
            "333087da2c763699ddd6e8885cd687971f54f0e5bc7ba572aa51c5d96f21c0e9",
            fixture["events"][1]["event_sha256"])

        private_keys = {
            "frame_thread", "native_ref", "native_pointer", "term_pointer",
            "province_pointer", "pointer", "private",
        }

        def assert_no_private_keys(value):
            if isinstance(value, dict):
                self.assertTrue(private_keys.isdisjoint(value))
                for child in value.values():
                    assert_no_private_keys(child)
            elif isinstance(value, list):
                for child in value:
                    assert_no_private_keys(child)

        candidate_event = fixture["events"][0]["event"]
        selected_event = fixture["events"][1]["event"]
        for event in (candidate_event, selected_event):
            native = event["native_provinces"]
            selection = {
                "war_id": event["war_id"],
                "direction": "offer",
                "province_ids": list(native["requested_province_ids"]),
                "beneficiary": native["requested_beneficiary"],
            }
            self.assertTrue(ObserverSession._valid_native_peace_province_offer_inspection(
                event, "cede_province", "FRA", "ENG", "initiate",
                event["date_raw"], selection, event["query_id"],
                event["session_id"]))

        candidate = ObserverSession._semantic_peace_province_offer_inspection(
            candidate_event, fixture["source"]["native_text_codec"])
        candidate_native = candidate["native_provinces"]
        self.assertEqual("offer", candidate["peace_context"]["direction"])
        self.assertEqual([], candidate["peace_context"]["terms"])
        self.assertEqual(33, candidate_native["candidate_count"])
        self.assertEqual(33, len(candidate_native["candidates"]))
        self.assertFalse(candidate_native["parameters_matched"])
        self.assertEqual([], candidate_native["selected_province_ids"])
        self.assertTrue(all(row["beneficiary"] == "ENG"
                            for row in candidate_native["candidates"]))
        self.assertIn(4111, [row["province_id"]
                             for row in candidate_native["candidates"]])
        self.assertTrue(all(row["name_readable"] and row["name"]
                            for row in candidate_native["candidates"]))
        self.assertFalse(candidate["native_evaluation"]["called"])
        assert_no_private_keys(candidate)

        selected = ObserverSession._semantic_peace_province_offer_inspection(
            selected_event, fixture["source"]["native_text_codec"])
        selected_native = selected["native_provinces"]
        self.assertEqual("offer", selected["peace_context"]["direction"])
        self.assertEqual([{
            "action_id": "cede_province", "province_ids": [4111],
            "beneficiary": "ENG",
        }], selected["peace_context"]["terms"])
        self.assertTrue(selected_native["parameters_matched"])
        self.assertEqual([4111], selected_native["selected_province_ids"])
        self.assertEqual("ENG", selected_native["selected_beneficiary"])
        self.assertEqual(10, selected_native["selection_delta_raw"])
        evaluation = selected["native_evaluation"]
        self.assertEqual(-24, evaluation["native_total"])
        self.assertEqual(10, evaluation["aggregate_score_raw"])
        self.assertEqual(7, len(evaluation["items"]))
        unknown_items = [item for item in evaluation["items"]
                         if item["native_identifier"] is None]
        self.assertEqual(1, len(unknown_items))
        self.assertEqual("被占领和被围攻的省份：", unknown_items[0]["text"])
        self.assertTrue(unknown_items[0]["native_value_verified"])
        assert_no_private_keys(selected)

        candidate_public = self._run_r46d_public_query(
            candidate_event, submission_ack=False)
        self.assertEqual("native_peace_province_offer_inspection",
                         candidate_public["interface_support"]["query"])
        self.assertEqual("unknown", candidate_public["legality"]["status"])
        self.assertEqual([], candidate_public["parameters"]["actual"][
            "peace_context"]["terms"])
        self.assertEqual(33, len(candidate_public["parameters"]["candidates"]))
        self.assertTrue(all(row["name_readable"] and row["name"]
                            for row in candidate_public["parameters"][
                                "candidates"]))
        assert_no_private_keys(candidate_public)

        selected_public = self._run_r46d_public_query(
            selected_event, submission_ack=True)
        self.assertEqual("native_peace_execution_inspection",
                         selected_public["interface_support"]["query"])
        self.assertEqual("available", selected_public["legality"]["status"])
        self.assertTrue(selected_public["legality"]["complete"])
        self.assertEqual([4111], selected_public["parameters"]["actual"][
            "peace_context"]["terms"][0]["province_ids"])
        self.assertEqual("ENG", selected_public["parameters"]["actual"][
            "peace_context"]["terms"][0]["beneficiary"])
        self.assertEqual(-24, selected_public["acceptance"]["native_total"])
        self.assertEqual(10, selected_public["costs"]["native_evaluation"][
            "aggregate_score_raw"])
        public_unknown_items = [item for item in selected_public["acceptance"][
            "items"] if item["native_identifier"] is None]
        self.assertEqual(1, len(public_unknown_items))
        self.assertEqual(6, public_unknown_items[0]["native_value"])
        self.assertEqual("被占领和被围攻的省份：",
                         public_unknown_items[0]["text"])
        self.assertNotIn("frame_thread",
                         json.dumps(selected_public, ensure_ascii=False))
        assert_no_private_keys(selected_public)

    def test_catalog_exposes_candidate_and_selected_forms(self):
        description = ACTIONS["cede_province"].describe()
        forms = {item["name"]: item for item in description[
            "inspection_parameter_forms"]}
        self.assertEqual([], forms["candidate_enumeration"]["parameters"]
                         ["peace_context"]["terms"])
        self.assertEqual("peace_context.terms[0].province_ids",
                         description["parameter_definitions"]
                         ["peace_context.terms[0].province_ids"]["path"])
        self.assertEqual(16, description["parameter_definitions"]
                         ["peace_context.terms[0].province_ids"]["max_items"])


if __name__ == "__main__":
    unittest.main()
