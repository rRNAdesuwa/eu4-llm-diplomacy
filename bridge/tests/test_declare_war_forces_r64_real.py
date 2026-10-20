from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from bridge.declarewar_forces import (
    project_declare_war_forces,
    valid_declare_war_forces,
)
from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.native_text import EU4_ESCAPE_CODEC


FIXTURE = Path(__file__).parent / "fixtures" / "declare_war_r64_forces_real.json"


class _SemanticForceSession:
    """Read-only session double for the public DiplomacyTools boundary."""

    def __init__(self, event: dict):
        self.event = event
        self.session_id = event["session_id"]
        self.calls: list[tuple] = []

    def health(self) -> dict:
        return {
            "status": "ready",
            "state_id": "r64-force-real-fixture",
            "date_raw": self.event["date_raw"],
            "reasons": [],
            "complete": True,
        }

    def installation_capabilities(self) -> frozenset[str]:
        return frozenset({"native_declare_war_query"})

    def inspect_declare_war(
        self,
        action_id: str,
        actor: str,
        recipient: str,
        phase: str,
        parameters: dict | None = None,
    ) -> dict:
        self.calls.append((action_id, actor, recipient, phase, parameters))
        return ObserverSession._semantic_declare_war_inspection(
            self.event, EU4_ESCAPE_CODEC
        )


class DeclareWarForcesR64RealTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.cases = {item["name"]: item for item in cls.payload["cases"]}

    @staticmethod
    def _projection_event(case: dict) -> dict:
        event = dict(case["query"])
        event["native_forces"] = case["native_forces"]
        return event

    def test_real_native_forces_validate_and_project_to_saved_public_forces(self) -> None:
        self.assertEqual(6, self.payload["source"]["case_count"])
        self.assertFalse(self.payload["source"]["candidate_lists_retained"])
        self.assertEqual(6, len(self.cases))
        for case in self.cases.values():
            with self.subTest(case=case["name"]):
                native = case["native_forces"]
                public = case["public_forces"]
                self.assertTrue(valid_declare_war_forces(native))
                self.assertEqual(public, project_declare_war_forces(native))
                self.assertTrue(public["complete"])
                self.assertNotIn("native_forces", public)
                for side_name in ("attackers", "defenders"):
                    side = public[side_name]
                    self.assertEqual("men", side["deployed"]["unit"])
                    self.assertEqual("men", side["reserve_manpower"]["unit"])
                    self.assertTrue(side["deployed"]["complete"])
                    self.assertTrue(side["reserve_manpower"]["complete"])
                summary = case["participant_summary"]
                by_side = summary["candidate_count_by_side"]
                self.assertEqual(
                    summary["candidate_count"],
                    sum(item["count"] for item in by_side.values()),
                )
                self.assertTrue(summary["complete"])
                self.assertNotIn("candidates", case["query"])

    def test_real_variants_preserve_expected_force_deltas(self) -> None:
        eng_base = self.cases["eng_base_no_casus_belli"]["public_forces"]
        eng_co = self.cases["eng_conquest_co_swe"]["public_forces"]
        mlo_base = self.cases["mlo_base_no_casus_belli"]["public_forces"]
        mlo_call = self.cases["mlo_call_sav"]["public_forces"]
        mlo_promise = self.cases["mlo_call_sav_promise_sav"]["public_forces"]
        mlo_combo = self.cases["mlo_call_sav_promise_sav_co_boh"]["public_forces"]

        self.assertIn("TEU", eng_co["defenders"]["countries"])
        self.assertEqual(
            16000,
            eng_co["defenders"]["deployed"]["total"]
            - eng_base["defenders"]["deployed"]["total"],
        )
        self.assertEqual(
            22890,
            eng_co["defenders"]["reserve_manpower"]["amount"]
            - eng_base["defenders"]["reserve_manpower"]["amount"],
        )

        self.assertEqual(
            16000,
            mlo_call["attackers"]["deployed"]["total"]
            - mlo_base["attackers"]["deployed"]["total"],
        )
        self.assertEqual(
            37500,
            mlo_call["attackers"]["reserve_manpower"]["amount"]
            - mlo_base["attackers"]["reserve_manpower"]["amount"],
        )
        self.assertEqual(mlo_call, mlo_promise)
        combo_summary = self.cases["mlo_call_sav_promise_sav_co_boh"][
            "participant_summary"]
        self.assertIn(
            "BOH",
            combo_summary["candidate_count_by_side"]["defender"][
                "selected_countries"],
        )
        self.assertGreater(
            mlo_combo["defenders"]["deployed"]["total"],
            mlo_base["defenders"]["deployed"]["total"],
        )

    def test_diplomacy_tools_inspect_keeps_forces_at_public_api_layer(self) -> None:
        for name in ("eng_base_no_casus_belli", "mlo_call_sav_promise_sav_co_boh"):
            case = self.cases[name]
            event = self._projection_event(case)
            session = _SemanticForceSession(event)
            ready = {
                "status": "ready",
                "state_id": "r64-force-real-fixture",
                "date_raw": event["date_raw"],
                "reasons": [],
                "complete": True,
            }
            with self.subTest(case=name), patch.object(session, "health", return_value=ready), patch(
                "bridge.diplomacy.probe_identity",
                return_value={"session_id": event["session_id"]},
            ):
                public = DiplomacyTools(None, session).inspect_diplomatic_action(
                    "declare_war",
                    event["actor"],
                    event["recipient"],
                    parameters=case["parameters"],
                )
            self.assertEqual(case["public_forces"], public["forces"])
            self.assertNotIn("native_forces", public)
            self.assertEqual(1, len(session.calls))
            self.assertEqual(case["parameters"], session.calls[0][-1])


if __name__ == "__main__":
    import unittest

    unittest.main()
