"""Bounded unclaimed-input waiting evidence, without opening a game process."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from bridge.tests import test_diplomacy_lab_v10 as v10_fixture
from work.native import lab_protocol_v11_1375 as lab
from work.native import lab_protocol_v10_1375 as frozen
from tools import verify_diplomacy_lifecycle_v11 as lifecycle
from tools import verify_diplomacy_preview_v11 as preview


def extend_v11_fixture(fixture):
    """Generate a new synthetic 20/72/72 stream; never edits historical evidence."""
    expanded = []
    families = tuple(lifecycle.ACTIONS)[12:]
    lifecycle_template = next(e for e in fixture.events if e['event'] == 'pair_lifecycle')
    for event in fixture.events:
        if event['event'] == 'pair_lifecycle_complete':
            expanded.extend(dict(lifecycle_template, action=name, size=lifecycle.ACTIONS[name]) for name in families)
            event = dict(event, passed=20)
        if event['event'] in ('pair_preview_all_cases_complete', 'pair_command_all_cases_complete'):
            phase = 'pair_preview_case' if event['event'].startswith('pair_preview') else 'pair_command_case'
            originals = [e for e in expanded if e['event'] == phase]
            for target in ('ENG', 'POR'):
                template = next(e for e in originals if e['target'] == target)
                for family in families:
                    for value in ((True,) if family in lifecycle.POSITIVE_ONLY else (True, False)):
                        expanded.append(dict(template, action=family, value=value,
                            mode='positive' if value else 'cancel',
                            case_index=1 + sum(e['event'] == phase for e in expanded)))
            cases = [e for e in expanded if e['event'] == phase]
            accepted = sum(e['allowed'] for e in cases)
            event = dict(event, cases=72, accepted=accepted, rejected=72-accepted)
        expanded.append(event)
    for event in expanded:
        if event['event'] in ('pair_lifecycle', 'pair_preview_case', 'pair_command_case'):
            action = event['action']
            event.update(fixed_subsidy_amount_milli=1000 if action == 'warsubsidy' else 0,
                fixed_subsidy_duration_years=10 if action == 'warsubsidy' else 0,
                fixed_gift_amount_milli=25000 if action == 'giftaction' else 0,
                fixed_transfer_fraction_milli=500 if action == 'transfer_trade_power' else 0,
                fixed_insult_index=-1 if action == 'insultaction' else 0)
    fixture.events = expanded


class InputWaitV11Tests(unittest.TestCase):
    def setUp(self):
        template = v10_fixture.LabV10Tests()
        template.setUp()
        self.addCleanup(template.doCleanups)
        self.f = template.session_fixture()
        extend_v11_fixture(self.f)
        self.f.metadata["purpose"] = lab.PURPOSE
        for name in ("session.json", "install.claim"):
            (self.f.session / name).write_text(json.dumps(self.f.metadata), encoding="utf-8")
        self.enterContext(patch.object(lab, "LiveLabProcess", side_effect=AssertionError("No live process in evidence tests")))
        self.t = self.f.events[-1]["uptime_ms"]

    def wait(self, state="begin", kind="request", **fields):
        result = dict(event="lab_input_wait", wait_state=state, pid=self.f.pid,
            process_creation_filetime=self.f.creation, sequence=0, input_sequence=1 if kind == "request" else 0,
            input_kind=kind, outcome="sharing_violation" if state == "begin" else "opened",
            win32_error=32, uptime_ms=self.t, attempts=1 if state == "begin" else 2, elapsed_ms=0,
            maximum_wait_ms=250, maximum_attempts=16, claim_created=False, native_invoked=False, retry_allowed=False)
        result.update(fields)
        return result

    def read(self, events):
        self.f.events = events
        self.f.write()
        return lab.read_evidence(self.f.session, self.f.metadata)

    def test_v11_scope_and_sources_are_distinct_but_fixture_and_wire_unchanged(self):
        self.assertNotEqual(lab.OUTPUT, frozen.OUTPUT)
        self.assertEqual(len(lab.ACTIONS), 36)
        self.assertTrue(frozen.ACTIONS < lab.ACTIONS)
        self.assertEqual(len(lab.SOURCES), 14)
        self.assertTrue(all("v11" in name for name in lab.SOURCES))
        self.assertEqual(lab.FIXTURE_PROFILE_SHA256, frozen.FIXTURE_PROFILE_SHA256)
        self.assertEqual(lab.encode_request(self.f.record), frozen.encode_request(self.f.record))

    def test_new_modes_roundtrip_without_fabricated_cancel(self):
        for action in lab.ACTIONS - frozen.ACTIONS:
            record = dict(self.f.record, action=action)
            self.assertEqual(lab.decode_request(lab.encode_request(record)), record)
            with self.assertRaises(ValueError):
                frozen.encode_request(record)
        for action in ('revoke_warning', 'cancel_insult', 'cancel_gift', 'cancel_trade_favors_for_gold'):
            with self.assertRaises(ValueError):
                lab.encode_request(dict(self.f.record, action=action))

    def test_twenty_family_matrix_has_seventy_two_modes_and_no_false_positive_only(self):
        result = self.read(self.f.events)
        self.assertEqual(len(result['phase_proofs']['lifecycle']['lifecycle']), 20)
        self.assertEqual(len(preview.EXPECTED), 72)
        self.assertFalse(any(not value and action in lifecycle.POSITIVE_ONLY for action, target, value in preview.EXPECTED))

    def test_fixed_extra_parameters_and_unsupported_cancel_fail_evidence(self):
        original = deepcopy(self.f.events)
        for family, field, bad in (('giftaction', 'fixed_gift_amount_milli', 0),
                                   ('transfer_trade_power', 'fixed_transfer_fraction_milli', 50),
                                   ('insultaction', 'fixed_insult_index', 0)):
            rows = deepcopy(original)
            next(row for row in rows if row['event'] == 'pair_preview_case' and row['action'] == family)[field] = bad
            with self.assertRaises(ValueError):
                self.read(rows)
        rows = deepcopy(original)
        next(row for row in rows if row['event'] == 'pair_preview_case' and row['action'] == 'giftaction').update(value=False, mode='cancel')
        with self.assertRaises(ValueError):
            self.read(rows)

    def test_core_fixed_contract_is_bound_to_each_claimed_id(self):
        prefix = deepcopy(self.f.events)
        for action in ('give_subsidies', 'send_gift', 'request_trade_power', 'cancel_trade_power_transfer', 'insult'):
            request = dict(self.f.record, action=action)
            (self.f.session/'00000000000000000001.claim').write_bytes(lab.encode_request(request))
            rows = deepcopy(prefix)
            rows.append(self.f.bound('lab_request_claimed',
                **{k:v for k,v in request.items() if k not in ('pid','creation','sequence')},
                durable_claim=True,retry_allowed=False))
            subsidy = action == 'give_subsidies'
            core = dict(action_id=action, actor='FRA',target='ENG',pid=self.f.pid,thread_id=self.f.thread,
                process_creation_filetime=self.f.creation,world='0x20000000',raw_date=56456976,status=1,reason=0,
                submit_entered=False,submit_returned=False,ownership_uncertain=False,applied_verified=False,
                freeze_session=False,retry_allowed=False,fixed_subsidy_amount_milli=1000 if subsidy else 0,
                fixed_subsidy_duration_years=10 if subsidy else 0,fixed_gift_amount_milli=25000 if action=='send_gift' else 0,
                fixed_transfer_fraction_milli=500 if 'trade_power' in action else 0,fixed_insult_index=-1 if action=='insult' else 0)
            for event in ('pair_engine_begin','pair_engine_complete'):
                rows.append(self.f.bound('lab_native_record',lease_pause=False,record=dict(core,event=event)))
            rows.append(self.f.bound('lab_request_complete',operation='pair',action=action,status=1,reason=0,
                submit_entered=False,submit_returned=False,ownership_uncertain=False,session_frozen=False,
                applied_verified=False,retry_allowed=False))
            self.assertFalse(self.read(rows)['pending'])
            tampered = deepcopy(rows)
            tampered[-2]['record']['fixed_insult_index'] = 1
            with self.assertRaises(ValueError):
                self.read(tampered)

    def test_wait_prefix_blocks_new_publication_without_claiming_operation(self):
        evidence = self.read(self.f.events + [self.wait()])
        self.assertTrue(evidence["input_wait_pending"])
        self.assertEqual(evidence["requests"], {})
        with self.assertRaisesRegex(ValueError, "awaiting"):
            lab.check_ready(evidence, self.f.live, self.t + 1, operation="pair")

    def test_completed_unclaimed_wait_restores_readiness_without_native_dispatch(self):
        evidence = self.read(self.f.events + [self.wait(), self.wait("end", uptime_ms=self.t+20, elapsed_ms=20)])
        self.assertFalse(evidence["input_wait_pending"])
        self.assertEqual(evidence["last_sequence"], 0)
        self.assertEqual(evidence["requests"], {})
        lab.check_ready(evidence, self.f.live, self.t + 20, operation="pair")

    def test_phase_sharing_wait_is_allowed_before_lifecycle_not_after_completion(self):
        initial = deepcopy(self.f.events)
        pos = next(i for i, row in enumerate(initial) if row["event"] == "pair_selftest_begin")
        phase_time = initial[pos-1]["uptime_ms"]
        old_time = self.t
        self.t = phase_time
        self.read(initial[:pos] + [self.wait(kind="lifecycle"), self.wait("end", kind="lifecycle")] + initial[pos:])
        self.t = old_time
        with self.assertRaises(ValueError):
            self.read(initial + [self.wait(kind="lifecycle")])

    def test_unclosed_phase_wait_cannot_start_engine_phase(self):
        initial = deepcopy(self.f.events)
        pos = next(i for i, row in enumerate(initial) if row["event"] == "pair_selftest_begin")
        self.t = initial[pos-1]["uptime_ms"]
        with self.assertRaisesRegex(ValueError, "Phase invocation"):
            self.read(initial[:pos] + [self.wait(kind="lifecycle")] + initial[pos:])

    def test_opened_wait_cannot_exceed_time_or_attempt_budget(self):
        initial = deepcopy(self.f.events)
        for fields in (dict(elapsed_ms=250, uptime_ms=self.t+250), dict(attempts=17), dict(attempts=1), dict(elapsed_ms=10, uptime_ms=self.t+20)):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.read(initial + [self.wait(), self.wait("end", **fields)])

    def test_failure_outcomes_remain_terminal_and_never_clear_for_new_attempt(self):
        initial = deepcopy(self.f.events)
        for outcome in ("budget_exhausted", "disappeared", "open_error"):
            with self.subTest(outcome=outcome), self.assertRaisesRegex(ValueError, "no retry"):
                self.read(initial + [self.wait(), self.wait("end", outcome=outcome)])

    def test_foreign_or_claimed_or_unbounded_wait_records_fail(self):
        initial = deepcopy(self.f.events)
        for fields in (dict(pid=99), dict(process_creation_filetime="01da000000000000"), dict(sequence=True),
                       dict(input_sequence=2), dict(claim_created=True), dict(native_invoked=True), dict(retry_allowed=True),
                       dict(win32_error=5), dict(maximum_wait_ms=1000), dict(maximum_attempts=100), dict(attempts=0)):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.read(initial + [self.wait(**fields)])

    def test_duplicate_or_orphan_or_reversed_wait_boundary_fails(self):
        initial = deepcopy(self.f.events)
        for suffix in ([self.wait("end")], [self.wait(), self.wait()],
                       [self.wait(), self.wait("end", input_kind="preview", input_sequence=0)],
                       [self.wait(), self.wait("end", uptime_ms=self.t-1)]):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                self.read(initial + suffix)

    def test_input_failure_preserves_stage_error_and_claim_status_in_terminal_error(self):
        row = dict(event="lab_input_failed", pid=self.f.pid, process_creation_filetime=self.f.creation,
            sequence=0, input_sequence=1, input_kind="request", stage="claim_flush", win32_error=112,
            close_win32_error=0, uptime_ms=self.t, expires=6400, bytes=144, attempts=1,
            claim_created=True, claim_flushed=False, request_deleted=False, native_invoked=False, retry_allowed=False)
        with self.assertRaisesRegex(ValueError, "claim_flush; win32_error=112; claim_created=True"):
            self.read(self.f.events + [row])

    def test_no_new_claim_can_bypass_unclosed_wait(self):
        self.f.claim()
        row = self.f.events.pop()
        with self.assertRaisesRegex(ValueError, "Mailbox operation"):
            self.read(self.f.events + [self.wait(), row])

    def test_frame_cannot_regress_after_a_later_input_diagnostic(self):
        frame = dict(self.f.events[-1], frames=self.f.events[-1]["frames"]+1, uptime_ms=self.t+1)
        with self.assertRaises(ValueError):
            self.read(self.f.events + [self.wait(), self.wait("end", uptime_ms=self.t+20, elapsed_ms=20), frame])

    def test_completed_phase_cannot_wait_again_before_its_proof_heartbeat(self):
        initial = deepcopy(self.f.events)
        pos = next(i for i, row in enumerate(initial) if row["event"] == "pair_selftest_complete") + 1
        self.t = max(row.get("uptime_ms", 0) for row in initial[:pos])
        with self.assertRaises(ValueError):
            self.read(initial[:pos] + [self.wait(kind="lifecycle")] + initial[pos:])


if __name__ == "__main__":
    unittest.main()
