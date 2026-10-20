"""Bounded, read-only native diplomacy inventory for an explicitly selected EU4 PE.

No process attachment, injection, executable writes, or imported historical RVAs.
Only the Python standard library is required for inventory. Install capstone for
instruction-validated references and bounded disassembly (--deps-dir supported).
The inventory is evidence, never an authorization to call a native address.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import re
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path


class PE:
    def __init__(self, path: Path):
        if path.stat().st_size > 128 * 1024 * 1024:
            raise ValueError("Refusing PE larger than 128 MiB (analysis memory budget)")
        self.path = path
        self.data = path.read_bytes()
        pos = self.u32(0x3C)
        if self.data[pos:pos + 4] != b"PE\0\0" or self.u16(pos + 4) != 0x8664:
            raise ValueError("Expected x64 PE")
        opt = pos + 24
        if self.u16(opt) != 0x20B:
            raise ValueError("Expected PE32+")
        self.base = self.u64(opt + 24)
        self.sections = []
        for i in range(self.u16(pos + 6)):
            h = opt + self.u16(pos + 20) + i * 40
            vs, rva, size, raw = struct.unpack_from("<IIII", self.data, h + 8)
            self.sections.append(dict(name=self.data[h:h + 8].rstrip(b"\0").decode("ascii"),
                                      rva=rva, raw=raw, size=size, virtual_size=vs,
                                      flags=self.u32(h + 36)))
        self.functions = []
        for s in self.sections:
            if s["name"] == ".pdata":
                for off in range(s["raw"], s["raw"] + s["size"] - 11, 12):
                    start, end, unwind = struct.unpack_from("<III", self.data, off)
                    if 0 < start < end:
                        self.functions.append((start, end, unwind))
        self.functions.sort()
        self.starts = [f[0] for f in self.functions]

    def u16(self, off):
        return struct.unpack_from("<H", self.data, off)[0]

    def u32(self, off):
        return struct.unpack_from("<I", self.data, off)[0]

    def u64(self, off):
        return struct.unpack_from("<Q", self.data, off)[0]

    def to_rva(self, off):
        for s in self.sections:
            if s["raw"] <= off < s["raw"] + s["size"]:
                return s["rva"] + off - s["raw"]
        return None

    def to_offset(self, rva):
        for s in self.sections:
            if s["rva"] <= rva < s["rva"] + s["size"]:
                return s["raw"] + rva - s["rva"]
        return None

    def executable(self, rva):
        return any(s["rva"] <= rva < s["rva"] + s["size"]
                   and s["flags"] & 0x20000000 for s in self.sections)

    def function(self, rva):
        i = bisect.bisect_right(self.starts, rva) - 1
        return self.functions[i] if i >= 0 and rva < self.functions[i][1] else None

    def bytes_at(self, rva, size):
        off = self.to_offset(rva)
        return self.data[off:off + size] if off is not None else b""


def hx(value):
    return None if value is None else hex(value)


def check_memory_budget():
    """Stop this analysis process well below the workspace's 1 GiB limit."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    handle = ctypes.windll.kernel32.GetCurrentProcess
    handle.restype = wintypes.HANDLE
    get_info = ctypes.windll.psapi.GetProcessMemoryInfo
    get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    get_info.restype = wintypes.BOOL
    if get_info(handle(), ctypes.byref(counters), counters.cb):
        if counters.PagefileUsage > 768 * 1024 * 1024:
            raise MemoryError("Stopped analysis at 768 MiB committed-memory guard")
        return counters.PeakPagefileUsage
    return None


def script_actions(root: Path):
    """Read explicit legacy names and static registration only; no guessed keys."""
    result = defaultdict(list)
    p = root / "common/diplomatic_actions/00_diplomatic_actions.txt"
    if p.exists():
        text = p.read_text(encoding="utf-8-sig")
        for no, line in enumerate(text.splitlines(), 1):
            m = re.match(r"^# ([a-z][a-z_]+)$", line)
            if m and no > 15:
                result[m[1]].append(dict(path=p.relative_to(root).as_posix(), line=no,
                                         evidence="legacy_header"))
            m = re.match(r"^([a-z][a-z_]+)\s*=\s*\{", line)
            if m:
                result[m[1]].append(dict(path=p.relative_to(root).as_posix(), line=no,
                                         evidence="legacy_definition"))
    p = root / "common/new_diplomatic_actions/00_diplomatic_actions.txt"
    if p.exists():
        text = p.read_text(encoding="utf-8-sig")
        inside = False
        for no, line in enumerate(text.splitlines(), 1):
            if line.startswith("static_actions"):
                inside = True
                continue
            if inside and line.startswith("}"):
                break
            m = re.match(r"\s*([a-z][a-z_]+)\s*=\s*\{", line)
            if inside and m:
                result[m[1]].append(dict(path=p.relative_to(root).as_posix(), line=no,
                                         evidence="static_registration"))
    return dict(result)


