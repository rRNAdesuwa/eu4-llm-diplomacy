from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal


FIXTURE = (Path(__file__).parent / "fixtures" /
           "peace_special_r54_real_inbound.json")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PRIVATE_MARKERS = {
    "session_id", "native_proposal_id", "query_id", "token3c", "date28",
    "date2c", "envoy30", "native_action", "native_node", "proposal3c",
    "created2c", "treasury_before_raw", "treasury_after_raw",
}


def _load_fixture() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class PeaceSpecialR54RealInboundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = _load_fixture()

    def _check_source(self, name: str) -> None:
        source = self.fixture["sources"][name]
        for key in ("path", "bytes", "sha256"):
            self.assertTrue(source[key])
        paths = [source, source["native_events"]]
        for metadata in paths:
            path = REPOSITORY_ROOT / metadata["path"]
            if path.exists():
                self.assertEqual(metadata["bytes"], path.stat().st_size)
                self.assertEqual(
                    metadata["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def _event(self, source_name: str, record: dict[str, object]) -> dict[str, object]:
        self._check_source(source_name)
        source = self.fixture["sources"][source_name]["native_events"]
        path = REPOSITORY_ROOT / source["path"]
        if path.exists():
            raw = path.read_bytes().splitlines()[record["source_line"] - 1]
            self.assertEqual(record["source_line_sha256"],
                             hashlib.sha256(raw).hexdigest())
            self.assertEqual(record["event"], json.loads(raw.decode("utf-8")))
        return record["event"]

    @staticmethod
    def _private_free(value: object) -> None:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        for marker in PRIVATE_MARKERS:
            if marker in text:
                raise AssertionError(f"private marker leaked: {marker}")

    def _session_for_events(self, root: Path, session_id: str,
                            events: list[dict[str, object]]) -> ObserverSession:
        installation = root / "installation.json"
        installation.write_text(json.dumps({
            "experiment_id": "r54-special-inbound-replay",
            "session_id": session_id,
            "native_text_codec": "eu4_escape",
        }, separators=(",", ":")), encoding="utf-8")
        ack = {
            "event": "diplomacy_observer_installed",
            "session_id": session_id,
            "native_inbound_alliance": True,
            "native_inbound_peace_response": True,
        }
        lines = [json.dumps(ack, separators=(",", ":"))]
        lines.extend(json.dumps(event, ensure_ascii=False,
                                separators=(",", ":")) for event in events)
        (root / "control-probe.jsonl").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")
        return ObserverSession(installation, root / "eu4.exe")

    def _replay_pending(self, event: dict[str, object]) -> tuple[list[dict], dict]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = self._session_for_events(root, event["session_id"], [event])
            journal = DurableJournal(":memory:", "r54-special-inbound-replay",
                                     event["session_id"])
            try:
                tools = DiplomacyTools(journal, session)
                offers = tools._read_inbound_proposals(
                    {"status": "ready", "date_raw": event["date28"]},
                    recipient="FRA")
                self.assertEqual(1, len(offers))
                context = tools._private_inbound_context(
                    {"status": "ready", "date_raw": event["date28"]},
                    offers[0]["proposal_id"], "peace_offer")
                self.assertIsNotNone(context)
                return offers, context
            finally:
                journal.close()

    def _replay_response(self, event: dict[str, object]) -> dict | None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = self._session_for_events(root, event["session_id"], [event])
            return session.read_native_peace_inbound_response(
                event["request_id"], event["actor"], event["recipient"],
                event["phase"], event["date_raw"], 1)

    def test_c_pending_and_e_restored_events_replay_to_safe_public_offers(self):
        c_record = self.fixture["cases"]["c_pending"]
        c_event = self._event("c", c_record)
        self.assertTrue(ObserverSession._valid_native_inbound_offer_event(
            c_event, c_event["session_id"]))
        offers, context = self._replay_pending(c_event)
        offer = offers[0]
        self.assertEqual("peace_offer", offer["action_id"])
        self.assertEqual("ENG", offer["actor"])
        self.assertEqual("FRA", offer["recipient"])
        self.assertEqual("peace", offer["family"])
        self.assertEqual("observed_pending", offer["observer_status"])
        self.assertEqual("native_inbound_response", offer["execute"]["accept"])
        self.assertEqual("native_inbound_response", offer["execute"]["reject"])
        self.assertEqual("ENG", context["actor"])
        self.assertEqual("FRA", context["recipient"])
        self._private_free(offer)

        e_record = self.fixture["cases"]["e_accept"]
        restored = self._event("e", e_record["restored_event"])
        self.assertTrue(ObserverSession._valid_native_inbound_pending_restored_event(
            restored, restored["session_id"]))
        restored_offers, _ = self._replay_pending(restored)
        self.assertEqual("saved_native_pending", restored_offers[0]["source"])
        self._private_free(restored_offers[0])

    def _assert_real_response(self, source_name: str, case_name: str,
                              *, accepted: bool) -> tuple[dict, dict, dict]:
        case = self.fixture["cases"][case_name]
        inspection = self._event(source_name, case["inspection_event"])
        submission = self._event(source_name, case["submission_event"])
        response = self._event(source_name, case["response_event"])
        self.assertTrue(ObserverSession._valid_native_inbound_inspection(
            inspection, inspection["query_id"], inspection["session_id"],
            inspection["actor"], inspection["phase"],
            inspection["native_proposal_id"], inspection["date_raw"],
            "peace_offer"))
        self.assertTrue(ObserverSession._valid_native_inbound_submission_result(
            submission, submission["request_id"], submission["session_id"],
            submission["actor"], submission["recipient"], submission["phase"],
            submission["date_raw"], inspection["native_proposal_id"],
            "peace_offer"))
        public_inspection = ObserverSession._public_native_inbound_inspection(
            inspection, inspection["date_raw"], "peace_offer")
        self.assertTrue(public_inspection["peace_context"]["complete"])
        self.assertTrue(public_inspection["peace_context"]["selected_terms_complete"])
        self.assertEqual("demand", public_inspection["peace_context"]["direction"])
        self.assertEqual("ENG", public_inspection["peace_context"]["original_actor"])
        self.assertEqual("FRA", public_inspection["peace_context"]["original_recipient"])
        self.assertEqual([{
            "action_id": "humiliate_rival", "country": "FRA", "beneficiary": "ENG",
        }], public_inspection["peace_context"]["terms"])
        public_submission = ObserverSession._public_native_inbound_submission_receipt(
            submission, submission["request_id"], submission["actor"],
            submission["phase"], submission["date_raw"], "peace_offer")
        public_result = ObserverSession._public_native_inbound_response_result(
            response, response["request_id"], response["session_id"],
            response["actor"], response["phase"], response["date_raw"],
            inspection["native_proposal_id"], "peace_offer")
        self.assertIsNotNone(public_submission)
        self.assertIsNotNone(public_result)
        assert public_result is not None
        self.assertEqual("accepted" if accepted else "rejected",
                         public_result["native_outcome"])
        self.assertEqual(2 if accepted else 1, public_result["native_state"])
        self.assertEqual(not accepted, public_result["war_after"])
        self.assertEqual(accepted, public_result["terms_verified"])
        self.assertTrue(public_result["pending_removed"])
        effect = public_result["effects"]["humiliate_rival"]
        self.assertEqual("FRA", effect["country"])
        self.assertEqual("ENG", effect["beneficiary"])
        self.assertFalse(effect["humiliated_before"])
        self.assertEqual(accepted, effect["humiliated_after"])
        self.assertTrue(effect["values_readable"])
        self.assertEqual(accepted, effect["verified"])
        consumed = self._replay_response(response)
        self.assertEqual(
            {"status": public_result["native_outcome"], "result": public_result},
            consumed)
        self._private_free({
            "inspection": public_inspection,
            "submission": public_submission,
            "result": public_result,
        })
        return response, inspection, public_result

    def test_d_reject_and_e_accept_project_real_context_and_h_effects(self):
        self._assert_real_response("d", "d_reject", accepted=False)
        self._assert_real_response("e", "e_accept", accepted=True)

    def test_forged_humiliate_consequences_are_rejected(self):
        d_case = self.fixture["cases"]["d_reject"]
        d_response = copy.deepcopy(d_case["response_event"]["event"])
        d_response["effects"]["humiliate_rival"]["verified"] = True
        self.assertIsNone(ObserverSession._public_native_inbound_response_result(
            d_response, d_response["request_id"], d_response["session_id"],
            d_response["actor"], d_response["phase"], d_response["date_raw"],
            1, "peace_offer"))

        e_case = self.fixture["cases"]["e_accept"]
        e_response = copy.deepcopy(e_case["response_event"]["event"])
        e_response["effects"]["humiliate_rival"]["beneficiary"] = "FRA"
        self.assertIsNone(ObserverSession._public_native_inbound_response_result(
            e_response, e_response["request_id"], e_response["session_id"],
            e_response["actor"], e_response["phase"], e_response["date_raw"],
            1, "peace_offer"))


if __name__ == "__main__":
    unittest.main()
