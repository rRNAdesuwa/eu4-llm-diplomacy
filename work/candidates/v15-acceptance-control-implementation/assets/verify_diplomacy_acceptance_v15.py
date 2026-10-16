"""Bounded acceptance-window replay. No native calls, retries or effect inference."""
from copy import deepcopy

MAX_SEQUENCE = 2**63 - 1
STATES = ("closed", "pending_on", "armed", "pending_submit", "submitted_known", "pending_off", "awaiting_health", "unknown")
SUCCESS_FIELDS = ("native_invoked", "callback_returned", "callback_success", "result_destroyed",
                  "arguments_unchanged", "readback_observed", "readback_matches", "world_identity_unchanged",
                  "callback_result_identity", "zero_arguments_confirmed", "audit_complete")


def require(condition, message):
    if not condition:
        raise ValueError("acceptance: " + message)


def integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def empty_window():
    return {"state": "closed", "on_sequence": 0, "submit_sequence": 0, "off_sequence": 0,
            "action": "none", "target": "none", "off_frame": 0}


def bound_submit(window, request):
    return (request["operation"] == "pair" and request["mode"] == "submit"
            and request["actor"] == "FRA" and request["action"] == window["action"]
            and request["target"] == window["target"] and request["sequence"] == window["submit_sequence"])


def same_binding(window, request):
    return (request["bound_action"] == window["action"] and request["bound_target"] == window["target"]
            and request["bound_submit_sequence"] == window["submit_sequence"])


def permits(window, request):
    if window["state"] == "closed":
        return True
    if window["state"] == "armed":
        return bound_submit(window, request)
    return (window["state"] == "submitted_known" and request["operation"] == "accept"
            and request["action"] == "accept_off" and request["sequence"] == window["off_sequence"]
            and same_binding(window, request))


def require_fresh_legality(request, proof, frame, now):
    require(type(proof) is dict and type(proof.get("request")) is dict and type(proof.get("complete")) is dict,
            "on requires the immediately preceding native legality proof")
    previous, complete = proof["request"], proof["complete"]
    require(previous["sequence"] == request["sequence"] - 1 and previous["operation"] == "pair"
            and previous["mode"] == "legality_only" and previous["actor"] == "FRA"
            and previous["action"] == request["bound_action"] and previous["target"] == request["bound_target"],
            "legality proof is not the exact prior action/target")
    require(integer(now, 1, 2**64 - 1) and now < previous["expires"], "prior legality proof expired")
    require(integer(complete.get("status"), 1, 1) and integer(complete.get("reason"), 0, 0)
            and complete.get("submit_entered") is False and complete.get("submit_returned") is False
            and complete.get("ownership_uncertain") is False and complete.get("session_frozen") is False
            and complete.get("audit_complete") is True,
            "legality completion is not a clean no-send success")
    records = proof.get("records")
    require(type(records) is list and records and records[-1].get("event") == "pair_engine_complete", "missing legality core")
    core = records[-1]
    require(all(core.get(k) is True for k in ("preview_called", "preview_allowed", "gate_called", "gate_allowed"))
            and integer(core.get("exception"), 0, 0) and core.get("ownership_uncertain") is False
            and core.get("freeze_session") is False and core.get("world") == frame["world_cookie"]
            and type(core.get("raw_date")) is int and core["raw_date"] == frame["raw_date"],
            "legality/gate/world/date proof is incomplete or stale")


def check_publication(request, evidence, now):
    window, frame = evidence["acceptance_window"], evidence["latest_frame"]
    require(permits(window, request), "reserved on/submit/off window forbids this operation; no sequence may be consumed")
    require(integer(frame.get("acceptance_flag"), 0, 1), "missing canonical native flag")
    if window["state"] == "closed":
        require(frame["acceptance_flag"] == 0, "closed window has nonzero flag")
    if request["operation"] == "accept" and request["action"] == "accept_on":
        require(window["state"] == "closed" and request["sequence"] <= MAX_SEQUENCE - 2, "on cannot reserve submit and off")
        require_fresh_legality(request, evidence["requests"].get(request["sequence"] - 1), frame, now)
    if window["state"] in ("armed", "submitted_known"):
        require(frame["acceptance_flag"] == 1 and frame.get("paused") is True, "active window is not paused flag1")


