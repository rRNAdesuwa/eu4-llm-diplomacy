"""Replay selected retained native bytes only; no new decode or process access."""
import hashlib,json,sys
from pathlib import Path
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'work/deps/capstone-5.0.7'))
from capstone import Cs,CS_ARCH_X86,CS_MODE_64,__version__
from work.discover_diplomacy import PE,check_memory_budget
SHA='9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
SOURCES=('work/reports/native-pair-effects-1375.json',
         'work/reports/native-pair-extension-v10-1375.json',
         'work/reports/native-pair-extension-effects-v10-1375.json',
         'work/reports/knowledge-effect-observer-20261015-r1/index-guard/static.json',
         'work/reports/knowledge-effect-observer-20261015-r1/static.json')


def main():
    pe=PE(ROOT.parent/'eu4.exe');assert hashlib.sha256(pe.data).hexdigest()==SHA
    pins={};documents={};lookup={}
    for source in SOURCES:
        raw=(ROOT/source).read_bytes();pins[source]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        document=json.loads(raw);documents[source]=document
        for key,f in document.get('functions',{}).items():
            for row in f['instructions']:lookup[row['rva']]=(source,'/functions/'+key,row)
        for i,f in enumerate(document.get('ranges',[])):
            for row in f['instructions']:lookup[row['rva']]=(source,'/ranges/'+str(i),row)
        check_memory_budget()
    selected={}
    def retain(rva):
        source,pointer,row=lookup[hex(rva)];raw=bytes.fromhex(row['bytes'])
        assert pe.bytes_at(rva,len(raw))==raw
        selected[hex(rva)]={'source':source,'json_pointer':pointer,**row}
    anchors=(0x289bb7,0x289bbb,0x289bbf,0x289bca,0x289bce,0x289bd5,
             0x289d09,0x289d10,0x289d17,0x4e4b97,0x4e4ba8,0x4ef327,0x4ef338,
             0x50f8d2,0x50f91c,0x50f930,0x50f934,0x50f938,0x50f954,
             0x4edb77,0x4edb7a,0x4edbc7,0x4edbcb,0x4edbcf,0x4edbec,
             0x520e89,0x520e8d,0x520e91,0x520ea6,0x4e1504,
             0xa5d242,0xa5d28d,0xa5d2c7,0xa5f275,0xa5f2b6,0xa5f2bb,
             0xa68cf4,0xa68b37)
    for anchor in anchors:retain(anchor)
    getters={}
    for action,source,entry in (
            ('offer_alliance',SOURCES[2],'0xa68d90'),
            ('royal_marriage',SOURCES[0],'0xa68be0'),
            ('guarantee',SOURCES[0],'0xa6a050')):
        rows=documents[source]['functions'][entry]['instructions']
        for row in rows:retain(int(row['rva'],16))
        raw=b''.join(bytes.fromhex(row['bytes']) for row in rows)
        assert pe.bytes_at(int(entry,16),len(raw))==raw
        getters[action]={'entry_rva':entry,'raw_hex':raw.hex(),'bytes':len(raw),
                         'sha256':hashlib.sha256(raw).hexdigest(),'source':source}
    # RAX in the root constructor remains this exact generic index vtable.
    constructor=documents[SOURCES[3]]['functions']['0x289b50']['instructions']
    vt=[row for row in constructor if row.get('rip_target')=='0x1c3a538']
    assert vt
    for row in vt:retain(int(row['rva'],16))
    conditions=json.loads((ROOT/'bridge/tag_action_conditions_1375.json').read_text())
    reply={};md=Cs(CS_ARCH_X86,CS_MODE_64);new_bytes=0
    for action in getters:
        action_vt=int(conditions['actions'][action]['native_check']['vtable_rva'],16)
        callee=pe.u64(pe.to_offset(action_vt+0xd0))-pe.base
        rows=[]
        for i in md.disasm(pe.bytes_at(callee,16),callee):
            rows.append({'rva':hex(i.address),'bytes':i.bytes.hex(),'mnemonic':i.mnemonic,'operands':i.op_str})
            new_bytes+=i.size
            if i.mnemonic=='ret':break
        assert rows[-1]['mnemonic']=='ret' and new_bytes<=16384 and __version__=='5.0.7'
        reply[action]={'action_vtable_rva':hex(action_vt),'reply_required_slot':'0xd0',
                       'target_rva':hex(callee),'prefix16_hex':pe.bytes_at(callee,16).hex(),
                       'newly_decoded':True,'instructions':rows}
    output={'schema':'EU4-RELATION-EFFECT-STATIC/1','game_sha256':SHA,'image_base':hex(pe.base),
            'evidence_kind':'retained ordinary native instruction replay, not REA decompilation',
            'selected_instructions':selected,'loaded_getter_pins':getters,'reply_slot_bytes':reply,
            'typed_index_vtable_rva':'0x1c3a538','new_decoded_bytes':new_bytes,
            'source_pins':pins,'game_process_accessed':False,'native_calls':0,
            'peak_committed_bytes':check_memory_budget()}
    (OUT/'static.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps({'retained_instructions':len(selected),'new_decoded_bytes':new_bytes,'reply':reply,
                      'peak_committed_bytes':output['peak_committed_bytes']}))


if __name__=='__main__':main()
