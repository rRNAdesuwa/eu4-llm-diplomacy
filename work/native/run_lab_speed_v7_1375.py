"""Run one bounded research speed lease with an independent process supervisor.

Requires an explicitly disposable campaign. A failed/unknown lease terminates
only the held, SHA/path/PID/creation-verified game process; no native retry or
second pause request is attempted. Importing this module performs no operation.
"""
from __future__ import annotations

import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from work.native import lab_protocol_v7_1375 as lab

DEADLINE_SECONDS = 12.0


def paused_state(reader):
    """Small read-only subset of the reviewed pause predicate, SP lab only."""
    q = reader.qword
    game = q(reader.base + 0x233FE78)
    server = q(game + 0x1E00)
    lab.require(q(server) == reader.base + 0x1CB8460, "Unexpected server vtable")
    manager = q(server + 0x418)
    lab.require(q(manager + 0x50) == server, "Pause manager identity mismatch")
    # This guard narrows this disposable experiment. False classification does
    # not, on its own, establish a general single-player security boundary.
    lab.require(reader.read(server + 0x19F1, 1) == b'\0', "Unsupported multiplayer-classifier branch")
    manual = reader.read(manager + 0x48, 1)[0]
    begin, end = q(manager), q(manager + 8)
    lab.require(manual in (0, 1) and ((begin == 0) == (end == 0)) and end >= begin
                and (end - begin) % 8 == 0 and end - begin <= 2048, "Malformed pause state")
    player, date = q(game + 0x1E60), reader.integer(game + 0x1DD0)
    lab.require(player == 0x0100007A00415246 and date > 0
                and reader.read(game + 0x7485, 1) == b'\0' and q(game + 0x74C8) == 0,
                "World identity or load guard failed")
    lab.require(q(reader.base + 0x233FE78) == game and q(game + 0x1E00) == server
                and q(server + 0x418) == manager, "Pause observation changed roots")
    return {'game': game, 'server': server, 'pause_manager': manager,
            'player': player, 'raw_date': date, 'paused': bool(manual or begin != end),
            'native_speed_index': reader.integer(game + 0x1E08)}


def same_world(before, after):
    return all(before[key] == after[key] for key in ('game', 'server', 'pause_manager', 'player')) \
        and after['raw_date'] >= before['raw_date']


def decision(evidence, sequence, before, after, elapsed):
    """Pure decision logic; unreadable/uncertain evidence is handled by caller."""
    if not same_world(before, after):
        return 'terminate_world_changed'
    if elapsed >= DEADLINE_SECONDS:
        return 'terminate_deadline'
    frame = evidence.get('latest_frame', {})
    if frame.get('session_frozen') or frame.get('world_changed') or frame.get('thread_changed'):
        return 'terminate_session_frozen'
    request = evidence.get('requests', {}).get(sequence)
    if request and request.get('lease_complete'):
        complete = request['lease_complete']
        if complete.get('session_frozen') is False and complete.get('readback_matches') is True \
                and complete.get('paused_readback') is True and after['paused'] \
                and not evidence.get('lease_pending') and not evidence.get('pending'):
            return 'completed'
        return 'terminate_pause_unverified'
    return 'wait'


def open_exact_termination_handle(process):
    kernel = process.kernel
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.TerminateProcess.argtypes = [W.HANDLE, W.UINT]
    kernel.TerminateProcess.restype = W.BOOL
    kernel.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
    kernel.WaitForSingleObject.restype = W.DWORD
    # Hold this handle before publishing, never reopen by PID on failure.
    handle = kernel.OpenProcess(0x0400 | 0x100000 | 0x0001, False, process.pid)
    if not handle:
        raise C.WinError(C.get_last_error())
    try:
        times = [W.FILETIME() for _ in range(4)]
        lab.require(kernel.GetProcessTimes(handle, *(C.byref(t) for t in times)), "Cannot verify termination handle")
        raw = lambda t: (t.dwHighDateTime << 32) | t.dwLowDateTime
        lab.require(f'{raw(times[0]):016x}' == process.creation and raw(times[1]) == 0,
                    "Termination handle refers to a different or exited process")
        return handle
    except BaseException:
        kernel.CloseHandle(handle)
        raise


def supervisor_identity(kernel):
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = W.HANDLE
    times = [W.FILETIME() for _ in range(4)]
    lab.require(kernel.GetProcessTimes(kernel.GetCurrentProcess(), *(C.byref(t) for t in times)),
                'Cannot identify the supervisor process')
    creation = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
    lab.require(creation > 0, 'Supervisor has no creation identity')
    return os.getpid(), f'{creation:016x}'


