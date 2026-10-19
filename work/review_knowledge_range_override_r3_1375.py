"""Independent file review of the observed range override and range-only fixture."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work.review_annex_fixture_r3_1375 import pin_file, require, children
from tools.build_diplomacy_unlock_mod import spans
from work.probe_knowledge_context_r3_1375 import range_arithmetic

OUT = ROOT / "work/reports/diplomacy-corrective-20261014-r3/knowledge-range-override"
TOOL_SHA = "6eaa9c7d0ca93fdd666ff682e0d6f287fb322cf84d0f72138fe4acb38fa9938d"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result_path = OUT / "review.json"
    if args.check:
        report = json.loads(result_path.read_text(encoding="utf-8"))
        for item in report["source_pins"].values():
            require(pin_file(Path(item["path"])) == item, "Override source pin changed: "+item["path"])
        require(pin_file(Path(report["markdown_pin"]["path"])) == report["markdown_pin"], "Override Markdown changed")
        require(not report["game_process_accessed"] and report["native_calls"] == report["requests_published"] == 0,
                "File-only boundary changed")
        print(json.dumps({"status": "checked", "source_pins": len(report["source_pins"]), "native_calls": 0}))
        return
    require(not result_path.exists(), "Independent review exists; use --check")
    paths = {"script": Path(__file__), "pin_helper": ROOT / "work/review_annex_fixture_r3_1375.py",
             "game": ROOT.parent / "eu4.exe", "decoder": ROOT / "work/discover_diplomacy.py",
             "tracer": OUT / "trace-override.py", "static": OUT / "override-static.json",
             "assembly": OUT / "override-disassembly.txt", "tool": ROOT / "work/probe_knowledge_range_override_r3_1375.py",
             "tool_receipt": OUT / "tool-file-validation.json", "frozen_knowledge_reader": ROOT / "work/probe_knowledge_context_r3_1375.py",
             "snapshot": OUT.parent / "runtime/knowledge-before-test.json",
             "fixture_modifier": OUT / "fixture-event-modifier-candidate.txt", "fixture_effect": OUT / "fixture-effect-candidate.txt",
             "fixture_parser": ROOT / "tools/build_diplomacy_unlock_mod.py", "fixture_parser_child": ROOT / "tools/build_diplomacy_catalog.py",
             "original_event_modifiers": ROOT.parent / "common/event_modifiers/00_event_modifiers.txt",
             "original_static_modifiers": ROOT.parent / "common/static_modifiers/00_static_modifiers.txt",
             "original_defines": ROOT.parent / "common/defines.lua",
             "frozen_mod_dip_tech": ROOT / "mod/llm_diplomacy_unlock/common/technologies/dip.txt",
             "frozen_mod_country_modifiers": ROOT / "mod/llm_diplomacy_unlock/common/event_modifiers/llm_diplomacy_unlock.txt"}
    pins = {name: pin_file(path) for name, path in paths.items()}
    require(pins["game"]["sha256"] == "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"
            and pins["tool"]["sha256"] == TOOL_SHA
            and pins["frozen_knowledge_reader"]["sha256"] == "337f916b1a1f1608de66488381e6b0d4c653a5633aad9faccca1cf62b0630ea1",
            "Wrong game or reader identity")
    static = json.loads(paths["static"].read_text(encoding="utf-8"))
    require(static["source_pins"]["script_sha256"] == pins["tracer"]["sha256"]
            and static["source_pins"]["decoder_sha256"] == pins["decoder"]["sha256"]
            and static["source_pins"]["disassembly_sha256"] == pins["assembly"]["sha256"], "Override static pin mismatch")
    snapshot = json.loads(paths["snapshot"].read_text(encoding="utf-8"))
    require(snapshot["two_pass_equal"] and snapshot["passes"][0] == snapshot["passes"][1], "Recorded knowledge sample differs")
    base = int(snapshot["module_base"], 16)
    pairs = snapshot["passes"][0]["knowledge_context_supplement"]["pairs"]
    native = pairs[0]["provider_native_range"]
    vt_rva = int(native["dynamic_override_vtable"], 16)-base
    slot_rva = int(native["dynamic_override_slot8"], 16)-base
    require(vt_rva == 0x1cc9318 and slot_rva == 0x8fa860, "Recorded typed override target differs")
    require(native["modifier_context_state_raw_28c8"] == 2 and native["modifier_raw"] == 0
            and native["base_range_raw_tech_50"] == 160000, "Unexpected preserved provider inputs")
    modifier_nodes = spans(paths["fixture_modifier"].read_text(encoding="utf-8"))
    require(len(modifier_nodes) == 1 and modifier_nodes[0].key == "llm_unlock_knowledge_range"
            and children(modifier_nodes[0]) == {"range": "2.2"}, "Range-only modifier candidate changed")
    effects = spans(paths["fixture_effect"].read_text(encoding="utf-8"))
    require(len(effects) == 1 and effects[0].key == "FRA" and len(effects[0].children) == 1
            and effects[0].children[0].key == "add_country_modifier"
            and children(effects[0].children[0]) == {"name": "llm_unlock_knowledge_range", "duration": "3650"},
            "Range-only fixture effect scope changed")
    original_mods = {node.key: children(node) for node in spans(paths["original_static_modifiers"].read_text(encoding="utf-8-sig"))}
    require(original_mods["tutorial_colonial_range"]["range"] == "0.1", "Original range-key example changed")
    receipt = json.loads(paths["tool_receipt"].read_text(encoding="utf-8"))
    require(receipt["tool_sha256"] == TOOL_SHA and not receipt["actual_tool_main_invoked"]
            and not receipt["sample_invoked"] and not receipt["game_process_accessed"], "Tool validation boundary invalid")
    for name, item in receipt["source_pins"].items():
        path = Path(name) if Path(name).is_absolute() else ROOT / name
        actual = pin_file(path)
        require(actual["sha256"] == item["sha256"] and actual["bytes"] == item["bytes"], "Tool source changed: "+name)
    observations = [
        {"id": "input_and_typed_dispatch", "rvas": ["0x350235", "0x350291", "0x350299", "0x8fa86a", "0x8fa86d", "0x8fa870"],
         "fact": "Typed slot8 copies *r9 original modifier0x79 into *rdx; r8 is the already resolved modifier context. The function does not dereference its this parameter. File table1cc9318 has slot0=8f48e0/slot8=8fa860; exact C++ class name remains unknown."},
        {"id": "direct_global_identity", "rvas": ["0x8fa875", "0x8fa87e", "0x8fa885", "0x8fa919"],
         "fact": "byte233ff2c!=0 ANDbyte233fed6==0 selects identity immediately; 233ff38 from knowledge local is a different gate and cannot replace233ff2c."},
        {"id": "tls_identity_or_add225", "rvas": ["0x8fa88b", "0x8fa8a1", "0x8fa8a7", "0x8fa8b1", "0x8fa8ba", "0x8fa8bc", "0x8fa8c6", "0x8fa8cf", "0x8fa8dc", "0x8fa8f0", "0x8fa914", "0x8fa917"],
         "fact": "Otherwise actual threadTLS may be initialized at+c; TLS+10!=0 also returns identity. The remaining path adds modifier0xe1 from the same context: dense+58 pointer then+70c, or signedcount+64 and8-byte sparse records firstkey225/value+4; absent yields native zero. Output addition wraps as signed32.",
         "unknowns": ["TLS initializer effects and owner-thread state", "Modifier225 business-name registration binding."]},
        {"id": "readonly_projection_cases", "rvas": ["0x8fa8db", "0x8fa913", "0x8fa926", "0x35029f", "0x3502aa", "0x350300", "0x350302"],
         "fact": "If the direct identity gate is observed, or all observed identity/add225 return alternatives give the same modifier/range/gate result, RPM can project that result without calling the override. Differing alternatives retain unknown. The native fixed-point range calculation and round-to1000 follow the override result."},
    ]
    addresses = {instruction["rva"] for item in static["ranges"] for instruction in item["instructions"]}
    require(all(rva in addresses for item in observations for rva in item["rvas"]), "Observation RVA not instruction boundary")
    distances = {pair["action"]: pair["provider_distance"]["distance_milli"] for pair in pairs}
    fixture = {"country": "FRA", "country_modifier_key": "range", "value": "2.2", "expected_raw_increment_if_bound": 2200,
               "duration": 3650, "structural_parse_passed": True, "installed": False, "executed": False,
               "primary_script_example": {"source": "original_static_modifiers", "key": "tutorial_colonial_range", "range": "0.1"},
               "script_key_to_native_modifier121_binding": "unproven here; verify the actual postfixture native modifier121 increment",
               "conditional_on_override_identity_or_zero_addend": {"base_range_raw": 160000, "original_modifier_raw": 0,
                   "candidate_modifier_raw": 2200, "projected_range_raw": range_arithmetic(160000, 2200),
                   "recorded_distances": distances},
               "required_before_testing": ["Explicitly prepare and load the new definition in a deliberate fresh test Mod; no frozen Mod was changed here.",
                                           "After applying the fixture, record a fresh baseline and verify native modifier121 and typed override result.",
                                           "Keep all original full/local gates, institution/area/war/share-count/envoy/cooldown/no-repeat checks.",
                                           "Do not attribute direct fixture application or range projection to an API effect."]}
    require(fixture["conditional_on_override_identity_or_zero_addend"]["projected_range_raw"] == 512000,
            "Conditional range arithmetic mismatch")
    md = OUT / "review.md"
    md.write_text(
        "# 当前知识分享范围覆盖：精确入口与只读闭合方案\n\n"
        "固定knowledge-before-test.json中的vtable完整地址减modulebase为RVA1cc9318，slot8为8fa860。完整入口跨三个.pdata片段：[8fa860,8fa927)，199字节；连同调用方共824字节/218指令，普通Capstone，无原生调用。\n\n"
        "入口先复制modifier121；global233ff2c!=0且233fed6==0时原样返回。否则真实线程TLS+10为真也原样返回，必要的TLS初始化使它不能作为只读函数调用。剩余分支才加同一modifier上下文中的编号225：dense table+70c或sparse第一条key225。函数不读取this对象额外字段。编号225名称及精确C++类名仍未绑定。\n\n"
        "只读补采233ff2c、modifier225即可处理大部分情况：直接门槛通过时identity已确定；225为0时两个返回分支一致；不同修正仍可能舍入成同一range或同一比较结果。其他情况保留全部分支与unknown，不调用TLS或override。\n\n"
        "新工具probe_knowledge_range_override_r3_1375.py，SHA6eaa9c7d0ca93fdd666ff682e0d6f287fb322cf84d0f72138fe4acb38fa9938d，继承原reader完整守卫/两遍/共享8192calls与1MiB，另核加载的199字节代码及typedtable。新节点knowledge_range_override_supplement；原337f知识reader保持。仅语法/import/25sourcepin验证，未运行main/sample。\n\n"
        "保存的范围输入：FRA base160000、modifier121=0、state2；JOL距离512000，MAL507000。原报告缺233ff2c/225，尚不能宣称实际range就是160000。单字段离线候选是FRA添加range=2.2的countrymodifier；若override保持原值或加0，2200原始增量使范围成为512000，等于JOL门槛且覆盖MAL。候选结构解析通过，未改/安装/执行Mod；实际字段绑定和其他硬条件必须以新基线再核。\n",
        encoding="utf-8")
    result = {"schema": "EU4TAG-KNOWLEDGE-RANGE-OVERRIDE-FILE-REVIEW/1", "source_pins": pins,
              "markdown_pin": pin_file(md), "observations": observations,
              "recorded_runtime_example_only": {"pid": snapshot["pid"], "creation": snapshot["creation"],
                   "vtable_rva_derived_from_complete_addresses": hex(vt_rva), "slot8_rva": hex(slot_rva),
                   "provider_modifier_state": 2, "original_modifier": 0, "base_range": 160000,
                   "distances": distances, "new_range_gate_and_modifier225_not_in_original_snapshot": True,
                   "actual_runtime_range_not_yet_proven": True},
              "fixture": fixture, "native_calls": 0, "requests_published": 0, "game_process_accessed": False,
              "frozen_reader_or_mod_modified": False, "complete_current_legality_proven": False,
              "limitations": ["Existing runtime report is a preserved observation, not current process state.",
                              "All machine projections are conditional on the captured fields and unchanged execution context; two equal passes are not an atomic future-call guarantee.",
                              "No range condition alone proves full/local/legacy/AI acceptance or sharing effects.",
                              "Historical dispatched/successful/unknown exclusions and original IDs remain binding."]}
    require({name: pin_file(path) for name, path in paths.items()} == pins, "Override review source changed")
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"status": "written", "source_pins": len(pins), "observations": len(observations),
                      "fixture_installed": False, "native_calls": 0}))


if __name__ == "__main__":
    main()
