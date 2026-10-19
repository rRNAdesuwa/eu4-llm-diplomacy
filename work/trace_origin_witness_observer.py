"""Bounded disk evidence for an early origin-witness observation prototype."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
from discover_diplomacy import PE, make_disassembler, check_memory_budget
from map_diplomacy_fields import bounded_cfg, SHA

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'work/reports/native-origin-witness-observer-1375.json'
INPUTS = {
    'native-epoch-sp-closure-1375.json': '24e112d11e0c3252ce70e1641b835ce160863e3bc72faa13d2b1f44a92662808',
    'native-single-player-origin-1375.json': '0622c8a67f085984db81aa3c5d2e15675ded40f8466bc7b41643b10ca10a7788',
    'native-single-player-context-1375.json': '0943d8f4b142daf260cbc4ea407fe4b05d6ad9898aa6c40ba44dc25788162bbf',
    'native-world-epoch-1375.json': 'd4ee6ad5c8a3577dff2209ec5884978862552c700338e07ef669bd866a30de05',
}
NEW = (0x10a6ec0, 0x10afa70, 0x6ea0b0, 0x14c2530, 0x80b420)
ANCHORS = (0x1120def, 0x1120f86, 0x1120ff6, 0x1121004, 0x1121685, 0x11216a0,
           0x10dae6c, 0x10dae8b, 0x10dae97, 0x10dae9c, 0x10daead, 0x10daede,
           0x8032d2, 0x8032d8, 0x803d19, 0x803d20, 0x803d27,
           0x6e8aa5, 0x6e8c15, 0x811add, 0x811afa,
           0x1574fb0, 0x1574fb4)


def generate():
    pe = PE(ROOT.parent / 'eu4.exe')
    assert hashlib.sha256(pe.data).hexdigest() == SHA
    md, _ = make_disassembler(Path(os.environ['TEMP']) / 'eu4-native-analysis-deps')
    assert md is not None
    prior_rows = {}
    for filename, digest in INPUTS.items():
        raw = (ROOT / 'work/reports' / filename).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == digest
        prior = json.loads(raw)
        for function in prior['functions'].values():
            for row in function.get('instructions', []):
                prior_rows[int(row['rva'],16)] = row
    selected = []
    for rva in ANCHORS:
        row = prior_rows[rva]
        raw = bytes.fromhex(row['bytes'])
        assert pe.bytes_at(rva, len(raw)) == raw
        selected.append(row)
    functions = {}
    for rva in NEW:
        instructions, edges = bounded_cfg(pe, md, rva, 0x2000, 2000)
        functions[hex(rva)] = {'prefix32': pe.bytes_at(rva,32).hex(),
            'instructions': [{'rva':hex(i.address), 'bytes':i.bytes.hex(), 'instruction':i.mnemonic+' '+i.op_str} for i in instructions],
            'edges': edges}
        check_memory_budget()
    decoded = sum(len(bytes.fromhex(i['bytes'])) for f in functions.values() for i in f['instructions'])
    assert decoded < 16384
    assert pe.u64(pe.to_offset(0x1cb8460)) - pe.base == 0x80b420
    facts = {
      'callback_is_not_frontend': 'Play1120dd0 RCX is a callback object; [callback+30] supplies frontend.1120f86 and1121685 establish this distinction. Bind actual frontend identity, never substitute Play RCX.',
      'holder_is_preserved_into_runtime': '10dae6c loads frontend+330;10dae9c passes it as runtime constructor R9.8032d2 forwards R9 as base constructor R8;6e8aa5/6e8c15 store it at server+330. Fifth parameter [entry_rsp+28] remains frontend+400 and copies to server+1708.',
      'holder_server_publication_is_owned': '10daede calls14c2530 on frontend holder. The function writes holder+70 from the input owning pointer and clears the input; it may destroy the previous server through virtual0 before returning. Observe entry before publication/destruction and bind exit consumption for the expected startup sequence.',
      'server_destructor_backstop': 'Runtime server vtable1cb8460 slot0 is80b420. It calls80b570 and conditionally frees5bc8 bytes. For an already bound server, revoke at entry rather than after its body runs.',
      'frame_is_not_a_lock': 'The bounded10a6ec0 graph includes callbacks at virtual8/a0/388/78 and calls10afa70, whose graph also invokes virtual callbacks. No thread affinity or engine serialization is established by these calls. Existing observed window-thread equality does not prove every destructor runs there.',
      'timing_helper_is_not_publication': '6ea0b0 after runtime construction checks server+2c/+34 and writes+34/+38 using timing calls. It does not publish game+1e00 in this bounded graph. Do not treat its return as world-origin commitment.',
      'finite_synchronization': 'Own event ordering can be made atomic and bounded; it cannot lock engine object lifetime. An observed foreign-thread mutation or reentrant invalidation revokes before native mutation. Publication requires no active opaque scope and unchanged generation, but production remains disabled until thread/lifetime coverage is independently proved.',
    }
    return {'schema':1, 'purpose':'early_origin_observer_design_only', 'game_sha256':SHA,
        'inputs':INPUTS, 'selected_prior_anchors':selected, 'functions':functions,
        'facts':facts, 'new_bound_server_entries':['0x14c2530','0x80b420'],
        'limits':{'new_functions':len(functions),'decoded_bytes':decoded,'decode_limit_bytes':16384,'memory_guard_mib':768},
        'initial_profile':'observed_SP_Play_direct_type2_fallback_only',
        'production_ready':False,'runtime_verified':False,'hook_installed':False,'game_process_accessed':False,
        'remaining_gaps':['No native event capture or hook ABI/trampoline implementation.',
            'Steam type1 path is recorded but does not establish a prototype witness.',
            'No proof all world/context mutation paths share frame/window thread or an engine lock.',
            'No whole-program indirect writer, alias, bulk store or exception coverage.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args = parser.parse_args()
    raw = (json.dumps(generate(),indent=2)+'\n').encode()
    if args.check:
        assert OUTPUT.read_bytes() == raw
    else:
        OUTPUT.write_bytes(raw)
    print(json.dumps({'report':str(OUTPUT),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}))
