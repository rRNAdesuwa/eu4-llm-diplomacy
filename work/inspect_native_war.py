"""Read-only, bounded EU4 1.37.4 war-effect evidence. Does not attach to EU4."""
import hashlib
import json
from pathlib import Path
import struct

from local_config import game_exe


def main() -> None:
    data = game_exe().read_bytes()
    digest = hashlib.sha256(data).hexdigest().upper()
    expected = 'B23FA0E1F698D31B01CDD1C3817A675805D8C6286CB66F9C231E6E2A42544D77'
    if digest != expected:
        raise SystemExit('Unsupported executable hash; no address interpretation performed.')
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    optional = pe + 24
    base = struct.unpack_from('<Q', data, optional + 24)[0]
    sections = []
    for index in range(struct.unpack_from('<H', data, pe + 6)[0]):
        header = optional + struct.unpack_from('<H', data, pe + 20)[0] + index * 40
        _, rva, size, raw = struct.unpack_from('<IIII', data, header + 8)
        sections.append((rva, size, raw))

    def offset(rva: int) -> int:
        for start, size, raw in sections:
            if start <= rva < start + size:
                return raw + rva - start
        raise ValueError(f'RVA outside file sections: {rva:#x}')

    def pointer(rva: int) -> int:
        return struct.unpack_from('<Q', data, offset(rva))[0] - base

    def call(rva: int) -> int:
        raw = offset(rva)
        assert data[raw] == 0xe8
        return rva + 5 + struct.unpack_from('<i', data, raw + 1)[0]

    evidence = {
        'binary_sha256': digest,
        'effect_vtable_rva': '0x1ca3678',
        'effect_parser_rva': hex(pointer(0x1ca3678 + 0x20)),
        'effect_executor_rva': hex(pointer(0x1ca3678 + 0x78)),
        'constructor_call_rva': '0x62a576',
        'constructor_rva': hex(call(0x62a576)),
        'dispatch_call_rva': '0x62a583',
        'dispatch_rva': hex(call(0x62a583)),
        'war_action_vtable_rva': '0x1c80d90',
        'v7_generic_command_vtable_rva': '0x1c814b0',
        'v7_peace_action_vtable_rva': '0x1c7b840',
        'runtime_validation': 'not performed by this offline tool',
    }
    assert evidence['effect_parser_rva'] == '0x629650'
    assert evidence['effect_executor_rva'] == '0x629b10'
    assert evidence['constructor_rva'] == '0x5004b0'
    assert evidence['dispatch_rva'] == '0x4ea850'
    # Verify the constructor's RIP-relative vtable load, not a guessed layout.
    raw = offset(0x5004f4)
    assert data[raw:raw + 3] == b'\x48\x8d\x05'
    assert 0x5004f4 + 7 + struct.unpack_from('<i', data, raw + 3)[0] == 0x1c80d90
    destination = Path(__file__).with_name('runtime') / 'native-war-path-evidence.json'
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    main()
