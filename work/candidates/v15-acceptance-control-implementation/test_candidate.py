"""Actual candidate Python codec/replay/publisher tests; no native build/game."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE / "files"))
from work.native import lab_protocol_v15_1375 as lab
from tools import verify_diplomacy_acceptance_v15 as verify

META = {"pid": 1234, "process_creation_filetime": "01dd000000000001", "window_thread": 987}
ACTION, TARGET = "offer_fleet_basing_rights", "POR"


def request(seq=2, action="accept_on", **kw):
    r = dict(pid=1234, creation=META["process_creation_filetime"], sequence=seq, expires=60000,
             operation="accept", mode="submit", action=action, actor="FRA", target="FRA", speed=0,
             bound_action=ACTION, bound_target=TARGET, bound_submit_sequence=3)
    r.update(kw)
    return r


def pair(seq=3, **kw):
    return request(seq, ACTION, operation="pair", target=TARGET,
                   bound_action="none", bound_target="none", bound_submit_sequence=0, **kw)


def frame(w=None, number=100, flag=0, **kw):
    w = w or verify.empty_window()
    r = dict(event="research_frame", **META, thread=987, frames=number, uptime_ms=1000 + number,
             world_cookie="0x100000", player_handle="0x0100007a00415246", raw_date=56456976,
             world_ready=True, paused=True, thread_changed=False, world_changed=False, session_frozen=False,
             acceptance_flag=flag, acceptance_state=w["state"], acceptance_origin_sequence=w["on_sequence"],
             acceptance_submit_sequence=w["submit_sequence"], acceptance_off_sequence=w["off_sequence"],
             acceptance_action=w["action"], acceptance_target=w["target"])
    r.update(kw)
    return r


def legality():
    return {"request": pair(1, mode="legality_only"),
            "complete": dict(status=1, reason=0, submit_entered=False, submit_returned=False,
                             ownership_uncertain=False, session_frozen=False, audit_complete=True),
            "records": [dict(event="pair_engine_complete", preview_called=True, preview_allowed=True,
                gate_called=True, gate_allowed=True, exception=0, ownership_uncertain=False, freeze_session=False,
                world="0x100000", raw_date=56456976)]}


def core(on=True, no_native=False):
    c = {key: True for key in verify.SUCCESS_FIELDS}
    c.update(event="test_acceptance_complete", thread_id=987, operation="accept_on" if on else "accept_off",
             desired_enabled=on, before_raw_flag=0 if on or no_native else 1, after_raw_flag=1 if on else 0,
             reason=12 if no_native else 0, exception_code=0, no_native=no_native, freeze_session=False, retry_allowed=False)
    if no_native:
        c.update(native_invoked=False, callback_returned=False, callback_success=False,
                 result_destroyed=False, callback_result_identity=False)
    return c


def complete(seq, c, **kw):
    r = dict(c, event="lab_request_complete", **META, sequence=seq, operation="accept", action=c["operation"],
             completion_frame=110 + seq, session_frozen=False, applied_verified=False,
             natural_ai_acceptance_verified=False)
    r.update(kw)
    return r


def arm():
    v = verify.AcceptanceSession(META)
    v.frame(frame())
    v.claim(request(), {1: legality()}, 1101)
    v.pending_grant(dict(event="lab_acceptance_pending", **META, sequence=2, bound_action=ACTION,
        bound_target=TARGET, bound_submit_sequence=3, off_sequence=4, native_invoked=False, retry_allowed=False,
        uptime_ms=1102, legality_sequence=1, legality_expires=60000))
    c = core()
    v.complete(complete(2, c), c)
    v.frame(frame(v.window, 120, 1))
    return v


def known_submit(v, *, dispatched=True):
    v.claim(pair(), {}, 1121)
    c = dict(event="pair_engine_complete", freeze_session=False, exception=0,
             submit_entered=dispatched, submit_returned=dispatched, caller_container_consumed=True if dispatched else None)
    e = dict(event="lab_request_complete", **META, sequence=3, operation="pair", ownership_uncertain=False,
             session_frozen=False, audit_complete=True)
    v.complete(e, c)
    return v


class Codec(unittest.TestCase):
    def test_real_codec_roundtrip_and_36_ids_remain_fixed(self):
        self.assertEqual(len(lab.ACTIONS), 36)
        for r in (request(), request(4, "accept_off"), pair()):
            self.assertEqual(lab.decode_request(lab.encode_request(r)), r)
        self.assertEqual(lab.PROTOCOL, "EU4LAB/3")
        self.assertEqual(lab.PURPOSE, "restricted_pair_lab_1375_v15")

    def test_on_requires_two_remaining_slots(self):
        maximum = lab.MAX_SEQUENCE
        good = request(maximum - 2, bound_submit_sequence=maximum - 1)
        self.assertEqual(lab.decode_request(lab.encode_request(good)), good)
        for seq in (maximum - 1, maximum):
            with self.subTest(sequence=seq), self.assertRaises(ValueError):
                lab.encode_request(request(seq, bound_submit_sequence=seq + 1))

    def test_controls_reject_arbitrary_values_or_floats(self):
        for field, value in (("operation", "console"), ("action", "toggle"), ("target", "POR"),
            ("bound_action", "yesman"), ("bound_target", "FRA"), ("bound_submit_sequence", True),
            ("bound_submit_sequence", 3.0), ("bound_submit_sequence", 4), ("speed", 1), ("mode", "legality_only")):
            with self.subTest(field=field,value=value), self.assertRaises(ValueError):
                lab.encode_request(request(**{field:value}))

    def test_ordinary_request_cannot_smuggle_control_binding(self):
        r = pair()
        for key, value in (("bound_action", ACTION), ("bound_target", "POR"), ("bound_submit_sequence", 3), ("bound_submit_sequence", False)):
            bad = dict(r, **{key:value})
            with self.subTest(field=key), self.assertRaises(ValueError): lab.encode_request(bad)

    def test_framing_rejects_old_protocol_duplicate_crlf_trailing_nul(self):
        raw = lab.encode_request(request())
        for bad in (raw.replace(b"EU4LAB/3", b"EU4LAB/2"), raw+b"\0", raw+b"speed=0\n", raw.replace(b"\n",b"\r\n"),
                    raw.replace(b"sequence=2\n", b"sequence=02\n")):
            with self.subTest(raw=bad[-50:]), self.assertRaises(ValueError): lab.decode_request(bad)

    def test_off_requires_immediately_following_original_submit(self):
        for seq, bound in ((2,1), (4,2), (4,4)):
            with self.subTest(sequence=seq), self.assertRaises(ValueError):
                lab.encode_request(request(seq, "accept_off", bound_submit_sequence=bound))


class WindowReplay(unittest.TestCase):
    def test_complete_window_needs_later_healthy_zero_frame(self):
        v = known_submit(arm())
        v.claim(request(4, "accept_off"), {}, 1122)
        c = core(False)
        v.complete(complete(4,c), c)
        self.assertEqual(v.window["state"], "awaiting_health")
        with self.assertRaises(ValueError): verify.verify({"acceptance_window":v.snapshot(),"latest_frame":frame(v.window, 114, 0)})
        closed = dict(v.window, state="closed")
        v.frame(frame(closed, 130, 0))
        result=verify.verify({"acceptance_window":v.snapshot(),"latest_frame":v.latest})
        self.assertTrue(result["closed_observed_zero"])
        for key in ("effect_verified","natural_ai_acceptance_verified","production_backend_registered"): self.assertIs(result[key],False)

    def test_effect_unknown_does_not_block_known_clean_rejection_off(self):
        v=known_submit(arm(),dispatched=False)
        self.assertEqual(v.window["state"],"submitted_known")
        self.assertTrue(verify.permits(v.window, request(4,"accept_off")))

    def test_every_wrong_operation_is_rejected_before_consuming_submit_slot(self):
        v=arm()
        bad=[request(3,"accept_off",bound_submit_sequence=2), request(3,bound_submit_sequence=4),
             pair(mode="legality_only"), dict(pair(),target="NAV"),dict(pair(),action="offer_alliance"),
             dict(pair(),operation="fixture",action="fixture_off",target="FRA"),dict(pair(),operation="speed",action="none",target="FRA",speed=0)]
        for r in bad:
            before=v.snapshot()
            with self.subTest(request=r), self.assertRaises(ValueError):v.claim(r,{},1121)
            self.assertEqual(v.snapshot(),before)
            self.assertIsNone(v.pending)

    def test_on_without_prior_legality_or_expired_proof_rejected(self):
        for prior, now in (({},1101),({1:legality()},60000)):
            v=verify.AcceptanceSession(META);v.frame(frame())
            with self.assertRaises(ValueError):v.claim(request(),prior,now)

    def test_legality_wrong_target_date_or_gate_cannot_arm(self):
        for mutate in (lambda p:p["request"].update(target="ENG"),lambda p:p["records"][0].update(raw_date=56457000),
                       lambda p:p["records"][0].update(gate_allowed=False),lambda p:p["records"][0].update(exception=False)):
            p=legality();mutate(p);v=verify.AcceptanceSession(META);v.frame(frame())
            with self.assertRaises(ValueError):v.claim(request(),{1:p},1101)

    def test_callback_without_durable_pending_grant_rejected(self):
        v=verify.AcceptanceSession(META);v.frame(frame());v.claim(request(),{1:legality()},1101)
        with self.assertRaises(ValueError):v.core(core())

    def test_repeated_pending_grant_rejected(self):
        v=arm()
        with self.assertRaises(ValueError):v.pending_grant(dict(event="lab_acceptance_pending",**META))

    def test_unknown_submit_ownership_cannot_authorize_off(self):
        for change in ({"exception":1},{"caller_container_consumed":False},{"submit_returned":False},{"freeze_session":True}):
            v=arm();v.claim(pair(),{},1121)
            c=dict(freeze_session=False,exception=0,submit_entered=True,submit_returned=True,caller_container_consumed=True,**{})
            c.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):
                v.complete(dict(event="lab_request_complete",**META,sequence=3,ownership_uncertain=False,session_frozen=False,audit_complete=True),c)
            self.assertFalse(verify.permits(v.window,request(4,"accept_off")))

    def test_no_native_off_cannot_close_active_grant(self):
        v=known_submit(arm());v.claim(request(4,"accept_off"),{},1122);c=core(False,True)
        with self.assertRaises(ValueError):v.complete(complete(4,c),c)
        self.assertEqual(v.window["state"],"pending_off")

    def test_closed_no_native_off_does_not_create_binding(self):
        v=verify.AcceptanceSession(META);v.frame(frame());v.claim(request(4,"accept_off"),{},1101)
        c=core(False,True);v.complete(complete(4,c),c)
        self.assertEqual(v.window,verify.empty_window())

    def test_no_native_diagnostic_requires_exact_reason_and_durable_audit(self):
        for change in ({"reason":0},{"reason":8},{"audit_complete":False}):
            v=verify.AcceptanceSession(META);v.frame(frame());v.claim(request(4,"accept_off"),{},1101)
            c=core(False,True);c.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):v.complete(complete(4,c),c)

    def test_handler_cleanup_audit_or_flag_failure_rejected(self):
        for key,value in (("result_destroyed",False),("audit_complete",False),("callback_result_identity",False),
                          ("arguments_unchanged",False),("after_raw_flag",0),("exception_code",1)):
            v=known_submit(arm());v.claim(request(4,"accept_off"),{},1122);c=core(False);c[key]=value
            if key=="after_raw_flag":c[key]=1
            with self.subTest(key=key),self.assertRaises(ValueError):v.complete(complete(4,c),c)

    def test_typed_flags_and_foreign_identity_are_not_coerced(self):
        for changes in ({"acceptance_flag":False},{"acceptance_flag":0.0},{"acceptance_origin_sequence":False},
                        {"pid":1235},{"process_creation_filetime":"01dd000000000002"},{"thread":988}):
            v=verify.AcceptanceSession(META)
            with self.subTest(changes=changes),self.assertRaises(ValueError):v.frame(frame(**changes))

    def test_off_same_or_earlier_frame_cannot_unlock(self):
        v=known_submit(arm());v.claim(request(4,"accept_off"),{},1122);c=core(False);v.complete(complete(4,c),c)
        with self.assertRaises(ValueError):v.frame(frame(dict(v.window,state="closed"),114,0))

    def test_off_core_return_is_not_wrapper_or_reset_health(self):
        v=known_submit(arm());v.claim(request(4,"accept_off"),{},1122);v.core(core(False))
        self.assertEqual(v.window["state"],"pending_off")
        self.assertFalse(verify.permits(v.window,pair(5)))

    def test_active_date_or_pause_change_fails_health(self):
        for change in ({"raw_date":56457000},{"paused":False},{"acceptance_flag":0}):
            v=arm()
            with self.subTest(change=change),self.assertRaises(ValueError):v.frame(frame(v.window,121,1,**change))


if __name__ == "__main__":
    unittest.main()
