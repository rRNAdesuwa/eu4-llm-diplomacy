"""New regression tests only, inside reviewed Job r3; never owned attach smoke."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from evidence import require
from protocol import HERE, PYTHON, pin, read_bound, verify_sources, load_reviewed_job, write_json_new

OUT = HERE/'offline-r2'


def log_pin(path):
    raw = Path(path).read_bytes()
    require(len(raw) <= 65536, 'offline_log_bound')
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def check():
    initial = verify_sources()
    receipt = json.loads(read_bound(OUT/'receipt.json'))
    require(receipt['manifest_sha256'] == initial['manifest_sha256'] and receipt['passed'] is True,
            'offline_receipt_or_manifest')
    for name, expected in receipt['output_pins'].items():
        require(name in ('stdout.txt', 'stderr.txt') and log_pin(OUT/name) == expected,
                'offline_output_changed')
    state = receipt['job']
    require(state['error'] is None and state['exit_code'] == 0 and state['direct_child_collected']
            and state['job_active_processes_final'] == 0 and receipt['new_tests'] == 7,
            'offline_job_receipt')
    print(json.dumps(dict(status='offline_r2_pins_match', source_manifest_sha256=initial['manifest_sha256'],
        tests_reexecuted=False, fixture_started=False, REA_executed=False, Frida_executed=False)))


def run():
    initial = verify_sources()
    OUT.mkdir()  # Exclusive: do not silently repeat or overwrite a test run.
    job = load_reviewed_job()
    command = [str(PYTHON), '-B', str(HERE/'test_profile_r2.py')]
    state = job.run_cli_tree(command, str(HERE), OUT/'stdout.txt', OUT/'stderr.txt',
                             timeout_seconds=45, memory_limit=768*1024*1024)
    stdout, stderr = (OUT/'stdout.txt').read_bytes(), (OUT/'stderr.txt').read_bytes()
    summary = re.search(rb'Ran ([0-9]+) tests? in [0-9.]+s\r?\n\r?\nOK\r?\n?\Z', stderr)
    final = verify_sources()
    passed = (state['error'] is None and state['exit_code'] == 0 and state['direct_child_collected']
        and state['job_active_processes_final'] == 0 and state['job_total_processes'] == 1
        and not state['completed_command_descendants_terminated'] and stdout == b''
        and summary is not None and summary.group(1) == b'7' and final == initial)
    receipt = dict(schema='REA-OWNED-SMOKE-NEW-OFFLINE-REGRESSIONS/2', passed=passed,
        manifest_sha256=initial['manifest_sha256'], command=command, job=state,
        new_tests=7 if summary is not None and summary.group(1) == b'7' else None,
        output_pins={name: log_pin(OUT/name) for name in ('stdout.txt', 'stderr.txt')},
        existing_parser_JS_job_host_suites_reexecuted=False,
        fake_controller_Popen_only=True, Node_executed=False, fixture_started=False,
        REA_executed=False, Frida_executed=False, game_accessed=False,
        native_game_calls=0, native_ready=False, lease=False)
    write_json_new(OUT/'receipt.json', receipt)
    print(json.dumps(dict(status='pass' if passed else 'failed', tests=receipt['new_tests'],
        receipt=pin(OUT/'receipt.json'), active=state['job_active_processes_final'],
        peak_job_commit=state['peak_job_commit'], Frida_executed=False)))
    return 0 if passed else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    if parser.parse_args().check:
        check()
    else:
        raise SystemExit(run())
