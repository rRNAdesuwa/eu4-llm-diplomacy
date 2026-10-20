from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_catalog import ACTIONS
from bridge.peace_execution import normalize_peace_execution_parameters
from work import run_peace_inbound_response as inbound_runner


WAR_ID = "war_0123456789abcdef_01234567"
REAL_QUERY_FIXTURE = Path(__file__).parent / "fixtures" / (
    "peace_annul_r53_real_queries.json")
REAL_INBOUND_INSPECTION_FIXTURE = Path(__file__).parent / "fixtures" / (
    "peace_annul_r53_real_inbound_inspection.json")
REAL_INBOUND_RESULTS_FIXTURE = Path(__file__).parent / "fixtures" / (
    "peace_annul_r53_real_inbound_results.json")


def _term(action_id: str) -> dict[str, object]:
    if action_id == "demand_ducats":
        return {"action_id": action_id, "amount": "10.0",
                "payer": "ENG", "claimant": "FRA"}
    if action_id == "cede_province":
        return {"action_id": action_id, "province_ids": [177],
                "beneficiary": "FRA"}
    if action_id == "war_reparations":
        return {"action_id": action_id, "payer": "ENG", "claimant": "FRA"}
    if action_id == "transfer_trade_power":
        return {"action_id": action_id, "source": "ENG",
                "beneficiary": "FRA"}
    if action_id == "concede_defeat":
        return {"action_id": action_id, "conceding_country": "ENG",
                "beneficiary": "FRA"}
    return {"action_id": "annul_treaties", "country": "POR",
            "treaty_partners": ["ENG", "SPA"]}


def _real_query_parameters(event: dict[str, object]) -> dict[str, object]:
    """Rebuild the public request from one captured QUERY12 selection."""

    terms: list[dict[str, object]] = []
    mask = event["term_mask"]
    money = event.get("native_money")
    if "m" in mask:
        assert isinstance(money, dict)
        amount_raw = money["requested_amount_raw"]
        assert isinstance(amount_raw, int)
        terms.append({
            "action_id": "demand_ducats",
            "amount": f"{amount_raw // 1000}.{(amount_raw % 1000) // 100}",
            "payer": money["payer"],
            "claimant": money["claimant"],
        })
    concede = event.get("native_concede_defeat")
    if "c" in mask:
        assert isinstance(concede, dict)
        terms.append({
            "action_id": "concede_defeat",
            "conceding_country": concede["conceding_country"],
            "beneficiary": concede["beneficiary"],
        })
    annul = event.get("native_annul_treaties")
    if "a" in mask and isinstance(annul, dict) \
            and annul.get("selection_requested") is True:
        terms.append({
            "action_id": "annul_treaties",
            "country": annul["country"],
            "treaty_partners": list(annul["treaty_partners"]),
        })
    raw = {"peace_context": {
        "war_id": event["war_id"],
        "direction": event["direction"],
        "terms": terms,
    }}
    return normalize_peace_execution_parameters(
        event["action_id"], event["actor"], event["recipient"],
        event["phase"], raw)


def _empty_execution_inspection() -> dict[str, object]:
    return {
        "interface_support": {},
        "session": {},
        "acceptance": {},
        "costs": {},
    }


