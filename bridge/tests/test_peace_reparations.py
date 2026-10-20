from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_catalog import ACTIONS
from bridge.peace_execution import normalize_peace_execution_parameters
from work.run_peace_outbound_execution import (
    PeaceExecutionError,
    _build_parameters,
)


WAR_ID = "war_0123456789abcdef_01234567"
ACTOR = "FRA"
RECIPIENT = "ENG"
DATE_RAW = 42
_ACTION_TO_MASK = {
    "demand_ducats": "m",
    "cede_province": "p",
    "war_reparations": "r",
}


def _rule_term_count(mask: str) -> int:
    """Count selected nonzero public terms represented by the native rule."""

    return 1 + int("m" in mask) + int("p" in mask)


def _reparations_term(direction: str = "demand") -> dict[str, str]:
    payer, claimant = ((ACTOR, RECIPIENT)
                       if direction == "offer" else (RECIPIENT, ACTOR))
    return {
        "action_id": "war_reparations",
        "payer": payer,
        "claimant": claimant,
    }


def _money_term(direction: str = "demand") -> dict[str, str]:
    payer, claimant = ((ACTOR, RECIPIENT)
                       if direction == "offer" else (RECIPIENT, ACTOR))
    return {
        "action_id": "demand_ducats",
        "amount": "10.0",
        "payer": payer,
        "claimant": claimant,
    }


def _province_term(direction: str = "demand") -> dict[str, object]:
    return {
        "action_id": "cede_province",
        "province_ids": [177],
        "beneficiary": ACTOR if direction == "demand" else RECIPIENT,
    }


def _parameters_for_mask(mask: str, direction: str = "demand",
                         primary: str | None = None) -> dict[str, object]:
    terms: list[dict[str, object]] = []
    if "m" in mask:
        terms.append(_money_term(direction))
    if "p" in mask:
        terms.append(_province_term(direction))
    if "r" in mask:
        terms.append(_reparations_term(direction))
    if primary is None:
        primary = {
            "r": "war_reparations",
            "mr": "demand_ducats",
            "pr": "cede_province",
            "mpr": "cede_province",
        }[mask]
    return normalize_peace_execution_parameters(
        primary, ACTOR, RECIPIENT, "initiate",
        {"peace_context": {
            "war_id": WAR_ID,
            "direction": direction,
            "terms": terms,
        }})


def _runner_parameters_for_mask(mask: str, direction: str = "demand",
                                primary: str | None = None) -> dict[str, object]:
    """Use the runner's public builder for its supported primary forms."""

    primary = primary or {
        "r": "war_reparations",
        "mr": "demand_ducats",
        "pr": "cede_province",
        "mpr": "cede_province",
    }[mask]
    if primary == "war_reparations":
        return _build_parameters(
            primary, WAR_ID, "10.0", None, None, direction,
            province_ids=[177] if "p" in mask else None,
            with_money="1.0" if "m" in mask else None)
    if primary == "demand_ducats":
        return _build_parameters(
            primary, WAR_ID, "10.0", None, None, direction,
            with_reparations=True)
    return _build_parameters(
        primary, WAR_ID, "10.0", 177, None, direction,
        with_money="1.0" if "m" in mask else None,
        with_reparations=True)


