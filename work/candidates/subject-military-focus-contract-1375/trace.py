"""Exact-build, disk-only, bounded military-focus command evidence. No process API."""
from __future__ import annotations
import argparse, hashlib, json, os, struct, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'work'))
from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg, token_descriptors

SOURCES = [
 'work/reports/native-subject-special-paths-1375.json',
 'work/reports/local-transport-submit-1375.json',
 'work/reports/preview-string-and-transport-1375.json',
 'work/candidates/next-diplomacy-interface-scope-1375/report.json',
 'work/candidates/next-diplomacy-interface-scope-1375/review.json',
 'work/discover_diplomacy.py', 'work/map_diplomacy_fields.py',
 '../common/subject_types/00_subject_types.txt', '../interface/countrysubjectsview.gui',
]
ENTRIES = [0x2b2850, 0x98940, 0xd2f410, 0x95660, 0xf4f9e0, 0xf576f0,
 0xf5d880, 0x3d79f0, 0x975360, 0x9753f0, 0x14c6290, 0x14c63c0,
 0x14c6500, 0x14c6930, 0x14ca210, 0x1580ff0, 0x1580e60]
# Exact independently reached blocks, excluding jump-table bytes. Parser is
# 7,353 bytes including embedded data: deliberately do not decode its whole body.
BLOCKS = [(0x975381,0x9753d3), (0x975434,0x975476),
 (0x24a84d,0x24a86b), (0xb1ef50,0xb1ef93), (0xb1f585,0xb1f5c7),
 (0xb202a1,0xb202f6), (0xb1fca1,0xb1fcb5), (0xb2036b,0xb2037f),
 (0xb23427,0xb2345e)]
FOCUS_OLD = [0x2b28c0,0x2b28f0,0x2b2900,0x2b29b0,0x2b2a70,0x2b2b30,
 0xf59b70,0x85420,0x85480,0x854f0,0x85560,0x855d0,0x85640,0x856a0]

def bounded(path, limit=8*1024*1024):
    with path.open('rb') as f: raw=f.read(limit+1)
    if len(raw)>limit: raise ValueError('Input budget exceeded: '+str(path))
    return raw

def record(path):
    raw=bounded(ROOT/path)
    return {'path':path,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}

def encode(i, cs):
    r={'rva':hex(i.address),'bytes':i.bytes.hex(),'instruction':(i.mnemonic+' '+i.op_str).strip()}
    for o in i.operands:
        if o.type==cs.CS_OP_MEM and o.mem.base==cs.x86_const.X86_REG_RIP:
            r['rip_target_rva']=hex(i.address+i.size+o.mem.disp)
    return r

