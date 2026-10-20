"""Bounded, exact-build single-player provenance research. Disk-only; no process API."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg


ENTRIES = [0x6eaa10, 0x80ff80, 0x811aa0, 0x8f450, 0x6e8a90,
           0x803270, 0x80b4c0, 0x10d23c0, 0x10da520,
           0x10eb670, 0x10f03b0, 0x10f0510, 0x1120dd0,
           0x10f6fb0, 0x10f7a80, 0xad6a70, 0x1102e00,
           0x157ffe0, 0x15800d0]


def fact(summary, *rvas, **details):
    return {"summary": summary, "evidence_rvas": [hex(r) for r in rvas],
            "runtime_verified": False, **details}


FACTS = {
    "single_player_button": fact(
        "Frontend constructor binds callback10f03b0 to literal single_player_button: "
        "callback object at frontend+108 is built into R14, then passed to that button. "
        "The callback stores zero in game+747c. The adjacent multi_player_button binds "
        "10f0510, which stores one. These are frontend selections, not immutable world provenance.",
        0x10eb7d0, 0x10eb83d, 0x10eb85a, 0x10ec5eb, 0x10ec602,
        0x10ec605, 0x10eb8e0, 0x10eb94d, 0x10ec60b, 0x10ec622,
        0x10f03c6, 0x10f03cd, 0x10f0555, 0x10f0564,
        mode_field={"offset": "0x747c", "width": 4, "single_player_selection": 0}),
    "frontend_configuration_default": fact(
        "Constructor10d23c0 derives the pre-world controller from6e8a90, installs vtable1d5a8c8, "
        "and initializes the member at+400: WORD member+2e8=1 (little-endian bytes1,0). "
        "The shared base retains the holder argument at+330. This default is not a permanent "
        "mode seal; reviewed network and play paths overwrite the same configuration.",
        0x10d2404, 0x10d24e3, 0x10d24ea, 0x10d251a, 0x10d2542,
        0x6e8aa5, 0x6e8c15,
        configuration_offset="0x400", configuration_flag_offsets=["0x2e8", "0x2e9"],
        default_bytes=[1, 0]),
    "single_player_play_path": fact(
        "1120dd0 reads SteamAPI_IsSteamRunning and a platform-manager field. When game+747c=0 "
        "and its computed fallback flag is false, it constructs a LobbySession configuration "
        "and explicitly assigns bytes1,0 via ad6a70 to controller+400. Later the routine sets "
        "controller+715=1. When Steam/platform fallback is selected, the explicit assignment "
        "is skipped and a different context virtual88 path executes. Thus this one copy site "
        "does not cover every single-player launch and presence of a LobbySession alone does "
        "not imply multiplayer origin.",
        0x1120dfc, 0x1120e02, 0x1120e04, 0x1120e28, 0x1120e2c,
        0x1120e3d, 0x1120e44, 0x1120e4a, 0x1120e4d,
        0x1120eab, 0x1120eea, 0x1120f86, 0x1120fed, 0x1120ff6,
        0x1121004, 0x1121575, 0x1121581, 0x112159f, 0x11215e9, 0x11216a0,
        assigned_bytes=[1, 0], all_sp_launch_paths_proven=False),
    "network_configuration_paths": fact(
        "10f6fb0 (password/session path) assigns WORD0x0100 to temporary config+2e8, copies it "
        "to controller+400, and sets game+747c=2. 10f7a80 (private_checkbox/password session "
        "path) assigns WORD0x0101, copies it to controller+400, and sets mode1. These prove "
        "network-associated configurations1 in the second byte reach the same controller; "
        "host/client role labels are inference, not a proved complete platform-mode enum.",
        0x10f7709, 0x10f7712, 0x10f7719, 0x10f7720, 0x10f777a,
        0x10f7f8a, 0x10f7f93, 0x10f7f9a, 0x10f7fa1, 0x10f8601,
        configurations=[{"frontend_mode": 2, "bytes": [0, 1]},
                        {"frontend_mode": 1, "bytes": [1, 1]}]),
    "configuration_assignment_is_mutable": fact(
        "ad6a70 explicitly copies both flag bytes from source to destination. A reviewed "
        "frontend settings path1102e00 also copies both flags out and back at controller+400. "
        "The bounded direct-reference review does not prove that bulk copies, indirect "
        "writers, alternate platform branches, or later lifecycle paths cannot modify them.",
        0xad6aad, 0xad6ab4, 0xad6aba, 0xad6ac6, 0x1103307,
        0x110335a, 0x1103367, 0x11033c9, 0x11033d6,
        exhaustive_writer_coverage=False),
    "runtime_server_configuration_copy": fact(
        "10da520 tests controller+715; its server creation branch passes controller+400 "
        "as the fifth x64 argument to803270. That constructor installs1cb8460 and invokes "
        "80b4c0 on server+1708 with the fifth argument. The helper copies config bytes+2e8/+2e9 "
        "into that member: runtime server+19f0/+19f1. The same runtime vtable is installed "
        "without choosing a separate type by those flag bytes; vtable1cb8460 is not an SP seal.",
        0x10da695, 0x10dae6c, 0x10dae8b, 0x10dae97, 0x10dae9c,
        0x10daead, 0x8032de, 0x8032e5, 0x803d19, 0x803d20, 0x803d27,
        0x80b51c, 0x80b523, 0x80b529, 0x80b530,
        copied_runtime_offsets=["0x19f0", "0x19f1"],
        static_dataflow_verified=True, strict_sp_proven=False),
    "classifier_false_positive": fact(
        "6eaa10 first calls virtual318. The runtime1cb8460 table resolves to80ff80 reading "
        "server+19f1. Even when that byte is1 (network-origin candidate), classifier false "
        "is possible: context54 or55 nonzero, and the player list is empty or contains only "
        "context+8c's local ID. Thus native classifier false cannot exclude a lone network "
        "host or certify non-joinability. Reachability of particular live network configurations "
        "was not exercised; the branch-level counterexample is exact.",
        0x6eaa20, 0x6eaa28, 0x6eaa36, 0x6eaa3c, 0x6eaa40,
        0x6eaa49, 0x6eaa6c, 0x6eaa72, 0x6eaa75, 0x6eaa77,
        0x6eaa80, 0x6eaa92, 0x80ff80,
        counterexample={"server_19f1": 1, "context_54": 1, "context_55": 0,
                        "player_node_ids": [], "classifier_result": False,
                        "live_network_reachability_verified": False}),
    "object_identity_matters": fact(
        "The predecessor controller1d5a8c8 resolves virtual318 to8f450, unconditional false, "
        "while runtime1cb8460 resolves it to80ff80. Both share the context getter811aa0: "
        "server+330 holder -> holder+370. Checking the classifier on an arbitrary current "
        "controller is unsound. The transport table1d96178 is constructed by157ffe0 after "
        "1575350 and also appears in its destructor; no SP-exclusive constructor or mode "
        "selection is established by that table identity.",
        0x8f450, 0x80ff80, 0x811aa0, 0x811aa7, 0x157fff2, 0x157fff8,
        0x15800da, transport_is_sp_exclusive=False),
}


def import_name(pe, iat_rva):
    """Parse a bounded PE32+ import table, without loading its DLLs."""
    nt = struct.unpack_from("<I", pe.data, 0x3c)[0]
    directory, size = struct.unpack_from("<II", pe.data, nt + 24 + 112 + 8)

    def name(rva):
        raw = pe.bytes_at(rva, 192)
        if b"\0" not in raw:
            raise ValueError("unbounded import name")
        return raw.split(b"\0", 1)[0].decode("ascii")

    for index in range(min(size // 20, 1024)):
        oft, stamp, forward, dll, first = struct.unpack("<5I", pe.bytes_at(directory + index * 20, 20))
        if not any((oft, stamp, forward, dll, first)):
            break
        for thunk in range(4096):
            value = struct.unpack("<Q", pe.bytes_at((oft or first) + thunk * 8, 8))[0]
            if not value:
                break
            if first + thunk * 8 == iat_rva:
                if value >> 63:
                    raise ValueError("ordinal import not accepted")
                return name(dll), name(value + 2)
    raise ValueError("required import missing")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exe", type=Path, default=Path(__file__).resolve().parents[2] / "eu4.exe")
    ap.add_argument("--deps-dir", type=Path, required=True)
    ap.add_argument("--output", type=Path, default=Path(__file__).parent / "reports/native-single-player-origin-1375.json")
    args = ap.parse_args()
    pe = PE(args.exe)
    digest = hashlib.sha256(pe.data).hexdigest()
    if digest != SHA:
        raise SystemExit(f"wrong executable SHA: {digest}")
    md, _ = make_disassembler(args.deps_dir)
    functions, by_rva = {}, {}
    total = 0
    for entry in ENTRIES:
        ins, edges = bounded_cfg(pe, md, entry, window=0x4000, max_instructions=4000)
        rows = [{"rva": hex(i.address), "bytes": i.bytes.hex(),
                 "instruction": f"{i.mnemonic} {i.op_str}".strip()} for i in ins]
        decoded = sum(i.size for i in ins)
        total += decoded
        if total > 256 * 1024:
            raise SystemExit("aggregate decode budget exceeded")
        by_rva.update({r["rva"]: r for r in rows})
        functions[hex(entry)] = {"instructions": rows, "edges": edges,
                                 "decoded_bytes": decoded, "complete_function_claimed": False}
        check_memory_budget()
    for key, claim in FACTS.items():
        missing = [r for r in claim["evidence_rvas"] if r not in by_rva]
        if missing:
            raise SystemExit(f"{key}: noninstruction anchors {missing}")
        claim["evidence_instructions"] = [by_rva[r] for r in claim["evidence_rvas"]]
    pins = []
    for table, slot, expected in [(0x1cb8460, 0x80, 0x811aa0), (0x1cb8460, 0x318, 0x80ff80),
                                   (0x1d5a8c8, 0x80, 0x811aa0), (0x1d5a8c8, 0x318, 0x8f450)]:
        actual = struct.unpack("<Q", pe.bytes_at(table + slot, 8))[0] - pe.base
        if actual != expected:
            raise SystemExit("vtable evidence mismatch")
        pins.append({"vtable_rva": hex(table), "slot": hex(slot), "target_rva": hex(actual)})
    literals = []
    for rva, text in [(0x1d5a6c0, "single_player_button"), (0x1d5a3e8, "multi_player_button"),
                      (0x1ce2ca8, "LobbySession"), (0x1d5c520, "private_checkbox"),
                      (0x1d5c258, "BAD_SERVER_PASSWORD"), (0x1d5eb18, "play_button")]:
        raw = pe.bytes_at(rva, len(text) + 1)
        if raw != text.encode("ascii") + b"\0":
            raise SystemExit("literal evidence mismatch")
        literals.append({"rva": hex(rva), "text": text, "bytes": raw.hex()})
    imported = import_name(pe, 0x1b676e8)
    if imported != ("steam_api64.dll", "SteamAPI_IsSteamRunning"):
        raise SystemExit("Steam branch import mismatch")
    prior = Path(__file__).parent / "reports/native-world-lifecycle-1375.json"
    prior_sha = hashlib.sha256(prior.read_bytes()).hexdigest()
    report = {
        "schema_version": 1, "binary_sha256": digest,
        "analysis_kind": "reviewed_bounded_static_no_process_access",
        "runtime_verified": False, "facts": FACTS, "functions": functions,
        "vtable_checks": pins, "literal_checks": literals,
        "import_check": {"iat_rva": "0x1b676e8", "dll": imported[0], "symbol": imported[1]},
        "prior_world_lifecycle_report": {"path": "work/reports/native-world-lifecycle-1375.json", "sha256": prior_sha},
        "candidate_readonly_snapshot": {
            "game_fields": {"frontend_mode": "DWORD +0x747c", "runtime_server": "QWORD +0x1e00",
                            "player_list": "QWORD +0xa50"},
            "server_vtable_rva": "0x1cb8460", "server_configuration_bytes": ["+0x19f0", "+0x19f1"],
            "context_chain": ["server+0x330", "holder+0x370"],
            "context_fields": ["BYTE +0x54", "BYTE +0x55", "DWORD +0x8c"],
            "node_fields": ["DWORD +0x18", "QWORD +0x60"],
            "max_player_nodes": 256, "same_snapshot_second_pass_required": True,
            "snapshot_alone_proves_world_origin": False,
        },
        "result": {"frontend_sp_selection_and_config_copy_proven": True,
                   "runtime_network_candidate_byte_identified": True,
                   "strict_single_player_predicate_identified": False,
                   "all_launch_and_mode_transition_paths_proven": False,
                   "current_world_origin_verified": False, "offline_nonjoinability_verified": False,
                   "production_ready": False},
        "false_positive_cases": [
            "classifier=false with gate1, a context flag set and empty/all-local-ID player nodes",
            "classifier invoked on pre-world controller: its virtual318 always returns false",
            "server/transport vtable alone: config, not a unique SP type, distinguishes reviewed paths",
            "frontend mode0 selected before a world replacement or after navigating away from an MP path",
            "stable pointers/date/flags across a load: prior lifecycle evidence permits same-address reset",
            "serialized multi_player=no inherits classifier limitations and is historical serialized state",
        ],
        "remaining_proofs": [
            "Resolve platform fallback and continue/load/new-game paths that skip explicit config bytes1,0 assignment.",
            "Trace context54/55 construction/writes and platform session joinability semantics; do not name either byte strict_single_player.",
            "Cover all config mutators including indirect/bulk copies and later host/join/menu transitions.",
            "Bind witnessed SP launch/config propagation to a new adapter-owned epoch before any world mutation; revoke on every load/reset/transition entry.",
            "Recheck actual runtime server/context/config, paused state, epoch and thread immediately before native consumption; snapshot equality is supplementary only.",
            "Use separate bounded read-only observations of fresh SP, resumed SP, Steam fallback, MP host with only local ID, join and return-to-menu; no multiplayer submissions required.",
        ],
        "limits": {"per_entry_window_bytes": 16384, "per_entry_max_instructions": 4000,
                   "aggregate_decode_budget_bytes": 262144, "memory_guard_mib": 768,
                   "calls_followed_automatically": False, "whole_program_writer_coverage": False},
        "summary": {"functions": len(functions), "facts": len(FACTS),
                    "instruction_anchors": sum(len(f["evidence_rvas"]) for f in FACTS.values()),
                    "decoded_bytes_including_overlaps": total},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf8")
    if len(encoded) > 4 * 1024 * 1024:
        raise SystemExit("report size limit exceeded")
    args.output.write_bytes(encoded)
    print(json.dumps({"output": str(args.output), "bytes": len(encoded),
                      "sha256": hashlib.sha256(encoded).hexdigest(), **report["summary"]}))


if __name__ == "__main__":
    main()
