from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from bridge.diplomacy import ObserverSession, DiplomacyTools
from bridge.peace_execution import normalize_peace_execution_parameters


WAR_ID = "war_0123456789abcdef_01234567"
DATE_RAW = 56548944


def _common_event(*, source: str | None, selection_requested: bool,
                  matching: int, selected: bool, matched: bool,
                  candidates: list[dict[str, object]]) -> dict[str, object]:
    native = {
        "requested": True,
        "candidate_count": len(candidates),
        "matching_candidate_count": matching,
        "candidate_found": matching == 1,
        "selection_requested": selection_requested,
        "selection_available": matching == 1,
        "selected": selected,
        "selected_term_count": 1 if selected else 0,
        "source": source,
        "beneficiary": "FRA",
        "selection_copy_verified": selection_requested,
        "parameters_matched": matched,
        "reason_code": None,
        "rule_checked": selected,
        "rule_available": selected,
        "rule_term_count": 1 if selected else 0,
        "rule_scope": "selected_nonzero_terms",
        "rule_diagnostic_hex": "",
        "rule_diagnostic_readable": False,
        "rule_diagnostic_truncated": False,
        "candidates_available": True,
        "candidates_complete": True,
        "candidates_truncated": False,
        "candidates": candidates,
    }
    event: dict[str, object] = {
        "event": "native_peace_trade_power_offer_inspection",
        "family": "peace",
        "session_id": "source-session",
        "query_id": "source-query",
        "action_id": "transfer_trade_power",
        "actor": "FRA",
        "recipient": "ENG",
        "phase": "initiate",
        "date_raw": DATE_RAW,
        "war_id": WAR_ID,
        "direction": "demand",
        "identity_scope": "observer_session",
        "query_complete": True,
        "native_offer_inspected": True,
        "pair_at_war": True,
        "unique_shared_war": True,
        "offer_constructed": True,
        "action_constructed": True,
        "offer_identity_verified": True,
        "participant_copy_verified": True,
        "object_unchanged": True,
        "cleanup_verified": True,
        "validity_called": True,
        "native_validity": True,
        "common_gate_checked": True,
        "common_action_gate": True,
        "initiation_gate_checked": True,
        "initiation_gate": True,
        "native_diagnostic_hex": "",
        "diagnostic_readable": True,
        "diagnostic_truncated": False,
        "common_diagnostic_hex": "",
        "common_diagnostic_readable": False,
        "common_diagnostic_truncated": False,
        "send_diagnostic_hex": "",
        "send_diagnostic_readable": False,
        "send_diagnostic_truncated": False,
        "native_wrapper_gate_checked": True,
        "native_wrapper_gate": True,
        "wrapper_identity_verified": True,
        "wrapper_payload_unchanged": True,
        "full_rules_complete": selected,
        "reasons_complete": False,
        "submitted": False,
        "term_mask": "t",
        "native_money": None,
        "native_provinces": None,
        "native_reparations": None,
        "native_trade_power": native,
    }
    if selected:
        event["native_payload"] = {
            "schema": "native_peace_serialized_fields_v1",
            "capture_available": True,
            "serialized_fields_complete": True,
            "source_copy_equal": True,
            "serialized_fields_unchanged": True,
            "source_owner_verified": True,
            "action_owner_verified": True,
            "term_count": 1,
            "selected_term_count": 1,
            "unsupported_term_count": 0,
            "selected_index_complete": True,
            "authority_bound": False,
        }
    return event


def _selection(source: str) -> dict[str, object]:
    return {
        "action_id": "transfer_trade_power",
        "war_id": WAR_ID,
        "direction": "demand",
        "amount_raw": -1,
        "province_ids": [],
        "beneficiary": None,
        "source": source,
        "trade_power_beneficiary": "FRA",
        "term_mask": "t",
        "_sources_protocol": True,
    }


