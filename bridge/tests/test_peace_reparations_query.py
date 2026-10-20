from __future__ import annotations

import copy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bridge.diplomacy import ObserverSession
from bridge.peace_execution import normalize_peace_execution_parameters


WAR_ID = "war_0123456789abcdef_01234567"
ACTOR = "FRA"
RECIPIENT = "ENG"
DATE_RAW = 42
_R48E_FIXTURE = (Path(__file__).resolve().parent / "fixtures"
                 / "peace_r48e_reparations_real_events.json")


def _term(action_id: str, direction: str = "demand") -> dict[str, object]:
    payer, claimant = ((ACTOR, RECIPIENT)
                       if direction == "offer" else (RECIPIENT, ACTOR))
    if action_id == "demand_ducats":
        return {"action_id": action_id, "amount": "10.0",
                "payer": payer, "claimant": claimant}
    if action_id == "cede_province":
        return {"action_id": action_id, "province_ids": [177],
                "beneficiary": ACTOR if direction == "demand" else RECIPIENT}
    return {"action_id": "war_reparations", "payer": payer,
            "claimant": claimant}


def _parameters(mask: str, primary: str, direction: str = "demand") -> dict:
    actions = {"m": "demand_ducats", "p": "cede_province",
               "r": "war_reparations"}
    terms = [_term(actions[bit], direction) for bit in "mpr" if bit in mask]
    return normalize_peace_execution_parameters(
        primary, ACTOR, RECIPIENT, "initiate",
        {"peace_context": {"war_id": WAR_ID, "direction": direction,
                            "terms": terms}})


def _payload(mask: str) -> dict[str, object]:
    # Native selected objects include base/default terms in addition to the
    # public terms.  Keep this count deliberately different from len(terms).
    selected_count = 2 if mask == "r" else 6 if "p" in mask else 3
    return {
        "schema": "native_peace_serialized_fields_v1",
        "capture_available": True,
        "serialized_fields_complete": True,
        "source_copy_equal": True,
        "serialized_fields_unchanged": True,
        "source_owner_verified": True,
        "action_owner_verified": True,
        "term_count": selected_count,
        "selected_term_count": selected_count,
        "unsupported_term_count": 0,
        "selected_index_complete": True,
        "authority_bound": False,
    }


def _rule_term_count(mask: str) -> int:
    """Count selected nonzero public terms represented by the native rule."""

    return 1 + int("m" in mask) + int("p" in mask)


def _event_from_wire(fields: list[str]) -> dict[str, object]:
    mask = fields[13]
    direction = fields[9]
    payer, claimant = ((ACTOR, RECIPIENT)
                       if direction == "offer" else (RECIPIENT, ACTOR))
    beneficiary = fields[12]
    event: dict[str, object] = {
        "event": "native_peace_reparations_offer_inspection",
        "family": "peace",
        "session_id": "query-session",
        "query_id": fields[2],
        "action_id": fields[3],
        "actor": fields[4],
        "recipient": fields[5],
        "phase": "initiate",
        "date_raw": int(fields[6]),
        "war_id": fields[8],
        "direction": direction,
        "identity_scope": "observer_session",
        "term_mask": mask,
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
        "common_diagnostic_readable": True,
        "common_diagnostic_truncated": False,
        "send_diagnostic_hex": "",
        "send_diagnostic_readable": True,
        "send_diagnostic_truncated": False,
        "native_wrapper_gate_checked": True,
        "native_wrapper_gate": True,
        "wrapper_identity_verified": True,
        "wrapper_payload_unchanged": True,
        "full_rules_complete": True,
        "reasons_complete": False,
        "submitted": False,
        "native_money": None,
        "native_provinces": None,
        "native_payload": _payload(mask),
        "native_reparations": {
            "requested": True,
            "candidate_count": 2,
            "matching_candidate_count": 1,
            "candidate_found": True,
            "selection_requested": True,
            "selection_available": True,
            "selected": True,
            "selected_term_count": 1,
            "payer": payer,
            "claimant": claimant,
            "selection_copy_verified": True,
            "parameters_matched": True,
            "reason_code": None,
            "rule_checked": True,
            "rule_available": True,
            "rule_term_count": _rule_term_count(mask),
            "rule_scope": "selected_nonzero_terms",
            "rule_diagnostic_hex": "",
            "rule_diagnostic_readable": True,
            "rule_diagnostic_truncated": False,
        },
    }
    if "m" in mask:
        amount = int(fields[10])
        event["native_money"] = {
            "query_complete": True,
            "requested_amount_raw": amount,
            "currency_scale": 1000,
            "currency_precision_raw": 100,
            "currency_scale_verified": True,
            "ceiling_input_raw": 100000,
            "currency_ceiling_raw": 100000,
            "amount_within_limit": True,
            "setter_called": True,
            "source_amount_raw": amount,
            "action_amount_raw": amount,
            "source_readback_matches": True,
            "action_copy_verified": True,
            "parameters_matched": True,
            "direction": direction,
            "direction_verified": True,
            "payer": payer,
            "claimant": claimant,
        }
    if "p" in mask:
        event["native_provinces"] = {
            "query_complete": True,
            "candidate_enumeration_complete": True,
            "candidate_count": 1,
            "candidates": [{
                "province_id": 177,
                "beneficiary": beneficiary,
                "selected": True,
                "name_hex": "",
                "name_readable": True,
                "name_truncated": False,
                "native_selectability_checked": True,
                "native_selectable": True,
            }],
            "selection_requested": True,
            "requested_province_ids": [177],
            "requested_beneficiary": beneficiary,
            "requested_candidates_found": True,
            "toggle_called": True,
            "toggle_call_count": 1,
            "parameters_matched": True,
            "selected_province_ids": [177],
            "selected_beneficiary": beneficiary,
            "selection_copy_verified": True,
            "selected_term_records_complete": True,
            "direction": direction,
            "direction_verified": True,
            "reason_code": None,
            "selection_delta_raw": 0,
        }
    return event


