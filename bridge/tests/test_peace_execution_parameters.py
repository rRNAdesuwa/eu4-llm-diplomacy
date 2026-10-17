import copy
import unittest

from bridge.peace_execution import normalize_peace_execution_parameters


WAR_ID = "war_0123456789abcdef_01234567"


def normalize(action, recipient, parameters, *, actor="FRA", phase="initiate"):
    return normalize_peace_execution_parameters(
        action, actor, recipient, phase, parameters)


class PeaceExecutionParameterTests(unittest.TestCase):
    def test_white_requires_empty_terms_and_returns_fresh_context(self):
        parameters = {"peace_context": {
            "war_id": WAR_ID, "direction": "demand", "terms": []}}
        original = copy.deepcopy(parameters)
        result = normalize("white_peace", "ENG", parameters)
        self.assertEqual(parameters, original)
        self.assertEqual(parameters, result)
        self.assertIsNot(parameters, result)
        self.assertIsNot(parameters["peace_context"], result["peace_context"])

    def test_mixed_terms_are_normalized_money_then_province(self):
        parameters = {"peace_context": {
            "war_id": WAR_ID,
            "direction": "demand",
            "terms": [
                {"action_id": "cede_province", "province_ids": [177, 12],
                 "beneficiary": "FRA"},
                {"action_id": "demand_ducats", "amount": 10,
                 "payer": "ENG", "claimant": "FRA"},
            ],
        }}
        result = normalize("demand_ducats", "ENG", parameters)
        self.assertEqual(
            ["demand_ducats", "cede_province"],
            [term["action_id"]
             for term in result["peace_context"]["terms"]])
        self.assertEqual("10.0",
                         result["peace_context"]["terms"][0]["amount"])
        self.assertEqual([177, 12],
                         result["peace_context"]["terms"][1]["province_ids"])
        self.assertEqual("FRA",
                         result["peace_context"]["terms"][1]["beneficiary"])

    def test_cede_action_requires_cede_term_and_accepts_optional_money(self):
        result = normalize("cede_province", "ENG", {"peace_context": {
            "war_id": WAR_ID, "direction": "demand", "terms": [
                {"action_id": "demand_ducats", "amount": "0.1",
                 "payer": "ENG", "claimant": "FRA"},
                {"action_id": "cede_province", "province_ids": [1],
                 "beneficiary": "SAV"},
            ]}})
        self.assertEqual("0.1", result["peace_context"]["terms"][0]["amount"])

    def test_amount_types_and_native_raw_precision(self):
        for value in (10, 10.0, "10", "10.0", "10.00"):
            result = normalize("demand_ducats", "ENG", {"peace_context": {
                "war_id": WAR_ID, "direction": "demand", "terms": [{
                    "action_id": "demand_ducats", "amount": value,
                    "payer": "ENG", "claimant": "FRA"}]}})
            self.assertEqual("10.0",
                             result["peace_context"]["terms"][0]["amount"])
        for value in (True, 0, -1, "10.01", "NaN", "Infinity", "1e1000000",
                      "10.00000000000000000000000000000000001"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                        ValueError, "PEACE_EXECUTION_MONEY_AMOUNT_INVALID"):
                    normalize("demand_ducats", "ENG", {"peace_context": {
                        "war_id": WAR_ID, "direction": "demand", "terms": [{
                            "action_id": "demand_ducats", "amount": value,
                            "payer": "ENG", "claimant": "FRA"}]}})

    def test_amount_upper_bound_and_parties_are_strict(self):
        valid = {"peace_context": {
            "war_id": WAR_ID, "direction": "demand", "terms": [{
                "action_id": "demand_ducats", "amount": "2147483.6",
                "payer": "ENG", "claimant": "FRA"}]}}
        self.assertEqual("2147483.6",
                         normalize("demand_ducats", "ENG", valid)[
                             "peace_context"]["terms"][0]["amount"])
        for amount in ("2147483.7", "2147483.647"):
            invalid = copy.deepcopy(valid)
            invalid["peace_context"]["terms"][0]["amount"] = amount
            with self.assertRaisesRegex(
                    ValueError, "PEACE_EXECUTION_MONEY_AMOUNT_INVALID"):
                normalize("demand_ducats", "ENG", invalid)
        invalid = copy.deepcopy(valid)
        invalid["peace_context"]["terms"][0]["payer"] = "FRA"
        with self.assertRaisesRegex(
                ValueError, "PEACE_EXECUTION_MONEY_PARTIES_INVALID"):
            normalize("demand_ducats", "ENG", invalid)

    def test_province_ids_are_unique_positive_int32_and_beneficiary_explicit(self):
        result = normalize("cede_province", "ENG", {"peace_context": {
            "war_id": WAR_ID, "direction": "demand", "terms": [{
                "action_id": "cede_province", "province_ids": [
                    2147483647, 177], "beneficiary": "FRA"}]}})
        self.assertEqual([2147483647, 177],
                         result["peace_context"]["terms"][0]["province_ids"])
        bad_values = ([True], [0], [-1], [1, 1], list(range(1, 18)))
        for province_ids in bad_values:
            with self.subTest(province_ids=province_ids):
                with self.assertRaisesRegex(
                        ValueError, "PEACE_EXECUTION_PROVINCE_IDS_INVALID"):
                    normalize("cede_province", "ENG", {"peace_context": {
                        "war_id": WAR_ID, "direction": "demand", "terms": [{
                            "action_id": "cede_province",
                            "province_ids": province_ids,
                            "beneficiary": "FRA"}]}})

    def test_unknown_keys_terms_and_action_mismatch_are_rejected(self):
        unknown_context = {"peace_context": {
            "war_id": WAR_ID, "direction": "demand", "terms": [],
            "extra": 1}}
        with self.assertRaisesRegex(
                ValueError, "PEACE_EXECUTION_CONTEXT_INVALID"):
            normalize("white_peace", "ENG", unknown_context)
        unknown_term = {"peace_context": {
            "war_id": WAR_ID, "direction": "demand", "terms": [{
                "action_id": "return_core", "province_ids": [177],
                "beneficiary": "FRA"}]}}
        with self.assertRaisesRegex(
                ValueError, "PEACE_EXECUTION_TERM_UNKNOWN"):
            normalize("cede_province", "ENG", unknown_term)
        unhashable_term = {"peace_context": {
            "war_id": WAR_ID, "direction": "demand", "terms": [{
                "action_id": ["demand_ducats"], "amount": 1,
                "payer": "ENG", "claimant": "FRA"}]}}
        with self.assertRaisesRegex(
                ValueError, "PEACE_EXECUTION_TERM_UNKNOWN"):
            normalize("demand_ducats", "ENG", unhashable_term)
        with self.assertRaisesRegex(
                ValueError, "PEACE_EXECUTION_ACTION_TERM_MISSING"):
            normalize("demand_ducats", "ENG", {"peace_context": {
                "war_id": WAR_ID, "direction": "demand", "terms": [{
                    "action_id": "cede_province", "province_ids": [177],
                    "beneficiary": "FRA"}]}})
        with self.assertRaisesRegex(
                ValueError, "PEACE_EXECUTION_DUPLICATE_TERM"):
            normalize("demand_ducats", "ENG", {"peace_context": {
                "war_id": WAR_ID, "direction": "demand", "terms": [
                    {"action_id": "demand_ducats", "amount": 1,
                     "payer": "ENG", "claimant": "FRA"},
                    {"action_id": "demand_ducats", "amount": 2,
                     "payer": "ENG", "claimant": "FRA"}]}})

    def test_identity_phase_context_and_beneficiary_rules(self):
        base = {"peace_context": {
            "war_id": WAR_ID, "direction": "demand", "terms": []}}
        checks = (
            ("actor", lambda: normalize("white_peace", "ENG", base,
                                         actor="ENG"),
             "PEACE_EXECUTION_ACTOR_INVALID"),
            ("recipient", lambda: normalize("white_peace", "FRA", base),
             "PEACE_EXECUTION_RECIPIENT_INVALID"),
            ("phase", lambda: normalize("white_peace", "ENG", base,
                                        phase="accept"),
             "PEACE_EXECUTION_PHASE_INVALID"),
            ("war", lambda: normalize("white_peace", "ENG", {
                "peace_context": {"war_id": "war_bad", "direction": "demand",
                                   "terms": []}}),
             "PEACE_EXECUTION_WAR_ID_INVALID"),
            ("direction", lambda: normalize("white_peace", "ENG", {
                "peace_context": {"war_id": WAR_ID, "direction": "sideways",
                                   "terms": []}}),
             "PEACE_EXECUTION_DIRECTION_INVALID"),
        )
        for name, call, code in checks:
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, code):
                    call()
        with self.assertRaisesRegex(
                ValueError, "PEACE_EXECUTION_BENEFICIARY_INVALID"):
            normalize("cede_province", "ENG", {"peace_context": {
                "war_id": WAR_ID, "direction": "demand", "terms": [{
                    "action_id": "cede_province", "province_ids": [177],
                    "beneficiary": "eng"}]}})

    def test_offer_direction_reverses_money_parties(self):
        result = normalize("demand_ducats", "ENG", {"peace_context": {
            "war_id": WAR_ID, "direction": "offer", "terms": [{
                "action_id": "demand_ducats", "amount": "10.0",
                "payer": "FRA", "claimant": "ENG"}]}})
        context = result["peace_context"]
        self.assertEqual("offer", context["direction"])
        self.assertEqual("FRA", context["terms"][0]["payer"])
        self.assertEqual("ENG", context["terms"][0]["claimant"])

    def test_offer_province_keeps_explicit_beneficiary_and_legacy_empty_defaults(self):
        offer = normalize("cede_province", "ENG", {"peace_context": {
            "war_id": WAR_ID, "direction": "offer", "terms": [{
                "action_id": "cede_province", "province_ids": [177],
                "beneficiary": "ENG"}]}})
        self.assertEqual("offer", offer["peace_context"]["direction"])
        self.assertEqual("ENG", offer["peace_context"]["terms"][0][
            "beneficiary"])


if __name__ == "__main__":
    unittest.main()
