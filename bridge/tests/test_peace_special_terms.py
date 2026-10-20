from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from bridge.diplomacy import ObserverSession
from bridge.diplomacy_catalog import ACTIONS
from bridge.peace_execution import normalize_peace_execution_parameters


WAR_ID = "war_0123456789abcdef_01234567"
ACTOR = "FRA"
RECIPIENT = "ENG"
DATE_RAW = 56548944


def _special_term(action_id: str, direction: str = "demand",
                  *, explicit: bool = True) -> dict[str, str]:
    country = RECIPIENT if direction == "demand" else ACTOR
    beneficiary = ACTOR if direction == "demand" else RECIPIENT
    term: dict[str, str] = {"action_id": action_id}
    if explicit:
        term.update({"country": country, "beneficiary": beneficiary})
    return term


def _base_effects() -> dict[str, object]:
    return {
        "complete": True,
        "date_unchanged": True,
        "currency_scale": 1000,
        "money": None,
        "provinces": [],
    }


def _humiliate_effect(*, verified: bool = True) -> dict[str, object]:
    return {
        "country": RECIPIENT,
        "beneficiary": ACTOR,
        "humiliated_before": False,
        "humiliated_after": True if verified else False,
        "country_prestige_before_raw": 10000,
        "country_prestige_after_raw": 9000,
        "country_prestige_delta_raw": -1000,
        "beneficiary_prestige_before_raw": 8000,
        "beneficiary_prestige_after_raw": 9000,
        "beneficiary_prestige_delta_raw": 1000,
        "prestige_scale": 1000,
        "values_readable": True,
        "verified": verified,
    }


def _show_strength_effect(*, verified: bool = True) -> dict[str, object]:
    return {
        **_humiliate_effect(verified=verified),
        "powers_before": [1, 2, 3],
        "powers_after": [4, 1, 8],
        "powers_delta": [3, -1, 5],
        "powers_requested": 3,
    }


def _force_religion_effect(*, verified: bool = True) -> dict[str, object]:
    return {
        "country": RECIPIENT,
        "beneficiary": ACTOR,
        "religion_before": "catholic",
        "religion_after": "protestant",
        "beneficiary_religion_before": "catholic",
        "beneficiary_religion_after": "protestant",
        "capital_religion_before": "catholic",
        "capital_religion_after": "protestant",
        "values_readable": True,
        "verified": verified,
    }