class AcceptanceSession:
    """Validate independent event identity plus exact grant transitions.

    Existing protocol reader still validates phase ordering, claims, pair core
    ownership and full request bytes. This adds no effect or SP assertion.
    """
    def __init__(self, metadata):
        self.metadata = metadata
        self.window = empty_window()
        self.pending = None
        self.latest = None
        self.pending_audited = False
        self.completed_windows = 0
        self.on_legality = None
        self.claimed_uptime = 0

    def identity(self, event):
        require(type(event.get("pid")) is int and event["pid"] == self.metadata["pid"]
                and event.get("process_creation_filetime") == self.metadata["process_creation_filetime"], "foreign process identity")

    def frame(self, event):
        self.identity(event)
        require(self.pending is None, "health frame overlaps a request callback")
        require(type(event.get("thread")) is int and event["thread"] == self.metadata["window_thread"], "foreign frame thread")
        require(integer(event.get("acceptance_flag"), 0, 1), "flag must be exact canonical integer")
        state = event.get("acceptance_state")
        require(state in STATES and state != "unknown", "unknown acceptance state")
        w = self.window
        if w["state"] == "awaiting_health" and state == "closed":
            require(integer(event.get("frames"), w["off_frame"] + 1, 2**31 - 1)
                    and event.get("world_ready") is True and event.get("paused") is True
                    and event.get("thread_changed") is False and event.get("world_changed") is False
                    and event.get("session_frozen") is False and event["acceptance_flag"] == 0,
                    "off lacks a later healthy paused zero boundary")
            w["state"] = "closed"
            self.completed_windows += 1
        require(state == w["state"], "frame window state differs from audited transitions")
        for field, key in (("acceptance_origin_sequence", "on_sequence"), ("acceptance_submit_sequence", "submit_sequence"),
                           ("acceptance_off_sequence", "off_sequence")):
            require(integer(event.get(field), 0, MAX_SEQUENCE) and event[field] == w[key], "frame sequence binding differs")
        require(event.get("acceptance_action") == w["action"] and event.get("acceptance_target") == w["target"], "frame action binding differs")
        expected_flag = 1 if state in ("armed", "submitted_known") else 0
        require(state in ("closed", "armed", "submitted_known", "awaiting_health") and event["acceptance_flag"] == expected_flag,
                "pending/unknown native transition or wrong flag in health frame")
        if state != "closed":
            require(event.get("paused") is True and event.get("world_cookie") == w["world"]
                    and event.get("player_handle") == w["player"] and event.get("raw_date") == w["date"]
                    and type(event.get("raw_date")) is int, "active grant world/date changed")
        self.latest = event

    def claim(self, record, requests, claimed_uptime):
        require(self.pending is None and self.latest is not None, "overlapping claim or no health")
        require(integer(claimed_uptime, self.latest["uptime_ms"], 2**64 - 1), "missing/regressing actual claim time")
        check_publication(record, {"acceptance_window": self.window, "latest_frame": self.latest, "requests": requests}, claimed_uptime)
        self.pending = record
        self.pending_audited = False
        self.claimed_uptime = claimed_uptime
        self.on_legality = requests.get(record["sequence"] - 1) if record["operation"] == "accept" and record["action"] == "accept_on" else None
        if self.window["state"] == "armed":
            self.window["state"] = "pending_submit"
        elif self.window["state"] == "submitted_known":
            self.window["state"] = "pending_off"
        # on's persistent pending event precedes its core begin, not the claim.

    def pending_grant(self, event):
        self.identity(event)
        r, frame = self.pending, self.latest
        require(r is not None and r["operation"] == "accept" and r["action"] == "accept_on"
                and self.window["state"] == "closed" and not self.pending_audited, "duplicate/unbound pending grant")
        require(event.get("sequence") == r["sequence"] and type(event.get("sequence")) is int
                and event.get("bound_action") == r["bound_action"] and event.get("bound_target") == r["bound_target"]
                and event.get("bound_submit_sequence") == r["bound_submit_sequence"]
                and type(event.get("bound_submit_sequence")) is int and event.get("off_sequence") == r["sequence"] + 2
                and type(event.get("off_sequence")) is int and event.get("retry_allowed") is False
                and event.get("native_invoked") is False, "pending grant binding mismatch")
        require(integer(event.get("uptime_ms"), self.claimed_uptime, 2**64 - 1)
                and integer(event.get("legality_sequence"), r["sequence"] - 1, r["sequence"] - 1)
                and type(event.get("legality_expires")) is int
                and event["legality_expires"] == self.on_legality["request"]["expires"], "pending legality lifetime differs")
        require_fresh_legality(r, self.on_legality, frame, event["uptime_ms"])
        self.window = {"state": "pending_on", "on_sequence": r["sequence"], "submit_sequence": r["sequence"] + 1,
                       "off_sequence": r["sequence"] + 2, "action": r["bound_action"], "target": r["bound_target"],
                       "world": frame["world_cookie"], "player": frame["player_handle"], "date": frame["raw_date"], "off_frame": 0}
        self.pending_audited = True

    def core(self, core):
        r = self.pending
        require(r is not None and r["operation"] == "accept", "acceptance core without fixed request")
        require(core.get("event") in ("test_acceptance_begin", "test_acceptance_complete")
                and type(core.get("thread_id")) is int and core["thread_id"] == self.metadata["window_thread"]
                and core.get("operation") == r["action"] and core.get("desired_enabled") is (r["action"] == "accept_on")
                and core.get("retry_allowed") is False, "foreign/unknown acceptance core")
        require(r["action"] != "accept_on" or self.pending_audited, "callback preceded durable pending grant")
        for key in SUCCESS_FIELDS + ("no_native", "freeze_session"):
            require(type(core.get(key)) is bool, "core boolean type mismatch: " + key)
        for key in ("before_raw_flag", "after_raw_flag"):
            require(core.get(key) is None or integer(core[key], 0, 1), "core noncanonical observed flag")
        require(integer(core.get("reason"), 0, 2**32 - 1) and integer(core.get("exception_code"), 0, 2**32 - 1), "core reason/exception type")

    def complete(self, event, core):
        self.identity(event)
        r = self.pending
        require(r is not None and type(event.get("sequence")) is int and event["sequence"] == r["sequence"], "unbound completion")
        if r["operation"] == "accept":
            self.core(core)
            require(core.get("event") == "test_acceptance_complete", "missing final control audit")
            fields = SUCCESS_FIELDS + ("no_native", "reason", "exception_code", "before_raw_flag", "after_raw_flag")
            require(all(key in event and key in core and type(event[key]) is type(core[key]) and event[key] == core[key] for key in fields),
                    "host/core acceptance result differs")
            require(core["freeze_session"] is False and core["exception_code"] == 0
                    and event.get("session_frozen") is False and event.get("retry_allowed") is False
                    and event.get("applied_verified") is False and event.get("natural_ai_acceptance_verified") is False,
                    "unknown or overclaimed control completion")
            if core["no_native"]:
                require(self.window["state"] == "closed" and r["action"] == "accept_off" and core["reason"] == 12
                        and core["audit_complete"] is True
                        and core["before_raw_flag"] == core["after_raw_flag"] == 0
                        and all(core[k] is False for k in ("native_invoked", "callback_returned", "callback_success", "result_destroyed")),
                        "no-native result cannot create/replace/close a grant")
            else:
                require(core["reason"] == 0 and all(core[k] is True for k in SUCCESS_FIELDS), "transition lacks normal return/cleanup/audit")
                on = r["action"] == "accept_on"
                require(core["before_raw_flag"] == (0 if on else 1) and core["after_raw_flag"] == (1 if on else 0), "wrong flag transition")
                require(self.window["state"] == ("pending_on" if on else "pending_off"), "wrong window at completion")
                require(integer(event.get("completion_frame"), 1, 2**31 - 1), "missing completion frame")
                self.window["state"] = "armed" if on else "awaiting_health"
                if not on:
                    self.window["off_frame"] = event["completion_frame"]
        elif self.window["state"] == "pending_submit":
            require(bound_submit(self.window, r) and event.get("ownership_uncertain") is False
                    and event.get("session_frozen") is False and core.get("freeze_session") is False
                    and integer(core.get("exception"), 0, 0) and event.get("audit_complete") is True,
                    "bound submit outcome/ownership unknown; no compensating off")
            require(core.get("submit_entered") is False or core.get("submit_returned") is True
                    and core.get("caller_container_consumed") is True, "entered submit lacks known consumed return")
            self.window["state"] = "submitted_known"
        self.pending = None

    def snapshot(self):
        return deepcopy(self.window)


