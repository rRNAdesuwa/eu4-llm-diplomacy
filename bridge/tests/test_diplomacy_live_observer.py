"""Synthetic composition and local HTTP only; never opens a game process."""
from copy import deepcopy
import http.client
import json
from pathlib import Path
import struct
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bridge import diplomacy_live_observer as live
from bridge.tests.test_knowledge_effect_reader_v2 import graph, capture
from bridge.tests.test_knowledge_effect_reader import (receipt,
    BASE, ARRAY, FRA, JOL, FRA_ADDRESS, JOL_ADDRESS, IDENTITY)

SOURCE_PINS = {"bridge/diplomacy_live_observer_manifest_1375.json": {"bytes": 1, "sha256": "c"*64}}
COMMAND = {"request_id": "new-knowledge-test", "action": "knowledge_sharing", "actor": "FRA", "target": "JOL"}


def full_capture(command, active=False):
    state = capture(graph(active), command["action"])
    return dict(schema="EU4DIPLOMACY-KNOWLEDGE-CAPTURE/1", identity=deepcopy(IDENTITY),
        command=deepcopy(command), game_sha256=live.GAME_SHA, state=state,
        source_pins=deepcopy(SOURCE_PINS), duration_ms=1.5, rpm_budget={"calls": 64, "bytes": 2048})


class CaptureFactory:
    def __init__(self):
        self.active = False
        self.calls = self.closed = 0
        self.error = self.on_capture = self.mutate = None

    def __call__(self, identity, backend, **options):
        factory = self
        self.calls += 1
        self.options = options

        class Context:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                factory.closed += 1

            def capture_knowledge(self, command, binding=None):
                if factory.error:
                    raise factory.error
                if factory.on_capture:
                    factory.on_capture()
                value = full_capture(command, factory.active)
                if factory.mutate:
                    factory.mutate(value)
                return value

        return Context()


class LiveCompositionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.temp = Path(temporary.name)
        self.session = self.temp / "native-session"
        self.session.mkdir()
        self.store = self.temp / "observations"
        self.command = deepcopy(COMMAND)
        self.receipt = receipt()
        self.receipt.update(command=deepcopy(self.command), audit_sha256="a"*64, terminal=False,
            gameplay_effects_verified=False)
        self.original = dict(schema="EU4DIPLOMACY-OBSERVATION/1", request_id=COMMAND["request_id"],
            identity=deepcopy(IDENTITY), command=deepcopy(self.command), transport_state="dispatched",
            audit_sha256="a"*64, completion_state="evidence_insufficient", request_state="unknown",
            native_calls=0, requests_published=0, memory_written=False, saves_written=0,
            AI_acceptance_verified=False, automatic_command_retry=False, persistence_verified=False,
            effect={"status": "unknown", "selected_effect_verified": False, "diagnostic_count": 0})
        self.factory = CaptureFactory()
        self.backend = SimpleNamespace(manifest_path=Path("unused-offline.json"),
            actions=("knowledge_sharing", "ask_knowledge_sharing", "ask_for_march", "annex_vassal"),
            session=lambda identity: self.session,
            key_path=lambda session, request_id: session / ("key-"+live.digest(request_id.encode("ascii"))+".json"))
        self.observer = live.LiveDiplomacyObserver(IDENTITY, backend=self.backend, store=self.store,
            knowledge_capture_factory=self.factory, allow_tag_host=True)
        patchers = [patch.object(live, "live_source_pins", return_value=deepcopy(SOURCE_PINS)),
            patch.object(live, "recorded_snapshot", side_effect=lambda *a: SimpleNamespace(status=lambda rid: deepcopy(self.receipt))),
            patch.object(live.ReplyAwareEffectObserver, "observe", side_effect=lambda *a, **k: deepcopy(self.original))]
        for item in patchers:
            self.last_mock = item.start()
            self.addCleanup(item.stop)

    def prepare(self):
        return self.observer.prepare(self.command)

    def observe(self, **kwargs):
        return self.observer.observe(self.command["request_id"], **kwargs)

    def baseline_path(self):
        return self.observer.directory(self.command["request_id"]) / "knowledge-baseline.json"

    def test_prepare_is_exact_absent_and_immutable_without_native_reservation(self):
        result = self.prepare()
        self.assertEqual(result["pair_status"], "pair_absent_observed")
        raw = self.baseline_path().read_bytes()
        before = json.loads(raw)
        self.assertEqual(before["capture"]["state"]["snapshot"]["provider"]["handle"], hex(FRA))
        self.assertFalse(before["provenance"]["atomic_publication_lock_held"])
        self.assertEqual(list(self.session.iterdir()), [])
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.prepare()
        self.assertEqual(self.baseline_path().read_bytes(), raw)
        self.assertEqual((self.factory.calls, self.factory.closed), (1, 1))
        self.assertTrue(self.factory.options["allow_tag_host"])

    def test_existing_reservation_or_lock_refuses_before_capture(self):
        for path in (self.session/"publisher.lock", self.backend.key_path(self.session, self.command["request_id"])):
            with self.subTest(path=path.name):
                path.touch()
                with self.assertRaisesRegex(ValueError, "reserved or publisher locked"):
                    self.prepare()
                path.unlink()
        self.assertEqual(self.factory.calls, 0)
        self.assertFalse(self.baseline_path().exists())

    def test_publication_during_capture_cannot_create_baseline(self):
        self.factory.on_capture = lambda: (self.session/"publisher.lock").touch()
        with self.assertRaisesRegex(ValueError, "Publication started during capture"):
            self.prepare()
        self.assertFalse(self.baseline_path().exists())
        self.assertTrue((self.session/"publisher.lock").exists())

    def test_already_active_or_unknown_state_cannot_be_preparation(self):
        self.factory.active = True
        with self.assertRaisesRegex(ValueError, "absent exact pair"):
            self.prepare()
        self.assertFalse(self.baseline_path().exists())
        self.factory.active = False
        self.factory.mutate = lambda c: c["state"].update(status="unknown")
        with self.assertRaisesRegex(ValueError, "projection differs"):
            self.prepare()

    def test_changed_tag_direction_or_non_equal_passes_are_refused(self):
        for mutate in (lambda c: c["state"]["snapshot"]["pair"].update(actor_tag="ENG"),
                       lambda c: c["state"].update(two_pass_equal=False)):
            with self.subTest(mutate=mutate):
                self.factory.mutate = mutate
                with self.assertRaises(ValueError):
                    self.prepare()
                self.assertFalse(self.baseline_path().exists())

    def test_new_exact_pair_with_full_receipt_is_observed_but_not_institution_completion(self):
        self.prepare()
        baseline = self.baseline_path().read_bytes()
        self.factory.active = True
        result = self.observe()
        self.assertTrue(result["effect"]["selected_effect_verified"])
        self.assertEqual(result["effect"]["completion_stage"], "active_sharing_pair_observed")
        self.assertEqual(result["completion_state"], "selected_effect_observed")
        self.assertEqual(result["native_receipt"], self.receipt)
        self.assertFalse(result["effect"]["native_known_cleanup_complete"])
        self.assertFalse(result["effect"]["institution_completion_verified"])
        self.assertFalse(result["effect"]["AI_acceptance_verified"])
        self.assertFalse(result["effect"]["world_epoch_proven"])
        self.assertEqual(result["supplement"]["r1_knowledge_effect"], self.original["effect"])
        self.assertTrue(Path(result["record"]).exists())
        self.assertTrue(Path(result["knowledge"]["capture_record"]["path"]).exists())
        self.assertNotIn("passes", result["knowledge"])
        self.assertLess(len(json.dumps(result).encode("ascii")), 256*1024)
        self.assertEqual(self.baseline_path().read_bytes(), baseline)

    def test_absent_after_is_not_observed_despite_native_dispatch(self):
        self.prepare()
        result = self.observe(record=False)
        self.assertEqual(result["effect"]["status"], "not_observed")
        self.assertEqual(result["transport_state"], "dispatched")
        self.assertFalse(result["effect"]["selected_effect_verified"])

    def test_no_baseline_never_uses_count_diagnostic_as_effect(self):
        self.factory.active = True
        self.original["effect"].update(status="observed", selected_effect_verified=True, diagnostic_count=1)
        result = self.observe(record=False)
        self.assertEqual(result["effect"]["status"], "unknown")
        self.assertEqual(result["transport_state"], "dispatched")
        self.assertEqual(self.factory.calls, 0)
        self.assertFalse(self.store.exists())

    def test_record_false_writes_nothing_and_capture_failure_preserves_dispatch(self):
        self.prepare()
        before = {p: p.read_bytes() for p in self.store.rglob("*") if p.is_file()}
        self.factory.error = OSError("Synthetic VM_READ unavailable")
        result = self.observe(record=False)
        self.assertEqual(result["transport_state"], "dispatched")
        self.assertEqual(result["native_receipt"], self.receipt)
        self.assertEqual(result["effect"]["status"], "unknown")
        self.assertFalse(result["effect"]["automatic_command_retry"])
        self.assertEqual(before, {p: p.read_bytes() for p in self.store.rglob("*") if p.is_file()})
        self.assertEqual(self.factory.closed, self.factory.calls)

    def test_wrong_receipt_handle_or_unclosed_ownership_never_passes(self):
        self.prepare()
        self.factory.active = True
        for alter in (lambda r: r["binding"].update(actor_handle=FRA+(1<<56)),
                      lambda r: r["native_result"].update(ownership_closed=False)):
            with self.subTest(alter=alter):
                original = deepcopy(self.receipt)
                alter(self.receipt)
                result = self.observe(record=False)
                self.assertEqual(result["effect"]["status"], "unknown")
                self.assertEqual(result["transport_state"], "dispatched")
                self.receipt = original

    def test_bad_source_or_baseline_command_preserves_receipt_without_capture(self):
        self.prepare()
        original = self.baseline_path().read_text()
        for key, value in (("source_manifest_sha256", "d"*64), ("command", {**self.command, "request_id": "different"})):
            with self.subTest(key=key):
                baseline = json.loads(original)
                baseline[key] = value
                self.baseline_path().write_text(json.dumps(baseline))
                result = self.observe(record=False)
                self.assertEqual(result["effect"]["status"], "unknown")
                self.assertEqual(result["native_receipt"], self.receipt)
        self.assertEqual(self.factory.calls, 1)

    def test_source_change_during_capture_does_not_become_success(self):
        self.prepare()
        self.factory.active = True
        self.factory.mutate = lambda c: c.update(source_pins={})
        result = self.observe(record=False)
        self.assertEqual(result["effect"]["status"], "unknown")
        self.assertEqual(result["transport_state"], "dispatched")

    def test_invalid_live_source_prevents_all_capture_and_retains_dispatch(self):
        with patch.object(live, "live_source_pins", side_effect=ValueError("Synthetic bad source")):
            result = self.observe(record=False)
        self.assertEqual(result["effect"]["status"], "unknown")
        self.assertEqual(result["native_receipt"], self.receipt)
        self.assertEqual(self.factory.calls, 0)
        self.last_mock.assert_not_called()
        self.assertFalse(self.store.exists())

    def test_receipt_change_during_capture_preserves_original_receipt_but_effect_unknown(self):
        self.prepare()
        original = deepcopy(self.receipt)
        self.factory.active = True
        self.factory.on_capture = lambda: self.receipt.update(audit_sha256="b"*64)
        result = self.observe(record=False)
        self.assertEqual(result["native_receipt"], original)
        self.assertEqual(result["effect"]["status"], "unknown")
        self.assertIn("Recorded dispatch changed", result["effect"]["failure"]["message"])

    def test_frozen_diagnostic_failure_keeps_transport_and_can_use_independent_pair_proof(self):
        self.prepare()
        self.factory.active = True
        self.last_mock.side_effect = ValueError("Synthetic invalid old count baseline")
        result = self.observe(record=False)
        self.assertEqual(result["transport_state"], "dispatched")
        self.assertEqual(result["supplement"]["r1_knowledge_effect"]["status"], "unknown")
        self.assertTrue(result["effect"]["selected_effect_verified"])

    def test_ask_uses_target_as_provider_and_original_actor_as_recipient(self):
        self.command.update(action="ask_knowledge_sharing", actor="JOL", target="FRA")
        self.receipt = receipt("ask_knowledge_sharing")
        self.receipt.update(command=deepcopy(self.command), audit_sha256="a"*64)
        self.original["command"] = deepcopy(self.command)
        self.prepare()
        self.factory.active = True
        result = self.observe(record=False)
        self.assertTrue(result["effect"]["selected_effect_verified"])
        self.assertEqual(result["knowledge"]["selected"]["provider"]["tag"], "FRA")
        self.assertEqual(result["knowledge"]["selected"]["recipient"]["tag"], "JOL")

    def test_nonknowledge_delegates_to_frozen_r2(self):
        self.receipt["command"]["action"] = "ask_for_march"
        self.original.update(request_state="waiting_for_recipient", completion_state="waiting_for_recipient")
        result = self.observe(record=False)
        self.assertEqual(result, self.original)
        self.assertEqual(self.factory.calls, 0)
        self.last_mock.assert_called_once_with(self.command["request_id"], record=False)

    def test_cli_reports_active_task_and_preserves_pending_exit_contract(self):
        from tools import observe_diplomacy_live as cli
        self.prepare()
        self.factory.active = True
        result = self.observe(record=False)
        summary = cli.compact(result)
        self.assertEqual(cli.result_code(result), 0)
        self.assertEqual(summary["knowledge_pair_status"], "active_pair_observed")
        self.assertEqual(summary["knowledge_provider"]["handle"], hex(FRA))
        self.assertFalse(summary["institution_completion_verified"])
        self.assertEqual(cli.result_code({"request_state": "waiting_for_recipient"}), 3)
        self.assertEqual(cli.result_code({"transport_state": "dispatched"}), 2)


