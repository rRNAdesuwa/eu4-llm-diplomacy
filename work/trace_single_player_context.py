"""Incremental SP context/Steam-fallback evidence; bounded PE reads, never process access."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg

PRIOR_SHA = "0622c8a67f085984db81aa3c5d2e15675ded40f8466bc7b41643b10ca10a7788"
ENTRIES = [0x14c83e0, 0x14c8940, 0x14c97e0, 0x14c9930, 0x14cd8b0,
           0x14ca360, 0x811ab0, 0x113b350, 0x1558f00, 0x15764d0,
           0x157b5b0, 0x216d60, 0x10f5770, 0x14cd4d0, 0x157f190]
SCANS = [(0x14c8000, 0x14d6000), (0x1575000, 0x1582000)]


def fact(summary, *rvas, **extra):
    return dict(summary=summary, evidence_rvas=[hex(r) for r in rvas], runtime_verified=False, **extra)


FACTS = {
    "context_type_and_flags": fact(
        "Both constructors14c83e0/14c8940 install context vtable1d8c900 and clear WORD+54. "
        "Type1 sets BYTE+54=1; type2 sets BYTE+55=1; DWORD+4c retains type. The config constructor "
        "takes type from configuration+A0; the explicit constructor takes its fourth argument. "
        "These flags describe context/transport type, not SP origin.",
        0x14c841c, 0x14c8432, 0x14c8772, 0x14c87b8, 0x14c87bd,
        0x14c87c3, 0x14c87c8, 0x14c87d4, 0x14c8991, 0x14c89a7,
        0x14c8969, 0x14c92be, 0x14c92cf, 0x14c9831, 0x14c9837,
        0x14c983d, 0x14c9842, 0x14c9853,
        context_vtable_rva="0x1d8c900", type_offset="0x4c",
        constructor_states=[{"type": 0, "flags": [0, 0]}, {"type": 1, "flags": [1, 0]},
                            {"type": 2, "flags": [0, 1]}]),
    "type_to_transport": fact(
        "Both constructors select transport by type:2->157ffe0/vtable1d96178, "
        "1->15764d0/vtable1d96088, 0->157b5b0/vtable1d96268. The explicit initializer stores "
        "transport at context+58 and writes context into transport+70. Type2 alone is not "
        "a world-origin witness: the same type can be requested by other constructors/callers.",
        0x14c86de, 0x14c86e4, 0x14c8701, 0x14c8729, 0x14c8752,
        0x14c8ca8, 0x14c8cc3, 0x14c8cc9, 0x14c8d00, 0x14c8da1,
        0x15764ed, 0x15764f4, 0x157b5cd, 0x157b5d4, 0x14c9819,
        0x14c98a4, 0x14c98a8,
        transports={"0": "0x1d96268", "1": "0x1d96088", "2": "0x1d96178"}),
    "fallback_closed": fact(
        "The already-reviewed1120dd0 fallback means !SteamAPI_IsSteamRunning OR platform "
        "object+8==3. When frontend mode0 and fallback=true, it clears the holder context "
        "through server virtual88, calls113b350 with type2 and port0x29a, then installs the "
        "new context through virtual88. 113b350 passes literal localhost and Launch to "
        "14c8940. Thus this fallback has an explicit local transport construction, not an "
        "unresolved virtual setter. The config bytes in controller+400 are not reset in this "
        "branch: a stale network config must still make the proposed witness fail closed.",
        0x1120dfc, 0x1120e02, 0x1120e04, 0x1120e28, 0x1120e2c,
        0x1121575, 0x1121581, 0x112159f, 0x11215b3, 0x11215bd,
        0x11215de, 0x11215e9, 0x113b3f4, 0x113b429, 0x113b448,
        0x113b44c, 0x113b45c,
        fallback_branch_resolved=True, fallback_config_reset_observed=False),
    "steam_sp_uses_shared_type": fact(
        "The non-fallback mode0 Play branch passes one as1558f00's sixth argument. "
        "1558f00 stores it at configuration+A0, the type read by14c83e0. Thus rejecting every "
        "type1 would reject the normal SP configuration path as well as a network host-like "
        "configuration. Keep server's copied config(1,0) AND a witnessed SP origin; neither "
        "context54=1 nor context55=1 is sufficient alone.",
        0x1120ecf, 0x1120ed3, 0x1120eea, 0x1558f0f, 0x1558f13,
        0x1558fc6, 0x1558fca, 0x14c86de, 0x14c8772,
        configuration_type_offset="0xa0", stack_argument_index=6),
    "context_replacement_boundary": fact(
        "Both pinned server/frontend virtual88 resolve811ab0. It consumes the incoming owning "
        "pointer, replaces holder+370, and destroys the old context through virtual destructor. "
        "Invalidate origin/queued requests before entry, including a null replacement; a later "
        "same-address allocation cannot retain the old witness. SP fallback and network join "
        "both use this setter, so recognize the expected SP construction sequence explicitly.",
        0x811ab6, 0x811ac0, 0x811ac3, 0x811ac9, 0x811ada,
        0x811add, 0x811afa, 0x10f57af, 0x10f57c9, 0x10f59dc,
        invalidation_entry="0x811ab0"),
    "reinitialization_boundary": fact(
        "14c9930 closes/resets an existing context, then calls14c97e0 using its existing "
        "+4c type and +58 transport. The initializer sets the matching flag but does not "
        "clear the opposite flag. Constructors clear both first; reuse must not be treated "
        "as a fresh origin, and a type/flag mismatch must reject. Invalidate before14c9930 "
        "or14c97e0 on an already-bound context.",
        0x14c9949, 0x14c994f, 0x14c9974, 0x14c997b, 0x14c9983,
        0x14c9837, 0x14c9842, 0x14c9853,
        invalidation_entries=["0x14c9930", "0x14c97e0"]),
    "in_place_transport_transition": fact(
        "14cd8b0 can keep the context address while changing role/transport: after +480 and "
        "+60 branches it sets context54=1, destroys the old +58 transport and constructs "
        "15764d0 there. Its other branch destroys transport and constructs157b5b0. The "
        "reviewed function does not update type+4c or clear55, so type alone can become stale. "
        "Two direct sites in14ca360 reach it. Invalidate at entry before notifications or "
        "destruction, not after observing a different pointer.",
        0x14cd8da, 0x14cd90c, 0x14cd93a, 0x14cd971, 0x14cd980,
        0x14cd9cc, 0x14cd9d2, 0x14cdbb8, 0x14cdc04, 0x14cdc0a,
        0x14ca56d, 0x14ca6aa,
        invalidation_entry="0x14cd8b0", same_context_address_possible=True),
    "noncontext_write_exclusion": fact(
        "The second scan range has one WORD+54 zero-store157f644. It targets a newly allocated "
        "0x58-byte helper at157f555/157f55a, not the0x880-byte context. Other +4c candidates "
        "are preserved as raw candidates, not promoted to context writes without object provenance.",
        0x157f550, 0x157f555, 0x157f55a, 0x157f644),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exe", type=Path, default=Path(__file__).resolve().parents[2] / "eu4.exe")
    ap.add_argument("--deps-dir", type=Path, required=True)
    ap.add_argument("--output", type=Path, default=Path(__file__).parent / "reports/native-single-player-context-1375.json")
    args = ap.parse_args()
    prior_path = Path(__file__).parent / "reports/native-single-player-origin-1375.json"
    prior_raw = prior_path.read_bytes()
    if len(prior_raw) > 4 * 1024 * 1024 or hashlib.sha256(prior_raw).hexdigest() != PRIOR_SHA:
        raise SystemExit("prior evidence mismatch")
    prior = json.loads(prior_raw)
    pe = PE(args.exe)
    digest = hashlib.sha256(pe.data).hexdigest()
    if digest != SHA:
        raise SystemExit("wrong executable SHA")
    md, cs = make_disassembler(args.deps_dir)
    by_rva = {i["rva"]: i for f in prior["functions"].values() for i in f["instructions"]}
    functions, total = {}, 0
    for entry in ENTRIES:
        ins, edges = bounded_cfg(pe, md, entry, window=16384, max_instructions=4000)
        rows = [{"rva": hex(i.address), "bytes": i.bytes.hex(),
                 "instruction": f"{i.mnemonic} {i.op_str}".strip()} for i in ins]
        count = sum(i.size for i in ins)
        total += count
        by_rva.update({i["rva"]: i for i in rows})
        functions[hex(entry)] = {"instructions": rows, "edges": edges, "decoded_bytes": count}
        check_memory_budget()
    for name, claim in FACTS.items():
        missing = [r for r in claim["evidence_rvas"] if r not in by_rva]
        if missing:
            raise SystemExit(f"{name}: missing anchors {missing}")
        claim["evidence_instructions"] = [by_rva[r] for r in claim["evidence_rvas"]]
    scans = []
    for low, high in SCANS:
        result = {"rva_range": [hex(low), hex(high)], "function_count": 0, "decoded_bytes": 0,
                  "writes": [], "scope": "pdata functions starting in this range; no whole-program completeness claim"}
        for start, end, _ in pe.functions:
            if not low <= start < high:
                continue
            if end - start > 65536:
                raise SystemExit("scan function bound exceeded")
            result["function_count"] += 1
            result["decoded_bytes"] += end - start
            for i in md.disasm(pe.bytes_at(start, end - start), start):
                if (i.mnemonic.startswith("mov") and i.operands and i.operands[0].type == cs.x86.X86_OP_MEM
                        and i.operands[0].mem.disp in (0x4c, 0x54, 0x55)):
                    result["writes"].append({"rva": hex(i.address), "function_rva": hex(start),
                                             "bytes": i.bytes.hex(), "instruction": f"{i.mnemonic} {i.op_str}"})
            check_memory_budget()
        total += result["decoded_bytes"]
        scans.append(result)
    if total > 256 * 1024:
        raise SystemExit("aggregate decode budget exceeded")
    pin = []
    for table in (0x1cb8460, 0x1d5a8c8):
        actual = pe.u64(pe.to_offset(table + 0x88)) - pe.base
        if actual != 0x811ab0:
            raise SystemExit("context setter virtual pin mismatch")
        pin.append({"vtable_rva": hex(table), "slot": "0x88", "target_rva": hex(actual)})
    literal_checks = []
    for rva, expected in [(0x1c45d90, "localhost"), (0x1d5f20c, "Launch"), (0x1c45d80, "InitialSession")]:
        if pe.bytes_at(rva, len(expected) + 1) != expected.encode("ascii") + b"\0":
            raise SystemExit("literal mismatch")
        literal_checks.append({"rva": hex(rva), "text": expected})
    report = {
        "schema_version": 1, "analysis_kind": "incremental_bounded_static_no_process_access",
        "binary_sha256": digest, "prior_report": {"path": "work/reports/native-single-player-origin-1375.json", "sha256": PRIOR_SHA},
        "runtime_verified": False, "facts": FACTS, "functions": functions,
        "bounded_write_inventory": scans, "virtual_checks": pin, "literal_checks": literal_checks,
        "proposed_consumer_predicate": {
            "status": "unimplemented_scoped_policy_draft", "standalone_snapshot_is_sufficient": False,
            "required_origin": "native-thread witness of mode0 SP Play, exact config(1,0), expected context installation and runtime-server construction, bound to adapter epoch",
            "common_fields": {"game_frontend_mode": 0, "server_vtable_rva": "0x1cb8460",
                              "server_19f0": 1, "server_19f1": 0, "context_vtable_rva": "0x1d8c900",
                              "transport_70_equals_context": True, "paused": True},
            "context_profiles": [
                {"type_4c": 2, "flags_54_55": [0, 1], "transport_vtable_rva": "0x1d96178", "origin_branch": "fallback or separately witnessed local constructor"},
                {"type_4c": 1, "flags_54_55": [1, 0], "transport_vtable_rva": "0x1d96088", "origin_branch": "reviewed Steam-SP configuration, requires full native trace before allowlisting"},
            ],
            "reject": ["type0", "noncanonical flags", "type/transport mismatch", "server config other than(1,0)",
                       "missing or revoked origin witness", "changed epoch/root/context/transport/player identity",
                       "foreign player ID or unreadable/unbounded/cyclic player list"],
            "max_player_nodes": 256, "consume_on_same_native_thread": True,
            "all_profiles_runtime_validated": False,
        },
        "mandatory_invalidation_entries": [
            {"rva": "0x811ab0", "reason": "context ownership replacement/clear", "before_first_mutation": True},
            {"rva": "0x14c9930", "reason": "same-context reinitialization", "before_first_mutation": True},
            {"rva": "0x14c97e0", "reason": "initializer called on a bound context", "before_first_mutation": True},
            {"rva": "0x14cd8b0", "reason": "in-place role/transport transition", "before_first_mutation": True},
            {"rva": "0x74b8a0", "reason": "prior-report load/reset entry, successful or failed", "before_first_mutation": True},
        ],
        "counterexample_resolution": {
            "network_gate1_classifier_false": "reject server19f1=1 independently of classifier",
            "premap_controller_classifier_false": "reject wrong runtime-server vtable",
            "same_context_role_transition": "entry invalidation plus exact type/flags/transport checks",
            "fallback_after_stale_network_configuration": "reject config !=(1,0); do not repair or silently rearm",
            "same_save_same_address_load": "origin epoch revoked before load; identity equality cannot restore it",
        },
        "remaining_acceptance_work": [
            "Run observation-only validation of the two exact context profiles and complete SP origin sequence before allowlisting either.",
            "Implement/review entry invalidation and epoch synchronization in a new native host; do not change a frozen research DLL.",
            "Refuse any launch/context constructor/transition not witnessed by the scoped host; do not infer permission from a post-hoc snapshot.",
        ],
        "result": {"context_flag_constructors_resolved": True, "sp_platform_fallback_resolved": True,
                   "concrete_mode_invalidation_entries_identified": True, "whole_program_writer_coverage": False,
                   "strict_sp_runtime_verified": False, "production_ready": False},
        "limits": {"per_entry_window_bytes": 16384, "per_entry_max_instructions": 4000,
                   "aggregate_decode_budget_bytes": 262144, "memory_guard_mib": 768},
        "summary": {"new_functions": len(functions), "facts": len(FACTS),
                    "instruction_anchors": sum(len(v["evidence_rvas"]) for v in FACTS.values()),
                    "inventory_functions": sum(s["function_count"] for s in scans),
                    "decoded_bytes_including_inventory_and_overlap": total},
    }
    raw = (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf8")
    if len(raw) > 4 * 1024 * 1024:
        raise SystemExit("report limit exceeded")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(raw)
    print(json.dumps({"output": str(args.output), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), **report["summary"]}))


if __name__ == "__main__":
    main()
