"""Run only the two new pure suites in reviewed Job r3, or verify their retained receipt."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from evidence import require
from protocol import (HERE, PYTHON, NODE, read_bound, verify_sources, load_reviewed_job,
                      require_clean_job, write_json_new, pin)

OUT = HERE/'offline-r1'


def log_pin(path):
    raw = Path(path).read_bytes()
    require(len(raw) <= 65536, 'offline_log_bound')
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def check():
    initial = verify_sources()
    receipt = json.loads(read_bound(OUT/'receipt.json'))
    require(receipt['passed'] is True and receipt['manifest_sha256'] == initial['manifest_sha256'],
            'offline_receipt_not_matching')
    require(receipt['source_postcheck'] is True and receipt['total_new_tests'] == 10,
            'offline_summary')
    for suite in receipt['suites']:
        require_clean_job(suite['job'])
        require(suite['tests'] == 5 and suite['passed'] is True, 'offline_suite_failure')
    for name, expected in receipt['output_pins'].items():
        require(name in ('python.stdout.txt','python.stderr.txt','node.stdout.txt','node.stderr.txt')
                and log_pin(OUT/name) == expected, 'offline_output_changed')
    print(json.dumps(dict(status='offline_pins_match', manifest_sha256=initial['manifest_sha256'],
        tests_reexecuted=False, fixture_started=False, REA_executed=False, Frida_executed=False)))


def run():
    initial = verify_sources()
    OUT.mkdir()  # Exclusive; preserve failures and never silently rerun either old or new suites.
    job = load_reviewed_job()
    suites = []
    specifications = [('python',[str(PYTHON),'-B',str(HERE/'test_contract.py')]),
        ('node',[str(NODE),'--test','--test-reporter=tap',str(HERE/'test_smoke.js')])]
    for name, command in specifications:
        state = job.run_cli_tree(command, str(HERE), OUT/(name+'.stdout.txt'), OUT/(name+'.stderr.txt'),
                                 timeout_seconds=45, memory_limit=768*1024*1024)
        stdout, stderr = (OUT/(name+'.stdout.txt')).read_bytes(), (OUT/(name+'.stderr.txt')).read_bytes()
        if name == 'python':
            summary = stdout == b'' and re.search(rb'Ran 5 tests in [0-9.]+s\r?\n\r?\nOK\r?\n?\Z', stderr) is not None
        else:
            summary = stderr == b'' and all(re.search(pattern,stdout,re.M) for pattern in
                (rb'^# tests 5\r?$',rb'^# pass 5\r?$',rb'^# fail 0\r?$',rb'^# skipped 0\r?$'))
        clean = True
        try:
            require_clean_job(state)
        except (ValueError, KeyError, TypeError):
            clean = False
        suites.append(dict(name=name, tests=5 if summary else None, command=command,
                           job=state, passed=bool(summary and clean)))
    final = verify_sources()
    passed = all(suite['passed'] for suite in suites) and final == initial
    output_names = [name+'.'+stream+'.txt' for name in ('python','node') for stream in ('stdout','stderr')]
    receipt = dict(schema='REA-OWNED-FFI-OFFLINE-RECEIPT/1', passed=passed,
        manifest_sha256=initial['manifest_sha256'], source_postcheck=final==initial,
        suites=suites, total_new_tests=10 if passed else None,
        output_pins={name:log_pin(OUT/name) for name in output_names},
        pure_Python_parser_and_Node_VM_only=True, old_tests_rerun=False,
        real_fixture_started=False, fixture_started=False, REA_executed=False,
        Frida_binding_imported=False, Frida_executed=False, game_accessed=False,
        actual_NativeFunction_calls=0, native_ready=False, native_ABI_ready=False, lease=False)
    write_json_new(OUT/'receipt.json', receipt)
    print(json.dumps(dict(status='pass' if passed else 'failed', receipt=pin(OUT/'receipt.json'),
        tests=receipt['total_new_tests'], active=[x['job']['job_active_processes_final'] for x in suites],
        peak_job_commit=max(x['job']['peak_job_commit'] for x in suites),
        fixture_started=False, REA_executed=False, Frida_executed=False)))
    return 0 if passed else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        check()
    else:
        raise SystemExit(run())
