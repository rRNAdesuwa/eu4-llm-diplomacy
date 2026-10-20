"""First runs of this smoke's two original pure suites, never Frida or fixture.

The runtime candidate graph stays fixed; this test driver has a separate pin in
its receipt. It does not run the earlier unrelated observer/parser/job suites.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT/'work/candidates/rea-frida-owned-smoke-20261015'
OUT = HERE/'initial-suites-r3'
sys.path.insert(0, str(HERE))
from evidence import require
from protocol import NODE, PYTHON, pin, verify_sources, load_reviewed_job, write_json_new

MANIFEST_SHA = '076ef47c157d6f2bbe47211e071d947ee2b5f5f1770e67f03d66c3e54c869934'


def log(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(65537)
    require(len(raw) <= 65536, 'pure_suite_output_bound')
    return raw


def log_pin(path):
    raw = log(path)
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def clean(state):
    return (state['error'] is None and state['exit_code'] == 0
        and state['direct_child_collected'] and state['job_active_processes_final'] == 0
        and 1 <= state['job_total_processes'] <= 8
        and not state['completed_command_descendants_terminated'])


def check():
    initial = verify_sources()
    receipt = json.loads((OUT/'receipt.json').read_bytes())
    require(initial['manifest_sha256'] == receipt['manifest_sha256'] == MANIFEST_SHA
            and receipt['passed'] is True and receipt['driver'] == pin(Path(__file__)),
            'initial_suites_source_or_receipt')
    for name, expected in receipt['output_pins'].items():
        require(name in ('python.stdout.txt', 'python.stderr.txt', 'node.stdout.txt', 'node.stderr.txt')
                and log_pin(OUT/name) == expected, 'initial_suites_output_changed')
    require(all(clean(case['job']) for case in receipt['suites']), 'initial_suites_cleanup')
    print(json.dumps(dict(status='initial_suites_pins_match', tests_reexecuted=False,
        fixture_started=False, REA_executed=False, Frida_executed=False)))


def run():
    initial = verify_sources()
    require(initial['manifest_sha256'] == MANIFEST_SHA, 'fixed_candidate_manifest_changed')
    driver = pin(Path(__file__))
    OUT.mkdir()
    job = load_reviewed_job()
    suites = []
    for name, argv, tests in (
        ('python', [str(PYTHON), '-B', str(HERE/'test_contract.py')], 9),
        ('node', [str(NODE), '--test', '--test-reporter=tap', str(HERE/'test_smoke.js')], 3),
    ):
        state = job.run_cli_tree(argv, str(HERE), OUT/(name+'.stdout.txt'),
            OUT/(name+'.stderr.txt'), timeout_seconds=45, memory_limit=768*1024*1024)
        stdout, stderr = log(OUT/(name+'.stdout.txt')), log(OUT/(name+'.stderr.txt'))
        if name == 'python':
            summary = (stdout == b'' and re.search(
                rb'Ran 9 tests in [0-9.]+s\r?\n\r?\nOK\r?\n?\Z', stderr) is not None)
        else:
            summary = (stderr == b'' and all(re.search(pattern, stdout, re.M) is not None
                for pattern in (rb'^# tests 3\r?$', rb'^# pass 3\r?$', rb'^# fail 0\r?$')))
        suites.append(dict(name=name, test_class='ContractTests' if name == 'python' else 'smoke NodeVM',
            tests=tests, first_execution=True, command=argv, job=state,
            summary_passed=summary, passed=clean(state) and summary))
    final = verify_sources()
    passed = all(case['passed'] for case in suites) and final == initial and pin(Path(__file__)) == driver
    receipt = dict(schema='REA-OWNED-SMOKE-INITIAL-PURE-SUITES/3', passed=passed,
        manifest_sha256=initial['manifest_sha256'], driver=driver, suites=suites,
        output_pins={name: log_pin(OUT/name) for name in
            ('python.stdout.txt', 'python.stderr.txt', 'node.stdout.txt', 'node.stderr.txt')},
        source_postcheck=final == initial, earlier_NewProfileTests_reexecuted=False,
        unrelated_old18JS_41parser_5job_15host_tests_reexecuted=False,
        Node_VM_only=True, fixture_started=False, REA_executed=False, Frida_executed=False,
        game_accessed=False, native_game_calls=0, native_ready=False, lease=False)
    write_json_new(OUT/'receipt.json', receipt)
    print(json.dumps(dict(status='pass' if passed else 'failed',
        suites=[dict(name=case['name'], tests=case['tests'], passed=case['passed'],
                     active=case['job']['job_active_processes_final'],
                     peak_job_commit=case['job']['peak_job_commit']) for case in suites],
        receipt=pin(OUT/'receipt.json'), Frida_executed=False)))
    return 0 if passed else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    if parser.parse_args().check:
        check()
    else:
        raise SystemExit(run())