class HeldCaptureCompositionTests(unittest.TestCase):
    def capture_with_fake_port(self, *, bind=False, research=None):
        m = graph(False)
        m.put(ARRAY, bytes(1380*8))
        m.q(ARRAY+122*8, FRA_ADDRESS)
        m.q(ARRAY+210*8, JOL_ADDRESS)
        backend = SimpleNamespace(actions=("knowledge_sharing", "ask_knowledge_sharing"),
            build=Path("fixed-build"), manifest={"DLL": "eu4_tag_command_1375_v31.dll", "PE_timestamp": 7, "SizeOfImage": 8})
        reader = live.KnowledgeRuntimeCapture(IDENTITY, backend)
        reader.modules = [(BASE, "eu4.exe")] + ([] if research is None else [(0x5000000, research)])
        reader.base = BASE
        reader.held = SimpleNamespace(identity_check=lambda: None, modules=lambda: reader.modules,
            injector=SimpleNamespace(_canonical=lambda p: str(p).lower()))
        reader.initial_pins = {}
        reader.live_initial_pins = deepcopy(SOURCE_PINS)
        with patch.object(live, "HeldRPMPort", return_value=m), patch.object(live, "observer_pins", return_value={}), \
             patch.object(live, "live_source_pins", return_value=deepcopy(SOURCE_PINS)):
            result = reader.capture_knowledge(COMMAND, {"actor_handle": FRA, "target_handle": JOL} if bind else None)
        return result

    def test_selected_tag_discovery_and_both_passes_share_one_outer_budget(self):
        result = self.capture_with_fake_port()
        self.assertEqual(result["state"]["status"], "pair_absent_observed")
        self.assertGreater(result["rpm_budget"]["calls"], result["state"]["read_budget"]["calls"])
        self.assertLessEqual(result["rpm_budget"]["bytes"], 512*1024)
        live.checked_capture(result, COMMAND, IDENTITY)

    def test_after_dispatch_uses_full_bound_handles_without_tag_scan(self):
        before = self.capture_with_fake_port()
        after = self.capture_with_fake_port(bind=True)
        self.assertEqual(before["state"], after["state"])
        self.assertLess(after["rpm_budget"]["calls"], before["rpm_budget"]["calls"])

    def test_unexpected_research_dll_is_refused_before_pair_reads(self):
        with self.assertRaisesRegex(ValueError, "Unexpected research module"):
            self.capture_with_fake_port(research="eu4_bridge_unknown.dll")


