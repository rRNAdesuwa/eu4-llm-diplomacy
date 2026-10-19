"""Correct the retained Node spec-reporter receipt parser, never rerun tests.

R1 expected TAP '# tests' counters; this Node emitted Unicode spec counters.
Preserve R1 stdout and false wrapper receipt, adopting its actual exit0/18pass.
"""
import argparse
import json
import re
from verify_offline import HERE, NODE, HELPER, pin, provenance, source_pins, write_new


def replay():
    provenance()
    old = json.loads((HERE/'offline-receipt.json').read_bytes())
    assert old['source_pins'] == source_pins() and old['source_unchanged']
    assert old['exit_code'] == 0 and old['runner_error'] is None and old['child_collected']
    assert old['passed'] is False and old['test_count'] == 18
    assert old['stdout_pin'] == pin(HERE/'offline-tests.stdout.tap')
    assert old['node'] == dict(path=str(NODE), **pin(NODE))
    assert old['memory_helper'] == dict(path=str(HELPER), **pin(HELPER))
    assert old['child_peak_committed_bytes'] < 768*1024*1024
    output = (HERE/'offline-tests.stdout.tap').read_text(encoding='utf-8')
    for name, expected in (('tests', 18), ('pass', 18), ('fail', 0), ('cancelled', 0), ('skipped', 0)):
        assert re.search(r'^(?:#|\u2139) '+name+' '+str(expected)+r'$', output, re.M), name
    assert re.search(r'^# tests 18$', output, re.M) is None
    return old


def current_pins():
    return source_pins() | {'verify_offline_r2.py': pin(HERE/'verify_offline_r2.py')}


def main():
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--adopt-retained-result', action='store_true')
    modes.add_argument('--check', action='store_true')
    args = parser.parse_args()
    old = replay()
    if args.adopt_retained_result:
        write_new('offline-verification-r2.json', dict(schema='EU4-FRIDA-ENTRY-OFFLINE-RECEIPT-CORRECTION/2',
            passed=True, source_pins=current_pins(), stored_tests=18, pass_count=18, fail_count=0,
            reason='Wrapper expected TAP counters; retained Node stdout uses Unicode spec counters. Actual test child exit0 and all18pass.',
            original_receipt_pin=pin(HERE/'offline-receipt.json'),
            unchanged_stdout_pin=pin(HERE/'offline-tests.stdout.tap'),
            original_false_receipt_preserved=True, tests_reexecuted=False,
            script_or_test_changed=False, child_peak_committed_bytes=old['child_peak_committed_bytes'],
            child_collected=True, actual_Frida_loaded=False, REA_invoked=False,
            game_accessed=False, actual_code_hook_installed=False, native_ready=False,
            sealed=False, shell_sessions_remaining=0))
    receipt = json.loads((HERE/'offline-verification-r2.json').read_bytes())
    assert receipt['passed'] and receipt['source_pins'] == current_pins()
    assert receipt['original_receipt_pin'] == pin(HERE/'offline-receipt.json')
    assert receipt['unchanged_stdout_pin'] == pin(HERE/'offline-tests.stdout.tap')
    print(json.dumps(dict(passed=True, stored_tests=18, tests_reexecuted=False,
        source_pins=current_pins(), verification_pin=pin(HERE/'offline-verification-r2.json'),
        child_peak_committed_bytes=receipt['child_peak_committed_bytes'],
        actual_Frida_loaded=False, REA_invoked=False, game_accessed=False,
        native_ready=False, sealed=False, shell_sessions_remaining=0)))


if __name__ == '__main__':
    main()
