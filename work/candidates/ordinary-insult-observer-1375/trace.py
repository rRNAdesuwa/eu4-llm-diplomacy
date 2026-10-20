"""Finite exact-PE analysis; no process access or native calls."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'work'))
from discover_diplomacy import PE, make_disassembler, check_memory_budget
from map_diplomacy_fields import SHA, bounded_cfg, token_descriptors
from trace_change_subject_type import rows

INPUTS = {
    'work/reports/native-ordinary-insult-effect-1375-initial.json': 'd6ecd628a8a43e006b4b35ea3f6f5e7b2136755eeb3f23016ee7a7e0f2ea02ef',
    'work/reports/native-insult-opinion-layout-1375-initial.json': 'c7d46db1c4a6d69fd59559ddf24ae9d01c322fee7f2ebd87abc56ebfba531442',
    'work/reports/native-insult-modifier-container-1375-initial.json': 'c358e7ce2234b77638ad40cd54eb0d4d7f85d2ed9bc8fbd5dab417a2b2e752b3',
}
ENTRIES = (0x5378f0, 0x384040, 0x383ef0, 0x28c4f0, 0x28ca50, 0x28dc90,
           0x9486a0, 0x948c50, 0x949630, 0x14c8030)
FACTS = {
 'ordinary_branch': {'evidence_rvas':['0x53794e','0x53795d','0x53796e','0x537975'],
   'summary':'Negative insult action index selects cached definition pointer at global233ff08 registry+2f8; target country receives actor full handle at384040. Nonnegative scornful branch is excluded.'},
 'trust': {'evidence_rvas':['0x5379af','0x5379cb'],
   'summary':'Target country bilateral array+1510 indexed by actor slot*48; BYTE+1e becomes clamp(old-5,0,100). This is target trust toward actor, not reverse trust.'},
 'manager_identity': {'evidence_rvas':['0x383ffc','0x38400b','0x28c5c0','0x28c707','0x28c723'],
   'summary':'Bilateral record+0 is manager; manager+10 is owner country and+18 is owner bilateral-array base. Record+10 is counterpart full handle. Observer requires all identities to agree. Manager dynamic vtable remains unclassified and is not used as a class claim.'},
 'container': {'evidence_rvas':['0x28ca76','0x28ca86','0x28cac2','0x28cac6','0x28cacd','0x28c520','0x28c524'],
   'summary':'Manager+300 is outer vector; buffer+308, signed capacity+310/count+314, each country-slot container24B. Inner vtable1c38348, pointer-array+8, signed capacity+10/count+14. 28ca50 may grow the outer array via28dc90; never call it to observe.'},
 'modifier': {'evidence_rvas':['0x28c567','0x28c56e','0x28c575','0x28c57f','0x28c582','0x28c589','0x28c597','0x28c59d'],
   'summary':'Owned28B modifier has vt1ccf4f8/type165, borrowed definition+10, expiry raw date+18, stack count+1c initialized1, signed value milli+20, raw flags24/25/26. Observer only follows known vt/type and exact cached insulted definition; unrelated unknown objects prevent a complete-absence claim.'},
 'definition_name': {'evidence_rvas':['0x94a20c','0x94a221','0x94a228','0x9486af','0x9486b2','0x949651'],
   'summary':'Registry wrapper+2f8 is initialized with literal insulted at1cce358; its cached pointer starts null and wrapper String32 is+8. Modifier definition String32 is+10. Exact pointer plus both names are checked without resolving a lazy cache.'},
 'definition_values': {'evidence_rvas':['0x384074','0x28c589','0x28c5a1','0x28c631'],
   'summary':'Definition+50 signed opinion (multiplied1000), +54 signed duration months, +5c minimum and+60 maximum. Unpacked base insulted defines opinion=-50, months120, yearly_decay5, max0. Runtime definition is separately read; mod precedence is not inferred from base script.'},
 'expiry': {'evidence_rvas':['0x38406a','0x384074','0x384078','0x28c64c','0x28c655','0x28c66a'],
   'summary':'Current raw date is passed through calendar-month helper14c8030 using definition months. Existing modifier expiry can refresh only if later and game+74c8 is null. First observer requires fresh modifier with future expiry; it does not implement arbitrary calendar conversion or refresh attribution.'},
 'serialization': {'evidence_rvas':['0x949649','0x94967e','0x94969e','0x9496c8','0x9496f0','0x94971a'],
   'summary':'Serializer949630 emits definition name, expiry date, fixed-point value, flag26, optional flag24 and stack count. Parent diplomacy save container role resolution is not implemented; no save persistence claim follows.'},
 'mutators_excluded': {'evidence_rvas':['0x28caad','0x537a03'],
   'summary':'Do not invoke28ca50 (array growth),1f9210 (lazy CB registry),384040,383ef0 or any virtual. CB addition and full diplomatic consequences are outside this selected-state observer.'},
}

def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)+'\n').encode()

def build():
    inputs = {}
    for path, expected in INPUTS.items():
        p=ROOT/path
        if not 0<p.stat().st_size<256*1024: raise ValueError('Initial report budget')
        raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=expected: raise ValueError('Initial report changed')
        inputs[path]={'bytes':len(raw),'sha256':expected}
    pe=PE(ROOT.parent/'eu4.exe')
    if hashlib.sha256(pe.data).hexdigest()!=SHA: raise ValueError('Exact executable differs')
    md,_=make_disassembler(Path(tempfile.gettempdir())/'eu4-native-analysis-deps')
    functions={};total=0
    for entry in ENTRIES:
        code,edges=bounded_cfg(pe,md,entry,window=0x3000,max_instructions=2400)
        total+=sum(i.size for i in code)
        if total>32768: raise ValueError('Decode budget')
        functions[hex(entry)]={'instructions':rows(pe,code),'edges':edges}
        check_memory_budget()
    # Fixed initializer slice, not an unbounded scan of the large registry ctor.
    code=list(md.disasm(pe.bytes_at(0x94a206,0x94a22d-0x94a206),0x94a206))
    if sum(i.size for i in code)!=0x27: raise ValueError('Initializer boundary')
    functions['0x94a206']={'instructions':rows(pe,code),'edges':[]}
    total+=sum(i.size for i in code)
    if pe.bytes_at(0x1cce358,9)!=b'insulted\0': raise ValueError('Literal differs')
    tokens=token_descriptors(pe)
    selected={hex(n):tokens[n] for n in (0x2968,0x284d,0x2dca,0x28b0,0x2e6f,0x2aa3)}
    script=ROOT/'work/runtime/unpacked-1.37.5/base/common/opinion_modifiers/00_opinion_modifiers.txt'
    raw=script.read_bytes()
    if len(raw)>256*1024: raise ValueError('Script budget')
    start=raw.find(b'\ninsulted = {');end=raw.find(b'\n}',start)+2
    if start<0 or end-start>256: raise ValueError('Script exact block unavailable')
    all_rows={r['rva']:r for f in functions.values() for r in f['instructions']}
    for value in FACTS.values():
        for rva in value['evidence_rvas']:
            if rva not in all_rows: raise ValueError('Missing evidence anchor '+rva)
    # Only selected direct instructions are reread from a loaded process later.
    anchors=(0x537947,0x53794e,0x53795d,0x53796e,0x537975,0x5379a4,
             0x5379af,0x5379b3,0x5379cb,0x28ca76,0x28cac6,0x28cacd,0x28c567,0x28c56e,
             0x28c575,0x28c589,0x28c707,0x28c723,0x94a20c,0x94a221,0x949651)
    pins=[all_rows[hex(a)] for a in anchors]
    report={'schema_version':1,'purpose':'ordinary_insult_selected_state_static_closure','exe_sha256':SHA,
       'inputs':inputs,'functions':functions,'facts':FACTS,'serializer_tokens':selected,
       'base_script':{'path':script.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(raw).hexdigest(),
                      'block':raw[start:end].decode(),'load_precedence_proven':False},
       'instruction_pins':pins,'decoded_bytes':total,'decoded_instructions':len(all_rows),
       'limits':{'function_count':len(ENTRIES),'window_bytes':0x3000,'instructions_each':2400,'total_bytes':32768,'memory_mib':768},
       'runtime_verified':False,'process_accessed':False,'execution_verified':False,
       'limitations':['No call is authorized by static evidence.','Manager dynamic class, CB effects, calendar refresh matching and parent save record scope remain outside this observer.']}
    dependencies={p:{'sha256':hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),'bytes':(ROOT/p).stat().st_size} for p in (
       'work/probe_diplomacy_current.py','bridge/native_build.py','work/local_config.py',
       'work/discover_diplomacy.py','work/map_diplomacy_fields.py','work/trace_change_subject_type.py')}
    from probe_diplomacy_current import pe_signature
    with pe.path.open('rb') as f: signature=pe_signature(f)
    contract={'schema_version':1,'profile':'ordinary_insult_selected_state_1375_1','exe_sha256':SHA,
       'report_sha256':hashlib.sha256(encoded(report)).hexdigest(),'dependencies':dependencies,
       'pe_signature':signature,'instruction_pins':pins,'inputs':inputs,
       'fixed_actor':'FRA','target_handles':{'ENG':'0x100002e00474e45','POR':'0x10000bd00524f50','NAV':'0x10000bc0056414e','FOI':'0x100007900494f46'},
       'actor_handle':'0x100007a00415246','definition_key':'insulted','registry_rva':0x233ff08,
       'definition_wrapper_offset':0x2f8,'container_vtable_rva':0x1c38348,'modifier_vtable_rva':0x1ccf4f8,
       'modifier_type':0x165,'maximum_country_slots':4096,'maximum_modifiers':256,
       'read_limits':{'single':65536,'total':1048576,'calls':8192},
       'observed_transition':'new ordinary modifier plus target trust decrease only',
       'execution_verified':False,'request_causality_verified':False}
    return {'report.json':encoded(report),'contract.json':encoded(contract)}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args()
    result=build()
    for name,raw in result.items():
        p=HERE/name
        if args.check:
            if p.read_bytes()!=raw: raise ValueError('Generated artifact differs: '+name)
        else:
            with p.open('xb') as f:f.write(raw)
        print(name,len(raw),hashlib.sha256(raw).hexdigest())

if __name__=='__main__':main()