def _query8_event(mask: str, direction: str = "demand",
                  primary: str = "war_reparations") -> dict[str, object]:
    payer, claimant = ((ACTOR, RECIPIENT)
                       if direction == "offer" else (RECIPIENT, ACTOR))
    event: dict[str, object] = {
        "event": "native_peace_reparations_offer_inspection",
        "family": "peace",
        "session_id": "session-reparations",
        "query_id": "query-reparations",
        "action_id": primary,
        "actor": ACTOR,
        "recipient": RECIPIENT,
        "phase": "initiate",
        "date_raw": DATE_RAW,
        "war_id": WAR_ID,
        "direction": direction,
        "identity_scope": "observer_session",
        "term_mask": mask,
        "native_reparations": {
            "requested": True,
            "candidate_count": 1,
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
        event["native_money"] = {
            "query_complete": True,
            "requested_amount_raw": 10000,
            "parameters_matched": True,
            "direction": direction,
            "direction_verified": True,
            "payer": payer,
            "claimant": claimant,
        }
    if "p" in mask:
        event["native_provinces"] = {
            "query_complete": True,
            "requested_province_ids": [177],
            "requested_beneficiary": ACTOR if direction == "demand" else RECIPIENT,
            "requested_candidates_found": True,
            "selected_province_ids": [177],
            "selected_beneficiary": ACTOR if direction == "demand" else RECIPIENT,
            "parameters_matched": True,
            "direction": direction,
            "direction_verified": True,
        }
    return event


class PeaceReparationsContractTests(unittest.TestCase):
    @staticmethod
    def _installation(root: Path, *, query: bool = False,
                      execution: bool = False,
                      caps: object | None = None) -> Path:
        session_id = "peace-reparations-session"
        installation = root / "installation.json"
        installation.write_text(json.dumps({
            "experiment_id": "peace-reparations-contract",
            "session_id": session_id,
            "pid": 1,
            "creation_filetime": 116444736000000000,
            "dll_sha256": "dll",
        }), encoding="utf-8")
        ack: dict[str, object] = {
            "event": "diplomacy_observer_installed",
            "session_id": session_id,
            "native_peace_reparations_query": query,
            "native_peace_reparations_execution": execution,
        }
        if caps is not None:
            ack["caps"] = caps
        (root / "control-probe.jsonl").write_text(
            json.dumps(ack) + "\n", encoding="utf-8")
        return installation

    @staticmethod
    def _execution_native(event: dict[str, object]) -> dict[str, object]:
        native = ObserverSession._semantic_peace_reparations_offer_inspection(
            event)
        native.update({
            "parameters_matched": True,
            "full_rules_complete": True,
            "validity_called": True,
            "native_validity": True,
            "common_gate_checked": True,
            "common_action_gate": True,
            "initiation_gate_checked": True,
            "initiation_gate": True,
            "native_wrapper_gate_checked": True,
            "native_wrapper_gate": True,
            "wrapper_identity_verified": True,
            "wrapper_payload_unchanged": True,
            "native_war_context": {"context_complete": True},
        })
        return native

    def test_catalog_describes_reparations_term_and_directional_roles(self):
        description = ACTIONS["war_reparations"].describe()
        definitions = description["parameter_definitions"]
        terms = definitions["peace_context.terms"]

        self.assertEqual("array", terms["type"])
        self.assertEqual(1, terms["min_length"])
        self.assertEqual(18, terms["max_length"])
        self.assertEqual(
            ["demand_ducats", "cede_province", "war_reparations",
             "transfer_trade_power", "concede_defeat", "annul_treaties",
             "humiliate_rival", "show_strength", "force_religion",
             "return_core", "revoke_core", "release_subject",
             "transfer_subject", "release_nation", "force_vassalization",
             "form_personal_union", "grant_independence", "full_annexation"],
            terms["allowed_action_ids"])
        self.assertEqual(
            terms["allowed_action_ids"], terms["canonical_order"])
        self.assertEqual("war_reparations", terms["primary_action_id"])
        self.assertEqual(["war_reparations"], terms["required_action_ids"])
        self.assertTrue(terms["unique_action_ids"])
        self.assertEqual(
            {action_id: 1 for action_id in terms["allowed_action_ids"]},
            terms["max_occurrences_by_action_id"])

        reparations_action_id = definitions[
            "peace_context.terms[0].action_id"]
        self.assertEqual(
            "peace_context.terms[0].action_id",
            reparations_action_id["path"])
        self.assertEqual(
            terms["allowed_action_ids"],
            reparations_action_id["allowed_action_ids"])
        self.assertEqual(
            {"action_id", "payer", "claimant"},
            set(ACTIONS["war_reparations"].describe()[
                "inspection_parameter_forms"][1]["parameters"][
                    "peace_context"]["terms"][0]),
        )

        forms = {
            form["name"]: form
            for form in description["inspection_parameter_forms"]
        }
        self.assertEqual({}, forms["discovery"]["parameters"])
        for direction, form_name, payer, claimant in (
                ("demand", "selected", "<recipient>", "<actor>"),
                ("offer", "selected_offer", "<actor>", "<recipient>")):
            with self.subTest(direction=direction):
                context = forms[form_name]["parameters"]["peace_context"]
                self.assertEqual(direction, context["direction"])
                self.assertEqual(
                    [{
                        "action_id": "war_reparations",
                        "payer": payer,
                        "claimant": claimant,
                    }],
                    context["terms"])

        payer = definitions["peace_context.terms[0].payer"]
        claimant = definitions["peace_context.terms[0].claimant"]
        self.assertEqual(
            {"demand": "recipient", "offer": "actor"},
            payer["equals_by_direction"])
        self.assertEqual(
            {"demand": "actor", "offer": "recipient"},
            claimant["equals_by_direction"])

    def test_catalog_exposes_combination_masks_and_updates_legacy_term_limits(self):
        expected_actions = {
            "r": ["war_reparations"],
            "mr": ["demand_ducats", "war_reparations"],
            "pr": ["cede_province", "war_reparations"],
            "mpr": ["demand_ducats", "cede_province",
                    "war_reparations"],
        }
        for action_id in ("demand_ducats", "cede_province",
                          "war_reparations"):
            with self.subTest(action_id=action_id):
                terms = ACTIONS[action_id].describe()[
                    "parameter_definitions"]["peace_context.terms"]
                self.assertGreater(terms["max_length"], 1)
                expected_order = [
                    "demand_ducats", "cede_province", "war_reparations",
                    "transfer_trade_power", "concede_defeat", "annul_treaties",
                    "humiliate_rival", "show_strength", "force_religion",
                    "return_core", "revoke_core", "release_subject",
                    "transfer_subject", "release_nation",
                    "force_vassalization", "form_personal_union",
                    "grant_independence", "full_annexation"]
                self.assertEqual(
                    expected_order, terms["canonical_order"])

                for mask, action_ids in expected_actions.items():
                    with self.subTest(mask=mask):
                        self.assertTrue(
                            set(action_ids).issubset(
                                terms["allowed_action_ids"]))

        money = ACTIONS["demand_ducats"].describe()
        money_forms = {
            form["name"]: form
            for form in money["inspection_parameter_forms"]
        }
        self.assertEqual(
            ["demand_ducats", "war_reparations"],
            [term["action_id"] for term in money_forms[
                "selected_reparations"]["parameters"]["peace_context"][
                    "terms"]],
        )
        province = ACTIONS["cede_province"].describe()
        province_forms = {
            form["name"]: form
            for form in province["inspection_parameter_forms"]
        }
        self.assertEqual(
            ["demand_ducats", "cede_province", "war_reparations"],
            [term["action_id"] for term in province_forms[
                "selected_combined"]["parameters"]["peace_context"][
                    "terms"]],
        )

    def test_normalization_canonicalizes_all_exec2_masks_and_binds_direction(self):
        for direction in ("demand", "offer"):
            with self.subTest(direction=direction):
                for mask in ("r", "mr", "pr", "mpr"):
                    with self.subTest(mask=mask):
                        parameters = _parameters_for_mask(mask, direction)
                        terms = parameters["peace_context"]["terms"]
                        self.assertEqual(
                            mask,
                            "".join(_ACTION_TO_MASK[term["action_id"]]
                                    for term in terms))
                        reparations = next(
                            term for term in terms
                            if term["action_id"] == "war_reparations")
                        expected = ((ACTOR, RECIPIENT)
                                    if direction == "offer"
                                    else (RECIPIENT, ACTOR))
                        self.assertEqual(expected[0], reparations["payer"])
                        self.assertEqual(expected[1], reparations["claimant"])
                        self.assertEqual(
                            (WAR_ID, direction,
                             10000 if "m" in mask else -1,
                             [177] if "p" in mask else [],
                             ACTOR if "p" in mask and direction == "demand"
                             else RECIPIENT if "p" in mask else None,
                             expected[0], expected[1], None, None, None, None,
                             None, None,
                             mask),
                            ObserverSession._peace_execution_fields(parameters))
                        fields = ObserverSession._peace_execution_fields(parameters)
                        self.assertIsNotNone(fields)
                        self.assertIsNone(fields[9])
                        self.assertIsNone(fields[10])

    def test_normalization_accepts_each_selected_primary_and_rejects_missing_primary(self):
        term_by_action = {
            "demand_ducats": _money_term(),
            "cede_province": _province_term(),
            "war_reparations": _reparations_term(),
        }
        for mask in ("r", "mr", "pr", "mpr"):
            selected = [term_by_action[action] for action in (
                "demand_ducats", "cede_province", "war_reparations")
                        if _ACTION_TO_MASK[action] in mask]
            for primary in ("demand_ducats", "cede_province", "war_reparations"):
                with self.subTest(mask=mask, primary=primary):
                    raw = {"peace_context": {
                        "war_id": WAR_ID, "direction": "demand",
                        "terms": copy.deepcopy(selected)}}
                    if primary in [term["action_id"] for term in selected]:
                        normalized = normalize_peace_execution_parameters(
                            primary, ACTOR, RECIPIENT, "initiate", raw)
                        self.assertEqual(
                            [term["action_id"] for term in normalized[
                                "peace_context"]["terms"]],
                            [action for action in (
                                "demand_ducats", "cede_province",
                                "war_reparations")
                             if action in [item["action_id"] for item in selected]])
                    else:
                        with self.assertRaises(ValueError) as raised:
                            normalize_peace_execution_parameters(
                                primary, ACTOR, RECIPIENT, "initiate", raw)
                        self.assertEqual(
                            "PEACE_EXECUTION_ACTION_TERM_MISSING",
                            raised.exception.args[0])

    def test_normalization_reorders_unordered_exec2_terms_to_wire_order(self):
        for mask, primary in (
                ("r", "war_reparations"),
                ("mr", "war_reparations"),
                ("pr", "war_reparations"),
                ("mpr", "war_reparations")):
            terms = []
            if "m" in mask:
                terms.append(_money_term("offer"))
            if "p" in mask:
                terms.append(_province_term("offer"))
            if "r" in mask:
                terms.append(_reparations_term("offer"))
            raw = {"peace_context": {
                "war_id": WAR_ID,
                "direction": "offer",
                "terms": list(reversed(terms)),
            }}
            normalized = normalize_peace_execution_parameters(
                primary, ACTOR, RECIPIENT, "initiate", raw)
            self.assertEqual(
                ["demand_ducats", "cede_province", "war_reparations"]
                if mask == "mpr" else
                ["demand_ducats", "war_reparations"] if mask == "mr" else
                ["cede_province", "war_reparations"] if mask == "pr" else
                ["war_reparations"],
                [term["action_id"] for term in normalized[
                    "peace_context"]["terms"]])

    def test_normalization_rejects_duplicate_unknown_and_wrong_party_terms(self):
        base = _parameters_for_mask("r")
        duplicate = copy.deepcopy(base)
        duplicate["peace_context"]["terms"].append(_reparations_term())
        with self.assertRaises(ValueError) as raised:
            normalize_peace_execution_parameters(
                "war_reparations", ACTOR, RECIPIENT, "initiate", duplicate)
        self.assertEqual("PEACE_EXECUTION_DUPLICATE_TERM", raised.exception.args[0])

        unknown = copy.deepcopy(base)
        unknown["peace_context"]["terms"][0]["action_id"] = "unknown_term"
        with self.assertRaises(ValueError) as raised:
            normalize_peace_execution_parameters(
                "war_reparations", ACTOR, RECIPIENT, "initiate", unknown)
        self.assertEqual("PEACE_EXECUTION_TERM_UNKNOWN", raised.exception.args[0])

        wrong_party = copy.deepcopy(base)
        wrong_party["peace_context"]["terms"][0]["payer"] = ACTOR
        with self.assertRaises(ValueError) as raised:
            normalize_peace_execution_parameters(
                "war_reparations", ACTOR, RECIPIENT, "initiate", wrong_party)
        self.assertEqual(
            "PEACE_EXECUTION_REPARATIONS_PARTIES_INVALID",
            raised.exception.args[0])

    def test_runner_builder_covers_all_masks_and_primary_reparations_combinations(self):
        expected_actions = {
            "r": ["war_reparations"],
            "mr": ["demand_ducats", "war_reparations"],
            "pr": ["cede_province", "war_reparations"],
            "mpr": ["demand_ducats", "cede_province", "war_reparations"],
        }
        for direction in ("demand", "offer"):
            for mask in expected_actions:
                with self.subTest(direction=direction, mask=mask):
                    parameters = _runner_parameters_for_mask(mask, direction)
                    terms = parameters["peace_context"]["terms"]
                    self.assertEqual(
                        expected_actions[mask],
                        [term["action_id"] for term in terms])
                    reparations = terms[-1]
                    payer, claimant = ((ACTOR, RECIPIENT)
                                       if direction == "offer"
                                       else (RECIPIENT, ACTOR))
                    self.assertEqual(payer, reparations["payer"])
                    self.assertEqual(claimant, reparations["claimant"])

                if mask != "r":
                    with self.subTest(direction=direction,
                                      mask=mask, primary="war_reparations"):
                        parameters = _runner_parameters_for_mask(
                            mask, direction, primary="war_reparations")
                        self.assertEqual(
                            expected_actions[mask],
                            [term["action_id"] for term in parameters[
                                "peace_context"]["terms"]])

        with self.assertRaises(PeaceExecutionError) as raised:
            _build_parameters(
                "war_reparations", WAR_ID, "10.0", None, None,
                "demand", with_reparations=True)
        self.assertEqual("REPARATIONS_DUPLICATE_TERM", raised.exception.code)

    def test_query8_semantic_projection_preserves_native_reparations_and_order(self):
        for direction in ("demand", "offer"):
            for mask in ("r", "mr", "pr", "mpr"):
                with self.subTest(direction=direction, mask=mask):
                    primary = {
                        "r": "war_reparations",
                        "mr": "demand_ducats",
                        "pr": "cede_province",
                        "mpr": "cede_province",
                    }[mask]
                    projected = ObserverSession._semantic_peace_reparations_offer_inspection(
                        _query8_event(mask, direction, primary))
                    self.assertEqual(
                        "native_peace_reparations_offer_inspection",
                        projected["event"])
                    self.assertEqual(primary, projected["action_id"])
                    reparations = projected["native_reparations"]
                    self.assertTrue(reparations["requested"])
                    self.assertTrue(reparations["selected"])
                    self.assertTrue(reparations["parameters_matched"])
                    self.assertTrue(reparations["rule_checked"])
                    self.assertTrue(reparations["rule_available"])
                    self.assertEqual(
                        1 + int("m" in mask) + int("p" in mask),
                        reparations["rule_term_count"])
                    self.assertEqual(
                        "selected_nonzero_terms", reparations["rule_scope"])
                    self.assertEqual("", reparations["rule_diagnostic_hex"])
                    self.assertTrue(reparations["rule_diagnostic_readable"])
                    self.assertFalse(reparations["rule_diagnostic_truncated"])
                    self.assertEqual(
                        (ACTOR, RECIPIENT) if direction == "offer"
                        else (RECIPIENT, ACTOR),
                        (reparations["payer"], reparations["claimant"]))
                    self.assertNotIn("frame_thread", json.dumps(projected))
                    self.assertNotIn('"private"', json.dumps(projected))
                    self.assertEqual(
                        (["demand_ducats", "cede_province", "war_reparations"]
                         if mask == "mpr" else
                         ["demand_ducats", "war_reparations"] if mask == "mr"
                         else ["cede_province", "war_reparations"]
                         if mask == "pr" else ["war_reparations"]),
                        [term["action_id"] for term in projected[
                            "peace_context"]["terms"]]
                        )

    def test_missing_reparations_rule_gate_is_not_available(self):
        event = _query8_event("r")
        for field in (
                "rule_checked", "rule_available", "rule_term_count",
                "rule_scope", "rule_diagnostic_hex",
                "rule_diagnostic_readable", "rule_diagnostic_truncated"):
            event["native_reparations"].pop(field)
        projected = self._execution_native(event)
        reparations = projected["native_reparations"]
        self.assertFalse(reparations.get("rule_checked", False))
        self.assertFalse(reparations.get("rule_available", False))
        execution = DiplomacyTools._apply_peace_execution_inspection(
            {
                "interface_support": {},
                "session": {"date_raw": DATE_RAW},
                "acceptance": {},
                "costs": {},
            },
            projected,
            _parameters_for_mask("r"),
        )
        self.assertNotEqual("available", execution["legality"]["status"])

    def test_false_reparations_rule_gate_blocks_execution_legality(self):
        native = self._execution_native(_query8_event("r"))
        native["native_reparations"]["rule_checked"] = True
        native["native_reparations"]["rule_available"] = False
        native["native_reparations"]["reason_code"] = (
            "NATIVE_PEACE_SELECTED_TERM_RULE_UNAVAILABLE")
        projected = DiplomacyTools._apply_peace_execution_inspection(
            {
                "interface_support": {},
                "session": {"date_raw": DATE_RAW},
                "acceptance": {},
                "costs": {},
            },
            native,
            _parameters_for_mask("r"),
        )
        self.assertNotEqual("available", projected["legality"]["status"])

    def test_reparations_masks_require_the_dedicated_query_capability(self):
        for mask in ("r", "mr", "pr", "mpr"):
            parameters = _parameters_for_mask(mask)
            self.assertEqual(
                "native_peace_reparations_query",
                DiplomacyTools._peace_execution_capability_for(
                    parameters, parameters["peace_context"]["terms"][0]["action_id"]))

    def test_installation_ack_keeps_query_and_execution_capabilities_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installation = self._installation(root, query=True, execution=True)
            session = ObserverSession(installation, root / "eu4.exe")
            capabilities = session.installation_capabilities()
            self.assertIn("native_peace_reparations_query", capabilities)
            self.assertIn("native_peace_reparations_execution", capabilities)

            list_only = self._installation(
                root, caps=["native_peace_reparations_query",
                           "native_peace_reparations_execution"])
            self.assertNotIn(
                "native_peace_reparations_query",
                ObserverSession(list_only, root / "eu4.exe").installation_capabilities())

    def test_exec2_submission_extends_exec1_with_canonical_mask(self):
        cases = (
            ("r", "war_reparations"),
            ("mr", "demand_ducats"),
            ("pr", "cede_province"),
            ("mpr", "cede_province"),
        )
        for mask, action_id in cases:
            with self.subTest(mask=mask):
                parameters = _runner_parameters_for_mask(mask)
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    installation = self._installation(
                        root, query=True, execution=True)
                    session = ObserverSession(installation, root / "eu4.exe")
                    fields = ObserverSession._peace_execution_fields(parameters)
                    self.assertIsNotNone(fields)
                    (war_id, direction, amount_raw, province_ids, beneficiary,
                     _payer, _claimant, _source, _trade_beneficiary,
                     _concede_country, _concede_beneficiary,
                     _annul_country, _annul_partners, expected_mask) = fields
                    self.assertIsNone(_concede_country)
                    self.assertIsNone(_concede_beneficiary)
                    self.assertIsNone(_annul_country)
                    self.assertIsNone(_annul_partners)
                    captured: dict[str, str] = {}

                    def publish(wire: str, request_id: str,
                                request_name: str) -> str:
                        captured["wire"] = wire
                        event = {
                            "event": "native_peace_submission_result",
                            "family": "peace",
                            "session_id": session.session_id,
                            "request_id": request_id,
                            "action_id": action_id,
                            "actor": ACTOR,
                            "recipient": RECIPIENT,
                            "phase": "initiate",
                            "date_raw": DATE_RAW,
                            "war_id": war_id,
                            "direction": direction,
                            "amount_raw": amount_raw,
                            "province_ids": province_ids,
                            "beneficiary": beneficiary or "-",
                            "term_mask": expected_mask,
                            "reparations_payer": _payer,
                            "reparations_claimant": _claimant,
                            "submitted": True,
                            "transport_verified": True,
                            "request_binding_verified": True,
                        }
                        with (root / "control-probe.jsonl").open(
                                "a", encoding="utf-8", newline="\n") as stream:
                            stream.write(json.dumps(event) + "\n")
                        return "published"

                    with patch.object(session, "_publish_atomic_request",
                                      side_effect=publish):
                        result = session.submit_peace(
                            f"reparations_{mask}", ACTOR, RECIPIENT,
                            "initiate", DATE_RAW, action_id, parameters,
                            timeout=1)
                    self.assertEqual("submitted", result["status"])
                    wire_fields = captured["wire"].strip().split()
                    self.assertEqual("EU4PEACE_EXEC2", wire_fields[0])
                    self.assertEqual(action_id, wire_fields[3])
                    self.assertEqual(expected_mask, wire_fields[-1])
                    self.assertEqual(expected_mask, result["receipt"]["term_mask"])

    def test_exec2_requires_both_dedicated_capabilities_before_publishing(self):
        parameters = _runner_parameters_for_mask("r")
        for query, execution, reason in (
                (False, True, "NATIVE_PEACE_REPARATIONS_QUERY_CAPABILITY_MISSING"),
                (True, False, "NATIVE_PEACE_REPARATIONS_EXECUTION_CAPABILITY_MISSING")):
            with self.subTest(query=query, execution=execution):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    installation = self._installation(
                        root, query=query, execution=execution)
                    session = ObserverSession(installation, root / "eu4.exe")
                    with patch.object(session, "_publish_atomic_request",
                                      side_effect=AssertionError("wire published")):
                        result = session.submit_peace(
                            "reparations_caps", ACTOR, RECIPIENT,
                            "initiate", DATE_RAW, "war_reparations",
                            parameters, timeout=0)
                    self.assertEqual("unavailable", result["status"])
                    self.assertEqual(reason, result["reason_code"])

    @staticmethod
    def _execution_event(parameters: dict[str, object], effects: dict[str, object],
                         *, request_id: str = "reparations-effect") -> dict[str, object]:
        fields = ObserverSession._peace_execution_fields(parameters)
        assert fields is not None
        (war_id, direction, amount_raw, province_ids, beneficiary,
         _payer, _claimant, _source, _trade_beneficiary,
         _concede_country, _concede_beneficiary,
         _annul_country, _annul_partners, term_mask) = fields
        assert _concede_country is None
        assert _concede_beneficiary is None
        assert _annul_country is None
        assert _annul_partners is None
        return {
            "event": "native_peace_execution_result",
            "family": "peace",
            "session_id": "peace-reparations-session",
            "request_id": request_id,
            "action_id": "war_reparations",
            "actor": ACTOR,
            "recipient": RECIPIENT,
            "phase": "initiate",
            "date_raw": DATE_RAW,
            "war_id": war_id,
            "direction": direction,
            "amount_raw": amount_raw,
            "province_ids": province_ids,
            "beneficiary": beneficiary,
            "term_mask": term_mask,
            "reparations_payer": _payer,
            "reparations_claimant": _claimant,
            "native_state": 0,
            "outcome": "executed",
            "war_before": True,
            "war_after": False,
            "response_verified": True,
            "request_binding_verified": True,
            "execution_verified": True,
            "terms_verified": True,
            "effects": effects,
        }

    def test_verified_reparations_effect_requires_false_to_true_and_binds_roles(self):
        parameters = _parameters_for_mask("r", "demand")
        effects = {
            "complete": True,
            "date_unchanged": True,
            "currency_scale": 1000,
            "money": None,
            "provinces": [],
            "war_reparations": {
                "payer": RECIPIENT,
                "claimant": ACTOR,
                "active_before": False,
                "active_after": True,
                "start_date_raw": 40,
                "end_date_raw": 100,
                "verified": True,
            },
        }
        projected = ObserverSession._public_native_peace_execution_result(
            self._execution_event(parameters, effects),
            "reparations-effect", "peace-reparations-session",
            ACTOR, RECIPIENT, "initiate", DATE_RAW,
            "war_reparations", parameters)
        self.assertIsNotNone(projected)
        self.assertEqual(
            effects["war_reparations"], projected["effects"]["war_reparations"])

        without_dates = copy.deepcopy(effects)
        without_dates["war_reparations"].pop("start_date_raw")
        without_dates["war_reparations"].pop("end_date_raw")
        self.assertIsNotNone(ObserverSession._public_native_peace_execution_result(
            self._execution_event(parameters, without_dates, request_id="no-dates"),
            "no-dates", "peace-reparations-session", ACTOR, RECIPIENT,
            "initiate", DATE_RAW, "war_reparations", parameters))

    def test_fake_verified_reparations_effect_is_rejected(self):
        parameters = _parameters_for_mask("r")
        base = {
            "complete": True,
            "date_unchanged": True,
            "currency_scale": 1000,
            "money": None,
            "provinces": [],
            "war_reparations": {
                "payer": RECIPIENT,
                "claimant": ACTOR,
                "active_before": False,
                "active_after": True,
                "verified": True,
            },
        }
        for field, value in (
                ("active_before", True),
                ("active_after", False),
                ("payer", ACTOR),
                ("claimant", RECIPIENT),
                ("start_date_raw", "not-an-int")):
            with self.subTest(field=field):
                effects = copy.deepcopy(base)
                effects["war_reparations"][field] = value
                event = self._execution_event(
                    parameters, effects, request_id=f"fake-{field}")
                self.assertIsNone(ObserverSession._public_native_peace_execution_result(
                    event, event["request_id"], "peace-reparations-session",
                    ACTOR, RECIPIENT, "initiate", DATE_RAW,
                    "war_reparations", parameters))

    def test_verified_reparations_effect_binds_offer_roles(self):
        parameters = _parameters_for_mask("r", "offer")
        effects = {
            "complete": True,
            "date_unchanged": True,
            "currency_scale": 1000,
            "money": None,
            "provinces": [],
            "war_reparations": {
                "payer": ACTOR,
                "claimant": RECIPIENT,
                "active_before": False,
                "active_after": True,
                "verified": True,
            },
        }
        projected = ObserverSession._public_native_peace_execution_result(
            self._execution_event(parameters, effects, request_id="offer-effect"),
            "offer-effect", "peace-reparations-session", ACTOR, RECIPIENT,
            "initiate", DATE_RAW, "war_reparations", parameters)
        self.assertIsNotNone(projected)
        self.assertEqual(
            (ACTOR, RECIPIENT),
            (projected["effects"]["war_reparations"]["payer"],
             projected["effects"]["war_reparations"]["claimant"]))


if __name__ == "__main__":
    unittest.main()
