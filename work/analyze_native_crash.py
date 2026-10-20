"""Read-only extraction of the observed EU4 minidump; no upload or process access."""
import argparse
import json
import mmap
import struct
from pathlib import Path

from local_config import get_path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, help='minidump to inspect; defaults to EU4_CRASH_DUMP from local.env')
parser.add_argument('--output', type=Path, default=Path(__file__).parent / 'runtime/native-crash-analysis.json')
args = parser.parse_args()
SOURCE = args.source or get_path('EU4_CRASH_DUMP')
assert SOURCE is not None
source_file = SOURCE.open('rb')
data = mmap.mmap(source_file.fileno(), 0, access=mmap.ACCESS_READ)
def u32(offset): return struct.unpack_from('<I', data, offset)[0]
def u64(offset): return struct.unpack_from('<Q', data, offset)[0]
assert data[:4] == b'MDMP'
streams = {}
for i in range(u32(8)):
    kind, size, rva = struct.unpack_from('<III', data, u32(12) + i * 12)
    streams[kind] = (rva, size)
modules = []
start = streams[4][0]
for i in range(u32(start)):
    p = start + 4 + i * 108
    name_rva = u32(p + 20)
    name = data[name_rva + 4:name_rva + 4 + u32(name_rva)].decode('utf-16le')
    modules.append({'base': u64(p), 'size': u32(p + 8), 'name': name})
regions = []
if 5 in streams:
    start = streams[5][0]
    for i in range(u32(start)):
        p = start + 4 + i * 16
        regions.append((u64(p), u32(p + 8), u32(p + 12)))
if 9 in streams:
    start = streams[9][0]
    file_rva = u64(start + 8)
    for i in range(u64(start)):
        address, size = struct.unpack_from('<QQ', data, start + 16 + i * 16)
        regions.append((address, size, file_rva))
        file_rva += size
if 3 in streams:
    start = streams[3][0]
    for i in range(u32(start)):
        p = start + 4 + i * 48
        regions.append((u64(p + 24), u32(p + 32), u32(p + 36)))
def read_dump_memory(address, size):
    for base, length, rva in regions:
        if base <= address and address + size <= base + length:
            return data[rva + address - base:rva + address - base + size]
    return None
def memory_qword(address):
    body = read_dump_memory(address, 8)
    return int.from_bytes(body, 'little') if body is not None else None
start = streams[6][0]
context = u32(start + 164)
names = ['rax','rcx','rdx','rbx','rsp','rbp','rsi','rdi','r8','r9','r10','r11','r12','r13','r14','r15','rip']
regs = {name: u64(context + 120 + i * 8) for i, name in enumerate(names)}
eu4 = next(m for m in modules if Path(m['name']).name.lower() == 'eu4.exe')
offer = read_dump_memory(regs['rsi'], 0x1c0)
offer_report = None
if offer:
    offer_report = {'address': hex(regs['rsi']), 'vtable_rva': hex(int.from_bytes(offer[:8], 'little') - eu4['base']),
        'handle_10': hex(int.from_bytes(offer[0x10:0x18], 'little')),
        'handle_18': hex(int.from_bytes(offer[0x18:0x20], 'little')), 'vectors': {}}
    for offset in (0x28, 0x40, 0x58, 0x70):
        begin, end, capacity = struct.unpack_from('<QQQ', offer, offset)
        offer_report['vectors'][hex(offset)] = {'begin': hex(begin), 'end': hex(end), 'capacity': hex(capacity)}
returns = []
stack = read_dump_memory(regs['rsp'], 1024)
if stack:
    for i in range(0, len(stack), 8):
        value = int.from_bytes(stack[i:i+8], 'little')
        if eu4['base'] <= value < eu4['base'] + eu4['size']:
            returns.append({'stack_offset': hex(i), 'candidate_rva': hex(value - eu4['base'])})
report = {'source': SOURCE.name, 'exception_thread': u32(start), 'exception_code': hex(u32(start + 8)),
    'exception_address': hex(u64(start + 24)),
    'exception_parameters': [hex(u64(start + 40 + i*8)) for i in range(min(u32(start + 32), 15))],
    'module_base': hex(eu4['base']), 'fault_rva': hex(regs['rip'] - eu4['base']),
    'registers': {k: hex(v) for k,v in regs.items()}, 'offer_candidate': offer_report,
    'stack_address_candidates': returns[:40], 'stack_note': 'Raw address scan, not an unwound call stack.'}
output = args.output
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, indent=2), encoding='utf-8')
data.close()
source_file.close()
if __name__ == '__main__':
    print(json.dumps({k:v for k,v in report.items() if k not in ('stack_address_candidates','source')}, indent=2))
