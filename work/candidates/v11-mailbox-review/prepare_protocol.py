"""Generate isolated v11 host tools from frozen v10 host templates. No game I/O."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FILES = (
    "work/native/lab_protocol_v10_1375.py",
    "work/native/inject_lab_v10_1375.py",
    "work/native/run_lab_speed_v10_1375.py",
    "tools/request_diplomacy_lab_v10.py",
    "tools/verify_diplomacy_lifecycle_v10.py",
    "tools/verify_diplomacy_preview_v10.py",
    "tools/verify_diplomacy_command_v10.py",
)


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("Missing/ambiguous v10 host anchor: " + old[:90])
    return text.replace(old, new)


NEW_IDS = ('warn', 'insult', 'form_coalition', 'leave_coalition',
           'support_independence', 'cancel_independence_support',
           'request_trade_power', 'cancel_trade_power_transfer', 'steer_trade',
           'cancel_steer_trade', 'send_gift', 'trade_favors_for_gold')
NEW_FAMILIES = {'warningaction': 64, 'insultaction': 72, 'form_coalition': 64,
                'support_independence_action': 64, 'transfer_trade_power': 72,
                'steer_trade': 64, 'giftaction': 72, 'trade_favors_for_gold': 64}
POSITIVE_ONLY = ('warningaction', 'insultaction', 'giftaction', 'trade_favors_for_gold')


def extend_actions(name, text):
    """Pin the independently reviewed 20-family / 36-ID candidate in host tools."""
    if name.endswith('lab_protocol_v10_1375.py'):
        start = text.index('ACTIONS = frozenset(')
        end = text.index('\n', start)
        old = text[start:end]
        import ast
        ids = ast.literal_eval(old[len('ACTIONS = frozenset('):-1])
        text = replace_once(text, old, 'ACTIONS = frozenset(' + repr(ids + NEW_IDS) + ')')
        old = next(line for line in text.splitlines() if line.startswith('FIXED_RESEARCH_PARAMETERS = '))
        params = ast.literal_eval(old.split(' = ', 1)[1])
        params.update(send_gift={'amount': '25.000'}, insult={'index': -1},
                      request_trade_power={'fraction_milli': 500},
                      cancel_trade_power_transfer={'fraction_milli': 500})
        text = replace_once(text, old, 'FIXED_RESEARCH_PARAMETERS = ' + repr(params))
        text = replace_once(text, 'subsidy = request["action"] in FIXED_RESEARCH_PARAMETERS',
                            'subsidy = request["action"] in ("give_subsidies", "cancel_subsidies")')
        anchor = '                                "Pair core fixed research parameters differ")'
        text = replace_once(text, anchor, anchor + '''
                        expected_extra = {
                            "fixed_gift_amount_milli": 25000 if request["action"] == "send_gift" else 0,
                            "fixed_transfer_fraction_milli": 500 if request["action"] in ("request_trade_power", "cancel_trade_power_transfer") else 0,
                            "fixed_insult_index": -1 if request["action"] == "insult" else 0,
                        }
                        require(all(type(core.get(k)) is int and core[k] == v for k, v in expected_extra.items()),
                                "Pair core fixed gift/trade/insult parameters differ")''')
    elif name.endswith('verify_diplomacy_lifecycle_v10.py'):
        start = text.index('ACTIONS = {')
        end = text.index('\nPREVIEW_EVENTS', start)
        import ast
        families = ast.literal_eval(text[start:end].split(' = ', 1)[1])
        families.update(NEW_FAMILIES)
        text = replace_once(text, text[start:end], 'ACTIONS = ' + repr(families) + '\nPOSITIVE_ONLY = frozenset(' + repr(POSITIVE_ONLY) + ')')
        text = text.replace('twelve', 'twenty').replace('Twelve', 'Twenty')
        text = text.replace('event["passed"] == 12', 'event["passed"] == 20').replace('count must be 12', 'count must be 20')
        anchor = '            self.check(type(event.get("fixed_subsidy_duration_years")) is int and event["fixed_subsidy_duration_years"] == (10 if action == "warsubsidy" else 0), "Fixed subsidy years evidence differs", line)'
        text = replace_once(text, anchor, anchor + '\n            self.check(fixed_extra_valid(event, action), "Fixed gift/trade/insult evidence differs", line)')
        helper = '''def fixed_extra_valid(event, action):
    expected = {"fixed_gift_amount_milli": 25000 if action == "giftaction" else 0,
                "fixed_transfer_fraction_milli": 500 if action == "transfer_trade_power" else 0,
                "fixed_insult_index": -1 if action == "insultaction" else 0}
    return all(type(event.get(k)) is int and event[k] == v for k, v in expected.items())


'''
        text = replace_once(text, 'class Session:', helper + 'class Session:')
    elif name.endswith('verify_diplomacy_preview_v10.py'):
        text = text.replace('twelve-family, forty-eight-case', 'twenty-family, seventy-two-case')
        text = replace_once(text,
            'EXPECTED = {(action, target, value) for action in lifecycle.ACTIONS for target in TARGETS for value in (True, False)}',
            'EXPECTED = {(action, target, value) for action in lifecycle.ACTIONS for target in TARGETS\n            for value in ((True,) if action in lifecycle.POSITIVE_ONLY else (True, False))}')
        text = text.replace('48', '72').replace('forty-eight', 'seventy-two').replace('Forty-eight', 'Seventy-two')
        text = replace_once(text, '            self.check(event.get("actor") == "FRA", "Preview actor must be FRA", line)',
            '            self.check(not valid_key or (action, target, value) in EXPECTED, "Unaudited cancellation mode", line)\n            self.check(event.get("actor") == "FRA", "Preview actor must be FRA", line)')
        anchor = '            self.check(type(event.get("fixed_subsidy_duration_years")) is int and event["fixed_subsidy_duration_years"] == (10 if action == "warsubsidy" else 0), "Fixed subsidy years evidence differs", line)'
        text = replace_once(text, anchor, anchor + '\n            self.check(lifecycle.fixed_extra_valid(event, action), "Fixed gift/trade/insult evidence differs", line)')
    elif name.endswith('verify_diplomacy_command_v10.py'):
        text = text.replace('forty-eight', 'seventy-two').replace('== 48', '== 72')
    return text


def generate(check=False):
    candidates = {}
    for name in FILES:
        raw = (ROOT / name).read_bytes()
        text = raw.decode("utf-8").replace("v10", "v11")
        if name.endswith("lab_protocol_v10_1375.py"):
            text = replace_once(text,
                "    lease = None\n    with path.open(\"rb\") as stream:",
                "    lease = None\n    input_wait = None\n    last_input_uptime = 0\n    with path.open(\"rb\") as stream:")
            anchor = "            if name.startswith(\"lab_\"):\n                require(\"command\" in proofs"
            block = (HERE / "input-diagnostics.inc.py").read_text(encoding="utf-8")
            text = replace_once(text, anchor, block + "\n" + anchor)
            text = replace_once(text,
                '            if name.startswith("lab_"):\n                require("command" in proofs',
                '            if name.startswith("lab_"):\n                require(input_wait is None, "Mailbox operation preceded the end of its unclaimed input wait")\n                require("command" in proofs')
            text = replace_once(text,
                'integer(event.get("uptime_ms"), max(1, previous_uptime), 2**64 - 1)',
                'integer(event.get("uptime_ms"), max(1, previous_uptime, last_input_uptime), 2**64 - 1)')
            text = replace_once(text,
                '            require(name == "research_frame" or name in phase_events, "Unknown non-mailbox event in research log: " + name)',
                '            require(input_wait is None or name == "research_frame", "Phase invocation preceded the end of its unclaimed input wait")\n            require(name == "research_frame" or name in phase_events, "Unknown non-mailbox event in research log: " + name)')
            text = replace_once(text,
                '"last_sequence": last_sequence, "pending": pending is not None, "lease_pending": lease is not None, "requests": requests,',
                '"last_sequence": last_sequence, "pending": pending is not None, "lease_pending": lease is not None, "requests": requests,\n            "input_wait_pending": input_wait is not None,')
            text = replace_once(text,
                '    require(not evidence["pending"], "Prior native request is incomplete; never automatically resubmit")',
                '    require(not evidence.get("input_wait_pending"), "A published input is awaiting its bounded pre-handle sharing wait")\n    require(not evidence["pending"], "Prior native request is incomplete; never automatically resubmit")')
        elif name.endswith("inject_lab_v10_1375.py"):
            text = text.replace("three audited on-disk save files", "two audited on-disk baseline save files")
        text = extend_actions(name, text)
        candidates[name.replace("v10", "v11")] = text.encode("utf-8")
    out = ROOT / "work/runtime/native1375-v11"
    manifest = out / "build.json"
    for name, raw in candidates.items():
        path = ROOT / name
        if path.exists() and path.read_bytes() == raw:
            continue
        if check:
            raise ValueError("Generated host tool differs: " + name)
        if manifest.exists() or any(out.glob("session-*")):
            raise ValueError("Refuse changing a built or used v11 host profile")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    result = {"purpose": "v11_host_mailbox_diagnostics_candidate", "game_process_accessed": False,
              "native_invoked": False, "action_count": 36, "family_count": 20,
              "phase_counts": {"lifecycle": 20, "preview": 72, "command": 72},
              "source_templates": {n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in FILES},
              "generated_sha256": {n: hashlib.sha256(raw).hexdigest() for n, raw in candidates.items()}}
    if not check:
        (HERE / "protocol-candidate.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = generate(args.check)
    print(json.dumps({k: v for k, v in result.items() if k not in ("source_templates", "generated_sha256")}))
