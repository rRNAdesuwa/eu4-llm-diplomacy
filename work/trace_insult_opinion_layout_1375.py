"""Decode the exact additional opinion-storage helper without game access."""
import hashlib
import json
from pathlib import Path
import tempfile
from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg
from trace_change_subject_type import rows

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / 'work/reports/native-ordinary-insult-effect-1375-initial.json'
EXPECTED = 'd6ecd628a8a43e006b4b35ea3f6f5e7b2136755eeb3f23016ee7a7e0f2ea02ef'
OUTPUT = ROOT / 'work/reports/native-insult-opinion-layout-1375-initial.json'

def main():
    if OUTPUT.exists():
        raise ValueError('Use a new revision; initial evidence is immutable')
    if not 0 < INPUT.stat().st_size <= 128 * 1024:
        raise ValueError('Input budget')
    raw = INPUT.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED:
        raise ValueError('Input decoding changed')
    pe = PE(ROOT.parent / 'eu4.exe')
    if hashlib.sha256(pe.data).hexdigest() != SHA:
        raise ValueError('Wrong executable')
    md, _ = make_disassembler(Path(tempfile.gettempdir()) / 'eu4-native-analysis-deps')
    code, edges = bounded_cfg(pe, md, 0x383ef0, window=0x1800, max_instructions=2000)
    decoded = sum(i.size for i in code)
    if decoded > 6144:
        raise ValueError('Decoded-byte budget')
    check_memory_budget()
    document = {'schema_version':1,'purpose':'insult_opinion_storage_static_decoding',
        'game_sha256':SHA,'input_sha256':EXPECTED,'entry_rva':'0x383ef0',
        'instructions':rows(pe,code),'edges':edges,'decoded_bytes':decoded,
        'runtime_verified':False,'observer_implemented':False,'process_accessed':False,
        'production_execution_verified':False}
    data = (json.dumps(document, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    with OUTPUT.open('xb') as stream:
        stream.write(data)
    print(json.dumps({'path':OUTPUT.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(data).hexdigest(),
                      'size_bytes':len(data),'decoded_bytes':decoded,'instructions':len(code)}))

if __name__ == '__main__':
    main()
