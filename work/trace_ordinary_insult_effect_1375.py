"""Bounded disk-only ordinary insult helper decoding; no process access."""
import hashlib
import json
from pathlib import Path
import tempfile
from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg
from trace_change_subject_type import rows

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / 'work/reports/native-pair-extension-v11-1375.json'
PARENT_SHA = 'ac4559379e218aaf1fa8ffc1dd7dc6b8332ed5b7bf681c4b66bfc59349944344'
OUTPUT = ROOT / 'work/reports/native-ordinary-insult-effect-1375-initial.json'
ENTRIES = (0x384040, 0x1f9210, 0x362ec0)

def main():
    if OUTPUT.exists():
        raise ValueError('Initial disk decoding is immutable; select a new revision')
    if not 0 < PARENT.stat().st_size <= 5 * 1024 * 1024:
        raise ValueError('Parent report budget')
    raw = PARENT.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PARENT_SHA:
        raise ValueError('Pinned parent changed')
    parent = json.loads(raw)
    pe = PE(ROOT.parent / 'eu4.exe')
    if hashlib.sha256(pe.data).hexdigest() != SHA:
        raise ValueError('Unsupported executable')
    md, _ = make_disassembler(Path(tempfile.gettempdir()) / 'eu4-native-analysis-deps')
    functions = {}
    decoded = 0
    for entry in ENTRIES:
        code, edges = bounded_cfg(pe, md, entry, window=0x1800, max_instructions=2000)
        decoded += sum(i.size for i in code)
        if decoded > 16384:
            raise ValueError('Total decoded instruction budget')
        functions[hex(entry)] = {'instructions':rows(pe,code),'edges':edges}
        check_memory_budget()
    effect = parent['functions']['0x5378f0']['instructions']
    selected = [row for row in effect if 0x53791f <= int(row['rva'],16) <= 0x537a03]
    for row in selected:
        instruction = bytes.fromhex(row['bytes'])
        if pe.bytes_at(int(row['rva'],16), len(instruction)) != instruction:
            raise ValueError('Parent effect instruction changed')
    document = {'schema_version':1,'purpose':'ordinary_insult_static_helper_decoding',
        'game_sha256':SHA,'parent_report_sha256':PARENT_SHA,
        'selected_effect_instructions':selected,'functions':functions,
        'limits':{'entries':len(ENTRIES),'per_entry_window':0x1800,'per_entry_instructions':2000,
                  'total_decoded_instruction_bytes':decoded,'max_total_bytes':16384,'memory_limit_mib':768},
        'runtime_verified':False,'selected_effect_verified':False,'observer_implemented':False,
        'production_execution_verified':False,'process_accessed':False,
        'limitations':['Helper names and selected layouts remain interpretations pending full review.',
                       'Bounded CFG does not prove all writers or world generation.']}
    data = (json.dumps(document, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    with OUTPUT.open('xb') as stream:
        stream.write(data)
    print(json.dumps({'path':OUTPUT.relative_to(ROOT).as_posix(),'size_bytes':len(data),
                      'sha256':hashlib.sha256(data).hexdigest(),'decoded_bytes':decoded,
                      'instruction_counts':{k:len(v['instructions']) for k,v in functions.items()}}))

if __name__ == '__main__':
    main()
