"""Read-only bounded diplomacy snapshot with a held exact process identity."""
from __future__ import annotations
import argparse
import ctypes as C
from ctypes import wintypes as W
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work import probe_diplomacy_current as probe
from work.native import lab_protocol_v15_1375 as lab


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', required=True, type=int)
    parser.add_argument('--creation', required=True)
    parser.add_argument('--before-injection', action='store_true')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    lab.require(output.parent == lab.OUTPUT.resolve() and not output.exists(),
                'Use a new evidence path in the v15 output directory')
    build, _ = probe.verified_executable(probe.game_exe())
    with lab.LiveLabProcess(args.pid, expected_creation=args.creation,
                            require_loaded=not args.before_injection) as process:
        started = datetime.now(timezone.utc).isoformat()
        initial = process.snapshot()
        state = probe.inspect_state(process.reader, process.reader.base,
                                    slots=256, actor='FRA', target='ENG')
        final = process.snapshot()
        lab.require(initial == final, 'World/date/player changed during capture')
        created, exited, kernel_time, user_time = (W.FILETIME() for _ in range(4))
        lab.require(process.kernel.GetProcessTimes(process.reader.handle, C.byref(created),
                    C.byref(exited), C.byref(kernel_time), C.byref(user_time)),
                    'Cannot recheck the held process identity')
        creation = (created.dwHighDateTime << 32) | created.dwLowDateTime
        exit_time = (exited.dwHighDateTime << 32) | exited.dwLowDateTime
        lab.require(f'{creation:016x}' == process.creation and exit_time == 0,
                    'Process identity changed or exited')
        report = {'schema_version': 1, 'read_only': True,
            'captured_at_utc': datetime.now(timezone.utc).isoformat(),
            'capture_started_at_utc': started, 'build': build,
            'source': {'kind': 'live_process', 'pid': args.pid,
                'module_base': hex(process.reader.base),
                'process_creation_filetime': creation, 'process_exit_filetime': exit_time,
                'access': ['PROCESS_QUERY_INFORMATION', 'PROCESS_VM_READ'],
                'atomic_snapshot': False, 'held_identity_verified_before_and_after': True},
            'read_budget': {'per_read_max_bytes': probe.MAX_READ,
                'total_max_bytes': probe.MAX_TOTAL_READ, 'country_slot_max': probe.MAX_SLOTS,
                'diplomat_entry_max': probe.MAX_DIPLOMATS,
                'bytes_requested': process.reader.bytes_read},
            'offset_profile': {'database_pointer_rva': hex(probe.DATABASE_POINTER_RVA),
                               'game_pointer_rva': hex(probe.GAME_POINTER_RVA)},
            'state': state, 'identity_before_and_after': [initial, final]}
        with output.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(report, stream, ensure_ascii=True, indent=2)
            stream.write('\n')
    print(json.dumps({'output': str(output), 'read_only': True, 'pid': args.pid,
                      'creation': args.creation, 'world_cookie': initial['world_cookie'],
                      'raw_date': initial['raw_date'], 'countries': len(state['countries'])}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
