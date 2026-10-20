"""Independent file-only audit of retained current-absence decoder captures."""
import ast
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy_live_observer import checked_capture, live_source_pins
from bridge.diplomacy_effect_observer import pins as r1_pins, full_handle
from bridge.diplomacy_reply_observer import reply_source_pins
from bridge.knowledge_effect_reader import verify_manifest as old_knowledge_pins
from bridge.knowledge_effect_reader_v2 import verify_manifest as v2_pins, evaluate_knowledge_effect
from bridge.tag_command_backend import read, digest, require, validate_identity

REPORT = ROOT/"work/reports/diplomacy-live-observer-20261015-r1/live-80340-knowledge-decoders.json"
EXPECTED_SHA = "9bd00df691e1229bf07ec1b3a9ef6dd260a0c3bcf19c4a8ef70f8dd76664e0ae"
PRODUCER = ROOT/"work/capture_knowledge_observer_live_20261015.py"


def pin(path):
    raw = read(path, 16*1024*1024)
    return {"bytes": len(raw), "sha256": digest(raw)}


def main():
    raw = read(REPORT, 128*1024)
    require(digest(raw) == EXPECTED_SHA and len(raw) == 33634, "Fixed live report changed")
    d = json.loads(raw)
    require(d["schema"] == "EU4-KNOWLEDGE-OBSERVER-LIVE-ACCEPTANCE/1", "Live report schema differs")
    identity = validate_identity(d["identity"])
    require((identity["pid"], identity["creation"]) == (80340, "01dd5c075fcf8c26"), "Recorded target differs")
    require(d["native_session_installed"] is False and d["memory_written"] is False
        and d["active_sharing_effect_tested"] is False and d["institution_completion_verified"] is False,
        "Report scopes differ")
    require(all(type(d[k]) is int and d[k] == 0 for k in ("native_calls", "requests_published", "saves_written", "reloads")),
        "Read-only producer effects differ")
    graphs = {"live": live_source_pins(), "knowledge_v2": v2_pins(), "knowledge_R1": old_knowledge_pins(),
        "reply_R2": reply_source_pins(), "effects_R1": r1_pins()}
    require(d["source_pins"] == graphs["live"], "Retained live source graph differs")
    source_pins = {}
    for graph in graphs.values():
        for name, value in graph.items():
            require(name not in source_pins or source_pins[name] == value, "Conflicting source graphs")
            source_pins[name] = value
    for path in (REPORT, PRODUCER, Path(__file__)):
        source_pins[path.relative_to(ROOT).as_posix()] = pin(path)
    producer_tree = ast.parse(read(PRODUCER, 65536).decode("utf-8"))
    calls = sorted({node.func.attr for node in ast.walk(producer_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)})
    require(not {"publish", "load", "WriteProcessMemory", "CreateRemoteThread", "install", "send"} & set(calls),
        "Producer now contains a native/write/publish call")
    require("capture_knowledge" in calls, "Retained producer no longer captures decoder state")
    expected = [("knowledge_sharing", "FRA", "JOL", "FRA", "JOL"),
        ("ask_knowledge_sharing", "MAL", "FRA", "FRA", "MAL")]
    require(len(d["captures"]) == 2, "Capture count differs")
    rows, previous_time = [], None
    for ordinal, (c, (action, actor, target, provider, recipient)) in enumerate(zip(d["captures"], expected)):
        command = {"request_id": "readonly-decoder-"+action, "action": action, "actor": actor, "target": target}
        state = checked_capture(c, command, identity)
        require(c["source_pins"] == d["source_pins"] and c["research_modules"] == [], "Capture source/module scope differs")
        require(c["atomic_main_thread_snapshot"] is False and c["world_epoch_proven"] is False,
            "Capture falsely claims atomic world evidence")
        require(c["memory_written"] is False and all(type(c[k]) is int and c[k] == 0 for k in
            ("native_calls", "requests_published", "saves_written")), "Capture is not read-only")
        require(state["status"] == "pair_absent_observed" and state["exact_pair_active_verified"] is False,
            "Capture is not an absence observation")
        s, r = state["snapshot"], state["snapshot"]["roots"]
        require(s["provider"]["tag"] == provider and s["recipient"]["tag"] == recipient, "Sharing roles differ")
        require(s["object"] is None and s["institution_completion_verified"] is False
            and s["aggregate_counts_used_as_pair_proof"] is False, "Absence proof scope differs")
        require(r["manual_pause"] == 1 and r["reset"] == r["recalculating"] == r["ironman"] == r["load_source"] == 0,
            "Load/pause/reset guards differ")
        require(r["date"] == s["now_raw"] == 56461512 and r["count"] == r["capacity"] == 1380,
            "Date/country table differs")
        for role, offset in (("provider", 0x2D0), ("recipient", 0x2B8)):
            country = s[role]
            slot, tag = full_handle(int(country["handle"], 16), r["count"], tag=country["tag"])
            require(country["slot"] == slot and tag == country["tag"], "Full country handle differs")
            index = s["indexes"][role]
            require(int(index["container"], 16) == int(country["address"], 16)+0x14F8+offset,
                "Typed sharing container offset differs")
            require(index["vtable_rva"] == "0x1c3a538"
                and type(index["capacity_signed"]) is int and type(index["count_signed"]) is int
                and 0 <= index["count_signed"] <= min(index["capacity_signed"], 256)
                and index["capacity_signed"] <= 4096, "Typed signed capacity/count guard differs")
            require(index["typed_allocation_metadata_verified"] is True
                and index["selected_member"] is False and index["object_pointer"] is None
                and index["count_signed"] == index["capacity_signed"] == 0 and int(index["array"], 16) == 0
                and index["records_sha256"] == digest(b""), "Empty typed index metadata inconsistent")
        g = s["global_bucket"]
        require(g["selected_objects"] == [] and g["iteration"] == 0 and 0 <= g["count"] <= 512,
            "Selected global task membership/iteration differs")
        require(int(g["manager"], 16) == int(r["game"], 16)+0x1BB8
            and int(g["end"], 16)-int(g["begin"], 16) == g["buckets"]*24
            and g["buckets"] == r["count"]
            and int(g["bucket"], 16) == int(g["begin"], 16)+s["provider"]["slot"]*24,
            "Provider global bucket direction/layout differs")
        require(bool(int(g["head"], 16)) == bool(int(g["tail"], 16)) == bool(g["count"]), "Global count/head/tail differs")
        outer, inner = c["rpm_budget"], state["read_budget"]
        for budget in (outer, inner):
            require(0 < budget["calls"] <= 4096 and 0 < budget["bytes"] <= 512*1024
                and 0 < budget["largest_read"] <= 65536, "Read budget exceeded")
        require(outer["calls"] >= inner["calls"] and outer["bytes"] >= inner["bytes"], "Shared outer budget differs")
        current_time = datetime.fromisoformat(c["captured_utc"])
        require(previous_time is None or previous_time <= current_time, "Capture order differs")
        previous_time = current_time
        # Actual retained states have no preparation/dispatch receipt. The pure
        # predicate must not infer an effect from current absence evidence.
        boundary = evaluate_knowledge_effect(action, None, state, {})
        require(boundary["status"] == "unknown" and boundary["selected_effect_verified"] is False,
            "Missing-baseline/receipt boundary incorrectly becomes success")
        rows.append(dict(capture_json_pointer=f"/captures/{ordinal}", command=command,
            identity=identity, provider=s["provider"], recipient=s["recipient"], pair=s["pair"],
            status=state["status"], two_complete_passes_equal=state["passes"][0] == state["passes"][1] == s,
            typed_indexes=s["indexes"], global_bucket=g, now_raw=s["now_raw"], roots=r,
            outer_rpm_budget=outer, inner_decoder_budget=inner, duration_ms=c["duration_ms"],
            current_exact_pair_absence_consistent=True, selected_active_effect_verified=False,
            no_baseline_no_receipt_effect_status=boundary["status"]))
    require(datetime.fromisoformat(d["captured_utc"]) >= previous_time, "Report predates final capture")
    require(rows[0]["provider"] == rows[1]["provider"] and rows[0]["roots"] == rows[1]["roots"]
        and rows[0]["global_bucket"] == rows[1]["global_bucket"], "Same provider/world captures differ")
    result = dict(schema="EU4-KNOWLEDGE-DECODER-INDEPENDENT-FILE-AUDIT/1", audit_status="passed",
        scope="Two retained exact current absence decoder captures, not dispatch/effect acceptance",
        input_report_sha256=EXPECTED_SHA, source_pins=source_pins, checked_source_pin_count=len(source_pins),
        frozen_live_graph_pin_count=len(graphs["live"]), frozen_sources_verified=True,
        producer_attribute_calls=calls, read_only_producer_source_consistent=True,
        captures=rows, decoder_current_absence_cases_passed=2, selected_active_effect_cases_tested=0,
        prepare_timing_baseline_verified=False, native_dispatch_verified=False, installed_session_verified=False,
        institution_completion_verified=False, saved_state_verified=False, cold_reload_verified=False,
        exact_external_request_id_causality_verified=False, AI_acceptance_verified=False,
        raw_RPM_decoder_independent_reexecution_performed=False,
        audit_game_process_accessed=False, audit_native_calls=0, audit_requests_published=0,
        audit_saves_written=0, audit_memory_written=False, automatic_command_retry=False,
        limitations=["Metadata/source consistency only: retained report does not contain a complete raw RPM byte transcript.",
            "Source pins establish which decoder guards produced the report; this audit does not read live memory.",
            "The nonce identity is not a TAG installation, dispatch receipt or immutable pre-publication prepare baseline.",
            "Provider global bucket count17 is not selected-pair sharing evidence; both selected typed indexes and selected global set are empty.",
            "Capture durations145.127/148.836ms exceed100ms; no atomic game-thread snapshot or world epoch is claimed.",
            "Report producer's first failed run wrote no retained report; only this fixed successful report is audited."])
    out = REPORT.parent/"independent-live-decoder-file-audit.json"
    output_raw = (json.dumps(result, ensure_ascii=True, indent=2)+"\n").encode("ascii")
    with out.open("xb") as stream:
        stream.write(output_raw)
    md = REPORT.parent/"independent-live-decoder-file-audit.md"
    text = ("# Independent knowledge decoder file audit\n\n"
        "Two current absence cases are consistent with the frozen decoder: FRA→JOL offer has provider FRA/recipient JOL; MAL→FRA ask has provider FRA/recipient MAL. All full handles, typed index offsets and direction agree.\n\n"
        "Each case contains two identical complete passes. Both selected indexes have vt RVA1c3a538, data0/capacity0/count0 and no selected object. The common FRA global bucket contains17 unrelated tasks and no selected sharing object; total count is not used as pair proof.\n\n"
        f"{len(source_pins)} fixed input/source pins passed, including the original report SHA{EXPECTED_SHA}. Each capture used1609 reads/25312B within shared4096/512KiB limits. Durations145.127 and148.836ms must not be reported as≤100ms.\n\n"
        "This is decoder/current-absence acceptance only. The random nonce is not an installed TAG session or a prepare baseline; no dispatch receipt, new active sharing effect, institution adoption, save or cold reload is verified. Missing baseline/receipt evaluates unknown. No game process was accessed by this audit. The retained JSON lacks a complete raw RPM transcript, so source and decoded metadata were independently checked without claiming raw-memory decoder replay.\n")
    with md.open("x", encoding="utf-8") as stream:
        stream.write(text)
    print(json.dumps({"audit": str(out), "bytes": len(output_raw), "sha256": digest(output_raw),
        "markdown": {"path": str(md), **pin(md)}, "checked_source_pins": len(source_pins),
        "cases": 2, "active_effect_cases": 0, "game_process_accessed": False}))


if __name__ == "__main__":
    main()
