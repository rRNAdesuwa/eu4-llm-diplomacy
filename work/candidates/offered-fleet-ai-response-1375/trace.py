"""Reproducible disk-only, bounded offered-fleet reply / yesman ABI evidence.

No process APIs, console execution, native calls, disassembly-wide searches,
patches, or runtime-readiness decisions. Existing exploratory drafts are retained.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "work"))
from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg
from trace_change_subject_type import rows

INPUTS = {
    "work/reports/native-pair-extension-v10-1375.json": "0c1731b0b29b296da73dc406fb31544ada59c17c275d17d623677b16998698bd",
    "work/reports/native-pair-extension-effects-v10-1375.json": "b6f4b69db38f5e3eae0c3cebf1fa5298701b86a98e8299d6f0e9759b84861f62",
    "work/reports/native-pair-replies-1375.json": "da3faa061af3d9ee8a3003412151594c6305b765afd8d739b4cb4a4759f63510",
    "work/discover_diplomacy.py": "a4df91d82e12db0687fcf7e52a2f97d0ac4d2d9af78f837ce6724d099ff50318",
    "work/map_diplomacy_fields.py": "a8334910e72d05cb0336ef55a20eb028d1a018efa04da4493c6cb5fe3157ae85",
    "work/trace_change_subject_type.py": "8bc16d94e8f6104a79ce541c6de0843894293e158f44efb6c47f27b9b8dec6da",
}
FUNCTIONS = (
    (0x534990, "offered_fleet_acceptance_score", 0x2800, 3000),
    (0x4ea1e0, "generic_score_at_least_one", 0x2800, 3000),
    (0x51fa90, "initial_positive_request_needs_reply", 0x400, 100),
    (0x8f450, "false_virtual", 0x100, 50),
    (0x534be0, "distinct_reverse_ask_evaluation_virtual", 0x1000, 500),
    (0x4e7c50, "common_command_execute_reply_dispatch", 0x2800, 3000),
    (0x2cd570, "target_ai_gate", 0x400, 150),
    (0xb52e0, "target_ai_gate_detail", 0x400, 150),
    (0x531b70, "offered_fleet_effect_and_reply_message", 0x2800, 3000),
    (0xe50180, "yesman_handler", 0x1000, 800),
    (0x6e910c, "console_registration_fragment_not_whole_function", 0x1000, 500),
    (0x1720b50, "static_to_runtime_command_record", 0x1000, 500),
    (0x1720930, "runtime_registry_append", 0x1000, 500),
    (0x172b120, "raw_callback_adapter", 0x100, 50),
    (0x1721320, "normal_console_dispatcher", 0x2800, 3000),
    (0x95660, "engine_string32_normal_destructor", 0x400, 150),
)
SLOTS = {
    0x40: 0x4e9930, 0x48: 0x531b70, 0x80: 0x533fa0,
    0xb0: 0x534900, 0xb8: 0x4ea1e0, 0xc8: 0x534be0,
    0xd0: 0x51fa90, 0xf0: 0x8f450, 0x120: 0x534990,
}


def fact(text, *rvas, **fields):
    return {"summary": text, "evidence_rvas": [hex(x) for x in rvas],
            "evidence_level": "static_only", "runtime_verified": False, **fields}


FACTS = {
    "ordinary_score": fact(
        "Offer-fleet virtual+120 returns signed -1000 on the ordinary path. If an "
        "optional reason list is supplied, it appends DIPLO_STRATEGIC_INTERESTS "
        "with the same -1000. There is no diprep/opinion score addition in this "
        "bounded score body. Virtual+c8 instead constructs a reverse ask object; "
        "its different evaluation must not replace this own acceptance score.",
        0x534a1b, 0x534a87, 0x534adf, 0x534b65,
        ordinary_score=-1000, positive_override_score=99999,
        ordinary_diprep_adjustment_observed=False),
    "yesman_score_branch": fact(
        "The special score99999 requires nonzero BYTE game+23a1 and equality "
        "between the actor-country handle slot and the selected effective-player "
        "slot. Selection uses game+1e68 only when BYTE+1e66==7 and BYTE+1e6f!=0; "
        "otherwise it uses game+1e60. The comparison is 16-bit slots after >>32, "
        "not a full-handle identity proof. No current runtime flag is inferred.",
        0x5349af, 0x5349b6, 0x5349bf, 0x5349c3, 0x5349dd,
        0x5349e7, 0x5349f0, 0x5349f9, 0x534a00, 0x534a0c, 0x534a11,
        game_global_rva="0x233fe78", flag_offset="0x23a1", flag_width_bytes=1,
        current_runtime_value=None, strict_single_player_proven=False),
    "acceptance_predicate": fact(
        "The generic +b8 predicate calls virtual+120 and tests signed EAX>=1. "
        "Thus -1000 is false and99999 is true; a successful queue submission is "
        "not this predicate and does not prove a positive reply.",
        0x4ea256, 0x4ea261, 0x4ea269, threshold=1),
    "reply_transition": fact(
        "On the traced AI reply branch, initial state0/value1 needs a reply. "
        "Target control/AI gates precede clone+b0. Offer-fleet +f0 returns false, "
        "so +b8 selects cloned state+34=1(reject) or2(accept). Wrapper+40 and "
        "queue bfe50 enqueue the response; the intermediate clone is then "
        "deleted after wrapper ownership duplication. Other control branches "
        "can defer/present the request; none proves immediate effect or SP.",
        0x4e8125, 0x4e8137, 0x4e8188, 0x4e819b, 0x4e81af,
        0x4e81c1, 0x4e81c7, 0x4e81d0, 0x4e81e7, 0x4e81ed, 0x4e81fe,
        rejection_state=1, acceptance_state=2, request_state=0),
    "accepted_effect_direction": fact(
        "For state2/value1 the offered-fleet effect allocates0x48, constructs "
        "a70670, stores recipient/target in relation+10 (rights holder), "
        "actor in+18 (port grantor), and current date in+20; a70760 registers "
        "the relationship. Proposal actor/target order must not be interpreted "
        "as holder/grantor order.",
        0x531f1d, 0x531f20, 0x531f29, 0x531f40, 0x531f4f,
        0x531f66, 0x531f6a, 0x531f6e, 0x531f75,
        holder="target", grantor="actor", relation_vtable_rva="0x1cddee0"),
    "rejection_and_message": fact(
        "State1/value1 follows the rejection message branch, builds RESULT from "
        "DIPLO_DENY, and publishes OFFER_FLEETBASING using8d4660/8c1b10. The "
        "accepted branch uses DIPLO_ACCEPT with the same message key. The key "
        "alone, absent RO relationship, or submit-return=true cannot classify "
        "an AI reply. A decoded RESULT/response state or independent UI evidence "
        "is required; this disk-only report contains no current UI observation.",
        0x532f47, 0x532f50, 0x533013, 0x533024, 0x5331c1,
        0x533216, 0x533221, 0x532145, 0x532650,
        message_key="OFFER_FLEETBASING", key_is_rejection_specific=False),
    "console_registration": fact(
        "The startup fragment registers378 static rows from1fc23e0, stride0xa0. "
        "Both pinned yesman rows bind callbacke50180. Adapter1720b50 changes "
        "the callable representation: runtime record+38=172b120 wrapper and "
        "+40=raw callback. The normal dispatcher loads both before invocation.",
        0x6e9167, 0x6e916f, 0x6e9176, 0x6e9186, 0x6e918b,
        0x1720b73, 0x1720b7e, 0x172175c, 0x1721760, 0x172176d),
    "normal_zero_argument_abi": fact(
        "Normal console dispatcher1721320 receives manager RCX, output RDX, "
        "token-vector R8. It removes token0(command name), creates a24-byte "
        "begin/end/capacity vector, and leaves all three pointers null when no "
        "arguments remain. Callback wrapper receives RCX=Result40*, RDX=that "
        "vector*, R8=raw callback; wrapper calls R8 and returns the original "
        "output pointer in RAX. Handler requires no third parameter. Direct "
        "candidate calls must use the exact all-null container, not a token "
        "'yesman', empty EngineString, reversed pointers, or merely end==begin.",
        0x1721674, 0x1721677, 0x1721680, 0x1721696, 0x1721699,
        0x17216b8, 0x17216ba, 0x1721764, 0x1721769, 0x172176d,
        0xe501c1, 0xe501c5, 0xe501c8, 0xe501cc, 0xe501ce,
        handler_rva="0xe50180", wrapper_rva="0x172b120",
        windows_x64_signature="Result40* handler(Result40* output, const Vector24<EngineString32>* arguments)",
        zero_arguments={"begin": 0, "end": 0, "capacity": 0},
        result={"size_bytes": 40, "alignment_bytes": 8, "success_byte_offset": 0,
                "message_offset": 8, "message_size_bytes": 32},
        arguments={"size_bytes": 24, "alignment_bytes": 8, "element_size_bytes": 32,
                   "begin_offset": 0, "end_offset": 8, "capacity_offset": 16}),
    "handler_side_effect_and_result": fact(
        "Handler initializes success=false and its output String32(empty, "
        "capacity15). A positive argument count returns false with the no-args "
        "diagnostic and does not toggle. Zero arguments load gameglobal and "
        "write BYTE+23a1=(old==0), then success=true, then format a result message. "
        "A noncanonical old byte is not preserved as a boolean identity. RAX "
        "returns the caller result pointer. There is no explicit set-on/set-off ABI.",
        0xe501a0, 0xe501a3, 0xe501a7, 0xe501aa, 0xe501ae,
        0xe501d4, 0xe501f0, 0xe502ae, 0xe502b5, 0xe502bc, 0xe502bf,
        0xe502c5, 0xe50310, 0xe50327, 0xe503de,
        operation="toggle_only", write_precedes_message_allocation=True),
    "normal_result_ownership": fact(
        "The handler owns its two local String32 temporaries and moves the "
        "formatted string into output+8, resetting the moved-from local before "
        "95660 cleanup. After normal callback return the normal dispatcher "
        "copies success and the output string, then destroys its temporary "
        "result's message with95660. It also destroys argument strings and "
        "frees the vector if allocated. The Result40 itself is caller storage, "
        "not a heap object to delete; a direct caller owns the returned message "
        "and must destroy it exactly once with the engine string destructor on "
        "a proven normal-return path. The handler overwrites output without "
        "first releasing a prior output string, so storage must be fresh.",
        0xe5037d, 0xe50380, 0xe50383, 0xe50387, 0xe5038b,
        0xe5038f, 0xe50397, 0xe5039f, 0xe503d9,
        0x1721938, 0x172193c, 0x1721946, 0x1721950, 0x1721ae5,
        normal_message_destructor_rva="0x95660", delete_result_storage=False),
    "exception_boundary": fact(
        "The flag write occurs before message formatting/allocation. An "
        "exception, allocation failure, or abnormal return can therefore leave "
        "the flag changed with result lifetime unknown. This report does not "
        "prove unwind cleanup or recovery. No blind toggle retry or speculative "
        "destructor is permitted. A future host requires durable once-only "
        "intent, explicit requested state and before0/1, native-thread guards, "
        "one callback attempt, post-byte and result validation, normal cleanup "
        "proof, and session freeze on any unknown. No such host is implemented here.",
        0xe502bf, 0xe50310, 0xe50327, 0xe5039f,
        retry_allowed=False, seh_recovery_verified=False, control_implemented=False),
    "dispatcher_guards_not_production_sp": fact(
        "The normal dispatcher marks a non-stats command at manager+44. For "
        "yesman it requires manager+19==0, else returns the literal 'Command "
        "not available in multiplayer or ironman mode.' That byte is populated "
        "by the startup fragment from6eaa10 and game+24d0; this is not a proved "
        "strict offline-world origin witness. It calls an optional global "
        "pre-callback, invokes the handler, then checks manager+19 again; if "
        "the forbidden condition is now true for a nonexception command, the "
        "observed path writes to address0. Calling e50180 directly bypasses "
        "these dispatcher guards, callback and bookkeeping, and cannot inherit "
        "their safety. Handler itself proves neither pause nor strict SP nor "
        "world lifetime. This is static ABI evidence, not deployment approval.",
        0x6e9133, 0x6e9155, 0x172145d, 0x1721463, 0x172160a,
        0x1721626, 0x172174e, 0x172175a, 0x1721774, 0x172192d,
        direct_call_equivalent_to_console=False, strict_single_player_proven=False),
}


def sha_file(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def checked_inputs():
    output = []
    for name, expected in INPUTS.items():
        path = ROOT / name
        digest = sha_file(path)
        if digest != expected:
            raise ValueError(f"Pinned static input changed: {name}")
        output.append({"path": name, "size_bytes": path.stat().st_size, "sha256": digest})
    return output


def localizations():
    wanted = {
        "localisation/diplo_reasons_l_english.yml": {"DIPLO_STRATEGIC_INTERESTS"},
        "localisation/EU4_l_english.yml": {"DIPLO_DENY", "DIPLO_ACCEPT", "OFFER_FLEET_BASING_RIGHT"},
        "localisation/messages_l_english.yml": {"OFFER_FLEETBASING_TITLE", "OFFER_FLEETBASING_SETUP", "OFFER_FLEETBASING_5", "OFFER_FLEETBASING_LOG"},
    }
    output = []
    for name, keys in wanted.items():
        path = ROOT.parent / name
        found = {}
        with path.open("r", encoding="utf-8-sig") as stream:
            for line_no, line in enumerate(stream, 1):
                if len(line) > 65536:
                    raise ValueError("Oversize localization line")
                key = line.strip().split(":", 1)[0]
                if key in keys:
                    if key in found:
                        raise ValueError(f"Duplicate localization key: {key}")
                    found[key] = {"line": line_no, "text": line.rstrip("\r\n")}
        if found.keys() != keys:
            raise ValueError(f"Missing localization: {name}: {keys - found.keys()}")
        output.append({"game_relative_path": name, "sha256": sha_file(path),
                       "size_bytes": path.stat().st_size, "entries": found})
    return output


def predicted_score(flag, actor_slot, effective_player_slot):
    """Offline model of just the decoded scalar branch, not native legality."""
    for val, bound in ((flag, 255), (actor_slot, 65535), (effective_player_slot, 65535)):
        if type(val) is not int or not 0 <= val <= bound:
            raise ValueError("Exact bounded integers required")
    return 99999 if flag != 0 and actor_slot == effective_player_slot else -1000


def require_canonical_empty_vector(values):
    if type(values) is not dict or set(values) != {"begin", "end", "capacity"}:
        raise ValueError("Exact Vector24 field set required")
    if any(type(v) is not int or v != 0 for v in values.values()):
        raise ValueError("Zero args must be the canonical all-null vector")


def make_report():
    inputs = checked_inputs()
    pe = PE(ROOT.parent / "eu4.exe")
    if hashlib.sha256(pe.data).hexdigest() != SHA:
        raise ValueError("Only the pinned 1.37.5 executable is supported")
    check_memory_budget()
    md, _ = make_disassembler(Path(tempfile.gettempdir()) / "eu4-native-analysis-deps")
    functions, by_rva = [], {}
    for entry, name, window, maximum in FUNCTIONS:
        ins, edges = bounded_cfg(pe, md, entry, window=window, max_instructions=maximum)
        evidence = rows(pe, ins)
        functions.append({"entry_rva": hex(entry), "name": name, "window_bytes": window,
                          "max_instructions": maximum, "decoded_bytes": sum(x.size for x in ins),
                          "instructions": evidence, "edges": edges, "runtime_verified": False})
        by_rva.update({r["rva"]: r for r in evidence})
        check_memory_budget()
    for f in FACTS.values():
        for rva in f["evidence_rvas"]:
            if rva not in by_rva:
                raise ValueError(f"Missing instruction boundary for fact: {rva}")
    vtable = {}
    for offset, expected in SLOTS.items():
        raw = pe.bytes_at(0x1c7f1f0 + offset, 8)
        actual = struct.unpack("<Q", raw)[0] - pe.base
        if actual != expected:
            raise ValueError("Offered-fleet vtable mismatch")
        vtable[hex(offset)] = {"rva": hex(actual), "pointer_bytes": raw.hex()}
    commands = []
    for row in (0x1fcb3a0, 0x1fccde0):
        raw = pe.bytes_at(row, 0xa0)
        name, description, handler = [struct.unpack_from("<Q", raw, offset)[0] - pe.base
                                      for offset in (8, 0x30, 0x38)]
        if (name, description, handler) != (0x1d34aec, 0x1d34af8, 0xe50180):
            raise ValueError("Yesman static command row mismatch")
        if pe.bytes_at(name, 7) != b"yesman\0" or pe.bytes_at(description, 30) != b"Toggles AI positive responses\0":
            raise ValueError("Yesman name/description mismatch")
        commands.append({"row_rva": hex(row), "index": (row - 0x1fc23e0) // 0xa0,
                         "row_bytes": raw.hex(), "name_rva": hex(name),
                         "description_rva": hex(description), "handler_rva": hex(handler)})
    loc = localizations()
    total_bytes = sum(f["decoded_bytes"] for f in functions)
    if total_bytes > 64 * 1024 or len(by_rva) > 12000:
        raise ValueError("Report instruction budget exceeded")
    return {
        "schema_version": 1, "purpose": "offered_fleet_ai_response_and_yesman_abi_static_1375",
        "exe_sha256": SHA, "runtime_verified": False, "production_ready": False,
        "process_accessed": False, "native_called": False, "control_implemented": False,
        "source_inputs": inputs, "localization_inputs": loc,
        "bounds": {"functions": len(functions), "unique_instructions": len(by_rva),
                   "decoded_bytes": total_bytes, "maximum_decoded_bytes": 65536,
                   "memory_stop_mib": 768, "recursive_callee_scan": False,
                   "whole_disassembly_read": False},
        "functions": functions, "offered_fleet_vtable": {"rva": "0x1c7f1f0", "slots": vtable},
        "console_registration": {"table_rva": "0x1fc23e0", "row_stride": 160,
                                 "row_count": 378, "yesman_rows": commands},
        "facts": FACTS,
        "readonly_observation_whitelist": [
            {"object": "module", "field": "game_pointer", "rva": "0x233fe78", "width_bytes": 8},
            {"object": "game", "field": "positive_response_flag", "offset": "0x23a1", "width_bytes": 1, "require_canonical_0_or_1": True},
            {"object": "game", "field": "player_handle", "offset": "0x1e60", "width_bytes": 8},
            {"object": "game", "field": "selection_byte", "offset": "0x1e66", "width_bytes": 1},
            {"object": "game", "field": "alternate_player_handle", "offset": "0x1e68", "width_bytes": 8},
            {"object": "game", "field": "alternate_selection_byte", "offset": "0x1e6f", "width_bytes": 1},
        ],
        "readonly_requirements": [
            "Exact executable/module identity, held PID+creation, and matching world before/after.",
            "Query/VM_READ only; bounded two passes with exact byte/integer types and no torn identity.",
            "Resolve actor country through validated database slot and full handle before interpreting the score slot comparison.",
            "A readonly flag sample is an instant observation, not strict SP, lifecycle synchronization, future consent, or write authorization.",
        ],
        "next_test_constraints": [
            "Do not resend the already-denied request or revoke a relationship that is absent.",
            "Higher diplomatic reputation or opinion does not change this own ordinary score body; no natural positive offered-fleet AI setup is established here.",
            "The already-supported ask-fleet path is a different request; its accepted relation can support cancel-fleet testing but does not verify offered-fleet/revoke-fleet direction.",
            "If a future disposable test host uses an explicit positive-response control, require fresh legality, exact player/recipient identities, paused world, durable once-only control request, canonical before0/1 and expected after, and a bounded explicit off boundary.",
            "Such a future control is a test fixture, not a natural-AI acceptance result and not an operation supported by frozen v14.",
            "Human-controlled recipient responses are a distinct untested path and are not proposed as an automatic fallback.",
        ],
        "unresolved": [
            "No handler call, normal-return cleanup, override flag transition, or offered-fleet acceptance was runtime tested by this report.",
            "No current game+23a1 value is inferred from a baseline, diprep, prior UI, or table registration.",
            "No exhaustive game+23a1 writer inventory, strict single-player origin, world generation hook coverage, or exception ownership recovery is claimed.",
            "Optional console pre-callback2357b50 and complete console eligibility lifecycle are not closed here; a direct handler is not declared equivalent to console execution.",
        ],
    }


def encoded(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode("ascii")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    report = make_report()
    payload = encoded(report)
    path = HERE / "report.json"
    if args.check:
        if path.read_bytes() != payload:
            raise SystemExit("Report differs from bounded disk recomputation")
    else:
        with path.open("xb") as stream:
            stream.write(payload)
    print(json.dumps({"check": args.check, "path": str(path.relative_to(ROOT)),
                      "sha256": hashlib.sha256(payload).hexdigest(), "bounds": report["bounds"],
                      "runtime_verified": False, "native_called": False}, sort_keys=True))


if __name__ == "__main__":
    main()
