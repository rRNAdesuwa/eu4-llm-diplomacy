"""Bounded disk-only construction/parameter review of seven next diplomacy families."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import sys
import struct

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(Path(tempfile.gettempdir())/"eu4-native-analysis-deps"))
from discover_diplomacy import PE,check_memory_budget,make_disassembler
from map_diplomacy_fields import SHA,bounded_cfg
from trace_change_subject_type import rows

NAMES=("allianceaction","milaccess","offermilaccess","fleet_access","offer_fleet_access","embargoaction","warsubsidy")
PUBLIC={
    "allianceaction":("offer_alliance","dissolve_alliance","ally proposer","other ally"),
    "milaccess":("ask_military_access","cancel_military_access","access requester/holder","access grantor"),
    "offermilaccess":("offer_military_access","revoke_military_access","access grantor","access recipient"),
    "fleet_access":("ask_fleet_basing_rights","cancel_fleet_basing_rights","basing requester/holder","port grantor"),
    "offer_fleet_access":("offer_fleet_basing_rights","revoke_fleet_basing_rights","port grantor","basing recipient"),
    "embargoaction":("embargo","revoke_embargo","embargo imposer","embargo target"),
    "warsubsidy":("give_subsidies","cancel_subsidies","subsidy payer","subsidy payee"),
}
SLOTS=(0,0x40,0x48,0x70,0x80,0x88,0x90,0x98,0xa0,0xa8,0xb0,0xc8,0xd0,0xe0,0x100,0x108)
EXTRA=(0x4e7470,0x4e8630,0x4e9d00,0x360453,0x5493d0,0x549480,0x1499540,
       0x1499cc0,0x1499d80,0x149a6d0,0x149a950,0x289670,
       0xa62dd0,0xa62f80,0xa697a0,0xa698f0,0xa68fb0,0xa694c0,0xa69660,0xa6fe20)
INPUTS={
    "native":("work/reports/native-diplomacy-1.37.5.json","c64df6e043c9e7a498a25082e0e768902764e4a271ab3579f0eaddb2f1391633"),
    "fields":("work/reports/native-action-fields-1375.json","cfabb4622b7c82f9e2476a82352f91fa5d0f8ba0f8150e75aac47fb4aeaddc96"),
    "modes":("work/reports/native-diplomacy-modes-1375.json","1c0fa12b630a134036c32caf826750ce82608c44fab80108e6cfd2b738d06676"),
}
def fact(text,*rvas,**extra):
    return {"summary":text,"evidence_rvas":[hex(x) for x in rvas],"runtime_verified":False,**extra}

FACTS={
    "seven_families_fourteen_ids":fact(
        "Alliance/embargo/subsidies each have true/false modes. Military and fleet access each have separate ask and offer families, each with true/false. This is seven families and fourteen public IDs, not five interchangeable factories.",
        0x512e40,0x512eba,0x525cf8,0x525d51,0x536bee,0x536c1b,0x5303eb,0x530476,0x5347eb,0x5348b3,0x51836e,0x51839b,0x549286),
    "factory_and_initialization":fact(
        "Six families allocate0x40; warsubsidy allocates0x48. Use token factory35d210, never stack-fabricate an object. Defaults include marker+8=0x165, invalid country handles, envoy+30=-1, state+34=0, value+38=1, byte39=0 and id+3c=0. Factory tail initializes dates. Independent current actor/original/target/date initialization still precedes preview/wrapping.",
        0x35d448,0x35d4c7,0x35d742,0x35d7c1,0x35e40c,0x35e48b,0x35dc73,0x35dce3,0x35dce6,0x35dcf4,0x360453,0x360459,0x36045c,0x360463),
    "plain_mode_setter":fact(
        "All seven virtual+e0 slots use4e99d0, a byte store into+38. None uses the spy-network mission-binding setter. Cancellation does not acquire a mission envoy ID through this setter; exact current relation and authority remain separate guards.",0x4e99d0),
    "clone_scalar_extension":fact(
        "Each clone allocates its class size, copies the common pair scalars, resets byte39, and initializes clone+2c from source+28. Warsubsidy additionally copies DWORD+40 andDWORD+44. There is no derived owning pointer/string in these seven clones.",
        0x51306e,0x5183ce,0x525d7e,0x536c4e,0x5304be,0x53490e,0x5492ee,0x549324,0x54932e,0x54935e,0x549361,0x549365,0x549368),
    "action_destruction":fact(
        "The six0x40 families use deleting destructor129450; warsubsidy uses129500, which resets the base vtable and conditionally frees0x48 with17394f0. All seven virtual+a8 slots are8f450(false), so they are ordinary uniquely owned action clones under the command destructor's tested static branch. Runtime lifetime has not been verified for these seven families.",
        0x129450,0x129500,0x129513,0x129518,0x12951d,0x8f450),
    "shared_command_ownership":fact(
        "All seven virtual+40 slots are the common4e9930 wrapper. Command owns a distinct cloned action at+50; original action remains independently owned. Command destructor4e7470 consults action+a8 then destroys its clone. V10 must preserve the existing pre-transfer cleanup and no-destruction/no-retry boundary after entering context_submit; the new families are not runtime-certified by old five-family evidence.",
        0x4e9930,0x4e7470),
    "reply_requirements":fact(
        "Alliance virtual+d0 returns value; four access families use51fa90(state==0 && value). Their positive proposals therefore use normal AI reply flow. Embargo and subsidies use8f450(false), so no approval reply is requested through this predicate. All cancellation modes return false. Do not force state1/2; accepted/declined reply and final effect require independent observation.",
        0x50f120,0x51fa90,0x51fa94,0x51fa96,0x51fa9c,0x51fa9f,0x8f450),
    "subsidy_amount":fact(
        "Action DWORD+40 is signed fixed-point thousandths of a ducat. The GUI money slider is a percentage control, not raw ducats: country+bb0 is divided by1000, slider value by100, multiplied, then converted back with*1000 and0.5 rounding. Submit1499cc0 copies dialog+2b0 into action+40. Use exact checked decimal-to-milli conversion in a future adapter, not a direct slider percentage.",
        0x1499823,0x149982e,0x149983c,0x1499844,0x149984b,0x1499853,0x1499872,0x1499ce5,0x1499cf2,0x5494cb,
        object_offset="0x40",width_bytes=4,native_scale=1000,public_parameter="monthly_amount"),
    "subsidy_duration_years":fact(
        "The GUI defaults dialog+2b4 to10, labels it YEARS, increments/decrements by10 and clamps to10..400. Submit copies it unchanged to action+44. Persistent subsidy expiry tests start_date+duration*0x2238 against current raw date. Thus the native scalar is years, not months. Existing public duration_months must not be copied directly; this design proposes duration_years with the reviewed UI domain. UI bounds are not claimed universal engine validation.",
        0x14999ca,0x14999f1,0x149a6ea,0x149a6f1,0x149a715,0x149a96a,0x149a971,0x149a992,
        0x1499cf5,0x1499d02,0xa62e14,0xa62e23,0xa62e27,
        object_offset="0x44",width_bytes=4,native_unit="years",ui_default=10,ui_minimum=10,ui_maximum=400,ui_step=10,
        public_parameter_mismatch="Current give_subsidies schema uses duration_months; explicit schema migration or checked conversion is required"),
    "subsidy_native_validity":fact(
        "Positive validity conditionally rejects amount<100 internal units after actor predicate289670, rejects an existing pair subsidy index, and invokes common legality4ebdb0. False mode requires a pair subsidy index. This function does not validate duration+44, so an API must not rely on preview to bound it. The actor predicate consults game+1d48..1d50; this report does not reinterpret it as strict player authority.",
        0x548cbb,0x548cbf,0x548cc8,0x548ccc,0x548cde,0x548ce5,0x548ee8,0x548efa,0x548f06,0x548f0d,0x548f22),
    "subsidy_selected_effect":fact(
        "Positive effect547880 allocates a persistent0x48 relation with vtable1c815d8, writes payer+10, payee+18, start+20, amount+40 and duration+44, and registers the same object in both pair directions througha697a0. Pair lookupa698f0 uses root+110/count+11c. Cancellation finds the relation via recipient's pair record, calls a62f80, clears both index links and marks relation+28=1. A future cancellation guard must match full payer/payee handles, not merely an undirected pair entry.",
        0x5478ae,0x54790c,0x54792c,0x547930,0x547934,0x54793b,0x547942,0x547979,0x5479ba,
        0x54875a,0x54876e,0xa698fc,0xa69903,0xa63067,0xa630a4,0xa630a9,
        relation_vtable_rva="0x1c815d8",relation_size=72,index_pointer_offset="0x110",index_count_offset="0x11c"),
    "embargo_selected_effect":fact(
        "Positive/negative effect routes calla6fe20 on actor's target relation with DL=1/0. The helper doubles that bool, clears mask0x02 at record+46 then ORs the new bit. Selected outgoing embargo state is record+46 &0x02, not the truce mask and not a cloned relation object. Dirty/cache marks are also written and must not be mistaken for embargo truth.",
        0x516f37,0x516f80,0x516f82,0x51752f,0xa6fe27,0xa6fe40,0xa6fe82,0xa6fe86,
        relation_record_offset="0x46",mask=2),
    "access_index_candidates":fact(
        "Military getter a68fb0 returns root+b0/count+bc indexed object. Fleet getters a694c0 and a69660 use root+e0/count+ec and root+f8/count+104 respectively. All are 16-byte slot/object indices. These are useful bounded observer starting points; full relation vtable/layout, direction and accepted-state binding must be independently closed before asserting an access effect.",
        0xa68fbc,0xa68fc3,0xa694cc,0xa694d3,0xa6966c,0xa69673),
}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("--check",action="store_true");args=ap.parse_args()
    source={}
    for key,(path,sha) in INPUTS.items():
        raw=(ROOT/path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError("Pinned source changed: "+path)
        source[key]=json.loads(raw)
    pe=PE(ROOT.parent/"eu4.exe");check_memory_budget()
    if hashlib.sha256(pe.data).hexdigest()!=SHA:raise ValueError("Wrong executable")
    md,_=make_disassembler(Path(tempfile.gettempdir())/"eu4-native-analysis-deps")
    functions={}
    def include(entry,window=0x4000):
        key=hex(entry)
        if key not in functions:
            ins,edges=bounded_cfg(pe,md,entry,window=window,max_instructions=6000)
            functions[key]={"prefix32":pe.bytes_at(entry,32).hex(),"instructions":rows(pe,ins),
                            "edges":edges,"window_bytes":window,"decoded_bytes":sum(i.size for i in ins)}
        return key
    inventory=source['native']['native_actions'];fieldmap={a['name']:a for a in source['fields']['actions']}
    actions=[]
    for name in NAMES:
        a=next(x for x in inventory['actions'] if x['name']==name)
        vt=int(a['vtable_rva'],16)
        for slot in SLOTS:
            method=int(a['slots'][hex(slot)],16)
            if pe.u64(pe.to_offset(vt+slot))-pe.base!=method:raise ValueError("Vtable slot changed")
            include(method)
        ref=int(a['factory_branch']['reference_rva'],16)
        alloc=max((x for x in inventory['factory_direct_calls'] if ref-0xa0<int(x['call_rva'],16)<ref),
                  key=lambda x:int(x['call_rva'],16))
        factory_start=int(alloc['call_rva'],16)-5
        if pe.bytes_at(factory_start,1)!=b'\xb9':raise ValueError("Factory allocation instruction changed")
        include(factory_start,0x90)
        actions.append({"name":name,"token_id":a['token_id'],"vtable_rva":a['vtable_rva'],
                        "proposed_public_modes":[{"action_id":PUBLIC[name][0],"value":True},{"action_id":PUBLIC[name][1],"value":False}],
                        "actor_role":PUBLIC[name][2],"target_role":PUBLIC[name][3],
                        "size":a['clone']['allocation']['size_bytes'],"slots":a['slots'],
                        "factory_block_rva":hex(factory_start),"factory_vtable_write_reference":hex(ref),
                        "clone_fields":a['clone']['source_field_reads'],"derived_fields":fieldmap[name]['derived_fields'],
                        "known_cancellation_modes":[x for x in source['modes']['actions'] if x.get('native_family')==name],
                        "runtime_verified":False,"execution_verified":False})
    for entry in EXTRA:include(entry)
    known={i['rva'] for f in functions.values() for i in f['instructions']}
    for key,f in FACTS.items():
        for rva in f['evidence_rvas']:
            if rva not in known:raise ValueError("Missing instruction for fact "+key+": "+rva)
    decoded=sum(f['decoded_bytes'] for f in functions.values())
    if decoded>192*1024:raise ValueError("Total decode exceeds192KiB")
    report={"schema":"native_pair_extension_v10_1375_v1","game_sha256":SHA,"runtime_verified":False,
        "public_backend_registered":False,"input_hashes":{k:{"path":v[0],"sha256":v[1]} for k,v in INPUTS.items()},
        "actions":actions,"base_fields":source['fields']['base_fields'],"facts":FACTS,"functions":functions,
        "ui_float_constants":[{"rva":hex(rva),"float32":struct.unpack('<f',pe.bytes_at(rva,4))[0],"bytes":pe.bytes_at(rva,4).hex()}
                              for rva in (0x1dc1938,0x1dc18c8,0x1d99d94)],
        "limits":{"function_window_max":0x4000,"instruction_count_per_window_max":6000,"decoded_bytes":decoded,
                  "memory_guard_bytes":768*1024*1024},
        "boundaries":["Disk-only static evidence; no game process access or native calls.",
                      "Bounded CFG does not enumerate indirect switch targets or prove completeness of all effects.",
                      "No live loader, native host or frozen v9 files are changed by this tool."]}
    payload=(json.dumps(report,indent=2)+"\n").encode();out=ROOT/'work/reports/native-pair-extension-v10-1375.json'
    if args.check:
        if out.read_bytes()!=payload:raise ValueError("Report differs")
    else:out.write_bytes(payload)
    check_memory_budget();print(json.dumps({"functions":len(functions),"decoded_bytes":decoded,"sha256":hashlib.sha256(payload).hexdigest(),"check":args.check}))

if __name__=="__main__":main()
