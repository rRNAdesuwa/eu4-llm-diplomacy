"""Offline discovery only: no sockets, live log, native calls or mailbox writes."""
import contextlib
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bridge import diplomacy_research_capabilities as cap
from bridge import diplomacy_lab_http as v9
from bridge import diplomacy_lab_http_v11 as v11
from bridge import diplomacy_lab_http_v12 as v12
from bridge.tests.test_diplomacy_lab_http import SyntheticRuntime
from tools import request_diplomacy_lab_v12 as cli


class ResearchPreflightDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.history = cap.capabilities(research_only=True)

    def test_exact_frozen_v12_history_is_available_only_on_its_own_http_profile(self):
        self.assertTrue(all(a["available"] for a in self.history["artifacts"].values()))
        for module, expected in ((v9,0),(v11,0),(v12,1)):
            runtime = SyntheticRuntime(Path(self.directory.name))
            service = module.ResearchService(runtime,capability_reader=lambda **_:self.history)
            result = service.capabilities()
            self.assertEqual(len(result["historical_preflights"]),expected)
            self.assertIsNone(result["live_readiness"])
            self.assertFalse(result["production"])
            self.assertEqual(runtime.inspections,0)
            self.assertEqual(runtime.calls,0)
            if expected:
                proof = result["historical_preflights"][0]
                self.assertEqual(proof["scope"]["pid"],17676)
                self.assertEqual(proof["scope"]["creation"],"01dd56989186135c")
                self.assertTrue(proof["historical_preflight_passed"])
                self.assertFalse(result["v12_candidate"]["runtime_verified"])
                self.assertEqual(len(proof["action_ids"]),36)
                self.assertEqual(proof["scope"]["request_count"],0)
        self.assertFalse(list(Path(self.directory.name).iterdir()))

    def test_v12_cli_separates_recorded_preflight_from_candidate_and_live_flags(self):
        with patch.object(cap,"capabilities",return_value=self.history), \
             patch.object(cli.lab,"LiveLabProcess") as process,patch.object(cli.lab,"verify_build") as build, \
             patch.object(cli.lab,"publish_research") as publish,contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(cli.main(["capabilities","--research-only"]),0)
        result = json.loads(stdout.getvalue())
        self.assertTrue(result["historical_preflights"][0]["historical_preflight_passed"])
        self.assertFalse(result["v12_candidate"]["runtime_verified"])
        self.assertIsNone(result["v12_live_readiness"])
        self.assertEqual(result["summary"]["actions_with_reviewed_state_effects"],28)
        self.assertEqual(result["summary"]["production_executable_actions"],0)
        process.assert_not_called();build.assert_not_called();publish.assert_not_called()

    def test_http_requires_exact_protocol_purpose_and_unique_canonical_action_list(self):
        edits = [lambda r:r.update(protocol="EU4LAB/1"),lambda r:r.update(purpose="restricted_pair_lab_1375_v11"),
            lambda r:r["action_ids"].append(r["action_ids"][0]),lambda r:r["action_ids"].reverse(),
            lambda r:r["action_ids"].pop()]
        for edit in edits:
            history = deepcopy(self.history);edit(history["historical_preflights"][0])
            runtime = SyntheticRuntime(Path(self.directory.name))
            service = v12.ResearchService(runtime,capability_reader=lambda **_:history)
            self.assertEqual(service.capabilities()["historical_preflights"],[])
            self.assertEqual(runtime.inspections,0)

    def test_http_alias_history_includes_trade_once_and_does_not_invent_support_effects(self):
        runtime=SyntheticRuntime(Path(self.directory.name))
        result=v12.ResearchService(runtime,capability_reader=lambda **_:self.history).capabilities()
        rows={row["action_id"]:row for row in result["history_actions"]}
        self.assertEqual(len(rows),37)
        self.assertNotIn("request_trade_power",rows)
        trade=rows["transfer_trade_power"]["observed_effects"]["experiments"]
        self.assertEqual(len(trade),1)
        self.assertEqual((trade[0]["action_id"],trade[0]["scope"]["sequence"]),("request_trade_power",3))
        self.assertTrue(trade[0]["claims"]["saved_state_verified"] and trade[0]["claims"]["reload_verified"])
        for action in ("cancel_requested_independence_support","cancel_offered_independence_support"):
            self.assertFalse(rows[action]["observed_effects"]["available"])
        self.assertEqual((runtime.inspections,runtime.calls),(0,0))
        self.assertIsNone(result["live_readiness"])
        self.assertFalse(result["production"])

    def test_fixed_http_trade_report_never_proves_effect_by_itself(self):
        root = cap.ROOT / "work/runtime/native1375-v12"
        raw = cap.read_bounded(root/"trade-power-http-submit-17676.json",32768)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),"f894ceebe969036b8018a58214fb1a3ebf2b93ccffae95d70eeb90c962cd7050")
        report = cap.decode_json(raw.decode("utf-8"))
        self.assertEqual([step["http_status"] for step in report["steps"]],[200,202,200,200])
        self.assertTrue(report["server_closed"] and report["server_thread_joined"])
        self.assertFalse(report["effect_verified"] or report["ai_acceptance_verified"] or report["automatic_retry"])
        session = root/"session-17676-01dd56989186135c"
        intent = cap.decode_json(cap.read_bounded(session/"00000000000000000003.http-intent",4096).decode("ascii"))
        host = cap.decode_json(cap.read_bounded(session/"00000000000000000003.host-intent",4096).decode("ascii"))
        claim = cap.read_bounded(session/"00000000000000000003.claim",1024)
        self.assertEqual(intent["request"],report["request"])
        self.assertEqual(intent["request_sha256"],hashlib.sha256(cap.canonical(report["request"]).encode("ascii")).hexdigest())
        self.assertEqual(host["body_ascii"].encode("ascii"),claim)
        self.assertEqual(host["request_sha256"],hashlib.sha256(claim).hexdigest())
        self.assertEqual(host["purpose"],"restricted_pair_lab_1375_v12")
        post, status, replay = [step["response"] for step in report["steps"][1:]]
        for response in (post,status,replay):
            self.assertEqual(response["request_sha256"],host["request_sha256"])
            self.assertFalse(response["production"] or response["applied_verified"])
            self.assertEqual(response["fixed_research_parameters"],{"fraction_milli":500})
        self.assertTrue(post["request_written"])
        self.assertFalse(post["replayed"])
        self.assertTrue(replay["replayed"])
        self.assertFalse(replay["request_written"])
        self.assertEqual(status["native"],replay["native"])
        self.assertEqual(status["state"],"native_completed")
        self.assertEqual(self.history["summary"]["actions_with_reviewed_state_effects"],28)
        self.assertIn("trade-power-http-submit-17676.json",{Path(a["path"]).name for a in self.history["artifacts"].values()})


if __name__ == "__main__":
    unittest.main()
