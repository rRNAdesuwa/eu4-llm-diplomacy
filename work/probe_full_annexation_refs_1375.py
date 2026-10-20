"""Bounded exact-build label/reference inventory; no process or native call."""
import argparse
import hashlib
import json
from pathlib import Path
from discover_diplomacy import PE, check_memory_budget, rip_references
from map_diplomacy_fields import SHA


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    pe = PE(root.parent / 'eu4.exe')
    if hashlib.sha256(pe.data).hexdigest() != SHA:
        raise ValueError('Exact executable required')
    targets, strings = set(), {}
    for label in ('PEACE_ANNEX', 'PEACE_ANNEXED', 'po_annex', 'po_demand_provinces'):
        needle, offset, rows = label.encode('ascii') + b'\0', 0, []
        while True:
            offset = pe.data.find(needle, offset)
            if offset < 0:
                break
            if len(rows) >= 32:
                raise ValueError('Label count budget')
            rva = pe.to_rva(offset)
            rows.append({'offset': offset, 'rva': None if rva is None else hex(rva)})
            if rva is not None:
                targets.add(rva)
            offset += len(needle)
        strings[label] = rows
    if len(targets) > 64:
        raise ValueError('Target budget')
    refs = rip_references(pe, targets)
    if sum(map(len, refs.values())) > 256:
        raise ValueError('Candidate reference budget')
    record = {'kind': 'full_annexation_label_reference_candidates', 'exe_sha256': SHA,
              'strings': strings, 'references': {hex(k): v for k, v in refs.items()},
              'reference_instruction_boundaries_verified': False, 'decoded_bytes': 0,
              'analysis_peak_commit': check_memory_budget(), 'game_accessed': False,
              'execution_supported': False, 'production_ready': False}
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(record, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(record, sort_keys=True))


if __name__ == '__main__':
    main()
