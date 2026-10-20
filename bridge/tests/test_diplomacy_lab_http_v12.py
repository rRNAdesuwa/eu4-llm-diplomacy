"""Offline v12 adapter isolation: synthetic mailbox only; never starts a server."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from bridge import diplomacy_lab_http as old
from bridge import diplomacy_lab_http_v12 as http
from bridge.tests.test_diplomacy_lab_http import SyntheticRuntime, fake_history
from work.native import lab_protocol_v9_1375 as v9
from work.native import lab_protocol_v12_1375 as v12
from bridge import diplomacy_lab_http_v10 as v10_http


class SyntheticV12Runtime(SyntheticRuntime):
    protocol = v12

    def publish(self, snapshot, request):
        self.calls += 1
        if self.failure:
            raise OSError("Synthetic v12 publication interruption")
        return v12.publish_research(snapshot["session"], snapshot["metadata"], snapshot["manifest_sha256"],
            snapshot["evidence"], snapshot["live"], sequence=request["sequence"], operation="pair",
            mode=request["mode"], action=request["action"], actor=request["actor"], target=request["target"],
            ttl_ms=request["ttl_ms"], clock=lambda: snapshot["now"])


class V12HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.session = Path(self.temp.name)
        self.enterContext(patch.object(v12, "_private_root", lambda _: None))
        self.v9live = self.enterContext(patch.object(v9, "LiveLabProcess", side_effect=AssertionError("No process access")))
        self.v12live = self.enterContext(patch.object(v12, "LiveLabProcess", side_effect=AssertionError("No process access")))
        self.runtime = SyntheticV12Runtime(self.session)
        self.service = http.ResearchService(self.runtime, capability_reader=fake_history)
        self.request = {"protocol": "EU4LAB/2", "pid": self.runtime.pid, "creation": self.runtime.creation,
                        "sequence": 1, "mode": "legality_only", "action": "give_subsidies", "actor": "FRA",
                        "target": "NAV", "ttl_ms": 5000}

    def post(self, **changes):
        return self.service.dispatch("POST", http.PREFIX + "/pair", self.request | changes)

    def test_candidate_discovery_is_36_but_historical_effects_stay_separate(self):
        status, value = self.service.dispatch("GET", http.PREFIX + "/capabilities")
        self.assertEqual(status, 200)
        self.assertEqual(len(value["http_pair_contract"]["actions"]), 36)
        self.assertEqual(set(value["http_pair_contract"]["actions"]), set(v12.ACTIONS))
        self.assertEqual(len(value["history_actions"]), 10)
        self.assertFalse(value["v12_candidate"]["runtime_verified"])
        self.assertFalse(value["production"])
        self.assertIsNone(value["live_readiness"])
        self.assertEqual(value["purpose"], v12.PURPOSE)
        self.assertEqual(value["http_pair_contract"]["fixed_research_parameters"]["give_subsidies"],
                         {"monthly_amount": "1.000", "duration_years": 10})
        value["http_pair_contract"]["fixed_research_parameters"]["give_subsidies"]["duration_years"] = 999
        self.assertEqual(v12.FIXED_RESEARCH_PARAMETERS["give_subsidies"]["duration_years"], 10)
        self.assertEqual(self.runtime.inspections, 0)
        self.v9live.assert_not_called()
        self.v12live.assert_not_called()

    def test_all_36_actions_both_modes_compile_only_fixed_v12_wire(self):
        for action in sorted(v12.ACTIONS):
            for mode in ("legality_only", "submit"):
                with self.subTest(action=action, mode=mode), tempfile.TemporaryDirectory() as directory:
                    runtime = SyntheticV12Runtime(directory)
                    service = http.ResearchService(runtime, capability_reader=fake_history)
                    status, value = service.dispatch("POST", http.PREFIX + "/pair", self.request | {"action": action, "mode": mode})
                    self.assertEqual(status, 202, value)
                    self.assertEqual(value["purpose"], v12.PURPOSE)
                    record = v12.decode_request((Path(directory) / "00000000000000000001.request").read_bytes())
                    self.assertEqual(set(record), set(v12.FIELDS))
                    self.assertEqual(record["action"], action)
                    self.assertEqual(record["mode"], mode)
                    self.assertEqual(value["fixed_research_parameters"], v12.FIXED_RESEARCH_PARAMETERS.get(action, {}))
                    self.assertFalse(value["native_dispatch_verified"])
                    intent = json.loads((Path(directory) / "00000000000000000001.host-intent").read_text())
                    self.assertEqual(intent["purpose"], v12.PURPOSE)

    def test_no_raw_subsidy_parameter_even_if_it_matches_fixed_value(self):
        for field, value in (("monthly_amount", "1.000"), ("amount_milli", 1000), ("duration_years", 10),
                             ("duration_months", 120), ("parameters", {}), ("fixed_subsidy_amount_milli", 1000)):
            status, result = self.post(**{field: value})
            self.assertEqual(status, 422)
            self.assertEqual(result["purpose"], v12.PURPOSE)
        self.assertEqual(self.runtime.inspections, 0)
        self.assertFalse(list(self.session.iterdir()))

    def test_gift_trade_and_insult_fixed_values_are_disclosed_but_never_accepted_as_input(self):
        contract=self.service.capabilities()["http_pair_contract"]["fixed_research_parameters"]
        self.assertEqual(contract["send_gift"], {"amount":"25.000"})
        self.assertEqual(contract["request_trade_power"], {"fraction_milli":500})
        self.assertEqual(contract["cancel_trade_power_transfer"], {"fraction_milli":500})
        self.assertEqual(contract["insult"], {"index":-1})
        for action, field, value in (("send_gift","amount","25.000"), ("send_gift","amount_milli",25000),
                                     ("request_trade_power","fraction_milli",500), ("insult","index",-1),
                                     ("trade_favors_for_gold","amount",1)):
            self.assertEqual(self.post(action=action, **{field:value})[0],422)
        self.assertEqual(self.runtime.inspections,0)
        self.assertFalse(list(self.session.iterdir()))

    def test_v10_service_cannot_accept_v12_runtime_or_new_actions(self):
        with self.assertRaises(old.ResearchError):
            v10_http.ResearchService(self.runtime)
        self.assertEqual(self.service.dispatch("POST","/research/v10/pair",self.request)[0],404)

    def test_unclaimed_input_wait_blocks_new_intent_without_claim_or_retry(self):
        self.runtime.snapshot["evidence"]["input_wait_pending"]=True
        self.assertEqual(self.post(action="send_gift")[0],409)
        status=self.service.status()
        self.assertFalse(status["pair_publication_ready"])
        self.assertTrue(status["input_wait_pending"])
        self.assertEqual(self.runtime.calls,0)
        self.assertFalse(list(self.session.iterdir()))

    def test_shared_v10_history_does_not_expand_v9_and_v12_keeps_candidate_separate(self):
        from bridge.diplomacy_research_capabilities import V10_ADDITIONAL_ACTIONS
        def expanded_history(**kwargs):
            value=fake_history(**kwargs)
            value["actions"] += [{"action_id":name} for name in sorted(V10_ADDITIONAL_ACTIONS)]
            return value
        v9_service=old.ResearchService(SyntheticRuntime(self.session),capability_reader=expanded_history)
        v12_service=http.ResearchService(self.runtime,capability_reader=expanded_history)
        self.assertEqual(len(v9_service.capabilities()["history_actions"]),10)
        self.assertEqual(len(v9_service.capabilities()["http_pair_contract"]["actions"]),10)
        described=v12_service.capabilities()
        self.assertEqual(len(described["history_actions"]),24)
        self.assertEqual(len(described["http_pair_contract"]["actions"]),36)
        self.assertFalse(described["v12_candidate"]["runtime_verified"])
        self.assertEqual(self.runtime.inspections,0)

    def test_v9_and_v12_routes_and_runtime_dependencies_are_isolated(self):
        old_runtime = SyntheticRuntime(self.session)
        service9 = old.ResearchService(old_runtime, capability_reader=fake_history)
        self.assertEqual(service9.dispatch("POST", old.PREFIX + "/pair", self.request)[0], 422)
        self.assertEqual(service9.dispatch("POST", http.PREFIX + "/pair", self.request)[0], 404)
        self.assertEqual(self.service.dispatch("POST", old.PREFIX + "/pair", self.request)[0], 404)
        self.assertEqual(self.post()[0], 202)
        self.assertEqual(old_runtime.calls, 0)
        with self.assertRaises(old.ResearchError):
            old.ResearchService(self.runtime)
        with self.assertRaises(old.ResearchError):
            http.ResearchService(old.V9ResearchRuntime(self.runtime.pid, self.runtime.creation))

    def test_fixture_speed_stage_load_and_other_versions_not_routed(self):
        for route in ("fixture", "speed", "stage", "load", "reset", "v1/requests"):
            self.assertEqual(self.service.dispatch("POST", http.PREFIX + "/" + route, self.request)[0], 404)
        self.assertEqual(self.post(protocol="EU4LAB/1")[0], 422)
        self.assertEqual(self.post(protocol="EU4PAIR/1")[0], 422)
        self.assertEqual(self.post(actor="ENG", mode="submit")[0], 422)
        self.assertEqual(self.post(target="RUS")[0], 422)
        self.assertEqual(self.runtime.inspections, 0)

    def test_restart_replay_conflict_and_intent_kind_remain_v12_bound(self):
        self.assertEqual(self.post()[0], 202)
        self.service = http.ResearchService(self.runtime, capability_reader=fake_history)
        result = self.post()[1]
        self.assertTrue(result["replayed"])
        self.assertFalse(result["request_written"])
        self.assertEqual(result["fixed_research_parameters"], {"monthly_amount": "1.000", "duration_years": 10})
        self.assertEqual(self.post(ttl_ms=6000)[0], 409)
        intent = self.session / "00000000000000000001.http-intent"
        value = json.loads(intent.read_text())
        self.assertEqual(value["kind"], "eu4_lab_v12_research_http")
        value["kind"] = old.HTTP_KIND
        intent.write_text(json.dumps(value))
        self.assertEqual(self.post()[0], 409)
        self.assertEqual(self.runtime.calls, 1)

    def test_unknown_v12_publication_has_durable_hold_and_no_next_sequence(self):
        self.runtime.failure = True
        self.assertEqual(self.post()[0], 502)
        self.runtime.failure = False
        self.assertEqual(self.post()[1]["state"], "publication_unknown")
        self.assertEqual(self.post(sequence=2)[0], 409)
        self.assertFalse(self.service.status()["pair_publication_ready"])
        self.assertEqual(self.runtime.calls, 1)

    def test_pause_and_pending_lease_guard_blocks_v12_new_actions_before_intent(self):
        frame = self.runtime.snapshot["evidence"]["latest_frame"]
        frame["paused"] = False
        self.assertEqual(self.post()[0], 409)
        frame["paused"] = True
        frame["lease_active"] = True
        self.assertEqual(self.post()[0], 409)
        self.assertFalse(list(self.session.iterdir()))

    def test_v12_runtime_calls_only_v12_build_session_fixture_and_live_guards(self):
        process = Mock()
        process.__enter__ = Mock(return_value=process)
        process.__exit__ = Mock(return_value=False)
        process.snapshot.return_value = deepcopy(self.runtime.snapshot["live"])
        with patch.object(v12, "LiveLabProcess", return_value=process) as opened, \
             patch.object(v9, "verify_build", side_effect=AssertionError("v9 dependency selected")) as wrong, \
             patch.object(v12, "verify_build", return_value=({"dll_sha256": "B" * 64, "running_speed_enabled": True}, "a" * 64)), \
             patch.object(v12, "session_path", return_value=self.session) as path, \
             patch.object(v12, "read_session_metadata", return_value=self.runtime.snapshot["metadata"]), \
             patch.object(v12, "read_evidence", return_value=self.runtime.snapshot["evidence"]), \
             patch.object(v12, "verify_installed_fixture", return_value={"disk_only": True}) as fixture, \
             patch.object(v12, "uptime_ms", return_value=3000):
            runtime = http.V12ResearchRuntime(self.runtime.pid, self.runtime.creation)
            runtime.inspect()
            path.assert_called_once_with(v12.OUTPUT, self.runtime.pid, self.runtime.creation)
            opened.assert_called_once_with(self.runtime.pid, expected_creation=self.runtime.creation)
            fixture.assert_called_once()
            wrong.assert_not_called()

    def test_v12_bind_rejects_v9_service_and_invalid_token_before_socket(self):
        with patch.object(old, "BoundedResearchServer") as server:
            with self.assertRaises(old.ResearchError):
                http.make_server(old.ResearchService(SyntheticRuntime(self.session)), token="a" * 32)
            with self.assertRaises(old.ResearchError):
                http.make_server(self.service, token=None)
            server.assert_not_called()


if __name__ == "__main__":
    unittest.main()
