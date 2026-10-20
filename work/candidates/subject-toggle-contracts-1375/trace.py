"""Disk-only exact-build subject toggle evidence. No process or native calls."""
from __future__ import annotations
import argparse, hashlib, json, os, struct, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'work'))
from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg, token_descriptors

SOURCES=[
 'work/reports/native-subject-interactions-1375.json',
 'work/candidates/subject-military-focus-contract-1375/report.json',
 'work/candidates/subject-military-focus-observer-1375/report.json',
 'work/candidates/next-diplomacy-interface-scope-1375/report.json',
 'work/discover_diplomacy.py','work/map_diplomacy_fields.py',
 '../common/subject_types/00_subject_types.txt',
 'work/AGENTS.md',
 'work/reports/native-pair-extension-v11-1375.json',
]
NEW=[0xaf9280,0xaf9570,0xaf9600,0xaf98f0,0xaf9d80,
 0xafc980,0xafcc30,0xafccb0,0xafd300,
 0xb062c0,0xb068a0,0xb06b60,0xb070f0,
 0xaf61b0,0xe61f0,0xe6260,0xe6280,0xe66b0,0x8f440,0xb22910,
 0x327dc0,0x36cb20,0xb35df0,0x3c5680,0xa612b0,0xb23e70,0xc0330,
 0xf5d330,0xf5c6f0,0xf5c7c0,0xa9250,0xf65890,0x14ca2d0]
REUSE=[0x81ee0,0x820f0,0x82720,0xaf37c0,0xaf3860,0xaf3af0,0xaf3b70,
 0xaf3bc0,0xaf3cd0,0xaf3e20,0xaf3e70,0xaf3f80,0xaf4030,0xaf41b0,
 0xa7040,0xa7070,0xa7180,0xaf9250,0xafc950,0xb06290]
FACTS={
 'constructor':['0xaf386d','0xaf38a2','0xaf38b4','0xaf38b8','0xaf38cd','0xaf38ed','0xaf38f7'],
 'state_getters':['0xe61f0','0xe6260','0xe6280','0xaf4068','0xaf4092','0xaf409c'],
 'gate':['0xaf3e3c','0xaf3e43','0xaf3e48','0xaf3eb3','0xaf3ee1','0xaf3ee9','0xaf3ef9','0xaf3f35','0xaf3f5c'],
 'visibility_mutation_boundary':['0xaf61b4','0xaf61bd','0xaf61c6','0xaf61e2','0xaf61ec'],
 'family_checks':['0xaf9579','0xaf95a0','0xaf95b4','0xafcc57','0xafcc6b','0x8f440'],
 'definition_allowed_map':['0xb234af','0xb234b7','0xb243c5','0xb243cc','0xc0346','0xc034a','0xc035d','0xc0361','0xc0370','0xc0378','0xb2294c','0xb2295e','0xb2296f','0xb22972','0xb22984','0xb22995','0xb229aa'],
 'clone_consumes_second_argument':['0xaf3b70','0xaf3ba2','0xaf3ba5','0xa70b7','0xa70ef','0xa714a','0xa714f','0xa715c'],
 'destructor':['0xa7049','0xa704d','0xa7059','0xa7065','0xa718f','0xa7193','0xa719f','0xa71a6','0xa71ab','0xa71b0','0xa71b8'],
 'serialization':['0xaf3bda','0xaf3bf3','0xaf3c2b','0xaf3c64','0xaf3c68','0xaf3c75','0xaf3c8b','0xaf3de5'],
 'normal_ui':['0xf5c706','0xf5c711','0xf5c7d9','0xf5c7ee','0xf5c8c3','0xf5c8dc','0xf5c8f0','0xf5c907','0xf5c913'],
 'context_handoff':['0x14ca2da','0x14ca2ec','0x14ca323','0x14ca332','0x14ca33d','0x14ca340'],
 'type2_normal_lifetime':['0x1580379','0x1580395','0x15809d0','0x15809ef','0x1580a33','0x1580c4a','0x1580c55','0x1580c5a'],
 'bit_writes':['0xaf92f9','0xafc9fa','0xb06346'],
 'broad_effect_recomputation':['0xaf930a','0xafca0b','0xb06357','0x327edd','0x327f86','0x327f8a','0x327f96','0x328097','0x328215','0x328318'],
 'embargo_rival_loop':['0xaf932d','0xaf9340','0xaf9344','0xaf934b','0xaf9352','0xaf9359','0x36cb3a','0x36cb92','0x36cbaa','0x36cbb8'],
 'scutage_cancel_additive_modifier':['0xafca10','0xafca19','0xafca1e','0xafca25','0xb35e10','0xb35e36','0x3c569c','0x3c56b7','0x3c5707','0x3c573b','0x3c5745','0x3c57de'],
 'divert_deletes_prior_transfer_both_modes':['0xb0637e','0xb063df','0xb063e2','0xb064da','0xb064e7','0xb064f4','0xb0653e'],
 'divert_enable':['0xb0662a','0xb0664d','0xb06651','0xb06655','0xb0665e','0xb0666a','0xb0666f','0xb06675','0xb06678'],
 'divert_disable_can_restore_half':['0xb065af','0xa612db','0xa612e4','0xa612f1','0xa612f9','0xa6131a','0xa613bf','0xa613c3','0xa613db','0xa613e0','0xa613e7'],
}

