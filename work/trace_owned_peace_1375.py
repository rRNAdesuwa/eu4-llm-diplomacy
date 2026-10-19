"""Bounded disk-only owned requestpeace/CPeaceOffer lifecycle evidence."""
from __future__ import annotations
import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg, token_descriptors
from trace_change_subject_type import rows

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'work/reports/native-owned-peace-1375.json'
NATIVE=ROOT/'work/reports/native-diplomacy-1.37.5.json'
NATIVE_SHA='c64df6e043c9e7a498a25082e0e768902764e4a271ab3579f0eaddb2f1391633'
FIELDS=ROOT/'work/reports/native-action-fields-1375.json'
FIELDS_SHA='cfabb4622b7c82f9e2476a82352f91fa5d0f8ba0f8150e75aac47fb4aeaddc96'
ENTRIES=(0x598af0,0x598b60,0x59ba40,0x59b450,0x59bb00,0x59bb70,0x59bd20,0x59bde0,
         0x2c6890,0x2c6980,0x975d40,0x975f40,0x9761c0,0x976290,0x976430,
         0x144150,0x998290,0x994280,0x130c280,0x1311670,0x1314340,0x1314c00,0x1314d10,
         0x2c67a0,0x9a1040,0x2761b0,0x1629e0,0x8eac0,0xc03b0,0x415e00,0x415e60,
         0x997280,0x13067b0,0x97bea0,0x978cd0,0x976120,0x163c90,0x97bd30,0x415d80,
         0x998000,0x981170,0x981690,0x97ed00,0x999850,0x179550,0x1795c0,0x1795f0,0x99af60,0x99a1d0,0x35d3aa)

def fact(summary,*rvas):
    return {'summary':summary,'evidence_rvas':list(map(hex,rvas)),'runtime_verified':False}