def generate():
    p=PE(ROOT.parent/'eu4.exe')
    assert hashlib.sha256(p.data).hexdigest()==SHA
    md,cs=make_disassembler(Path(os.environ.get('TEMP',''))/'eu4-native-analysis-deps')
    if md is None: raise ValueError('Capstone required')
    funcs={}; new_bytes=0
    for a in ENTRIES:
        ins,e=bounded_cfg(p,md,a,window=8192,max_instructions=2500)
        n=sum(i.size for i in ins); assert n<=8192
        funcs[hex(a)]={'kind':'new_bounded_cfg','decoded_bytes':n,'instructions':[encode(i,cs) for i in ins],'edges':e}
        new_bytes+=n; check_memory_budget()
    for a,b in BLOCKS:
        ins=list(md.disasm(p.bytes_at(a,b-a),a)); assert sum(i.size for i in ins)==b-a
        funcs[hex(a)]={'kind':'new_exact_block','end_rva':hex(b),'decoded_bytes':b-a,'instructions':[encode(i,cs) for i in ins]}
        new_bytes+=b-a
    assert new_bytes<=65536
    old=json.loads(bounded(ROOT/SOURCES[0]))
    assert old['game_sha256']==SHA
    for a in FOCUS_OLD:
        f=old['functions'][hex(a)]
        funcs[hex(a)]={'kind':'reused_cfg','source':SOURCES[0],'json_pointer':'/functions/'+hex(a),**f}
    for name,wanted in [(SOURCES[1],{0x1580370}),(SOURCES[2],{0x1580270})]:
        j=json.loads(bounded(ROOT/name)); assert j['binary_sha256']==SHA
        for f in j['functions']:
            a=int(f['requested_rva'],16)
            if a not in wanted: continue
            rows=[{'rva':i['rva'],'bytes':i['bytes'],'instruction':(i['mnemonic']+' '+i['operands']).strip()} for i in f['instructions']]
            funcs[hex(a)]={'kind':'reused_linear','source':name,'instructions':rows,'decoded_bytes':sum(len(bytes.fromhex(i['bytes'])) for i in rows)}
    lookup={}
    for f in funcs.values():
        for i in f['instructions']:
            assert p.bytes_at(int(i['rva'],16),len(bytes.fromhex(i['bytes'])))==bytes.fromhex(i['bytes'])
            lookup[i['rva']]=i
    tokens=token_descriptors(p)
    token_rows={hex(k):tokens[k] for k in [0x3017,0x3018,0x3019,0x35c3,0x3695,0xc7,0xcc,0xdb,0x240]}
    vt={hex(i):hex(p.u64(p.to_offset(0x1c54678)+i)-p.base) for i in range(0,0xa8,8)}
    assert all(p.executable(int(v,16)) for v in vt.values())
    pins=[{'rva':'0x1c54678','bytes':p.bytes_at(0x1c54678,0xa8).hex(),'meaning':'command vtable 21 slots'}]
    pins.append({'rva':'0x1ce7488','bytes':p.bytes_at(0x1ce7488,0x28).hex(),'meaning':'subject definition vtable through parser slot20'})
    switches=[]
    for token,base,bt,jt,expected in [(0x35c3,0x3521,0xb208e4,0xb20844,0xb1fca1),(0x3695,0x365d,0xb209f0,0xb209cc,0xb2036b)]:
        ix=p.bytes_at(bt+token-base,1)[0];dst=p.u32(p.to_offset(jt+4*ix));assert dst==expected
        switches.append({'token':hex(token),'base':hex(base),'byte_index_rva':hex(bt+token-base),'index':ix,'target_cell_rva':hex(jt+4*ix),'target':hex(dst)})
        for a,n in [(bt+token-base,1),(jt+4*ix,4)]:pins.append({'rva':hex(a),'bytes':p.bytes_at(a,n).hex(),'meaning':'exact parser switch cell'})
    for a in [0x9753d4,0x9754a4]:pins.append({'rva':hex(a),'bytes':p.bytes_at(a,24).hex(),'meaning':'six enum switch targets'})
    assertions={
     'ctor_default':['0x2b2852','0x2b2885','0x2b28a5','0x2b28ac','0x2b28b4'],
     'prototype_registration':['0x24a852','0x24a85e','0x24a866','0x14c6946','0x14c69e2'],
     'clone_consumed_string':['0x14c68c1','0x14c68fe','0x14c6903','0x14c690b','0x2b2b14'],
     'destructor':['0x98959','0x9895d','0x98962','0x98967','0x9896f'],
     'native_gate_is_not_authority':['0x2b2b30','0x2b2b4a','0x2b2b4e','0x2b2b57','0x2b2b5d'],
     'effect':['0x2b28c0','0x2b28e7'],
     'overlord_subject_vector':['0xf4fa1a','0xf4fa4f','0xf4fa97','0xf4faf5','0xf4fbe1'],
     'definition_field_binding':['0xb1f5b3','0xb1f5bb','0xb1fca1','0xb202e2','0xb202ea','0xb2036b'],
     'definition_identity':['0xb23427','0xb2342e','0xb23435','0xb23439'],
     'gui_conditions':['0xf57c68','0xf57dc5','0xf57dd5','0xf57e2b','0xf5dd1e','0xf5dd4b'],
     'tls_query_has_side_effect_path':['0x97539b','0x9753b2','0x9753bc'],
     'context_consumes_before_checks':['0x14ca22a','0x14ca22d','0x14ca234','0x14ca253','0x14ca299'],
     'transport_serializes_reconstructs_enqueues':['0x1580563','0x15809d0','0x15809ef','0x1580a33','0x1581102'],
    }
    facts=json.loads(bounded(HERE/'contract.json'))
    return {'schema_version':1,'binary_sha256':SHA,'analysis':'disk-only static candidate',
     'runtime_verified':False,'execution_verified':False,'production_supported':False,
     'inputs':[record(x) for x in SOURCES], 'contract':facts,'enum_bindings':old['enum_bindings']['military_focus'],
     'command_vtable':vt,'tokens':token_rows,'parser_switches':switches,'data_pins':pins,
     'facts':{k:{'evidence':[lookup[r] for r in v]} for k,v in assertions.items()},'functions':funcs,
     'limits':{'each_cfg_window_bytes':8192,'new_decoded_bytes':new_bytes,'new_total_limit':65536,
       'exploratory_unique_byte_upper_bound':45056,'exploratory_claims_excluded':['misaligned/raw pattern candidates','unrelated GUI method 3ce0b0'],
       'reused_instructions_verified':sum(len(f['instructions']) for f in funcs.values() if f['kind'].startswith('reused')),
       'all_unique_instruction_anchors':len(lookup),'memory_guard_bytes':805306368},
     'limitations':facts['unsupported']}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args()
    raw=(json.dumps(generate(),ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
    path=HERE/'report.json'
    if args.check: assert bounded(path)==raw,'report differs'
    else: path.write_bytes(raw)
    print(json.dumps({'pass':True,'check':args.check,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}))
if __name__=='__main__':main()