def bounded(p,limit=8*1024*1024):
    with p.open('rb') as f: raw=f.read(limit+1)
    if len(raw)>limit:raise ValueError('bounded input exceeded: '+str(p))
    return raw
def rec(name):
    raw=bounded(ROOT/name)
    return {'path':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def enc(i,cs):
    r={'rva':hex(i.address),'bytes':i.bytes.hex(),'instruction':(i.mnemonic+' '+i.op_str).strip()}
    for o in i.operands:
        if o.type==cs.CS_OP_MEM and o.mem.base==cs.x86_const.X86_REG_RIP:
            r['rip_target_rva']=hex(i.address+i.size+o.mem.disp)
    return r
def generate():
    pe=PE(ROOT.parent/'eu4.exe');assert hashlib.sha256(pe.data).hexdigest()==SHA
    if (HERE/'input-pins.json').exists():
        assert json.loads(bounded(HERE/'input-pins.json'))==[rec(n) for n in SOURCES],'input pins changed'
    md,cs=make_disassembler(Path(os.environ.get('TEMP',''))/'eu4-native-analysis-deps')
    assert md is not None
    fs={};new_bytes=0
    for a in NEW:
        ins,edges=bounded_cfg(pe,md,a,window=8192,max_instructions=2500)
        n=sum(i.size for i in ins);assert n<=8192
        fs[hex(a)]={'kind':'new_bounded_cfg','decoded_bytes':n,'instructions':[enc(i,cs) for i in ins],'edges':edges}
        new_bytes+=n;assert new_bytes<=49152;check_memory_budget()
    old=json.loads(bounded(ROOT/SOURCES[0]));assert old['binary']['sha256']==SHA
    for a in REUSE:
        fs[hex(a)]={'kind':'reused_cfg','source':SOURCES[0],'json_pointer':'/functions/'+hex(a),**old['functions'][hex(a)]}
    mil=json.loads(bounded(ROOT/SOURCES[1]));assert mil['binary_sha256']==SHA
    for a in [0x3d79f0,0xf4f9e0,0x95660,0x14c6290,0x14c63c0,0x14c6500,0x14ca210,0x1580370,0x1580ff0]:
        fs[hex(a)]={'kind':'reused_cfg','source':SOURCES[1],'json_pointer':'/functions/'+hex(a),**mil['functions'][hex(a)]}
        fs[hex(a)]['kind']='reused_cfg';fs[hex(a)]['source']=SOURCES[1]
        fs[hex(a)]['json_pointer']='/functions/'+hex(a)
    other=json.loads(bounded(ROOT/SOURCES[-1]));assert other['game_sha256']==SHA
    for a in [0xa749f0,0xa74b90]:
        fs[hex(a)]={**other['functions'][hex(a)],'kind':'reused_cfg','source':SOURCES[-1],'json_pointer':'/functions/'+hex(a)}
    ro=json.loads(bounded(ROOT/SOURCES[2]));assert ro['exe_sha256']==SHA
    for a in [0xb231f0,0x1fd1a0,0xa62b40]:
        fs[hex(a)]={**ro['functions'][hex(a)],'kind':'reused_cfg','source':SOURCES[2],'json_pointer':'/functions/'+hex(a)}
    anchors={}
    for f in fs.values():
        for i in f['instructions']:
            raw=bytes.fromhex(i['bytes']);assert pe.bytes_at(int(i['rva'],16),len(raw))==raw
            anchors[i['rva']]=i
    facts={key:{'evidence':[anchors[r] for r in refs]} for key,refs in FACTS.items()}
    selected=[x for x in old['actions'] if x['name'] in ['scutage','divert_trade','embargo_rivals']]
    pins=[];vts={}
    for x in selected:
        a=int(x['singleton_rva'],16)
        pins.append({'rva':hex(a),'bytes':pe.bytes_at(a,16).hex(),
          'meaning':'disk initial singleton; startup registration replaces vtable, token +8 and flags +c=1/+d=0 remain literal initial values'})
    for a,n in [(0x1c3a650,0xa8)]+[(int(x['vtable_rva'],16),0x48) for x in selected]:
        raw=pe.bytes_at(a,n);pins.append({'rva':hex(a),'bytes':raw.hex(),'meaning':'vtable exact slots'})
        vts[hex(a)]={hex(i):hex(struct.unpack_from('<Q',raw,i)[0]-pe.base) for i in range(0,n,8)}
    tokens=token_descriptors(pe)
    names={hex(k):tokens.get(k) for k in [0x31d8,0x31da,0x31db,0x31df,0x3224,0x28e9,0x2cb6,0x3228,0x2e09,524,15]}
    strings=[]
    for a in [0x1ce4670,0x1ce4d08,0x1ce49c8,0x1ce4d48,0x1ce53b0,0x1ce46d8,0x1ce46f0,0x1ce4d80,0x1ce4d90,0x1ce4f40,0x1ce4f60]:
        raw=pe.bytes_at(a,256).split(b'\0',1)[0];assert len(raw)<256
        strings.append({'rva':hex(a),'bytes':(raw+b'\0').hex(),'text':raw.decode('ascii')})
    contract=json.loads(bounded(HERE/'contract.json')) if (HERE/'contract.json').exists() else None
    return {'schema_version':1,'binary_sha256':SHA,'runtime_verified':False,'execution_verified':False,
      'production_supported':False,'analysis':'bounded disk-only static candidate',
      'inputs':[rec(n) for n in SOURCES],'actions':selected,'command':old['command'],'registry':old['registry'],
      'command_and_singleton_vtables':vts,'data_pins':pins,'strings':strings,'tokens':names,'functions':fs,'contract':contract,'facts':facts,
      'limits':{'each_cfg_window_bytes':8192,'total_new_decoded_limit':49152,'new_decoded_bytes':new_bytes,
        'unique_instruction_anchors':len(anchors),'memory_guard_bytes':805306368,
        'cfg_boundary_note':'Reachable bounded graphs, not proven complete function bodies; no recursive callee decode. Tail branches and indirect/unwind edges remain explicit or unsupported.',
        'exploratory_new_decode_outside_report':0,
        'call_discovery':'find_calls.py scans executable-section raw bytes for four exact rel32 targets only (no decoded scan); raw candidates are not instruction-alignment proof.'}}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args()
    raw=(json.dumps(generate(),sort_keys=True,ensure_ascii=False,indent=2)+'\n').encode();p=HERE/'report.json'
    if a.check:assert bounded(p)==raw,'report differs'
    else:p.write_bytes(raw)
    print(json.dumps({'pass':True,'check':a.check,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'peak_committed_bytes':check_memory_budget()}))
if __name__=='__main__':main()
