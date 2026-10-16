"""Bounded disk-only closure of seven-family persistent relationship effects."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg, token_descriptors
from trace_change_subject_type import rows

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "work/reports/native-pair-extension-v10-1375.json"
INPUT_SHA = "0c1731b0b29b296da73dc406fb31544ada59c17c275d17d623677b16998698bd"
ENTRIES = (0xa5d1b0, 0xa5d2a0, 0xa5d790, 0xa68c20, 0xa68d90,
           0xa70100, 0xa70270, 0xa70310, 0xa68ee0, 0xa68fb0, 0xa69060, 0xa69160,
           0xa70670, 0xa70760, 0xa70840, 0xa693f0, 0xa694c0, 0xa695a0, 0xa69660,
           0xa703c0, 0xa70410, 0xa69030, 0x28b220)


def fact(summary, *anchors):
    return {"summary": summary, "evidence_rvas": list(map(hex, anchors)), "runtime_verified": False}


FACTS = {
    "alliance": fact("Accepted positive alliance (state2/value true) allocates0x48 and installs relation vtable1c7a740; +10/+18 are its two full country handles. a5d1b0 registers the same relation in both root80/8c indexes via a68c20. a5d790 unregisters both and marks removed; symmetric presence cannot identify which proposal created it.",
        0x50f800, 0x50f80b, 0x50f81e, 0x50f850, 0x50f91c, 0x50f930, 0x50f934, 0x50f938, 0x50f93e,
        0xa5d242, 0xa5d280, 0xa68ca9, 0xa68d9c, 0xa68da3, 0xa5d849, 0xa5d886, 0xa5dd18),
    "military": fact("Military relation ctor a70100 creates vtable1cdde60 (0x48 bytes at both action allocations). Relation+10 is access holder and +18 grantor. milaccess copies action actor/recipient directly, offermilaccess reverses those relation fields. Both creation paths require state2/value true. a70270 registers holder rootb0/bc througha68ee0 and grantor rootc8/d4 througha69060. a70310 clears both indexes and writes removed+28=1.",
        0xa70148, 0xa70155, 0x523ec9, 0x52405c, 0x524393, 0x524397, 0x5243a0, 0x5243b3,
        0x5243d9, 0x5243dd, 0x5243e1, 0x534dcc, 0x534f58, 0x535284, 0x535288, 0x535291,
        0x5352a4, 0x5352ca, 0x5352ce, 0xa70276, 0xa7027d, 0xa702b5, 0xa702f6,
        0xa68eff, 0xa68fbc, 0xa68fc3, 0xa6907f, 0xa6916c, 0xa69173, 0xa7036a, 0xa703aa, 0xa703af),
    "fleet": fact("Fleet relation ctor a70670 creates vtable1cddee0 (0x48 bytes). Relation+10 is basing holder, +18 port grantor. fleet_access copies actor/recipient; offer_fleet_access reverses them. Both require state2/value true. a70760 registers holder roote0/ec througha693f0 and grantor rootf8/104 througha695a0. a70840 clears both and marks removed+28=1.",
        0xa706b8, 0xa706c5, 0x52d97c, 0x52db0f, 0x52db12, 0x52db1b, 0x52db2d, 0x52db51, 0x52db58, 0x52db5c,
        0x531bdd, 0x531f1d, 0x531f20, 0x531f29, 0x531f3b, 0x531f5b, 0x531f66, 0x531f6a,
        0xa707a5, 0xa707e6, 0xa6940f, 0xa694cc, 0xa694d3, 0xa695bf, 0xa6966c, 0xa69673,
        0xa7089a, 0xa708da, 0xa70925),
    "enforce_peace_flag": fact("Both access relation constructors initialize BYTE+40=0; shared serializer/parser names it enforce_peace, token2dda. It is not an automatic/conditional access flag. The selected observer reports flag1 separately and does not treat it as ordinary diplomatic proposal effect.",
        0xa70155, 0xa706c5, 0xa70425, 0xa70429, 0xa703c9, 0xa703dc),
    "conditional_access_is_separate": fact("The conditional-access UI calls a69030, which forwards to rule evaluator28b220. That evaluator can return true for same country/root50 relations before rootb0; after no b0 match it continues into overlord and further rule paths. Thus effective movement permission is not equivalent to an indexed explicit military agreement. The observer reads b0/c8 objects only; it does not evaluate movement permission or infer no conditional access when the object is absent.",
        0xa69048, 0x28b300, 0x28b317, 0x28b319, 0x28b31f, 0x28b335, 0x28b344, 0x28b34b,
        0x28b362, 0x28b36f, 0x28b39c, 0xf09101, 0xf09178),
}


def generate():
    raw = INPUT.read_bytes()
    if len(raw) > 5 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != INPUT_SHA:
        raise ValueError("Extension input SHA mismatch")
    prior = json.loads(raw)
    pe = PE(ROOT.parent / "eu4.exe")
    if hashlib.sha256(pe.data).hexdigest() != SHA:
        raise ValueError("Exact executable SHA mismatch")
    md, _ = make_disassembler(Path(os.environ.get("TEMP", ".")) / "eu4-native-analysis-deps")
    functions, lookup, decoded = {}, {}, 0
    for entry in ENTRIES:
        code, edges = bounded_cfg(pe, md, entry, window=0x4000, max_instructions=4000)
        decoded += sum(i.size for i in code)
        if decoded > 65536:
            raise ValueError("Helper decode budget exceeded")
        records = rows(pe, code)
        functions[hex(entry)] = {"instructions": records, "edges": edges}
        lookup.update({r["rva"]: r for r in records})
        check_memory_budget()
    # Parent report instructions are already tied to exact bytes, but verify
    # every selected imported anchor again against the PE.
    imported = {r["rva"]: r for f in prior["functions"].values() for r in f["instructions"]}
    # Explicit UI basic block: 0xf09101 references DIPIRO_CONDITIONAL_ACCESS,
    # 0xf09178 calls the distinct permission-rule evaluator.
    ui = list(md.disasm(pe.bytes_at(0xf09101, 0x7c), 0xf09101))
    uirows = rows(pe, ui)
    lookup.update({r["rva"]: r for r in uirows})
    functions["0xf09101"] = {"instructions": uirows, "basic_block_excerpt": True}
    token = token_descriptors(pe).get(0x2dda)
    if token != [{"name": "enforce_peace", "descriptor_rva": "0x2182740"}]:
        raise ValueError("Access relation token changed")
    facts = json.loads(json.dumps(FACTS))
    for value in facts.values():
        value["instructions"] = []
        for anchor in value["evidence_rvas"]:
            row = lookup.get(anchor) or imported.get(anchor)
            if row is None:
                raise ValueError("Missing evidence anchor " + anchor)
            b = bytes.fromhex(row["bytes"])
            if pe.bytes_at(int(anchor, 16), len(b)) != b:
                raise ValueError("Evidence bytes differ")
            value["instructions"].append(row)
    pins = []
    for vt, register, remove in ((0x1c7a740, 0xa5d2a0, 0xa5d790), (0x1cdde60, 0xa70270, 0xa70310), (0x1cddee0, 0xa70760, 0xa70840)):
        for slot, method in ((0x58, register), (0x60, remove)):
            if pe.u64(pe.to_offset(vt + slot)) - pe.base != method:
                raise ValueError("Relation lifecycle vtable mismatch")
            pins.append({"vtable": hex(vt), "slot": hex(slot), "target": hex(method)})
    return {"schema_version": 1, "game_sha256": SHA, "runtime_verified": False, "execution_verified": False,
            "input": {"path": INPUT.relative_to(ROOT).as_posix(), "sha256": INPUT_SHA},
            "facts": facts, "functions": functions, "vtable_checks": pins, "enforce_peace_token": token,
            "inherited_effects": {k: prior["facts"][k] for k in ("subsidy_selected_effect", "embargo_selected_effect", "subsidy_duration_years")},
            "observer_scope": "Explicit indexed pair relations or outgoing embargo bit; not effective movement permission, request causality, reply acceptance or global world identity.",
            "limits": {"max_functions": 24, "max_function_window": 16384, "max_instructions": 4000,
                       "maximum_helper_decoded_bytes": 65536, "actual_helper_decoded_bytes": decoded,
                       "ui_excerpt_bytes": 124, "memory_guard_mib": 768, "process_access": False}}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    data = (json.dumps(generate(), ensure_ascii=False, indent=2) + "\n").encode()
    path = ROOT / "work/reports/native-pair-extension-effects-v10-1375.json"
    changed = not path.is_file() or path.read_bytes() != data
    if not args.check:
        path.write_bytes(data)
    print(json.dumps({"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "stale": args.check and changed}))
    return int(args.check and changed)


if __name__ == "__main__":
    raise SystemExit(main())
