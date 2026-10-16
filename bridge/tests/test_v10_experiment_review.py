"""Synthetic rejection tests for the fixed interrupted-session reviewer."""
from copy import deepcopy
import hashlib
import unittest

from work import verify_v10_experiment_1375 as review


def pair(submit=True):
    request = dict(pid=review.PID, creation=review.CREATION, sequence=3 if submit else 2,
                   operation="pair", mode="submit" if submit else "legality_only", action="offer_alliance",
                   actor="FRA", target="POR", speed=0)
    final = dict(event="pair_engine_complete", pid=review.PID, process_creation_filetime=review.CREATION,
        thread_id=review.THREAD, world=review.WORLD, actor_handle="0x100007a00415246", target_handle="0x10000bd00524f50",
        fixed_subsidy_amount_milli=0, fixed_subsidy_duration_years=0, status=2 if submit else 1, reason=0, exception=0,
        original_destroyed=True, ownership_uncertain=False, freeze_session=False, applied_verified=False,
        submit_entered=submit, submit_returned=submit, command_destroyed_before_dispatch=not submit,
        preview_called=True, preview_allowed=True, gate_called=True, gate_allowed=True,
        context_submit_return=True if submit else None, caller_container_consumed=True if submit else None)
    names = ["pair_engine_begin", "pair_engine_dispatch_intent", "pair_engine_complete"] if submit else ["pair_engine_begin", "pair_engine_complete"]
    return dict(request=request, records=[dict(final, event=name) for name in names],
                complete={k: final[k] for k in ("status", "reason", "submit_entered", "submit_returned", "ownership_uncertain")})


class V10ReviewTests(unittest.TestCase):
    def terminal(self):
        freeze = dict(event="lab_session_frozen", pid=review.PID, process_creation_filetime=review.CREATION,
                      sequence=12, reason=review.FREEZE_REASON, retry_allowed=False)
        shared = dict(pid=review.PID, creation=review.CREATION, sequence=13, speed=5, retry_allowed=False)
        events = [dict(shared, event="supervisor_armed", deadline_seconds=12.0,
                       before=dict(paused=True, native_speed_index=0, game=int(review.WORLD, 16), raw_date=56457144)),
                  dict(shared, event="supervisor_stopped_disposable_process", stopped=True,
                       reason="Native lab session is frozen; no retry: " + review.FREEZE_REASON)]
        return freeze, events

    def test_abort_evidence_is_valid_but_not_a_completed_request(self):
        freeze, events = self.terminal()
        review.validate_terminal(freeze, events, claim_exists=False, lease_claim_exists=False)
        self.assertEqual(freeze["sequence"], 12)
        self.assertEqual(events[-1]["sequence"], 13)

    def test_claim_or_pause_claim_invalidates_unclaimed_abort(self):
        for claim, pause in ((True, False), (False, True)):
            with self.assertRaises(review.lab.LabError):
                review.validate_terminal(*self.terminal(), claim_exists=claim, lease_claim_exists=pause)

    def test_foreign_process_or_false_termination_cannot_close_session(self):
        for mutation in (lambda e: e[-1].update(creation="01dd568ed7034bcc"),
                         lambda e: e[-1].update(stopped=False), lambda e: e[-1].update(sequence=12),
                         lambda e: e.append(dict(e[-1]))):
            freeze, events = self.terminal(); mutation(events)
            with self.assertRaises(review.lab.LabError):
                review.validate_terminal(freeze, events, claim_exists=False, lease_claim_exists=False)

    def test_reason_is_not_silently_promoted_to_specific_ttl_diagnosis(self):
        freeze, events = self.terminal(); freeze["reason"] = "ttl_expired"
        with self.assertRaises(review.lab.LabError):
            review.validate_terminal(freeze, events, claim_exists=False, lease_claim_exists=False)

    def test_legality_and_submit_have_different_ownership_boundaries(self):
        for submit in (True, False):
            row = pair(submit)
            review.validate_pair(row, "offer_alliance", 3 if submit else 2, submit=submit)
        with self.assertRaises(review.lab.LabError):
            review.validate_pair(pair(False), "offer_alliance", 2, submit=True)

    def test_dispatch_return_without_consumed_container_is_rejected(self):
        row = pair(); row["records"][-1]["caller_container_consumed"] = False
        with self.assertRaises(review.lab.LabError):
            review.validate_pair(row, "offer_alliance", 3, submit=True)

    def test_postdispatch_destructor_unknown_ownership_and_wrong_world_rejected(self):
        for field, value in (("command_destroyed_before_dispatch", True), ("ownership_uncertain", True),
                             ("world", "0x1234"), ("target_handle", "0x10000bc0056414e"),
                             ("fixed_subsidy_amount_milli", 1000), ("exception", 1)):
            row = pair(); row["records"][-1][field] = value
            with self.assertRaises(review.lab.LabError):
                review.validate_pair(row, "offer_alliance", 3, submit=True)

    def test_http_replay_requires_same_result_and_no_second_write(self):
        row = pair()
        request = dict(protocol="EU4LAB/2", pid=review.PID, creation=review.CREATION,
                       sequence=3, mode="submit", action="offer_alliance", actor="FRA", target="POR", ttl_ms=5000)
        intent = dict(kind="eu4_lab_v10_research_http", request=request, manifest_sha256=review.MANIFEST_SHA,
                      automatic_retry=False, request_sha256=hashlib.sha256(review.canonical(request).encode("ascii")).hexdigest())
        host = dict(request_sha256="a" * 64)
        base = dict(pid=review.PID, creation=review.CREATION, purpose=review.lab.PURPOSE, protocol=review.lab.PROTOCOL,
                    research_only=True, production=False, production_backend_registered=False, applied_verified=False,
                    strict_live_single_player_verified=False, world_generation_verified=False,
                    sequence=3, request_sha256=host["request_sha256"])
        completed = dict(base, state="native_completed", native=row, request=row["request"], native_dispatch_verified=True)
        values = [base, dict(base, request_written=True, replayed=False), completed,
                  dict(completed, request_written=False, replayed=True)]
        trace = [("GET", "/research/v10/status", 200), ("POST", "/research/v10/pair", 202),
                 ("GET", "/research/v10/requests/3", 200), ("POST", "/research/v10/pair", 200)]
        report = dict(pid=review.PID, creation=review.CREATION, purpose="v10_real_http_alliance_transport_experiment",
                      token_recorded=False, server_closed=True, automatic_retry=False, production_backend_registered=False,
                      observed_effect=False, request=request, http_events=[dict(method=m, path=p, status=s, response=v)
                          for (m, p, s), v in zip(trace, values)])
        review.validate_http(report, row, intent, host)
        for mutation in (lambda r: r["http_events"][-1]["response"].update(request_written=True),
                         lambda r: r.update(server_closed=False),
                         lambda r: r["request"].update(ttl_ms=6000),
                         lambda r: r["http_events"][-1]["response"].update(native={})): 
            altered = deepcopy(report); mutation(altered)
            with self.assertRaises(review.lab.LabError):
                review.validate_http(altered, row, intent, host)


if __name__ == "__main__":
    unittest.main()
