"""File-only knowledge-sharing layout/spec review; --check verifies exact pins."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work.review_annex_fixture_r3_1375 import pin_file, require

OUT = ROOT / "work/reports/diplomacy-corrective-20261014-r3"
GAME_SHA = "9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"
TOOL_SHA = "337f916b1a1f1608de66488381e6b0d4c653a5633aad9faccca1cf62b0630ea1"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = OUT / "knowledge-rpm-layout-review.json"
    if args.check:
        report = json.loads(target.read_text(encoding="utf-8"))
        for pin in report["source_pins"].values():
            require(pin_file(Path(pin["path"])) == pin, "Knowledge source pin changed: " + pin["path"])
        require(pin_file(Path(report["markdown_pin"]["path"])) == report["markdown_pin"], "Knowledge Markdown pin changed")
        require(report["native_calls"] == report["requests_published"] == 0
                and report["game_process_accessed"] is False, "File-only boundary changed")
        print(json.dumps({"status": "checked", "source_pins": len(report["source_pins"]),
                          "observations": len(report["observations"]), "game_process_accessed": False}))
        return
    require(not target.exists(), "Independent knowledge review exists; use --check")
    paths = {"script": Path(__file__), "pin_helper": ROOT / "work/review_annex_fixture_r3_1375.py",
             "memory_guard": ROOT / "work/validate_current_diplomacy_1375.py", "game": ROOT.parent / "eu4.exe",
             "decoder": ROOT / "work/discover_diplomacy.py", "tracer": OUT / "trace-knowledge-layout.py",
             "static": OUT / "knowledge-layout-static.json", "assembly": OUT / "knowledge-layout-disassembly.txt",
             "prior_findings": ROOT / "work/reports/rea-api-discovery-20261013/conditions/findings.json",
             "prior_conditions": ROOT / "work/reports/rea-api-discovery-20261013/conditions/conditions-disassembly-manifest.json",
             "prior_save_countries": OUT / "latest-save-selected-countries.json",
             "prior_save_provinces": OUT / "latest-save-capital-area-provinces.json",
             "prior_plan": OUT / "candidate-preparation.json",
             "tool": ROOT / "work/probe_knowledge_context_r3_1375.py",
             "tool_receipt": OUT / "knowledge-rpm-tool-file-validation.json",
             "guarded_reader": ROOT / "work/probe_remaining_pairs_r3_1375.py",
             "map_area": ROOT.parent / "map/area.txt",
             "map_parser": ROOT / "tools/build_diplomacy_unlock_mod.py",
             "map_parser_child": ROOT / "tools/build_diplomacy_catalog.py"}
    pins = {key: pin_file(path) for key, path in paths.items()}
    require(pins["game"]["sha256"] == GAME_SHA and pins["tool"]["sha256"] == TOOL_SHA,
            "Wrong game or delivered knowledge tool")
    static = json.loads(paths["static"].read_text(encoding="utf-8"))
    require(static["game_sha256"] == GAME_SHA and static["evidence_kind"] == "ordinary_capstone_file_analysis"
            and static["source_pins"]["disassembly_sha256"] == pins["assembly"]["sha256"]
            and static["source_pins"]["script_sha256"] == pins["tracer"]["sha256"]
            and static["source_pins"]["decoder_sha256"] == pins["decoder"]["sha256"], "Static capture pin mismatch")
    tool_receipt = json.loads(paths["tool_receipt"].read_text(encoding="utf-8"))
    require(tool_receipt["tool_sha256"] == TOOL_SHA and not tool_receipt["actual_tool_main_invoked"]
            and not tool_receipt["sample_invoked"] and not tool_receipt["game_process_accessed"],
            "Knowledge tool runtime boundary invalid")
    for name, pin in tool_receipt["source_pins"].items():
        path = Path(name) if Path(name).is_absolute() else ROOT / name
        actual = pin_file(path)
        require(actual["bytes"] == pin["bytes"] and actual["sha256"] == pin["sha256"],
                "Knowledge tool source pin changed: " + name)
    observations = [
        {"id": "offer_vs_ask_roles", "kind": "observation", "rvas": ["0x52bebf", "0x52bee8", "0x52befa", "0x529efd", "0x52bf1d"],
         "fact": "Offer local uses actor as provider/target as recipient. Ask local constructs the reversed knowledge object, while both full checks retain original actor for common envoy/cooldown gates.",
         "pairs": [{"action": "knowledge_sharing", "actor": "FRA", "target": "JOL", "provider": "FRA", "recipient": "JOL", "envoys": "FRA", "cooldown": ["FRA", "JOL"]},
                   {"action": "ask_knowledge_sharing", "actor": "MAL", "target": "FRA", "provider": "FRA", "recipient": "MAL", "envoys": "MAL", "cooldown": ["MAL", "FRA"]}]},
        {"id": "native_distance_direction", "kind": "observation", "rvas": ["0x529d51", "0x529d65", "0x529d7f", "0x529d83", "0x529da0", "0x529da2"],
         "fact": "Provider+2398/+23a0 first vector and +23b0/+23b8 distance vector both need byte-length>=2 for cached distance read. The indexed distance is unsignedWORD[recipient signed16 slot]*1000; it must be <=provider native range. Explicit observed short-vector branches produce native zero; missing samples do not.",
         "unknowns": ["Cache construction/invalidation", "Native only checks length>=2, not full recipient-index bound; RPM refuses to guess an out-of-observed-vector element."]},
        {"id": "range_input_and_modifier_layout", "kind": "observation", "rvas": ["0x350178", "0x35017f", "0x350229", "0x350235", "0x350239", "0x350240", "0x350244", "0x35024c", "0x350260", "0x3503b9"],
         "fact": "Range base is *(provider+2440)+50 signedDWORD. After93d750, modifier context=return+8: nonzero byte+10 selects *(context+58)+3cc for modifier0x79; otherwise signedcount+64 and 8-byte(key,value) records at+58 select firstkey0x79, absent/<=0 yields native zero.",
         "unknowns": ["The modifier business-name parser binding is not proved here.", "The accessor context may differ from the provider's ordinary data during calculation."]},
        {"id": "modifier_context_nonpure_and_calculating_state", "kind": "observation", "rvas": ["0x93d77a", "0x93d77f", "0x93d783", "0x93d78c", "0x93d78f", "0x93d8e9", "0x93d9c2", "0x93d9cb", "0xdf3c6", "0xdf3ce"],
         "fact": "93d750 normally returns input+8=provider+28c8; when thread-cache comparison differs and DWORD at+28c8 is1, it follows a diagnostic/fallback path. Its binary diagnostic names CCountryModifiers::EState::CALCULATING. df320's decoded prefix has a virtual allocation path and lock xadd write. These helpers must not be invoked for read-only querying.",
         "native_globals": {"context_cache": "0x1fd4ab8", "fallback_modifier_context": "0x245bb20"},
         "projection": "Only state!=1 proves the ordinary own-context return regardless of unresolved cache match; state1 retains unknown."},
        {"id": "dynamic_range_override_and_rounding", "kind": "observation", "rvas": ["0x35027b", "0x350282", "0x350299", "0x35029f", "0x3502aa", "0x3502f2", "0x350300", "0x350302"],
         "fact": "global2358080->+2da0 nonnull invokes vtable+8 to adjust the modifier. Then signed fixed-point multiplication/division by1000 and rounding to1000 are applied. The new RPM tool only projects arithmetic if this override is null and modifier context is established; a nonnull override's slot is recorded without calling it.",
         "unknowns": ["Current override implementation/state", "Its selected vtable target may be analysed later from a passive snapshot, without invoking it."]},
        {"id": "existing_registry_not_initializer", "kind": "observation", "rvas": ["0x855af0", "0x855b16", "0x855b1b", "0xa70c8e", "0xa70c92", "0xa70cc5", "0xa70cc9", "0xa70cdb"],
         "fact": "855ad0 returns the address of staticregistry2328b10; candidate pointer vector at+10/+18 gives its observed iteration order, each candidate's signedDWORD+10 is native ID. Getter slow path allocates and writes global data, so RPM only reads existing bounded vector/guard245b6b8; guard-1 is retained as uninitialized/unknown and is not initialized.",
         "unknowns": ["Native ID to institution name mapping", "Registry ordering is not assumed chronological", "Real engine-thread epoch/TLS guard."]},
        {"id": "accepted_and_progress_are_indirect_arrays", "kind": "observation", "rvas": ["0xa70cea", "0xa70cf1", "0xa70cfc", "0xa70d03", "0xa70d4d", "0xa70d54", "0xa70d5c"],
         "fact": "country+0xc68 andprovince+0xd0 are pointers. At registryID*4, provider acceptedDWORD!=0 and recipient acceptedDWORD==0; selected recipient-owned province progress signedDWORD<100000. These are not inline arrays and the getter supplies no native length checks in this range.",
         "rpm_bound": "32 existing registry entries, IDs0..31; only native-selected4-byte indices; no guessed vector end/capacity.",
         "unknowns": ["Actual native array lengths/capacities", "Serialized position/name mapping and percentage interpretation are not promoted into native facts."]},
        {"id": "exact_recipient_capital_area_machine_path", "kind": "observation", "rvas": ["0xa70c71", "0xa70c78", "0xa70c7c", "0xa70d0a", "0xa70d18", "0xa70d25", "0xa70d2b", "0xa70d36", "0xa70d3d", "0xa70d48"],
         "fact": "recipient+14b0 capitalpointer ->capital+28 definitionpointer ->definition+40 selectedareapointer. Area+88/+90 is an int32 province-ID list; map each via game+1ca8+ID*2e10, require native owner+468 slot==recipient before progress check. No all-province scan is equivalent.",
         "rpm_bound": "96 selected list entries max; capital/province nativeID+20 is correlated with the indexed address, full owner handles validated against the complete country table. Exact area set can be matched with installedmap/area.txt plus capitalID.",
         "unknowns": ["Exact CProvince/definition/area class vtable identity", "Business area name remains inference until independent complete ID-set correlation; no capital-file guess replaces native vector."]},
        {"id": "sharing_counts_and_context_gate", "kind": "observation", "rvas": ["0x529a71", "0x529a7d", "0x529a97", "0x529aa9", "0x529c31", "0x529c41", "0x529c5a", "0x529c68"],
         "fact": "Provider andrecipient signed counts+17dc/+17c4 must all<=0. Context direct branch allows233ff38!=0 AND233fed6==0; otherwise actual engine-thread TLS/initializer path remains required. RPM captures global bytes, not another thread's TLS or guessed licensing names.",
         "unknowns": ["Sharing object creation/expiry/war cleanup", "Exact thread TLS+0x10 value when direct globals do not pass."]},
    ]
    addresses = {i["rva"] for entry in static["ranges"] for i in entry["instructions"]}
    require(all(rva in addresses for item in observations for rva in item["rvas"]),
            "Knowledge observation points outside decoded instruction boundaries")
    prior = json.loads(paths["prior_plan"].read_text(encoding="utf-8"))
    leads = [item for item in prior["institution_difference_pair_leads"] if item.get("recipient") in ("JOL", "MAL")]
    md = OUT / "knowledge-rpm-layout-review.md"
    md.write_text(
        "# 双向知识分享：只读布局与补充工具\n\n"
        "固定1.37.5 SHA9ad3efe1…，10个有界范围4,506字节/1,101指令，普通Capstone；无进程访问、原生调用或请求。\n\n"
        "|动作|请求actor→target|本地provider→recipient|公共外交官/冷却|\n|---|---|---|---|\n"
        "|knowledge_sharing|FRA→JOL|FRA→JOL|FRA / FRA→JOL|\n"
        "|ask_knowledge_sharing|MAL→FRA|FRA→MAL|MAL / MAL→FRA|\n\n"
        "原生范围都取FRA；按接收方槽分别读FRA距离缓存。两个参与者+17dc/+17c4四个signedcount均需<=0；不是只查本pair。\n\n"
        "机构registry静态地址2328b10，+10/+18是候选指针向量、候选对象+10是ID。country+c68和province+d0都是指针，再按ID*4读取。registry/helper含懒初始化和写入，工具不调用。\n\n"
        "精确局部列表来自recipient+14b0→capital+28→definition+40→area+88/+90；只遍历该int32省份ID向量，按game+1ca8/stride2e10映射，核完整owner后查progress<100000。工具额外以完整省份集合与installedmap/area.txt匹配；类型VT与机构名称映射仍未知。固定旧存档JOL首都1116、MAL1124只是线索，不替代新采样。\n\n"
        "范围输入是provider+2440→+50，经modifier0x79和global2358080→+2da0动态覆盖。93d750在state1(CALCULATING)时依赖线程缓存，df320含写入。工具只在state!=1且动态override为空时投影原生定点算式；其余range=null并明确unknown。全局context非直接通过时TLS也保持unknown。\n\n"
        "新独立工具work/probe_knowledge_context_r3_1375.py，SHA337f916b1a1f1608de66488381e6b0d4c653a5633aad9faccca1cf62b0630ea1；CLI与原reader相同：--pid/--creation/--output，可选--allow-tag-host。继承两遍相等、held身份/模块/暂停/Mod−1/build7守卫及共享8192calls/1MiB。新投影写knowledge_context_supplement，始终complete_legality_proven=false。已做语法/import/20sourcepin与地图结构校验，未运行main或sample。旧reader及冻结证据未改；任何后续派发仍须当前no-repeat策略。\n",
        encoding="utf-8")
    result = {"schema": "EU4TAG31-KNOWLEDGE-RPM-LAYOUT-REVIEW/1", "game_sha256": GAME_SHA,
              "evidence_kind": "ordinary_capstone_plus_preserved_save_and_shipped_map_files",
              "source_pins": pins, "markdown_pin": pin_file(md), "observations": observations,
              "preserved_save_leads_only": leads,
              "save_leads_are_not_current_native_legality": True,
              "tool": {"path": paths["tool"].resolve().as_posix(), "sha256": TOOL_SHA,
                       "syntax_and_files_only_verified": True, "main_or_sample_invoked": False,
                       "shared_limits": {"calls": 8192, "bytes": 1048576}, "two_pass_equality_required": True},
              "native_calls": 0, "requests_published": 0, "game_process_accessed": False,
              "reader_or_frozen_evidence_modified": False, "current_native_legality_proven_count": 0,
              "limitations": ["No new runtime state, current legal pair, first-failed branch or actual sharing effect is proven.",
                              "Two equal RPM passes are not an atomic engine-thread snapshot or future-dispatch guarantee.",
                              "Unknown fields/TLS/override/array bounds are not converted into false/zero/passed.",
                              "No-repeat blocks from any later dispatch/success/unknown evidence override prior candidate status."]}
    require({key: pin_file(path) for key, path in paths.items()} == pins, "Knowledge sources changed during review")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"status": "written", "source_pins": len(pins), "observations": len(observations),
                      "native_calls": 0, "game_process_accessed": False}))


if __name__ == "__main__":
    main()
