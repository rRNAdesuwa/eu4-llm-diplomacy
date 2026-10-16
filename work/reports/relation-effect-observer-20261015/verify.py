"""File-only byte/source checks of the additive reader; never sample a process."""
import argparse,hashlib,json,sys
from pathlib import Path
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'work/deps/capstone-5.0.7'))
from capstone import Cs,CS_ARCH_X86,CS_MODE_64,__version__
from bridge import relation_effect_reader as reader
from work.discover_diplomacy import PE,check_memory_budget


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--check',action='store_true');ap.parse_args()
    pins=reader.verify_manifest();static=json.loads((OUT/'static.json').read_text())
    pe=PE(ROOT.parent/'eu4.exe');assert hashlib.sha256(pe.data).hexdigest()==static['game_sha256']
    for row in static['selected_instructions'].values():
        raw=bytes.fromhex(row['bytes']);assert pe.bytes_at(int(row['rva'],16),len(raw))==raw
    md=Cs(CS_ARCH_X86,CS_MODE_64);assert __version__=='5.0.7'
    rows=0
    for action,reply in static['reply_slot_bytes'].items():
        vt=int(reply['action_vtable_rva'],16);target=int(reply['target_rva'],16)
        assert pe.u64(pe.to_offset(vt+0xd0))-pe.base==target
        raw=b''.join(bytes.fromhex(r['bytes']) for r in reply['instructions'])
        assert pe.bytes_at(target,len(raw))==raw
        assert reply['instructions']==[{'rva':hex(i.address),'bytes':i.bytes.hex(),'mnemonic':i.mnemonic,'operands':i.op_str}
                                       for i in md.disasm(raw,target)]
        rows+=len(reply['instructions'])
        getter=static['loaded_getter_pins'][action]
        assert reader.PROFILES[action]['code']==getter['raw_hex']
    assert static['new_decoded_bytes']==16
    print(json.dumps({'verified':True,'source_pins_including_manifest':len(pins),
                      'retained_instructions':len(static['selected_instructions']),'newly_decoded_bytes':16,
                      'new_instruction_rows':rows,'peak_committed_bytes':check_memory_budget(),
                      'game_process_accessed':False,'native_calls':0,'requests_published':0}))


if __name__=='__main__':main()
