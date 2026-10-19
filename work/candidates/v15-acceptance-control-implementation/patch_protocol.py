"""Deterministic candidate-only protocol delta; never operates on live paths."""
from pathlib import Path


def transform(s):
    def replace(old, new, count=1):
        nonlocal s
        assert s.count(old) == count, (old[:100], s.count(old))
        s = s.replace(old, new)
    replace('FIELDS = ("pid", "creation", "sequence", "expires", "operation", "mode", "action", "actor", "target", "speed")',
            'FIELDS = ("pid", "creation", "sequence", "expires", "operation", "mode", "action", "actor", "target", "speed", "bound_action", "bound_target", "bound_submit_sequence")')
    replace('    else:\n        raise LabError("Unknown research operation")\n    raw =', '''    elif record["operation"] == "accept":
        require(record["mode"] == "submit" and record["action"] in ("accept_on", "accept_off")
                and record["actor"] == record["target"] == "FRA" and record["speed"] == 0,
                "Invalid fixed acceptance operation")
        require(record["bound_action"] in ACTIONS and record["bound_target"] in TAGS
                and record["bound_target"] != "FRA", "Invalid acceptance binding")
        require(integer(record["bound_submit_sequence"], 1, MAX_SEQUENCE), "Invalid bound sequence")
        if record["action"] == "accept_on":
            require(record["sequence"] <= MAX_SEQUENCE - 2 and record["bound_submit_sequence"] == record["sequence"] + 1,
                    "On must reserve the consecutive submit and off slots")
        else:
            require(record["sequence"] >= 3 and record["bound_submit_sequence"] == record["sequence"] - 1,
                    "Off must use the slot immediately after its original submit")
    else:
        raise LabError("Unknown research operation")
    if record["operation"] != "accept":
        require(record["bound_action"] == record["bound_target"] == "none"
                and type(record["bound_submit_sequence"]) is int and record["bound_submit_sequence"] == 0,
                "Ordinary operations require exact unbound sentinels")
    raw =''')
    replace('if key in ("pid", "sequence", "expires", "speed"):', 'if key in ("pid", "sequence", "expires", "speed", "bound_submit_sequence"):')
    replace('target, speed, ttl_ms, now):', 'target, speed, ttl_ms, now, bound_action="none", bound_target="none", bound_submit_sequence=0):')
    replace('"actor": actor, "target": target, "speed": speed}\n    return record, encode_request(record)', '''"actor": actor, "target": target, "speed": speed, "bound_action": bound_action,
              "bound_target": bound_target, "bound_submit_sequence": bound_submit_sequence}
    raw = encode_request(record)
    from tools.verify_diplomacy_acceptance_v15 import check_publication
    check_publication(record, evidence, now)
    return record, raw''')
    replace('clock=uptime_ms, recheck=None, watchdog_verified=False, fixture_check=None):', 'clock=uptime_ms, recheck=None, watchdog_verified=False, fixture_check=None,\n                     bound_action="none", bound_target="none", bound_submit_sequence=0):')
    replace('action=action, actor=actor, target=target, speed=speed, ttl_ms=ttl_ms, now=clock())', 'action=action, actor=actor, target=target, speed=speed, ttl_ms=ttl_ms, now=clock(),\n                                      bound_action=bound_action, bound_target=bound_target, bound_submit_sequence=bound_submit_sequence)')
    replace('            check_ready(current_evidence, current_live, clock(), operation=operation)\n            require(', '''            check_ready(current_evidence, current_live, clock(), operation=operation)
            from tools.verify_diplomacy_acceptance_v15 import check_publication
            check_publication(record, current_evidence, clock())
            require(''')
    replace('    from tools.verify_diplomacy_owned_peace_v15 import OwnedPeaceSession, OWNED_EVENTS', '    from tools.verify_diplomacy_owned_peace_v15 import OwnedPeaceSession, OWNED_EVENTS\n    from tools.verify_diplomacy_acceptance_v15 import AcceptanceSession')
    replace('    owned = OwnedPeaceSession(metadata)', '    owned = OwnedPeaceSession(metadata)\n    acceptance = AcceptanceSession(metadata)')
    replace('                owned.frame(event,line_number)', '                acceptance.frame(event)\n                owned.frame(event,line_number)')
    replace('"pid", "sequence", "expires", "operation", "mode", "action", "actor", "target", "speed")}', '"pid", "sequence", "expires", "operation", "mode", "action", "actor", "target", "speed", "bound_action", "bound_target", "bound_submit_sequence")}')
    replace('                    pending = {"request": record, "records": [], "complete": None}', '                    acceptance.claim(record, requests, event.get("claimed_uptime_ms"))\n                    pending = {"request": record, "records": [], "complete": None}')
    replace('                elif name == "lab_native_record":', '                elif name == "lab_acceptance_pending":\n                    acceptance.pending_grant(event)\n                elif name == "lab_native_record":')
    replace('                    fixture = pending is not None and pending["request"]["operation"] == "fixture"', '                    fixture = pending is not None and pending["request"]["operation"] == "fixture"\n                    control_accept = pending is not None and pending["request"]["operation"] == "accept"')
    replace('                    elif fixture:\n                        requested_event', '                    elif control_accept:\n                        acceptance.core(core)\n                    elif fixture:\n                        requested_event')
    replace('expected_begin = "pair_engine_begin" if pair else ("test_fixture_begin" if fixture else "test_speed_begin")', 'expected_begin = "pair_engine_begin" if pair else ("test_acceptance_begin" if control_accept else ("test_fixture_begin" if fixture else "test_speed_begin"))')
    replace('("pair_engine_complete", "test_speed_complete", "test_fixture_complete")', '("pair_engine_complete", "test_speed_complete", "test_fixture_complete", "test_acceptance_complete")', 2)
    replace('                    elif pending["request"]["operation"] == "fixture":', '                    elif pending["request"]["operation"] == "accept":\n                        require(event.get("action") == pending["request"]["action"], "Acceptance completion differs from fixed request")\n                        fields = ("reason", "native_invoked", "callback_returned", "callback_success", "result_destroyed", "arguments_unchanged")\n                    elif pending["request"]["operation"] == "fixture":')
    replace('                    pending = None\n                elif name == "lab_lease_complete":', '                    acceptance.complete(event, core)\n                    pending = None\n                elif name == "lab_lease_complete":')
    replace('"input_wait_pending": input_wait is not None,', '"input_wait_pending": input_wait is not None, "acceptance_window": acceptance.snapshot(),')
    replace('    frame = evidence["latest_frame"]\n    require(type(frame.get("owned_peace_tested"))', '''    frame = evidence["latest_frame"]
    require(integer(frame.get("acceptance_flag"), 0, 1) and type(live.get("acceptance_flag")) is int
            and live["acceptance_flag"] == frame["acceptance_flag"], "Independent/native acceptance flag differs")
    require(evidence.get("acceptance_window",{}).get("state") not in ("pending_on","pending_submit","pending_off","awaiting_health","unknown"),
            "Acceptance transition or required reset health is unresolved")
    if phase:
        require(evidence["acceptance_window"]["state"] == "closed" and frame["acceptance_flag"] == 0,
                "Preflight requires closed flag0")
    require(type(frame.get("owned_peace_tested"))''')
    replace('"parse", "pid", "creation", "sequence", "ttl_expired", "ttl_range", "claim_open",', '"parse", "pid", "creation", "sequence", "ttl_expired", "ttl_range", "acceptance_window", "claim_open",')
    replace('        require(u64(self.reader.base + GAME_POINTER_RVA) == game and u64(game + 0x1e60) == player,', '        flag = self.reader.read(game + 0x23a1, 1)[0]\n        require(flag in (0, 1) and self.reader.read(game + 0x23a1, 1)[0] == flag, "Acceptance flag is noncanonical or changed")\n        require(u64(self.reader.base + GAME_POINTER_RVA) == game and u64(game + 0x1e60) == player,')
    replace('"player_handle": f"0x{player:016x}", "raw_date": date}', '"player_handle": f"0x{player:016x}", "raw_date": date, "acceptance_flag": flag}')
    return s


if __name__ == "__main__":
    raise SystemExit("Use prepare.py --check or --refresh-candidate; patch helpers cannot write independently")