class PeaceAnnulTreatiesTests(unittest.TestCase):
    def _parameters(self, terms: list[dict[str, object]],
                    action_id: str = "annul_treaties") -> dict[str, object]:
        return {"peace_context": {
            "war_id": WAR_ID, "direction": "demand", "terms": terms,
        }}

    def test_selected_a_is_canonical_and_has_no_direction_role(self):
        terms = [_term(action_id) for action_id in (
            "annul_treaties", "concede_defeat", "transfer_trade_power",
            "war_reparations", "cede_province", "demand_ducats")]
        normalized = normalize_peace_execution_parameters(
            "annul_treaties", "FRA", "ENG", "initiate",
            self._parameters(terms))
        self.assertEqual(
            ["demand_ducats", "cede_province", "war_reparations",
             "transfer_trade_power", "concede_defeat", "annul_treaties"],
            [term["action_id"]
             for term in normalized["peace_context"]["terms"]])
        fields = ObserverSession._peace_execution_fields(normalized)
        self.assertIsNotNone(fields)
        assert fields is not None
        self.assertEqual("POR", fields[-3])
        self.assertEqual(["ENG", "SPA"], fields[-2])
        self.assertEqual("mprtca", fields[-1])

    def test_a_discovery_is_empty_selection_and_not_executable_term(self):
        normalized = normalize_peace_execution_parameters(
            "annul_treaties", "FRA", "ENG", "initiate",
            self._parameters([]))
        self.assertEqual([], normalized["peace_context"]["terms"])
        fields = ObserverSession._peace_execution_fields(normalized)
        self.assertIsNotNone(fields)
        assert fields is not None
        self.assertEqual((None, None, ""), fields[-3:])

    def test_a_shape_rejects_self_duplicate_or_unsorted_partners(self):
        for partners, code in (
                (["POR", "POR"], "PEACE_EXECUTION_ANNUL_PARTNERS_INVALID"),
                (["POR", "ENG"], "PEACE_EXECUTION_ANNUL_PARTNERS_INVALID"),
                (["SPA", "ENG"], "PEACE_EXECUTION_ANNUL_PARTNERS_INVALID")):
            with self.subTest(partners=partners):
                with self.assertRaisesRegex(ValueError, code):
                    normalize_peace_execution_parameters(
                        "annul_treaties", "FRA", "ENG", "initiate",
                        self._parameters([{
                            "action_id": "annul_treaties", "country": "POR",
                            "treaty_partners": partners,
                        }]))

    def test_query12_selection_binds_country_and_partner_csv(self):
        session = object.__new__(ObserverSession)
        session.installation_capabilities = lambda: frozenset({
            "native_peace_annul_treaties_query",
        })
        captured: dict[str, object] = {}
        session.inspect_alliance = lambda *args, **kwargs: captured.update(
            {"args": args, "kwargs": kwargs}) or {"ok": True}
        result = session.inspect_peace_annul_treaties_offer(
            "annul_treaties", "FRA", "ENG", "initiate", {
                "action_id": "annul_treaties", "war_id": WAR_ID,
                "direction": "demand", "amount_raw": -1,
                "province_ids": [], "beneficiary": None, "source": "-",
                "trade_power_beneficiary": None, "payer": None,
                "claimant": None, "conceding_country": None,
                "concede_beneficiary": None, "annul_country": "POR",
                "annul_partners": ["ENG", "SPA"], "term_mask": "a",
            })
        self.assertEqual({"ok": True}, result)
        selection = captured["kwargs"]["peace_annul_treaties_offer"]
        self.assertEqual("POR", selection["annul_country"])
        self.assertEqual(["ENG", "SPA"], selection["annul_partners"])
        self.assertEqual("native_peace_annul_treaties_offer_inspection",
                         captured["kwargs"]["inspection_event"])

    def test_catalog_exposes_a_fields_and_eighteen_term_order(self):
        description = ACTIONS["annul_treaties"].describe()
        definitions = description["parameter_definitions"]
        terms = definitions["peace_context.terms"]
        self.assertEqual(0, terms["min_length"])
        self.assertEqual(18, terms["max_length"])
        self.assertEqual(
            ["demand_ducats", "cede_province", "war_reparations",
             "transfer_trade_power", "concede_defeat", "annul_treaties",
             "humiliate_rival", "show_strength", "force_religion",
             "return_core", "revoke_core", "release_subject",
             "transfer_subject", "release_nation", "force_vassalization",
             "form_personal_union", "grant_independence", "full_annexation"],
            terms["canonical_order"])
        self.assertEqual("country", ACTIONS["annul_treaties"].parameters[1])
        self.assertEqual("treaty_partners", ACTIONS["annul_treaties"].parameters[2])
        self.assertEqual(
            "peace_context.terms[0].treaty_partners",
            definitions["peace_context.terms[0].treaty_partners"]["path"])

    def test_a_effect_rows_validate_without_guessing_duration_or_penalty(self):
        effect = {
            "country": "POR", "partner": "ENG",
            "present_before": False, "present_after": True,
            "start_date_raw": 56500000, "end_date_raw": 43808760,
            "alliance_before": True, "alliance_after": False,
            "values_readable": True, "verified": True,
        }
        effects = {
            "complete": True, "date_unchanged": True,
            "currency_scale": 1000, "money": None, "provinces": [],
            "annul_treaties": [effect],
        }
        self.assertTrue(ObserverSession._valid_native_peace_effects(
            effects, "demand", -1, [], None, "FRA", "ENG", 56545080, True,
            annul_country="POR", annul_partners=["ENG"],
            annul_treaties_requested=True))
        rejected = {**effects, "annul_treaties": [{
            **effect, "present_after": True, "verified": False,
        }]}
        self.assertTrue(ObserverSession._valid_native_peace_effects(
            rejected, "demand", -1, [], None, "FRA", "ENG", 56545080, False,
            annul_country="POR", annul_partners=["ENG"],
            annul_treaties_requested=True))

    def test_a_plus_money_requires_complete_and_unforged_money_effect(self):
        terms = [
            {"action_id": "demand_ducats", "amount": "1.0",
             "payer": "FRA", "claimant": "ENG"},
            {"action_id": "annul_treaties", "country": "FRA",
             "treaty_partners": ["GEN", "PAP"]},
        ]
        response = {
            "action_id": "peace_offer",
            "family": "peace",
            "actor": "ENG",
            "recipient": "FRA",
            "phase": "accept",
            "war_before": True,
            "war_after": False,
            "native_outcome": "accepted",
            "terms_verified": True,
            "date_raw": 56549088,
            "peace_context": {
                "war_id": WAR_ID,
                "direction": "demand",
                "original_actor": "ENG",
                "original_recipient": "FRA",
                "complete": True,
                "selected_terms_complete": True,
                "terms": terms,
            },
            "effects": {
                "complete": True,
                "date_unchanged": True,
                "currency_scale": 1000,
                "money": {
                    "amount_raw": 1000,
                    "payer": "FRA",
                    "paid_raw": 1000,
                    "credits": [{"country": "ENG", "amount_raw": 1000}],
                    "verified": True,
                },
                "provinces": [],
                "war_reparations": None,
                "transfer_trade_power": None,
                "concede_defeat": None,
                "annul_treaties": [
                    {
                        "country": "FRA", "partner": "GEN",
                        "present_before": True, "present_after": True,
                        "start_date_raw": 56549088,
                        "end_date_raw": 43808760,
                        "alliance_before": True, "alliance_after": False,
                        "values_readable": True, "verified": True,
                    },
                    {
                        "country": "FRA", "partner": "PAP",
                        "present_before": True, "present_after": True,
                        "start_date_raw": 56549088,
                        "end_date_raw": 43808760,
                        "alliance_before": True, "alliance_after": False,
                        "values_readable": True, "verified": True,
                    },
                ],
            },
        }
        complete = inbound_runner._public_effect_contract(
            {"result": response}, "accept")
        self.assertTrue(complete["all"], complete)
        self.assertTrue(complete["checks"]["money_province_full_effects"])

        missing_money = copy.deepcopy(response)
        missing_money["effects"]["money"] = None
        missing_contract = inbound_runner._public_effect_contract(
            {"result": missing_money}, "accept")
        self.assertFalse(missing_contract["all"])
        self.assertFalse(missing_contract["checks"][
            "money_province_full_effects"])

        forged_money = copy.deepcopy(response)
        forged_money["effects"]["money"]["credits"] = [
            {"country": "ENG", "amount_raw": 999}]
        forged_contract = inbound_runner._public_effect_contract(
            {"result": forged_money}, "accept")
        self.assertFalse(forged_contract["all"])
        self.assertFalse(forged_contract["checks"][
            "money_province_full_effects"])

    def test_r53_real_query_projects_public_legality_and_candidates(self):
        with REAL_QUERY_FIXTURE.open(encoding="utf-8") as stream:
            fixture = json.load(stream)

        expected_status = {
            "demand-annul-single": "available",
            "demand-annul-multiple": "available",
            "money-annul": "available",
            "offer-annul-single": "available",
            "offer-annul-multiple": "available",
            "concede-annul": "unavailable",
            "wrong-country-annul": "unknown",
            "demand-annul-candidates": "unknown",
            "offer-annul-candidates": "unknown",
        }
        for case in fixture["cases"]:
            event = case["event"]
            name = case["name"]
            with self.subTest(case=name):
                parameters = _real_query_parameters(event)
                projected = ObserverSession._semantic_peace_annul_treaties_offer_inspection(
                    copy.deepcopy(event))
                execution = DiplomacyTools._apply_peace_execution_inspection(
                    _empty_execution_inspection(), projected, parameters)

                self.assertEqual(expected_status[name],
                                 execution["legality"]["status"])
                self.assertEqual(
                    "native_peace_execution_inspection",
                    execution["interface_support"]["query"])
                self.assertNotIn("frame_thread", json.dumps(execution))
                candidates = execution["parameters"]["candidates"]
                self.assertIsInstance(candidates, dict)
                self.assertEqual(
                    {"candidates_available", "candidates_complete",
                     "candidates_truncated", "candidate_count",
                     "matching_candidate_count", "candidates"},
                    set(candidates))
                self.assertTrue(candidates["candidates"])
                self.assertTrue(all(
                    set(row) == {"country", "partner", "selected", "complete"}
                    for row in candidates["candidates"]))

                if expected_status[name] == "available":
                    self.assertTrue(execution["parameters"]["complete"])
                    self.assertEqual(
                        parameters, execution["parameters"]["actual"])
                    self.assertTrue(
                        execution["native_annul_treaties"]["parameters_matched"])
                elif name == "concede-annul":
                    self.assertFalse(execution["parameters"]["complete"])
                    self.assertEqual(
                        parameters, execution["parameters"]["actual"])
                    self.assertTrue(
                        execution["native_annul_treaties"]["parameters_matched"])
                    self.assertTrue(any(
                        reason["code"] ==
                        "NATIVE_PEACE_SELECTED_TERM_RULE_UNAVAILABLE"
                        for reason in execution["legality"]["reasons"]))
                else:
                    self.assertFalse(execution["parameters"]["complete"])
                    self.assertIsNone(execution["parameters"]["actual"])
                    self.assertFalse(
                        execution["native_annul_treaties"]["parameters_matched"])
                    if name.endswith("candidates"):
                        self.assertEqual([], execution["peace_context"]["terms"])
                    else:
                        self.assertEqual(
                            parameters["peace_context"]["terms"],
                            execution["peace_context"]["terms"])

    def test_public_annul_candidate_projection_keeps_256_rows(self):
        with REAL_QUERY_FIXTURE.open(encoding="utf-8") as stream:
            fixture = json.load(stream)
        discovery = next(
            case["event"] for case in fixture["cases"]
            if case["name"] == "demand-annul-candidates")
        event = copy.deepcopy(discovery)
        candidates = [
            {"country": "ENG", "partner": f"{index:03X}",
             "selected": False, "complete": True}
            for index in range(256)
        ]
        native = event["native_annul_treaties"]
        native["candidate_count"] = 256
        native["candidates_available"] = True
        native["candidates_complete"] = True
        native["candidates_truncated"] = False
        native["candidates"] = candidates
        expected_selection = {
            "action_id": "annul_treaties",
            "war_id": event["war_id"],
            "direction": event["direction"],
            "term_mask": "a",
            "amount_raw": -1,
            "province_ids": [],
            "beneficiary": None,
            "annul_country": "-",
            "annul_partners": [],
        }
        self.assertTrue(
            ObserverSession._valid_native_peace_annul_treaties_offer_inspection(
                event, "annul_treaties", event["actor"], event["recipient"],
                event["phase"], event["date_raw"], expected_selection,
                event["query_id"], event["session_id"]))
        projected = ObserverSession._semantic_peace_annul_treaties_offer_inspection(
            event)
        self.assertEqual(
            256, len(projected["native_annul_treaties"]["candidates"]))
        execution = DiplomacyTools._apply_peace_execution_inspection(
            _empty_execution_inspection(), projected,
            _real_query_parameters(event))
        self.assertEqual("unknown", execution["legality"]["status"])
        self.assertEqual(
            256, len(execution["parameters"]["candidates"]["candidates"]))

    def test_r53_d001_real_inbound_inspection_projects_annul_context(self):
        with REAL_INBOUND_INSPECTION_FIXTURE.open(encoding="utf-8") as stream:
            fixture = json.load(stream)
        event = fixture["event"]
        source = fixture["source"]
        source_path = Path(source["path"])
        self.assertTrue(source_path.exists())
        self.assertEqual(source["bytes"], source_path.stat().st_size)
        self.assertEqual(
            source["sha256"], hashlib.sha256(source_path.read_bytes()).hexdigest())
        canonical = json.dumps(event, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":"))
        self.assertEqual(
            source["event_sha256"],
            hashlib.sha256(canonical.encode("utf-8")).hexdigest())

        self.assertTrue(ObserverSession._valid_native_inbound_inspection(
            event, event["query_id"], event["session_id"], event["actor"],
            event["phase"], event["native_proposal_id"], event["date_raw"],
            "peace_offer"))
        context = event["peace_context"]
        self.assertTrue(ObserverSession._valid_inbound_peace_context(
            context, "ENG", "FRA"))
        fields = ObserverSession._inbound_peace_context_fields(
            context, "ENG", "FRA")
        self.assertIsNotNone(fields)
        assert fields is not None
        self.assertTrue(fields["annul_treaties_requested"])
        self.assertEqual("FRA", fields["annul_country"])
        self.assertEqual(["GEN", "PAP"], fields["annul_partners"])

        public = ObserverSession._public_native_inbound_inspection(
            event, event["date_raw"], "peace_offer")
        self.assertEqual("peace", public["family"])
        self.assertEqual(
            [{"action_id": "annul_treaties", "country": "FRA",
              "treaty_partners": ["GEN", "PAP"]}],
            public["peace_context"]["terms"])
        for private_key in (
                "native_proposal_id", "native_proposal_pointer", "token3c",
                "envoy30", "date28", "date2c"):
            self.assertNotIn(private_key, public)

        wrong_roles = copy.deepcopy(context)
        wrong_roles["original_actor"] = "FRA"
        self.assertFalse(ObserverSession._valid_inbound_peace_context(
            wrong_roles, "ENG", "FRA"))
        for partners in (["GEN", "GEN"], ["FRA", "PAP"]):
            invalid = copy.deepcopy(context)
            invalid["terms"][0]["treaty_partners"] = partners
            with self.subTest(partners=partners):
                self.assertFalse(ObserverSession._valid_inbound_peace_context(
                    invalid, "ENG", "FRA"))
                self.assertIsNone(ObserverSession._inbound_peace_context_fields(
                    invalid, "ENG", "FRA"))

    def test_r53_real_inbound_responses_consume_annul_effects(self):
        with REAL_INBOUND_RESULTS_FIXTURE.open(encoding="utf-8") as stream:
            fixture = json.load(stream)

        responses = {}
        for outcome, record in fixture["cases"].items():
            inspection = record["events"]["inspection"]["event"]
            response = record["events"]["response"]["event"]
            self.assertTrue(ObserverSession._valid_native_inbound_inspection(
                inspection, inspection["query_id"], inspection["session_id"],
                inspection["actor"], inspection["phase"],
                inspection["native_proposal_id"], inspection["date_raw"],
                "peace_offer"))
            public = ObserverSession._public_native_inbound_response_result(
                response, response["request_id"], response["session_id"],
                response["actor"], response["phase"], response["date_raw"],
                inspection["native_proposal_id"], "peace_offer")
            self.assertIsNotNone(public)
            assert public is not None
            responses[outcome] = (response, inspection, public)
            self.assertEqual(outcome, "accept" if public["native_outcome"]
                             == "accepted" else "reject")
            self.assertNotIn("session_id", public)
            self.assertNotIn("native_proposal_id", public)
            rows = public["effects"]["annul_treaties"]
            self.assertEqual({"GEN", "PAP"},
                             {row["partner"] for row in rows})
            if outcome == "accept":
                self.assertEqual("accepted", public["native_outcome"])
                self.assertTrue(public["terms_verified"])
                self.assertFalse(public["war_after"])
                self.assertTrue(all(row["verified"] for row in rows))
                self.assertTrue(all(row["present_after"] for row in rows))
                self.assertTrue(all(not row["alliance_after"] for row in rows))
                self.assertEqual({56549088},
                                 {row["start_date_raw"] for row in rows})
                self.assertEqual({43808760},
                                 {row["end_date_raw"] for row in rows})
            else:
                self.assertEqual("rejected", public["native_outcome"])
                self.assertFalse(public["terms_verified"])
                self.assertTrue(public["war_after"])
                self.assertTrue(all(not row["verified"] for row in rows))
                self.assertTrue(all(row["alliance_after"] for row in rows))

        accepted, inspection, _ = responses["accept"]

        forged_partner = copy.deepcopy(accepted)
        forged_partner["effects"]["annul_treaties"][0]["partner"] = "SAV"
        self.assertIsNone(ObserverSession._public_native_inbound_response_result(
            forged_partner, accepted["request_id"], accepted["session_id"],
            accepted["actor"], accepted["phase"], accepted["date_raw"],
            inspection["native_proposal_id"], "peace_offer"))

        duplicate_partner = copy.deepcopy(accepted)
        duplicate_partner["effects"]["annul_treaties"][1]["partner"] = "GEN"
        self.assertIsNone(ObserverSession._public_native_inbound_response_result(
            duplicate_partner, accepted["request_id"], accepted["session_id"],
            accepted["actor"], accepted["phase"], accepted["date_raw"],
            inspection["native_proposal_id"], "peace_offer"))

        missing_partner = copy.deepcopy(accepted)
        missing_partner["effects"]["annul_treaties"].pop()
        self.assertIsNone(ObserverSession._public_native_inbound_response_result(
            missing_partner, accepted["request_id"], accepted["session_id"],
            accepted["actor"], accepted["phase"], accepted["date_raw"],
            inspection["native_proposal_id"], "peace_offer"))

        rejected = responses["reject"][0]
        forged_rejection = copy.deepcopy(rejected)
        forged_rejection["effects"]["annul_treaties"][0]["verified"] = True
        self.assertIsNone(ObserverSession._public_native_inbound_response_result(
            forged_rejection, rejected["request_id"], rejected["session_id"],
            rejected["actor"], rejected["phase"], rejected["date_raw"],
            responses["reject"][1]["native_proposal_id"], "peace_offer"))


if __name__ == "__main__":
    unittest.main()
