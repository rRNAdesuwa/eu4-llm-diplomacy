"""Future reviewed own-fixture smoke controller. Never accepts an external PID.

Only launch_smoke.py may launch this inside the audited r3 Job. No smoke has
been executed as part of preparing this source. WinAPI work is lazy, in main.
"""
import argparse
import ctypes
from ctypes import wintypes as w
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from evidence import extract, require, strict_json
from protocol import (HERE, OUTPUT, PYTHON, NODE, REA, MANIFEST, read_bound, pin,
                      verify_sources, load_reviewed_job, write_json_new)


def owned_kernel():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    declarations = [
        ('GetCurrentProcess', [], w.HANDLE),
        ('IsProcessInJob', [w.HANDLE, w.HANDLE, ctypes.POINTER(w.BOOL)], w.BOOL),
        ('GetProcessTimes', [w.HANDLE, ctypes.POINTER(w.FILETIME), ctypes.POINTER(w.FILETIME),
                            ctypes.POINTER(w.FILETIME), ctypes.POINTER(w.FILETIME)], w.BOOL),
        ('QueryInformationJobObject', [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD,
                                      ctypes.c_void_p], w.BOOL),
    ]
    for name, arguments, result in declarations:
        function = getattr(kernel, name)
        function.argtypes, function.restype = arguments, result
    return kernel


