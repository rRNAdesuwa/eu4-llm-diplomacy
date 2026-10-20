import copy
import hashlib
import json
from pathlib import Path
import unittest

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.native_text import EU4_ESCAPE_CODEC
from bridge.favor_resources import (
    MEN_QUERY_CAPABILITY,
    MEN_SUBMISSION_CAPABILITY,
    TRUST_QUERY_CAPABILITY,
    TRUST_SUBMISSION_CAPABILITY,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "bridge" / "tests" / "fixtures" / "r73_favor_queries_real.json"
FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _raw_case(name: str) -> dict:
    rows = [case for case in FIXTURE["cases"] if case.get("name") == name]
    if len(rows) != 1:
        raise AssertionError(f"missing fixture case: {name}")
    row = rows[0]
    raw = copy.deepcopy(row["raw"])
    canonical = json.dumps(
        raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != row["raw_sha256"]:
        raise AssertionError(f"fixture raw sha mismatch: {name}")
    if raw.get("session_id") != FIXTURE["session_id"]:
        raise AssertionError(f"fixture session mismatch: {name}")
    health = row.get("health", FIXTURE["health"])
    if raw.get("date_raw") != health["date_raw"]:
        raise AssertionError(f"fixture date mismatch: {name}")
    return raw


class RawFavorReplaySession:
    record = {"controlled_countries": ["FRA"]}
    native_text_codec = EU4_ESCAPE_CODEC

    def __init__(self, raw: dict, health: dict | None = None):
        self.raw = copy.deepcopy(raw)
        self.session_id = raw["session_id"]
        self.health_payload = copy.deepcopy(health or FIXTURE["health"])
        self.health_payload["date_raw"] = raw["date_raw"]
        self.semantic = ObserverSession._semantic_inspection(
            self.raw, {}, codec=EU4_ESCAPE_CODEC)

    def health(self):
        return copy.deepcopy(self.health_payload)

    def installation_capabilities(self):
        action = self.raw["action_id"]
        return frozenset({
            MEN_QUERY_CAPABILITY if action == "trade_favors_for_men"
            else TRUST_QUERY_CAPABILITY,
            MEN_SUBMISSION_CAPABILITY if action == "trade_favors_for_men"
            else TRUST_SUBMISSION_CAPABILITY,
        })

    def inspect_alliance(self, action, actor, recipient, phase, *args, **kwargs):
        self.semantic["action_id"] = action
        self.semantic["actor"] = actor
        self.semantic["recipient"] = recipient
        self.semantic["phase"] = phase
        return copy.deepcopy(self.semantic)


class R73FavorQueryContractTests(unittest.TestCase):
    def test_fixture_records_source_hashes_and_health(self):
        self.assertEqual("r73_favor_queries_real_fixture_v1", FIXTURE["format"])
        self.assertRegex(FIXTURE["source_report_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(FIXTURE["source_catalog_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(5, len(FIXTURE["cases"]))
        self.assertRegex(FIXTURE["source_extra"]["report_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(FIXTURE["source_extra"]["native_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(all(
            isinstance(case.get("source_raw_line_sha256"), str)
            and len(case["source_raw_line_sha256"]) == 64
            for case in FIXTURE["cases"]))

    def test_real_r73_negative_keeps_resource_adapter_support(self):
        for name in ("trust_FRA_PAP", "men_FRA_PAP"):
            with self.subTest(name=name):
                raw = _raw_case(name)
                session = RawFavorReplaySession(raw)
                result = DiplomacyTools(None, session).inspect_diplomatic_action(
                    raw["action_id"], "FRA", raw["recipient"])
                self.assertEqual(
                    "native_favor_%s_submission" % raw["native_favor_trade"]["kind"],
                    result["interface_support"]["execute"],
                )
                self.assertEqual("available", result["authorization"]["status"])
                self.assertEqual("unavailable", result["legality"]["status"])
                self.assertEqual(
                    result["native_diagnostic"]["text"],
                    result["legality"]["reasons"][0]["text"],
                )

    def test_real_no_diplomat_keeps_support_separate_from_legality(self):
        raw = _raw_case("men_FRA_SAV_no_diplomat")
        self.assertEqual(0, raw["available_diplomat_count"])
        row = next(case for case in FIXTURE["cases"] if case["name"] == "men_FRA_SAV_no_diplomat")
        session = RawFavorReplaySession(raw, row["health"])
        result = DiplomacyTools(None, session).inspect_diplomatic_action(
            raw["action_id"], "FRA", raw["recipient"])
        self.assertEqual("native_favor_men_submission", result["interface_support"]["execute"])
        self.assertEqual("available", result["authorization"]["status"])
        self.assertEqual("unavailable", result["legality"]["status"])
        codes = [item["code"] for item in result["legality"]["reasons"]]
        self.assertIn("NATIVE_DIPLOMAT_UNAVAILABLE", codes)
        self.assertEqual(
            result["native_diagnostic"]["text"],
            result["legality"]["reasons"][0]["text"],
        )

    def test_real_negative_validity_reason_uses_native_chinese_diagnostic(self):
        for name in ("trust_FRA_GEN", "men_FRA_LIT"):
            with self.subTest(name=name):
                raw = _raw_case(name)
                self.assertIs(raw["native_validity"], False)
                session = RawFavorReplaySession(raw)
                result = DiplomacyTools(None, session).inspect_diplomatic_action(
                    raw["action_id"], "FRA", raw["recipient"])
                first = result["legality"]["reasons"][0]
                self.assertEqual("NATIVE_VALIDITY_FALSE", first["code"])
                self.assertIn("人情", first["text"])
                self.assertEqual(first["text"], result["native_diagnostic"]["text"])
                self.assertIn(
                    "信任" if raw["native_favor_trade"]["kind"] == "trust" else "好感度",
                    first["text"],
                )


if __name__ == "__main__":
    unittest.main()