FACTS={
    'requestpeace_factory':fact('The selected generic factory branch allocates0x210, constructs a temporary default CPeaceOffer, calls598af0 with invalid actor/target handles,date0x29c77f8,demand1, then cleans the temporary. This is a constructor path, not permission to hand-zero nested containers.',
        0x35d3aa,0x35d3af,0x35d3f8,0x35d408,0x35d410,0x35d415,0x35d429,0x35d435),
    'requestpeace_constructor':fact('598af0(this,actor,target,demand,offer_ptr,date) writes base actor/original+10/+18,target+20,date+28/+2c,envoy-1,state0,value1,ID0. It sets diplomats+40=1,demand+41=R9B, deep-copies offer_ptr into embedded+48 via975f40, then sets force+208=0. The constructor itself does not allocate the outer0x210.',
        0x598b04,0x598b08,0x598b0c,0x598b10,0x598b21,0x598b26,0x598b39,0x598b3d,0x598b45,0x598b4a,0x598b4f),
    'requestpeace_clone_and_delete':fact('59ba40 allocates0x210, copies base/three derived bool fields and deep-copies the embedded offer from source+48 to destination+48. 598b60 always cleans embedded+48 through9761c0, then frees outer0x210 only when deleting flag bit0 is set. Never separately deleting-destruct the embedded offer.',
        0x59ba4d,0x59ba52,0x59babb,0x59bac2,0x59bacd,0x59bad1,0x59bad6,0x598b6f,0x598b73,0x598b82,0x598b87,0x598b8f),
    'default_offer_is_not_zero_memory':fact('2c6890 installs vt1c578b8/type165, invalid giver/taker handles,is_demand0; zeros seven vector triples+28..c8 and the bucket triple+d0. Helper2c67a0 initializes owner+e8, an f8 hash with an allocated0x30 sentinel/16 bucket pointers and two40-byte composite hash structures at138/178. Flags1b8=0,1b9=1. Default empty object still has native-owned allocations.',
        0x2c689d,0x2c68ab,0x2c68ae,0x2c68cf,0x2c68d2,0x2c6905,0x2c6944,0x2c6963,0x2c6968,0x2c67b7,0x2c67d3,0x2c67d6,0x2c67e2,0x2c680f,0x2c6812,0x2c681c,0x2c6829),
    'parameter_offer_constructor':fact('975d40(this,taker,giver,is_demand) stores R8 at+10,RDX at+18,R9B at+20; after owned-container initialization it resolves participants via97bea0, ensures40 type-index bucket vectors, initializes auxiliary state with978cd0 and enumerates native candidate terms with97ed00. This is world-dependent work, not merely scalar initialization.',
        0x975d71,0x975d75,0x975d79,0x975e0e,0x975e20,0x975e44,0x975ed2,0x975efb,0x975f0c,0x975f14,0x97ed33,0x97ee32,0x97ee91,0x981112),
    'participant_vectors':fact('Exact serializer tokens establish +10 giver314c,+18 taker314d,+20 is_demand314f; +58 givers3238,+70 takers3239,+28 war_givers323a,+40 war_takers323b; +1b9 apply_penalties3ca6. These four vectors contain8-byte country handles, not owned country pointers. Helper144150 allocates independent vector storage and copies8-byte values only.',
        0x9816a9,0x9816b0,0x9816dc,0x9816e1,0x981705,0x981709,0x981716,0x98171a,0x981727,0x98172b,0x981738,0x98173c,0x981749,0x98174e,0x98176e,0x98177b,0x144190,0x1441a4,0x1441c0,0x1441c7),
    'offer_copy_and_owner_fixup':fact('975f40 allocates independent storage for four participant vectors; zero-initializes component/index triples; copies hash containers through998290/994280; copies1b8/1b9. It sets owner+e8=this, resets components/index with976290, then clones source components with976430. The latter temporarily copies source owner/state but finally rewrites+e8 to destination. A memcpy would alias native allocations and retain a wrong owner.',
        0x975f85,0x975f93,0x975fa1,0x975faf,0x975fb7,0x97600b,0x9760ac,0x9760bd,0x9760d1,0x9760de,0x9760ec,0x9760f3,0x9760f9,0x976104,0x9765fd,0x976704),
    'offer_assignment':fact('976120 is assignment to an already constructed destination: it first deletes old components/replaces buckets via976290, assigns four participant vectors with1419c0, copies giver/taker/demand/apply_penalties, then clones components/state via976430. It is not the uninitialized-memory constructor ABI.',
        0x976130,0x97613d,0x976149,0x976152,0x976164,0x976176,0x976188,0x976194,0x9761a1,0x9761a7),
    'component_vector_owns_objects':fact('Offer+88..98 stores owned component pointers. 976430 iterates every source pointer and calls9a1040, appending a separately allocated clone. Type virtual+78 returns a type descriptor whose firstDWORD indexes40 cases; 9a1040 rejects indices>39. All40 cases independently match existing factory vtables and make one allocation with field copies. The four deleting destructors only restore base vtable and optionally free their0x30/38/40/48 allocation; no recursively owned per-component allocations are freed on these paths.',
        0x976452,0x976479,0x976480,0x9764a0,0x9a1051,0x9a1054,0x9a1057,0x9a106a,0x9a1074,0x179563,0x179568,0x17956d,0x1795d8,0x1795dd,0x179608,0x17960d,0x99af78,0x99af7d),
    'selected_component_index':fact('Only clones with component+20 nonzero are inserted into the+d0 type-index buckets. The source bucket ordinal of the original pointer is preserved when found; otherwise the clone is appended. Bucket entries alias the owned+88 objects and are not separate owners. 976290 deletes+88 pointees through virtual deleting destructor0(1), sets end=begin, then replaces+d0 with40 zero vector triples allocated by997280.',
        0x9764c9,0x9764de,0x9764e7,0x976510,0x976550,0x9765d7,0x9762d7,0x9762e3,0x9762e8,0x9762fe,0x976315,0x97632e,0x997289,0x99728e,0x9972a3,0x9975ba,0x9975c0),
    'hash_nested_value_storage':fact('Offer+f8 hash has separately allocated0x30 linked nodes and bucket pointer storage. Nodes use DWORD key+10 and an owned vector at node+18;999850 allocates/copies0x68-byte records via99a1d0. Cleanup415e60 calls163c90 to release each node vector then frees every0x30 node and sentinel.163c90 frees the buffer without per-element destructor calls;99a1d0 performs field copies. The game meaning of these0x68 records remains unidentified.',
        0x9982e3,0x99830c,0x99836a,0x99836f,0x998384,0x9998ae,0x9998b5,0x9998d3,0x99a1f3,0x99a2de,0x415e93,0x415e97,0x415e9c,0x415ea4,0x415eb9,0x163cba,0x163cdf),
    'composite_hash_storage':fact('Offer+138/+178 are independent40-byte composite hash objects:994280 allocates a0x40 sentinel and bucket vector, copies metadata, and copies nodes with998000. Cleanup415e00 frees linked0x40 nodes/sentinel without recursively destructing their payload. C03b0 releases the separate bucket vector. Payload semantics are not fully named.',
        0x9942a8,0x9942ab,0x9942b7,0x9942bb,0x9942ea,0x9942f9,0x9761e3,0x9761ea,0x9761ef,0x9761f6,0x9761fb,0x976202,0x415e33,0x415e38,0x415e4d,0x415e57),
    'offer_cleanup_order':fact('9761c0 first virtually deletes owned component objects via2761b0, then frees auxiliary hashes138/178/f8, frees each+d0 bucket buffer and the outer vector through1629e0, then releases+a0,+b8,+88 and the four participant vector buffers through8eac0. Index/buffer cleanup does not delete component pointers again. Standalone deleting destructor2c6980 invokes cleanup before optional free1c0; embedded requestpeace uses cleanup only.',
        0x9761de,0x2761ef,0x2761f4,0x27620d,0x976226,0x976232,0x162a06,0x162a61,0x97623e,0x97624a,0x976256,0x97625f,0x976268,0x976271,0x976284,0x2c6980),
    'gui_negotiation_direction':fact('13067b0 records selected target in GUI+2c. For demand it calls975d40(dst,current player,target,1), making target giver/player taker; its copy/assignment goes into GUI+48. For offer it calls975d40(dst,target,current player,0), making player giver/target taker, then assigns GUI+208. Existing per-target cached offers can instead be copied. GUI+660 chooses which of the two complete objects is used, not a flip of the outer action actor/target.',
        0x13067d5,0x13067fb,0x1306863,0x1306866,0x1306871,0x13068a9,0x13068b2,0x130690a,0x1306962,0x1306965,0x1306970,0x130699d,0x13069a9,0x130c2a5,0x130c2b2,0x130c2bb),
    'gui_request_assembly':fact('130c280 builds a temporary outer requestpeace with current player in actor/original, GUI+2c as recipient, current game date,envoy-1,state0,value1,diplomats1,demand=GUI+660,force0. It deep-copies selected GUI+48 or+208 into embedded+48 and cleans it before returning. It uses request virtual+120 for UI evaluation; this traced function is not itself evidence of a final submit.',
        0x130c29f,0x130c2c2,0x130c2e1,0x130c2f0,0x130c2f5,0x130c2fa,0x130c307,0x130c315,0x130c32c,0x130c331,0x130c33e,0x130c343,0x130c3a4,0x130c3c2,0x130c51f),
    'war_is_resolved_from_current_pair':fact('97bd30 resolves offer.taker through country lookup, then giver counterpart record and root+50/DWORD+5c 16-byte index to return the current pair war pointer.97bea0 copies that war+48/+78 full side vectors into war_givers/war_takers according to taker membership, and builds actual givers/takers depending on leader/subject membership. This is a borrowed current-world lookup, not an owned war field or a public arbitrary war-ID selector.',
        0x97bd30,0x97bd34,0x97bd56,0x97bd5e,0x97bd73,0x97bd77,0x97bd87,0x97bd97,0x97beaa,0x97bebb,0x97bec8,0x97bf0f,0x97bf1e,0x97bf23,0x97bf3c,0x97bf41,0x97bff0,0x97c180),
    'request_validity_and_reply':fact('Request validity59b450 independently looks up pair war and rejects absence; it calls59ae00 with actor,target,war and checks treaty-derived province/participant conditions plus base legality.59bb00 is vtable+d0 reply predicate: state must0 and cfd70 on counterpart diplomacy record must<=1; it is not GUI assembly or submission.',
        0x59b4b1,0x59b4b5,0x59b4c7,0x59b4d2,0x59b4f1,0x59b50f,0x59b545,0x59b5d0,0x59bb04,0x59bb4c,0x59bb51,0x59bb56),
    'request_serialized_fields':fact('Request parser/serializer confirm diplomats2746 at+40,demand29df at+41,embedded terms29de at+48,force19e at+208. Terms serialization/parsing go through the embedded CPeaceOffer serializer/parser virtual dispatch. Existence of a force flag is not approval to bypass normal legality or acceptance.',
        0x59bd3e,0x59bd62,0x59bd82,0x59bd9a,0x59bda8,0x59be17,0x59be1d,0x59be2a,0x59be2e,0x59be34,0x59be42),
}