def make_disassembler(deps_dir):
    if deps_dir:
        sys.path.insert(0, str(deps_dir))
    try:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        md.detail = True
        return md, capstone
    except ImportError:
        return None, None


def rip_references(pe, targets):
    """One bounded byte-pattern pass; evidence remains candidate until decoded."""
    refs = defaultdict(list)
    pattern = re.compile(rb"[\x40-\x4f]?[\x8d\x8b][\x05\x0d\x15\x1d\x25\x2d\x35\x3d]....", re.S)
    for s in pe.sections:
        if not s["flags"] & 0x20000000:
            continue
        for m in pattern.finditer(pe.data, s["raw"], s["raw"] + s["size"]):
            rva = pe.to_rva(m.start())
            target = rva + len(m.group()) + struct.unpack_from("<i", m.group(), len(m.group()) - 4)[0]
            if target in targets:
                f = pe.function(rva)
                refs[target].append(dict(instruction_rva=hx(rva),
                                         function_range=[hx(f[0]), hx(f[1])] if f else None,
                                         evidence="rip_byte_pattern_candidate"))
    return refs


def disassemble(pe, md, rva, max_bytes=0x10000):
    f = pe.function(rva)
    if f:
        start, end = f[:2]
        if end - start > max_bytes:
            return None
    else:
        # Leaf functions may have no unwind entry. Stop at the first return.
        start, end = rva, rva + min(max_bytes, 0x100)
    out = []
    for ins in md.disasm(pe.bytes_at(start, end - start), start):
        out.append(ins)
        if not f and ins.mnemonic in ("ret", "retf", "int3"):
            break
    return out


def validate_refs(pe, md, refs):
    # A cache stores only instruction addresses, never whole-program decoding.
    cache = {}
    decoded_bytes = 0
    for target_refs in refs.values():
        for ref in target_refs:
            rva = int(ref["instruction_rva"], 16)
            f = pe.function(rva)
            key = f[0] if f else rva
            if key not in cache:
                check_memory_budget()
                if decoded_bytes > 16 * 1024 * 1024:
                    ref["decode_limit"] = True
                    continue
                insns = disassemble(pe, md, rva)
                decoded_bytes += sum(i.size for i in insns or [])
                cache[key] = {i.address: (i.mnemonic, i.op_str) for i in insns or []}
            if rva in cache[key]:
                mnemonic, operands = cache[key][rva]
                ref.update(evidence="instruction_boundary_validated", mnemonic=mnemonic,
                           operands=operands)
    return decoded_bytes


def locate_rtti_vtables(pe, rtti):
    """Validate x64 COL self RVAs before following them to vtable prefixes."""
    types = {int(r["type_descriptor_rva"], 16): r for r in rtti
             if r["type_descriptor_rva"] is not None}
    locators = {}
    for s in pe.sections:
        if s["flags"] & 0x20000000 or not s["flags"] & 0x40000000:
            continue
        for off in range(s["raw"], s["raw"] + s["size"] - 23, 4):
            if pe.u32(off) != 1:
                continue
            signature, adjustment, cd_offset, type_rva, hierarchy, self_rva = struct.unpack_from(
                "<IIIIII", pe.data, off)
            if type_rva in types and self_rva == pe.to_rva(off) and pe.to_offset(hierarchy) is not None:
                locators[self_rva] = dict(rva=hx(self_rva), object_adjustment=adjustment,
                                          constructor_displacement=cd_offset,
                                          hierarchy_rva=hx(hierarchy), vtable_rvas=[])
                types[type_rva].setdefault("complete_object_locators", []).append(locators[self_rva])
    if not locators:
        return
    for s in pe.sections:
        if s["flags"] & 0x20000000:
            continue
        for off in range(s["raw"], s["raw"] + s["size"] - 15, 8):
            col = pe.u64(off) - pe.base
            if col in locators and pe.executable(pe.u64(off + 8) - pe.base):
                locators[col]["vtable_rvas"].append(hx(pe.to_rva(off + 8)))


