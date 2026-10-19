"""Exact-build bounded load/session evidence; no process access and no hook code."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg


ENTRIES = [0x74b8a0, 0x5cdc60, 0x5cf740, 0x74a260, 0x756a30,
           0x110d760, 0xd84b80, 0x5d0580, 0x74b330, 0x1adfdf0,
           0x11150a0, 0x1115350, 0x1132ca0, 0x112fd10, 0x1131470,
           0x6eaa10, 0x80ff80, 0x811aa0, 0x802540, 0x81af10, 0x74eb20]


def fact(summary, *rvas, **extra):
    return dict(summary=summary, evidence_rvas=[hex(r) for r in rvas],
                runtime_verified=False, **extra)


FACTS = {
    "load_entry": fact(
        "74b8a0 takes game in RCX and load-source object in RDX, sets game+74c8 to source, "
        "sets game+7480=1, rebinds server via756a30, obtains context through server+80 and calls "
        "5cdc60. This is an early candidate invalidation boundary for the reviewed deserialization "
        "path. Merely sampling game pointer/date after load cannot detect this path.",
        0x74b8aa, 0x74b8ad, 0x74b8c8, 0x74b8f0, 0x74b917, 0x74b926, 0x74b93d,
        0x74ba03, source_pointer_offset=0x74c8, loaded_byte_offset=0x7480,
        hook_candidate_rva="0x74b8a0", universal_coverage_proven=False),
    "deserialize_sequence": fact(
        "5cdc60 packs game/source/result pointers into a temporary context and directly calls "
        "5cf740. The latter clears game subobjects and calls74a260 before deserializing "
        "gamestate through14e4240. Its failure result and success result are written to a caller "
        "result byte; there is no observed monotonic world generation in this sequence. "
        "Hooking only a success return is too late to invalidate preexisting pointers/requests.",
        0x5cdc78, 0x5cdc7c, 0x5cdc80, 0x5cdd54, 0x5cdd58,
        0x5cf76f, 0x5cf77e, 0x5cf7a1, 0x5cfe87, 0x5cfec1, 0x5d0175),
    "reset_flags": fact(
        "74a260 sets game+7485=1 while resetting the world and clears it before returning. "
        "It clears game+7480 only if game+74c8 is null. Thus7485 is a transient reset guard and "
        "7480 is not a load counter. Sampling either once per frame can miss a whole load/reset. "
        "Server virtual+140 in the pinned table is802540 and reads server+1158; its wider mode "
        "meaning is not proved. These predicates must not be renamed single_player.",
        0x74a284, 0x74a289, 0x74a843, 0x74a84d, 0x74b1e8,
        0x802540, generation_counter_identified=False),
    "known_callers": fact(
        "Four reviewed direct sites call74b8a0:5d0c78,74b671,d852b9,1adfe39. UI wrapper110d760 "
        "callsd84b80, whose full-load branch calls74b8a0. Three reviewed callers reach110d760. "
        "These direct-call observations establish concrete paths, not coverage of every load/new "
        "game/return-to-menu/network-resync/indirect or exceptional path.",
        0x5d0c78, 0x74b671, 0xd852b9, 0x1adfe39, 0x110d7d5,
        0x111520a, 0x111591c, 0x113373a,
        direct_callers_of_74b8a0=["0x5d0580", "0x74b330", "0xd84b80", "0x1adfdf0"],
        coverage_gaps=["indirect callers", "new game", "return to menu", "network resync",
                       "exceptional/unwind paths", "concurrent lifecycle callbacks"]),
    "native_multiplayer_classifier": fact(
        "6eaa10 is the native boolean used by the multiplayer/standard label and serialization "
        "token3329 multi_player. It first calls server virtual318 (pinned80ff80: server+19f1). "
        "When false it returns false. Otherwise context54/55 both zero returns true; if either "
        "is nonzero it scans game+a50 nodes, returning true if any node+18 ID differs from "
        "context+8c. Empty/all-same-ID lists return false. Its false branch therefore does not "
        "independently prove a dedicated offline-only session with no multiplayer origin.",
        0x6eaa20, 0x6eaa28, 0x6eaa36, 0x6eaa3c, 0x6eaa40, 0x6eaa49,
        0x6eaa6c, 0x6eaa72, 0x6eaa75, 0x6eaa77, 0x6eaa80, 0x6eaa92,
        0x80ff80, 0x81b50b, 0x81b514, 0x81b523, 0x74f41b, 0x74f423, 0x74f436,
        signature="bool __fastcall(void* server)", native_classifier_rva="0x6eaa10",
        strict_single_player_predicate_proven=False,
        readonly_formula={"server_gate_offset": 0x19f1, "server_gate_width": 1,
                          "context_flags": [0x54, 0x55], "context_local_id_offset": 0x8c,
                          "game_player_list_head": 0xa50, "node_id_offset": 0x18,
                          "node_next_offset": 0x60, "id_width": 4}),
    "context_is_not_session_mode": fact(
        "The pinned server+80 getter is the two-load chain server+330 -> +370. "
        "The same context is used by local submission and native multiplayer classification. "
        "Context ready bytes55/80d and transport vtable identity establish neither offline "
        "origin nor a monotonic load generation. No safe standalone SP predicate was established "
        "by this bounded analysis.",
        0x811aa0, 0x811aa7, 0x6eaa30, 0x6eaa3c),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exe", type=Path, default=Path(__file__).resolve().parents[2] / "eu4.exe")
    ap.add_argument("--deps-dir", type=Path, required=True)
    ap.add_argument("--output", type=Path, default=Path(__file__).parent / "reports/native-world-lifecycle-1375.json")
    args = ap.parse_args()
    pe = PE(args.exe)
    digest = hashlib.sha256(pe.data).hexdigest()
    if digest != SHA:
        raise SystemExit(f"wrong executable SHA: {digest}")
    md, _ = make_disassembler(args.deps_dir)
    functions, all_ins = {}, {}
    for entry in ENTRIES:
        ins, edges = bounded_cfg(pe, md, entry, window=0x4000, max_instructions=4000)
        rows = [{"rva": hex(i.address), "bytes": i.bytes.hex(),
                 "instruction": f"{i.mnemonic} {i.op_str}".strip()} for i in ins]
        all_ins.update({r["rva"]: r for r in rows})
        functions[hex(entry)] = {"prefix32": pe.bytes_at(entry, 32).hex(),
                                 "instructions": rows, "edges": edges,
                                 "decoded_bytes": sum(len(i.bytes) for i in ins),
                                 "runtime_verified": False}
        check_memory_budget()
    for name, claim in FACTS.items():
        missing = [r for r in claim["evidence_rvas"] if r not in all_ins]
        if missing:
            raise SystemExit(f"{name}: noninstruction anchors {missing}")
        claim["evidence_instructions"] = [all_ins[r] for r in claim["evidence_rvas"]]
    pins = []
    for slot, expected in [(0x80, 0x811aa0), (0x140, 0x802540), (0x318, 0x80ff80)]:
        actual = pe.u64(pe.to_offset(0x1cb8460 + slot)) - pe.base
        assert actual == expected, (slot, actual)
        pins.append({"vtable_rva": "0x1cb8460", "slot": hex(slot), "target_rva": hex(actual)})
    literals = []
    for rva, expected in [(0x1cb6db8, "multiplayer"), (0x1cb6da8, "standard"),
                          (0x21f413c, "multi_player")]:
        actual = pe.bytes_at(rva, len(expected) + 1)
        assert actual == expected.encode("ascii") + b"\0"
        literals.append({"rva": hex(rva), "text": expected, "bytes": actual.hex()})
    assert pe.u32(pe.to_offset(0x21f4138)) == 0x3329
    report = {"schema_version": 1, "binary_sha256": digest,
              "analysis_kind": "reviewed_bounded_static_no_process_access", "runtime_verified": False,
              "facts": FACTS, "functions": functions, "vtable_checks": pins, "literal_checks": literals,
              "result": {"early_load_candidate_rva": "0x74b8a0", "all_load_paths_proven": False,
                         "native_generation_counter_identified": False,
                         "strict_single_player_predicate_identified": False,
                         "ready_for_unrestricted_mailbox": False},
              "recommended_experiment": [
                  "Use separate observation-only instrumentation of candidate load/reset entry boundaries; do not publish a production generation claim yet.",
                  "Revoke session and invalidate pending requests before the observed load starts, even if the load later fails; do not automatically rearm on return.",
                  "Own an atomic monotonically increasing epoch in the adapter rather than relabeling game flags as counters.",
                  "Exercise each load/new-game/menu transition, failed load and same-save reload; correlate entry observation before all world mutation and request consumption.",
                  "Obtain a separately verified strict session-mode predicate or session provenance before enabling an offline-only generic submit service.",
                  "Retain process creation identity and a fresh handshake, but do not use stable pointers/date as same-world evidence."],
              "limits": {"per_entry_window_bytes": 0x4000, "per_entry_max_instructions": 4000,
                         "memory_guard_mib": 768, "calls_followed_automatically": False},
              "summary": {"functions": len(functions), "facts": len(FACTS),
                          "decoded_bytes_including_overlaps": sum(f["decoded_bytes"] for f in functions.values())}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    print(json.dumps({"output": str(args.output), "bytes": args.output.stat().st_size,
                      "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(), **report["summary"]}))


if __name__ == "__main__":
    main()