def verify(evidence):
    """Final window closure only; never an effect, natural-AI or SP result."""
    window = evidence["acceptance_window"]
    require(window["state"] == "closed" and evidence["latest_frame"]["acceptance_flag"] == 0,
            "unresolved acceptance window")
    return {"scope": "acceptance_control_window_only", "closed_observed_zero": True,
            "natural_ai_acceptance_verified": False, "effect_verified": False,
            "strict_single_player_verified": False, "production_backend_registered": False}


def main(argv=None):
    """Read-only replay of a fixed versioned session; never opens a game handle."""
    import argparse
    import json
    import sys
    from work.native import lab_protocol_v15_1375 as lab
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--creation", required=True)
    args = parser.parse_args(argv)
    try:
        manifest, manifest_sha = lab.verify_build()
        session = lab.session_path(lab.OUTPUT, args.pid, args.creation)
        metadata = lab.read_session_metadata(session, args.pid, args.creation)
        evidence = lab.read_evidence(session, metadata)
        proof = verify(evidence)
        print(json.dumps({"purpose": lab.PURPOSE, "proof": proof,
            "manifest_sha256": manifest_sha, "dll_sha256": manifest["dll_sha256"],
            "log_sha256": evidence["log_sha256"], "acceptance_window": evidence["acceptance_window"],
            "game_process_accessed": False}, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