class PeaceReparationsQueryTests(unittest.TestCase):
    @staticmethod
    def _r48e_fixture() -> dict[str, object]:
        with _R48E_FIXTURE.open(encoding="utf-8") as stream:
            return json.load(stream)

    @classmethod
    def _r48e_case(cls, name: str) -> dict[str, object]:
        fixture = cls._r48e_fixture()
        return next(case for case in fixture["cases"]
                    if case["name"] == name)

    @classmethod
    def _r48e_selection(cls, case: dict[str, object]) -> dict[str, object]:
        """Derive the validator input from the captured request itself."""

        request = case["request"]
        context = request["parameters"]["peace_context"]
        terms = context["terms"]
        money_term = next(term for term in terms
                          if term["action_id"] == "demand_ducats")
        province_term = next(term for term in terms
                             if term["action_id"] == "cede_province")
        reparations_term = next(term for term in terms
                                if term["action_id"] == "war_reparations")
        return {
            "action_id": request["action_id"],
            "war_id": context["war_id"],
            "direction": context["direction"],
            "amount_raw": int(Decimal(money_term["amount"]) * 1000),
            "province_ids": province_term["province_ids"],
            "beneficiary": province_term["beneficiary"],
            "payer": reparations_term["payer"],
            "claimant": reparations_term["claimant"],
            "term_mask": "mpr",
        }

    def _session(self, root: Path, caps: dict[str, bool] | None = None) -> ObserverSession:
        installation = root / "installation.json"
        installation.write_text(json.dumps({
            "experiment_id": "query8-test",
            "session_id": "query-session",
            "pid": 1,
            "creation_filetime": 7,
            "dll_sha256": "dll",
            "controlled_countries": ["FRA"],
        }), encoding="utf-8")
        ack = {"event": "diplomacy_observer_installed",
               "session_id": "query-session",
               "native_peace_reparations_query": True,
               "caps": {}}
        if caps:
            ack["caps"].update(caps)
        (root / "control-probe.jsonl").write_text(
            json.dumps(ack) + "\n", encoding="utf-8")
        session = ObserverSession(installation, root / "eu4.exe")
        session.health = lambda: {"status": "ready", "date_raw": DATE_RAW}
        return session

    def test_query8_wire_poll_and_semantic_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = self._session(root)
            request: dict[str, str] = {}

            def publish(pending: str, _request: str) -> None:
                wire = Path(pending).read_text(encoding="ascii").strip()
                request["wire"] = wire
                event = _event_from_wire(wire.split())
                with (root / "control-probe.jsonl").open(
                        "a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(event) + "\n")

            with patch("bridge.diplomacy.os.link", side_effect=publish), \
                    patch("bridge.diplomacy.probe_identity",
                          return_value={"session_id": "query-session"}):
                result = session.inspect_peace_reparations_offer(
                    "war_reparations", ACTOR, RECIPIENT, "initiate", {
                        "action_id": "war_reparations",
                        "war_id": WAR_ID,
                        "direction": "demand",
                        "amount_raw": -1,
                        "province_ids": [],
                        "beneficiary": None,
                        "payer": RECIPIENT,
                        "claimant": ACTOR,
                        "term_mask": "r",
                    })
            wire_fields = request["wire"].split()
            self.assertEqual("EU4DIP_QUERY8", wire_fields[0])
            self.assertEqual("war_reparations", wire_fields[3])
            self.assertEqual(["-1", "-", "-", "r"], wire_fields[-4:])
            self.assertEqual("native_peace_reparations_offer_inspection",
                             result["event"])

    def test_execution_routes_every_reparations_mask_before_legacy_logic(self):
        cases = {
            "r": "war_reparations",
            "mr": "demand_ducats",
            "pr": "cede_province",
            "mpr": "cede_province",
        }
        with tempfile.TemporaryDirectory() as directory:
            session = self._session(Path(directory))
            for mask, primary in cases.items():
                with self.subTest(mask=mask):
                    parameters = _parameters(mask, primary)
                    with patch.object(
                            session, "inspect_peace_reparations_offer",
                            return_value={"event": "routed"}) as routed:
                        result = session.inspect_peace_execution(
                            primary, ACTOR, RECIPIENT, "initiate", parameters)
                    self.assertEqual({"event": "routed"}, result)
                    selection = routed.call_args.args[-1]
                    self.assertEqual(mask, selection["term_mask"])
                    self.assertEqual(primary, selection["action_id"])

    def test_validator_accepts_native_selected_count_without_public_term_count(self):
        wire = (
            "EU4DIP_QUERY8 7 query cede_province FRA ENG 42 9 "
            f"{WAR_ID} demand 10000 177 FRA mpr")
        event = _event_from_wire(wire.split())
        selection = {
            "action_id": "cede_province", "war_id": WAR_ID,
            "direction": "demand", "amount_raw": 10000,
            "province_ids": [177], "beneficiary": ACTOR,
            "payer": RECIPIENT, "claimant": ACTOR, "term_mask": "mpr",
        }
        self.assertTrue(ObserverSession._valid_native_peace_reparations_offer_inspection(
            event, "cede_province", ACTOR, RECIPIENT, "initiate", DATE_RAW,
            selection, "query", "query-session"))
        self.assertEqual(6, event["native_payload"]["selected_term_count"])
        self.assertEqual(3, event["native_reparations"]["rule_term_count"])
        self.assertEqual("selected_nonzero_terms",
                         event["native_reparations"]["rule_scope"])
        event["native_reparations"]["rule_available"] = False
        event["native_reparations"]["reason_code"] = (
            "NATIVE_PEACE_SELECTED_TERM_RULE_UNAVAILABLE")
        event["native_reparations"]["rule_diagnostic_hex"] = "6e6f"
        self.assertTrue(ObserverSession._valid_native_peace_reparations_offer_inspection(
            event, "cede_province", ACTOR, RECIPIENT, "initiate", DATE_RAW,
            selection, "query", "query-session"))
        missing_rule = copy.deepcopy(event)
        for field in ("rule_checked", "rule_available", "rule_term_count",
                      "rule_scope", "rule_diagnostic_hex",
                      "rule_diagnostic_readable", "rule_diagnostic_truncated"):
            missing_rule["native_reparations"].pop(field)
        self.assertFalse(ObserverSession._valid_native_peace_reparations_offer_inspection(
            missing_rule, "cede_province", ACTOR, RECIPIENT, "initiate", DATE_RAW,
            selection, "query", "query-session"))

        for field, value in (("rule_term_count", 4),
                             ("rule_scope", "selected_terms")):
            malformed_rule = copy.deepcopy(event)
            malformed_rule["native_reparations"][field] = value
            self.assertFalse(
                ObserverSession._valid_native_peace_reparations_offer_inspection(
                    malformed_rule, "cede_province", ACTOR, RECIPIENT,
                    "initiate", DATE_RAW, selection, "query", "query-session"),
                msg=f"malformed {field} should fail validation")

    def test_rule_term_count_and_scope_cover_all_query8_masks(self):
        cases = (
            ("r", "war_reparations", "-1", "-", "-", 1),
            ("mr", "demand_ducats", "10000", "-", "-", 2),
            ("pr", "cede_province", "-1", "177", ACTOR, 2),
            ("mpr", "cede_province", "10000", "177", ACTOR, 3),
        )
        for mask, primary, amount, province, beneficiary, expected_count in cases:
            with self.subTest(mask=mask):
                wire = (
                    "EU4DIP_QUERY8 7 query " + primary + " FRA ENG 42 9 "
                    f"{WAR_ID} demand {amount} {province} {beneficiary} {mask}")
                event = _event_from_wire(wire.split())
                native = event["native_reparations"]
                self.assertEqual(expected_count, native["rule_term_count"])
                self.assertEqual("selected_nonzero_terms", native["rule_scope"])

    def test_r48e_positive_query_replays_roles_and_selected_seven(self):
        case = self._r48e_case("positive_mpr_selected7")
        event = case["event"]
        request = case["request"]
        expected = self._r48e_selection(case)
        native = event["native_reparations"]

        self.assertEqual("native_peace_reparations_offer_inspection",
                         event["event"])
        self.assertEqual("offer", expected["direction"])
        self.assertEqual("FRA", native["payer"])
        self.assertEqual("ENG", native["claimant"])
        self.assertEqual(7, event["native_payload"]["selected_term_count"])
        self.assertEqual(7, native["rule_term_count"])
        self.assertEqual("selected_nonzero_terms", native["rule_scope"])
        self.assertTrue(
            ObserverSession._valid_native_peace_reparations_offer_inspection(
                event, request["action_id"], request["actor"],
                request["recipient"], "initiate", event["date_raw"],
                expected, event["query_id"], event["session_id"]))

    def test_r48e_payer_mismatch_is_rejected(self):
        case = self._r48e_case("positive_mpr_selected7")
        event = copy.deepcopy(case["event"])
        request = case["request"]
        expected = self._r48e_selection(case)
        event["native_reparations"]["payer"] = "ENG"

        self.assertFalse(
            ObserverSession._valid_native_peace_reparations_offer_inspection(
                event, request["action_id"], request["actor"],
                request["recipient"], "initiate", event["date_raw"],
                expected, event["query_id"], event["session_id"]))

    def test_r48e_overcap_rule_unavailable_replays_without_evaluator(self):
        case = self._r48e_case("overcap_rule_unavailable")
        event = case["event"]
        request = case["request"]
        expected = self._r48e_selection(case)
        native = event["native_reparations"]
        reason = case["public_reason"]

        self.assertEqual(16, len(expected["province_ids"]))
        self.assertEqual(18, event["native_payload"]["selected_term_count"])
        self.assertEqual(18, native["rule_term_count"])
        self.assertEqual("selected_nonzero_terms", native["rule_scope"])
        self.assertTrue(native["rule_checked"])
        self.assertFalse(native["rule_available"])
        self.assertEqual(
            "NATIVE_PEACE_SELECTED_TERM_RULE_UNAVAILABLE",
            native["reason_code"])
        self.assertFalse(event["native_evaluation"]["called"])
        self.assertEqual(reason["code"], native["reason_code"])
        self.assertIn("不能提供超过100%战争分数价值的条件", reason["text"])
        self.assertTrue(
            ObserverSession._valid_native_peace_reparations_offer_inspection(
                event, request["action_id"], request["actor"],
                request["recipient"], "initiate", event["date_raw"],
                expected, event["query_id"], event["session_id"]))

    def test_r48e_cannot_core_rule_unavailable_replays_as_negative(self):
        case = self._r48e_case("cannot_core_rule_unavailable")
        event = case["event"]
        request = case["request"]
        expected = self._r48e_selection(case)
        native = event["native_reparations"]
        reason = case["public_reason"]

        self.assertEqual(7, len(expected["province_ids"]))
        self.assertFalse(native["rule_available"])
        self.assertEqual(9, native["rule_term_count"])
        self.assertFalse(event["native_evaluation"]["called"])
        self.assertEqual(reason["code"], native["reason_code"])
        self.assertIn("不能选择这个省份，因为英格兰无法将其核心化", reason["text"])
        self.assertTrue(
            ObserverSession._valid_native_peace_reparations_offer_inspection(
                event, request["action_id"], request["actor"],
                request["recipient"], "initiate", event["date_raw"],
                expected, event["query_id"], event["session_id"]))

    def test_r48e_submission_and_execution_replay_public_effects(self):
        fixture = self._r48e_fixture()
        submission = next(case["event"] for case in fixture["cases"]
                          if case["name"] == "submission")
        execution = next(case["event"] for case in fixture["cases"]
                         if case["name"] == "execution")

        self.assertTrue(submission["submitted"])
        self.assertTrue(submission["transport_verified"])
        self.assertTrue(submission["request_binding_verified"])
        self.assertEqual("FRA", submission["reparations_payer"])
        self.assertEqual("ENG", submission["reparations_claimant"])
        self.assertEqual(2, execution["native_state"])
        self.assertEqual("accepted", execution["outcome"])
        self.assertTrue(execution["execution_verified"])
        self.assertTrue(execution["terms_verified"])
        self.assertTrue(execution["war_before"])
        self.assertFalse(execution["war_after"])

        effects = execution["effects"]
        self.assertTrue(effects["complete"])
        self.assertEqual(1000, effects["money"]["paid_raw"])
        self.assertEqual("FRA", effects["money"]["payer"])
        self.assertEqual(5, len(effects["provinces"]))
        self.assertEqual("FRA", effects["provinces"][0]["owner_before"])
        self.assertEqual("ENG", effects["provinces"][0]["owner_after"])
        self.assertEqual("ENG", effects["provinces"][4]["controller_before"])
        reparations = effects["war_reparations"]
        self.assertTrue(reparations["active_after"])
        self.assertEqual("FRA", reparations["payer"])
        self.assertEqual("ENG", reparations["claimant"])
        self.assertEqual(87600,
                         reparations["end_date_raw"]
                         - reparations["start_date_raw"])


if __name__ == "__main__":
    unittest.main()
