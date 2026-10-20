from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest

from bridge.diplomacy import ObserverSession


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (Path(__file__).parent / "fixtures" /
           "peace_country_r61_inbound_full_annex_real.json")


class PeaceCountryR61InboundFullAnnexRealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.event = cls.fixture["event"]
        cls.source = cls.fixture["source"]

    def _assert_source_event(self) -> dict:
        path = ROOT / Path(self.source["path"])
        self.assertTrue(path.is_file(), path)
        raw_file = path.read_bytes()
        self.assertEqual(self.source["size"], len(raw_file))
        self.assertEqual(self.source["sha256"], hashlib.sha256(raw_file).hexdigest())
        lines = raw_file.splitlines()
        raw_line = lines[self.source["source_line"] - 1]
        self.assertEqual(self.source["source_line_bytes"], len(raw_line))
        self.assertEqual(self.source["source_line_sha256"],
                         hashlib.sha256(raw_line).hexdigest())
        event = json.loads(raw_line.decode("utf-8"))
        self.assertEqual(self.event, event)
        return event

    def test_real_live_full_annex_proof_and_combined_context_validate(self):
        event = self._assert_source_event()
        expected = self.fixture["expected"]
        self.assertTrue(ObserverSession._valid_native_inbound_inspection(
            event, event["query_id"], event["session_id"],
            expected["actor"], expected["phase"],
            expected["native_proposal_id"], expected["date_raw"],
            expected["action_id"]))
        context = event["peace_context"]
        self.assertTrue(ObserverSession._valid_inbound_peace_context(
            context, "ENG", "FRA"))
        fields = ObserverSession._inbound_peace_context_fields(
            context, "ENG", "FRA")
        self.assertIsNotNone(fields)
        assert fields is not None
        self.assertTrue(fields["full_annex_proof_verified"])
        self.assertEqual("TYR", fields["full_annexation_country"])
        self.assertEqual("FRA", fields["full_annexation_beneficiary"])
        self.assertEqual(
            expected["peace_context"]["terms"], fields["terms"])

        public = ObserverSession._public_native_inbound_inspection(
            event, expected["date_raw"], expected["action_id"])
        self.assertEqual(context, public["peace_context"])
        self.assertTrue(public["peace_context"]["complete"])
        self.assertTrue(public["peace_context"]["selected_terms_complete"])
        serialized = json.dumps(public, ensure_ascii=False, sort_keys=True)
        for marker in ("query_id", "session_id", "native_proposal_id",
                       "date28", "date2c", "envoy30", "token3c"):
            self.assertNotIn(marker, serialized)

    def test_live_proof_snapshot_owned_and_native_flags_are_required(self):
        self._assert_source_event()
        for field in ("live_snapshot_complete", "sealed_snapshot_equal",
                      "owner_owned_ids_complete", "native_check_called",
                      "native_check_result"):
            tampered = copy.deepcopy(self.event)
            tampered["peace_context"]["full_annex_proof"][field] = False
            with self.subTest(field=field):
                self.assertFalse(ObserverSession._valid_native_inbound_inspection(
                    tampered, tampered["query_id"], tampered["session_id"],
                    "ENG", "accept", 1, tampered["date_raw"],
                    "peace_offer"))

        wrong_owner = copy.deepcopy(self.event)
        wrong_owner["peace_context"]["full_annex_proof"]["owner"] = "ENG"
        self.assertFalse(ObserverSession._valid_inbound_peace_context(
            wrong_owner["peace_context"], "ENG", "FRA"))

    def test_preflight_reuse_schema_allows_live_flags_false_but_binds_identity(self):
        self._assert_source_event()
        reused = copy.deepcopy(self.event)
        proof = self.fixture["expected"]["reuse_proof"]
        reused["peace_context"]["full_annex_proof"] = copy.deepcopy(proof)
        self.assertTrue(self.fixture["expected"]["reuse_variant_is_synthetic"])
        self.assertTrue(ObserverSession._valid_native_inbound_inspection(
            reused, reused["query_id"], reused["session_id"],
            "ENG", "accept", 1, reused["date_raw"], "peace_offer"))
        self.assertTrue(ObserverSession._valid_inbound_peace_context(
            reused["peace_context"], "ENG", "FRA"))
        fields = ObserverSession._inbound_peace_context_fields(
            reused["peace_context"], "ENG", "FRA")
        self.assertIsNotNone(fields)
        assert fields is not None
        self.assertTrue(fields["full_annex_proof_verified"])
        self.assertEqual("PREFLIGHT_PROOF_REUSED", proof["reason"])
        self.assertFalse(proof["live_offer_present"])
        self.assertFalse(proof["sealed_snapshot_equal"])

        identity_tampered = copy.deepcopy(reused)
        identity_tampered["peace_context"]["full_annex_proof"][
            "request_identity_matches"] = False
        self.assertFalse(ObserverSession._valid_native_inbound_inspection(
            identity_tampered, identity_tampered["query_id"],
            identity_tampered["session_id"], "ENG", "accept", 1,
            identity_tampered["date_raw"], "peace_offer"))

    def test_canonicalizer_keeps_both_real_country_terms_and_proof(self):
        event = self._assert_source_event()
        context = event["peace_context"]
        public = ObserverSession._canonicalize_inbound_peace_context(context)
        self.assertIsNotNone(public)
        assert public is not None
        self.assertEqual(context["war_id"], public["war_id"])
        self.assertEqual(context["direction"], public["direction"])
        self.assertEqual(context["terms"], public["terms"])
        self.assertEqual(context["full_annex_proof"], public["full_annex_proof"])
        self.assertEqual(
            {"release_nation", "full_annexation"},
            {term["action_id"] for term in public["terms"]})


if __name__ == "__main__":
    unittest.main()
