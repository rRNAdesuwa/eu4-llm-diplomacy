"""Independently compare fixed acceptance literals with bounded disk PE reads."""
import hashlib
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT.parent / 'eu4.exe'
SOURCE = ROOT / 'work/native/v16/test-acceptance-1375.cpp'
EXPECTED = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'


def main():
    source = SOURCE.read_bytes()
    assert len(source) < 32768
    digest = hashlib.sha256()
    with EXE.open('rb') as stream:
        while chunk := stream.read(65536):
            digest.update(chunk)
        assert digest.hexdigest() == EXPECTED
        stream.seek(0)
        header = stream.read(4096)
        pe = struct.unpack_from('<I', header, 0x3c)[0]
        assert header[:2] == b'MZ' and header[pe:pe + 4] == b'PE\0\0'
        machine, count = struct.unpack_from('<HH', header, pe + 4)
        optional_size = struct.unpack_from('<H', header, pe + 20)[0]
        assert machine == 0x8664 and count <= 32
        optional = pe + 24
        base = struct.unpack_from('<Q', header, optional + 24)[0]
        sections = []
        for i in range(count):
            row = optional + optional_size + i * 40
            virtual_size, rva, raw_size, raw_offset = struct.unpack_from('<IIII', header, row + 8)
            sections.append((rva, virtual_size, raw_size, raw_offset))

        def read_rva(rva, size):
            assert 0 < size <= 2048
            owners = [s for s in sections if s[0] <= rva and rva + size <= s[0] + s[2]]
            assert len(owners) == 1
            section = owners[0]
            stream.seek(section[3] + rva - section[0])
            raw = stream.read(size)
            assert len(raw) == size
            return raw

        text = source.decode()
        block = text.split('constexpr Pin kPins[] = {', 1)[1].split('\n};', 1)[0]
        pins, differences = [], []
        for name, strings in re.findall(r'\{(kCallback|kDestructor|0x[0-9a-f]+),\s*((?:"[0-9a-f]+"\s*)+)\}', block):
            rva = {'kCallback': 0xe50180, 'kDestructor': 0x95660}.get(name)
            if rva is None:
                rva = int(name, 16)
            expected = bytes.fromhex(''.join(re.findall(r'"([0-9a-f]+)"', strings)))
            actual = read_rva(rva, len(expected))
            changes = [(i, a, b) for i, (a, b) in enumerate(zip(expected, actual)) if a != b]
            differences.extend((rva + i, a, b) for i, a, b in changes)
            pins.append(dict(rva=hex(rva), bytes=len(expected), differences=changes,
                             source_sha256=hashlib.sha256(expected).hexdigest(),
                             game_sha256=hashlib.sha256(actual).hexdigest()))
        assert len(pins) == 8 and sum(p['bytes'] for p in pins) == 945
        assert differences == [(0xe50222, 0x20, 0x10)]
        assert read_rva(0xe50221, 2) == b'\x77\x10'
        data_checks = 0
        for row in (0x1fcb3a0, 0x1fccde0):
            for offset, target in ((8, 0x1d34aec), (0x30, 0x1d34af8), (0x38, 0xe50180)):
                assert struct.unpack('<Q', read_rva(row + offset, 8))[0] - base == target
                data_checks += 1
        for rva, value in ((0x1d34aec, b'yesman\0'),
                           (0x1d34af8, b'Toggles AI positive responses\0'),
                           (0x1dc1c90, struct.pack('<QQ', 0, 15)),
                           (0x1d2b970, b'ENABLED\0'), (0x1d2b978, b'DISABLED\0'),
                           (0x1d2bc30, b'AI positive response is now ')):
            assert read_rva(rva, len(value)) == value
            data_checks += 1
        assert SOURCE.read_bytes() == source
    target = ROOT / 'work/review-results/v16-acceptance-pin-root-20261008a.json'
    report = dict(purpose='root_independent_disk_acceptance_literal_review',
        status='one_mismatch_reproduced', source_sha256=hashlib.sha256(source).hexdigest(),
        exact_executable_sha256=EXPECTED, pins=pins, constant_data_check_count=data_checks,
        corrected_branch='7710 / ja 0xe50233', native_calls=False, process_accessed=False,
        sources_unchanged=True, runtime_acceptance_verified=False, production_ready=False)
    with target.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, indent=2); stream.write('\n')
    print(json.dumps(dict(output=str(target), code_pins=8, code_bytes=945,
                         mismatches=1, constant_data_checks=data_checks)))


if __name__ == '__main__':
    main()