def token_vtable_inventory(pe, md, script_names):
    """Discover Clausewitz integer token accessors, then infer their table slot.

    This is separate from MSVC RTTI: the engine serializes integer identifiers.
    A descriptor/name is only retained when its integer has a strict immediate
    return accessor and that accessor occurs in a static function-pointer table.
    """
    if md:
        import capstone as cs
    tokens = {}
    for s in pe.sections:
        if s["name"] != ".data":
            continue
        for m in re.finditer(rb"[a-z][a-z0-9_]{2,100}\x00", pe.data[s["raw"]:s["raw"] + s["size"]]):
            off = s["raw"] + m.start()
            identifier = pe.u32(off - 4)
            if 0 < identifier < 0x10000 and pe.data[off + len(m.group()):off + len(m.group()) + 16] == bytes(16):
                tokens[identifier] = dict(name=m.group()[:-1].decode(), token_id=identifier,
                                          descriptor_rva=hx(pe.to_rva(off - 4)))
    accessors = {}
    for s in pe.sections:
        if not s["flags"] & 0x20000000:
            continue
        for m in re.finditer(rb"\xb8(.{4})\xc3", pe.data[s["raw"]:s["raw"] + s["size"]], re.S):
            identifier = struct.unpack("<I", m[1])[0]
            if identifier in tokens:
                rva = pe.to_rva(s["raw"] + m.start())
                accessors[rva] = dict(**tokens[identifier], accessor_rva=hx(rva),
                                      accessor_bytes=m.group().hex())
    slots = {}
    for s in pe.sections:
        if s["name"] not in (".rdata", "_RDATA"):
            continue
        for off in range(s["raw"], s["raw"] + s["size"] - 7, 8):
            target = pe.u64(off) - pe.base
            if target in accessors:
                slots[pe.to_rva(off)] = accessors[target]
    seed_slots = {r: t for r, t in slots.items() if t["name"] in script_names}
    targets = {r - delta for r in seed_slots for delta in range(0, 0x181, 8)}
    refs = rip_references(pe, targets)
    offset_names = defaultdict(set)
    for slot, token in seed_slots.items():
        for delta in range(0, 0x181, 8):
            if refs.get(slot - delta):
                offset_names[delta].add(token["name"])
    if not offset_names:
        return dict(status="no_accessor_slot_inferred")
    token_slot = max(offset_names, key=lambda delta: len(offset_names[delta]))
    def function_pointer_table(table):
        return all(pe.to_offset(table + delta) is not None
                   and pe.executable(pe.u64(pe.to_offset(table + delta)) - pe.base)
                   for delta in range(0, 0xC0, 8))
    seed_tables = {slot - token_slot: token for slot, token in seed_slots.items()
                   if refs.get(slot - token_slot) and function_pointer_table(slot - token_slot)}
    factory_hits = defaultdict(set)
    for table, token in seed_tables.items():
        for ref in refs[table]:
            if ref["function_range"]:
                factory_hits[int(ref["function_range"][0], 16)].add(token["name"])
    factory_candidates = sorted(factory_hits, key=lambda f: len(factory_hits[f]), reverse=True)
    factory_rva = factory_candidates[0]
    instructions = disassemble(pe, md, factory_rva) if md else None
    direct_tables = {}
    factory_calls = []
    if instructions:
        allocation = None
        for i in instructions:
            if i.mnemonic == "mov" and i.op_str.startswith("ecx, 0x"):
                allocation = int(i.op_str.split(", ")[1], 16)
            if i.mnemonic == "call" and len(i.operands) == 1 and i.operands[0].type == cs.x86.X86_OP_IMM:
                factory_calls.append(dict(call_rva=hx(i.address), target_rva=hx(i.operands[0].imm),
                                           nearest_ecx_immediate=allocation))
            if i.mnemonic == "lea":
                for o in i.operands:
                    if o.type == cs.x86.X86_OP_MEM and o.mem.base == cs.x86.X86_REG_RIP:
                        table = i.address + i.size + o.mem.disp
                        if table + token_slot in slots:
                            direct_tables[table] = dict(reference_rva=hx(i.address),
                                                        nearest_allocation_size_candidate=allocation)
    # Discover the action family by the method shared by all seed tables. The
    # +0x40 slot is descriptive evidence only; runtime signature is not inferred.
    shared = Counter(pe.u64(pe.to_offset(t + 0x40)) - pe.base for t in seed_tables)
    wrapper_rva = shared.most_common(1)[0][0]
    tables = {}
    for slot, token in slots.items():
        table = slot - token_slot
        off = pe.to_offset(table + 0x40)
        if off is not None and pe.u64(off) - pe.base == wrapper_rva and function_pointer_table(table):
            tables[table] = token
    # Annexation/integration specialize command creation. Their factory/name
    # evidence must not be lost merely because one inherited slot is overridden.
    tables.update(seed_tables)
    tables.update({table: slots[table + token_slot] for table in direct_tables})
    table_refs = rip_references(pe, set(tables))
    if md:
        validate_refs(pe, md, table_refs)
    actions = []
    for table, token in sorted(tables.items(), key=lambda item: item[1]["name"]):
        row = dict(**token, vtable_rva=hx(table), token_slot_offset=hx(token_slot),
                   evidence_level="static_vtable_and_token_accessor",
                   references=table_refs.get(table, []), runtime_verified=False,
                   slots={hx(delta): hx(pe.u64(pe.to_offset(table + delta)) - pe.base)
                          for delta in range(0, 0x130, 8)
                          if pe.to_offset(table + delta) is not None})
        if table in direct_tables:
            row["factory_branch"] = direct_tables[table]
        if md:
            clone_rva = int(row["slots"]["0xb0"], 16)
            clone = disassemble(pe, md, clone_rva)
            clone_calls = []
            alloc = None
            source_reads = []
            memory_writes = []
            self_registers = {"rcx"}
            if clone:
                for index, ins in enumerate(clone):
                    if ins.mnemonic == "mov" and ins.op_str.startswith("ecx, 0x"):
                        if index + 1 < len(clone) and clone[index + 1].mnemonic == "call" and alloc is None:
                            alloc = dict(size_bytes=int(ins.op_str.split(", ")[1], 16),
                                         size_instruction_rva=hx(ins.address),
                                         allocator_call_rva=hx(clone[index + 1].address),
                                         allocator_target=clone[index + 1].op_str)
                    if ins.mnemonic == "call":
                        clone_calls.append(dict(rva=hx(ins.address), target=ins.op_str))
                    # This records syntactic evidence, not full alias analysis.
                    # Preserve source aliases initialized from the incoming RCX.
                    if ins.mnemonic in ("mov", "movzx", "movsx") and len(ins.operands) == 2:
                        dst, src = ins.operands
                        if dst.type == cs.x86.X86_OP_REG:
                            dn = ins.reg_name(dst.reg)
                            if src.type == cs.x86.X86_OP_REG and ins.reg_name(src.reg) in self_registers:
                                self_registers.add(dn)
                            else:
                                self_registers.discard(dn)
                        if src.type == cs.x86.X86_OP_MEM and ins.reg_name(src.mem.base) in self_registers:
                            source_reads.append(dict(offset=hx(src.mem.disp), width_bytes=src.size,
                                                     rva=hx(ins.address), instruction=ins.mnemonic + " " + ins.op_str))
                        if dst.type == cs.x86.X86_OP_MEM and ins.reg_name(dst.mem.base) not in ("rsp", "rbp"):
                            memory_writes.append(dict(base_register=ins.reg_name(dst.mem.base),
                                                      offset=hx(dst.mem.disp), width_bytes=dst.size,
                                                      rva=hx(ins.address), instruction=ins.mnemonic + " " + ins.op_str))
            size = alloc["size_bytes"] if alloc else None
            row["clone"] = dict(rva=hx(clone_rva), allocation=alloc,
                                 source_field_reads=source_reads, memory_writes=memory_writes,
                                 calls=clone_calls,
                                 ownership_status="Engine clone/factory allocation observed; destructor slot present. Transfer/free contract requires runtime verification.")
            row["layout"] = dict(allocation_size_candidate=size,
                                  base_layout_only_candidate=size == 0x40,
                                  extension_bytes_candidate=max(size - 0x40, 0) if size is not None else None,
                                  parameters_verified=False,
                                  unsupported_extra_fields="See clone writes at offsets >= 0x40; semantic types and ownership are not yet established.")
        actions.append(row)
    return dict(status="static_family_recovered", token_slot_offset=hx(token_slot),
                slot_inference=[dict(offset=hx(k), distinct_script_names=len(v))
                                for k, v in sorted(offset_names.items(), key=lambda kv: -len(kv[1]))[:8]],
                shared_wrapper_rva=hx(wrapper_rva), factory_rva=hx(factory_rva),
                factory_candidates=[dict(rva=hx(f), distinct_seed_action_refs=len(factory_hits[f]))
                                    for f in factory_candidates[:8]],
                factory_direct_calls=factory_calls, actions=actions,
                unclassified_script_names=sorted(set(script_names) - {x["name"] for x in actions}))


