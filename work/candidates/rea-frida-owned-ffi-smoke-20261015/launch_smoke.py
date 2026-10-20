"""check is file-only; run-reviewed is reserved for a later reviewed execution.

No external target PID, endpoint, executable, script or duration can be supplied.
"""
import argparse
import ctypes
from pathlib import Path
import re
import secrets
import sys

from evidence import extract, require, strict_json
from protocol import (HERE, OUTPUT, PYTHON, NODE, REA, verify_sources, load_reviewed_job,
                      write_json_new, read_bound, pin, require_clean_job)


def launch():
    require(sys.platform == 'win32' and ctypes.sizeof(ctypes.c_void_p) == 8, 'win64_only')
    require(Path(sys.executable).resolve() == PYTHON.resolve(), 'fixed_python_required')
    initial = verify_sources()
    # Creating an exclusive fresh directory is the single invocation claim.
    # There is no automatic retry and no facility to supply an old target PID.
    nonce = secrets.token_hex(16)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    directory = OUTPUT/nonce
    directory.mkdir()
    claim_path = directory/'claim.json'
    write_json_new(claim_path, dict(schema='REA-OWNED-FFI-SMOKE-CLAIM/1', nonce=nonce,
                                  manifest_sha256=initial['manifest_sha256']))
    job = load_reviewed_job()
    command = [str(PYTHON), '-B', str(HERE/'controller.py'), '--claim', str(claim_path)]
    receipt = dict(schema='REA-OWNED-FFI-SMOKE-LAUNCHER/1', status='unknown', nonce=nonce,
        manifest_sha256=initial['manifest_sha256'], controller_argv=command,
        job=None, controller_receipt=None, error=None, source_postcheck=False,
        game_accessed=False, native_game_calls=0, native_ready=False, native_ABI_ready=False, lease=False,
        validation_scope='two fixed kernel32 calls in our waiting fixture; no EU4, action ABI or main-frame provenance')
    try:
        receipt['job'] = job.run_cli_tree(command, str(HERE), directory/'controller.stdout.txt',
            directory/'controller.stderr.txt', timeout_seconds=45, memory_limit=768*1024*1024)
        state = receipt['job']
        require_clean_job(state)
        require((directory/'controller.stdout.txt').stat().st_size == 0
                and (directory/'controller.stderr.txt').stat().st_size == 0, 'controller_output_not_empty')
        controlled = strict_json(read_bound(directory/'controller-receipt.json'))
        receipt['controller_receipt'] = controlled
        require(controlled['schema'] == 'REA-OWNED-FFI-SMOKE-CONTROLLER/1'
                and controlled['status'] == 'owned_fixture_kernel32_ffi_observed'
                and controlled['nonce'] == nonce and controlled['manifest_sha256'] == initial['manifest_sha256']
                and controlled['error'] is None and controlled['source_postcheck'] is True,
                'controller_not_clean')
        fixture, cli = controlled['fixture'], controlled['cli']
        require(type(fixture['pid']) is int and fixture['pid'] > 0
                and fixture['target_selected_from_own_Popen'] is True
                and fixture['external_target_pid_accepted'] is False
                and type(fixture['creation']) is str and re.fullmatch('[0-9a-f]{16}', fixture['creation'])
                and fixture['creation'] == fixture['post_creation']
                and fixture['alive_after_provider_cleanup'] is True, 'fixture_identity_receipt')
        cleanup = controlled['fixture_cleanup']
        require(cleanup['owned_child_pid'] == fixture['pid'] and cleanup['collected'] is True
                and cleanup['handle_closed'] is True and cleanup['exit_code'] == 0
                and cleanup['error'] is None and cleanup['graceful_stop_sent'] is True
                and cleanup['terminate_used'] is False, 'fixture_not_collected')
        script = directory/'rendered-smoke.js'
        expected_argv = [str(NODE), str(REA/'scripts/rea.mjs'),
            'instrument-with-frida', 'attach', str(fixture['pid']), '--duration-ms', '1500',
            '--script-file', str(script), '--device-id', 'local', '--format', 'json', '--full-output']
        require(cli['argv'] == expected_argv and cli['exit_code'] == 0 and cli['error'] is None
                and cli['collected'] is True, 'cli_argv_or_collection')
        rendered = controlled['rendered_script']
        require(rendered['path'] == str(script) and pin(script) ==
                dict(bytes=rendered['bytes'], sha256=rendered['sha256']), 'rendered_source_receipt')
        parsed = extract(read_bound(directory/'rea.stdout.json'), pid=fixture['pid'], nonce=nonce,
            script_path=str(script), script_sha256=rendered['sha256'])
        require(parsed == controlled['parsed_observation'], 'raw_evidence_receipt_disagrees')
        final = verify_sources()
        require(final == initial, 'source_changed_after_collected_job')
        receipt['source_postcheck'] = True
        receipt['status'] = 'owned_fixture_kernel32_ffi_observed'
    except BaseException as exc:
        receipt['error'] = dict(type=type(exc).__name__, code='owned_smoke_launch_refused_or_failed')
    write_json_new(directory/'launcher-receipt.json', receipt)
    print(receipt['status']+' '+str(directory/'launcher-receipt.json'))
    return 0 if receipt['status'] == 'owned_fixture_kernel32_ffi_observed' else 1


def main():
    parser = argparse.ArgumentParser(description='Prepared candidate, no external target accepted')
    parser.add_argument('operation', choices=('check', 'run-reviewed'))
    operation = parser.parse_args().operation
    if operation == 'check':
        value = verify_sources()
        print('source_pins_match '+value['manifest_sha256']+' runtime_executed_by_check=false')
        return 0
    return launch()


if __name__ == '__main__':
    raise SystemExit(main())