def generate():
    raw=NATIVE.read_bytes()
    if len(raw)>2*1024*1024 or hashlib.sha256(raw).hexdigest()!=NATIVE_SHA:raise ValueError('Native input changed')
    native=json.loads(raw)
    field_bytes=FIELDS.read_bytes()
    if len(field_bytes)>2*1024*1024 or hashlib.sha256(field_bytes).hexdigest()!=FIELDS_SHA:raise ValueError('Fields input changed')
    fields=json.loads(field_bytes)
    action=next(a for a in native['native_actions']['actions'] if a['name']=='requestpeace')
    pe=PE(ROOT.parent/'eu4.exe')
    if hashlib.sha256(pe.data).hexdigest()!=SHA:raise ValueError('Wrong executable')
    md,_=make_disassembler(Path(tempfile.gettempdir())/'eu4-native-analysis-deps')
    functions={};decoded=0
    for entry in ENTRIES:
        if len(functions)>=52:raise ValueError('Function budget exceeded')
        code,edges=bounded_cfg(pe,md,entry,window=0x6000,max_instructions=5000)
        decoded+=sum(i.size for i in code)
        if decoded>128*1024:raise ValueError('Decode budget exceeded')
        functions[hex(entry)]={'pdata':list(map(hex,pe.function(entry) or ())), 'instructions':rows(pe,code),'edges':edges}
        check_memory_budget()
    component_cases=[]
    for index in range(40):
        table=0x9a1d9c+index*4;entry=pe.u32(pe.to_offset(table))
        if not 0x9a1076<=entry<0x9a1d93:raise ValueError('Unexpected clone switch target')
        code,edges=bounded_cfg(pe,md,entry,window=0x1800,max_instructions=700)
        decoded+=sum(i.size for i in code)
        if decoded>128*1024:raise ValueError('Decode budget exceeded')
        encoded=rows(pe,code)
        vt=int([row['rip_target'] for row in encoded if row['instruction'].startswith('lea ') and 'rip_target' in row][-1],16)
        field_case=next(case for case in fields['peace_components'] if case['factory_case_index']==index)
        if field_case['vtable_rva']!=hex(vt):raise ValueError('Clone/factory vtable mismatch')
        destructor=pe.u64(pe.to_offset(vt))-pe.base;getter=pe.u64(pe.to_offset(vt+0x78))-pe.base
        getter_code,_=bounded_cfg(pe,md,getter,window=0x40,max_instructions=12)
        decoded+=sum(i.size for i in getter_code)
        if destructor not in ENTRIES:raise ValueError('Unreviewed component destructor')
        expected_getter=(['xor eax, eax','mov dword ptr [rdx], eax','mov qword ptr [rdx + 8], rax','mov rax, rdx','ret'] if index==0 else
                         [f'mov dword ptr [rdx], {hex(index) if index>=10 else index}','mov rax, rdx','mov qword ptr [rdx + 8], 0','ret'])
        if index==39:expected_getter=['mov rax, qword ptr [rcx + 0x30]','mov qword ptr [rdx + 8], rax','mov rax, rdx','mov dword ptr [rdx], 0x27','ret']
        actual_getter=[(i.mnemonic+' '+i.op_str).rstrip() for i in getter_code]
        if actual_getter!=expected_getter:raise ValueError('Type getter does not return exact switch index')
        calls=[i for i in code if i.mnemonic=='call']
        if len(calls)!=1 or calls[0].operands[0].type!=2 or calls[0].operands[0].imm!=0x1a332d4:
            raise ValueError('Component clone has extra or indirect calls')
        first=code[0]
        if first.mnemonic!='mov' or first.op_str.split(',')[0]!='ecx' or first.operands[1].type!=2:raise ValueError('No allocation size')
        component_cases.append({'type_index':index,'table_rva':hex(table),'entry_rva':hex(entry),
                                'native_token_name':field_case['name'],'size_bytes':first.operands[1].imm,
                                'vtable_rva':hex(vt),'deleting_destructor_rva':hex(destructor),
                                'type_getter_rva':hex(getter),'type_getter_instructions':rows(pe,getter_code),
                                'serialized_fields':field_case['fields'],
                                'instructions':encoded,'edges':edges,'runtime_verified':False})
        check_memory_budget()
    vtables={}
    for vt,bound in ((0x1c7b840,0x130),(0x1c578b8,0x40)):
        slots={}
        for slot in range(0,bound,8):
            method=pe.u64(pe.to_offset(vt+slot))-pe.base
            if not pe.executable(method):raise ValueError('Invalid method table')
            slots[hex(slot)]=hex(method)
        vtables[hex(vt)]=slots
    lookup={row['rva']:row for fn in list(functions.values())+component_cases for row in fn['instructions']}
    facts=json.loads(json.dumps(FACTS))
    for item in facts.values():
        item['instructions']=[]
        for key in item['evidence_rvas']:
            row=lookup[key];data=bytes.fromhex(row['bytes'])
            if pe.bytes_at(int(key,16),len(data))!=data:raise ValueError('Anchor mismatch')
            item['instructions'].append(row)
    all_tokens=token_descriptors(pe)
    tokens={hex(key):all_tokens[key] for key in (0x293c,0x19e,0x2746,0x29de,0x29df,0x314c,0x314d,0x314f,0x3238,0x3239,0x323a,0x323b,0x3ca6)}
    if any(len(records)!=1 for records in tokens.values()):raise ValueError('Ambiguous token name')
    return {'schema':'native_owned_peace_1375_v1','game_sha256':SHA,'runtime_verified':False,'execution_verified':False,
        'inputs':[{'path':NATIVE.relative_to(ROOT).as_posix(),'sha256':NATIVE_SHA},{'path':FIELDS.relative_to(ROOT).as_posix(),'sha256':FIELDS_SHA}],
        'action':{key:action[key] for key in ('name','token_id','vtable_rva','accessor_rva')},
        'vtables':vtables,'token_descriptors':tokens,'facts':facts,'functions':functions,'component_clone_switch_cases':component_cases,
        'request_layout':{'size_bytes':0x210,'embedded_offer_offset':'0x48','embedded_offer_size_bytes':0x1c0,
            'bool_fields':{'0x40':'diplomats','0x41':'demand','0x208':'force'},
            'constructor_rva':'0x598af0','clone_rva':'0x59ba40','deleting_destructor_rva':'0x598b60'},
        'offer_layout':[
            {'offset':'0x10','name':'giver','type':'country_handle_u64','owned':False},
            {'offset':'0x18','name':'taker','type':'country_handle_u64','owned':False},
            {'offset':'0x20','name':'is_demand','type':'bool_byte','owned':False},
            *[{'offset':hex(offset),'name':name,'type':'vector3_8byte_country_handles','storage_owned':True,'elements_owned':False}
                for offset,name in ((0x28,'war_givers'),(0x40,'war_takers'),(0x58,'givers'),(0x70,'takers'))],
            {'offset':'0x88','name':'all_components','type':'vector3_component_pointers','storage_owned':True,'elements_owned':True},
            {'offset':'0xa0','name':'unnamed_auxiliary_vector_a','type':'vector3_8byte_elements','storage_owned':True,'elements_owned':False,'element_semantics_verified':False},
            {'offset':'0xb8','name':'unnamed_auxiliary_vector_b','type':'vector3_8byte_elements','storage_owned':True,'elements_owned':False,'element_semantics_verified':False},
            {'offset':'0xd0','name':'selected_components_by_type','type':'vector3_of_40_vector3_component_aliases','storage_owned':True,'elements_owned':False},
            {'offset':'0xe8','name':'state_owner','type':'self_pointer','owned':False,'must_rebind_after_copy':True},
            {'offset':'0xf0','name':'unnamed_state_pair','type':'two_dword_values','semantics_verified':False},
            {'offset':'0xf8','name':'state_hash','type':'hash_nodes_0x30_with_key_u32_and_owned_vector_0x68_records','storage_owned':True},
            {'offset':'0x138','name':'state_composite_hash_a','type':'hash_nodes_0x40','storage_owned':True,'payload_semantics_verified':False},
            {'offset':'0x178','name':'state_composite_hash_b','type':'hash_nodes_0x40','storage_owned':True,'payload_semantics_verified':False},
            {'offset':'0x1b8','name':'auxiliary_state_initialized_candidate','type':'byte','semantic_name_verified':False},
            {'offset':'0x1b9','name':'apply_penalties','type':'bool_byte'}],
        'unresolved_boundaries':[
            'No native constructor/clone/destructor/GUI function has been called or runtime-verified by this report.',
            'Final GUI click-to-command/submit ownership transfer and exception unwinding after partially completed allocations are not closed.',
            'The parameter constructor reads live world and populates many native candidate terms; it is not a bounded empty-terms ABI.',
            'Borrowed current war identity must be independently pinned/rechecked; two TAGs are not a public arbitrary war selector or world-epoch proof.',
            'The auxiliary hash0x68-record payload semantics and+a0/+b8 cache element meanings remain unnamed.',
            'Per-term legality, warscore, AI acceptance, force/apply_penalties policy and final war effects are outside lifecycle proof.',
            'Aliasing a source offer into a request, hand-zeroing containers, deleting index aliases, or deleting the embedded offer allocation separately is unsupported.'],
        'limits':{'max_functions':52,'functions':len(functions),'max_window_bytes':0x6000,'max_instructions_per_function':5000,
                  'component_switch_cases':40,'max_instructions_per_case':700,'max_case_window_bytes':0x1800,
                  'decoded_bytes':decoded,'max_decoded_bytes':128*1024,'memory_guard_mib':768,'process_access':False}}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    report=generate();raw=(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode()
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_bytes()!=raw:raise ValueError('Report differs')
    else:OUTPUT.write_bytes(raw)
    print(json.dumps({'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'functions':len(report['functions']),
                      'decoded_bytes':report['limits']['decoded_bytes'],'check':args.check}))

if __name__=='__main__':main()
