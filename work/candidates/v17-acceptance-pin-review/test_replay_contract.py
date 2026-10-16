"""Actual-reader regressions against exact native printf and enum contracts."""
from copy import deepcopy
import re
import unittest
import test_integration as integration
from test_candidate import HERE, lab, verify, core


class ReplayContract(unittest.TestCase):
    def test_contract_names_and_ordinals_match_actual_pinned_native_source(self):
        header = (HERE / "native-core/test-acceptance-1375.h").read_text(encoding="utf-8")
        implementation = (HERE / "native-core/test-acceptance-1375.cpp").read_text(encoding="utf-8")
        reason = re.search(r"enum class Reason[^\{]+\{([^}]+)\}", header).group(1)
        stage = re.search(r"enum class Stage[^\{]+\{([^}]+)\}", header).group(1)
        reasons = [v.strip() for v in reason.split(",") if v.strip()]
        stages = [v.strip() for v in stage.split(",") if v.strip()]
        self.assertEqual(reasons.index("already_desired"), verify.ALREADY_DESIRED)
        self.assertEqual(reasons.index("callback_contract"), 12)
        self.assertEqual(stages.index("begin_audit"), verify.BEGIN_STAGE)
        self.assertEqual(stages.index("complete"), verify.COMPLETE_STAGE)
        audit = implementation.split("bool audit(", 1)[1].split("void execute(", 1)[0]
        fields = set(re.findall(r'\\"(\w+)\\":', audit))
        self.assertEqual(fields, verify.CORE_FIELDS)

    def fixture(self):
        t = integration.Integration()
        t.setUp()
        self.addCleanup(t.doCleanups)
        t.full_window()
        return t

    def reject(self, t):
        with self.assertRaises(ValueError):
            t.read()

    def test_each_native_core_key_is_required_and_extra_keys_reject(self):
        t = self.fixture()
        original = deepcopy(t.events)
        for name in ("test_acceptance_begin", "test_acceptance_complete"):
            for key in verify.CORE_FIELDS:
                t.events = deepcopy(original)
                c = next(e["record"] for e in t.events if e.get("record", {}).get("event") == name)
                del c[key]
                with self.subTest(event=name, key=key):
                    self.reject(t)
            t.events = deepcopy(original)
            next(e["record"] for e in t.events if e.get("record", {}).get("event") == name)["unknown"] = True
            self.reject(t)

    def test_begin_every_default_boolean_and_flag_stage_date_is_checked(self):
        t = self.fixture()
        original = deepcopy(t.events)
        first = next(e["record"] for e in original if e.get("record", {}).get("event") == "test_acceptance_begin")
        changes = {k: not first[k] for k in verify.SUCCESS_FIELDS + ("no_native", "freeze_session") + verify.FALSE_PROOFS}
        changes.update(stage=5, reason=1, exception_code=1, after_raw_flag=0, before_raw_flag=1, after_date=1, before_date=-123)
        for key, value in changes.items():
            t.events = deepcopy(original)
            next(e["record"] for e in t.events if e.get("record", {}).get("event") == "test_acceptance_begin")[key] = value
            with self.subTest(key=key):
                self.reject(t)

    def test_each_control_date_is_strict_and_bound_to_same_claim_grant(self):
        t = self.fixture()
        original = deepcopy(t.events)
        for seq in (2, 4):
            for name in ("test_acceptance_begin", "test_acceptance_complete"):
                for key in ("before_date", "after_date"):
                    for value in (-123, True, 56456976.0, 56457000):
                        t.events = deepcopy(original)
                        c = next(e["record"] for e in t.events if e.get("sequence") == seq and e.get("record", {}).get("event") == name)
                        c[key] = value
                        with self.subTest(seq=seq, name=name, key=key, value=value):
                            self.reject(t)

    def test_complete_enum_stage_and_proof_claims_cannot_be_fabricated(self):
        t = self.fixture()
        original = deepcopy(t.events)
        for key, value in [("stage", 14), ("stage", 15.0), ("stage", True), ("reason", 12)] + [(k, True) for k in verify.FALSE_PROOFS]:
            t.events = deepcopy(original)
            for e in t.events:
                if e.get("sequence") == 2 and e.get("record", {}).get("event") == "test_acceptance_complete":
                    e["record"][key] = value
                if e.get("sequence") == 2 and e["event"] == "lab_request_complete" and key in e:
                    e[key] = value
            with self.subTest(key=key):
                self.reject(t)

    def test_each_request_requires_own_unexpired_bounded_native_claim_time(self):
        t = self.fixture()
        original = deepcopy(t.events)
        claims = {e["sequence"]: deepcopy(e) for e in original if e["event"] == "lab_request_claimed"}
        for sequence in (1, 2, 3, 4):
            for delta in (-1, 0, 60001):
                t.events = deepcopy(original)
                for seq, old in claims.items():
                    r = {k: old[k] for k in lab.FIELDS if k != "creation"}
                    r["creation"] = t.f.metadata["process_creation_filetime"]
                    if seq == sequence:
                        r["expires"] = old["claimed_uptime_ms"] + delta
                        next(e for e in t.events if e["event"] == "lab_request_claimed" and e["sequence"] == seq)["expires"] = r["expires"]
                    (t.f.session / f"{seq:020}.claim").write_bytes(lab.encode_request(r))
                with self.subTest(sequence=sequence, delta=delta):
                    self.reject(t)

    def test_closing_frame_keeps_original_grant_identity_before_transition(self):
        t = self.fixture()
        original = deepcopy(t.events)
        for change in ({"raw_date": t.last_frame["raw_date"] + 24}, {"raw_date": float(t.last_frame["raw_date"])},
                       {"world_cookie": "0x200000"}, {"player_handle": "0x010000bd00524f50"},
                       {"thread": float(t.f.metadata["window_thread"])}, {"paused": False}):
            t.events = deepcopy(original)
            t.events[-1].update(change)
            with self.subTest(change=change):
                self.reject(t)

    def test_on_own_expiry_at_durable_pending_boundary_full_pipeline(self):
        t = self.fixture()
        original = deepcopy(t.events)
        pending_time = next(e["uptime_ms"] for e in original if e["event"] == "lab_acceptance_pending")
        for delta in (-1, 0, 1):
            t.events = deepcopy(original)
            claim = next(e for e in t.events if e["event"] == "lab_request_claimed" and e["sequence"] == 2)
            claim["expires"] = pending_time + delta
            # For delta=-1 preserve a strictly earlier valid claim time so this
            # rejects at the newly checked pending boundary, not old claim TTL.
            claim["claimed_uptime_ms"] = pending_time - 2
            record = {k: claim[k] for k in lab.FIELDS if k != "creation"}
            record["creation"] = t.f.metadata["process_creation_filetime"]
            (t.f.session / f"{2:020}.claim").write_bytes(lab.encode_request(record))
            with self.subTest(expires_minus_pending=delta):
                if delta <= 0:
                    with self.assertRaisesRegex(ValueError, "expired before durable pending"):
                        t.read()
                else:
                    result = t.read()
                    self.assertEqual(result["acceptance_window"]["state"], "closed")
                    self.assertEqual(result["last_sequence"], 4)

    def test_duplicate_begin_is_not_an_extra_native_attempt(self):
        t = self.fixture()
        i = next(i for i, e in enumerate(t.events) if e.get("record", {}).get("event") == "test_acceptance_begin")
        t.events.insert(i + 1, deepcopy(t.events[i]))
        self.reject(t)

    def test_native_11_noop_off_accepted_but_callback_contract_12_rejected(self):
        t = integration.Integration()
        t.setUp()
        self.addCleanup(t.doCleanups)
        for seq in (1, 2, 3):
            t.pair(seq)
            t.health(seq, "closed", 0, 0)
        t.control(4, False)
        c = core(False, True)
        c.update(thread_id=t.f.metadata["window_thread"], before_date=t.last_frame["raw_date"], after_date=t.last_frame["raw_date"])
        for e in t.events:
            if e.get("sequence") == 4 and e.get("record", {}).get("event") == "test_acceptance_begin":
                e["record"]["before_raw_flag"] = 0
            if e.get("sequence") == 4 and e.get("record", {}).get("event") == "test_acceptance_complete":
                e["record"] = deepcopy(c)
            if e.get("sequence") == 4 and e["event"] == "lab_request_complete":
                for key in list(e):
                    if key in c and key not in ("event", "operation"):
                        e[key] = c[key]
        t.health(4, "closed", 0, 0)
        result = t.read()
        self.assertEqual(result["acceptance_window"], verify.empty_window())
        for e in t.events:
            if e.get("sequence") == 4 and e.get("record", {}).get("event") == "test_acceptance_complete":
                e["record"]["reason"] = 12
            if e.get("sequence") == 4 and e["event"] == "lab_request_complete":
                e["reason"] = 12
        self.reject(t)


if __name__ == "__main__":
    unittest.main()
