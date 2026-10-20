"""File-only positive/negative exact sharing decoder acceptance audit."""
import ast
from datetime import datetime
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "work"))
from discover_diplomacy import check_memory_budget
from bridge.diplomacy_live_observer import checked_capture, live_source_pins
from bridge.diplomacy_effect_observer import pins as effect_pins, full_handle, ptr
from bridge.diplomacy_reply_observer import reply_source_pins
from bridge.knowledge_effect_reader import verify_manifest as knowledge_v1_pins, _object
from bridge.knowledge_effect_reader_v2 import verify_manifest as knowledge_v2_pins, evaluate_knowledge_effect
from bridge.tag_command_backend import read, digest, require, validate_identity

DIR = ROOT / "work/reports/diplomacy-live-observer-20261015-r1"
REPORT = DIR / "live-80340-existing-active-sharing.json"
EXPECTED_SHA = "aafcdd139496ffa912fe965a231b25d6dac4edd9cb3136cc7dd128f7a4a43b2c"
PRODUCER = ROOT / "work/capture_existing_knowledge_pairs_20261015.py"
DISCOVERY = ROOT / "work/reports/knowledge-nearby-candidates-20261015/live-selected-pairs.json"
ABSENCE = DIR / "live-80340-knowledge-decoders.json"
ABSENCE_AUDIT = DIR / "independent-live-decoder-file-audit.json"


def pin(path):
    raw = read(path, 16 * 1024 * 1024)
    return dict(bytes=len(raw), sha256=digest(raw))


class RetainedObjectBytes:
    """Exactly one retained JSON byte range, never a process memory port."""
    def __init__(self, address, raw):
        self.address, self.raw = address, raw
        self.calls = 0

    def read(self, address, size):
        require(address == self.address and size == len(self.raw), "Unexpected retained object range")
        self.calls += 1
        return self.raw


def index_guard(index, country, offset, country_count):
    require(int(index["container"], 16) == int(country["address"], 16) + 0x14f8 + offset,
        "Sharing index container direction differs")
    require(index["vtable_rva"] == "0x1c3a538" and index["typed_allocation_metadata_verified"] is True,
        "Typed sharing metadata unavailable")
    cap, count = index["capacity_signed"], index["count_signed"]
    require(type(cap) is int and type(count) is int and 0 <= count <= min(cap, 256) and cap <= 4096,
        "Typed sharing count/capacity differs")
    array = int(index["array"], 16)
    require((cap == 0 and array == 0) or (cap > 0 and 0x10000 <= array < array + cap * 16 <= 2**47),
        "Sharing array allocation metadata invalid")
    slot, tag = full_handle(int(country["handle"], 16), country_count, tag=country["tag"])
    require((slot, tag) == (country["slot"], country["tag"]), "Country generation/tag/slot differs")