def creation(kernel, child):
    # Only the Popen-created handle. There is deliberately no OpenProcess API.
    times = [w.FILETIME() for _ in range(4)]
    require(kernel.GetProcessTimes(w.HANDLE(int(child._handle)),
            *(ctypes.byref(value) for value in times)), 'own_child_creation_query')
    return format((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime, '016x')


def contained(kernel, job):
    assigned = w.BOOL()
    require(kernel.IsProcessInJob(kernel.GetCurrentProcess(), None, ctypes.byref(assigned))
            and assigned.value, 'controller_not_in_job')
    limits = job.Extended()
    require(kernel.QueryInformationJobObject(None, 9, ctypes.byref(limits),
            ctypes.sizeof(limits), None), 'current_job_limits_query')
    basic = limits.BasicLimitInformation
    require(basic.LimitFlags & 0x2308 == 0x2308 and basic.ActiveProcessLimit == 8
            and limits.ProcessMemoryLimit == 768*1024*1024
            and limits.JobMemoryLimit == 768*1024*1024, 'reviewed_job_limits_required')
    return dict(in_job=True, limit_flags=basic.LimitFlags, active_limit=basic.ActiveProcessLimit,
                process_memory_limit=limits.ProcessMemoryLimit, job_memory_limit=limits.JobMemoryLimit,
                identity_basis='reviewed launcher exact-handle assignment plus inherited job')


def wait_ready(child, path, expected_nonce):
    deadline = time.monotonic()+5
    while True:
        require(child.poll() is None, 'fixture_exited_before_ready')
        size = path.stat().st_size
        require(size <= 1024, 'fixture_ready_output_bound')
        if size:
            raw = read_bound(path, 1024)
            if raw.endswith(b'\n'):
                value = strict_json(raw, 1024)
                require(type(value) is dict and set(value) == {'schema', 'pid', 'nonce'}
                        and value == dict(schema='REA-OWNED-FIXTURE-READY/1',
                                          pid=child.pid, nonce=expected_nonce)
                        and type(value['pid']) is int, 'fixture_ready_binding')
                return value
        require(time.monotonic() < deadline, 'fixture_ready_timeout')
        time.sleep(0.02)


def cli_argv(pid, script):
    require(type(pid) is int and 0 < pid <= 0xffffffff, 'own_cli_pid')
    return [str(NODE), str(REA/'scripts/rea.mjs'), 'instrument-with-frida', 'attach', str(pid),
            '--duration-ms', '1500', '--script-file', str(script), '--device-id', 'local',
            '--format', 'json', '--full-output']


def run_cli(argv, directory):
    stdout_path, stderr_path = directory/'rea.stdout.json', directory/'rea.stderr.txt'
    cli, exit_code, error = None, None, None
    started = time.monotonic()
    try:
        with stdout_path.open('xb') as stdout, stderr_path.open('xb') as stderr:
            cli = subprocess.Popen(argv, cwd=REA, stdin=subprocess.DEVNULL, stdout=stdout,
                stderr=stderr, creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
            deadline = time.monotonic()+25
            while cli.poll() is None:
                require(all(path.stat().st_size <= 65536 for path in (stdout_path, stderr_path)),
                        'cli_output_bound')
                require(time.monotonic() < deadline, 'cli_wait_timeout')
                time.sleep(0.02)
            exit_code = cli.wait(timeout=3)
            require(all(path.stat().st_size <= 65536 for path in (stdout_path, stderr_path)),
                    'cli_final_output_bound')
    except BaseException as exc:
        # Do not persist arbitrary exception messages, arguments or environments.
        error = dict(type=type(exc).__name__, code='owned_cli_failed')
    finally:
        if cli is not None:
            try:
                if cli.poll() is None:
                    cli.terminate()  # Only this controller's exact Popen handle.
                exit_code = cli.wait(timeout=3)
            finally:
                cli._handle.Close()
    return dict(argv=argv, exit_code=exit_code, error=error,
                seconds=round(time.monotonic()-started, 3), collected=cli is not None,
                stdout='rea.stdout.json', stderr='rea.stderr.txt', acceptance_limit_per_stream=65536,
                output_writer_may_overshoot_before_refusal=True)


def cleanup_fixture(child, nonce):
    result = dict(owned_child_pid=child.pid, graceful_stop_sent=False, terminate_used=False,
                  collected=False, exit_code=None, handle_closed=False, error=None)
    try:
        if child.poll() is None:
            try:
                child.stdin.write((nonce+'\n').encode('ascii'))
                child.stdin.flush()
                result['graceful_stop_sent'] = True
            except (OSError, ValueError):
                pass
        if child.stdin is not None:
            try:
                child.stdin.close()
            except (OSError, ValueError):
                pass  # Pipe cleanup must not skip collecting our child.
        try:
            result['exit_code'] = child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            child.terminate()  # Never a PID-selected or existing process.
            result['terminate_used'] = True
            result['exit_code'] = child.wait(timeout=3)
        result['collected'] = child.poll() is not None
    except BaseException as exc:
        result['error'] = dict(type=type(exc).__name__, code='own_fixture_cleanup_failed')
    finally:
        child._handle.Close()
        result['handle_closed'] = True
    return result


def run(claim_path):
    require(os.name == 'nt' and ctypes.sizeof(ctypes.c_void_p) == 8, 'win64_only')
    require(Path(sys.executable).resolve() == PYTHON.resolve(), 'fixed_python_required')
    claim_path = Path(claim_path).resolve()
    require(claim_path.name == 'claim.json' and claim_path.parent.parent == OUTPUT.resolve()
            and re.fullmatch('[0-9a-f]{32}', claim_path.parent.name), 'own_claim_path')
    directory = claim_path.parent
    claim = strict_json(read_bound(claim_path, 4096), 4096)
    require(type(claim) is dict and set(claim) == {'schema', 'nonce', 'manifest_sha256'}
            and claim['schema'] == 'REA-OWNED-SMOKE-CLAIM/1'
            and claim['nonce'] == directory.name, 'own_claim_binding')
    initial = verify_sources()
    require(initial['manifest_sha256'] == claim['manifest_sha256'], 'claim_source_changed')
    kernel, job = owned_kernel(), load_reviewed_job()
    job_state = contained(kernel, job)
    child = None
    receipt = dict(schema='REA-OWNED-SMOKE-CONTROLLER/1', status='unknown',
        nonce=claim['nonce'], manifest_sha256=initial['manifest_sha256'], controller_pid=os.getpid(),
        containment=job_state, fixture=None, cli=None, parsed_observation=None, error=None,
        fixture_cleanup=None, source_postcheck=False, game_accessed=False, script_hook_count=0,
        script_target_data_reads=0, script_target_field_writes=0, native_game_calls=0,
        REA_attach_command_attempts=0, script_load_scope='owned waiting fixture only',
        Frida_runtime_injection_expected=True, native_ready=False, lease=False)
    try:
        nonce = claim['nonce']
        with (directory/'fixture.stdout.txt').open('xb') as stdout, (directory/'fixture.stderr.txt').open('xb') as stderr:
            child = subprocess.Popen([str(PYTHON), '-B', str(HERE/'fixture.py'), nonce],
                cwd=HERE, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
            before = creation(kernel, child)
            ready = wait_ready(child, directory/'fixture.stdout.txt', nonce)
            receipt['fixture'] = dict(pid=child.pid, creation=before, ready=ready,
                target_selected_from_own_Popen=True, external_target_pid_accepted=False)
            config = dict(schema='REA-OWNED-SMOKE-CONFIG/1', pid=child.pid, nonce=nonce)
            agent = read_bound(HERE/'smoke.js')
            require(pin(HERE/'smoke.js') == initial['manifest']['candidate_sources']['smoke.js'],
                    'agent_changed_before_render')
            rendered = ('const REA_OWNED_SMOKE_CONFIG = '+json.dumps(config, separators=(',', ':'))+';\n').encode('ascii')+agent
            script = directory/'rendered-smoke.js'
            with script.open('xb') as stream:
                stream.write(rendered)
            rendered_pin = dict(bytes=len(rendered), sha256=hashlib.sha256(rendered).hexdigest())
            receipt['rendered_script'] = dict(path=str(script), **rendered_pin)
            argv = cli_argv(child.pid, script)
            require(argv[3:5] == ['attach', str(child.pid)], 'argv_owned_target_binding')
            receipt['REA_attach_command_attempts'] = 1
            receipt['cli'] = run_cli(argv, directory)
            require(receipt['cli']['error'] is None and receipt['cli']['exit_code'] == 0
                    and receipt['cli']['collected'], 'rea_cli_not_clean')
            require((directory/'rea.stderr.txt').stat().st_size == 0, 'rea_stderr_not_empty')
            require(child.poll() is None and creation(kernel, child) == before,
                    'owned_fixture_identity_or_liveness_changed')
            receipt['fixture']['post_creation'] = before
            receipt['fixture']['alive_after_provider_cleanup'] = True
            require(pin(script) == rendered_pin, 'rendered_source_changed')
            receipt['parsed_observation'] = extract(read_bound(directory/'rea.stdout.json'),
                pid=child.pid, nonce=nonce, script_path=str(script), script_sha256=rendered_pin['sha256'])
            final = verify_sources()
            require(final == initial, 'source_graph_changed_after_smoke')
            receipt['source_postcheck'] = True
    except BaseException as exc:
        receipt['error'] = dict(type=type(exc).__name__, code='owned_smoke_refused_or_failed')
    finally:
        if child is not None:
            receipt['fixture_cleanup'] = cleanup_fixture(child, claim['nonce'])
    cleanup = receipt['fixture_cleanup']
    if (receipt['error'] is None and receipt['parsed_observation'] is not None
            and receipt['source_postcheck'] and cleanup is not None and cleanup['error'] is None
            and cleanup['collected'] and cleanup['handle_closed'] and cleanup['exit_code'] == 0
            and cleanup['graceful_stop_sent'] and not cleanup['terminate_used']):
        receipt['status'] = 'owned_fixture_attach_scriptload_observed'
    write_json_new(directory/'controller-receipt.json', receipt)
    return 0 if receipt['status'] == 'owned_fixture_attach_scriptload_observed' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Internal owned fixture controller; use launcher')
    parser.add_argument('--claim', required=True)
    arguments = parser.parse_args()
    raise SystemExit(run(arguments.claim))