def reviewed_build_semantics(sha256):
    """Human-reviewed bounded instruction evidence, scoped to the exact PE."""
    if sha256 != "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a":
        return {}
    fields = [
        ("actor", 0x10, 8, 0x2931, 0x4E8C84),
        ("original", 0x18, 8, 0x2D87, 0x4E8D10),
        ("recipient", 0x20, 8, 0x2932, 0x4E8D7D),
        ("date", 0x28, 4, 0x284D, 0x4E8B8C),
        ("last_command_date", 0x2C, 4, 0x2A2E, 0x4E8D35),
        ("envoy", 0x30, 4, 0x2AD6, 0x4E8D1F),
        ("type", 0x34, 4, 0xE1, 0x4E8C06),
        ("value", 0x38, 1, 0x3EC, 0x4E8BAC),
        ("id", 0x3C, 4, 0xB, 0x4E8C14),
    ]
    variants = [
        ("break_marriage", "royal_marriage", 0x4EFB30, 0x4F00E1, "BREAKRMDESCR / BREAKRMCURIADESCR"),
        ("revoke_guarantee", "guaranteeaction", 0x522111, 0x522285, "REVOKEGUARANTDESC2 / REVOKEGUARANTNEWDESC"),
        ("stop_improving_relations", "improve_relation", 0x574AD1, 0x574AE8, "CANCEL_IMPROVERELATIONDESC_NEW"),
        ("stop_building_spy_network", "spy_network", 0x585C05, 0x58619F, "CANCEL_BUILDSPYNETWORK_LONG_DESC"),
        ("cancel_vassalization", "vassalaction", 0x51F5A2, 0x51F680,
         "VASSAL_CANCEL_CONFIRM / VASSAL_CANCEL_PRESTIGE; validity 0x51f435..0x51f491 rejects actor subject of recipient via IS_SUBJECT"),
    ]
    positive_variants = [
        ("royal_marriage", 0x4EFB30, 0x4EFB3A, "MARNEWDESC"),
        ("guaranteeaction", 0x522111, 0x52211B, "GUARANTNEWDESC"),
        ("improve_relation", 0x574AD1, 0x574AD6, "IMPROVERELATIONDESC_NEW"),
        ("spy_network", 0x585C05, 0x585C0F, "BUILDSPYNETWORK_LONG_DESC_1"),
        ("vassalaction", 0x51F5A2, 0x51F5AC, "VASSALNEWDESC"),
    ]
    return dict(
        base_fields=[dict(name=name, offset=hx(offset), width_bytes=width, serializer_token_id=token,
                          parse_instruction_rva=hx(rva), evidence="native_token_deserializer")
                     for name, offset, width, token, rva in fields],
        factory_signature_candidate=dict(rva="0x35d210", arguments=["ECX: integer action token", "RDX: scriptable definition pointer; null for native fixed types"],
                                         unknown_token_result="image+0x1fd1ca0 sentinel object, not nullptr",
                                         execution_verified=False),
        initialization_evidence=dict(
            independent_setter_discovered=False,
            method="Engine factory initializes each derived object; native AI callers directly populate the common base.",
            ai_construction_rvas=["0x135df6", "0x135e2f", "0x597c78", "0x597cae"],
            common_initial_values={"0x8": "0x165", "0x10": "actor country handle", "0x18": "actor country handle",
                                   "0x20": "recipient country handle", "0x28": "current game date", "0x2c": "current game date",
                                   "0x30": -1, "0x34": 0, "0x38": True, "0x39": 0, "0x3c": 0},
            warning="No generic executable initializer ABI established. Do not infer parameter-free behavior solely from a 0x40 allocation."),
        static_variants=[dict(source_key=source, native_action_name=native, value=False,
                              direction_verified=True,
                              evidence=[dict(rva=hx(branch), kind="boolean_value_branch", detail="Action +0x38 is compared to zero."),
                                        dict(rva=hx(target), kind="false_branch_localization", detail=labels)],
                              runtime_verified=False) for source, native, branch, target, labels in variants]
            + [dict(source_key=native, native_action_name=native, value=True, direction_verified=True,
                    evidence=[dict(rva=hx(branch), kind="boolean_value_branch", detail="Action +0x38 is compared to zero."),
                              dict(rva=hx(target), kind="true_branch_localization", detail=labels)],
                    runtime_verified=False) for native, branch, target, labels in positive_variants])


