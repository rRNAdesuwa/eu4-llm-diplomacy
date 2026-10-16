"""Read-only, build-specific EU4 structural probe. No calls or memory writes.

Offsets below are derived from this build's offline instruction references.
Country field meanings remain candidates until compared with game observations.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
from pathlib import Path
import sys
import time

from local_config import game_exe

EXPECTED_HASH = 'b23fa0e1f698d31b01cdd1c3817a675805d8c6286cb66f9c231e6e2a42544d77'
GAME = game_exe()
DATABASE_POINTER_RVA = 0x233D8B0
GAME_POINTER_RVA = 0x233FE58

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', required=True, type=int)
    parser.add_argument('--peace-ui', action='store_true', help='Bounded read-only pointer graph search for the native peace window')
    parser.add_argument('--peace-heap', action='store_true', help='Also search committed private writable regions, bounded by 4 GiB and 20 seconds')
    parser.add_argument('--peace-address', type=lambda value: int(value, 0), help='Recheck an already located window address; all identity checks still apply')
    parser.add_argument('--output', type=Path, default=Path(__file__).parent / 'runtime/native-state-probe.json')
    args = parser.parse_args()
    if sys.platform != 'win32' or C.sizeof(C.c_void_p) != 8:
        raise RuntimeError('Requires 64-bit Windows Python')
    if hashlib.sha256(GAME.read_bytes()).hexdigest() != EXPECTED_HASH:
        raise RuntimeError('Unsupported executable build')

    kernel = C.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.CloseHandle.restype = W.BOOL
    kernel.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = W.BOOL
    kernel.K32EnumProcessModulesEx.argtypes = [W.HANDLE, C.POINTER(W.HMODULE), W.DWORD, C.POINTER(W.DWORD), W.DWORD]
    kernel.K32EnumProcessModulesEx.restype = W.BOOL
    kernel.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
    kernel.ReadProcessMemory.restype = W.BOOL

    # QUERY_INFORMATION | VM_READ only. No VM_WRITE, VM_OPERATION or CREATE_THREAD.
    handle = kernel.OpenProcess(0x0400 | 0x0010, False, args.pid)
    if not handle:
        raise C.WinError(C.get_last_error())
    try:
        path = C.create_unicode_buffer(32768)
        length = W.DWORD(len(path))
        if not kernel.QueryFullProcessImageNameW(handle, 0, path, C.byref(length)):
            raise C.WinError(C.get_last_error())
        if Path(path.value).resolve() != GAME.resolve():
            raise RuntimeError('PID does not match the expected game executable')
        modules = (W.HMODULE * 1024)()
        needed = W.DWORD()
        if not kernel.K32EnumProcessModulesEx(handle, modules, C.sizeof(modules), C.byref(needed), 3):
            raise C.WinError(C.get_last_error())
        if not needed.value or needed.value > C.sizeof(modules):
            raise RuntimeError('Invalid or oversized module list')
        base = modules[0]

        def read(address, size):
            if not address or address < 0x10000 or size > 1048576:
                raise RuntimeError('Invalid read range')
            buffer = C.create_string_buffer(size)
            actual = C.c_size_t()
            if not kernel.ReadProcessMemory(handle, address, buffer, size, C.byref(actual)) or actual.value != size:
                raise C.WinError(C.get_last_error())
            return buffer.raw

        def qword(address):
            return int.from_bytes(read(address, 8), 'little')

        if read(base, 2) != b'MZ':
            raise RuntimeError('Invalid module base')
        database = qword(base + DATABASE_POINTER_RVA)
        game = qword(base + GAME_POINTER_RVA)
        if not database or not game:
            raise RuntimeError('Game world is not initialized; load a campaign first')
        array = qword(database + 0x118)
        player_handle = qword(game + 0x1E60)
        player_slot = (player_handle >> 32) & 0xffff
        player_country = qword(array + player_slot * 8) if player_slot < 4096 else 0
        player_object_handle = qword(player_country + 0x20) if player_country else 0
        if player_country and ((player_object_handle >> 32) & 0xffff) != player_slot:
            raise RuntimeError('Player handle does not match the candidate country object')
        slots = []
        # Fixed bounded probe, not an assumed total number of countries.
        for index in range(256):
            try:
                country = qword(array + index * 8)
                if not country:
                    continue
                candidate = qword(country + 0x20)
                encoded_index = (candidate >> 32) & 0xffff
                if encoded_index == index:
                    tag_bytes = (candidate & 0xffffff).to_bytes(3, 'little')
                    tag = tag_bytes.decode('ascii') if all(0x20 <= byte <= 0x7e for byte in tag_bytes) else None
                    slots.append({'slot': index, 'pointer': hex(country),
                                  'candidate_handle': hex(candidate), 'index_matches_slot': True, 'tag': tag})
            except OSError:
                continue
        if not slots:
            raise RuntimeError('No structurally consistent country slots; offsets not validated')
        report = {'pid': args.pid, 'binary_sha256': EXPECTED_HASH, 'module_base': hex(base),
                  'database_pointer': hex(database), 'game_pointer': hex(game),
                  'candidate_country_array': hex(array), 'consistent_slots': slots,
                  'candidate_player_slot': player_slot, 'candidate_player_pointer': hex(player_country),
                  'player_tag': (player_object_handle & 0xffffff).to_bytes(3, 'little').decode('ascii'),
                  'scope': 'Read-only slot/handle/tag evidence; no diplomacy API or treasury fields established.'}
        fra_slot = next((item for item in slots if item['tag'] == 'FRA'), None)
        if fra_slot:
            current_date = int.from_bytes(read(game + 0x1DD0, 4), 'little', signed=True)
            country_date = int.from_bytes(read(int(fra_slot['pointer'], 16) + 0x24A0, 4), 'little', signed=True)
            global_date = int.from_bytes(read(game + 0x1D9C, 4), 'little', signed=True)
            global_actor = qword(game + 0x1DA0)
            same_actor = ((global_actor >> 32) & 0xffff) == fra_slot['slot']
            threshold = max(country_date, global_date) if same_actor else country_date
            report['fra_send_date_guard'] = {'current_raw_date': current_date,
                'country_raw_date': country_date, 'global_raw_date': global_date,
                'global_actor_handle': hex(global_actor), 'global_actor_is_fra': same_actor,
                'guard_passes': current_date > threshold,
                'required_raw_date_increment': max(0, threshold + 1 - current_date),
                'note': 'Raw integer date comparison from native send callback; date unit not independently mapped.'}
        if args.peace_ui or args.peace_heap or args.peace_address:
            # Constructor-derived vtable and listener checks; never invoke the callback.
            target_vtable = base + 0x1D760A0
            target_callback = base + 0x130F080
            queue = [(game, 0, 'game')]
            if args.peace_address:
                queue.insert(0, (args.peace_address, 0, 'explicit_candidate'))
            try:
                queue.append((qword(base + 0x23494D0), 0, 'ui_global'))
            except OSError:
                pass
            visited = set()
            matches = []
            cursor = 0
            while cursor < len(queue) and len(visited) < 2048:
                address, depth, route = queue[cursor]
                cursor += 1
                if address in visited or not 0x10000 <= address < 0x00007FFF00000000 or address % 8:
                    continue
                visited.add(address)
                try:
                    blob = read(address, 4096)
                except OSError:
                    try:
                        blob = read(address, 1024)
                    except OSError:
                        continue
                for offset in range(0, len(blob) - 7, 8):
                    value = int.from_bytes(blob[offset:offset + 8], 'little')
                    if value == target_vtable:
                        candidate = address + offset
                        try:
                            owner = qword(candidate + 0x670)
                            callback = qword(candidate + 0x678)
                            if owner == candidate and callback == target_callback:
                                details = read(candidate, 0x3C8)
                                matches.append({'pointer': hex(candidate), 'route': route,
                                    'recipient_handle': hex(int.from_bytes(details[0x2C:0x34], 'little')),
                                    'direction_flag_660': read(candidate + 0x660, 1)[0],
                                    'listener_owner_matches': True, 'send_callback_rva': '0x130f080',
                                    'proposal_48_hex': details[0x48:0x208].hex(),
                                    'proposal_208_hex': details[0x208:0x3C8].hex()})
                        except OSError:
                            pass
                    if depth < 3 and 0x10000 <= value < 0x00007FFF00000000 and value % 8 == 0:
                        if not base <= value < base + 0x4000000 and value not in visited and len(queue) < 12000:
                            queue.append((value, depth + 1, f'{route}+{offset:#x}'))
                if matches:
                    break
            unique = {item['pointer']: item for item in matches}
            report['peace_ui_probe'] = {'read_only': True, 'visited_addresses': len(visited),
                'search_limit': 2048, 'max_depth': 3, 'matches': list(unique.values()),
                'note': 'No match does not prove absence; bounded graph search only.'}
            if args.peace_heap and not unique:
                class MemoryInfo(C.Structure):
                    _fields_ = [('BaseAddress', C.c_void_p), ('AllocationBase', C.c_void_p),
                                ('AllocationProtect', W.DWORD), ('PartitionId', W.WORD),
                                ('RegionSize', C.c_size_t), ('State', W.DWORD),
                                ('Protect', W.DWORD), ('Type', W.DWORD)]
                kernel.VirtualQueryEx.argtypes = [W.HANDLE, C.c_void_p, C.POINTER(MemoryInfo), C.c_size_t]
                kernel.VirtualQueryEx.restype = C.c_size_t
                address = 0x10000
                scanned = 0
                started = time.monotonic()
                needle = target_vtable.to_bytes(8, 'little')
                while address < 0x00007FFFFFFF0000 and scanned < 4 * 1024**3 and time.monotonic() - started < 20:
                    info = MemoryInfo()
                    if not kernel.VirtualQueryEx(handle, address, C.byref(info), C.sizeof(info)):
                        break
                    region_start = info.BaseAddress or address
                    region_end = region_start + info.RegionSize
                    if region_end <= address:
                        break
                    if info.State == 0x1000 and info.Type == 0x20000 and info.Protect in (0x04, 0x40):
                        chunk_start = region_start
                        while chunk_start < region_end and scanned < 4 * 1024**3 and time.monotonic() - started < 20:
                            size = min(1048576, region_end - chunk_start)
                            scanned += size
                            try:
                                blob = read(chunk_start, size)
                            except OSError:
                                chunk_start += size
                                continue
                            offset = blob.find(needle)
                            while offset >= 0:
                                candidate = chunk_start + offset
                                try:
                                    if qword(candidate + 0x670) == candidate and qword(candidate + 0x678) == target_callback:
                                        details = read(candidate, 0x3C8)
                                        unique[hex(candidate)] = {'pointer': hex(candidate), 'route': 'private_heap_scan',
                                            'recipient_handle': hex(int.from_bytes(details[0x2C:0x34], 'little')),
                                            'direction_flag_660': read(candidate + 0x660, 1)[0],
                                            'listener_owner_matches': True, 'send_callback_rva': '0x130f080',
                                            'proposal_48_hex': details[0x48:0x208].hex(),
                                            'proposal_208_hex': details[0x208:0x3C8].hex()}
                                except OSError:
                                    pass
                                offset = blob.find(needle, offset + 1)
                            chunk_start += size
                    if unique:
                        break
                    address = region_end
                report['peace_ui_probe'].update({'matches': list(unique.values()),
                    'heap_bytes_scanned': scanned, 'heap_seconds': round(time.monotonic() - started, 3),
                    'heap_limit_bytes': 4 * 1024**3, 'heap_time_limit_seconds': 20})
            for item in report['peace_ui_probe']['matches']:
                item['proposal_participants'] = {}
                for proposal_name in ('proposal_48_hex', 'proposal_208_hex'):
                    blob = bytes.fromhex(item[proposal_name])
                    vectors = {}
                    for offset in (0x28, 0x40, 0x58, 0x70):
                        begin, end, capacity = (int.from_bytes(blob[pos:pos + 8], 'little')
                            for pos in (offset, offset + 8, offset + 16))
                        entry = {'begin': hex(begin), 'end': hex(end), 'capacity': hex(capacity)}
                        if not begin and not end and not capacity:
                            entry.update({'count': 0, 'members': []})
                        elif begin >= 0x10000 and begin <= end <= capacity and (end - begin) % 8 == 0 and (end - begin) // 8 <= 4096:
                            try:
                                members = []
                                for pos in range(begin, end, 8):
                                    member = qword(pos)
                                    slot = (member >> 32) & 0xffff
                                    valid = slot < 4096 and qword(qword(array + slot * 8) + 0x20) == member
                                    members.append({'handle': hex(member), 'slot': slot,
                                        'tag': (member & 0xffffff).to_bytes(3, 'little').decode('ascii', errors='replace'),
                                        'country_handle_valid': valid})
                                entry.update({'count': len(members), 'members': members})
                            except (OSError, RuntimeError) as error:
                                entry['error'] = str(error)
                        else:
                            entry['error'] = 'Invalid vector range; not read'
                        vectors[hex(offset)] = entry
                    item['proposal_participants'][proposal_name] = vectors
                try:
                    ui_root = qword(int(item['pointer'], 16) + 0x978)
                    ui_context = qword(ui_root + 0x330)
                    dispatcher = qword(ui_context + 0x370)
                    transport = qword(dispatcher + 0x58)
                    transport_vtable = qword(transport) if transport else 0
                    submit = qword(transport_vtable + 0x30) if transport_vtable else 0
                    item['dispatch_context'] = {'ui_root': hex(ui_root), 'ui_context': hex(ui_context),
                        'dispatcher': hex(dispatcher), 'transport': hex(transport),
                        'transport_submit_candidate_rva': hex(submit - base) if submit else None,
                        'note': 'Read-only pointers, no submission or thread verification.'}
                    global_refs = []
                    needle = ui_root.to_bytes(8, 'little')
                    for rva in range(0x2330000, 0x2350000, 4096):
                        try:
                            blob = read(base + rva, 4096)
                        except OSError:
                            continue
                        offset = blob.find(needle)
                        while offset >= 0:
                            if offset % 8 == 0:
                                global_refs.append(hex(rva + offset))
                            offset = blob.find(needle, offset + 1)
                    item['dispatch_context']['ui_root_global_pointer_candidates'] = global_refs
                except OSError:
                    item['dispatch_context'] = {'error': 'Pointer chain could not be read'}
        args.output.parent.mkdir(exist_ok=True, parents=True)
        args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps({'output': str(args.output), 'consistent_slots': len(slots), 'read_only': True}))
    finally:
        kernel.CloseHandle(handle)

if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError) as error:
        print(f'Native probe: {error}', file=sys.stderr)
        raise SystemExit(2)