def main():
    raw = read(REPORT, 128 * 1024)
    require(len(raw) == 67947 and digest(raw) == EXPECTED_SHA, "Fixed active decoder report changed")
    data = json.loads(raw)
    require(data["schema"] == "EU4-KNOWLEDGE-EXISTING-PAIR-ACCEPTANCE/1", "Active acceptance schema differs")
    identity = validate_identity(data["identity"])
    require((identity["pid"], identity["creation"]) == (80340, "01dd5c075fcf8c26"), "Process identity differs")
    require(data["memory_written"] is False and data["new_API_effect_tested"] is False
        and data["institution_completion_verified"] is False
        and data["exact_external_request_id_causality_verified"] is False, "Scope flags differ")
    require(all(type(data[k]) is int and data[k] == 0 for k in
        ("native_calls", "requests_published", "saves_written", "reloads")), "Producer report is not read-only")
    graphs = {"live": live_source_pins(), "knowledge_v2": knowledge_v2_pins(),
        "knowledge_R1": knowledge_v1_pins(), "reply_R2": reply_source_pins(), "effects_R1": effect_pins()}
    require(data["source_pins"] == graphs["live"], "Active capture source graph differs")
    sources = {}
    for graph in graphs.values():
        for name, value in graph.items():
            require(name not in sources or sources[name] == value, "Conflicting frozen source graphs")
            sources[name] = value
    require(pin(ABSENCE_AUDIT) == {"bytes": 19198,
        "sha256": "57cffcf85498309331133eef37ea2a6b12eca5c1b2a5e58ed3bdb4a6369adaed"}, "Prior absence audit changed")
    require(pin(ABSENCE) == {"bytes": 33634,
        "sha256": "9bd00df691e1229bf07ec1b3a9ef6dd260a0c3bcf19c4a8ef70f8dd76664e0ae"}, "Prior absence capture changed")
    negative_audit = json.loads(read(ABSENCE_AUDIT, 128 * 1024))
    negative = json.loads(read(ABSENCE, 128 * 1024))
    require(negative_audit["audit_status"] == "passed" and negative_audit["decoder_current_absence_cases_passed"] == 2
        and negative_audit["selected_active_effect_cases_tested"] == 0, "Prior negative acceptance differs")
    for name, value in negative_audit["source_pins"].items():
        require(pin(ROOT / name) == value, "Prior absence audit input changed: " + name)
        sources[name] = value
    discovery_raw = read(DISCOVERY, 1024 * 1024)
    require(digest(discovery_raw) == data["discovery_source_sha256"], "Discovery seed source changed")
    discovery_seed = json.loads(discovery_raw)
    require(discovery_seed["identity"]["pid"] == identity["pid"]
        and discovery_seed["identity"]["creation"] == identity["creation"], "Seed process identity differs")
    for path in (REPORT, PRODUCER, DISCOVERY, ABSENCE, ABSENCE_AUDIT, Path(__file__)):
        sources[path.relative_to(ROOT).as_posix()] = pin(path)
    tree = ast.parse(read(PRODUCER, 65536).decode("utf-8"))
    attributes = sorted({n.func.attr for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)})
    require(not {"publish", "load", "WriteProcessMemory", "CreateRemoteThread", "install", "send"} & set(attributes),
        "Producer gained a native/write/publication operation")
    require("capture_knowledge" in attributes and "identity_check" in attributes, "Producer capture guards differ")
    require(any(isinstance(n, ast.With) and any(isinstance(x.context_expr, ast.Call)
        and isinstance(x.context_expr.func, ast.Name) and x.context_expr.func.id == "KnowledgeRuntimeCapture"
        for x in n.items) for n in ast.walk(tree)), "Held reader context release path differs")
    expected = [("knowledge_sharing", "MOS", "NOG", "MOS", "NOG", 174.799),
        ("ask_knowledge_sharing", "YAS", "TIM", "TIM", "YAS", 157.298),
        ("knowledge_sharing", "MNG", "SYG", "MNG", "SYG", 155.118)]
    require(len(data["captures"]) == len(data["discoveries"]) == 3, "Active/discovery case count differs")
    rows, roots_seen, image_bases = [], [], set()
    previous_time = None
    combined_calls, combined_bytes = data["discovery_read_budget"]["calls"], data["discovery_read_budget"]["bytes"]
    require((combined_calls, combined_bytes) == (75, 978), "Discovery budget differs")
    for ordinal, (capture, discovery, expected_case) in enumerate(zip(data["captures"], data["discoveries"], expected)):
        action, actor, target, provider_tag, recipient_tag, duration = expected_case
        command = dict(request_id="readonly-existing-" + actor + "-" + target,
            action=action, actor=actor, target=target)
        state = checked_capture(capture, command, identity)
        require(capture["source_pins"] == graphs["live"] and capture["research_modules"] == [], "Capture source/modules differ")
        require(capture["atomic_main_thread_snapshot"] is False and capture["world_epoch_proven"] is False,
            "Capture falsely claims atomic world proof")
        require(capture["memory_written"] is False and all(type(capture[k]) is int and capture[k] == 0
            for k in ("native_calls", "requests_published", "saves_written")), "Capture is not read-only")
        require(state["status"] == "active_pair_observed" and state["exact_pair_active_verified"] is True,
            "Selected active status differs")
        selected, root = state["snapshot"], state["snapshot"]["roots"]
        roots_seen.append(root)
        require(root["manual_pause"] == 1 and root["reset"] == root["recalculating"] == root["load_source"] == root["ironman"] == 0,
            "Pause/reset/load guards differ")
        require(root["date"] == selected["now_raw"] == 56461512 and root["count"] == root["capacity"] == 1380,
            "Date/country table differs")
        require((selected["provider"]["tag"], selected["recipient"]["tag"]) == (provider_tag, recipient_tag),
            "Provider/recipient orientation differs")
        require(selected["institution_completion_verified"] is False
            and selected["aggregate_counts_used_as_pair_proof"] is False
            and selected["special_flag_40_termination_context_unresolved"] is False, "Proof scope differs")
        obj = selected["object"]
        obj_address = ptr(int(obj["address"], 16))
        for role, other, offset in (("provider", "recipient", 0x2d0), ("recipient", "provider", 0x2b8)):
            index = selected["indexes"][role]
            index_guard(index, selected[role], offset, root["count"])
            require(index["count_signed"] == index["capacity_signed"] == 1
                and index["selected_member"] is True and index["object_pointer"] == obj["address"],
                "Active selected index member differs")
            # These retained captures contain exactly one index entry. Its
            # semantic entry, including zero padding, reproduces the recorded
            # complete-record hash, independently of the decoder projection.
            entry = struct.pack("<i4xQ", selected[other]["slot"], obj_address)
            require(digest(entry) == index["records_sha256"], "Single typed record hash differs")
        require(discovery["historical_object_pointer_dereferenced"] is False
            and discovery["provider"] == selected["provider"]
            and discovery["current_counterparts"] == [selected["recipient"]], "Current counterpart discovery differs")
        seed_country = discovery_seed["passes"][0]["countries"][provider_tag]["country"]
        require(seed_country["handle"] == selected["provider"]["handle"], "Revalidated provider seed handle differs")
        discovery_index = dict(discovery["index"])
        require(discovery_index.pop("object_pointer") is None and discovery_index.pop("selected_member") is False,
            "Discovery unexpectedly claims selected object membership")
        observed_index = dict(selected["indexes"]["provider"])
        observed_index.pop("object_pointer")
        observed_index.pop("selected_member")
        require(discovery_index == observed_index, "Discovery typed index changed before strict capture")
        object_raw = bytes.fromhex(obj["raw_header_hex"])
        require(len(object_raw) == 0x48, "Selected object header size differs")
        base = struct.unpack_from("<Q", object_raw)[0] - int(obj["vtable_rva"], 16)
        ptr(base)
        image_bases.add(base)
        replay = RetainedObjectBytes(obj_address, object_raw)
        require(_object(replay, base, obj_address, root["count"], selected["now_raw"]) == obj and replay.calls == 1,
            "Retained raw typed object replay differs")
        require(obj["vtable_rva"] == "0x1cde0a0" and obj["marker"] == 357 and obj["token"] == 0x3776
            and obj["provider_handle"] == selected["provider"]["handle"]
            and obj["recipient_handle"] == selected["recipient"]["handle"], "Typed task endpoints/kind differ")
        require(0 < obj["start_raw"] <= selected["now_raw"] < obj["deadline_raw"]
            and obj["expired"] is False and obj["removed_byte_28"] == obj["insertion_failed_byte_29"] == obj["raw_flag_40"] == 0,
            "Active lifecycle/deadline differs")
        global_bucket = selected["global_bucket"]
        require(global_bucket["selected_objects"] == [obj] and global_bucket["iteration"] == 0
            and 0 < global_bucket["count"] <= 512, "Global selected typed object differs")
        require(int(global_bucket["manager"], 16) == int(root["game"], 16) + 0x1bb8
            and int(global_bucket["end"], 16) - int(global_bucket["begin"], 16) == global_bucket["buckets"] * 24
            and global_bucket["buckets"] == root["count"]
            and int(global_bucket["bucket"], 16) == int(global_bucket["begin"], 16) + selected["provider"]["slot"] * 24,
            "Provider-oriented global bucket layout differs")
        require(int(global_bucket["head"], 16) != 0 and int(global_bucket["tail"], 16) != 0,
            "Global current active bucket lacks endpoints")
        for budget in (capture["rpm_budget"], state["read_budget"]):
            require(budget["limits"] == dict(calls=4096, bytes=524288, single_read=65536)
                and 0 < budget["calls"] <= 4096 and 0 < budget["bytes"] <= 524288
                and 0 < budget["largest_read"] <= 65536, "Reader budget differs")
        require(capture["rpm_budget"]["calls"] >= state["read_budget"]["calls"]
            and capture["rpm_budget"]["bytes"] >= state["read_budget"]["bytes"], "Outer shared budget omits inner capture")
        combined_calls += capture["rpm_budget"]["calls"]
        combined_bytes += capture["rpm_budget"]["bytes"]
        require(capture["duration_ms"] == duration, "Recorded duration differs")
        stamp = datetime.fromisoformat(capture["captured_utc"])
        require(previous_time is None or stamp >= previous_time, "Capture order differs")
        previous_time = stamp
        boundary = evaluate_knowledge_effect(action, None, state, {})
        require(boundary["status"] == "unknown" and boundary["selected_effect_verified"] is False,
            "Current active pair without baseline/receipt became API effect success")
        rows.append(dict(capture_json_pointer=f"/captures/{ordinal}", command=command,
            status=state["status"], provider=selected["provider"], recipient=selected["recipient"],
            indexes=selected["indexes"], global_bucket=global_bucket, object=obj,
            two_complete_passes_equal=True, current_exact_pair_active_consistent=True,
            selected_raw_object_header_replay_performed=True, single_index_entry_hash_reconstructed=True,
            discovery_revalidated_current_handles=True, now_raw=selected["now_raw"],
            duration_ms=duration, outer_rpm_budget=capture["rpm_budget"], inner_decoder_budget=state["read_budget"],
            no_baseline_no_receipt_effect_status=boundary["status"], selected_API_effect_verified=False))
    require(len(image_bases) == 1 and all(r == roots_seen[0] for r in roots_seen), "Captured world/base differs")
    require(datetime.fromisoformat(data["captured_utc"]) >= previous_time, "Report predates last capture")
    require((combined_calls, combined_bytes) == (849, 12486), "Producer aggregate read accounting differs")
    require(combined_calls <= 4096 and combined_bytes <= 524288, "Discovery+all selected captures exceed aggregate bound")
    negatives = []
    for c in negative["captures"]:
        state = checked_capture(c, c["command"], negative["identity"])
        require(state["status"] == "pair_absent_observed" and state["snapshot"]["object"] is None
            and state["exact_pair_active_verified"] is False, "Prior current absence case changed")
        require(state["snapshot"]["roots"] == roots_seen[0], "Positive/negative snapshots have different recorded roots")
        negatives.append(dict(command=c["command"], status=state["status"],
            provider=state["snapshot"]["provider"]["tag"], recipient=state["snapshot"]["recipient"]["tag"]))
    result = dict(schema="EU4-KNOWLEDGE-EXISTING-PAIR-INDEPENDENT-FILE-AUDIT/1", audit_status="passed",
        scope="Three current active exact-pair captures plus unchanged two prior absence cases; decoder acceptance only",
        fixed_input_sha256=EXPECTED_SHA, source_pins=sources, checked_source_pin_count=len(sources),
        frozen_source_graphs_verified=True, producer_attribute_calls=attributes,
        read_only_producer_source_consistent=True, held_context_manager_release_source_consistent=True,
        captures=rows, unchanged_negative_decoder_cases=negatives,
        decoder_current_active_cases_passed=3, decoder_current_absence_cases_passed=2,
        total_current_state_decoder_cases=5, selected_new_API_effect_cases_tested=0,
        producer_total_discovery_plus_capture_budget=dict(calls=combined_calls, bytes=combined_bytes,
            note="Discovery has a separate BudgetReader; this is retained aggregate accounting, not a claim that all calls used one budget object."),
        recorded_shared_image_base=hex(next(iter(image_bases))), recorded_roots=roots_seen[0],
        task_kind_0x3776_is_external_request_id=False, prepare_baseline_verified=False,
        native_dispatch_verified=False, AI_acceptance_verified=False, institution_completion_verified=False,
        saved_state_verified=False, cold_reload_verified=False, world_epoch_proven=False,
        exact_external_request_id_causality_verified=False,
        raw_RPM_decoder_full_reexecution_performed=False, retained_selected_object_header_replay_performed=True,
        audit_game_process_accessed=False, audit_native_calls=0, audit_requests_published=0,
        audit_saves_written=0, audit_memory_written=False, old_tests_rerun=False,
        resources=dict(audit_peak_committed_bytes=check_memory_budget(), memory_limit_bytes=768 * 1024 * 1024),
        limitations=["Active pairs pre-existed observation; there is no pre-publication prepare baseline or original dispatch receipt.",
            "Task token0x3776 is the native kind getter constant, shared by all three tasks; it cannot identify an external request.",
            "The72B selected raw headers and singleton index record hashes are replayable, but full global list node raw bytes and all RPM reads are not retained.",
            "Global membership metadata and typed guards are source-checked, not a complete independent memory transcript replay.",
            "Durations174.799/157.298/155.118ms exceed100ms; consistent two passes do not prove an atomic game-thread snapshot or immutable world epoch.",
            "No institution adoption, persistence, save/cold reload, AI acceptance or new API success is established."])
    output = DIR / "independent-existing-sharing-file-audit.json"
    output_raw = (json.dumps(result, ensure_ascii=True, indent=2) + "\n").encode("ascii")
    with output.open("xb") as stream:
        stream.write(output_raw)
    markdown = DIR / "independent-existing-sharing-file-audit.md"
    text = ("# Current knowledge-sharing decoder file audit\n\n"
        "Three positive current-state cases passed: MOS→NOG offer (providerMOS), YAS→TIM ask (providerTIM), and MNG→SYG offer (providerMNG). All complete handles and directions agree. Both typed indexes have vt1C3A538/data/capacity1/count1 and point to the exact same typed task found in the provider global bucket. Each full two-pass snapshot is equal.\n\n"
        "The selected72B raw task headers replay exactly: vt1CDE0A0/marker357/full endpoints, future raw deadline, removed28=failed29=flag40=0. Singleton index record hashes also reproduce. The common token3776 is a task-kind constant, not an external request ID. Full global node/RPM transcript replay is unavailable.\n\n"
        f"{len(sources)} fixed input/source pins passed. Report SHA{EXPECTED_SHA}. Discovery plus all three captures total849 reads/12486B; individual strict capture budgets remain below4096/512KiB. Durations174.799/157.298/155.118ms are not≤100ms.\n\n"
        "Together with the unchanged earlier FRA→JOL and MAL→FRA absence observations, this provides3 active+2 absent decoder acceptance cases. It verifies zero new API effects: there is no prepare baseline or dispatch receipt, and the pure effect predicate remains unknown. No institution adoption, AI acceptance, exact request causality, atomic world epoch, save or cold reload is claimed. This audit did not access the game or rerun old tests.\n")
    with markdown.open("x", encoding="utf-8") as stream:
        stream.write(text)
    print(json.dumps(dict(audit=pin(output), markdown=pin(markdown), source_pins=len(sources),
        active_cases=3, absence_cases=2, new_API_effect_cases=0, game_process_accessed=False)))


if __name__ == "__main__":
    main()