class LiveSourceAndHttpTests(unittest.TestCase):
    def test_frozen_dependency_graph_is_checked_without_runtime(self):
        with patch.object(live, "KnowledgeRuntimeCapture", side_effect=AssertionError("No process permitted")):
            pins = live.live_source_pins()
            self.assertIn("bridge/knowledge_effect_reader_v2_manifest_1375.json", pins)

    def test_changed_new_module_is_refused(self):
        original = live.read

        def altered(path, limit):
            return b"changed" if Path(path) == live.ROOT/"bridge/diplomacy_live_observer.py" else original(path, limit)

        with patch.object(live, "read", side_effect=altered):
            with self.assertRaisesRegex(ValueError, "Live source changed"):
                live.live_source_pins()

    def test_catalog_overrides_only_new_knowledge_support_without_runtime(self):
        with patch.object(live, "live_source_pins", return_value=deepcopy(SOURCE_PINS)):
            catalog = live.live_catalog()
        knowledge = [r for r in catalog["profiles"] if r["action"] in live.KNOWLEDGE_ACTIONS]
        self.assertEqual(len(knowledge), 2)
        self.assertTrue(all(r["completion_stage"] == "active_sharing_pair_observed" for r in knowledge))
        self.assertFalse(catalog["all120_effect_profiles_complete"])

    def test_live_http_catalog_uses_r1_auth_and_write_refusal(self):
        observer = SimpleNamespace(observe=lambda rid: {"transport_state": "dispatched", "effect": {"status": "unknown"}})
        token = "offline-live-token-0123456789"
        with patch.object(live, "live_source_pins", return_value=deepcopy(SOURCE_PINS)):
            server = live.make_live_server(observer, port=0, token=token)
            worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
            worker.start()
            try:
                for method, path, headers, expected in (
                    ("GET", "/observer/v1/capabilities", {}, 403),
                    ("GET", "/observer/v1/capabilities", {"Authorization": "Bearer "+token, "Origin": "http://other"}, 403),
                    ("GET", "/observer/v1/capabilities", {"Authorization": "Bearer "+token}, 200),
                    ("GET", "/observer/v1/capabilities?bad=1", {"Authorization": "Bearer "+token}, 422),
                    ("POST", "/observer/v1/prepare", {"Authorization": "Bearer "+token}, 405)):
                    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                    try:
                        connection.request(method, path, headers=headers)
                        response = connection.getresponse()
                        payload = json.loads(response.read())
                        self.assertEqual(response.status, expected)
                        if response.status == 200:
                            self.assertEqual(payload["knowledge_pair_profiles"], list(live.KNOWLEDGE_ACTIONS))
                    finally:
                        connection.close()
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=3)
                self.assertFalse(worker.is_alive())


if __name__ == "__main__":
    unittest.main()
