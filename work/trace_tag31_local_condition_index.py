"""File-only bounded +80 index for the 51 pinned tag31 action families.

Instruction references are evidence of references, not decoded game rules.
Never follows callees or scans a pre-existing disassembly.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import gc
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

from discover_diplomacy import PE, check_memory_budget, make_disassembler

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SHA = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"
WINDOW = 0x1800
MAX_INSTRUCTIONS = 1200
KEY_PATTERN = re.compile(rb"[A-Z][A-Z0-9_]{2,119}\Z")
PARAMETER_KEYS = {"AMOUNT", "COUNTRY", "COST", "DATE", "DIP", "MEMBER", "MONTHS", "OVERLORD", "RELIGION", "SUBJECTTYPES", "VAL", "VALUE", "WHO", "YEAR", "YEARS"}
PROFILE_PATH = ROOT / "bridge/native/tag_diplomacy_1375_v31/src/work/candidates/v24-pair-send-core-r2-1375/pair_send.cpp"


def budget():
    # discover_diplomacy stops at 768 MiB of this process's committed memory.
    return check_memory_budget() or 0


def decode_bounded(pe, md, cs, entry):
    pending, seen, edges, stops = [entry], {}, [], []
    instruction_limit = False
    while pending and not instruction_limit:
        pc = pending.pop()
        while pc not in seen:
            if not entry <= pc < entry + WINDOW or not pe.executable(pc):
                stops.append({"rva": hex(pc), "reason": "outside_window_or_nonexecutable"})
                break
            if len(seen) >= MAX_INSTRUCTIONS:
                instruction_limit = True
                stops.append({"rva": hex(pc), "reason": "instruction_limit"})
                break
            ins = next(md.disasm(pe.bytes_at(pc, min(15, entry + WINDOW - pc)), pc, count=1), None)
            if ins is None:
                stops.append({"rva": hex(pc), "reason": "undecodable_bytes"})
                break
            seen[pc] = ins
            next_pc = pc + ins.size
            if ins.mnemonic in ("ret", "retf", "int3", "ud2"):
                break
            if ins.mnemonic.startswith("j") or ins.mnemonic.startswith("loop"):
                op = ins.operands[0]
                if op.type == cs.x86.X86_OP_IMM:
                    target = op.imm
                    local = entry <= target < entry + WINDOW and pe.executable(target)
                    edges.append({"source_rva": hex(pc), "target_rva": hex(target), "kind": "direct_branch", "candidate_in_window": local})
                    if local:
                        pending.append(target)
                else:
                    edges.append({"source_rva": hex(pc), "kind": "indirect_branch", "operand": ins.op_str})
                if ins.mnemonic == "jmp":
                    break
            pc = next_pc
            if len(seen) % 128 == 0:
                budget()
        budget()
    for edge in edges:
        target = int(edge["target_rva"], 16) if "target_rva" in edge else None
        edge["followed"] = target in seen if target is not None else False
    return seen, edges, stops, instruction_limit


def summarize_family(pe, md, cs, profile):
    entry = profile["local80"]
    seen, edges, stops, instruction_limit = decode_bounded(pe, md, cs, entry)
    primary = pe.function(entry)
    calls, indirect_calls, string_refs = [], [], []
    ranges, terminal_rvas, outside_primary = [], [], []
    for rva in sorted(seen):
        ins = seen[rva]
        if not ranges or ranges[-1][1] != rva:
            ranges.append([rva, rva + ins.size])
        else:
            ranges[-1][1] = rva + ins.size
        if ins.mnemonic in ("ret", "retf", "int3", "ud2"):
            terminal_rvas.append({"rva": hex(rva), "mnemonic": ins.mnemonic})
        if primary and not primary[0] <= rva < primary[1]:
            outside_primary.append(hex(rva))
        if ins.mnemonic == "call":
            op = ins.operands[0]
            record = {"instruction_rva": hex(rva), "bytes": ins.bytes.hex(), "instruction": f"{ins.mnemonic} {ins.op_str}"}
            if op.type == cs.x86.X86_OP_IMM:
                target = op.imm
                target_function = pe.function(target)
                record.update(target_rva=hex(target), target_executable=pe.executable(target), followed=False,
                              target_pdata_range=[hex(x) for x in target_function[:2]] if target_function else None)
                calls.append(record)
            else:
                indirect_calls.append(record)
        for op in ins.operands:
            if op.type != cs.x86.X86_OP_MEM or op.mem.base != cs.x86.X86_REG_RIP:
                continue
            target = rva + ins.size + op.mem.disp
            raw = pe.bytes_at(target, 121)
            if b"\0" not in raw:
                continue
            value = raw.split(b"\0", 1)[0]
            if not KEY_PATTERN.fullmatch(value):
                continue
            key = value.decode("ascii")
            string_refs.append({"instruction_rva": hex(rva), "bytes": ins.bytes.hex(),
                                "instruction": f"{ins.mnemonic} {ins.op_str}", "string_rva": hex(target), "key": key,
                                "failure_key_candidate": key not in PARAMETER_KEYS,
                                "evidence": "instruction_boundary_decoded_rip_relative_ascii_z_reference",
                                "is_taken_failure_branch_proven": False})
    unfollowed = [e for e in edges if not e["followed"]]
    limiting_stops = [s for s in stops if s["reason"] in {"instruction_limit", "undecodable_bytes", "outside_window_or_nonexecutable"}]
    result = {
        "family": profile["family"], "token": hex(profile["token"]), "vtable_rva": hex(profile["vtable"]),
        "entry_rva": hex(entry), "full88_rva": hex(profile["full88"]), "vtable_local80_matches_registry": profile["slot_verified"],
        "boundaries": {"window_start_rva": hex(entry), "window_end_rva_exclusive": hex(entry + WINDOW),
                       "primary_pdata_range": [hex(x) for x in primary[:2]] if primary else None,
                       "primary_unwind_rva": hex(primary[2]) if primary else None,
                       "decoded_ranges": [[hex(a), hex(b)] for a, b in ranges],
                       "decoded_min_rva": hex(min(seen)) if seen else None,
                       "decoded_end_rva_exclusive": hex(max(i.address + i.size for i in seen.values())) if seen else None},
        "coverage": {"kind": "reachable_bounded_instruction_graph_no_callee_traversal",
                     "decoded_instruction_count": len(seen), "decoded_bytes": sum(i.size for i in seen.values()),
                     "instruction_limit_hit": instruction_limit, "window_or_decode_stop": bool(limiting_stops),
                     "unfollowed_direct_branch_count": sum(e["kind"] == "direct_branch" for e in unfollowed),
                     "unresolved_indirect_branch_count": sum(e["kind"] == "indirect_branch" for e in unfollowed),
                     "instructions_outside_primary_pdata_count": len(outside_primary),
                     "native_logic_complete": False,
                     "truncated": bool(limiting_stops or unfollowed),
                     "truncated_meaning": "A bound, undecodable path, external/tail branch, or unresolved indirect branch prevents closed local CFG coverage; callees are always omitted."},
        "terminal_instructions": terminal_rvas, "stops": stops, "unfollowed_branches": unfollowed,
        "direct_calls": calls, "indirect_calls": indirect_calls, "localization_key_references": string_refs,
        "no_failure_condition_conclusion": True,
    }
    del seen, edges, stops, ranges, calls, indirect_calls, string_refs
    gc.collect()
    return result


def profiles_and_actions(pe):
    source = PROFILE_PATH.read_bytes()
    text = source.decode("utf-8-sig")
    block = re.search(r"registry\{\{(.*?)\}\};", text, re.S).group(1)
    profiles = []
    for row in re.findall(r"\{Family::([^{}]+)\}", block):
        fields = [x.strip() for x in row.split(",")]
        profile = {"family": fields[0], "token": int(fields[1], 16), "vtable": int(fields[3], 16),
                   "local80": int(fields[7], 16), "full88": int(fields[8], 16)}
        slot = pe.to_offset(profile["vtable"] + 0x80)
        profile["slot_verified"] = slot is not None and pe.u64(slot) - pe.base == profile["local80"]
        if not profile["slot_verified"]:
            raise ValueError("Registry +80 differs from pinned EXE vtable")
        profiles.append(profile)
    if len(profiles) != 51 or len({p["family"] for p in profiles}) != 51:
        raise ValueError("Expected exactly 51 unique registered families")
    names = re.findall(r'"([^"]+)"', re.search(r"names\{\{(.*?)\}\};", text, re.S).group(1))
    binding_text = re.search(r"bindings\{\{(.*?)\}\};", text, re.S).group(1)
    bindings = re.findall(r'\{Family::(\w+),(true|false),"([^"]*)"\}', binding_text)
    if len(names) != 120 or len(bindings) != 118:
        raise ValueError("Expected 120 names and 118 pair-family bindings")
    by_family = {p["family"]: p for p in profiles}
    actions = []
    for name, (family, mode, script_key) in zip(names, bindings):
        actions.append({"action": name, "family": family, "positive_mode": mode == "true", "script_key": script_key or None,
                        "local80_rva": hex(by_family[family]["local80"]), "conditions_complete": False})
    for name in names[len(bindings):]:
        actions.append({"action": name, "family": None, "local80_rva": None,
                        "outside_pair_family_index": True, "conditions_complete": False})
    return profiles, actions, hashlib.sha256(source).hexdigest()


def add_english_text(families, localisation):
    wanted = {r["key"] for f in families for r in f["localization_key_references"]}
    matches = collections.defaultdict(list)
    files = sorted(localisation.glob("*english*.yml")) if localisation.exists() else []
    total_bytes = 0
    pattern = re.compile(r'^\s*([A-Za-z0-9_.\-]+):\d*\s+"(.*)"\s*(?:#.*)?$')
    for path in files:
        total_bytes += path.stat().st_size
        with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
            for line_number, line in enumerate(stream, 1):
                match = pattern.match(line.rstrip("\r\n"))
                if match and match[1] in wanted:
                    value = match[2]
                    matches[match[1]].append({"file": path.relative_to(ROOT).as_posix(), "line": line_number,
                                             "short_text": value[:240], "text_truncated": len(value) > 240})
        budget()
    for family in families:
        for reference in family["localization_key_references"]:
            reference["english_localization"] = matches.get(reference["key"], [])
            reference["english_key_found"] = reference["key"] in matches
    return {"file_count": len(files), "streamed_bytes": total_bytes, "wanted_keys": len(wanted),
            "matched_unique_keys": len(matches), "source": localisation.relative_to(ROOT).as_posix(),
            "proves_runtime_language_or_failure": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "work/runtime/tag31-local-condition-index-20261013.json")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Refusing to overwrite an existing historical index")
    pe = PE(ROOT.parent / "eu4.exe")
    digest = hashlib.sha256(pe.data).hexdigest()
    if digest != EXPECTED_SHA:
        raise ValueError("Unexpected EXE SHA256")
    md, cs = make_disassembler(Path(tempfile.gettempdir()) / "eu4-native-analysis-deps")
    if md is None:
        raise RuntimeError("Capstone unavailable")
    profiles, actions, source_sha = profiles_and_actions(pe)
    families, peak_commit = [], budget()
    for profile in profiles:
        family = summarize_family(pe, md, cs, profile)
        families.append(family)
        peak_commit = max(peak_commit, budget())
        print(f"{len(families):02}/51 {family['family']} instructions={family['coverage']['decoded_instruction_count']} keys={len(family['localization_key_references'])} truncated={family['coverage']['truncated']}", flush=True)
        del family
        gc.collect()
    english = add_english_text(families, ROOT / "work/runtime/unpacked-1.37.5/base/localisation")
    peak_commit = max(peak_commit, budget())
    stats = {"family_count": len(families), "action_name_count": len(actions), "pair_family_action_count": sum(a["family"] is not None for a in actions),
             "outside_pair_family_actions": [a["action"] for a in actions if a["family"] is None],
             "decoded_instruction_count": sum(f["coverage"]["decoded_instruction_count"] for f in families),
             "decoded_bytes": sum(f["coverage"]["decoded_bytes"] for f in families),
             "direct_call_count": sum(len(f["direct_calls"]) for f in families),
             "unique_direct_call_targets": len({c["target_rva"] for f in families for c in f["direct_calls"]}),
             "localization_reference_count": sum(len(f["localization_key_references"]) for f in families),
             "unique_localization_keys": len({r["key"] for f in families for r in f["localization_key_references"]}),
             "failure_key_candidate_reference_count": sum(r["failure_key_candidate"] for f in families for r in f["localization_key_references"]),
             "truncated_family_count": sum(f["coverage"]["truncated"] for f in families),
             "instruction_limit_family_count": sum(f["coverage"]["instruction_limit_hit"] for f in families),
             "unfollowed_direct_branch_count": sum(f["coverage"]["unfollowed_direct_branch_count"] for f in families),
             "unresolved_indirect_branch_count": sum(f["coverage"]["unresolved_indirect_branch_count"] for f in families),
             "peak_committed_memory_bytes": peak_commit}
    report = {"schema": "EU4TAG31-LOCAL-CONDITION-INDEX/1", "captured_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "file_only": True, "game_process_accessed": False, "native_calls": 0, "runtime_verified": False,
              "game_sha256": digest, "registry_source": PROFILE_PATH.relative_to(ROOT).as_posix(), "registry_sha256": source_sha,
              "limits": {"decode_window_bytes_per_family": WINDOW, "max_instructions_per_family": MAX_INSTRUCTIONS,
                         "committed_memory_stop_bytes": 768 * 1024 * 1024, "callee_traversal": False,
                         "raw_string_read_bytes_per_rip_reference": 121, "temporary_instruction_objects_released_each_family": True},
              "limitations": ["This is a reference index, not a complete native condition decoder or a failure-branch trace.",
                              "A localization key reference proves the key and instruction boundary only; it may describe positive, cancellation, placeholder, or failure text.",
                              "failure_key_candidate is only a lexical exclusion of common parameter names, not a decoded predicate.",
                              "Family +80 may contain positive and cancellation modes. Calls and action script conditions are not recursively decoded.",
                              "An external direct branch may be a tail call. Truncated marks open local CFG paths and does not assert corrupted code.",
                              "118 public names map to the 51 pair families; select_rival/remove_rival use independent paths and have no family +80 entry here.",
                              "Public full+88 common conditions can reject before any +80 entry is reached.",
                              "English short text is from unpacked files; effective mod precedence and runtime strings are not verified."],
              "statistics": stats, "english_localization_scan": english, "actions": actions, "families": families}
    budget()
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"output": str(args.output), "statistics": stats, "english": english}, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
