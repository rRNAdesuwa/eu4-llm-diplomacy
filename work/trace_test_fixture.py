"""Exact-build bounded offline evidence for the private diplomacy test fixture.

Reads the disk PE, reviewed scripts and optional installation metadata only.
No process attachment, native calls, installation changes or game requests.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg, token_descriptors

ENTRIES = [0xe4f1d0, 0xe5bb30, 0xe42b00, 0x6ee1d0, 0x6f5500, 0x6f5700,
           0x17050d0, 0x6ee530, 0x756f00, 0x95660,
           0x35a830, 0x14c8030, 0x4e8630, 0x14a7650,
           0x19f6ea0, 0x19fad70, 0x19fb410, 0x1710440, 0x1718300,
           0x5de770, 0x5eddd0, 0x2c9960, 0x6fec50, 0x6fec80, 0x6fee60,
           0x6ff110, 0x6ff4e0, 0x2e1670, 0x93d750]
CALLBACKS = {"run": (0x1fc2558, 0xe4f1d0), "event": (0x1fc3638, 0xe5bb30)}


def fact(summary, *rvas, **details):
    return dict(summary=summary, evidence_rvas=[hex(r) for r in rvas], runtime_verified=False, **details)


FACTS = {
    "cooldown_definition_binding": fact(
        "The exact key DIPLOMAT_COOLDOWN_TIME is passed with output address233e064 to "
        "Lua integer reader14a7650. This is a config-to-global binding, not a supported "
        "runtime script effect or permission to write the global. A changed mod define "
        "must be loaded through a new, verified startup; changing a file is not live proof.",
        0x49a00b, 0x49a012, 0x49a021, 0x14a7674, 0x14a779d,
        global_rva="0x233e064", value_width=4, configuration_key="NDiplomacy.DIPLOMAT_COOLDOWN_TIME"),
    "zero_months_still_has_strict_gate": fact(
        "35a830 copies current rawdate, adds configured months, then writes the directional "
        "relation threshold. 14c8030 returns immediately for months0. Command gate still "
        "requires current date strictly greater than threshold for an initial request. "
        "Thus zero months does not permit paused same-rawdate repetition or retroactively "
        "clear existing save thresholds. Observe the actual threshold and advance normally.",
        0x35a83a, 0x35a840, 0x35a852, 0x35a872, 0x14c8030, 0x14c8032,
        0x4e869c,
        country_relation_array=0x1510, relation_stride=0x48, threshold_offset=0x30),
    "envoy_manager_layout": fact(
        "Country construction creates diplomat manager with token2746 and type3, stores "
        "it as the fourth pointer in country+1480 manager vector. 6fec50 initializes its "
        "vtable1cac380, token DWORD+10, type BYTE+14, unaligned country handle QWORD+16 "
        "and owned entry-pointer vector+20/+28/+30. These fields support bounded read-only "
        "pool observation; never resize the native vector directly.",
        0x2cb753, 0x2cb757, 0x2cb75d, 0x2cb762, 0x2cb80d, 0x2cb818,
        0x6fec57, 0x6fec63, 0x6fec67, 0x6fec6a, 0x6fec6e, 0x6fec72,
        country_vector_offset=0x1480, diplomat_manager_index=3, manager_vtable_rva="0x1cac380"),
    "desired_envoy_count_uses_modifier_aggregate": fact(
        "Named UpdateEnvoyCount2e1670 retrieves country aggregate modifier index0x22 (decimal34), "
        "either dense value+114 or sparse eight-byte {index,value} entries. A dynamic modifier "
        "hook at global2358080+ d00 may transform it. Signed fixed-point divide1000 feeds "
        "6ff110 for diplomat manager. 93d750 is not a simple passive getter: it checks "
        "thread/local validity and has diagnostic/fallback allocation paths. Do not call it "
        "from an external reader or claim a raw aggregate field alone equals availability.",
        0x2e16af, 0x2e18a8, 0x2e18af, 0x2e18b8, 0x2e18c3, 0x2e18e2,
        0x2e1903, 0x2e191c, 0x2e1954, 0x2e196c, 0x2e1970,
        0x93d77a, 0x93d78c, 0x93d9c2,
        modifier_index=0x22, fixed_point_scale=1000, native_recalculate_rva="0x2e1670"),
    "pool_resize_rebinds_envoy_ids": fact(
        "6ff110 resizes via native entry creation/removal then rewrites entry DWORD+44 IDs "
        "and rebinds missions via24ff20. Spy missions also rewrite linked task+2c envoyID. "
        "Removing a large test bonus can remove active entries and change IDs: after either "
        "fixture operation re-resolve the entire manager/entry/mission graph. Existing IDs "
        "and pointers are not stable test handles; no direct resize call is implemented.",
        0x6ff131, 0x6ff148, 0x6ff179, 0x6ff1a5, 0x6ff1ec, 0x6ff205, 0x6ff240,
        0x6ff510, 0x6ff55a,
        entry_size=0x48, entry_state_byte=0x18, entry_mission_qword=0x10, entry_id_dword=0x44),
    "event_callback_abi": fact(
        "Registered event callback is e5bb30. RCX points to explicit Result40 output, "
        "RDX points to read-only three-pointer vector of String32. First argument is event "
        "name; second is target resolved by e42b00. Success byte0 and String32 at output+8 "
        "are returned by moving the local result; RAX is the output pointer. Only normally "
        "returned output.message is engine-owned and destroyed through95660.",
        0xe5bb4f, 0xe5bb52, 0xe5bb8f, 0xe5bb96, 0xe5bc00, 0xe5bc27,
        0xe5c3a1, 0xe5c3a9, 0xe5c3ae, 0xe5c3b3, 0xe5c3b8, 0xe5c3bd,
        signature="Result40* __fastcall(Result40*, const Vector24<String32>*)",
        fixed_core_arguments=[["llmt.1", "FRA"], ["llmt.2", "FRA"]], string_size=32, vector_size=24,
        result_size=40, result_string_offset=8, input_is_sso=True, implemented_arbitrary_strings=False),
    "event_lookup_and_target_fallback": fact(
        "6ee1d0 resolves a textual event ID through event registry and returns null when missing; "
        "callback rejects that path. e42b00 resolves country text, but missing/invalid target "
        "falls back to current or special observed player. The private core therefore uses "
        "exact FRA input and independently validates current player plus live country slot122 "
        "against full handle0100007a00415246. File/startup attestation is not a claim that the "
        "engine loaded a particular definition; native name lookup and state readback remain necessary.",
        0x6ee1fa, 0x6ee205, 0x6ee20c, 0x6ee2aa, 0x6ee2b4,
        0xe5bc2f, 0xe5bc32, 0xe42b12, 0xe42bd0, 0xe42c64, 0xe42c89,
        registry_global_rva="0x2340308", actor_and_target="FRA", full_france_handle="0x0100007a00415246"),
    "event_normal_path_is_effectful": fact(
        "With exactly two arguments, country event callback executes definition+180 effect "
        "through virtual+78, then registers a normal event using756f00 and sends it to server "
        "event UI via10b9a50/6ecae0. A third argument selects another option path and is "
        "not implemented. Native callback success only confirms this processing path, not "
        "a modifier or diplomat-count effect. Hidden event behavior still needs runtime observation.",
        0xe5c021, 0xe5c031, 0xe5c034, 0xe5c15b, 0xe5c162, 0xe5c173,
        0xe5c180, 0xe5c1b4, 0xe5c1c0, 0xe5c1c8,
        callback_success_is_effect_proof=False, option_argument_supported=False),
    "event_temporary_global_requires_freeze_on_exception": fact(
        "Callback saves byte1fd10c4, writes zero during event execution, and restores the saved "
        "byte on normal return. An exception can bypass restoration. The test core records "
        "normal restoration and permanently freezes on exception/unknown ownership; it never "
        "repairs the global, destroys uncertain output or retries after an exception.",
        0xe5bb5d, 0xe5bb64, 0xe5bb6b, 0xe5c3c0,
        temporary_flag_rva="0x1fd10c4", post_exception_native_repair=False),
    "run_abi_and_extension_check": fact(
        "run e4f1d0 uses the same output/vector ABI but requires exactly one argument, copies "
        "its file name and searches for the literal .txt. This is substring validation, not "
        "an exact suffix or caller-approved path policy. It checks VFS existence, creates "
        "a read stream and parser, and executes parsed effects for the current/observed country. "
        "The new core deliberately does not expose run or any script path.",
        0xe4f220, 0xe4f22a, 0xe4f22e, 0xe4f28b, 0xe4f2ca, 0xe4f2d5,
        0xe4f302, 0xe4f3cc, 0xe4f4b7, 0xe4f4bd, 0xe4f5a9, 0xe4f5d9,
        implemented=False),
    "run_uses_virtual_paths_not_windows_absolute_paths": fact(
        "VFS existence19f6ea0 delegates19fad70, sanitizes through19fb410 then iterates mount "
        "records. Sanitizer rejects colon, backslash and . or .. path components; a Windows "
        "absolute path is not the right interface. Stream1710440 calls1718300 mode0, which "
        "uses19f7f60 read path. Fixed basename scripts in the installed user-data root are "
        "candidates, but mount precedence/source identity are not proven by a disk file's "
        "existence. No trusted per-file resolver/anti-shadowing proof is implemented.",
        0x19f6ea4, 0x19fae27, 0x19fae3c, 0x19fae84, 0x19fb4d8, 0x19fb4de,
        0x19fb4ed, 0x19fb4fd, 0x1710491, 0x171839d, 0x17183a0,
        resolved_mount_source_verified=False),
}


def file_record(path):
    data = path.read_bytes()
    if len(data) > 2 * 1024 * 1024:
        raise ValueError(f"Script/source exceeds bound: {path}")
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data), "text": data.decode("utf-8-sig")}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    ap.add_argument("--exe", type=Path, default=root.parent / "eu4.exe")
    ap.add_argument("--deps-dir", type=Path, required=True)
    ap.add_argument("--user-data", type=Path)
    ap.add_argument("--output", type=Path, default=root / "work/reports/native-test-fixture-1375.json")
    args = ap.parse_args()
    pe = PE(args.exe)
    digest = hashlib.sha256(pe.data).hexdigest()
    if digest != SHA:
        raise SystemExit(f"Unsupported executable SHA: {digest}")
    md, _ = make_disassembler(args.deps_dir)
    functions, lookup = {}, {}

    def rows_for(instructions):
        rows = []
        for ins in instructions:
            row = {"rva": hex(ins.address), "bytes": ins.bytes.hex(), "instruction": f"{ins.mnemonic} {ins.op_str}".strip()}
            for operand in ins.operands:
                if operand.type == 3 and ins.reg_name(operand.mem.base) == "rip":
                    target = ins.address + ins.size + operand.mem.disp
                    row["rip_target"] = hex(target)
                    raw = pe.bytes_at(target, 128).split(b"\0")[0]
                    if raw and all(32 <= b < 127 for b in raw):
                        row["ascii"] = raw.decode("ascii")
            rows.append(row)
            lookup[row["rva"]] = row
        return rows

    for entry in ENTRIES:
        ins, edges = bounded_cfg(pe, md, entry, window=0x4000, max_instructions=4000)
        rows = rows_for(ins)
        functions[hex(entry)] = {"prefix32": pe.bytes_at(entry, 32).hex(), "instructions": rows,
                                  "edges": edges, "decoded_bytes": sum(len(i.bytes) for i in ins), "runtime_verified": False}
        check_memory_budget()
    # A reviewed 41-byte call-site window inside the enormous define loader;
    # never disassemble the entire enclosing 342-KiB function.
    window = rows_for(md.disasm(pe.bytes_at(0x49a00b, 0x29), 0x49a00b))
    if [x.get("rip_target") for x in window[:2]] != ["0x233e064", "0x1c699f0"]:
        raise ValueError("Define binding window changed")
    for name, claim in FACTS.items():
        missing = [r for r in claim["evidence_rvas"] if r not in lookup]
        if missing:
            raise ValueError(f"{name}: non-instruction anchors {missing}")
        claim["evidence_instructions"] = [lookup[r] for r in claim["evidence_rvas"]]
    callbacks = {}
    for name, (slot, target) in CALLBACKS.items():
        name_rva = pe.u64(pe.to_offset(slot - 0x30)) - pe.base
        if pe.u64(pe.to_offset(slot)) != pe.base + target or pe.bytes_at(name_rva, 16).split(b"\0")[0] != name.encode("ascii"):
            raise ValueError(f"Console registration mismatch: {name}")
        callbacks[name] = {"slot_rva": hex(slot), "callback_rva": hex(target), "name_rva": hex(name_rva)}
    sources = {}
    for path in sorted((root / "mod/llm_diplomacy_test").rglob("*")):
        if path.is_file():
            sources[str(path.relative_to(root)).replace("\\", "/")] = file_record(path)
    sources["vanilla_define"] = {"path": str(args.exe.parent / "common/defines.lua"),
        "matched_lines": [dict(line=n, text=line) for n, line in enumerate((args.exe.parent / "common/defines.lua").read_text(encoding="utf-8-sig").splitlines(), 1) if "DIPLOMAT_COOLDOWN_TIME" in line]}
    installation = {"checked": False, "engine_loaded_verified": False}
    if args.user_data:
        config = file_record(args.user_data / "dlc_load.json")
        enabled = json.loads(config["text"])["enabled_mods"]
        installation.update(checked=True, config=config, enabled_mods=enabled,
            test_mod_enabled_on_disk="mod/llm_diplomacy_test.mod" in enabled,
            note="Disk configuration at generation only; not process/session state or evidence of loaded definitions.")
        installation["run_candidate_files"] = [file_record(args.user_data / name) for name in
            ("llm_test_diplomats_on.txt", "llm_test_diplomats_off.txt") if (args.user_data / name).is_file()]
    tokens = token_descriptors(pe)
    report = {"schema_version": 1, "game_sha256": digest, "runtime_verified": False,
        "status": "bounded_static_and_file_evidence_no_process_access", "callbacks": callbacks,
        "functions": functions, "define_binding_window": window, "facts": FACTS,
        "tokens": {hex(k): tokens[k] for k in (0x2746, 0x2732, 0x2792, 0x2a2d)},
        "script_sources": sources, "installation_disk_observation": installation,
        "core_surface": {"name": "eu4_test_fixture_1375", "operations": {"enable": "llmt.1", "disable": "llmt.2"},
            "target": "FRA", "profile_id": "1375_test_fixture_v1", "compiled_only": True,
            "implemented_run": False, "implemented_yesman": False, "runtime_effect_verified": False},
        "limits": {"max_window_per_entry": 0x4000, "max_instructions_per_entry": 4000,
            "memory_guard_mib": 768, "automatic_call_following": False},
        "summary": {"functions": len(functions), "facts": len(FACTS),
            "decoded_bytes_including_overlaps": sum(v["decoded_bytes"] for v in functions.values())}}
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(), **report["summary"]}))


if __name__ == "__main__": main()