def inventory(pe, root, md):
    sources = script_actions(root)
    seeds = set(sources) | {"diplomaticactioncommand", "diplomatic_action", "action",
                            "requestpeace", "set_war_peace_command"}
    strings = []
    for m in re.finditer(rb"[\x20-\x7e]{4,240}\x00", pe.data):
        name = m.group()[:-1].decode("ascii")
        if (name in seeds or "diplomaticaction" in name.lower()
                or name.startswith(".?AV?$CRelationsContainerArray")
                or re.fullmatch(r"[a-z_]*diplomat[a-z_]*command", name)):
            strings.append(dict(value=name, rva=pe.to_rva(m.start()), offset=m.start()))
    rtti = []
    for m in re.finditer(rb"\.\?A[UV][^\x00]{1,240}@@\x00", pe.data):
        name = m.group()[:-1].decode("ascii", errors="replace")
        rtti.append(dict(name=name, name_rva=hx(pe.to_rva(m.start())),
                         type_descriptor_rva=hx(pe.to_rva(m.start() - 16))))
    locate_rtti_vtables(pe, rtti)
    targets = {s["rva"] + delta for s in strings if s["rva"] is not None
               for delta in (0, -4)}
    refs = rip_references(pe, targets)
    decoded = validate_refs(pe, md, refs) if md else 0
    for s in strings:
        s["references"] = refs[s["rva"]]
        s["token_header_candidate_rva"] = hx(s["rva"] - 4)
        s["token_header_references"] = refs[s["rva"] - 4]
        s["rva"] = hx(s["rva"])
        s.pop("offset")
    native_actions = token_vtable_inventory(pe, md, set(sources))
    native_actions.update(reviewed_build_semantics(hashlib.sha256(pe.data).hexdigest()))
    return dict(schema_version=1, analysis_kind="offline_static_only",
                binary=dict(filename=pe.path.name, size_bytes=len(pe.data),
                            sha256=hashlib.sha256(pe.data).hexdigest(), image_base=hx(pe.base),
                            function_table_entries=len(pe.functions)),
                sections=[{k: hx(v) if isinstance(v, int) else v for k, v in s.items()}
                          for s in pe.sections],
                limitations=["No runtime execution, ABI, ownership or cooldown validation.",
                             "Byte-pattern references are candidates unless instruction-boundary validated.",
                             "No historical build addresses are accepted or reused.",
                             "RTTI names may be absent for engine classes; absence is recorded, not guessed."],
                resources=dict(max_pe_bytes=128 * 1024 * 1024, max_function_bytes=0x10000,
                               max_decoded_reference_bytes=16 * 1024 * 1024,
                               actual_decoded_string_reference_bytes=decoded,
                               committed_memory_stop_bytes=768 * 1024 * 1024,
                               peak_committed_bytes=check_memory_budget()),
                scripted_actions=[dict(name=k, sources=v) for k, v in sorted(sources.items())],
                strings=strings, rtti=rtti,
                native_actions=native_actions)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--game-root", type=Path,
                        help="Prefer the unpacked resource root (or installed script root)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deps-dir", type=Path)
    parser.add_argument("--rva", type=lambda s: int(s, 0), action="append",
                        help="Emit bounded function evidence instead of the primary inventory")
    args = parser.parse_args()
    pe = PE(args.exe)
    md, capstone = make_disassembler(args.deps_dir)
    if args.rva:
        if not md:
            parser.error("Bounded disassembly requires capstone")
        rows = []
        for rva in args.rva:
            insns = disassemble(pe, md, rva)
            rows.append(dict(requested_rva=hx(rva),
                             function_range=[hx(x) for x in pe.function(rva)[:2]]
                             if pe.function(rva) else None,
                             instructions=[dict(rva=hx(i.address), bytes=i.bytes.hex(),
                                                mnemonic=i.mnemonic, operands=i.op_str)
                                           for i in insns or []],
                             refused=insns is None))
        report = dict(binary_sha256=hashlib.sha256(pe.data).hexdigest(),
                      analysis_kind="bounded_offline_disassembly", functions=rows)
    else:
        report = inventory(pe, args.game_root or args.exe.parent, md)
        report["disassembler"] = capstone.__version__ if capstone else None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(dict(output=str(args.output), binary_sha256=hashlib.sha256(pe.data).hexdigest(),
                          strings=len(report.get("strings", [])),
                          scripted_actions=len(report.get("scripted_actions", [])),
                          rtti=len(report.get("rtti", []))), ensure_ascii=False))


if __name__ == "__main__":
    main()
