"""Reproduce bounded disk-only script vassalize/create_vassal and truce evidence."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg
from trace_change_subject_type import rows, fact

FUNCTIONS = [0x5de510, 0xddbb90, 0xdd4e60, 0x60ad60, 0xdd50b0,
             0xdd9060, 0xdd9370, 0xdd9bd0, 0xdd9eb0, 0xb22380,
             0xddbbe0, 0xddcfd0, 0x4e5630, 0xa68d90,
             0x2f1620, 0xa5d790, 0x3eb120]
BLOCKS = [(0x5dec50, 0x5dec96), (0x5dec96, 0x5deca1),
          (0x5ded0d, 0x5ded4f), (0x5dfbdb, 0x5dfbf8),
          (0x5e05a1, 0x5e05be), (0x5e0f3e, 0x5e0f68),
          (0xa675b0, 0xa676d0), (0xa68554, 0xa6855c)]
FACTS = {
    "vassalize_is_existing_country_route": fact(
        "Token2758 maps to factory case5dfbdb, size68/ctor5de510/vtable1c9e7a8. "
        "It defaults type String32+40 to 'vassal', and booleans+60/+61 to1. Scalar "
        "TAG parsing via slot48=dd4e60 resolves country with286120 into full handle+38. "
        "Virtual98=dd50b0 returns that handle for a literal TAG. Its existence and "
        "proper scope still require a reviewed baseline; parsing a TAG is not effect proof.",
        0x5dfbdb, 0x5dfbed, 0x5de546, 0x5de56b, 0x5de57f,
        0xdd4eca, 0xdd4ed2, 0xdd50db),
    "vassalize_actual_apply": fact(
        "Apply dd9370 checks country scope, resolves type name withdd9eb0/b23df0, "
        "and tests definition's potential-overlord predicate throughb22380. It resolves "
        "the target by virtual98 and refuses the same country slot. Atdd976c it calls "
        "4e5630 with definitionRCX, current scope overlordRDX, targetR8, current date "
        "addressR9. Additional args: null,+invalid old-overlord handle,+60,+61. This "
        "is an actual relation-creation path, unlike the change_subject_type disk stub.",
        0xdd96ad, 0xdd96cd, 0xdd96ea, 0xdd970f, 0xdd971c, 0xdd9726,
        0xdd972f, 0xdd9745, 0xdd9749, 0xdd975e, 0xdd9765, 0xdd976c,
        actor_role="overlord", target_role="subject", default_type="vassal"),
    "flags_are_not_truce_switches": fact(
        "Object+60 is parsed from keep_liberty_desire3ea4; +61 from message00dd. "
        "Both default true. They are not a documented no-truce flag. The literal "
        "vassalize=NAV form preserves defaults and does not invent an extra parameter.",
        0xdd9c1f, 0xdd9c35, 0xdd9e6c, 0x5de57f),
    "create_vassal_is_distinct": fact(
        "Token27a9 selects5e05a1, size40/ctorddbb90/vtable1d240f8; scalar target is "
        "parsed into+38 via60ad60. Applyddbbe0 resolves its target withddcfd0, has a "
        "special rebel branch, queries36d120 for release candidates, requires a matching "
        "target slot in that list, collects source-owned/controlled target-core provinces, "
        "and invokesa87a00 before constructing a vassal dependency. This release workflow "
        "is not an alias for directly making an already independent NAV a subject.",
        0x5e05a1, 0x5e05b3, 0xddbf25, 0xddbf5e, 0xddbfac, 0xddbfda,
        0xddc015, 0xddc03d, 0xddc046, 0xddc059, 0xddc121, 0xddc2ed,
        0xddc2f1, 0xddc2f5, 0xddc328),
    "dependency_creation": fact(
        "4e5630 handles existing dependencies and surrounding diplomatic state. Its "
        "new relation stores definition+40, overlord+10, subject+18 and passed date+20; "
        "it registers then applies througha5ff20. Existing dependency/war/other relations "
        "are material side effects, so this report recommends only the reviewed independent "
        "NAV baseline. It does not claim an isolated single-field mutation.",
        0x4e5c2b, 0x4e5c54, 0x4e5ce0, 0x4e5d55,
        0x4e5da2, 0x4e5da6, 0x4e5daa, 0x4e5db7, 0x4e5dc3),
    "alliance_cleanup_truce": fact(
        "The relation cleanup loop callsa68d90 to look up an existing alliance. If absent "
        "it skips the alliance-removal branch. If present and2f1620 returns true, it calls "
        "a5d790. Predicate2f1620 immediately returns true when country.overlord slot equals "
        "the other country. Alliance removala5d790 calls3eb120 in both directions. "
        "3eb120 conditionally writes relation+34=current_date and+24=derived truce length, "
        "thena675b0 recomputes relation+45 bit1 from the resulting expiry. This supplies "
        "a concrete explanation for truce after turning an existing ally into a vassal. "
        "That explanation is static correlation, not proof of a particular live request's cause.",
        0x4e6581, 0x4e6589, 0x4e659a, 0x4e65df, 0x4e65e2,
        0x2f1657, 0x2f1674, 0x2f16ae, 0xa5d8b3, 0xa5d8e0,
        0x3eb228, 0x3eb2b8, 0x3eb2e2, 0x3eb337, 0x3eb375,
        0xa6763d, 0xa6765f, 0xa67681,
        implies_no_alliance_skips_this_branch=True, proves_all_paths_truce_free=False),
    "fixture_scope": fact(
        "A fixed FRA event containing vassalize=NAV is a supported static candidate, "
        "provided a separately reviewed baseline proves NAV exists, is independent, "
        "and has neither FRA alliance nor bilateral truce. Do not first create the alliance. "
        "Do not use the positive save where NAV is already a vassal. This is test setup, "
        "not a claim that ordinary diplomatic acceptance or cancellation gates were bypassed "
        "in normal-mode coverage. After the event independently observe dependency type, "
        "full handles, start date and both truce fields before attempting native cancellation.",
        runtime_effect_verified=False, candidate_effect="vassalize = NAV"),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exe", type=Path, default=Path("../eu4.exe"))
    ap.add_argument("--game-dir", type=Path, default=Path(".."))
    ap.add_argument("--output", type=Path, default=Path("work/reports/native-vassal-effects-1375.json"))
    ap.add_argument("--deps-dir", type=Path)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    pe = PE(args.exe)
    digest = hashlib.sha256(pe.data).hexdigest()
    if digest != SHA:
        raise ValueError("Exact PE SHA256 mismatch")
    md, _ = make_disassembler(args.deps_dir)
    tokens = {}
    for name, token, descriptor in [("vassalize",0x2758,0x203dd58),
                                    ("create_vassal",0x27a9,0x20481e0),
                                    ("keep_liberty_desire",0x3ea4,0x231abc0),
                                    ("message",0xdd,0x1ff9c98)]:
        assert pe.u32(pe.to_offset(descriptor)) == token
        assert pe.bytes_at(descriptor+4,len(name)+1) == name.encode()+b"\0"
        tokens[name] = {"token":hex(token),"descriptor_rva":hex(descriptor)}
    dispatch = {}
    for name,token,expected in [("vassalize",0x2758,0x5dfbdb),("create_vassal",0x27a9,0x5e05a1)]:
        idx=token-0x2711; byte_rva=0x5e5250+idx; mapped=pe.bytes_at(byte_rva,1)[0]
        pointer_rva=0x5e4f34+mapped*4; target=pe.u32(pe.to_offset(pointer_rva))
        assert target == expected
        dispatch[name]={"byte_table_rva":hex(byte_rva),"mapped_index":mapped,
                        "target_table_rva":hex(pointer_rva),"case_rva":hex(target)}
    vtables={hex(vt):{hex(slot):hex(pe.u64(pe.to_offset(vt+slot))-pe.base)
                     for slot in range(0,end,8)}
             for vt,end in [(0x1c9e7a8,0xa0),(0x1d240f8,0x98)]}
    assert vtables["0x1c9e7a8"]["0x98"] == "0xdd50b0"
    funcs={}
    for entry in FUNCTIONS:
        ins,edges=bounded_cfg(pe,md,entry,window=0x3000,max_instructions=3500)
        funcs[hex(entry)]={"prefix32":pe.bytes_at(entry,32).hex(),"instructions":rows(pe,ins),
                           "edges":edges,"decoded_bytes":sum(i.size for i in ins)}
    blocks={}
    for start,end in BLOCKS:
        ins=list(md.disasm(pe.bytes_at(start,end-start),start))
        assert sum(i.size for i in ins)==end-start
        blocks[hex(start)]={"end_rva_exclusive":hex(end),"instructions":rows(pe,ins),"decoded_bytes":end-start}
    stock=[]
    for relative,lo,hi,required in [("missions/Brunei_Missions.txt",133,142,"vassalize = SUL"),
                                    ("common/rebel_types/nationalist.txt",268,280,"create_vassal = REB")]:
        raw=(args.game_dir/relative).read_bytes()
        excerpt="\n".join(raw.decode("utf-8-sig").splitlines()[lo-1:hi])
        assert required in excerpt
        stock.append({"path":relative,"sha256":hashlib.sha256(raw).hexdigest(),
                      "first_line":lo,"last_line":hi,"excerpt":excerpt})
    report={"binary_sha256":digest,"scope":"bounded_offline_vassalize_and_create_vassal",
            "runtime_verified":False,"tokens":tokens,"factory_dispatch":dispatch,
            "vtables":vtables,"facts":FACTS,"stock_evidence":stock,
            "functions":funcs,"blocks":blocks,
            "total_decoded_bytes":sum(v["decoded_bytes"] for v in (*funcs.values(),*blocks.values())),
            "limits":{"process_access":False,"native_calls":False,"game_or_mod_writes":False,
                      "whole_factory_disassembly":False,"window_bytes":0x3000,
                      "max_instructions_per_entry":3500,"max_committed_memory_bytes":768*1024*1024}}
    payload=(json.dumps(report,indent=2,ensure_ascii=False)+"\n").encode()
    check_memory_budget()
    if args.check:
        if args.output.read_bytes()!=payload:raise ValueError("Reproduced report differs")
    else:args.output.write_bytes(payload)
    print(json.dumps({"sha256":hashlib.sha256(payload).hexdigest(),"decoded_bytes":report["total_decoded_bytes"],
                      "functions":len(funcs),"blocks":len(blocks),"check":args.check,"runtime_verified":False}))


if __name__=="__main__":main()
