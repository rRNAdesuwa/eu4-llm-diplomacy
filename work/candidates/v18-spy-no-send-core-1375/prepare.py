"""Bounded offline candidate and exact PE pin verification; no compile or process API."""
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 24 * 1024 * 1024


def bounded(path, limit):
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Read budget')
    return raw


def descriptor(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def pe_check(report, header):
    exe = ROOT.parent / 'eu4.exe'
    digest = hashlib.sha256()
    with exe.open('rb') as stream:
        for raw in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(raw)
        if digest.hexdigest() != report['game_sha256']:
            raise ValueError('Wrong executable SHA')
        stream.seek(0)
        pe = stream.read(4096)
        if pe[:2] != b'MZ':
            raise ValueError('PE signature')
        nt, = struct.unpack_from('<I', pe, 0x3c)
        if not 64 <= nt <= 1024 or pe[nt:nt + 4] != b'PE\0\0':
            raise ValueError('PE header boundary')
        machine, sections, timestamp = struct.unpack_from('<HHI', pe, nt + 4)
        optional_size, = struct.unpack_from('<H', pe, nt + 20)
        magic, = struct.unpack_from('<H', pe, nt + 24)
        image_size, = struct.unpack_from('<I', pe, nt + 24 + 56)
        if (machine, magic, timestamp, image_size) != (0x8664, 0x20b, report['pe_timestamp'], report['image_size']):
            raise ValueError('PE identity')
        if not 1 <= sections <= 32 or not 112 <= optional_size <= 512:
            raise ValueError('PE table bound')
        table = nt + 24 + optional_size
        if table + sections * 40 > len(pe):
            raise ValueError('PE sections outside header')
        entries = [struct.unpack_from('<IIII', pe, table + i * 40 + 8) for i in range(sections)]

        def at(rva, size):
            matches = [(raw + rva - va) for virtual, va, raw_size, raw in entries
                       if va <= rva and rva - va + size <= raw_size and rva - va + size <= max(raw_size, virtual)]
            if len(matches) != 1:
                raise ValueError('Unbacked or overlapping RVA')
            stream.seek(matches[0])
            result = stream.read(size)
            if len(result) != size:
                raise ValueError('Short pin read')
            return result

        codes = report['code_pins']
        slots = report['vtable_slots']
        if len(codes) != 21 or len(slots) != 52:
            raise ValueError('Fixed pin inventory differs')
        extracted_code = [(int(rva, 16), raw) for rva, raw in re.findall(r'\{0x([0-9a-f]+), "([0-9a-f]+)"\}', header)]
        extracted_slots = [(int(rva, 16), int(target, 16)) for rva, target in re.findall(r'\{0x([0-9a-f]+), 0x([0-9a-f]+)\}', header)]
        if extracted_code != [(p['rva'], p['hex']) for p in codes] or extracted_slots != [(p['rva'], p['target']) for p in slots]:
            raise ValueError('C++ pin table differs from report')
        for pin in codes:
            expected = bytes.fromhex(pin['hex'])
            if not 1 <= len(expected) <= 32 or at(pin['rva'], len(expected)) != expected:
                raise ValueError('Code pin mismatch')
        preferred, = struct.unpack_from('<Q', pe, nt + 24 + 24)
        for pin in slots:
            value, = struct.unpack('<Q', at(pin['rva'], 8))
            if value != preferred + pin['target']:
                raise ValueError('Vtable pin mismatch')
    return {'code_pins': len(codes), 'code_bytes': sum(len(bytes.fromhex(p['hex'])) for p in codes), 'virtual_slots': len(slots)}


def check():
    sources = json.loads(bounded(HERE / 'source-pins.json', 128 * 1024))
    index = json.loads(bounded(HERE / 'candidate-index.json', 128 * 1024))
    if not 1 <= len(sources) <= 128 or not 1 <= len(index) <= 24:
        raise ValueError('Inventory budget')
    total = 0
    for mapping in (sources, index):
        for name, expected in mapping.items():
            path = ROOT / name
            if path.resolve() != path or not path.is_relative_to(ROOT):
                raise ValueError('Noncanonical source path')
            raw = bounded(path, MAX_FILE)
            total += len(raw)
            if total > MAX_TOTAL or descriptor(raw) != expected:
                raise ValueError('Source or byte budget differs: ' + name)
    report = json.loads(bounded(HERE / 'pin-report.json', 32 * 1024))
    result = pe_check(report, bounded(HERE / 'pins.h', 32 * 1024).decode('ascii'))
    result.update(source_pins=len(sources), candidate_sources=len(index), checked_bytes=total,
                  process_access=False, native_game_calls=False, runtime_verified=False,
                  dll_built=False, production_ready=False)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', required=True, action='store_true')
    parser.parse_args()
    print(json.dumps(check(), sort_keys=True))