def run(pid, creation, sequence, speed):
    manifest, _ = lab.verify_build()
    lab.require(manifest.get('running_speed_enabled') is True, 'Build has no reviewed running-speed lease')
    with lab.LiveLabProcess(pid, expected_creation=creation) as process:
        session = lab.session_path(lab.OUTPUT, pid, creation)
        metadata = lab.read_session_metadata(session, pid, creation)
        evidence = lab.read_evidence(session, metadata)
        lab.check_ready(evidence, process.snapshot(), lab.uptime_ms(), operation='speed')
        lab.require(sequence == evidence['last_sequence'] + 1, 'Sequence is not the next native request')
        before = paused_state(process.reader)
        lab.require(before['paused'], 'Supervisor requires a paused baseline')
        for suffix in ('host-intent', 'request', 'claim', 'supervisor.jsonl'):
            path = session / f'{sequence:020}.{suffix}'
            lab._no_links(path)
            lab.require(not path.exists(), 'This sequence has already been attempted')
        parent_pid, parent_creation = supervisor_identity(process.kernel)
        handle = open_exact_termination_handle(process)
        child = None
        published_possible = False
        completed = False
        report_path = session / f'{sequence:020}.supervisor.jsonl'
        try:
            with report_path.open('x', encoding='utf-8', newline='\n') as report:
                def record(event, **fields):
                    row = {'event': event, 'pid': pid, 'creation': creation, 'sequence': sequence,
                           'speed': speed, 'retry_allowed': False, **fields}
                    report.write(json.dumps(row, sort_keys=True) + '\n')
                    report.flush()
                    os.fsync(report.fileno())
                record('supervisor_armed', deadline_seconds=DEADLINE_SECONDS, before=before)
                started = time.monotonic()
                # A file avoids pipe saturation and keeps publication diagnostics
                # available if the parent must stop the exact disposable process.
                with (session / f'{sequence:020}.publisher-output.txt').open('x', encoding='utf-8') as publisher:
                    try:
                        published_possible = True
                        child = subprocess.Popen([
                            sys.executable, '-B', str(ROOT / 'tools/request_diplomacy_lab_v7.py'),
                            '--pid', str(pid), '--creation', creation, 'speed', str(speed),
                            '--sequence', str(sequence), '--ttl-ms', '5000', '--publish',
                            '--watchdog-parent', str(parent_pid), '--watchdog-creation', parent_creation],
                            cwd=ROOT, stdout=publisher, stderr=subprocess.STDOUT,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                        while True:
                            elapsed = time.monotonic() - started
                            if elapsed >= DEADLINE_SECONDS:
                                raise RuntimeError('Independent supervisor deadline elapsed')
                            current = lab.read_evidence(session, metadata)
                            observed = paused_state(process.reader)
                            outcome = decision(current, sequence, before, observed, elapsed)
                            if outcome.startswith('terminate_'):
                                raise RuntimeError(outcome)
                            if outcome == 'completed':
                                # Completion must be persisted and independently
                                # observed paused, with no outstanding native work.
                                lab.require(child.wait(timeout=1) == 0, 'Publisher failed despite native lease completion')
                                completed = True
                                record('supervisor_complete', after=observed, elapsed_seconds=elapsed,
                                       native_lease_complete=current['requests'][sequence]['lease_complete'])
                                return {'status': 'completed_and_paused', 'report': str(report_path),
                                        'before_date': before['raw_date'], 'after_date': observed['raw_date']}
                            if child.poll() not in (None, 0):
                                raise RuntimeError('Publisher returned an error; no retry')
                            time.sleep(0.05)
                    except BaseException as error:
                        # Even a paused observation cannot prove that an already
                        # published request will never execute on a later frame.
                        # Terminate this held process, not another native call.
                        if published_possible and not completed:
                            stopped = process.kernel.WaitForSingleObject(handle, 0) == 0
                            if not stopped:
                                if not process.kernel.TerminateProcess(handle, 0xE1375006):
                                    raise C.WinError(C.get_last_error()) from error
                                stopped = process.kernel.WaitForSingleObject(handle, 5000) == 0
                            record('supervisor_stopped_disposable_process', reason=str(error), stopped=stopped)
                            lab.require(stopped, 'Exact disposable process did not exit within five seconds')
                        raise
        finally:
            if child is not None and child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            process.kernel.CloseHandle(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--creation', required=True)
    parser.add_argument('--sequence', type=int, required=True)
    parser.add_argument('--speed', type=int, choices=range(1, 6), required=True)
    parser.add_argument('--ack-disposable', action='store_true', required=True)
    args = parser.parse_args()
    try:
        result = run(args.pid, args.creation, args.sequence, args.speed)
        print(json.dumps(result))
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        print('run_lab_speed_v7_1375: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
