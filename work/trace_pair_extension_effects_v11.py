"""Bounded disk-only evidence for v11 read-only selected-state observations."""
from __future__ import annotations
import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg
from trace_change_subject_type import rows

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / 'work/reports/native-pair-extension-v11-1375.json'
PARENT_SHA = 'ac4559379e218aaf1fa8ffc1dd7dc6b8332ed5b7bf681c4b66bfc59349944344'
OUTPUT = ROOT / 'work/reports/native-pair-extension-effects-v11-1375.json'
ENTRIES = (0x3383b0, 0xa6a150, 0xdf1a0, 0xc9cc0)


def fact(text, *anchors):
    return {'summary': text, 'evidence_rvas': list(map(hex, anchors)), 'runtime_verified': False}


FACTS = {
    'warning_index': fact('Warning bool getter reads relation-root+1b8 array and DWORD+1c4 count, 16-byte slot/object entries, then checks object+18 against counterpart slot. Full-handle/vtable/marker checks must be stronger in the observer.',
        0xa6a15f, 0xa6a166, 0xa6a184, 0xa6a190, 0xa6a199),
    'coalition_deferred_removal': fact('373880 passes target+1910 list todf1a0. If list+14 BYTE (country1924) is nonzero, removal only marks node+18=1 and keeps count. Otherwise it unlinks and frees node then decrements DWORD count+10. Observer must exclude marked membership while still traversing bounded links/count.',
        0x3738be, 0x3738ea, 0xdf1b7, 0xdf1bd, 0xdf1c9, 0xdf1cd, 0xdf202),
    'treasury': fact('ChangeTreasury3383b0 diagnostic names the operation; it adds signed DWORD amount to country+bb0 and clamps to +/-1000000000 native units. Gift money and favor-for-gold amounts reach this helper through AddExpense(negated) and AddIncome, so treasury uses the same ducat x1000 units. Balance differences alone cannot establish request causality.',
        0x3383f8, 0x338417, 0x338419, 0x33841f, 0x33842d, 0x338441, 0x3388a4, 0x3388b8, 0x3385d3),
    'favors_record_and_direction': fact('Favor-gold effect selects recipient country+1510 and actor slot, then c9cc0 returns records+slot*48. a658d0 conditionally subtracts native cost from signed DWORD record+20, clamping0..100000; cost expression4f495c multiplies native favor count by1000. Thus target record for actor stores favors actor can spend on target. No assumption that arbitrary country records are initialized or that the conditional feature gate is enabled.',
        0x4f4927, 0x4f4945, 0x4f4950, 0x4f4957, 0xc9cc0, 0xc9cc3, 0xc9cc7,
        0x4f495c, 0x4f4976, 0xa658e0, 0xa658e9, 0xa658ec, 0xa658ee, 0xa658f3, 0xa6590c),
}


def generate():
    raw = PARENT.read_bytes()
    if len(raw)>4*1024*1024 or hashlib.sha256(raw).hexdigest()!=PARENT_SHA:
        raise ValueError('Parent report SHA mismatch')
    parent = json.loads(raw)
    pe = PE(ROOT.parent / 'eu4.exe')
    if hashlib.sha256(pe.data).hexdigest()!=SHA:
        raise ValueError('Wrong executable')
    md,_ = make_disassembler(Path(tempfile.gettempdir())/'eu4-native-analysis-deps')
    functions = {}
    decoded = 0
    for entry in ENTRIES:
        code, edges = bounded_cfg(pe,md,entry,window=0x1800,max_instructions=2000)
        decoded += sum(i.size for i in code)
        if decoded>16384:
            raise ValueError('Helper decode budget exceeded')
        functions[hex(entry)]={'instructions':rows(pe,code),'edges':edges}
        check_memory_budget()
    lookup={r['rva']:r for doc in (parent, {'functions':functions}) for f in doc['functions'].values() for r in f['instructions']}
    facts=json.loads(json.dumps(FACTS))
    for value in facts.values():
        value['instructions']=[]
        for key in value['evidence_rvas']:
            row=lookup[key];b=bytes.fromhex(row['bytes'])
            if pe.bytes_at(int(key,16),len(b))!=b:
                raise ValueError('Evidence bytes mismatch')
            value['instructions'].append(row)
    return {'schema':'native_pair_extension_effects_v11_1375_v1','game_sha256':SHA,
        'runtime_verified':False,'execution_verified':False,'input':{'path':PARENT.relative_to(ROOT).as_posix(),'sha256':PARENT_SHA},
        'facts':facts,'functions':functions,
        'observer_boundaries':['Insult opinion/CB modifier identity is not closed and remains unsupported.',
            'Economic compare requires explicit positive expected amount (and favor cost for favor-gold), same raw date and exact paired scalar deltas; no acceptance/request attribution.',
            'Root/player/full handles and two identical passes do not establish an atomic snapshot or reliable world epoch.'],
        'limits':{'functions':len(functions),'max_window_bytes':6144,'max_instructions':2000,'max_decoded_bytes':16384,
            'decoded_bytes':decoded,'memory_guard_mib':768,'process_access':False}}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true');a=p.parse_args()
    report=generate();data=(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode()
    if a.check:
        if not OUTPUT.is_file() or OUTPUT.read_bytes()!=data:raise ValueError('Report differs')
    else:OUTPUT.write_bytes(data)
    print(json.dumps({'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'decoded_bytes':report['limits']['decoded_bytes'],'check':a.check}))


if __name__=='__main__':main()