class PeaceSpecialTermsTests(unittest.TestCase):
    def _parameters(self, terms: list[dict[str, object]],
                    action_id: str = "humiliate_rival",
                    direction: str = "demand") -> dict[str, object]:
        return normalize_peace_execution_parameters(
            action_id, ACTOR, RECIPIENT, "initiate", {
                "peace_context": {
                    "war_id": WAR_ID,
                    "direction": direction,
                    "terms": terms,
                },
            })

    def test_normalizer_defaults_special_roles_and_orders_nine_terms(self):
        terms: list[dict[str, object]] = [
            _special_term("force_religion", explicit=False),
            _special_term("show_strength"),
            {"action_id": "annul_treaties", "country": "POR",
             "treaty_partners": ["ENG"]},
            _special_term("humiliate_rival"),
            {"action_id": "transfer_trade_power", "source": "ENG",
             "beneficiary": "FRA"},
            {"action_id": "war_reparations", "payer": "ENG",
             "claimant": "FRA"},
            {"action_id": "cede_province", "province_ids": [177],
             "beneficiary": "FRA"},
            {"action_id": "demand_ducats", "amount": "1.0",
             "payer": "ENG", "claimant": "FRA"},
            {"action_id": "concede_defeat", "conceding_country": "ENG",
             "beneficiary": "FRA"},
        ]
        normalized = self._parameters(terms, action_id="force_religion")
        ordered = normalized["peace_context"]["terms"]
        self.assertEqual(
            ["demand_ducats", "cede_province", "war_reparations",
             "transfer_trade_power", "concede_defeat", "annul_treaties",
             "humiliate_rival", "show_strength", "force_religion"],
            [term["action_id"] for term in ordered])
        self.assertEqual(
            {"action_id": "force_religion", "country": RECIPIENT,
             "beneficiary": ACTOR}, ordered[-1])
        fields = ObserverSession._peace_execution_fields(normalized)
        self.assertIsNotNone(fields)
        assert fields is not None
        self.assertEqual("mprtcahsf", fields[-1])
        self.assertEqual(14, len(fields))

    def test_special_roles_reject_wrong_parties_and_duplicate_terms(self):
        wrong = _special_term("humiliate_rival")
        wrong["country"] = ACTOR
        with self.assertRaisesRegex(
                ValueError, "PEACE_EXECUTION_SPECIAL_PARTIES_INVALID"):
            self._parameters([wrong])
        with self.assertRaisesRegex(
                ValueError, "PEACE_EXECUTION_DUPLICATE_TERM"):
            self._parameters([
                _special_term("show_strength"),
                _special_term("show_strength"),
            ], action_id="show_strength")

    def test_catalog_exposes_shared_eighteen_term_special_contract(self):
        description = ACTIONS["force_religion"].describe()
        terms = description["parameter_definitions"]["peace_context.terms"]
        self.assertEqual(18, terms["max_length"])
        self.assertEqual(
            ["demand_ducats", "cede_province", "war_reparations",
             "transfer_trade_power", "concede_defeat", "annul_treaties",
             "humiliate_rival", "show_strength", "force_religion",
             "return_core", "revoke_core", "release_subject",
             "transfer_subject", "release_nation", "force_vassalization",
             "form_personal_union", "grant_independence", "full_annexation"],
            terms["canonical_order"])
        self.assertEqual(
            "recipient",
            description["parameter_definitions"][
                "peace_context.terms[0].country"]["equals_by_direction"][
                    "demand"])

    def test_special_query_adapter_emits_query13_selection(self):
        session = object.__new__(ObserverSession)
        session.installation_capabilities = lambda: frozenset({
            "native_peace_special_terms_query",
        })
        captured: dict[str, object] = {}
        session.inspect_alliance = lambda *args, **kwargs: captured.update(
            {"args": args, "kwargs": kwargs}) or {"ok": True}
        result = session.inspect_peace_special_offer(
            "show_strength", ACTOR, RECIPIENT, "initiate", {
                "action_id": "show_strength", "war_id": WAR_ID,
                "direction": "demand", "amount_raw": -1,
                "province_ids": [], "beneficiary": None, "source": "-",
                "trade_power_beneficiary": None, "payer": None,
                "claimant": None, "conceding_country": None,
                "concede_beneficiary": None, "annul_country": "-",
                "annul_partners": [], "term_mask": "s",
                "special_terms": [_special_term("show_strength")],
            })
        self.assertEqual({"ok": True}, result)
        kwargs = captured["kwargs"]
        self.assertEqual("native_peace_special_offer_inspection",
                         kwargs["inspection_event"])
        self.assertEqual({"action_id": "show_strength", "country": RECIPIENT,
                          "beneficiary": ACTOR},
                         kwargs["peace_special_offer"]["special_terms"][0])

    def test_h_only_execution_wire_uses_exec7_and_a_placeholders(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = object.__new__(ObserverSession)
            session.directory = Path(temporary)
            (session.directory / "control-probe.jsonl").write_text(
                "", encoding="ascii")
            session.record = {"creation_filetime": 123}
            session.session_id = "special-wire-session"
            session.installation_capabilities = lambda: frozenset({
                "native_peace_submission",
                "native_peace_special_terms_query",
                "native_peace_special_terms_execution",
            })
            captured: dict[str, str] = {}

            def publish(value: str, *_args: object) -> str:
                captured["wire"] = value
                return "published"

            session._publish_atomic_request = publish
            result = session.submit_peace(
                "special-wire-request", ACTOR, RECIPIENT, "initiate", DATE_RAW,
                "humiliate_rival", {
                    "peace_context": {
                        "war_id": WAR_ID,
                        "direction": "demand",
                        "terms": [_special_term("humiliate_rival")],
                    },
                }, timeout=0)
            wire = captured["wire"].split()
            self.assertEqual("EU4PEACE_EXEC7", wire[0])
            self.assertEqual("h", wire[-4])
            self.assertEqual(["-", "-", "-"], wire[-3:])
            self.assertEqual("NATIVE_PEACE_SUBMISSION_TIMEOUT",
                             result["reason_code"])

    def test_inbound_context_maps_special_roles_and_rejects_wrong_direction(self):
        inbound_actor = "ENG"
        inbound_recipient = "FRA"
        context = {
            "war_id": WAR_ID,
            "direction": "demand",
            "complete": True,
            "selected_terms_complete": True,
            "original_actor": inbound_actor,
            "original_recipient": inbound_recipient,
            "terms": [
                {"action_id": "force_religion", "country": inbound_recipient,
                 "beneficiary": inbound_actor},
                {"action_id": "humiliate_rival", "country": inbound_recipient,
                 "beneficiary": inbound_actor},
                {"action_id": "show_strength", "country": inbound_recipient,
                 "beneficiary": inbound_actor},
            ],
        }
        fields = ObserverSession._inbound_peace_context_fields(
            context, inbound_actor, inbound_recipient)
        self.assertIsNotNone(fields)
        assert fields is not None
        self.assertEqual("ENG", fields["special_by_action"][
            "force_religion"]["beneficiary"])
        self.assertTrue(fields["force_religion_requested"])
        invalid = {**context, "terms": [
            {"action_id": "humiliate_rival", "country": inbound_actor,
             "beneficiary": inbound_actor},
        ]}
        self.assertIsNone(ObserverSession._inbound_peace_context_fields(
            invalid, inbound_actor, inbound_recipient))

    def test_special_effects_validate_arithmetic_roles_and_public_projection(self):
        effects = _base_effects()
        effects.update({
            "humiliate_rival": _humiliate_effect(),
            "show_strength": _show_strength_effect(),
            "force_religion": _force_religion_effect(),
        })
        self.assertTrue(ObserverSession._valid_native_peace_effects(
            effects, "demand", -1, [], None, ACTOR, RECIPIENT, DATE_RAW, True,
            humiliate_rival_country=RECIPIENT,
            humiliate_rival_beneficiary=ACTOR,
            humiliate_rival_requested=True,
            show_strength_country=RECIPIENT,
            show_strength_beneficiary=ACTOR,
            show_strength_requested=True,
            force_religion_country=RECIPIENT,
            force_religion_beneficiary=ACTOR,
            force_religion_requested=True))
        public = ObserverSession._public_native_peace_effects(effects)
        self.assertEqual(3, public["show_strength"]["powers_requested"])
        self.assertNotIn("private", public["force_religion"])

        malformed = {**effects, "show_strength": {
            **effects["show_strength"], "powers_delta": [3, 0, 5]}}
        self.assertFalse(ObserverSession._valid_native_peace_effects(
            malformed, "demand", -1, [], None, ACTOR, RECIPIENT, DATE_RAW, True,
            humiliate_rival_country=RECIPIENT,
            humiliate_rival_beneficiary=ACTOR,
            humiliate_rival_requested=True,
            show_strength_country=RECIPIENT,
            show_strength_beneficiary=ACTOR,
            show_strength_requested=True,
            force_religion_country=RECIPIENT,
            force_religion_beneficiary=ACTOR,
            force_religion_requested=True))

        malformed_religion = {**effects, "force_religion": {
            **effects["force_religion"], "capital_religion_after": 5}}
        self.assertFalse(ObserverSession._valid_native_peace_effects(
            malformed_religion, "demand", -1, [], None, ACTOR, RECIPIENT,
            DATE_RAW, True,
            humiliate_rival_country=RECIPIENT,
            humiliate_rival_beneficiary=ACTOR,
            humiliate_rival_requested=True,
            show_strength_country=RECIPIENT,
            show_strength_beneficiary=ACTOR,
            show_strength_requested=True,
            force_religion_country=RECIPIENT,
            force_religion_beneficiary=ACTOR,
            force_religion_requested=True))

    def test_rejected_special_effects_keep_readable_values_without_verified(self):
        effects = _base_effects()
        effects["humiliate_rival"] = _humiliate_effect(verified=False)
        effects["show_strength"] = _show_strength_effect(verified=False)
        effects["force_religion"] = _force_religion_effect(verified=False)
        self.assertTrue(ObserverSession._valid_native_peace_effects(
            effects, "demand", -1, [], None, ACTOR, RECIPIENT, DATE_RAW, False,
            humiliate_rival_country=RECIPIENT,
            humiliate_rival_beneficiary=ACTOR,
            humiliate_rival_requested=True,
            show_strength_country=RECIPIENT,
            show_strength_beneficiary=ACTOR,
            show_strength_requested=True,
            force_religion_country=RECIPIENT,
            force_religion_beneficiary=ACTOR,
            force_religion_requested=True))


if __name__ == "__main__":
    unittest.main()
