"""Bounded offline proof for peace-component catalog names and script registry.

Reads a pinned executable and installed/unpacked data; never opens a process.
Does not construct a peace offer or establish callable public parameter bindings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from discover_diplomacy import PE, check_memory_budget, make_disassembler
from map_diplomacy_fields import SHA, bounded_cfg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_diplomacy_catalog import LOC, parse_script, scalar, walk

FIELDS_SHA = "cfabb4622b7c82f9e2476a82352f91fa5d0f8ba0f8150e75aac47fb4aeaddc96"
MAX_WINDOW = 0x4000
MAX_INSTRUCTIONS = 3000
MAX_TOTAL_CODE = 128 * 1024
# Public aliases are accepted only when this component's own display virtual
# directly references the already-enumerated localization key.
LABELS = (
    ("peace.give_up_claims", "po_give_up_claim", "PEACE_GIVE_UP_CLAIMS", 0x9B5DB0, 0x9B5DC7),
    ("peace.war_reparations", "po_war_reparations", "WAR_REPARATIONS", 0x9B66D0, 0x9B66DF),
    ("peace.enforce_fleet_basing_rights", "po_enforce_fleet_basing_rights", "ENFORCED_FLEET_BASING_RIGHTS", 0x9C0440, 0x9C044F),
    ("peace.concede_colonial_region", "po_concede_colonial_region", "PEACE_CONCEDE_COLONIAL_REGION", 0x9C8180, 0x9C8255),
    ("peace.end_rivalry", "po_end_rivalry", "PEACE_END_RIVALRY", 0x9CA180, 0x9CA18F),
    ("peace.pillage_capital", "po_pillage_capital_state", "PEACE_PILLAGE_CAPITAL_STATE", 0x9B19F0, 0x9B1A8D),
    ("peace.show_strength", "po_humiliate", "PEACE_SHOW_STRENGTH", 0x9BC880, 0x9BC88F),
    ("peace.po_enforce_military_access", "po_enforce_military_access", "ENFORED_MILITARY_ACCESS", 0x9BFEF0, 0x9BFEFF),
    ("peace.po_transfer_vassals", "po_transfer_vassals", "PEACEOFFER_TRANSFER_TXT", 0x9CD690, 0x9CD765),
    ("peace.revoke_reform", "revoke_reform", "DEMAND_REVOKE_REFORM", 0x9BDC20, 0x9BDC2F),
    ("peace.po_humiliate_rival", "po_humiliate_rival", "PEACE_HUMILIATE", 0x9BC2A0, 0x9BC2AF),
)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def limited(path, maximum=4 * 1024 * 1024):
    if path.stat().st_size > maximum:
        raise ValueError(f"Input exceeds bounded size: {path.name}")
    return path.read_bytes()


def generate(exe, game, unpacked, fields_path, deps):
    check_memory_budget()
    pe = PE(exe)
    if digest(pe.data) != SHA:
        raise ValueError("Unsupported executable SHA-256")
    raw_fields = limited(fields_path)
    if digest(raw_fields) != FIELDS_SHA:
        raise ValueError("Fields report is not the reviewed full SHA-256")
    fields = json.loads(raw_fields)
    if fields["binary"]["sha256"].lower() != SHA:
        raise ValueError("Fields report binary mismatch")
    components = {c["name"]: c for c in fields["peace_components"]}
    if len(components) != 40 or {c["factory_case_index"] for c in components.values()} != set(range(40)):
        raise ValueError("Incomplete peace factory case table")
    md, cs = make_disassembler(deps)
    if md is None:
        raise ValueError("Capstone unavailable")
    entries = {row[3] for row in LABELS} | {0x9D2C90, 0x9D3730, 0x9D33D0,
        0xACB010, 0xAC9A30, 0xAC9BE0, 0x9A0F23, 0x9B6180, 0x9BFF80,
        0x9CE0B0, 0x9BDEF0}
    functions, instructions, decoded = {}, {}, 0
    for entry in sorted(entries):
        code, edges = bounded_cfg(pe, md, entry, window=MAX_WINDOW, max_instructions=MAX_INSTRUCTIONS)
        rows = [{"rva": hex(i.address), "bytes": i.bytes.hex(), "instruction": f"{i.mnemonic} {i.op_str}".strip()} for i in code]
        instructions.update({i.address: i for i in code})
        size = sum(i.size for i in code)
        decoded += size
        if decoded > MAX_TOTAL_CODE:
            raise ValueError("Total decode budget exceeded")
        functions[hex(entry)] = {"entry_rva": hex(entry), "decoded_bytes": size, "instructions": rows, "edges": edges}
        check_memory_budget()
    # Exact-SHA instruction block inside a large loader. It is deliberately
    # recorded as a linear snippet, not misrepresented as a function entry.
    snippet = list(md.disasm(pe.bytes_at(0x20E484, 0x22), 0x20E484))
    if sum(i.size for i in snippet) != 0x22:
        raise ValueError("Loader snippet boundary mismatch")
    instructions.update({i.address: i for i in snippet})
    snippet_rows = [{"rva": hex(i.address), "bytes": i.bytes.hex(), "instruction": f"{i.mnemonic} {i.op_str}".strip()} for i in snippet]

    def anchor(rva):
        if rva not in instructions:
            raise ValueError(f"Missing decoded instruction anchor {rva:#x}")
        i = instructions[rva]
        return {"rva": hex(rva), "bytes": i.bytes.hex(), "instruction": f"{i.mnemonic} {i.op_str}".strip()}

    def literal(rva, expected):
        i = instructions[rva]
        refs = [i.address + i.size + op.mem.disp for op in i.operands
                if op.type == cs.CS_OP_MEM and op.mem.base == cs.x86_const.X86_REG_RIP]
        if len(refs) != 1 or pe.bytes_at(refs[0], len(expected) + 1) != expected.encode("ascii") + b"\0":
            raise ValueError(f"Direct literal mismatch at {rva:#x}: {expected}")
        return {**anchor(rva), "literal_rva": hex(refs[0]), "literal": expected}

    manifest_raw = limited(unpacked / "manifest.json")
    manifest = json.loads(manifest_raw)
    pattern = re.compile(r"(?:^|/)common/(?:peace_treaties|cb_types|wargoal_types)/")
    selected = [f for f in manifest["files"] if pattern.search(f["path"])]
    input_sources, script_definitions, references = [], [], []
    for item in selected:
        raw = limited(unpacked / item["path"])
        if digest(raw) != item["sha256"] or len(raw) != item["bytes"]:
            raise ValueError("Unpacked source differs from manifest")
        source = {"path": item["origin"], "unpacked_path": item["path"], "sha256": digest(raw), "bytes": len(raw)}
        # Archives keep independent namespaces; do not silently decide override
        # precedence if a future extraction contains another definition.
        if not item["path"].startswith("base/"):
            source["active_load_order_resolved"] = False
            input_sources.append(source)
            continue
        installed = limited(game / item["origin"])
        if digest(installed) != digest(raw):
            raise ValueError("Installed source differs from unpacked evidence")
        input_sources.append(source)
        nodes = parse_script(raw.decode("utf-8-sig"))
        if item["origin"].startswith("common/peace_treaties/"):
            for node in nodes:
                visible = next((n for n in node.children if n.key == "is_visible"), None)
                script_definitions.append({"name": node.key, "source_path": item["origin"], "line": node.line,
                    "source_sha256": digest(raw), "explicitly_hidden": bool(visible and scalar(visible, "always") == "no"),
                    "component_name": "scriptable_diplomatic_action", "runtime_verified": False})
        else:
            for node in walk(nodes):
                if node.key in ("peace_options", "allowed_peace_options", "not_allowed_peace_options", "attacker_disabled_po", "defender_disabled_po"):
                    for option in node.children:
                        if option.value is None and not option.children:
                            references.append({"name": option.key, "source_path": item["origin"], "line": option.line,
                                "container": node.key, "reference_proves_runtime_eligibility": False})

    wanted_labels = {row[2] for row in LABELS} | {"GIVE_UP_CLAIMS_TOOLTIP", "ENFORCE_MILITARY_ACCESS", "TRANSFER_VASSAL_TOOLTIP", "REVOKE_REFORM_TOOLTIP"}
    loc = {}
    for path in sorted((game / "localisation").glob("*_l_english.yml")):
        raw = limited(path)
        matched = []
        for line, text in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
            match = LOC.match(text)
            if match and match[1] in wanted_labels:
                matched.append((match[1], {"source_path": path.relative_to(game).as_posix(), "line": line, "text": match[2], "source_sha256": digest(raw)}))
        if matched:
            source = {"path": path.relative_to(game).as_posix(), "sha256": digest(raw), "bytes": len(raw)}
            input_sources.append(source)
            loc.update(matched)
    if set(loc) != wanted_labels:
        raise ValueError("Missing expected localization evidence")
    bindings = []
    for public_id, component, label, method, use in LABELS:
        vt = int(components[component]["vtable_rva"], 16)
        if pe.u64(pe.to_offset(vt) + 0x100) - pe.base != method:
            raise ValueError("Peace display vtable slot mismatch")
        bindings.append({"action_id": public_id, "component_name": component, "label_key": label,
            "vtable_slot_offset": "0x100", "method_rva": hex(method), "direct_literal": literal(use, label),
            "localization": loc[label], "runtime_verified": False})

    def fact(detail, rvas):
        return {"detail": detail, "evidence_instructions": [anchor(r) for r in rvas], "runtime_verified": False}

    facts = {
        "peace_definition_loader": fact("The joined /peace_treaties path goes to loader 0x9d2c90. It creates a registry, installs it in global 0x242bd80 and passes each parsed file to 0x9d33d0; this is not /new_diplomatic_actions.",
            [0x20E484, 0x20E498, 0x20E4A1, 0x9D2CBF, 0x9D2CD3, 0x9D2CDC, 0x9D373D, 0x9D2FF7, 0x9D2FFE]),
        "named_definition_registration": fact("For each root name, parser creates a 0x290 definition via 0xacb010 and inserts name-to-definition into registry+0x30. Its factory descriptor stores case 39 and the definition pointer. Constructor moves the name String32 to definition+0x10.",
            [0x9D34D6, 0x9D352E, 0x9D354D, 0x9D3558, 0x9D355F, 0x9D3569, 0x9D3572, 0x9D357A, 0xACB050, 0xACB053, 0xACB057, 0xACB05B]),
        "factory_descriptor_binding": fact("The dedicated peace factory 0x99ff90 consumes a descriptor; case 39 allocates 0x38 bytes, installs the peace vtable 0x1cd21b0 and copies descriptor+8 definition into component+0x30. It is a separate ABI from ordinary diplomacy factory 0x35d210.",
            [0x9A0F23, 0x9A0F28, 0x9A0F74, 0x9A0F7B, 0x9A0F7E, 0x9A0F82]),
        "script_type_roundtrip": fact("Peace type token 0xe1 resolves an exact name through global 0x242bd80 and stores its definition pointer at component+0x30. Serializer reads that pointer's String32 at +0x10. Missing lookup can yield null; passing a caller string as this pointer is invalid.",
            [0xAC9A39, 0xAC9A68, 0xAC9AE8, 0xAC9AF7, 0xAC9B08, 0xAC9B7C, 0xAC9B8A, 0xAC9BEF, 0xAC9BF9, 0xAC9C01, 0xAC9C05, 0xAC9C20]),
        "give_up_claims_country_scope": fact("This peace component has one derived taker country handle, not a province array. Its tooltip says WHO and subjects give up all claims in TARGET. A public claims_against country is provisional until giver/taker/offer directions are bound.", [0x9B61D1, 0x9B61F1]),
    }
    facts["peace_definition_loader"]["path_literal"] = literal(0x20E484, "/peace_treaties")
    for rva, key in ((0x9B61F1, "GIVE_UP_CLAIMS_TOOLTIP"), (0x9BFFF1, "ENFORCE_MILITARY_ACCESS"),
                     (0x9CE263, "TRANSFER_VASSAL_TOOLTIP"), (0x9BDFB5, "REVOKE_REFORM_TOOLTIP")):
        literal(rva, key)
    return {"schema_version": 1, "analysis_kind": "bounded_static_peace_catalog_bindings", "game_sha256": SHA,
        "runtime_verified": False, "execution_verified": False, "public_backend_registered": False,
        "fields_report": {"path": "work/reports/native-action-fields-1375.json", "sha256": FIELDS_SHA},
        "source_audit": {"manifest_path": "work/runtime/unpacked-1.37.5/manifest.json", "manifest_sha256": digest(manifest_raw),
            "selected_files": len(selected), "archive_files_in_selected_directories": sum(not f["path"].startswith("base/") for f in selected),
            "load_order_resolved": False, "installed_base_sources_match_unpacked": True},
        "inputs": sorted(input_sources, key=lambda s: s["path"]), "label_bindings": bindings,
        "scripted_peace_definitions": sorted(script_definitions, key=lambda s: s["name"]),
        "peace_option_references": references, "parameter_localization": {k: loc[k] for k in sorted(wanted_labels) if k.endswith("TOOLTIP") or k == "ENFORCE_MILITARY_ACCESS"},
        "catalog_corrections": [
            {"action_id": "peace.po_humiliate", "name_zh": "展现力量", "reason": "Its own +0x100 method names PEACE_SHOW_STRENGTH; po_humiliate_rival names PEACE_HUMILIATE.", "compatible_alias_id": "peace.show_strength"},
            {"action_id": "peace.po_transfer_vassals", "reason": "Previous scanner omitted attacker_disabled_po containers. Disabled references prove an option identifier exists, not that it is allowed."},
            {"action_id": "peace.po_enforce_military_access", "reason": "Hardcoded component +0x100 directly names ENFORED_MILITARY_ACCESS; source-only option lists missed it."},
            {"action_id": "peace.revoke_reform", "reason": "Hardcoded peace component directly names DEMAND_REVOKE_REFORM; separate from an emperor voluntarily revoking reform."},
            {"action_id": "peace.give_up_claims", "reason": "Replace unsupported province_ids request with provisional claims_against country scope; native binding remains partial."}],
        "facts": facts, "functions": functions, "loader_snippet": snippet_rows,
        "limits": {"function_window_bytes": MAX_WINDOW, "max_instructions_per_function": MAX_INSTRUCTIONS,
            "total_code_budget_bytes": MAX_TOTAL_CODE, "decoded_instruction_bytes": decoded + 0x22,
            "max_source_file_bytes": 4 * 1024 * 1024, "analysis_memory_guard_bytes": 768 * 1024 * 1024},
        "unresolved": ["Owned peace-offer construction, war and current negotiator identity, component ownership and disposal are unverified.",
            "Native giver/offer_giver/offer_taker/taker roles have not been bound to public actor/target fields.",
            "Full annexation is not mapped to an independent factory class; no composite implementation is inferred.",
            "No legality, acceptance, application, persistence or runtime visibility is established by this report."]}


def render_docs(report):
    visible = [s for s in report["scripted_peace_definitions"] if not s["explicitly_hidden"]]
    return "\n".join([
        "# 1.37.5 和平条款静态目录闭合", "",
        "本报告只读解析精确 SHA 的 EXE、字段报告和已解包游戏源文件，没有打开游戏进程。可复现：`python work/trace_peace_catalog.py --check`；省略路径按 local.env 读取。", "",
        f"游戏 SHA-256：`{report['game_sha256']}`。字段报告 SHA-256：`{FIELDS_SHA}`。",
        "报告自身 SHA 随目录合并时钉扎在 build_diplomacy_catalog.py；修改证据后必须重新审查。", "",
        "独立的和平组件工厂为 `0x99ff90`，包含 40 个 case。不要调用普通外交工厂 `0x35d210` 来构造它们。组件必须装入具备正确战争、谈判方和所有权的和约；这里没有实现发送接口。", "",
        "## 名称与扫描修正", "",
        "7 个原本只有本地化的旧 ID 由各组件 vtable+0x100 的直接字符串引用闭合。保留旧 ID：`peace.show_strength` 是 `peace.po_humiliate` 的兼容别名，两者均为展现力量；真正的羞辱宿敌组件是 `po_humiliate_rival`。公共 ID 个数不等于独立组件个数。", "",
        "补充 `peace.po_transfer_vassals`：源文件已有 7 个 attacker_disabled_po 引用，旧扫描器漏读这个容器。禁用集合只证明标识存在，不能作为可执行条件。`peace.po_enforce_military_access` 与 `peace.revoke_reform` 由原生显示方法和本地化共同证明；后者是和约要求撤销帝国改革，与皇帝自愿撤销操作区分。", "",
        "| 公开 ID | 和平组件 | 原生显示 key | +0x100 方法 |", "| --- | --- | --- | --- |",
        *[f"| `{b['action_id']}` | `{b['component_name']}` | `{b['label_key']}` | `{b['method_rva']}` |" for b in report["label_bindings"]], "",
        "## 脚本和平专属路径", "",
        f"可见脚本定义 {len(visible)} 个。`/peace_treaties` → loader `0x9d2c90` → registry `0x242bd80` → `0x9d33d0` 按根名称注册定义；descriptor case=39/+8 定义指针 → 和平工厂 case39 的 component+0x30。parser `0xac9a30` 的 type 查同一 registry，serializer `0xac9be0` 使用 definition+0x10 名称。这个共享 token 虽也叫 scriptable_diplomatic_action，却具有独立 vtable、字段、工厂和定义注册表。", "",
        f"解包审计覆盖 {report['source_audit']['selected_files']} 个 CB/war-goal/peace 源文件，匹配安装目录；这些目录的归档新增文件为 {report['source_audit']['archive_files_in_selected_directories']}。整个游戏的 MOD/DLC 覆盖和活动载入顺序仍未解析。明确 is_visible always=no 的定义保留为排除项。", "",
        "## 字段与未知项", "",
        "基础字段分别为 offer_giver+0x10、offer_taker+0x18、is_selected+0x20、**未对齐 giver+0x22**。不能把 giver 与 offer_giver 合并，不能假定 actor/target 就是其顺序。割地/撤销核心/归还核心的 province_id 实际存省份对象指针；殖民地区存定义指针，脚本和平 type 也存定义指针，外部整数或字符串不能直接写入。金币 value 为 4 字节有符号定点 ×1000，公开金额上下限/步进尚待原生校验。", "",
        "`peace.give_up_claims` 的额外国家字段和文案明确是放弃某国境内全部宣称，旧 province_ids 数组没有证据，改为暂定 claims_against TAG。所有条款 parameter_status 继续 partial，public_parameter_binding_verified=false；没有将序列化字段当成完成的请求适配器。", "",
        *["- " + item for item in report["unresolved"]], "",
        "全部 runtime_verified/execution_verified=false。保存重载、AI 接受、和平结算和完整外交覆盖均未因此完成。", ""])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path)
    parser.add_argument("--unpacked", type=Path, default=ROOT / "work/runtime/unpacked-1.37.5")
    parser.add_argument("--fields-report", type=Path, default=ROOT / "work/reports/native-action-fields-1375.json")
    parser.add_argument("--deps", type=Path, default=Path(os.environ.get("TEMP", ".")) / "eu4-native-analysis-deps")
    parser.add_argument("--output", type=Path, default=ROOT / "work/reports/native-peace-catalog-1375.json")
    parser.add_argument("--docs", type=Path, default=ROOT / "docs/native-peace-catalog-1375.md")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.game_root is None:
        from local_config import get_value
        args.game_root = Path(get_value("EU4_GAME_ROOT"))
    report = generate(args.game_root / "eu4.exe", args.game_root, args.unpacked, args.fields_report, args.deps)
    products = {args.output: json.dumps(report, ensure_ascii=False, indent=2) + "\n", args.docs: render_docs(report)}
    stale = []
    for path, value in products.items():
        raw = value.encode("utf-8")
        if args.check:
            if not path.is_file() or path.read_bytes() != raw:
                stale.append(path.name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    print(json.dumps({"mode": "check" if args.check else "write", "stale": stale,
        "report_sha256": digest(products[args.output].encode("utf-8")), "label_bindings": len(report["label_bindings"]),
        "decoded_bytes": report["limits"]["decoded_instruction_bytes"]}))
    return int(bool(stale))


if __name__ == "__main__":
    raise SystemExit(main())