class PeaceTradePowerSourceTests(unittest.TestCase):
    def test_normalizer_accepts_third_country_source_but_not_beneficiary(self):
        parameters = normalize_peace_execution_parameters(
            "transfer_trade_power", "FRA", "ENG", "initiate", {
                "peace_context": {
                    "war_id": WAR_ID,
                    "direction": "demand",
                    "terms": [{
                        "action_id": "transfer_trade_power",
                        "source": "UTR",
                        "beneficiary": "FRA",
                    }],
                },
            })
        self.assertEqual("UTR", parameters["peace_context"]["terms"][0]["source"])
        with self.assertRaisesRegex(
                ValueError, "PEACE_EXECUTION_TRADE_POWER_PARTIES_INVALID"):
            normalize_peace_execution_parameters(
                "transfer_trade_power", "FRA", "ENG", "initiate", {
                    "peace_context": {
                        "war_id": WAR_ID,
                        "direction": "demand",
                        "terms": [{
                            "action_id": "transfer_trade_power",
                            "source": "FRA",
                            "beneficiary": "FRA",
                        }],
                    },
                })

    def test_query10_selected_source_validates_and_projects_candidates(self):
        rows = [
            {"source": "UTR", "beneficiary": "FRA", "selected": True,
             "complete": True},
            {"source": "SWE", "beneficiary": "FRA", "selected": False,
             "complete": True},
        ]
        event = _common_event(
            source="UTR", selection_requested=True, matching=1,
            selected=True, matched=True, candidates=rows)
        selection = _selection("UTR")
        self.assertTrue(ObserverSession._valid_native_peace_trade_power_offer_inspection(
            event, "transfer_trade_power", "FRA", "ENG", "initiate",
            DATE_RAW, selection, "source-query", "source-session"))
        projected = ObserverSession._semantic_peace_trade_power_offer_inspection(event)
        self.assertEqual("UTR", projected["native_trade_power"]["source"])
        self.assertEqual(rows, projected["native_trade_power"]["candidates"])
        self.assertEqual("UTR", projected["peace_context"]["terms"][0]["source"])
        execution = DiplomacyTools._apply_peace_execution_inspection(
            {"interface_support": {}, "session": {"date_raw": DATE_RAW},
             "acceptance": {}, "costs": {}}, projected, {
                 "peace_context": {
                     "war_id": WAR_ID, "direction": "demand",
                     "terms": [{"action_id": "transfer_trade_power",
                                "source": "UTR", "beneficiary": "FRA"}],
                 },
             })
        self.assertEqual(rows, execution["parameters"]["candidates"]["candidates"])
        self.assertEqual("UTR", execution["parameters"]["actual"]
                         ["peace_context"]["terms"][0]["source"])

    def test_query10_candidate_discovery_is_unknown_and_not_selected(self):
        rows = [{"source": "UTR", "beneficiary": "FRA", "selected": False,
                 "complete": True}]
        event = _common_event(
            source=None, selection_requested=False, matching=0,
            selected=False, matched=False, candidates=rows)
        selection = _selection("-")
        selection["_sources_protocol"] = True
        self.assertTrue(ObserverSession._valid_native_peace_trade_power_offer_inspection(
            event, "transfer_trade_power", "FRA", "ENG", "initiate",
            DATE_RAW, selection, "source-query", "source-session"))
        projected = ObserverSession._semantic_peace_trade_power_offer_inspection(event)
        self.assertEqual([], projected["peace_context"]["terms"])
        self.assertFalse(projected["native_trade_power"]["selection_requested"])
        execution = DiplomacyTools._apply_peace_execution_inspection(
            {"interface_support": {}, "session": {"date_raw": DATE_RAW},
             "acceptance": {}, "costs": {}}, projected, {
                 "peace_context": {
                     "war_id": WAR_ID, "direction": "demand", "terms": [],
                 },
             })
        self.assertEqual("unknown", execution["legality"]["status"])
        self.assertEqual(rows, execution["parameters"]["candidates"]["candidates"])
        self.assertIsNone(execution["parameters"]["actual"])

    def test_source_ack_selects_query10_and_exec4_wire(self):
        session = object.__new__(ObserverSession)
        session.installation_capabilities = lambda: frozenset({
            "native_peace_trade_power_query",
            "native_peace_trade_power_execution",
            "native_peace_trade_power_sources",
        })
        captured: dict[str, object] = {}
        session.inspect_alliance = lambda *args, **kwargs: captured.update(
            {"args": args, "kwargs": kwargs}) or {"ok": True}
        result = session.inspect_peace_trade_power_offer(
            "transfer_trade_power", "FRA", "ENG", "initiate", _selection("UTR"))
        self.assertEqual({"ok": True}, result)
        self.assertTrue(captured["kwargs"]["peace_trade_power_offer"]
                        ["_sources_protocol"])

        with tempfile.TemporaryDirectory() as directory:
            session = object.__new__(ObserverSession)
            session.directory = Path(directory)
            (session.directory / "control-probe.jsonl").write_text("", encoding="ascii")
            session.record = {"creation_filetime": 123}
            session.session_id = "source-session"
            session.installation_capabilities = lambda: frozenset({
                "native_peace_trade_power_query",
                "native_peace_trade_power_execution",
                "native_peace_trade_power_sources",
            })
            wire: dict[str, str] = {}
            def publish(value: str, *_args: object) -> str:
                wire["value"] = value
                return "published"
            session._publish_atomic_request = publish
            result = session.submit_peace(
                "source-request", "FRA", "ENG", "initiate", DATE_RAW,
                "transfer_trade_power", {
                    "peace_context": {
                        "war_id": WAR_ID,
                        "direction": "demand",
                        "terms": [{"action_id": "transfer_trade_power",
                                   "source": "UTR", "beneficiary": "FRA"}],
                    },
                }, timeout=0)
            self.assertTrue(wire["value"].startswith("EU4PEACE_EXEC4 "))
            self.assertTrue(wire["value"].rstrip().endswith(" t UTR"))
            self.assertEqual("NATIVE_PEACE_SUBMISSION_TIMEOUT", result["reason_code"])

    def test_public_inspection_keeps_empty_t_discovery_out_of_white_peace(self):
        class Session:
            def installation_capabilities(self):
                return frozenset({
                    "native_peace_trade_power_query",
                    "native_peace_trade_power_sources",
                })

            def health(self):
                return {"status": "ready", "date_raw": DATE_RAW,
                        "state_id": "source-state", "complete": True}

            def inspect_peace_trade_power_offer(self, *args):
                self.selection = args[-1]
                return {"error_code": "QUERY_OBSERVATION_TIMEOUT"}

        tools = DiplomacyTools(None, Session())
        result = tools.inspect_diplomatic_action(
            "transfer_trade_power", "FRA", "ENG", "initiate", {
                "peace_context": {
                    "war_id": WAR_ID, "direction": "demand", "terms": [],
                },
            })
        self.assertEqual("unknown", result["legality"]["status"])
        self.assertEqual([], result["parameters"]["requested"]
                         ["peace_context"]["terms"])
        self.assertEqual("QUERY_OBSERVATION_TIMEOUT",
                         result["legality"]["reasons"][0]["code"])
        self.assertEqual("-", tools.session.selection["source"])
        self.assertEqual("t", tools.session.selection["term_mask"])


if __name__ == "__main__":
    unittest.main()
