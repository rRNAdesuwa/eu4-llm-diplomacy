"""Incremental exact-build world/SP invalidation evidence, bounded and disk-only.

This script neither opens a process nor installs a hook. Pattern inventories are
explicitly finite; they are not a whole-program alias or indirect-call proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg

ROOT = Path(__file__).resolve().parents[1]
PRIORS = {
    "native-world-epoch-1375.json": "d4ee6ad5c8a3577dff2209ec5884978862552c700338e07ef669bd866a30de05",
    "native-single-player-origin-1375.json": "0622c8a67f085984db81aa3c5d2e15675ded40f8466bc7b41643b10ca10a7788",
    "native-single-player-context-1375.json": "0943d8f4b142daf260cbc4ea407fe4b05d6ad9898aa6c40ba44dc25788162bbf",
}
TARGETS = (0x74dd50, 0x286250, 0x2830a0, 0x80b4c0, 0xad6a70,
           0x803270, 0x811ab0, 0x14c9930, 0x14c97e0, 0x14cd8b0,
           0x14c99c0, 0x83a4f0)
NEW_ENTRIES = (0x2812a0, 0x8f4c0, 0x8f4f0, 0x80fee0, 0x80fc90,
               0x838dc0, 0x10f4330, 0x83a4f0, 0x83dae0, 0x83ef40,
               0x841be0, 0x80b570, 0x1574fb0, 0x1577280, 0x157c620,
               0x14c88f0, 0x14c99c0)
MAX_DECODE = 192 * 1024


def fact(summary, *rvas, **extra):
    return {"summary": summary, "evidence_rvas": [hex(r) for r in rvas],
            "runtime_verified": False, **extra}


FACTS = {
    "database_destruction_has_two_direct_callers": fact(
        "Validated direct E8/E9 references to286250 are1ff572 in application cleanup1fefa0 "
        "and74ddc3 in base-game cleanup74dd50. Application cleanup tests the database separately, "
        "destroys/frees it and clears global233d8d0. Its earlier game destruction is conditional. "
        "Thus a hook only at74dd50 is not a complete database-destruction cut even for these two paths. "
        "Use application-cleanup entry for early revocation and286250 as the bound-database backstop.",
        0x1ff05f, 0x1ff06b, 0x1ff072, 0x1ff07c, 0x1ff563, 0x1ff56a,
        0x1ff56d, 0x1ff572, 0x1ff57f, 0x1ff584, 0x74ddc3),
    "database_reconstruction_is_a_separate_boundary": fact(
        "2812a0 initializes database+108/+118 to null.2830a0 allocates the0x9b78-stride "
        "country block and writes+108, then may replace the pointer-index allocation through "
        "8f4f0 with RCX=database+110. Revoke before2830a0 on a bound database, not after a "
        "new array pointer appears. Any2812a0 during an armed session can conservatively revoke "
        "even before a later lazy publication, without claiming every construction is a world load.",
        0x2812da, 0x2812e0, 0x2812ee, 0x2812f5, 0x2812fc,
        0x283128, 0x28313e, 0x283143, 0x28314a, 0x283173, 0x283181),
    "pointer_index_reallocation_is_shared": fact(
        "8f4f0 copies count(+14) entries from old container+8 into the new allocation, "
        "calls virtual+10 on that container, and replaces+8. Database-index vtable1c38348 "
        "virtual+10 resolves8f4c0, which frees and zeros+8. These generic helpers are shared: "
        "a future observer must compare RCX to the bound database+110 (and separately bound "
        "game-country container) before invalidating; observing every generic-container call "
        "would be an unbounded false-positive policy. This is not proof of all index item writes.",
        0x8f4ff, 0x8f506, 0x8f520, 0x8f524, 0x8f531, 0x8f537,
        0x8f53a, 0x8f542, 0x8f4c9, 0x8f4d2, 0x8f4d7),
    "server_config_copies_have_finite_callers": fact(
        "The executable-byte direct-reference inventory validates one80b4c0 caller:803d27 "
        "inside runtime-server construction803270 with destination server+1708.80b4c0 copies "
        "source+2e8/+2e9 to destination+2e8/+2e9, hence server+19f0/+19f1. The only validated "
        "direct ad6a70 callers are the two already-reviewed network frontend assignments and "
        "the SP Play assignment. This narrows direct scalar-copy provenance; it does not prove "
        "absence of aliased bulk writes, computed calls, or shared configuration mutation.",
        0x803d19, 0x803d27, 0x80b51c, 0x80b523, 0x80b529, 0x80b530,
        0x10f7720, 0x10f7fa1, 0x1121004),
    "nineteen_f1_is_not_a_migration_counter": fact(
        "80fee0 tests server19f1, closes the existing transport through virtual18, then uses "
        "811ab0 twice to clear the context and install a newly constructed type2 context. "
        "It does not write19f1.80fc90 similarly closes transport before calling14ca360. "
        "Thus context/transport mutation is demonstrably independent of observing a19f1 change. "
        "The scalar flag remains a required rejection check, not an epoch or standalone strict-SP proof.",
        0x80ff0a, 0x80ff13, 0x80ff1f, 0x80ff26, 0x80ff2d, 0x80ff41,
        0x80ff62, 0x80ff6a, 0x80ff75, 0x80fce2, 0x80fd05, 0x80fd16),
    "four_context_entries_are_too_late_for_some_close_paths": fact(
        "The four prior candidates cover owning-pointer replacement811ab0, reset14c9930, "
        "initialization14c97e0 and in-place transport transition14cd8b0. However transport "
        "virtual18 can already execute before811ab0; for type2,1574fb0 directly stores0 at "
        "backlinked context+48 while preserving context, transport and server addresses. "
        "Type0's157c620 also zeros context+48; type1's1577280 calls platform/session close "
        "methods. A bound-transport close-entry observer is an earlier backstop. These functions "
        "do not by themselves classify the human meaning of every close call.",
        0x80ff2d, 0x80ff41, 0x80fd05, 0x14c9949, 0x14c9983,
        0x1574fb0, 0x1574fb4, 0x1577284, 0x1577290, 0x15772b1,
        0x157c65f, 0x157c662, 0x157c671),
    "callbacks_can_precede_the_transition_backstop": fact(
        "14ca360 clears pending byte840 and invokes observer virtual8 notifications before "
        "calling14cd8b0 at both sites. The latter entry precedes its own transport replacement, "
        "but not those earlier notifications. Calling14ca360 is not itself proof of migration: "
        "it is a state dispatcher with ordinary branches. An entry-only conditional check cannot "
        "cover a flag changed during its later virtual38 call. Until notifications/reentrancy "
        "and worker synchronization are proven, keep dispatch/preview closed across such transitions.",
        0x14ca537, 0x14ca540, 0x14ca55b, 0x14ca56d,
        0x14ca64e, 0x14ca66d, 0x14ca676, 0x14ca69b, 0x14ca6aa),
    "context_reset_can_bypass_reinitialize": fact(
        "838dc0 obtains context from server330->370. If54 or55 is set it calls14cd4d0 "
        "directly and clears841, bypassing14c9930; otherwise it may reinitialize.14cd4d0 "
        "destroys an owned list at158 and zeros158/160/168, while retaining the context object. "
        "Include this bound-context reset as a conservative origin invalidator if that owned "
        "list participates in the session witness; its exact list semantic type is not asserted here.",
        0x8395a8, 0x8395ac, 0x8395b3, 0x8395be, 0x8395c4,
        0x8395d6, 0x8395e0, 0x8395e5, 0x14cd500,
        0x14cd53d, 0x14cd544, 0x14cd54b),
    "config_pointer_escape_precludes_no_alias_claim": fact(
        "Leaf83a4f0 returns a pointer to server+1708 when its owner+48 is nonnull; otherwise "
        "it returns a static default. Several reviewed callers also form that pointer directly "
        "for name/session operations. Machine code does not encode C++const. The direct-copy "
        "and displacement inventories therefore cannot prove that the copied flags are immutable.",
        0x83a4f0, 0x83a4f4, 0x83a4f7, 0x83a4f9, 0x83a501,
        0x83de1d, 0x83f057, 0x8420d7),
    "context_destructor_is_separate_from_setter": fact(
        "Context vtable1d8c900 slot0 resolves14c88f0, which calls14c99c0 before optional "
        "0x880-byte free. A direct body-destructor call bypasses the deleting wrapper, so "
        "14c99c0 is the lower backstop.811ab0 covers its reviewed holder replacement, not all "
        "possible direct destruction of a bound context.",
        0x14c88ff, 0x14c8904, 0x14c8909, 0x14c8911),
}


def generate(exe, deps):
    check_memory_budget()
    pe = PE(exe)
    if hashlib.sha256(pe.data).hexdigest() != SHA:
        raise ValueError("Unsupported executable")
    md, cs = make_disassembler(deps)
    if md is None:
        raise ValueError("Capstone unavailable")
    prior_functions, lookup, inputs = {}, {}, []
    for name, digest in PRIORS.items():
        path = ROOT / "work/reports" / name
        if path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("Prior input too large")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Prior input hash mismatch: " + name)
        prior = json.loads(raw)
        for entry, fn in prior["functions"].items():
            prior_functions[int(entry, 16)] = fn
            for row in fn["instructions"]:
                lookup[int(row["rva"], 16)] = row
        inputs.append({"path": path.relative_to(ROOT).as_posix(), "sha256": digest})
    functions, cache = {}, {}
    decoded = 0

    def verify_row(row):
        data = bytes.fromhex(row["bytes"])
        if pe.bytes_at(int(row["rva"], 16), len(data)) != data:
            raise ValueError("Prior instruction bytes changed")
        return row

    def decode(entry):
        nonlocal decoded
        if entry in prior_functions:
            return {int(r["rva"], 16): verify_row(r) for r in prior_functions[entry]["instructions"]}
        if entry in cache:
            return cache[entry]
        if len(cache) >= 48:
            raise ValueError("Incremental CFG function budget exceeded")
        ins, edges = bounded_cfg(pe, md, entry, window=16384, max_instructions=4000)
        decoded += sum(i.size for i in ins)
        if decoded > MAX_DECODE:
            raise ValueError("Decode budget exceeded")
        rows = [{"rva": hex(i.address), "bytes": i.bytes.hex(),
                 "instruction": f"{i.mnemonic} {i.op_str}".strip()} for i in ins]
        cache[entry] = {int(r["rva"], 16): r for r in rows}
        lookup.update(cache[entry])
        functions[hex(entry)] = {"prefix32": pe.bytes_at(entry, 32).hex(), "instructions": rows,
                                 "edges": edges, "decoded_bytes": sum(i.size for i in ins)}
        check_memory_budget()
        return cache[entry]

    for entry in NEW_ENTRIES:
        decode(entry)

    # Full executable-section BYTE PATTERN inventory, followed by CFG validation
    # only for the small target set. The 759 lazy constructor sites are not CFGs.
    refs = {hex(t): [] for t in TARGETS}
    constructor_candidates, store_candidates = [], []
    pattern = re.compile(rb"[\x48-\x4f]\x89[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]....|\x48\xc7\x05........", re.S)
    for section in pe.sections:
        if not section["flags"] & 0x20000000:
            continue
        for match in re.finditer(b"[\xe8\xe9]", pe.data[section["raw"]:section["raw"] + section["size"]]):
            off = section["raw"] + match.start()
            if off + 5 > section["raw"] + section["size"]:
                continue
            site = pe.to_rva(off)
            target = site + 5 + struct.unpack_from("<i", pe.data, off + 1)[0]
            if target == 0x2812a0:
                constructor_candidates.append(site)
            if target not in TARGETS:
                continue
            fn = pe.function(site)
            row = decode(fn[0]).get(site) if fn else lookup.get(site)
            actual = list(md.disasm(bytes.fromhex(row["bytes"]), site)) if row else []
            verified = bool(len(actual) == 1 and actual[0].mnemonic in ("call", "jmp")
                            and actual[0].operands[0].type == cs.CS_OP_IMM
                            and actual[0].operands[0].imm == target)
            refs[hex(target)].append({"site": hex(site), "function": hex(fn[0]) if fn else None,
                                      "instruction_verified": verified, "instruction": row})
        for match in pattern.finditer(pe.data, section["raw"], section["raw"] + section["size"]):
            site = pe.to_rva(match.start())
            target = site + len(match.group()) + struct.unpack_from("<i", match.group(), 3)[0]
            if target in (0x233d8d0, 0x233fe78):
                store_candidates.append({"site": hex(site), "target": hex(target), "bytes": match.group().hex()})
        check_memory_budget()
    if len(constructor_candidates) > 1024 or len(store_candidates) > 1024:
        raise ValueError("Pattern candidate budget exceeded")
    for row in store_candidates:
        site = int(row["site"], 16)
        near = [a for a in constructor_candidates if 5 <= site - a <= 24]
        row["preceding_constructor_byte_pattern"] = hex(near[0]) if len(near) == 1 else None
        row["instruction_verified"] = site in lookup
        if site in lookup:
            row["instruction"] = verify_row(lookup[site])
    if len(store_candidates) != 764 or len(constructor_candidates) != 759:
        raise ValueError("Reviewed pattern counts changed")
    unexpected = {r["site"] for r in store_candidates if not r["preceding_constructor_byte_pattern"]}
    if unexpected != {"0x1ff07c", "0x1ff584", "0x21031d", "0x74c156", "0x74ddd7"}:
        raise ValueError("Non-constructor store candidate set changed")
    expected_sites = {
        "0x74dd50": {"0x74bff2", "0x74d89f"}, "0x286250": {"0x1ff572", "0x74ddc3"},
        "0x2830a0": {"0x207752", "0x20b315"}, "0x80b4c0": {"0x803d27"},
        "0xad6a70": {"0x10f7720", "0x10f7fa1", "0x1121004"},
    }
    for target, expected in expected_sites.items():
        if {r["site"] for r in refs[target]} != expected or not all(r["instruction_verified"] for r in refs[target]):
            raise ValueError("Reviewed direct caller set mismatch: " + target)

    # Only database-neighborhood pdata and scalar +19f1 candidate functions are
    # decoded here. Unrelated +19f0 immediate matches include enormous functions;
    # they are retained as byte candidates without speculative full disassembly.
    scans = []
    for low, high, offsets in [(0x280000, 0x28a000, {0x100, 0x108, 0x110, 0x118, 0x120, 0x124})]:
        scan = {"range": [hex(low), hex(high)], "method": "pdata linear instruction inventory; object provenance not inferred from displacement",
                "function_count": 0, "decoded_bytes": 0, "writes": []}
        for start, end, _ in pe.functions:
            if not low <= start < high:
                continue
            scan["function_count"] += 1
            scan["decoded_bytes"] += end - start
            if end - start > 65536:
                raise ValueError("Regional function bound exceeded")
            for ins in md.disasm(pe.bytes_at(start, end - start), start):
                if (ins.operands and ins.operands[0].type == cs.CS_OP_MEM
                        and ins.operands[0].mem.disp in offsets and ins.operands[0].access & cs.CS_AC_WRITE):
                    scan["writes"].append({"rva": hex(ins.address), "function": hex(start),
                                           "bytes": ins.bytes.hex(), "instruction": f"{ins.mnemonic} {ins.op_str}"})
            check_memory_budget()
        decoded += scan["decoded_bytes"]
        scans.append(scan)
    displacements = {}
    for value in (0x19f0, 0x19f1, 0x1708):
        matches = []
        for section in pe.sections:
            if not section["flags"] & 0x20000000:
                continue
            for match in re.finditer(re.escape(struct.pack("<I", value)), pe.data[section["raw"]:section["raw"] + section["size"]]):
                site = pe.to_rva(section["raw"] + match.start())
                fn = pe.function(site)
                row = None
                # Runtime-server region avoids treating other classes' fields as server fields.
                if value == 0x19f1 and 0x800000 <= site < 0x840000:
                    available = decode(fn[0]) if fn else decode(0x80ff80)
                    covering = [r for a, r in available.items() if a <= site < a + len(bytes.fromhex(r["bytes"]))]
                    row = covering[0] if len(covering) == 1 else None
                matches.append({"byte_rva": hex(site), "function": hex(fn[0]) if fn else None,
                                "instruction": row, "object_provenance_verified": False})
        displacements[hex(value)] = {"method": "literal little-endian disp/immediate bytes, not complete alias coverage", "candidates": matches}
    if decoded > MAX_DECODE:
        raise ValueError("Aggregate incremental decode budget exceeded")

    pointers = {}
    for target in TARGETS:
        hits = []
        for section in pe.sections:
            if section["flags"] & 0x20000000:
                continue
            for match in re.finditer(re.escape(struct.pack("<Q", pe.base + target)), pe.data[section["raw"]:section["raw"] + section["size"]]):
                site = pe.to_rva(section["raw"] + match.start())
                hits.append({"rva": hex(site), "qword_aligned": site % 8 == 0, "section": section["name"]})
        pointers[hex(target)] = hits
    pins = []
    for vt, slot, expected in ((0x1c38348, 0x10, 0x8f4c0), (0x1d8c900, 0, 0x14c88f0),
                              (0x1d96178, 0x18, 0x1574fb0), (0x1d96088, 0x18, 0x1577280),
                              (0x1d96268, 0x18, 0x157c620), (0x1cb8460, 0x88, 0x811ab0),
                              (0x1d5a8c8, 0x88, 0x811ab0)):
        if pe.u64(pe.to_offset(vt + slot)) - pe.base != expected:
            raise ValueError("Vtable pin mismatch")
        pins.append({"vtable": hex(vt), "slot": hex(slot), "target": hex(expected),
                     "slot_bytes": pe.bytes_at(vt + slot, 8).hex(), "prefix32": pe.bytes_at(expected, 32).hex()})
    facts = json.loads(json.dumps(FACTS))
    for name, claim in facts.items():
        missing = [r for r in claim["evidence_rvas"] if int(r, 16) not in lookup]
        if missing:
            raise ValueError(f"{name}: missing anchors {missing}")
        claim["instructions"] = [verify_row(lookup[int(r, 16)]) for r in claim["evidence_rvas"]]

    return {
        "schema_version": 1, "analysis_kind": "bounded_incremental_static_epoch_and_single_player_closure",
        "binary_sha256": SHA, "inputs": inputs, "runtime_verified": False, "production_ready": False,
        "facts": facts, "functions": functions, "direct_references": refs,
        "global_store_pattern_inventory": {"method": "selected REX.W MOV RIP-relative encodings only; constructor proximity is not CFG/alias proof",
                                            "constructor_candidate_count": len(constructor_candidates), "stores": store_candidates},
        "bounded_regional_writes": scans, "displacement_byte_inventory": displacements,
        "nonexecutable_absolute_pointer_inventory": pointers, "vtable_pins": pins,
        "finite_coverage": {
            "database_destruction_direct_callers": ["0x1fefa0", "0x74dd50"],
            "base_game_cleanup_direct_callers": ["0x74bf70", "0x74d890"],
            "country_block_creation_direct_callers": ["0x207310", "0x208620"],
            "server_configuration_copy_direct_callers": ["0x803270"],
            "world_universal_cut_proven": False, "strict_single_player_snapshot_proven": False,
            "four_context_entries_cover_preceding_transport_close": False,
        },
        "guard_design": {
            "status": "unimplemented_static_design_only",
            "initial_state": "REVOKED; a late-injected adapter cannot synthesize witnessed SP origin from current fields",
            "early_world_entries": ["0x1fefa0", "0x210000", "0x74b8a0", "0x5cf740", "0x749020", "0x74bf70", "0x74dd50"],
            "identity_backstops": ["0x74a260", "0x74c080", "0x2812a0", "0x2830a0", "0x286250"],
            "country_incarnation": "0x2e1a30: revoke bound country incarnation, or conservatively entire session; ordinary dynamic-country creation also reaches this",
            "array_backstops": [{"entry": "0x8f4f0", "match": "RCX == bound database + 0x110"},
                                {"entry": "0x8f4c0", "match": "RCX == bound database + 0x110"}],
            "network_entries": ["0x811ab0", "0x14c9930", "0x14c97e0", "0x14cd8b0", "0x14c99c0", "0x14cd4d0"],
            "transport_close_entries": ["0x1574fb0", "0x1577280", "0x157c620"],
            "scoping": "context/transport callbacks compare RCX to already-bound identities without traversing freed pointers; any expected-origin construction is a new witness, never rearm-on-return",
            "action_on_entry": "atomically revoke readiness and queued authority before native mutation; monotonically advance generation; leave attempt claims consumed; never restore previous generation on failure/return",
            "snapshot_checks": ["exact module and native-thread evidence", "bound game/database/block/index/server/holder/context/transport/full country handles",
                                "server config19f0/19f1=(1,0)", "frontend selection0 plus independently witnessed SP construction",
                                "canonical context type/flags/transport and backlink", "no pending session transition840; reject unknown state enums",
                                "generation read before/after snapshot and immediately before ownership transfer"],
            "synchronization_requirement": "Atomic epoch double-read alone does not protect native calls from concurrent destruction; main-thread serialization or a proven engine lock/worker exclusion is still required",
        },
        "remaining_gaps": [
            "Computed/virtual call targets and unreviewed bulk/aliased stores are not excluded by these inventories.",
            "No proof that every logical world replacement enters the listed cut before every child invalidation; in-place country Clear and dynamic-country paths need policy.",
            "Direct reference closure is limited to E8/E9 patterns validated against bounded CFGs; absolute-pointer absence is not absence of indirect calls.",
            "Server config address escapes; no whole-program proof of19f1 immutability, migration updates, or a standalone strict-SP boolean.",
            "14ca360 invokes callbacks before the14cd8b0 backstop and can observe transition flags after virtual calls; reentrancy/notification ordering is unresolved.",
            "Hook patch safety, exception coverage, thread affinity, synchronization, and replay-resistant origin witness remain unimplemented and untested.",
        ],
        "limits": {"maximum_incremental_cfg_functions": 48, "incremental_cfg_functions": len(functions),
                   "maximum_decoded_bytes": MAX_DECODE, "incremental_decoded_bytes": decoded,
                   "memory_guard_mib": 768, "hard_stop_mib": 1024, "process_access": False,
                   "prior_cfgs_reused_with_sha_and_byte_validation": True},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=ROOT.parent / "eu4.exe")
    parser.add_argument("--deps-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "work/reports/native-epoch-sp-closure-1375.json")
    args = parser.parse_args()
    result = generate(args.exe, args.deps_dir)
    raw = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    args.output.write_bytes(raw)
    print(json.dumps({"path": str(args.output), "sha256": hashlib.sha256(raw).hexdigest(),
                      "bytes": len(raw), "facts": len(result["facts"]), "limits": result["limits"]}))


if __name__ == "__main__":
    main()
