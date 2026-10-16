from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bridge.cli import main
from bridge.compiler import ActionRequest, RequestError, compile_request, compile_requests
from bridge.protocol import (
    IncompleteSnapshotError,
    InterleavedSnapshotError,
    InvalidIdentifierError,
    ProtocolError,
    parse_log,
)
from bridge.planner import OpenAICompatiblePlanner, PlannerDisabledError


class ProtocolTests(unittest.TestCase):
    def test_prefixes_multiple_snapshots_and_ack_are_parsed(self) -> None:
        log = "\n".join(
            [
                "2026.10.04> EU4LLM|BEGIN|live|FRA",
                "[effect] EU4LLM|FIELD|live|treasury|123.4",
                "EU4LLM|FIELD|live|ai|yes",
                "EU4LLM|END|live",
                "EU4LLM|ACK|req_1|applied",
                "prefix EU4LLM|BEGIN|live|FRA",
                "EU4LLM|FIELD|live|treasury|130",
                "EU4LLM|END|live",
            ]
        )
        parsed = parse_log(log)
        self.assertEqual(len(parsed.snapshots), 2)
        self.assertEqual(parsed.snapshots[0].fields["treasury"], "123.4")
        self.assertEqual(parsed.snapshots[1].fields["treasury"], "130")
        self.assertEqual(parsed.acks[0].to_dict(), {"request_id": "req_1", "status": "applied"})

    def test_incomplete_snapshot_is_rejected(self) -> None:
        with self.assertRaises(IncompleteSnapshotError):
            parse_log("EU4LLM|BEGIN|live|FRA\nEU4LLM|FIELD|live|year|1444\n")

    def test_interleaving_and_wrong_end_id_are_rejected(self) -> None:
        with self.assertRaises(InterleavedSnapshotError):
            parse_log(
                "EU4LLM|BEGIN|a|FRA\nEU4LLM|BEGIN|b|FRA\n"
            )
        with self.assertRaises(InterleavedSnapshotError):
            parse_log(
                "EU4LLM|BEGIN|a|FRA\nEU4LLM|END|b\n"
            )

    def test_invalid_ids_and_unknown_operations_are_rejected(self) -> None:
        with self.assertRaises(InvalidIdentifierError):
            parse_log("EU4LLM|BEGIN|bad-id|FRA\nEU4LLM|END|bad-id\n")
        with self.assertRaises(ProtocolError):
            parse_log("EU4LLM|BEGIN|live|FRA\nEU4LLM|FIELD|live|x|a|injected\n")
        with self.assertRaises(ProtocolError):
            parse_log("EU4LLM|NOPE|live\n")

    def test_lenient_mode_drops_truncated_snapshot_and_reports_issue(self) -> None:
        parsed = parse_log("EU4LLM|BEGIN|live|FRA\n", strict=False)
        self.assertEqual(parsed.snapshots, ())
        self.assertEqual(len(parsed.issues), 1)


class CompilerTests(unittest.TestCase):
    def test_snapshot_uses_fixed_effect_and_fra_scope(self) -> None:
        script = compile_request({"id": "live", "action": "snapshot"})
        self.assertIn("exists = FRA", script)
        self.assertIn("FRA = {", script)
        self.assertIn('log = "EU4LLM|BEGIN|live|FRA"', script)
        self.assertIn('EU4LLM|ACK|live|applied', script)
        self.assertNotIn("llm_req_live", script)

    def test_mutations_are_guarded_and_idempotent(self) -> None:
        lock = compile_request({"request_id": "req_1", "action": "lock_diplomacy"})
        self.assertIn("ai = yes", lock)
        self.assertIn("exists = yes", lock)
        self.assertIn("NOT = { has_country_flag = llm_req_req_1 }", lock)
        self.assertIn("set_country_flag = llm_req_req_1", lock)
        self.assertIn("set_country_flag = llm_diplomacy_locked", lock)
        self.assertIn("EU4LLM|ACK|req_1|rejected", lock)

        unlock = compile_request({"id": "req_2", "action": "unlock_diplomacy", "target": "FRA"})
        self.assertIn("clr_country_flag = llm_diplomacy_locked", unlock)

    def test_improve_relations_is_fixed_to_eng_and_works_while_locked(self) -> None:
        script = compile_request(
            {"id": "req_3", "action": "improve_relations", "target": "ENG"}
        )
        # The flag blocks native AI diplomacy. An explicitly authorized bridge
        # action must still be able to run while the lock is set.
        self.assertNotIn("NOT = { has_country_flag = llm_diplomacy_locked }", script)
        self.assertIn("ENG = {", script)
        self.assertIn("exists = yes", script)
        self.assertIn("add_opinion = {", script)
        self.assertIn("who = ENG", script)
        self.assertIn("modifier = llm_bridge_goodwill", script)
        self.assertNotIn("set_country_flag = llm_diplomacy_locked", script)

    def test_untrusted_request_cannot_reach_script(self) -> None:
        invalid_requests = [
            {"id": "bad-id", "action": "lock_diplomacy"},
            {"id": "x", "action": "run", "code": "set_country_flag = hacked"},
            {"id": "x", "action": "improve_relations", "target": "ENG } log = hacked"},
            {"id": "x", "action": "improve_relations"},
            {"id": "x", "action": "lock_diplomacy", "target": "ENG"},
            {"id": "x", "request_id": "y", "action": "lock_diplomacy"},
        ]
        for request in invalid_requests:
            with self.subTest(request=request), self.assertRaises(RequestError):
                compile_request(request)
        with self.assertRaises(RequestError):
            compile_request(ActionRequest("bad-id", "lock_diplomacy"))

    def test_request_lists_are_compiled_without_cross_contamination(self) -> None:
        script = compile_requests(
            [
                {"id": "a", "action": "lock_diplomacy"},
                {"id": "b", "action": "unlock_diplomacy"},
            ]
        )
        self.assertEqual(script.count("Generated by EU4LLM bridge"), 2)
        self.assertIn("EU4LLM|ACK|a|applied", script)
        self.assertIn("EU4LLM|ACK|b|applied", script)


class CliTests(unittest.TestCase):
    def test_cli_parse_and_compile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "game.log"
            log.write_text(
                "EU4LLM|BEGIN|live|FRA\nEU4LLM|END|live\nEU4LLM|ACK|r1|rejected\n",
                encoding="utf-8",
            )
            request = root / "request.json"
            request.write_text(
                json.dumps({"id": "r1", "action": "lock_diplomacy"}),
                encoding="utf-8",
            )
            run = root / "run.txt"
            self.assertEqual(main(["parse", str(log)]), 0)
            self.assertEqual(main(["compile", str(request), str(run)]), 0)
            self.assertIn("set_country_flag = llm_diplomacy_locked", run.read_text(encoding="utf-8"))


class PlannerTests(unittest.TestCase):
    def test_planner_is_disabled_without_an_explicit_opt_in(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            planner = OpenAICompatiblePlanner.from_environment()
        self.assertFalse(planner.enabled)
        with self.assertRaises(PlannerDisabledError):
            planner.plan(parse_log("EU4LLM|BEGIN|live|FRA\nEU4LLM|END|live\n").snapshots[0])


if __name__ == "__main__":
    unittest.main()

