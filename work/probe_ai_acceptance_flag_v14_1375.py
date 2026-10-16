"""Read only the statically reviewed AI-response flag and player selectors."""
from __future__ import annotations
import argparse
import ctypes as C
from ctypes import wintypes as W
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work import probe_diplomacy_current as probe
from work.native import lab_protocol_v14_1375 as lab

REPORT = ROOT / 'work/candidates/offered-fleet-ai-response-1375/report.json'
REPORT_SHA = 'f7eeae58d29902ca3999c7bd00e47dacde43e64c72ca215a6df47417e015eee5'


def check_report():
    lab.require(REPORT.stat().st_size <= 2 * 1024 * 1024, 'Static report exceeds bound')
    raw = REPORT.read_bytes()
    lab.require(hashlib.sha256(raw).hexdigest() == REPORT_SHA, 'Static evidence changed')


def held_identity(process):
    created, exited, cpu_kernel, cpu_user = (W.FILETIME() for _ in range(4))
    lab.require(process.kernel.GetProcessTimes(process.reader.handle, C.byref(created),
                C.byref(exited), C.byref(cpu_kernel), C.byref(cpu_user)), 'No held identity')
    creation = (created.dwHighDateTime << 32) | created.dwLowDateTime
    exit_time = (exited.dwHighDateTime << 32) | exited.dwLowDateTime
    lab.require(f'{creation:016x}' == process.creation and exit_time == 0, 'Identity changed/exited')
    return dict(creation_filetime=creation, exit_filetime=exit_time)


def read_pass(process):
    reader = process.reader
    identity = process.snapshot()
    game = int(identity['world_cookie'], 16)
    def byte(offset):
        return reader.read(game + offset, 1)[0]
    def qword(offset):
        return struct.unpack('<Q', reader.read(game + offset, 8))[0]
    fields = dict(positive_response_flag=byte(0x23a1), primary_player=qword(0x1e60),
                  selector_byte=byte(0x1e66), alternate_player=qword(0x1e68),
                  alternate_enabled_byte=byte(0x1e6f))
    lab.require(fields['positive_response_flag'] in (0, 1), 'Noncanonical flag')
    selected = fields['alternate_player'] if (fields['selector_byte'] == 7 and
               fields['alternate_enabled_byte'] != 0) else fields['primary_player']
    database = reader.qword(reader.base + probe.DATABASE_POINTER_RVA)
    array = reader.qword(database + 0x118)
    selected_country = probe.country_identity(reader, array, (selected >> 32) & 0xffff, selected)
    lab.require(selected_country is not None, 'Selected full country identity unavailable')
    lab.require(process.snapshot() == identity, 'World/date/player changed within pass')
    return dict(identity=identity, fields=fields, selected_country=selected_country)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--creation', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    lab.require(output.parent == lab.OUTPUT.resolve() and not output.exists(), 'Use new v14 evidence path')
    check_report()
    executable = probe.game_exe()
    build, signature = probe.verified_executable(executable)
    started = datetime.now(timezone.utc).isoformat()
    with lab.LiveLabProcess(args.pid, expected_creation=args.creation) as process:
        held_before = held_identity(process)
        passes = [read_pass(process), read_pass(process)]
        lab.require(passes[0] == passes[1], 'Typed fixed-width passes changed')
        held_after = held_identity(process)
        lab.require(held_before == held_after, 'Held creation changed')
        lab.require(probe.pe_signature(process.reader, process.reader.base) == signature, 'Live PE changed')
        final_build, final_signature = probe.verified_executable(executable)
        lab.require(final_build == build and final_signature == signature, 'Disk EXE changed')
        check_report()
        report = dict(schema_version=1, kind='ai_acceptance_flag_read_only_v14',
            static_report_sha256=REPORT_SHA, captured_started_utc=started,
            captured_finished_utc=datetime.now(timezone.utc).isoformat(), build=build,
            read_only=True, native_calls=0, memory_writes=0, atomic_snapshot=False,
            paused_verified=False, strict_single_player_verified=False, world_epoch_verified=False,
            execution_authorized=False, production_ready=False, held_identity=[held_before, held_after],
            passes=passes, bytes_read=process.reader.bytes_read)
        with output.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(report, stream, indent=2, ensure_ascii=True)
            stream.write('\n')
    print(json.dumps(dict(output=str(output), read_only=True,
          flag=passes[0]['fields']['positive_response_flag'], selected=passes[0]['selected_country'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
