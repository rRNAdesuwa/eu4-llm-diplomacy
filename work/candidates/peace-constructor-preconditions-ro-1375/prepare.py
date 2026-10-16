"""Build/check a disk-only contract from already bounded CFGs; decode nothing."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EXE_SHA = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
INPUTS = {
    'work/reports/native-peace-parameters-1375.json': '93dda3790212669bd227cc8a09b50685b6a502402f9a5677baf3e58d962c5677',
    'work/reports/native-peace-candidate-boundaries-1375.json': '8d0f68855b499d1c22647de3e17383c801e21345de50901e3ed8b42c77213f8e',
}
# These are prior CFG instructions, not newly decoded windows or recursive calls.
RANGES = {
    'war_borrowed_lookup': (0, '0x97bd30', 0x97bd30, 0x97bd9b),
    'war_side_vectors': (0, '0x97bea0', 0x97bebb, 0x97bf56),
    'government_vassal_variant_owner': (0, '0x97d4e0', 0x97d83a, 0x97d876),
    'government_tributary_variant_owner': (0, '0x97db60', 0x97de68, 0x97def6),
    'government_variant_wrapper': (1, '0x7ace30', 0x7ace30, 0x7ace91),
    'government_default_cache': (1, '0x798dc0', 0x798dc6, 0x798e72),
    'tls_gate_first': (0, '0x97e1f0', 0x97e207, 0x97e244),
    'tls_gate_second': (0, '0x97e500', 0x97ea11, 0x97ea4e),
    'tls_initializer': (1, '0x1a33458', 0x1a33458, 0x1a334ae),
    'goal_resolution': (1, '0x97c300', 0x97c379, 0x97c3e8),
    'goal_conditions_true': (1, '0x97c300', 0x97c5a8, 0x97c5fc),
    'goal_conditions_false': (1, '0x97c300', 0x97c6c3, 0x97c708),
    'dependency_definition': (0, '0x97db60', 0x97ddf6, 0x97de04),
    'dependency_condition_call': (0, '0x97db60', 0x97e07e, 0x97e097),
    'dependency_conditions': (1, '0xb22380', 0xb22422, 0xb22442),
    'take_colony_validity': (1, '0xd9f0b0', 0xd9f0b0, 0xd9f103),
    'take_colony_definition': (1, '0x9b120', 0x9b120, 0x9b124),
    'take_colony_virtual78': (1, '0x8f440', 0x8f440, 0x8f442),
}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(262144), b''): h.update(block)
    return h.hexdigest()


class PE:
    """Minimal disk section mapper, with bounded header reads and no decoding."""
    def __init__(self, path):
        self.stream = Path(path).open('rb')
        dos = self.read(0, 64)
        assert dos[:2] == b'MZ'
        pos = struct.unpack_from('<I', dos, 60)[0]
        assert 64 <= pos <= 0x1000
        coff = self.read(pos, 24)
        signature, machine, count, self.timestamp = struct.unpack_from('<4sHHI', coff)
        assert signature == b'PE\0\0' and machine == 0x8664 and 1 <= count <= 32
        optional_size = struct.unpack_from('<H', coff, 20)[0]
        assert 112 <= optional_size <= 512
        optional = self.read(pos + 24, optional_size)
        assert struct.unpack_from('<H', optional)[0] == 0x20b
        self.image_base = struct.unpack_from('<Q', optional, 24)[0]
        self.image_size = struct.unpack_from('<I', optional, 56)[0]
        sections = self.read(pos + 24 + optional_size, 40 * count)
        self.sections = []
        for i in range(count):
            vsize, rva, size, off = struct.unpack_from('<IIII', sections, i * 40 + 8)
            self.sections.append((rva, size, off))

    def read(self, offset, size):
        assert 0 < size <= 4096
        self.stream.seek(offset)
        data = self.stream.read(size)
        assert len(data) == size
        return data

    def at(self, rva, size):
        for start, raw_size, offset in self.sections:
            if start <= rva and rva + size <= start + raw_size:
                return self.read(offset + rva - start, size)
        raise ValueError('RVA not backed by disk bytes')


def render():
    prior = []
    for name, digest in INPUTS.items():
        path = ROOT / name
        assert path.stat().st_size < 2 * 1024 * 1024 and sha(path) == digest
        prior.append(json.loads(path.read_bytes()))
    exe = ROOT.parent / 'eu4.exe'
    assert sha(exe) == EXE_SHA
    pe = PE(exe)
    anchors = {}
    try:
        for name, (index, function, lo, hi) in RANGES.items():
            source = list(INPUTS)[index]
            rows = prior[index]['functions'][function]['instructions']
            chosen = []
            for i, row in enumerate(rows):
                rva = int(row['rva'], 16)
                if lo <= rva <= hi:
                    data = bytes.fromhex(row['bytes'])
                    assert pe.at(rva, len(data)) == data
                    chosen.append(dict(row, source=source, json_pointer=f'/functions/{function}/instructions/{i}'))
            assert chosen, name
            anchors[name] = chosen
        slots = prior[1]['take_colony_example_vtable']
        for row in slots['slots'].values():
            assert pe.at(int(row['cell_rva'], 16), 8).hex() == row['bytes']
        # These arithmetic assertions must stay explicit; they corrected easy
        # misreadings of wrapper offsets and the incomplete prior TLS summary.
        assert 0x38 + 0x138 == 0x170 and 0x78 + 0x138 == 0x1b0 and 0x58 + 0x138 == 0x190
        assert 0x97e207 + 7 + int.from_bytes(bytes.fromhex('861d9c01'), 'little', signed=True) == 0x233ff94
        assert 0x97c39e + 7 + int.from_bytes(bytes.fromhex('8b3c9c01'), 'little', signed=True) == 0x2340030
        count = sum(len(bytes.fromhex(row['bytes'])) for rows in anchors.values() for row in rows)
        return {
            'schema_version': 1, 'purpose': 'peace_constructor_readonly_query_contract',
            'exe_sha256': EXE_SHA, 'pe': {'machine': 'x64', 'image_base': hex(pe.image_base), 'image_size': pe.image_size, 'timestamp': pe.timestamp},
            'inputs': INPUTS, 'anchors': anchors, 'take_colony_vtable': slots,
            'government_variant_paths': {
                'country_instance_pointer_offset': '0x1420', 'instance_definition_pointer_offset': '0x10',
                'instance_variant_pointer_offsets': ['0x170', '0x110'],
                'nogovernment_global_rva': '0x233fe88', 'nogovernment_variant_pointer_offsets': ['0x1b0', '0x150'],
                'secondary_global_rva': '0x242bc80', 'secondary_variant_pointer_offsets': ['0x190', '0x130'],
                'variant_type_offset': '0x0', 'normalized_type': 't if t >= 0 else ~t',
                'recognized_bool_types': [0, -1], 'bool_storage_offset': '0x8', 'bool_storage_width': 1,
                'is_script_condition_pointer': False,
                'scope': 'observe direct instance only; absent instance records fallback risk, never calls a getter or prewarms cache'},
            'tls': {'gate_a_rva': '0x233ff94', 'gate_b_rva': '0x233fed6',
                'tls_path_condition': 'gate_a == 0 or gate_b != 0', 'skip_condition': 'gate_a != 0 and gate_b == 0',
                'gs_array_offset': '0x58', 'caller_array_index': 0, 'initializer_index_rva': '0x233c574',
                'initialized_byte_offset': '0xc', 'enumeration_gate_byte_offset': '0x10',
                'correction_to_prior_summary': '233fed6 nonzero was only sufficient, not necessary; preceding 233ff94 comparison also enters TLS when zero.'},
            'goal': {'war_pointer_offset': '0x160', 'fallback_global_rva': '0x2340030',
                'dependency_registry_global_rva': '0x233ffd8', 'dependency_definition_pointer_offset': '0x80',
                'condition_vectors': {'flag_false_taker_in_A': '0x50', 'flag_true_taker_in_A': '0x140',
                    'flag_false_taker_not_in_A': '0x288', 'flag_true_taker_not_in_A': '0x378'},
                'condition_vector_pointer_offset': '0x8', 'signed_count_offset': '0x14', 'stride': 8,
                'condition_virtual_slot': '0x30', 'dependency_conditions_pointer_offset': '0x48', 'dependency_conditions_signed_count_offset': '0x54'},
            'coverage': {'new_decoded_bytes': 0, 'prior_instruction_bytes_rechecked': count, 'process_accessed': False,
                'runtime_verified': False, 'parameter_constructor_authorized': False,
                'constructor_purity_verified': False, 'world_epoch_verified': False,
                'all_script_classes_reviewed': False, 'native_thread_provenance_verified': False},
        }
    finally: pe.stream.close()


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--check', action='store_true'); args = parser.parse_args()
    report = (json.dumps(render(), indent=2, sort_keys=True) + '\n').encode()
    out = HERE / 'static-contract.json'
    if args.check:
        assert out.read_bytes() == report, 'Static contract differs'
    else:
        with out.open('xb') as stream: stream.write(report)
    print(json.dumps({'check': args.check, 'sha256': hashlib.sha256(report).hexdigest(), 'bytes': len(report), 'new_decoded_bytes': 0, 'game_accessed': False}))


if __name__ == '__main__': main()
