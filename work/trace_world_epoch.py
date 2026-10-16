"""Exact-build, bounded, disk-only world identity invalidation research.

No process access, native calls, hooks, requests, or production capability edits.
Direct E8/E9 and selected RIP-store scans are finite pattern searches, not an
assertion that arbitrary indirect branches or all stores have been recovered.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg

ROOT = Path(__file__).resolve().parents[1]
OLD_REPORT = ROOT / "work/reports/native-world-lifecycle-1375.json"
OLD_SHA = "1f0bb0398c6bb28da9bdbd92fb2c827c67883ed30c3185b3453718a6c25a0ce1"
TARGETS = (0x5cf740, 0x74a260, 0x749020, 0x74bf70, 0x74dd50, 0x74d890,
           0x74b8a0, 0x210000, 0x826c20, 0x2e1a30, 0x286250, 0x2830a0, 0x75d1e0, 0x74e8e0)
ENTRIES = TARGETS + (0x5cdc60, 0x777130, 0x74c080, 0x74c8b0, 0x207310,
                    0x1fefa0, 0x112aba0, 0x5d0580, 0x74b330, 0xd84b80, 0x1adfdf0,
                    0x481f90, 0x28a9d0, 0x112fd10, 0x1131470)
MAX_DECODE = 192 * 1024


def fact(summary, *rvas, **extra):
    return {"summary": summary, "evidence_rvas": [hex(x) for x in rvas], "runtime_verified": False, **extra}


FACTS = {
    "load_helper_is_not_universal": fact(
        "5cf740 has one validated direct caller5cdc60, which packs a temporary game/source/result context. "
        "It clears game+15d0/+1b40 before calling74a260 and then parses gamestate. "
        "74a260 also has direct callers749020 and74bf70, both bypassing5cf740. "
        "Thus5cf740 is a deserialization helper, not a demonstrated authority for all world teardown.",
        0x5cdc78, 0x5cdc7c, 0x5cdc80, 0x5cdd58, 0x5cf765, 0x5cf76f, 0x5cf77e, 0x5cf7a1,
        0x5cfe87, 0x7491c7, 0x74bfc6, universal_boundary=False),
    "reset_changes_identity_before_reading_save": fact(
        "5d0580 can invoke826c20 before its later74b8a0 call. 826c20 labels itself ResetGamestate and calls210000. "
        "210000 labels itself ResetGame, invokes the current game virtual destructor with delete=1, "
        "writes global233fe78=null, and calls74c080 to allocate/publish a new game. It then rebuilds country definitions and objects "
        "via207310/2830a0 before invoking749020. Therefore74b8a0 alone is too late for this outer-reset load path; "
        "a destructor/earlier-reset invalidation must already have fired.",
        0x5d0a15, 0x5d0a22, 0x5d0a2f, 0x5d0c78, 0x826c7d, 0x826f94,
        0x210201, 0x2102fb, 0x21030f, 0x210318, 0x21031b, 0x21031d, 0x210324,
        0x2103d3, 0x210401, 0x74c094, 0x74c0a9, 0x74c0b5, 0x74c156, 0x207752),
    "common_clear_and_preserved_country_storage": fact(
        "74a260 calls777130 before setting transient reset flag game+7485. It later loops game+1ce8 using virtual+40 count "
        "and calls2e1a30 on each country. 2e1a30 directly references CCountry::Clear(), clears relation storage through "
        "country+14f8 helper28a9d0, clears existing envoy-holder state via6ff110, and overwrites overlord+18f0. "
        "This is in-place logical invalidation: stable country/game addresses and unchanged TAG/date are insufficient. "
        "A hook at flag7485's store or after successful parsing is later than the first child replacements.",
        0x74a284, 0x74a289, 0x74ad81, 0x74ad87, 0x74ad92, 0x74ad99, 0x74ad9d,
        0x2e1a77, 0x2e3522, 0x2e352b, 0x2e352f, 0x2e35b6, 0x2e35bd, 0x2e3698,
        0x28aa20, 0x28aa6e, 0x777232, 0x777239, 0x77724d),
    "reinitialize_entry_precedes_server_unbinding": fact(
        "749020 clears game+1e00 (server binding), loaded/reset state and then invokes74a260. "
        "Afterward it passes database+110 into74e8e0, which clears/rebuilds game+1ce8 country pointers from database+118 "
        "and invokesCCountry::Clear() again. Hooking749020 entry precedes this server unbinding and country state destruction; "
        "hooking74a260 alone would miss the earlier server-binding write.",
        0x749192, 0x749199, 0x7491a0, 0x7491c7, 0x749207, 0x749211,
        0x74e913, 0x74e91d, 0x74e9f0, 0x74e9f4, 0x74e9fb, 0x74ea0d),
    "derived_game_destructor_precedes_common_clear": fact(
        "Runtime game vtable1cb00c8 slot0 is74bf70. The deleting destructor installs that vtable, "
        "obtains the existing server context and clears context+830/+838 before74a260. It then calls74dd50 "
        "and conditionally frees0x7518 bytes.74bf70 entry must invalidate before those context writes; "
        "neither74a260 nor74dd50 alone is an early boundary for the whole object.",
        0x74bf7f, 0x74bf86, 0x74bf98, 0x74bfad, 0x74bfb5, 0x74bfbc, 0x74bfc6,
        0x74bff2, 0x74bff8, 0x74bffe, 0x74c006),
    "base_game_and_country_database_destruction": fact(
        "Base game vtable1cb0020 slot0 is74d890, which directly calls74dd50 before optionally freeing0x7478 bytes. "
        "74dd50 changes the vtable and destroys a child at+1e58, then calls286250 on global country database233d8d0, "
        "frees the database and writes its global pointer null.286250 iterates contiguous country storage+108 in0x9b78-byte "
        "strides through2cbf20, frees that block, zeroes its pointer/count, then frees and zeroes lookup array+118. "
        "The base-destructor path bypasses74a260, so a base cleanup entry backstop is required even if normal live games use the derived table.",
        0x74d89f, 0x74d8a9, 0x74dd67, 0x74dd6e, 0x74dd85, 0x74dd93,
        0x74ddc3, 0x74ddd0, 0x74ddd7, 0x286280, 0x286290, 0x2862a3,
        0x2862b1, 0x2862c7, 0x2862cc, 0x2862d3, 0x28644d, 0x286459, 0x28645e),
    "country_array_creation_rebinds_identity": fact(
        "2830a0 references CountryDatabase Create Countries. It allocates0x9b78*count bytes into database+108, "
        "constructs countries via2c9960, and populates database+118 with their addresses. "
        "Each is then cleared via2e1a30. Known direct callers are startup208620 and after-reset207310; "
        "these caller observations do not prove no indirect or alternate world-construction path exists.",
        0x283128, 0x28313e, 0x283143, 0x28314a, 0x2831b2, 0x2831ec,
        0x283291, 0x283298, 0x28329e, 0x2832a1, 0x2832a8, 0x283472),
    "country_clear_is_not_itself_a_world_epoch": fact(
        "2e1a30 also has two calls within75d1e0, reached by481f90. The latter references dynamiccountries.cpp, "
        "client_vassal/crown_colony and NEWCOLONIALCOUNTRY/NEWCLIENTCOUNTRY. This is concrete evidence of ordinary "
        "dynamic-country creation sharing country reset machinery. A global epoch on everyCCountry::Clear could revoke "
        "an otherwise unchanged game session during normal play. Per-country incarnation invalidation may still be necessary; "
        "do not count these calls as full-world reloads or suppress them without identity policy.",
        0x75d2f1, 0x75d39c, 0x48204d, 0x4820c0, 0x482138, 0x48265a, 0x48329c, 0x483337),
    "shutdown_and_setup_reset_paths": fact(
        "Application cleanup1fefa0 invokes the current game virtual destructor and then writes global233fe78=null. "
        "Setup callback112aba0 has two direct210000 calls and later uses REVERT_SAVE_CAL; it is also stored as an "
        "absolute code pointer in rdata1d5e408. Its exact UI callback binding/reachability is not closed here. "
        "These paths establish teardown/reinitialization sites without asserting every return-to-menu/new-game UI action shares them.",
        0x1ff05f, 0x1ff06b, 0x1ff072, 0x1ff07a, 0x1ff07c,
        0x112ac0c, 0x112aca1, 0x112af59),
    "failed_parse_keeps_old_session_revoked": fact(
        "5cf740 clears before reaching14e4240 at5cfa11/5cfc4c/5cfe87. Its failure text and result=false are after mutation. "
        "A reset/load hook must revoke at entry regardless of later success or failure and must not rearm on return. "
        "The RNW rejection helpers112fd10/1131470 additionally contain indirect callbacks not resolved here; their logs alone "
        "are not proof of world mutation or of safe return to the same world.",
        0x5cf7a1, 0x5cfa11, 0x5cfc4c, 0x5cfe87, 0x5cfec1, 0x5d0175,
        0x112fe78, 0x11315c9),
    "load_failure_timing_is_not_uniform": fact(
        "5d0580 tests its file/source object before resetting; the null branch returns2 without reaching826c20. "
        "A later return3 can be reached after the826c20 reset when the server/source branch is taken. These are distinct timing cases: not every load error proves "
        "world mutation, and failure after reset cannot restore an earlier authorization. This does not classify every error path.",
        0x5d09fb, 0x5d09fe, 0x5d0a00, 0x5d0a1c, 0x5d0a2f, 0x5d0c4f, error_path_coverage_complete=False),
}


def generate(exe, deps):
    check_memory_budget()
    pe = PE(exe)
    if hashlib.sha256(pe.data).hexdigest() != SHA:
        raise ValueError("Unsupported executable SHA-256")
    if OLD_REPORT.stat().st_size > 2 * 1024 * 1024 or hashlib.sha256(OLD_REPORT.read_bytes()).hexdigest() != OLD_SHA:
        raise ValueError("Prior lifecycle report changed")
    md, cs = make_disassembler(deps)
    if md is None:
        raise ValueError("Capstone unavailable")
    cache, functions, lookup = {}, {}, {}
    decoded = 0

    def decode(entry):
        nonlocal decoded
        if entry in cache:
            return cache[entry]
        if len(cache) >= 64:
            raise ValueError("Function-count budget exceeded")
        code, edges = bounded_cfg(pe, md, entry, window=0x4000, max_instructions=4000)
        decoded += sum(i.size for i in code)
        if decoded > MAX_DECODE:
            raise ValueError("Decode budget exceeded")
        cache[entry] = {i.address: i for i in code}
        rows = [{"rva": hex(i.address), "bytes": i.bytes.hex(), "instruction": f"{i.mnemonic} {i.op_str}".strip()} for i in code]
        lookup.update({int(r["rva"], 16): r for r in rows})
        functions[hex(entry)] = {"prefix32": pe.bytes_at(entry, 32).hex(), "instructions": rows, "edges": edges}
        check_memory_budget()
        return cache[entry]

    for entry in sorted(set(ENTRIES)):
        decode(entry)
    refs = {hex(target): [] for target in TARGETS}
    candidates = 0
    for section in pe.sections:
        if not section["flags"] & 0x20000000:
            continue
        for match in re.finditer(b"[\xe8\xe9]", pe.data[section["raw"]:section["raw"] + section["size"]]):
            offset = section["raw"] + match.start()
            if offset + 5 > section["raw"] + section["size"]:
                continue
            site = pe.to_rva(offset)
            target = site + 5 + struct.unpack_from("<i", pe.data, offset + 1)[0]
            if target not in TARGETS:
                continue
            candidates += 1
            if candidates > 256:
                raise ValueError("Direct-reference candidate budget exceeded")
            function = pe.function(site)
            instruction = decode(function[0]).get(site) if function else None
            verified = bool(instruction and instruction.mnemonic in ("call", "jmp") and instruction.operands[0].type == cs.CS_OP_IMM and instruction.operands[0].imm == target)
            refs[hex(target)].append({"site": hex(site), "function": hex(function[0]) if function else None,
                "instruction_verified": verified, "bytes": instruction.bytes.hex() if verified else pe.bytes_at(site, 5).hex()})
    stores = []
    pattern = re.compile(rb"[\x48-\x4f]\x89[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]....|\x48\xc7\x05........", re.S)
    for section in pe.sections:
        if not section["flags"] & 0x20000000:
            continue
        for match in pattern.finditer(pe.data, section["raw"], section["raw"] + section["size"]):
            site = pe.to_rva(match.start())
            target = site + len(match.group()) + struct.unpack_from("<i", match.group(), 3)[0]
            if target != 0x233fe78:
                continue
            function = pe.function(site)
            instruction = decode(function[0]).get(site) if function else None
            if instruction is None:
                raise ValueError("Unvalidated candidate global game store")
            stores.append({**lookup[site], "function": hex(function[0]), "target_rva": hex(target)})
    if {int(r["rva"], 16) for r in stores} != {0x1ff07c, 0x21031d, 0x74c156}:
        raise ValueError("Reviewed global-store set changed")
    pins = []
    for table, slot, target in ((0x1cb00c8, 0, 0x74bf70), (0x1cb0020, 0, 0x74d890)):
        if pe.u64(pe.to_offset(table + slot)) - pe.base != target:
            raise ValueError("Game destructor vtable mismatch")
        pins.append({"vtable_rva": hex(table), "slot": hex(slot), "target_rva": hex(target)})
    if pe.u64(pe.to_offset(0x1d5e408)) - pe.base != 0x112aba0:
        raise ValueError("Setup callback pointer mismatch")
    literals = []
    for site, expected in ((0x210201, "ResetGame"), (0x826c7d, "ResetGamestate, %d"),
                           (0x2e1a77, "CCountry::Clear() %s"), (0x283472, "CountryDatabase Create Countries ["),
                           (0x112af59, "REVERT_SAVE_CAL"), (0x48329c, "NEWCOLONIALCOUNTRY"), (0x483337, "NEWCLIENTCOUNTRY")):
        instruction = next(c[site] for c in cache.values() if site in c)
        targets = [instruction.address + instruction.size + op.mem.disp for op in instruction.operands if op.type == cs.CS_OP_MEM and op.mem.base == cs.x86_const.X86_REG_RIP]
        if len(targets) != 1 or pe.bytes_at(targets[0], len(expected) + 1) != expected.encode() + b"\0":
            raise ValueError("Reviewed literal mismatch at " + hex(site))
        literals.append({"site": hex(site), "target_rva": hex(targets[0]), "literal": expected})
    facts = json.loads(json.dumps(FACTS))
    for key, value in facts.items():
        if any(int(r, 16) not in lookup for r in value["evidence_rvas"]):
            raise ValueError("Missing instruction anchor in " + key)
        value["evidence_instructions"] = [lookup[int(r, 16)] for r in value["evidence_rvas"]]
    hooks = [
        {"entry_rva": "0x74b8a0", "role": "direct in-place load before game+74c8/server rebind and any5cf740 cleanup", "abi_candidate": "RCX=game, RDX=load_source"},
        {"entry_rva": "0x749020", "role": "reinitialize before game+1e00 server unbinding and common reset", "abi_candidate": "RCX=game"},
        {"entry_rva": "0x74bf70", "role": "derived game destructor before context+830/+838 clear, common reset and base destruction", "abi_candidate": "RCX=game, EDX=deleting-destructor flags"},
        {"entry_rva": "0x74dd50", "role": "base cleanup backstop including74d890 path that bypasses common reset", "abi_candidate": "RCX=base game"},
    ]
    for hook in hooks:
        hook.update(prefix32=pe.bytes_at(int(hook["entry_rva"], 16), 32).hex(), runtime_verified=False, hook_installation_verified=False)
    return {"schema_version": 1, "analysis_kind": "bounded_static_world_epoch_boundary_candidates", "game_sha256": SHA,
        "runtime_verified": False, "execution_verified": False, "production_ready": False,
        "inputs": [{"path": OLD_REPORT.relative_to(ROOT).as_posix(), "sha256": OLD_SHA}],
        "facts": facts, "direct_references": refs, "game_global_store_candidates": stores,
        "vtable_checks": pins, "setup_callback_pointer": {"slot_rva": "0x1d5e408", "target_rva": "0x112aba0"},
        "literal_checks": literals, "functions": functions,
        "candidate_cut": {"scope": "small entry cut for the explicitly reviewed live-game load/reinitialize/derived-destruction/base-destruction graph",
            "hooks": hooks, "small_candidate_entry_set_only": True, "minimality_proven": False,
            "global_minimality_proven": False,
            "universal_coverage_proven": False, "replacement_for_process_creation_identity": False,
            "reason_not_only_5cf740": "common reset and deleting/base destructor paths bypass it",
            "reason_not_only_74a260": "earlier load-child cleanup/server unbinding/context writes and base teardown bypass",
            "optional_observation_backstops": ["0x210000 ResetGame for phase labels and earlier outer cancellation", "0x74a260 common reset for unexpected direct/indirect invocation", "0x286250 country database destruction for unexpected ownership paths"],
            "do_not_treat_as_global_epoch": ["0x2e1a30 CCountry::Clear also runs in dynamic-country creation", "transient game+7485 flag", "stable game/country pointers or dates"]},
        "path_matrix": [
            {"path": "in-place successful or failed gamestate parse", "chain": ["74b8a0", "5cdc60", "5cf740", "74a260", "2e1a30", "14e4240"], "candidate_boundary": "74b8a0", "static_path_verified": True},
            {"path": "outer reset preceding load", "chain": ["5d0580", "826c20", "210000", "game.vt[0]=74bf70", "74dd50", "286250", "74c080", "207310", "2830a0"], "candidate_boundary": "74bf70", "static_path_verified": True},
            {"path": "reinitialize country view", "chain": ["749020", "74a260", "74e8e0", "2e1a30"], "candidate_boundary": "749020", "static_path_verified": True},
            {"path": "application cleanup", "chain": ["1fefa0", "game.vt[0]=74bf70", "74a260", "74dd50", "286250"], "candidate_boundary": "74bf70", "static_path_verified": True},
            {"path": "base game destruction", "chain": ["basegame.vt[0]=74d890", "74dd50", "286250"], "candidate_boundary": "74dd50", "static_path_verified": True},
            {"path": "setup revert callback", "chain": ["112aba0", "210000", "game.vt[0]=74bf70"], "candidate_boundary": "74bf70", "static_path_verified": True, "exact_ui_binding_verified": False},
            {"path": "normal dynamic-country creation", "chain": ["481f90", "75d1e0", "2e1a30"], "candidate_boundary": None, "static_path_verified": True, "whole_world_transition": False},
        ],
        "remaining_gaps": [
            "The precise UI callback/vtable dispatch for every New Game, Return to Menu and RNW/error callback is not closed;112aba0's stored pointer and indirect calls in112fd10/1131470 require binding before universal UI coverage is claimed.",
            "Direct relative-call and selected RIP-mov store coverage does not cover computed function pointers, alternate instruction encodings, bulk copies, all exception/unwind paths or unreviewed networking/resynchronization.",
            "No runtime hook coverage, trampoline/relocation, reentrancy, cross-thread ordering or SEH behavior has been verified. Prefix pins are not installation code.",
            "Session/context origin can change without world teardown; combine separate811ab0/14c9930/14cd8b0 provenance invalidation evidence. This report does not replace strict SP provenance.",
            "Ordinary dynamic-country reuse needs a per-country incarnation policy. Raw TAG/full-handle equality alone is not proven to prevent logical identity reuse after Clear.",
        ],
        "epoch_contract": {"ownership": "adapter-owned atomic monotonic counter, never write a counter into native game flags",
            "at_entry": "increment and permanently revoke the armed session before original code; duplicate/nested hits may increment again",
            "failure_policy": "failed load, callback exception, missing audit or wraparound remain revoked; do not rearm on return",
            "fresh_authorization": "new observed world identities, current thread, strict mode provenance and explicit new handshake required",
            "native_generation_counter_identified": False, "verified_epoch_in_production": False},
        "limits": {"function_window_bytes": 0x4000, "max_instructions_per_function": 4000, "max_functions": 64,
            "max_direct_candidates": 256, "total_decode_limit_bytes": MAX_DECODE, "memory_guard_mib": 768,
            "function_count": len(functions), "decoded_bytes_including_overlaps": decoded, "direct_candidates": candidates,
            "automatic_recursive_callee_traversal": False}}


def render_docs(report):
    digest = hashlib.sha256((json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()).hexdigest()
    return "\n".join([
        "# 1.37.5 世界身份撤销边界增量", "",
        "`5cf740` 不是统一世界清理入口。它只闭合读档解析 helper；重置、game 析构与 base game 析构有其他路径。本轮将游戏和国家数据库的销毁/重建链静态对应起来，给出有限路径集合上的 4 个入口候选。仍未证明所有界面/联网/异常路径覆盖，也没有安装或实测 epoch hook。", "",
        f"EXE SHA-256 `{SHA}`；机器报告 SHA-256 `{digest}`。全部 runtime_verified/execution_verified/production_ready=false。只读磁盘，不访问游戏进程、不修改冻结源、DLL 或目录。", "",
        "复现：`python -B work/trace_world_epoch.py --check`。每函数 16 KiB / 4,000 条指令，最多 64 函数，总解码 192 KiB，768 MiB 内存保护；不递归追所有调用。", "",
        "## 证据改变了什么", "",
        "1. `5cf740` 的唯一已验证直接调用来自 `5cdc60`；共享清理 `74a260` 还有 `749020` 和 `74bf70` 两个直接调用者。只在 `5cf740` 撤销会话会漏这些路径。",
        "2. 外层 `5d0580 → 826c20 → 210000` 明确使用 ResetGamestate / ResetGame 字符串。`210000` 在随后读档前已通过 game 虚析构销毁旧对象、把全局 `233fe78` 清零、重新构造 game 与国家数据库。因此只在 `74b8a0` 撤销也可能晚于旧世界销毁。",
        "3. runtime game 虚表 `1cb00c8` 的槽 0 是 `74bf70`。该析构在 `74a260` 之前就清 context+830/+838，随后进入 `74dd50`。base 虚表 `1cb0020` 的槽 0 是 `74d890`，直接进入 `74dd50`，绕过 `74a260`。",
        "4. `74dd50 → 286250` 确实析构连续国家存储（每项 0x9b78），释放 database+108 和 lookup+118，清空指针/计数，释放数据库并清零全局 `233d8d0`。`2830a0` 随后分配国家块、构造国家和重新填充 lookup。",
        "5. `74a260` 还会在原有国家地址上调用 `2e1a30`；其日志字符串是 `CCountry::Clear()`。该函数清外交关系存储、外交官 holder 状态及宗主句柄。指针、TAG、日期相同不能证明世界未变。", "",
        "## 有限已审查路径上的入口集合", "",
        "| 候选入口 | 必须先撤销的原因 |", "| --- | --- |",
        *[f"| `{h['entry_rva']}` | {h['role']} |" for h in report["candidate_cut"]["hooks"]], "",
        "这 4 个点是针对本报告明确路径族的较小入口截断集合，不是全程序最小性或通用覆盖证明。`210000` 可另作更早外层重置观察；`74a260`、`286250` 可作异常来源的观察后备。重复进入只需再次撤销，不能在退出时恢复旧授权。", "",
        "`749020` 在 common clear 前已经写 game+1e00=null；`5cf740` 在 common clear 前已清其他 game 子对象。故把所有状态变化统一延后到 `74a260` 也不成立。前缀字节只用于构建钉扎，尚未审查 trampoline、指令搬迁、重入、线程/异常与安装生命周期。", "",
        "## 不应把正常国家创建当成读档", "",
        "`2e1a30` 的另两个调用在 `75d1e0`，来自 `481f90`。后者直接引用 dynamiccountries.cpp、client_vassal/crown_colony、NEWCOLONIALCOUNTRY/NEWCLIENTCOUNTRY，说明普通动态国家创建共用 Clear。不能直接在每次 Clear 上计全世界 epoch 后宣称所有命中都是读档；这还需要单独的国家 incarnation 策略，或接受保守撤销造成的额外中断。", "",
        "## 仍未覆盖的具体点", "",
        *["- " + gap for gap in report["remaining_gaps"]], "",
        "对 global game 指针的有限 RIP-mov 扫描找到且验证 3 处写入：1ff07c（应用清理置空）、21031d（ResetGame 置空）、74c156（新对象发布）。这不是全部可能写法或间接写的穷尽证明。setup 的 112aba0 两条分支都进入 ResetGame，但尚未完整绑定每个 UI 按钮；不能据 REVERT_SAVE_CAL 文案就称“返回菜单全部覆盖”。", "",
        "同样，RNW 两个错误 helper 的字符串只证明拒绝/错误分支存在；其中间接回调仍未解析，不能仅凭出现日志判定有没有破坏世界。已闭合的 gamestate 解析失败则明确发生在清理之后，因此失败也必须保持撤销。", "",
        "外层加载器的失败时序也不同：`5d0580` 的空文件/source 分支在这里的 `826c20` 调用前返回 2；server/source 分支经过该重置后仍可能返回 3。返回码 3 本身也不证明重置分支必定执行；不能从任意“加载失败”文案推断它是否经过撤销边界。候选入口一旦命中则始终保持撤销。", "",
        "## 下一步的有限验收", "",
        "先仅安装观察/撤销逻辑，按同存档重复加载、成功/失败加载、setup revert、返回菜单/新局和进程退出逐项核对入口命中顺序，确保旧请求不能在第一次破坏前继续消费。另把 context setter/reinitialize/transport 变化纳入 SP provenance 失效。需要新握手才能重新授权；本报告没有把这些候选提升成生产 gate。", "",
        f"本轮解码 {report['limits']['function_count']} 个有界函数、{report['limits']['decoded_bytes_including_overlaps']} 字节（含重叠）。", ""])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=ROOT.parent / "eu4.exe")
    parser.add_argument("--deps", type=Path, default=Path(os.environ.get("TEMP", ".")) / "eu4-native-analysis-deps")
    parser.add_argument("--output", type=Path, default=ROOT / "work/reports/native-world-epoch-1375.json")
    parser.add_argument("--docs", type=Path, default=ROOT / "docs/native-world-epoch-1375.md")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    report = generate(args.exe, args.deps)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    products = {args.output: payload, args.docs: render_docs(report)}
    stale = []
    for path, content in products.items():
        raw = content.encode("utf-8")
        if args.check:
            if not path.is_file() or path.read_bytes() != raw:
                stale.append(path.name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    print(json.dumps({"mode": "check" if args.check else "write", "report_sha256": hashlib.sha256(payload.encode()).hexdigest(),
        "bytes": len(payload.encode()), "limits": report["limits"], "stale": stale}))
    return int(bool(stale))


if __name__ == "__main__":
    raise SystemExit(main())
